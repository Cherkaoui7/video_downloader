import os
import re
import shutil
import subprocess
import time
import uuid
import atexit
import requests
import traceback
from flask import Flask, render_template, request, jsonify, send_file, after_this_request
from yt_dlp import YoutubeDL
from urllib.parse import urljoin, urlparse
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024
DOWNLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "downloads")
COOKIE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(COOKIE_DIR, exist_ok=True)

FFMPEG_LOCATION = shutil.which("ffmpeg")
if not FFMPEG_LOCATION:
    candidates = [
        r"C:\Users\USER\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.2-full_build\bin\ffmpeg.exe",
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\ProgramData\chocolatey\bin\ffmpeg.exe",
    ]
    for p in candidates:
        if os.path.isfile(p):
            FFMPEG_LOCATION = p
            break

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)

BASE_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

BASE_YDL_OPTS = {"quiet": True, "no_warnings": True}
if FFMPEG_LOCATION:
    BASE_YDL_OPTS["ffmpeg_location"] = FFMPEG_LOCATION

_selenium_driver = None


def safe_filename(s, max_len=80):
    s = s.strip()[:max_len].rsplit(" ", 1)[0] if len(s) > max_len else s.strip()
    keep = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 -_.")
    return "".join(c if c in keep else "_" for c in s).strip("._ ") or "video"


def get_selenium_driver():
    global _selenium_driver
    if _selenium_driver is None:
        print("[SELENIUM] Initializing ChromeDriver...")
        opts = Options()
        opts.add_argument("--headless=new")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        opts.add_experimental_option("useAutomationExtension", False)
        opts.add_argument(f"user-agent={USER_AGENT}")
        opts.add_argument("--window-size=1920,1080")
        opts.add_argument("--log-level=3")

        service = Service(ChromeDriverManager().install())
        _selenium_driver = webdriver.Chrome(service=service, options=opts)
        _selenium_driver.set_page_load_timeout(45)
        atexit.register(lambda: _selenium_driver.quit())
        print("[SELENIUM] ChromeDriver ready.")
    return _selenium_driver


QUALITY_MAP = {
    "480": "bestvideo[height<=480]+bestaudio/best[height<=480]",
    "720": "bestvideo[height<=720]+bestaudio/best[height<=720]",
    "1080": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
    "4K": "bestvideo[height<=2160]+bestaudio/best[height<=2160]",
}

RESIZE_HEIGHTS = {"480": 480, "720": 720, "1080": 1080, "4K": 2160}


def make_headers(referer=None):
    h = dict(BASE_HEADERS)
    if referer:
        h["Referer"] = referer
        h["Origin"] = urlparse(referer).scheme + "://" + urlparse(referer).netloc
    return h


def resize_video(input_path, output_path, target_height):
    ffmpeg = FFMPEG_LOCATION or "ffmpeg"
    cmd = [
        ffmpeg, "-y", "-i", input_path,
        "-vf", f"scale=-2:{target_height}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        output_path,
    ]
    try:
        subprocess.run(cmd, capture_output=True, timeout=600)
        return os.path.isfile(output_path) and os.path.getsize(output_path) > 0
    except Exception:
        return False


def find_video_urls(page_url):
    try:
        resp = requests.get(page_url, headers=BASE_HEADERS, timeout=15)
        resp.raise_for_status()
        html = resp.text
    except Exception:
        return []

    patterns = [
        r'["\']([^"\']+\.(mp4|webm|mkv|avi|mov)(\?[^"\']*)?)["\']',
        r'["\']([^"\']+(?:video|source|src|file|playlist)[^"\']*\.(m3u8|mpd)(\?[^"\']*)?)["\']',
        r'<(?:video|source|iframe)[^>]+src=["\']([^"\']+)["\']',
        r'["\'](?:file|url|src|link)["\']\s*:\s*["\']([^"\']+)["\']',
    ]

    video_exts = {".mp4", ".webm", ".mkv", ".avi", ".mov", ".m3u8", ".mpd"}
    video_mime = ("video/", "application/vnd.apple.mpegurl", "application/dash+xml")

    seen = set()
    for pat in patterns:
        for m in re.finditer(pat, html, re.IGNORECASE):
            raw = m.group(1)
            absolute = urljoin(page_url, raw)
            if absolute in seen:
                continue
            seen.add(absolute)
            ext = os.path.splitext(urlparse(absolute).path)[1].lower().split("?")[0]
            if ext in video_exts:
                return [absolute]

    candidates = []
    for pat in patterns:
        for m in re.finditer(pat, html, re.IGNORECASE):
            candidates.append(urljoin(page_url, m.group(1)))
    for c in candidates:
        if c in seen:
            continue
        try:
            hr = requests.head(c, headers=BASE_HEADERS, timeout=8, allow_redirects=True)
            ct = hr.headers.get("Content-Type", "")
            if ct.startswith(video_mime):
                return [c]
        except Exception:
            continue
    return []


