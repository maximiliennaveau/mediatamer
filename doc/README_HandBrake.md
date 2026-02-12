# HandBrake batch convert

This file contains a small script to batch-convert videos using HandBrakeCLI with the following recommended settings for a Synology DS418 + LG 1080p setup:

- Format: MKV
- Video: H.265 (x265)
- Framerate: Same as source, Constant Framerate
- Quality: RF 20
- Audio: AAC, 160–320 kbps (script defaults to 192 kbps)
- Subtitles: prefer external .srt files; avoid PGS subtitles. If no external SRT is present, the script will by default try to keep a VOSTFR embedded subtitle track (non-PGS) when available.

Files:

- `handbrake_batch_convert.sh`: Bash script.

Make executable:

- `chmod +x handbrake_batch_convert.sh`