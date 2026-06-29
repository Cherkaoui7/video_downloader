# Video Downloader

A universal web-based video downloader that supports thousands of sites via yt-dlp, with Selenium fallback for dynamic/unsupported sites, and FFmpeg upscaling.

## Features

- **yt-dlp engine** — supports 1000+ sites (YouTube, Vimeo, Dailymotion, etc.)
- **Selenium fallback** — extracts hidden video URLs from iframes and JS-rendered players
- **Cookie support** — upload cookies.txt for age-gated / login-restricted content
- **Quality presets** — 480p, 720p, 1080 HD, 4K UHD
- **FFmpeg upscaling** — if the source is lower quality, the app upscales to your selection
- **Auto-cleanup** — downloaded files are deleted after serving

## Requirements

- Python 3.8+
- Google Chrome (for Selenium fallback)
- FFmpeg (for merging streams and upscaling)

## Installation

### 1. Install FFmpeg

**Windows (using winget):**
```bash
winget install Gyan.FFmpeg
```
Restart your terminal after installation.

**macOS:**
```bash
brew install ffmpeg
```

**Linux:**
```bash
sudo apt install ffmpeg
```

Verify FFmpeg is installed:
```bash
ffmpeg -version
```

### 2. Clone and install dependencies

```bash
git clone https://github.com/Cherkaoui7/video_downloader.git
cd video_downloader
pip install -r requirements.txt
```

### 3. Run the app

```bash
python app.py
```

Open your browser to **http://127.0.0.1:5000**

## Usage

### Basic download

1. Paste any video URL into the input field
2. Select a quality (480p / 720p / 1080 HD / 4K UHD)
3. Click **Download**
4. The file saves to your computer with the original video title

### Cookie upload (for restricted sites)

1. Install a browser extension like "Get cookies.txt" (Chrome / Firefox)
2. Go to the site you want to download from, log in if needed
3. Export cookies as a Netscape-format `cookies.txt` file
4. In the app, click **🍪 Cookies**
5. Click **Choose File** and select your `cookies.txt`
6. The app will use these cookies for all subsequent downloads

### Removing cookies

- Click **🍪 Cookies** → **Remove** to delete uploaded cookies

## How it works

The app attempts downloads in this order:

1. **yt-dlp with headers** — fastest, works for 1000+ sites
2. **yt-dlp with generic extractor** — fallback for unknown sites
3. **HTML scraping** — regex-based extraction of video URLs from page source
4. **Selenium headless browser** — loads the page, scans iframes, extracts video sources

After download, FFmpeg resizes the video to the selected quality if needed.

## Project structure

```
video_downloader/
├── app.py              # Flask backend
├── requirements.txt    # Python dependencies
├── templates/
│   └── index.html      # Frontend UI
├── static/
│   ├── script.js       # Frontend logic
│   └── style.css       # Dark theme UI
├── downloads/          # Temporary files (auto-cleaned)
├── cookies/            # Uploaded cookies.txt
└── README.md
```

## Troubleshooting

**"Unsupported URL" / "403 Forbidden"**
- Try uploading cookies from your browser
- The site may use DRM (Netflix, Disney+, etc.) which cannot be downloaded

**Download shows 400 error**
- Check the server console for detailed error messages
- The URL may be invalid or the site may be blocking automated access

**FFmpeg not found**
- Ensure FFmpeg is installed and accessible from your terminal
- Windows users: restart your terminal after installation
