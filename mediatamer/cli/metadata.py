"""Extract MKV metadata (MediaTamer packaged module)."""

import argparse
from pathlib import Path

from mediatamer.config import load_config
from mediatamer.parameters import get_extensions
from mediatamer.signals.cache import get_or_create_metadata


def get_agument_parser(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument(
        "-i", "--input", type=Path, default=Path.cwd(), help="Input directory to scan"
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path.cwd() / "mkv_metadata",
        help="Output directory for metadata",
    )
    parser.add_argument(
        "--csv", action="store_true", help="Write a combined CSV summary"
    )
    parser.add_argument(
        "--extensions",
        nargs="*",
        default=get_extensions(),
        help="Extensions to scan (default .mkv)",
    )
    parser.add_argument(
        "--tmdb-api-key",
        type=str,
        help="TMDB API key for episode title lookup (can be set in config)",
    )
    parser.add_argument(
        "--language",
        type=str,
        default="en-US",
        help="Language for TMDB lookup (e.g., fr-FR, en-US)",
    )
    parser.add_argument(
        "--ai",
        action="store_true",
        help="Use Holistic AI Matcher for episode detection",
    )
    return parser


def main():
    parser = argparse.ArgumentParser(description="Extract metadata from videos.")
    parser = get_agument_parser(parser)
    args = parser.parse_args()

    config = load_config()
    tmdb_key = args.tmdb_api_key or config.get("tmbd-api-key")

    input_dir = args.input.resolve()
    out_dir = args.output.resolve()
    exts = {e if e.startswith(".") else f".{e}" for e in args.extensions}

    files = sorted(
        [p for p in input_dir.rglob("*") if p.suffix.lower() in exts and p.is_file()]
    )
    if not files:
        print("No MKV files found in", input_dir)
        return

    rows = []
    ai_matcher = None
    if args.ai:
        if not tmdb_key:
            print("Error: --ai requires --tmdb-api-key or config setting.")
            return
        ai_matcher = HolisticAIMatcher(tmdb_api_key=tmdb_key)

    for f in files:
        try:
            if args.ai:
                from mediatamer.signals.cache import save_metadata

                meta_obj = get_or_create_metadata(f, input_dir)
                ai_matcher.match(meta_obj)
                save_metadata(meta_obj)

                # Convert to the legacy dictionary format for output
                meta = extract_metadata(f, input_dir, tmdb_key, args.language)
                # Add AI match info to the dict
                meta["ai_match"] = meta_obj.ai_match
            else:
                meta = extract_metadata(f, input_dir, tmdb_key, args.language)
        except Exception as e:
            print(f"Error extracting metadata for {f}: {e}")
            continue
        write_json(out_dir, meta)
        rows.append(meta)

    if args.csv:
        write_csv_summary(out_dir, rows)

    print(f"Metadata written to {out_dir} (per-file JSON).")
    if args.csv:
        print(f"CSV summary: {out_dir / 'metadata_summary.csv'}")


if __name__ == "__main__":
    main()
