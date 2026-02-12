# MediaTamer

Small package providing two CLI tools:

- `organize-for-jellyfin` — organize a folder of episodic video files into `Show/Season 01/Show - S01E01.ext` layout
- `extract-mkv-metadata` — extract MKV metadata using `ffprobe` into per-file JSON and optional CSV

Usage (from package root):

```bash
# Dry-run organize
organize-for-jellyfin -i ./ -o ~/jellyfin/tv_shows

# Extract MKV metadata
extract-mkv-metadata -i ./ -o ./metadata --csv
```

Build with Nix Flake (see `flake.nix`).
