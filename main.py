import os
import sys
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext
import ttkthemes
from PIL import Image, ImageTk
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import yt_dlp
from moviepy.editor import VideoFileClip
import re
import json
import sv_ttk
import queue
import threading
import uuid
import unicodedata

class CustomTooltip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip = None
        self.widget.bind("<Enter>", self.show_tooltip)
        self.widget.bind("<Leave>", self.hide_tooltip)

    def show_tooltip(self, event=None):
        x, y, _, _ = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 20

        self.tooltip = tk.Toplevel(self.widget)
        self.tooltip.wm_overrideredirect(True)
        self.tooltip.wm_geometry(f"+{x}+{y}")

        label = ttk.Label(self.tooltip, text=self.text, justify='left',
                         background="#363636", foreground="white",
                         padding=(10, 5))
        label.pack()

    def hide_tooltip(self, event=None):
        if self.tooltip:
            self.tooltip.destroy()
            self.tooltip = None

class Logger:
    def __init__(self, text_widget):
        self.text_widget = text_widget

    def log(self, message, level="INFO"):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        level_colors = {
            "INFO": "#4CAF50",
            "ERROR": "#FF5252",
            "WARNING": "#FFB74D",
            "SUCCESS": "#66BB6A"
        }
        
        self.text_widget.configure(state='normal')
        self.text_widget.insert(tk.END, f"[{timestamp}] ", "timestamp")
        self.text_widget.insert(tk.END, f"[{level}] ", f"level_{level.lower()}")
        self.text_widget.insert(tk.END, f"{message}\n", "message")
        
        self.text_widget.see(tk.END)
        self.text_widget.configure(state='disabled')

