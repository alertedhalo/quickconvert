# QuickConvert

Flask + yt-dlp + FFmpeg web app for MP3/MP4 conversion of content you own or have permission to download.

## Local run
Install Python 3.10+, FFmpeg, then run:

```bash
pip install -r requirements.txt
python app.py
```
Open http://127.0.0.1:5000

## Deploy
A Dockerfile and render.yaml are included. Import this repository as a Docker web service on a host that permits this use. FFmpeg and adequate disk/RAM are required.

## Production notes
- Add scheduled cleanup for downloads/.
- Add authentication, rate limits, quotas, and disk limits before public launch.
- Do not operate as an unrestricted public downloader; respect copyright and platform terms.
- Update yt-dlp and FFmpeg regularly.
- This starter uses in-memory jobs and local temporary files; multi-instance production needs a task queue and shared storage.
