# MediaTamer

MediaTamer cleans and organizes episodic media into a Jellyfin-friendly layout and extracts MKV metadata.

Includes two CLI tools:

- `organize-for-jellyfin` — organize a folder of episodic video files into `Show/Season 01/Show - S01E01.ext` layout
- `extract-mkv-metadata` — extract MKV metadata using `ffprobe` into per-file JSON and optional CSV

Usage (from package root):

```bash
# Dry-run organize
mediatamer -i ./ -o ~/jellyfin/tv_shows

# Extract MKV metadata
extract-mkv-metadata -i ./ -o ./metadata --csv
```

<!-- Build instructions moved to 'Development (Nix)' below -->

Prerequisites
-
- Python 3.8+
- `ffmpeg` / `ffprobe` (used by `extract-mkv-metadata`). When using Nix, the dev shell provides `ffmpeg`.

Development (Nix)
-
Enter a development shell with Python and `ffmpeg` available:

```bash
cd /data/videos
nix develop ./mediatamer#default
```

Install locally (pip)
-
To install the CLI tools into your active Python environment:

```bash
python -m pip install -e .
```

Notes
-
- `ffprobe` is required to inspect embedded subtitle and stream metadata; it is not a Python dependency and therefore is not listed in `pyproject.toml`.
- Use the Nix dev shell to get a consistent environment for development and running the CLIs.