def extract_with_selenium(page_url):
    print(f"[SELENIUM] Opening page...")
    try:
        driver = get_selenium_driver()
    except Exception as e:
        print(f"[SELENIUM] Driver init failed: {e}")
        return None

    try:
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        try:
            driver.get(page_url)
            print("[SELENIUM] Page loaded")
        except Exception as e:
            print(f"[SELENIUM] Page load warning (continuing): {e}")

        wait = WebDriverWait(driver, 15)
        video_url = None

        # Strategy 1: find player iframe
        print("[SELENIUM] Scanning all iframes...")
        all_iframes = driver.find_elements(By.TAG_NAME, "iframe")
        print(f"[SELENIUM] Found {len(all_iframes)} iframes")
        for i, src in enumerate([f.get_attribute("src") or "" for f in all_iframes]):
            print(f"  iframe [{i}]: {src[:100]}")

        for i in range(len(all_iframes)):
            try:
                driver.switch_to.frame(all_iframes[i])
                time.sleep(2)
                try:
                    video = wait.until(EC.presence_of_element_located((By.TAG_NAME, "video")))
                    video_url = driver.execute_script("return arguments[0].currentSrc || arguments[0].src || '';", video)
                    if not video_url:
                        sources = video.find_elements(By.TAG_NAME, "source")
                        for s in sources:
                            src = s.get_attribute("src")
                            if src:
                                video_url = src
                                break
                    if video_url and (video_url.startswith("http") or video_url.startswith("blob:")):
                        print(f"[SELENIUM] Found video URL in iframe [{i}]: {video_url[:80]}")
                        driver.switch_to.default_content()
                        break
                except Exception:
                    pass
                driver.switch_to.default_content()
            except Exception:
                driver.switch_to.default_content()

        # Strategy 2: direct video on main page
        if not video_url:
            print("[SELENIUM] Checking main page for <video>...")
            try:
                video = wait.until(EC.presence_of_element_located((By.TAG_NAME, "video")))
                video_url = driver.execute_script("return arguments[0].currentSrc || arguments[0].src || '';", video)
                if not video_url:
                    sources = video.find_elements(By.TAG_NAME, "source")
                    for s in sources:
                        src = s.get_attribute("src")
                        if src:
                            video_url = src
                            break
                if video_url:
                    print(f"[SELENIUM] Found video on main page: {video_url[:80]}")
            except Exception as e:
                print(f"[SELENIUM] No <video> on main page: {e}")

        # Strategy 3: regex in page text
        if not video_url:
            print("[SELENIUM] Scanning page text for stream URLs...")
            for js in [
                "return (document.body.innerText.match(/https?:\\/\\/[^\\s\"']+\\.(m3u8|mp4|webm|mkv|ts)[^\\s\"']*/i) || [''])[0];",
            ]:
                found = driver.execute_script(js)
                if found and found.strip():
                    video_url = found.strip()
                    print(f"[SELENIUM] Found stream via regex: {video_url[:80]}")
                    break

        if not video_url:
            print("[SELENIUM] No video URL found")
            return None

        page_title = driver.title or os.path.splitext(os.path.basename(video_url))[0]
        referer = page_url
        origin = f"{urlparse(page_url).scheme}://{urlparse(page_url).netloc}"
        return {"url": video_url.strip(), "origin": origin, "referer": referer, "title": safe_filename(page_title)}

    except Exception as e:
        print(f"[SELENIUM] Error: {e}")
        traceback.print_exc()
        return None


