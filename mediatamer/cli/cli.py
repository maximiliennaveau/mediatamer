"""Top-level `mediatamer` CLI that dispatches subcommands to bundled tools.

Usage:
  mediatamer organize [args...]   # calls mediatamer.organize:main
  mediatamer compress [args...]   # calls mediatamer.compress:main
  mediatamer metadata [args...]   # calls mediatamer.extract_mkv_metadata:main
"""

from __future__ import annotations

import sys
import importlib
import argcomplete
import argparse
from typing import Any
from mediatamer.cli.organize import get_argument_parser as get_organize_parser
from mediatamer.cli.compress import get_agument_parser as get_compress_parser
from mediatamer.cli.metadata import get_agument_parser as get_metadata_parser
from mediatamer.cli.get_tv_shows_metadata import (
    get_argument_parser as get_tv_metadata_parser,
)
from mediatamer.cli.cache_subtitles import (
    get_argument_parser as get_cache_subtitles_parser,
)
from mediatamer.config import load_config


def _call_module_main(module_name: str, argv: list[str]) -> int | None:
    mod = importlib.import_module(module_name)
    old_argv = sys.argv
    try:
        sys.argv = [old_argv[0]] + argv
        if hasattr(mod, "main"):
            return mod.main()
        raise SystemExit(f"Module {module_name} has no main() entry")
    finally:
        sys.argv = old_argv


def create_parser(config: dict[str, Any] | None = None):
    parser = argparse.ArgumentParser(
        description="MediaTamer — organize and compress media for Jellyfin",
        prog="mediatamer",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Organize command
    organize_parser = subparsers.add_parser(
        "organize", help="Organize video files into Jellyfin layout"
    )
    organize_parser = get_organize_parser(organize_parser)
    if config:
        organize_parser.set_defaults(tmdb_api_key=config.get("tmbd-api-key"))

    # Compress command
    compress_parser = subparsers.add_parser(
        "compress", help="Compress video files for optimal streaming"
    )
    compress_parser = get_compress_parser(compress_parser)

    # Metadata command
    metadata_parser = subparsers.add_parser(
        "metadata", help="Extract MKV metadata to JSON and CSV"
    )
    metadata_parser = get_metadata_parser(metadata_parser)

    # TV Metadata command (New name)
    tv_parser = subparsers.add_parser("tv-metadata", help="Extract TV Show metadata")
    tv_parser = get_tv_metadata_parser(tv_parser)
    if config:
        tv_parser.set_defaults(
            tmdb_api_key=config.get("tmbd-api-key"),
            jellyfin_url=config.get("jellyfin-url"),
            jellyfin_api_key=config.get("jellyfin-api-key"),
        )

    # Subtitle cache command
    cache_subtitles_parser = subparsers.add_parser(
        "cache-subtitles", help="Bulk cache subtitles for a directory"
    )
    cache_subtitles_parser = get_cache_subtitles_parser(cache_subtitles_parser)

    return parser


def main() -> int | None:
    config = load_config()
    parser = create_parser(config)
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 2

    cmd = args.command.lower()

    if cmd == "organize":
        return _call_module_main("mediatamer.organize", sys.argv[2:])
    if cmd == "compress":
        return _call_module_main("mediatamer.compress", sys.argv[2:])
    if cmd in ("metadata", "meta"):
        return _call_module_main("mediatamer.metadata", sys.argv[2:])
    if cmd in ("dvd-metadata", "tv-metadata"):
        return _call_module_main("mediatamer.get_tv_shows_metadata", sys.argv[2:])
    if cmd == "cache-subtitles":
        return _call_module_main("mediatamer.cli.cache_subtitles", sys.argv[2:])

    parser.print_help()
    return 2


if __name__ == "__main__":
    parser = create_parser()
    if argcomplete:
        argcomplete.autocomplete(parser)
    raise SystemExit(main())
