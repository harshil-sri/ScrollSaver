import yt_dlp
import os
import subprocess

def run_yt_dlp(url: str) -> list[str]:
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': 'downloads/%(id)s_%(epoch)d.%(ext)s',
        'quiet': True,
    }
    if os.path.exists("cookies.txt"):
        ydl_opts['cookiefile'] = "cookies.txt"
        
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if info:
            expected_filename = ydl.prepare_filename(info)
            if os.path.exists(expected_filename):
                return [expected_filename]
    return []

def run_gallery_dl(url: str) -> list[str]:
    cmd = ["gallery-dl", url, "-d", "downloads"]
    if os.path.exists("cookies.txt"):
        cmd.extend(["--cookies", "cookies.txt"])
        
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    downloaded_files = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("#"):
            path = line.split(" ", 1)[-1].strip()
            if os.path.exists(path):
                downloaded_files.append(path)
        elif os.path.exists(line):
            downloaded_files.append(line)
            
    if not downloaded_files:
        raise Exception("gallery-dl succeeded but no files were found in stdout.")
    return downloaded_files

def download_media(url: str) -> list[str]:
    """Downloads audio/video/images from the URL and returns a list of file paths."""
    os.makedirs("downloads", exist_ok=True)
    
    # URL Routing: /p/ or /tv/ goes to gallery-dl, everything else goes to yt-dlp
    if "/p/" in url or "/tv/" in url:
        try:
            return run_gallery_dl(url)
        except Exception as e:
            raise Exception(f"gallery-dl failed. Check URL or cookies. Error: {str(e)}")
    else:
        try:
            return run_yt_dlp(url)
        except Exception as e:
            # Fallback for unexpected URL structures
            try:
                return run_gallery_dl(url)
            except Exception as inner_e:
                raise Exception(f"Both yt-dlp and gallery-dl failed. Error: {str(e)}")