def try_download(url, fmt, outtmpl, uid, cookie_file=None):
    cookie_opts = {}
    if cookie_file and os.path.isfile(cookie_file):
        cookie_opts["cookiefile"] = cookie_file

    # Strategy 1: yt-dlp with headers
    headers = make_headers(url)
    strategies = [
        {**BASE_YDL_OPTS, **cookie_opts, "outtmpl": outtmpl, "merge_output_format": "mp4", "format": fmt, "http_headers": headers},
        {**BASE_YDL_OPTS, **cookie_opts, "outtmpl": outtmpl, "merge_output_format": "mp4", "format": fmt, "http_headers": headers, "force_generic_extractor": True, "referer": url},
    ]

    last_err = None
    for opts in strategies:
        try:
            with YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=True)
        except Exception as e:
            last_err = e
            continue

    # Strategy 2: HTML scrape
    video_urls = find_video_urls(url)
    if video_urls:
        target = video_urls[0]
        ext = target.rsplit(".", 1)[-1].split("?")[0] or "mp4"
        path = outtmpl.replace("%(ext)s", ext)
        try:
            resp = requests.get(target, headers=make_headers(url), stream=True, timeout=30)
            resp.raise_for_status()
            with open(path, "wb") as f:
                for chunk in resp.iter_content(8192):
                    f.write(chunk)
            return {"title": os.path.splitext(os.path.basename(target))[0]}
        except Exception as e:
            last_err = e

    # Strategy 3: Selenium
    sel_result = extract_with_selenium(url)
    if sel_result and sel_result["url"].startswith("http"):
        sel_url = sel_result["url"]
        sel_headers = make_headers(sel_result.get("referer", url))
        sel_ext = sel_url.rsplit(".", 1)[-1].split("?")[0].lower()

        # Direct video file → download with requests
        if sel_ext in {"mp4", "webm", "mkv", "avi", "mov"}:
            path = outtmpl.replace("%(ext)s", sel_ext)
            try:
                resp = requests.get(sel_url, headers=sel_headers, stream=True, timeout=60)
                resp.raise_for_status()
                with open(path, "wb") as f:
                    for chunk in resp.iter_content(8192):
                        f.write(chunk)
                title = sel_result.get("title") or os.path.splitext(os.path.basename(sel_url))[0]
                return {"title": title}
            except Exception as e:
                last_err = e
        else:
            # Stream URL (.m3u8, .mpd) → use yt-dlp
            try:
                ydl_opts = {**BASE_YDL_OPTS, **cookie_opts, "outtmpl": outtmpl, "format": "best", "http_headers": sel_headers, "merge_output_format": "mp4"}
                with YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(sel_url, download=True)
            except Exception as e:
                last_err = e

    raise last_err


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload-cookie", methods=["POST"])
def upload_cookie():
    if "cookie" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    f = request.files["cookie"]
    if f.filename == "":
        return jsonify({"error": "Empty filename"}), 400
    f.save(os.path.join(COOKIE_DIR, "cookies.txt"))
    return jsonify({"ok": True, "file": "cookies.txt"})


@app.route("/cookie-status", methods=["GET"])
def cookie_status():
    path = os.path.join(COOKIE_DIR, "cookies.txt")
    exists = os.path.isfile(path)
    size = os.path.getsize(path) if exists else 0
    return jsonify({"loaded": exists, "size": size})


@app.route("/remove-cookie", methods=["POST"])
def remove_cookie():
    path = os.path.join(COOKIE_DIR, "cookies.txt")
    if os.path.isfile(path):
        os.remove(path)
    return jsonify({"ok": True})


@app.route("/download", methods=["POST"])
def download():
    url = request.json.get("url", "").strip()
    quality = request.json.get("quality", "720")
    if not url:
        return jsonify({"error": "URL is required"}), 400

    fmt = QUALITY_MAP.get(quality)
    if not fmt:
        return jsonify({"error": f"Invalid quality '{quality}'"}), 400

    cookie_file = os.path.join(COOKIE_DIR, "cookies.txt")
    if not os.path.isfile(cookie_file):
        cookie_file = None

    uid = uuid.uuid4().hex[:8]
    outtmpl = os.path.join(DOWNLOAD_DIR, f"video_{uid}.%(ext)s")

    try:
        info = try_download(url, fmt, outtmpl, uid, cookie_file)
        filename = None
        for f in os.listdir(DOWNLOAD_DIR):
            if uid in f:
                filename = os.path.join(DOWNLOAD_DIR, f)
                break
        if not filename:
            raise Exception("Downloaded file not found on disk")

        # Resize to target quality via FFmpeg if available
        target_h = RESIZE_HEIGHTS.get(quality)
        if target_h and FFMPEG_LOCATION:
            resized = os.path.join(DOWNLOAD_DIR, f"video_{uid}_resized.mp4")
            print(f"[RESIZE] Upscaling to {target_h}p...")
            if resize_video(filename, resized, target_h):
                os.remove(filename)
                os.rename(resized, os.path.join(DOWNLOAD_DIR, f"video_{uid}.mp4"))
                filename = os.path.join(DOWNLOAD_DIR, f"video_{uid}.mp4")
                print(f"[RESIZE] Done: {target_h}p")

        title = info.get("title", "video")
        _, ext = os.path.splitext(filename)
        return jsonify({"file": os.path.basename(filename), "title": title + ext})
    except Exception as e:
        msg = str(e)
        if len(msg) > 300:
            msg = msg[:300] + "..."
        return jsonify({"error": msg}), 400


@app.route("/file/<name>")
def get_file(name):
    path = os.path.join(DOWNLOAD_DIR, name)
    if not os.path.exists(path):
        return jsonify({"error": "File not found"}), 404

    @after_this_request
    def cleanup(response):
        try:
            os.remove(path)
        except Exception:
            pass
        return response

    download_name = request.args.get("title", name)
    return send_file(path, as_attachment=True, download_name=download_name)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
