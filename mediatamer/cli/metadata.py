"""Extract MKV metadata (MediaTamer packaged module)."""

import argparse
from pathlib import Path

from mediatamer.config import load_config
from mediatamer.extract_metada import extract_all_metadata
from mediatamer.signals.video_metadata import VideoMetadata, metadata_to_dict
from mediatamer.utils import extract_files_to_process
from mediatamer.cli.argparse_utils import add_common_arguments


def get_argument_parser(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument(
        "-i", "--input", type=Path, default=Path.cwd(), help="Input directory to scan"
    )
    parser = add_common_arguments(parser)
    return parser


def main():
    parser = argparse.ArgumentParser(description="Extract metadata from videos.")
    parser = get_agument_parser(parser)
    args = parser.parse_args()

    config = load_config(args.config)

    input_dir = args.input.resolve()

    files = extract_files_to_process(input_dir)
    metadata_list = {}
    for f in files:
        try:
            print(f"Extracting metadata for {f}...")
            meta = VideoMetadata(path=f)
            meta = extract_all_metadata(meta, config, no_cache=args.no_cache)
            metadata_list[str(f)] = metadata_to_dict(meta)
        except Exception as e:
            print(f"Error extracting metadata for {f}:\n{e}")
            continue

        print(f"TVDB info: {meta.final_result}")

        print(f"Extracted metadata for {f}:")
        print(f"\t- Series name: {meta.final_result['series_full_name']}")
        print(f"\t- Episode title: {meta.final_result['name']}")
        print(f"\t- Season number: {meta.final_result['seasonNumber']}")
        print(f"\t- Episode number: {meta.final_result['number']}")

        print(f"Extracting metadata for {f}... Done")


if __name__ == "__main__":
    main()
