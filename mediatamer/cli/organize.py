"""Organize module for MediaTamer."""

import json
from pathlib import Path
import argparse

# from shutil import move, copy2
import argcomplete

from mediatamer.config import load_config
from mediatamer.signals.video_metadata import VideoMetadata, metadata_to_dict
from mediatamer.extract_metada import extract_all_metadata
from mediatamer.cli.argparse_utils import add_common_arguments
from mediatamer.utils import (
    sanitize_filename,
    zero_pad,
    extract_files_to_process,
)


def get_argument_parser(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument(
        "--input", "-i", type=Path, default=Path.cwd(), help="Input root to scan"
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path.cwd() / "Jellyfin_Organized",
        help="Output root",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually move/copy files. If not set, runs as dry-run and prints actions",
    )
    parser.add_argument(
        "--move",
        action="store_true",
        help="Move files instead of copying when --apply is used",
    )
    parser = add_common_arguments(parser)
    return parser


def main():
    parser = argparse.ArgumentParser(
        description="Organize video files into Jellyfin layout (Show/Season XX/Show - SXXEXX.ext - Title)"
    )
    parser = get_argument_parser(parser)
    argcomplete.autocomplete(parser)
    args = parser.parse_args()

    # Load config
    config = load_config(args.config)

    input_root = args.input.resolve()
    output_root = args.output.resolve()

    output_json_path = output_root / "metadata.json"
    output_data = {}

    files = extract_files_to_process(input_root)
    for f in files:
        try:
            print(f"Extracting metadata for {f}...")
            meta = VideoMetadata(path=f)
            meta = extract_all_metadata(meta, config, no_cache=args.no_cache)
        except Exception as e:
            print(f"Error extracting metadata for {f}:\n{e}")
            continue

        print(f"Extracted metadata for {f}:")
        print(f"\t- Series name: {meta.final_result['series_full_name']}")
        print(f"\t- Episode title: {meta.final_result['name']}")
        print(f"\t- Season number: {meta.final_result['seasonNumber']}")
        print(f"\t- Episode number: {meta.final_result['number']}")

        output_path = str(
            output_root
            / meta.final_result["series_full_name"]
            / f"Season {zero_pad(meta.final_result['seasonNumber'])}"
            / f"{sanitize_filename(meta.final_result['series_full_name'])} - "
            f"S{zero_pad(meta.final_result['seasonNumber'])}"
            f"E{zero_pad(meta.final_result['number'])} - "
            f"{meta.final_result['name']}"
            f"{meta.path.suffix.lower()}"
        )

        output = {}
        output["output_path"] = output_path
        output_data[str(f)] = output
        print(output_data)

    output_root.mkdir(parents=True, exist_ok=True)
    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=4)
    print("\nDone. Files organized under:", output_root)


if __name__ == "__main__":
    main()