class YouTubeShortsAutoPost:
    def __init__(self):
        self.upload_queue = queue.Queue()
        self.is_processing = False
        
        self.SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
        self.api_service_name = "youtube"
        self.api_version = "v3"
        self.client_secrets_file = "client_secrets.json"
        self.credentials = None
        self.youtube = None
        
        # Basic yt-dlp options
        self.ydl_opts = {
            'format': 'best',
            'outtmpl': 'downloads/%(id)s.%(ext)s',
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'DNT': '1',
                'Connection': 'keep-alive',
            },
        }
        
        # Initialize platform-specific options
        self.platform_opts = {
            'TikTok': {
                'format': 'best',
                'force_generic_extractor': False,
                'extractor_args': {
                    'tiktok': {
                        'embed_url': None,
                        'api_hostname': 'api16-normal-c-useast1a.tiktokv.com',
                        'app_version': '1.0.0',
                        'manifest_app_version': '1.0.0'
                    }
                }
            },
            'Instagram': {
                'format': 'best',
                'force_generic_extractor': False,
                'extract_flat': True
            },
            'Facebook': {
                'format': 'best',
                'force_generic_extractor': False,
                'extract_flat': True
            }
        }
        
        self.setup_gui()
        
    def setup_gui(self):
        self.root = tk.Tk()
        self.root.title("YouTube Shorts Auto Uploader")
        self.root.geometry("1200x800")
        self.root.iconbitmap("icon.ico")
        
        sv_ttk.set_theme("dark")
        
        self.title_font = ('Segoe UI', 24, 'bold')
        self.header_font = ('Segoe UI', 12, 'bold')
        self.text_font = ('Segoe UI', 10)

        # Create main canvas with scrollbar
        self.canvas = tk.Canvas(self.root)
        scrollbar = ttk.Scrollbar(self.root, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)

        # Configure canvas
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)

        # Pack main scrollable components
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Add mousewheel scrolling
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        
        # Main container inside scrollable frame
        main_container = ttk.Frame(self.scrollable_frame)
        main_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        header_frame = ttk.Frame(main_container)
        header_frame.pack(fill=tk.X, pady=(0, 20))
        
        title_label = ttk.Label(
            header_frame,
            text="YouTube Shorts Auto Uploader",
            font=self.title_font,
            foreground='#FFFFFF'
        )
        title_label.pack(pady=20)

        content_frame = ttk.Frame(main_container)
        content_frame.pack(fill=tk.BOTH, expand=True)
        content_frame.grid_columnconfigure(0, weight=3)
        content_frame.grid_columnconfigure(1, weight=2)

        left_panel = self.create_left_panel(content_frame)
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        right_panel = self.create_right_panel(content_frame)
        right_panel.grid(row=0, column=1, sticky="nsew", padx=(10, 0))

    def _on_mousewheel(self, event):
        """Handle mousewheel scrolling"""
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")

    def create_left_panel(self, parent):
        left_frame = ttk.Frame(parent)
        
        # Authentication Section
        auth_frame = ttk.LabelFrame(
            left_frame,
            text="Authentication",
            padding=15
        )
        auth_frame.pack(fill=tk.X, pady=(0, 15))

        self.login_button = ttk.Button(
            auth_frame,
            text="Connect to YouTube",
            command=self.authenticate,
            style='Accent.TButton'
        )
        self.login_button.pack(pady=10)
        CustomTooltip(self.login_button, "Click to authenticate with your YouTube account")

        # Upload Settings Section
        upload_frame = ttk.LabelFrame(
            left_frame,
            text="Upload Settings",
            padding=15
        )
        upload_frame.pack(fill=tk.X, pady=(0, 15))

        # Source Selection
        source_frame = ttk.Frame(upload_frame)
        source_frame.pack(fill=tk.X, pady=(0, 10))
        
        source_label = ttk.Label(
            source_frame,
            text="Source Platform",
            font=self.header_font
        )
        source_label.pack(anchor='w')
        
        self.source_var = tk.StringVar()
        sources = ttk.Combobox(
            source_frame,
            textvariable=self.source_var,
            values=('Instagram', 'Facebook', 'TikTok', 'Local File'),
            state='readonly',
            font=self.text_font
        )
        sources.pack(fill=tk.X, pady=(5, 0))
        CustomTooltip(sources, "Select the source platform for your video")

        # Privacy Setting
        privacy_frame = ttk.Frame(upload_frame)
        privacy_frame.pack(fill=tk.X, pady=10)
        
        privacy_label = ttk.Label(
            privacy_frame,
            text="Video Privacy",
            font=self.header_font
        )
        privacy_label.pack(side=tk.LEFT, padx=(0, 10))
        
        self.privacy_var = tk.StringVar(value="private")
        self.privacy_switch = ttk.Checkbutton(
            privacy_frame,
            text="Public",
            variable=self.privacy_var,
            onvalue="public",
            offvalue="private"
        )
        self.privacy_switch.pack(side=tk.LEFT)
        CustomTooltip(self.privacy_switch, "Toggle between public and private upload")

        # URLs Input
        url_frame = ttk.Frame(upload_frame)
        url_frame.pack(fill=tk.X, pady=10)
        
        url_label = ttk.Label(
            url_frame,
            text="Video URLs (one per line)",
            font=self.header_font
        )
        url_label.pack(anchor='w')
        
        self.url_text = tk.Text(
            url_frame,
            height=6,
            font=self.text_font,
            wrap=tk.WORD
        )
        self.url_text.pack(fill=tk.X, pady=(5, 0))
        CustomTooltip(self.url_text, "Enter multiple URLs, one per line")
        
        browse_btn = ttk.Button(
            url_frame,
            text="Browse Files",
            command=self.browse_files,
            style='Accent.TButton'
        )
        browse_btn.pack(anchor='e', pady=(5, 0))

        # Title Input
        title_frame = ttk.Frame(upload_frame)
        title_frame.pack(fill=tk.X, pady=10)
        
        title_label = ttk.Label(
            title_frame,
            text="Video Title Template",
            font=self.header_font
        )
        title_label.pack(anchor='w')
        
        self.title_entry = ttk.Entry(
            title_frame,
            font=self.text_font
        )
        self.title_entry.pack(fill=tk.X, pady=(5, 0))
        CustomTooltip(self.title_entry, "Enter title template. Use {number} for auto-numbering")

        # Caption Input
        caption_frame = ttk.Frame(upload_frame)
        caption_frame.pack(fill=tk.X, pady=10)
        
        caption_label = ttk.Label(
            caption_frame,
            text="Video Description",
            font=self.header_font
        )
        caption_label.pack(anchor='w')
        
        self.caption_text = tk.Text(
            caption_frame,
            height=6,
            font=self.text_font,
            wrap=tk.WORD
        )
        self.caption_text.pack(fill=tk.X, pady=(5, 0))
        CustomTooltip(self.caption_text, "Enter the description for your YouTube Shorts")

        # Upload Button
        self.upload_btn = ttk.Button(
            upload_frame,
            text="Upload to YouTube Shorts",
            command=self.start_batch_upload,
            style='Accent.TButton'
        )
        self.upload_btn.pack(pady=(20, 10))
        CustomTooltip(self.upload_btn, "Click to start the batch upload process")

        return left_frame

    def create_right_panel(self, parent):
        right_frame = ttk.LabelFrame(
            parent,
            text="Activity Log",
            padding=15
        )
        
        self.log_text = scrolledtext.ScrolledText(
            right_frame,
            height=30,
            font=('Consolas', 10),
            wrap=tk.WORD
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        self.log_text.tag_configure("timestamp", foreground="#888888")
        self.log_text.tag_configure("level_info", foreground="#4CAF50")
        self.log_text.tag_configure("level_error", foreground="#FF5252")
        self.log_text.tag_configure("level_warning", foreground="#FFB74D")
        self.log_text.tag_configure("level_success", foreground="#66BB6A")
        self.log_text.tag_configure("message", foreground="#FFFFFF")
        
        self.logger = Logger(self.log_text)
        
        return right_frame

    def browse_files(self):
        """Open file browser for multiple local video selection."""
        filenames = filedialog.askopenfilenames(
            filetypes=[("Video files", "*.mp4 *.mov *.avi *.mkv")])
        if filenames:
            self.url_text.delete("1.0", tk.END)
            self.url_text.insert("1.0", "\n".join(filenames))

    def start_batch_upload(self):
        """Initialize the batch upload process."""
        if not self.youtube:
            self.logger.log("Please login to YouTube first", "ERROR")
            return
            
        source = self.source_var.get()
        if not source:
            self.logger.log("Please select a source platform", "ERROR")
            return
            
        # Get URLs and filter empty lines
        urls = [url.strip() for url in self.url_text.get("1.0", tk.END).strip().split("\n") if url.strip()]
        
        if not urls:
            self.logger.log("Please provide at least one URL or file", "ERROR")
            return
            
        self.logger.log(f"Processing {len(urls)} videos for upload...", "INFO")
        
        # Clear the queue while ensuring thread safety
        with self.upload_queue.mutex:
            self.upload_queue.queue.clear()
            
        # Add all URLs to the queue
        for i, url in enumerate(urls, 1):
            title_template = self.title_entry.get() or "Short {number}"
            title = title_template.replace("{number}", str(i))
            
            self.upload_queue.put({
                'url': url,
                'source': source,
                'title': title,
                'caption': self.caption_text.get("1.0", tk.END).strip(),
                'privacy': self.privacy_var.get()
            })
            
        # Start processing if not already running
        if not self.is_processing:
            self.is_processing = True
            self.upload_btn.configure(state='disabled')
            threading.Thread(target=self.process_queue, daemon=True).start()

    def process_queue(self):
        """Process the upload queue."""
        try:
            while not self.upload_queue.empty():
                upload_data = self.upload_queue.get()
                
                try:
                    self.logger.log(f"Processing: {upload_data['url']}")
                    
                    # Download video
                    video_file = self.download_video(upload_data['url'], upload_data['source'])
                    
                    # Clean metadata if not local file
                    if upload_data['source'] != "Local File":
                        video_file = self.clean_metadata(video_file)
                    
                    # Upload to YouTube
                    video_id = self.upload_to_youtube(
                        video_file,
                        upload_data['title'],
                        upload_data['caption'],
                        upload_data['privacy']
                    )
                    
                    self.logger.log(f"✅ Upload successful! Video ID: {video_id}", "SUCCESS")
                    
                    # Clean up downloaded file if it's not a local file
                    if upload_data['source'] != "Local File" and os.path.exists(video_file):
                        os.remove(video_file)
                        
                except Exception as e:
                    self.logger.log(f"❌ Error processing {upload_data['url']}: {str(e)}", "ERROR")
                    
                self.upload_queue.task_done()
                
        finally:
            self.is_processing = False
            self.root.after(0, lambda: self.upload_btn.configure(state='normal'))
            self.logger.log("Batch upload process completed", "SUCCESS")

    def upload_to_youtube(self, video_file, title, caption, privacy_status):
        """Upload video to YouTube as a Short."""
        try:
            self.logger.log("Preparing upload to YouTube...")
            
            body = {
                'snippet': {
                    'title': title or f"Short - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    'description': caption,
                    'tags': ['Short'],
                    'categoryId': '22'
                },
                'status': {
                    'privacyStatus': privacy_status,
                    'selfDeclaredMadeForKids': False
                }
            }
            
            media = MediaFileUpload(
                video_file,
                mimetype='video/*',
                resumable=True
            )
            
            self.logger.log("Uploading video...")
            
            request = self.youtube.videos().insert(
                part=','.join(body.keys()),
                body=body,
                media_body=media
            )
            
            response = request.execute()
            self.logger.log("Upload completed successfully!", "SUCCESS")
            return response['id']
            
        except Exception as e:
            self.logger.log(f"Upload failed: {str(e)}", "ERROR")
            raise

    def clean_metadata(self, video_path):
        """Remove metadata from video file with improved filename handling."""
        try:
            self.logger.log("Cleaning video metadata...")
            
            clean_filename = os.path.join(
                os.path.dirname(video_path),
                f"clean_{str(uuid.uuid4())}{os.path.splitext(video_path)[1]}"
            )
            
            video = VideoFileClip(video_path)
            
            video.write_videofile(
                clean_filename,
                codec='libx264',
                audio_codec='aac',
                temp_audiofile=f'temp-{uuid.uuid4()}.m4a',
                remove_temp=True
            )
            
            video.close()
            
            if os.path.exists(video_path):
                os.remove(video_path)
            os.rename(clean_filename, video_path)
            
            self.logger.log("Metadata cleaning completed")
            return video_path
            
        except Exception as e:
            self.logger.log(f"Error cleaning metadata: {str(e)}", "ERROR")
            raise
    
    def clean_title(self, title):
        """Remove hashtags and clean title."""
        title = re.sub(r'#\w+', '', title)
        title = re.sub(r'\s+', ' ', title)
        title = title.strip()
        return title
    
    def sanitize_filename(self, filename):
        """Sanitize filename by removing invalid characters and limiting length."""
        filename = "".join(char for char in filename if char.isalnum() or char in (' ', '-', '_', '.'))
        filename = unicodedata.normalize('NFKD', filename).encode('ASCII', 'ignore').decode('ASCII')
        if len(filename) > 200:
            name, ext = os.path.splitext(filename)
            filename = name[:196] + ext
        return filename

    def get_safe_filename(self, base_path):
        """Generate a safe, unique filename."""
        name, ext = os.path.splitext(base_path)
        counter = 1
        while os.path.exists(base_path):
            base_path = f"{name}_{counter}{ext}"
            counter += 1
        return base_path

    def download_video(self, url, source):
        """Download video from various sources with improved error handling."""
        try:
            if source == "Local File":
                self.logger.log("Using local file...")
                return url
            
            self.logger.log(f"Downloading video from {source}...")
            
            # Create downloads directory if it doesn't exist
            os.makedirs("downloads", exist_ok=True)
            
            # Combine default options with platform-specific options
            current_opts = self.ydl_opts.copy()
            if source in self.platform_opts:
                current_opts.update(self.platform_opts[source])
            
            # Generate a unique filename
            unique_id = str(uuid.uuid4())
            output_template = f'downloads/{unique_id}.%(ext)s'
            current_opts['outtmpl'] = output_template

            try:
                with yt_dlp.YoutubeDL(current_opts) as ydl:
                    # Try to extract info first
                    try:
                        info_dict = ydl.extract_info(url, download=False)
                        if info_dict is None:
                            raise Exception("Could not extract video info")
                    except Exception as e:
                        self.logger.log(f"Info extraction failed, attempting direct download: {str(e)}", "WARNING")
                        info_dict = {'id': unique_id}

                    # Update output template with video ID if available
                    video_id = info_dict.get('id', unique_id)
                    current_opts['outtmpl'] = f'downloads/{video_id}.%(ext)s'
                    
                    # Perform the actual download
                    with yt_dlp.YoutubeDL(current_opts) as ydl_download:
                        info = ydl_download.download([url])
                    
                    # Find the downloaded file
                    downloads_dir = "downloads"
                    downloaded_files = [f for f in os.listdir(downloads_dir) 
                                     if f.startswith(video_id) and os.path.isfile(os.path.join(downloads_dir, f))]
                    
                    if not downloaded_files:
                        raise Exception("Download completed but file not found")
                    
                    video_path = os.path.join(downloads_dir, downloaded_files[0])
                    self.logger.log(f"Download completed: {video_path}")
                    return video_path

            except Exception as e:
                raise Exception(f"Download failed: {str(e)}")
                
        except Exception as e:
            self.logger.log(f"Download failed: {str(e)}", "ERROR")
            raise
    
    def authenticate(self):
        """Authenticate with YouTube API."""
        try:
            self.logger.log("Starting YouTube authentication...")
            
            flow = InstalledAppFlow.from_client_secrets_file(
                self.client_secrets_file, self.SCOPES)
            self.credentials = flow.run_local_server(port=0)
            self.youtube = build(
                self.api_service_name, self.api_version, credentials=self.credentials)
            
            self.logger.log("Authentication successful!", "SUCCESS")
            self.login_button.configure(state='disabled')
            
        except Exception as e:
            self.logger.log(f"Authentication failed: {str(e)}", "ERROR")

if __name__ == "__main__":
    try:
        os.makedirs("downloads", exist_ok=True)
        app = YouTubeShortsAutoPost()
        app.root.mainloop()
    except ImportError as e:
        print("Please install required package: pip install sv-ttk")
        sys.exit(1)