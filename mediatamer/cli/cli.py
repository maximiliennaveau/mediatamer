"""Top-level `mediatamer` CLI that dispatches subcommands to bundled tools.

Usage:
  mediatamer organize [args...]   # calls mediatamer.organize:main
  mediatamer compress [args...]   # calls mediatamer.compress:main
  mediatamer metadata [args...]   # calls mediatamer.metadata:main
  mediatamer validate [args...]   # calls mediatamer.validate:main
"""

from __future__ import annotations

import sys
import importlib
import argcomplete
import argparse
from typing import Any
from mediatamer.cli.organize import get_argument_parser as get_organize_parser
from mediatamer.cli.compress import get_argument_parser as get_compress_parser
from mediatamer.cli.metadata import get_argument_parser as get_metadata_parser
from mediatamer.cli.validate import get_validate_parser
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
        organize_parser.set_defaults(tmdb_api_key=config.get("tmdb-api-key"))

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
    meta_parser = subparsers.add_parser(
        "meta", help="Extract MKV metadata to JSON and CSV"
    )
    meta_parser = get_metadata_parser(meta_parser)

    # Validate command
    validate_parser = subparsers.add_parser(
        "validate", help="Validate connections to online tools"
    )
    validate_parser = get_validate_parser(validate_parser)

    return parser


def main() -> int | None:
    # 1. Pre-parse for --config to load it before fully creating the parser
    # This is a bit tricky with subcommands, so we do a two-pass if needed,
    # or just let the subcommands handle it as they do now.
    # However, mediatamer top-level also uses load_config().

    # Simple check for -c or --config in sys.argv
    config_path = None
    if "-c" in sys.argv:
        idx = sys.argv.index("-c")
        if idx + 1 < len(sys.argv):
            config_path = sys.argv[idx + 1]
    elif "--config" in sys.argv:
        idx = sys.argv.index("--config")
        if idx + 1 < len(sys.argv):
            config_path = sys.argv[idx + 1]

    config = load_config(config_path)
    parser = create_parser(config)
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 2

    cmd = args.command.lower()

    if cmd == "organize":
        return _call_module_main("mediatamer.cli.organize", sys.argv[2:])
    if cmd == "compress":
        return _call_module_main("mediatamer.cli.compress", sys.argv[2:])
    if cmd in ("metadata", "meta"):
        return _call_module_main("mediatamer.cli.metadata", sys.argv[2:])
    if cmd == "validate":
        return _call_module_main("mediatamer.cli.validate", sys.argv[2:])

    parser.print_help()
    return 2


if __name__ == "__main__":
    parser = create_parser()
    if argcomplete:
        argcomplete.autocomplete(parser)
    raise SystemExit(main())
