"""Compress module for MediaTamer (converts videos to optimal format for Jellyfin streaming on DS418 NAS)."""

import argparse
import shutil
from pathlib import Path

try:
    import argcomplete
except ImportError:
    argcomplete = None
from mediatamer.cli.argparse_utils import add_common_arguments
from mediatamer.utils import extract_files_to_process
from mediatamer.parameters import get_extensions
from mediatamer.compress import compress_file


def get_argument_parser(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument(
        "--input",
        "-i",
        type=Path,
        default=Path.cwd(),
        help="Input directory or file to scan",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path.cwd() / "compressed",
        help="Output root",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually move/copy files. If not set, runs as dry-run and prints actions",
    )
    parser.add_argument(
        "--no-embedded", action="store_true", help="Do not include embedded subtitles"
    )
    parser.add_argument("--exts", nargs="*", help="Video extensions to process")
    parser.add_argument(
        "--crf",
        type=int,
        default=18,
        help="CRF value for libx264 (lower => better quality, slower).",
    )
    parser.add_argument(
        "--preset",
        choices=(
            "ultrafast",
            "superfast",
            "veryfast",
            "faster",
            "fast",
            "medium",
            "slow",
            "slower",
            "veryslow",
        ),
        default="slow",
        help="x264 preset (slower => better compression).",
    )
    parser.add_argument(
        "--tune",
        choices=("film", "animation", "grain", "stillimage", "psnr", "ssim"),
        default=None,
        help="x264 tune parameter (optional)",
    )
    parser.add_argument(
        "--profile",
        choices=("baseline", "main", "high"),
        default="high",
        help="x264 profile to signal in the output (default: high)",
    )
    parser = add_common_arguments(parser)
    if argcomplete:
        argcomplete.autocomplete(parser)
    return parser


def main():
    parser = argparse.ArgumentParser(
        description="Compress video files for optimal Jellyfin streaming on DS418 NAS"
    )
    parser = get_argument_parser(parser)
    args = parser.parse_args()

    input_path = args.input.resolve()
    files = extract_files_to_process(input_path) or []
    if not files:
        return 0

    output_dir = args.output.resolve()
    # Determine if user passed an output *file* (e.g. -o /tmp/out.mkv)
    out_is_file = False
    try:
        out_suffix = args.output.suffix.lower()
        exts = {e if e.startswith(".") else f".{e}" for e in get_extensions()}
        if out_suffix in exts:
            out_is_file = True
    except Exception:
        out_is_file = False
    if args.exts:
        exts = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in args.exts}
        files = [p for p in files if p.suffix.lower() in exts]

    # Check ffmpeg availability
    if shutil.which("ffmpeg") is None:
        print("Error: ffmpeg not found in PATH")
        return 1

    for infile in sorted(files):
        if input_path.is_file():
            outfile = (
                output_dir
                if out_is_file
                else output_dir / infile.with_suffix(".mkv").name
            )
        else:
            outfile = output_dir / infile.relative_to(input_path).with_suffix(".mkv")
        if args.apply:
            outfile.parent.mkdir(parents=True, exist_ok=True)

        cmd, result = compress_file(
            infile,
            outfile,
            crf=args.crf,
            preset=args.preset,
            tune=args.tune,
            profile=args.profile,
            apply=args.apply,
        )

        if not cmd:
            print(f"Skipping (already H.264): {infile}")
            continue

        print(f"Converting: {infile} -> {outfile}")
        if not args.apply:
            print(f"DRY RUN: {' '.join(cmd)}")
        else:
            if result is None or result.returncode != 0:
                code = None if result is None else result.returncode
                print(f"Failed: {infile} (exit {code})")

    print("Done.")


if __name__ == "__main__":
    main()
