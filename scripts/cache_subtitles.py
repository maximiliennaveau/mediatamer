#!/usr/bin/env python3
"""Pre-extract subtitles from all videos and cache them for faster debugging.

This script extracts complete subtitles (via OCR if needed) from all video files
in a directory and saves them to a cache directory. The matcher can then use
these cached subtitles instead of re-extracting them every time.

Usage:
    python scripts/cache_subtitles.py /path/to/videos --cache-dir /path/to/cache
"""

import os
import argparse
import json
from pathlib import Path
import sys
import hashlib

# Add parent directory to path to import mediatamer
sys.path.insert(0, str(Path(__file__).parent.parent))

from mediatamer.extract_subtitle import extract_subtitle_text, extract_credits_text
from mediatamer.parameters import get_extensions


def get_file_hash(path: Path) -> str:
    """Get a hash of the file for cache key."""
    # Use file size + mtime as a quick hash
    stat = path.stat()
    return hashlib.md5(f"{path.name}_{stat.st_size}_{stat.st_mtime}".encode()).hexdigest()


def cache_subtitle(video_path: Path, cache_dir: Path, force: bool = False):
    """Extract and cache subtitle for a single video file."""
    file_hash = get_file_hash(video_path)
    cache_file = cache_dir / f"{file_hash}.json"
    
    if cache_file.exists() and not force:
        print(f"  [CACHED] {video_path.name}")
        return
    
    print(f"  [EXTRACTING] {video_path.name}...")
    
    # Extract full subtitles
    subtitle_text = extract_subtitle_text(video_path, prefer_non_pgs=True)
    
    # Extract credits (opening + closing)
    credits_text = extract_credits_text(video_path, opening_duration=180.0, closing_duration=180.0)
    
    # Save to cache
    cache_data = {
        'file_path': str(video_path),
        'file_name': video_path.name,
        'file_hash': file_hash,
        'subtitle_text': subtitle_text,
        'credits_text': credits_text,
    }
    
    with cache_file.open('w', encoding='utf-8') as f:
        json.dump(cache_data, f, indent=2, ensure_ascii=False)
    
    print(f"    ✓ Cached to {cache_file.name}")


def main():
    parser = argparse.ArgumentParser(description="Pre-extract and cache subtitles from videos")
    parser.add_argument("input_dir", type=Path, help="Directory containing video files")
    parser.add_argument("--cache-dir", type=Path, default=Path(os.getenv("SUBTITLE_CACHE_DIR")),
                        help="Directory to store cached subtitles (default env: SUBTITLE_CACHE_DIR)")
    parser.add_argument("--force", action="store_true",
                        help="Force re-extraction even if cache exists")
    parser.add_argument("--extensions", nargs="*", default=get_extensions(),
                        help="Video file extensions to process")
    
    args = parser.parse_args()
    
    input_dir = args.input_dir.resolve()
    cache_dir = args.cache_dir.resolve()
    
    if not input_dir.exists():
        print(f"Error: Input directory does not exist: {input_dir}")
        return 1
    
    # Create cache directory
    cache_dir.mkdir(parents=True, exist_ok=True)
    print(f"Cache directory: {cache_dir}")
    
    # Find all video files
    exts = {e if e.startswith('.') else f".{e}" for e in args.extensions}
    video_files = sorted([p for p in input_dir.rglob("*") if p.suffix.lower() in exts and p.is_file()])
    
    if not video_files:
        print(f"No video files found in {input_dir}")
        return 1
    
    print(f"\nFound {len(video_files)} video files")
    print("=" * 60)
    
    # Process each file
    for i, video_file in enumerate(video_files, 1):
        print(f"\n[{i}/{len(video_files)}] {video_file.relative_to(input_dir)}")
        try:
            cache_subtitle(video_file, cache_dir, force=args.force)
        except Exception as e:
            print(f"    ✗ Error: {e}")
            continue
    
    print("\n" + "=" * 60)
    print(f"✓ Caching complete! {len(list(cache_dir.glob('*.json')))} files cached")
    print(f"\nTo use cached subtitles, set environment variable:")
    print(f"  export SUBTITLE_CACHE_DIR={cache_dir}")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
