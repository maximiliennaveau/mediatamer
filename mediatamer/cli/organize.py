"""Organize module for MediaTamer."""

import json
import shutil
from pathlib import Path
import argparse

import argcomplete

from mediatamer.config import load_config
from mediatamer.signals.video_metadata import VideoMetadata
from mediatamer.extract_metada import extract_all_metadata
from mediatamer.cli.argparse_utils import add_common_arguments
from mediatamer.compress import (
    compress_file,
    detect_hw_encoder,
    get_hw_encoder_diagnostics,
)
from mediatamer.mkv_metadata import write_mkv_metadata
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
        default=Path.cwd().parent / "jellyfin_organized",
        help="Output root",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually compress and write metadata. If not set, runs as dry-run.",
    )
    parser.add_argument(
        "--crf",
        type=int,
        default=20,
        help="CRF value for libx265 (lower => better quality, slower).",
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
        default="veryslow",
        help="x265 preset (slower => better compression).",
    )
    parser.add_argument(
        "--tune",
        choices=("psnr", "ssim", "grain", "zerolatency", "fastdecode", "animation"),
        default=None,
        help="x265 tune parameter (optional).",
    )
    parser.add_argument(
        "--profile",
        choices=("main", "main10"),
        default="main",
        help="x265 profile (default: main).",
    )
    parser.add_argument(
        "--no-hwenc",
        action="store_true",
        default=False,
        dest="no_hwenc",
        help="Disable hardware encoder auto-detection and force software libx265.",
    )
    parser = add_common_arguments(parser)
    return parser


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Master organizer: find metadata, compress to H.264 MKV, "
            "and burn metadata tags — ready for Jellyfin."
        )
    )
    parser = get_argument_parser(parser)
    argcomplete.autocomplete(parser)
    args = parser.parse_args()

    dry_run = not args.apply
    if dry_run:
        print("[DRY RUN] No files will be written. Pass --apply to execute.\n")

    config = load_config(args.config)

    # Auto-detect hardware encoder unless the user opted out
    if args.no_hwenc:
        hw_encoder = None
    else:
        hw_encoder = detect_hw_encoder()
        if hw_encoder:
            print(f"Hardware encoder detected: {hw_encoder}")
        else:
            print("No hardware encoder found, using software libx265.")
            diagnostics = get_hw_encoder_diagnostics()
            if diagnostics:
                for encoder, reason in diagnostics.items():
                    print(f"  - {encoder}: {reason}")

    input_root = args.input.resolve()
    output_root = args.output.resolve()

    if args.apply:
        output_root.mkdir(parents=True, exist_ok=True)

    output_json_path = output_root / "metadata.json"
    output_data = {}

    files = extract_files_to_process(input_root, config)
    for video_file in files:
        print(f"Processing: {video_file}")

        # --- Step 1: find metadata ---
        print("  [1/3] Extracting metadata...")
        meta = VideoMetadata(path=video_file)
        meta = extract_all_metadata(meta, config, no_cache=args.no_cache)
        if not meta.final_result:
            print("  Failed to extract metadata. Skipping.\n")
            continue

        fr = meta.final_result
        print(f"  Series:  {fr['series_full_name']}")
        print(f"  Title:   {fr['name']}")
        print(f"  Season:  {fr['seasonNumber']}")
        print(f"  Episode: {fr['number']}")

        output_path = (
            output_root
            / sanitize_filename(fr["series_full_name"])
            / f"Season {zero_pad(fr['seasonNumber'])}"
            / (
                f"{sanitize_filename(fr['series_full_name'])} - "
                f"S{zero_pad(fr['seasonNumber'])}"
                f"E{zero_pad(fr['number'])} - "
                f"{sanitize_filename(fr['name'])}"
                ".mkv"
            )
        )
        output_data[str(video_file)] = {"output_path": str(output_path)}

        # --- Step 2: compress ---
        print(f"  [2/3] Compress -> {output_path}")
        if args.apply:
            output_path.parent.mkdir(parents=True, exist_ok=True)

        cmd, result = compress_file(
            video_file,
            output_path,
            crf=args.crf,
            preset=args.preset,
            tune=args.tune,
            profile=args.profile,
            hw_encoder=hw_encoder,
            apply=args.apply,
        )

        if not cmd:
            # Already H.264 — copy to destination when applying
            print("  Already H.264, skipping re-encode.")
            if args.apply and not output_path.exists():
                print(f"  Copying {video_file} -> {output_path}")
                shutil.copy2(video_file, output_path)
        elif dry_run:
            print(f"  DRY RUN ffmpeg: {' '.join(cmd)}")
        elif result is not None and result.returncode != 0:
            print(
                f"  Compression failed (exit {result.returncode}). Skipping metadata burn.\n"
            )
            continue

        # --- Step 3: burn metadata into the MKV ---
        print("  [3/3] Burning metadata into MKV...")
        if args.apply:
            if output_path.exists():
                ok = write_mkv_metadata(output_path, meta)
                if ok:
                    print("  Metadata written successfully.")
                else:
                    print("  Failed to write metadata.")
            else:
                print("  Output file not found, skipping metadata burn.")
        else:
            try:
                season = int(fr["seasonNumber"])
                episode = int(fr["number"])
                title = f"{fr['series_full_name']} - S{season:02d}E{episode:02d} - {fr['name']}"
            except Exception:
                title = fr.get("name", output_path.stem)
            print(
                f"  DRY RUN mkvpropedit: would write title='{title}' and episode tags."
            )

        print()

    # Save JSON manifest in any case for debugging and future use:
    if output_data:
        existing_data = {}
        if output_json_path.exists():
            try:
                with open(output_json_path, "r", encoding="utf-8") as fh:
                    existing_data = json.load(fh) or {}
                if not isinstance(existing_data, dict):
                    existing_data = {}
            except Exception:
                existing_data = {}
        merged_data = {**existing_data, **output_data}
        with open(output_json_path, "w", encoding="utf-8") as fh:
            json.dump(merged_data, fh, indent=4, sort_keys=True)
        print(f"Metadata manifest saved: {output_json_path}")

    print(
        "\nDone."
        if not dry_run
        else "\nDry run complete. Pass --apply to process files."
    )


if __name__ == "__main__":
    main()
