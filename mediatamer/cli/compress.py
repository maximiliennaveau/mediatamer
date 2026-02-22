"""Compress module for MediaTamer (converts videos to optimal format for Jellyfin streaming on DS418 NAS)."""

import argparse
import subprocess
import re
from pathlib import Path
from typing import Optional

try:
    import argcomplete
except ImportError:
    argcomplete = None

VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".avi", ".m4v", ".ts", ".mpg", ".mpeg", ".flv"}


def find_external_srt(base: Path) -> Optional[Path]:
    """Find external SRT file with same base name."""
    suffixes = ["", ".vostfr", ".VOSTFR", ".fr", ".FR", ".fra", ".FRA"]
    suffixes += [".eng", ".ENG", ".en", ".EN", ".english", ".ENGLISH"]
    for suf in suffixes:
        srt_path = base.with_suffix(f"{suf}.srt")
        if srt_path.exists():
            return srt_path
    # Also check plain .srt
    srt_path = base.with_suffix(".srt")
    if srt_path.exists():
        return srt_path
    return None


def find_embedded_sub(infile: Path) -> Optional[str]:
    """Scan for embedded non-PGS subtitle track, preferring English then French."""
    try:
        cmd = ["HandBrakeCLI", "-i", str(infile), "--scan"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        scan_out = result.stdout + result.stderr
        # Look for subtitle lines not PGS
        lines = scan_out.split("\n")
        candidates = []
        for line in lines:
            if "subtitle" in line.lower() and "pgs" not in line.lower():
                candidates.append(line)
        # Prefer English
        english_subs = [
            l for l in candidates if re.search(r"\b(eng|english)\b", l, re.I)
        ]
        if english_subs:
            match = re.search(r"track\s*(\d+)", english_subs[0], re.I)
            if match:
                return match.group(1)
        # Then French
        french_subs = [
            l for l in candidates if re.search(r"\b(fra|fre|french|vost)\b", l, re.I)
        ]
        if french_subs:
            match = re.search(r"track\s*(\d+)", french_subs[0], re.I)
            if match:
                return match.group(1)
    except Exception:
        pass
    return None


def build_handbrake_cmd(
    infile: Path, outfile: Path, srtfile: Optional[Path], embedded_sub: Optional[str]
) -> list[str]:
    """Build HandBrakeCLI command for optimal compression on DS418."""
    # For DS418 (RTD1296, low power), use H.264 instead of H.265 for better compatibility and less CPU
    # CRF 20 for quality, AAC 192kbps, same framerate/resolution
    cmd = [
        "HandBrakeCLI",
        "-i",
        str(infile),
        "-o",
        str(outfile),
        "-f",
        "mkv",
        "-e",
        "x264",  # H.264 for lower CPU usage
        "-q",
        "20",  # CRF 20
        "-a",
        "1,2,3",  # First and second audio tracks
        "-E",
        "av_aac,av_aac,av_aac",  # AAC for all three
        "-B",
        "192,192,192",  # 192 kbps for all three
        "-s",
        "1,2,3",  # Include first subtitle track if available
    ]
    if srtfile:
        cmd.extend(["--srt-file", str(srtfile), "--srt-lang", "eng"])
    elif embedded_sub:
        cmd.extend(["-s", embedded_sub])
    return cmd


def get_agument_parser(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument(
        "--input", "-i", type=Path, required=True, help="Input directory to scan"
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
    argcomplete.autocomplete(parser)
    return parser


def main():
    parser = argparse.ArgumentParser(
        description="Compress video files for optimal Jellyfin streaming on DS418 NAS"
    )
    parser = get_agument_parser(parser)
    args = parser.parse_args()

    input_dir = args.input.resolve()
    if not input_dir.is_dir():
        print(f"Error: {input_dir} is not a directory")
        return 1

    output_dir = args.output.resolve() if args.output else input_dir / "compressed"
    exts = {
        e.lower() if e.startswith(".") else f".{e.lower()}"
        for e in (args.exts or VIDEO_EXTS)
    }

    # Check HandBrakeCLI
    if (
        not subprocess.run(["which", "HandBrakeCLI"], capture_output=True).returncode
        == 0
    ):
        print("Error: HandBrakeCLI not found in PATH")
        return 1

    # Find all video files
    files = [
        p for p in input_dir.rglob("*") if p.is_file() and p.suffix.lower() in exts
    ]

    if not files:
        print("No video files found")
        return 0

    for infile in sorted(files):
        rel_path = infile.relative_to(input_dir)
        outfile = output_dir / rel_path.with_suffix(".mkv")
        if args.apply:
            outfile.parent.mkdir(parents=True, exist_ok=True)

        base = infile.with_suffix("")
        srtfile = find_external_srt(base)
        embedded_sub = None
        if not srtfile and not args.no_embedded:
            embedded_sub = find_embedded_sub(infile)

        cmd = build_handbrake_cmd(infile, outfile, srtfile, embedded_sub)

        print(f"Converting: {infile} -> {outfile}")
        if not args.apply:
            print(f"DRY RUN: {' '.join(cmd)}")
        else:
            result = subprocess.run(cmd)
            if result.returncode != 0:
                print(f"Failed: {infile} (exit {result.returncode})")

    print("Done.")


if __name__ == "__main__":
    main()
