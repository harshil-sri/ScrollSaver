import yt_dlp
import os
import subprocess

import json
import glob

import glob
def run_yt_dlp(url: str, out_dir: str) -> tuple[list[str], str]:
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': f'{out_dir}/%(id)s_%(epoch)d.%(ext)s',
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

import sys
def run_gallery_dl(url: str, out_dir: str) -> tuple[list[str], str]:
    cmd = [sys.executable, "-m", "gallery_dl", url, "-d", out_dir, "--write-metadata"]
    cookie_path = "/etc/secrets/cookies.txt" if os.path.exists("/etc/secrets/cookies.txt") else "cookies.txt"
    if os.path.exists(cookie_path):
        cmd.extend(["--cookies", cookie_path])
        
    subprocess.run(cmd, check=True) # Output doesn't need to be parsed
    
    downloaded_files = []
    all_files = glob.glob(os.path.join(out_dir, "**", "*"), recursive=True)
    
    for f in all_files:
        if os.path.isfile(f) and not f.endswith(".json"):
            downloaded_files.append(f)
            
    if not downloaded_files:
        raise Exception("gallery-dl succeeded but no files were found in the output directory.")
        
    # Attempt to find the metadata JSON file created by --write-metadata
    caption = ""
    for f in all_files:
        if f.endswith(".json"):
            try:
                with open(f, "r", encoding="utf-8") as jf:
                    meta = json.load(jf)
                    caption = meta.get("edge_media_to_caption", {}).get("edges", [{}])[0].get("node", {}).get("text", "")
                    if not caption:
                        caption = meta.get("caption", "")
            except Exception:
                pass
            if caption:
                break
            
    return downloaded_files, caption

def download_media(url: str, out_dir: str = "downloads") -> tuple[list[str], str]:
    """Downloads audio/video/images from the URL and returns a tuple (list of file paths, caption string)."""
    os.makedirs(out_dir, exist_ok=True)
    
    # URL Routing: /p/ or /tv/ goes to gallery-dl, everything else goes to yt-dlp
    if "/p/" in url or "/tv/" in url:
        try:
            return run_gallery_dl(url, out_dir)
        except Exception as e:
            raise Exception(f"gallery-dl failed. Check URL or cookies. Error: {str(e)}")
    else:
        try:
            return run_yt_dlp(url, out_dir)
        except Exception as e:
            # Fallback for unexpected URL structures
            try:
                return run_gallery_dl(url, out_dir)
            except Exception as inner_e:
                raise Exception(f"Both yt-dlp and gallery-dl failed. Error: {str(e)}")

