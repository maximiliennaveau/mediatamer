# Subtitle Caching System

## Purpose
Pre-extract subtitles from all videos once and cache them to avoid repeated expensive OCR operations during debugging and testing.

## Quick Start

### 1. Extract and Cache Subtitles
```bash
# Extract subtitles from all videos in a directory
nix develop --command python3 scripts/cache_subtitles.py /data/videos/unsorted_videos/Doctor_Who_S9_DVD3

# Or specify a custom cache directory
nix develop --command python3 scripts/cache_subtitles.py /data/videos/unsorted_videos/Doctor_Who_S9_DVD3 --cache-dir /tmp/subtitle_cache
```

### 2. Use Cached Subtitles
```bash
# Set environment variable to enable cache
export SUBTITLE_CACHE_DIR=/data/videos/mediatamer/.subtitle_cache

# Now run your tests or commands - they'll use cached subtitles!
nix develop --command python3 tests/unit/test_get_tv_shows_metadata.py -v
```

## How It Works

1. **Extraction**: `scripts/cache_subtitles.py` processes each video file:
   - Extracts complete subtitles (via OCR if needed)
   - Extracts credits (opening + closing 3 minutes)
   - Saves to JSON file named by file hash

2. **Cache Lookup**: When `extract_subtitle_text()` or `extract_credits_text()` is called:
   - Checks if `SUBTITLE_CACHE_DIR` environment variable is set
   - Looks for cached data by file hash
   - Returns cached data if found, otherwise extracts normally

3. **Cache Key**: Uses MD5 hash of `filename + size + mtime` to detect file changes

## Cache Structure

```
.subtitle_cache/
├── a1b2c3d4e5f6.json  # Cached data for video 1
├── f6e5d4c3b2a1.json  # Cached data for video 2
└── ...
```

Each JSON file contains:
```json
{
  "file_path": "/path/to/video.mkv",
  "file_name": "B1_t00.mkv",
  "file_hash": "a1b2c3d4e5f6",
  "subtitle_text": "Full subtitle text...",
  "credits_text": "Credits text..."
}
```

## Benefits

- **Speed**: Extract once, use many times during debugging
- **Consistency**: Same subtitles used across all test runs
- **Debugging**: Can manually inspect cached subtitle text
- **Flexibility**: Can force re-extraction with `--force` flag

## Commands

```bash
# Extract with default cache location (.subtitle_cache)
python3 scripts/cache_subtitles.py /path/to/videos

# Force re-extraction
python3 scripts/cache_subtitles.py /path/to/videos --force

# Custom cache directory
python3 scripts/cache_subtitles.py /path/to/videos --cache-dir /tmp/cache

# Specific file extensions
python3 scripts/cache_subtitles.py /path/to/videos --extensions mkv mp4 avi
```

## Environment Variables

- `SUBTITLE_CACHE_DIR`: Path to cache directory (if not set, caching is disabled)

## Notes

- Cache is automatically invalidated if file size or modification time changes
- OCR extraction can take 30-60 seconds per file
- Cache files are human-readable JSON for easy inspection
