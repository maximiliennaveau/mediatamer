"""Extract MKV metadata (MediaTamer packaged module)."""

import argparse
from pathlib import Path

from mediatamer.config import load_config
from mediatamer.extract_metada import extract_all_metadata
from mediatamer.signals.video_metadata import VideoMetadata
from mediatamer.utils import extract_files_to_process
from mediatamer.cli.argparse_utils import add_common_arguments


def get_agument_parser(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
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
            meta = VideoMetadata(path=f)
            meta = extract_all_metadata(meta, config, no_cache=args.no_cache)
            metadata_list[str(f)] = metadata_to_dict(meta)
        except Exception as e:
            print(f"Error extracting metadata for {f}: {e}")
            continue

        print(f"Extracted metadata for {f}:")
        print(f"Show: {meta.ai_match.get('show')}")
        print(f"Season: {meta.ai_match.get('season')}")
        print(f"Episode: {meta.ai_match.get('episode')}")
        print(f"Title: {meta.ai_match.get('title')}")
        print(f"Type: {meta.ai_match.get('type')}")


if __name__ == "__main__":
    main()
