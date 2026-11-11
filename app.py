import os
import re
import uuid
import threading
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, request, jsonify, send_file, render_template, abort
import yt_dlp

BASE = Path(__file__).resolve().parent
DOWNLOADS = BASE / "downloads"
DOWNLOADS.mkdir(exist_ok=True)
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024
jobs = {}
lock = threading.Lock()
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "www.youtube-nocookie.com"}

def valid_youtube_url(value):
    try:
        parsed = urlparse(value.strip())
        return parsed.scheme in {"http", "https"} and (parsed.hostname or "").lower() in YOUTUBE_HOSTS
    except Exception:
        return False

def run_download(job_id, url, output_format, quality):
    job_dir = DOWNLOADS / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    def hook(data):
        with lock:
            job = jobs.get(job_id)
            if not job:
                return
            if data.get("status") == "downloading":
                total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
                done = data.get("downloaded_bytes") or 0
                job["progress"] = min(94, int(done * 94 / total)) if total else job.get("progress", 5)
                job["message"] = "Downloading…"
            elif data.get("status") == "finished":
                job["progress"] = 96
                job["message"] = "Processing file…"

    if output_format == "mp3":
        postprocessors = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": quality}]
        format_selector, extension = "bestaudio/best", "mp3"
    else:
        postprocessors = []
        format_selector, extension = f"bv*[height<={quality}]+ba/b[height<={quality}]/b", "mp4"

    options = {
        "outtmpl": str(job_dir / "media.%(ext)s"),
        "format": format_selector,
        "merge_output_format": "mp4" if output_format == "mp4" else None,
        "postprocessors": postprocessors,
        "progress_hooks": [hook],
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "restrictfilenames": True,
        "overwrites": True,
    }
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
            title = re.sub(r"[^A-Za-z0-9 _.-]", "", info.get("title", "youtube-media"))[:90].strip()
        candidates = list(job_dir.glob(f"*.{extension}"))
        if not candidates:
            candidates = [p for p in job_dir.iterdir() if p.is_file() and p.suffix.lower() in {".mp4", ".mp3", ".m4a", ".webm", ".mkv"}]
        if not candidates:
            raise RuntimeError("No output file was created. Check FFmpeg and the source video.")
        with lock:
            jobs[job_id].update({"status": "complete", "progress": 100, "message": "Ready to download",
                                 "file": str(candidates[0]), "filename": f"{title or 'youtube-media'}.{extension}"})
    except Exception as exc:
        with lock:
            jobs[job_id].update({"status": "error", "progress": 0,
                                 "message": "Could not convert this link.", "error": str(exc)[:500]})

@app.get("/")
def index():
    return render_template("index.html")

@app.post("/api/convert")
def create_job():
    data = request.get_json(silent=True) or {}
    url = str(data.get("url", "")).strip()
    output_format = data.get("format")
    quality = str(data.get("quality", "192"))
    if not valid_youtube_url(url):
        return jsonify(error="Please enter a valid YouTube video URL."), 400
    if output_format not in {"mp3", "mp4"}:
        return jsonify(error="Choose MP3 or MP4."), 400
    if output_format == "mp3" and quality not in {"128", "192", "256", "320"}:
        return jsonify(error="Invalid MP3 quality."), 400
    if output_format == "mp4" and quality not in {"360", "480", "720", "1080"}:
        return jsonify(error="Invalid video quality."), 400
    job_id = uuid.uuid4().hex
    with lock:
        jobs[job_id] = {"status": "working", "progress": 1, "message": "Starting…"}
    threading.Thread(target=run_download, args=(job_id, url, output_format, quality), daemon=True).start()
    return jsonify(job_id=job_id)

@app.get("/api/status/<job_id>")
def job_status(job_id):
    with lock:
        job = jobs.get(job_id)
        if not job:
            abort(404)
        return jsonify({k: v for k, v in job.items() if k not in {"file", "error"}})

@app.get("/api/download/<job_id>")
def download(job_id):
    with lock:
        job = jobs.get(job_id)
        if not job or job.get("status") != "complete":
            abort(404)
        path, filename = job.get("file"), job.get("filename", "converted-media")
    if not path or not Path(path).is_file():
        abort(404)
    return send_file(path, as_attachment=True, download_name=filename)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=False)
