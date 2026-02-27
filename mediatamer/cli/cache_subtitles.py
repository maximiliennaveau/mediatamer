#!/usr/bin/env python3
"""CLI command to pre-extract and cache subtitles for a directory of videos."""

import os
import argparse
from pathlib import Path
from typing import Optional, List

from mediatamer.signals.subtitle import extract_subtitle_text, extract_credits_text
from mediatamer.parameters import get_extensions


def cache_subtitle(video_path: Path, force: bool = False):
    """Extract and cache subtitle for a single video file using production logic."""
    # Production functions automatically handle caching if SUBTITLE_CACHE_DIR is set.
    # We pass 'prefer_non_pgs=True' to ensure we try text first then OCR.

    print(f"  [PROCESSING] {video_path.name}...")

    # Extract full subtitles (this writes to cache internally)
    extract_subtitle_text(video_path, prefer_non_pgs=True)

    # Extract credits (this writes to cache internally)
    extract_credits_text(video_path, opening_duration=180.0, closing_duration=180.0)

    print(f"    ✓ Processed {video_path.name}")


def get_argument_parser(
    parser: Optional[argparse.ArgumentParser] = None,
) -> argparse.ArgumentParser:
    if parser is None:
        parser = argparse.ArgumentParser(
            description="Pre-extract and cache subtitles from videos"
        )

    parser.add_argument("input_dir", type=Path, help="Directory containing video files")
    parser.add_argument(
        "--cache-dir",
        type=Path,
        help="Directory to store cached subtitles (default env: SUBTITLE_CACHE_DIR)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-extraction (note: core logic currently respects existing cache)",
    )
    parser.add_argument(
        "--extensions",
        nargs="*",
        default=get_extensions(),
        help="Video file extensions to process",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = get_argument_parser()
    args = parser.parse_args(argv)

    input_dir = args.input_dir.resolve()

    if args.cache_dir:
        cache_dir = args.cache_dir.resolve()
        cache_dir.mkdir(parents=True, exist_ok=True)
        os.environ["SUBTITLE_CACHE_DIR"] = str(cache_dir)
    elif not os.getenv("SUBTITLE_CACHE_DIR"):
        print(
            "Error: --cache-dir must be provided or SUBTITLE_CACHE_DIR environment variable must be set."
        )
        return 1

    if not input_dir.exists():
        print(f"Error: Input directory does not exist: {input_dir}")
        return 1

    print(f"Cache directory: {os.getenv('SUBTITLE_CACHE_DIR')}")

    # Find all video files
    exts = {e if e.startswith(".") else f".{e}" for e in args.extensions}
    video_files = sorted(
        [p for p in input_dir.rglob("*") if p.suffix.lower() in exts and p.is_file()]
    )

    if not video_files:
        print(f"No video files found in {input_dir}")
        return 1

    print(f"\nFound {len(video_files)} video files")
    print("=" * 60)

    # Process each file
    for i, video_file in enumerate(video_files, 1):
        print(f"\n[{i}/{len(video_files)}] {video_file.relative_to(input_dir)}")
        try:
            cache_subtitle(video_file, force=args.force)
        except Exception as e:
            print(f"    ✗ Error: {e}")
            continue

    print("\n" + "=" * 60)
    print("✓ Processing complete!")
    print("\nTo use cached subtitles, ensure environment variable is set:")
    print(f"  export SUBTITLE_CACHE_DIR={os.getenv('SUBTITLE_CACHE_DIR')}")

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
