import yt_dlp
import os
import subprocess

import json
import glob

def run_yt_dlp(url: str) -> tuple[list[str], str]:
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': 'downloads/%(id)s_%(epoch)d.%(ext)s',
        'quiet': True,
    }
    cookie_path = "/etc/secrets/cookies.txt" if os.path.exists("/etc/secrets/cookies.txt") else "cookies.txt"
    if os.path.exists(cookie_path):
        ydl_opts['cookiefile'] = cookie_path
        
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if info:
            caption = info.get("description", "")
            expected_filename = ydl.prepare_filename(info)
            if os.path.exists(expected_filename):
                return [expected_filename], caption
    return [], ""

def run_gallery_dl(url: str) -> tuple[list[str], str]:
    cmd = ["gallery-dl", url, "-d", "downloads", "--write-metadata"]
    cookie_path = "/etc/secrets/cookies.txt" if os.path.exists("/etc/secrets/cookies.txt") else "cookies.txt"
    if os.path.exists(cookie_path):
        cmd.extend(["--cookies", cookie_path])
        
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    downloaded_files = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("#"):
            path = line.split(" ", 1)[-1].strip()
            if os.path.exists(path) and not path.endswith(".json"):
                downloaded_files.append(path)
        elif os.path.exists(line) and not line.endswith(".json"):
            downloaded_files.append(line)
            
    if not downloaded_files:
        raise Exception("gallery-dl succeeded but no files were found in stdout.")
        
    # Attempt to find the metadata JSON file created by --write-metadata
    caption = ""
    for f in downloaded_files:
        json_path = f + ".json"
        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as jf:
                    meta = json.load(jf)
                    # Instagram typically stores caption here
                    caption = meta.get("edge_media_to_caption", {}).get("edges", [{}])[0].get("node", {}).get("text", "")
                    if not caption:
                        caption = meta.get("caption", "")
            except Exception:
                pass
            break # Just need one caption per post
            
    return downloaded_files, caption

def download_media(url: str) -> tuple[list[str], str]:
    """Downloads audio/video/images from the URL and returns a tuple (list of file paths, caption string)."""
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

