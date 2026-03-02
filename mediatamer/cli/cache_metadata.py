#!/usr/bin/env python3
"""CLI command to pre-extract and cache all metadata signals for a directory of videos."""

import argparse
from pathlib import Path
from typing import Optional, List

from mediatamer.parameters import get_extensions
from mediatamer.signals.cache import get_or_create_metadata


def cache_video_metadata(video_path: Path, scan_root: Optional[Path] = None):
    """Extract and cache all metadata signals for a single video file."""
    print(f"  [PROCESSING] {video_path.name}...")

    # This automatically extracts and saves to the centralized cache
    get_or_create_metadata(video_path, scan_root)

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

    if not input_dir.exists():
        print(f"Error: Input directory does not exist: {input_dir}")
        return 1

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
            cache_video_metadata(video_file, scan_root=input_dir)
        except Exception as e:
            print(f"    ✗ Error: {e}")
            continue

    print("\n" + "=" * 60)
    print("✓ Processing complete!")
    print("\nMetadata is saved in ~/.cache/mediatamer/metadata/")

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
