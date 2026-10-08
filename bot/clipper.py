"""Clipper: download video (yt-dlp) + process (ffmpeg trim + vertical)."""
import os, subprocess, shutil, hashlib, json, re

ROOT = os.path.dirname(os.path.dirname(__file__))
CLIPS_DIR = os.path.join(ROOT, "clips")
INBOX_DIR = os.path.join(ROOT, "inbox")

FFMPEG = shutil.which("ffmpeg") or "/home/ubuntu/.hermes/tools/ffmpeg-9.0.1-linux-x64/bin/ffmpeg"
FFPROBE = shutil.which("ffprobe") or "/home/ubuntu/.hermes/tools/ffmpeg-9.0.1-linux-x64/bin/ffprobe"

def _has_ytdlp():
    try:
        import yt_dlp
        return True
    except ImportError:
        return shutil.which("yt-dlp") is not None

def probe_video(path):
    """Dapatkan info video: duration, width, height."""
    try:
        r = subprocess.run([FFPROBE, "-v", "quiet", "-print_format", "json",
                            "-show_format", "-show_streams", path],
                           capture_output=True, text=True, timeout=30)
        data = json.loads(r.stdout)
        duration = float(data.get("format", {}).get("duration", 0))
        vstream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
        return {"duration": duration,
                "width": vstream.get("width", 0),
                "height": vstream.get("height", 0)}
    except Exception as e:
        print(f"    probe error: {e}")
        return {"duration": 0, "width": 0, "height": 0}

def download_video(url, max_duration=120):
    """Download video dari URL (TikTok) via yt-dlp. Return path atau None."""
    if not _has_ytdlp():
        print("    [DL] yt-dlp belum terinstall — skip download. Install: /usr/bin/pip3 install yt-dlp")
        return None
    
    os.makedirs(CLIPS_DIR, exist_ok=True)
    url_hash = hashlib.md5(url.encode()).hexdigest()[:10]
    outtmpl = os.path.join(CLIPS_DIR, f"src_{url_hash}.mp4")
    
    try:
        import yt_dlp
        opts = {
            "outtmpl": outtmpl,
            "format": "mp4/bestvideo[height<=1280]+bestaudio/best[height<=1280]/best",
            "max_filesize": 200 * 1024 * 1024,
            "merge_output_format": "mp4",
            "quiet": True,
            "no_warnings": True,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
        
        if os.path.exists(outtmpl):
            info = probe_video(outtmpl)
            if info["duration"] > max_duration:
                print(f"    [DL] Video {info['duration']:.0f}s > {max_duration}s max — akan di-trim")
            return outtmpl
    except Exception as e:
        print(f"    [DL] Error download {url[:50]}: {e}")
    return None

def get_inbox_videos():
    """Ambil video dari folder inbox/ (user drop video seller yang rights-cleared)."""
    os.makedirs(INBOX_DIR, exist_ok=True)
    videos = []
    for f in os.listdir(INBOX_DIR):
        if f.lower().endswith((".mp4", ".mov", ".webm", ".avi")):
            videos.append(os.path.join(INBOX_DIR, f))
    return sorted(videos)

def process_clip(src_path, max_duration=60, vertical=True, out_width=720, out_height=1280):
    """Process clip: trim ke max_duration + re-encode vertikal 9:16.
    
    Return path ke file hasil, atau path asli kalau gak perlu diubah.
    """
    os.makedirs(CLIPS_DIR, exist_ok=True)
    info = probe_video(src_path)
    duration = info["duration"]
    width, height = info["width"], info["height"]
    
    # Cek apakah perlu trim/re-encode
    needs_trim = duration > max_duration
    is_vertical = height >= width
    needs_resize = vertical and (width != out_width or height != out_height)
    
    if not needs_trim and not needs_resize:
        print(f"    [CLIP] Gak perlu process ({duration:.0f}s, {width}x{height})")
        return src_path
    
    clip_id = os.path.basename(src_path).rsplit(".", 1)[0]
    out_path = os.path.join(CLIPS_DIR, f"processed_{clip_id}.mp4")
    
    cmd = [FFMPEG, "-y", "-i", src_path]
    
    # Trim
    if needs_trim:
        cmd += ["-t", str(max_duration)]
    
    # Scale + pad ke vertikal 9:16 (letterbox kalau aspect beda)
    if needs_resize:
        cmd += [
            "-vf", (
                f"scale={out_width}:{out_height}:force_original_aspect_ratio=decrease,"
                f"pad={out_width}:{out_height}:(ow-iw)/2:(oh-ih)/2:color=black,"
                f"fps=30"
            ),
        ]
    
    cmd += ["-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k", out_path]
    
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if os.path.exists(out_path) and os.path.getsize(out_path) > 5000:
            new_info = probe_video(out_path)
            print(f"    [CLIP] Processed: {duration:.0f}s->{new_info['duration']:.0f}s, "
                  f"{width}x{height}->{new_info['width']}x{new_info['height']}")
            return out_path
        else:
            print(f"    [CLIP] ffmpeg output kosong/kecil: {r.stderr[-200:]}")
    except Exception as e:
        print(f"    [CLIP] ffmpeg error: {e}")
    
    return src_path  # fallback: pakai asli

def cleanup_old(days=7):
    """Hapus clips lebih dari N hari."""
    import time as _time
    cutoff = _time.time() - days * 86400
    for d in [CLIPS_DIR, os.path.join(ROOT, "posted")]:
        if not os.path.exists(d):
            continue
        for f in os.listdir(d):
            fp = os.path.join(d, f)
            if os.path.isfile(fp) and os.path.getmtime(fp) < cutoff:
                try:
                    os.remove(fp)
                except:
                    pass
