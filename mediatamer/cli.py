"""Top-level `mediatamer` CLI that dispatches subcommands to bundled tools.

Usage:
  mediatamer organize [args...]   # calls mediatamer.organize:main
  mediatamer compress [args...]   # calls mediatamer.compress:main
  mediatamer metadata [args...]   # calls mediatamer.extract_mkv_metadata:main
"""
from __future__ import annotations

import sys
import importlib

try:
    import argcomplete
except ImportError:
    argcomplete = None

import argparse


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


def create_parser():
    parser = argparse.ArgumentParser(
        description="MediaTamer — organize and compress media for Jellyfin",
        prog="mediatamer"
    )
    subparsers = parser.add_subparsers(
        dest="command", help="Available commands")

    # Organize command
    organize_parser = subparsers.add_parser(
        "organize", help="Organize video files into Jellyfin layout")
    organize_parser.add_argument(
        "--input", "-i", type=str, help="Input root to scan")
    organize_parser.add_argument(
        "--output", "-o", type=str, help="Output root")
    organize_parser.add_argument(
        "--apply", action="store_true", help="Actually move/copy files")
    organize_parser.add_argument(
        "--move", action="store_true", help="Move files instead of copying")
    organize_parser.add_argument("--exts", nargs="*", help="Video extensions")

    # Compress command
    compress_parser = subparsers.add_parser(
        "compress", help="Compress video files for optimal streaming")
    compress_parser.add_argument(
        "--input", "-i", type=str, required=True, help="Input directory to scan")
    compress_parser.add_argument(
        "--output", "-o", type=str, help="Output directory")
    compress_parser.add_argument(
        "--apply", action="store_true", help="Actually compress files")
    compress_parser.add_argument(
        "--no-embedded", action="store_true", help="Do not include embedded subtitles")
    compress_parser.add_argument("--exts", nargs="*", help="Video extensions")

    # Metadata command
    subparsers.add_parser("metadata", help="Extract MKV metadata")

    return parser


def main() -> int | None:
    parser = create_parser()
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

    parser.print_help()
    return 2


if __name__ == "__main__":
    parser = create_parser()
    if argcomplete:
        argcomplete.autocomplete(parser)
    raise SystemExit(main())
