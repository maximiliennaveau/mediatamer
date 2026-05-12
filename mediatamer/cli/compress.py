"""Compress module for MediaTamer (converts videos to optimal format for Jellyfin streaming on DS418 NAS)."""

import argparse
import subprocess
import re
import shutil
from pathlib import Path
from typing import Optional

try:
    import argcomplete
except ImportError:
    argcomplete = None
from mediatamer.cli.argparse_utils import add_common_arguments
from mediatamer.utils import extract_files_to_process, detect_language


def find_external_srt(base: Path) -> Optional[Path]:
    """Find external SRT file with same base name."""
    suffixes = ["", ".vostfr", ".VOSTFR", ".fr", ".FR", ".fra", ".FRA"]
    suffixes += [".eng", ".ENG", ".en", ".EN", ".english", ".ENGLISH"]
    for suf in suffixes:
        srt_path = base.with_suffix(f"{suf}.srt")
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
            line for line in candidates if re.search(r"\b(eng|english)\b", line, re.I)
        ]
        if english_subs:
            match = re.search(r"track\s*(\d+)", english_subs[0], re.I)
            if match:
                return match.group(1)
        # Then French
        french_subs = [
            line
            for line in candidates
            if re.search(r"\b(fra|fre|french|vost)\b", line, re.I)
        ]
        if french_subs:
            match = re.search(r"track\s*(\d+)", french_subs[0], re.I)
            if match:
                return match.group(1)
    except Exception:
        pass
    return None


def get_srt_lang(srt_path: Path) -> str:
    """Detect language of an SRT file and return a 3-letter ISO639-2 code.

    Falls back to 'eng' on error or unknown language.
    """
    try:
        lines = []
        with open(srt_path, "r", encoding="utf-8", errors="ignore") as fh:
            for raw in fh:
                line = raw.strip()
                if not line:
                    continue
                # Skip numeric indices
                if re.match(r"^\d+$", line):
                    continue
                # Skip timestamp lines like 00:00:01,000 --> 00:00:04,000
                if re.match(
                    r"^\d{2}:\d{2}:\d{2}[,\.]\d{3}\s*--?>\s*\d{2}:\d{2}:\d{2}[,\.]\d{3}",
                    line,
                ):
                    continue
                lines.append(line)
                if len(lines) >= 200:
                    break
        text = " ".join(lines)
        lang = detect_language(text)
        iso_map = {
            "en": "eng",
            "fr": "fra",
            "es": "spa",
            "de": "deu",
            "it": "ita",
            "pt": "por",
            "zh": "zho",
            "ja": "jpn",
            "ru": "rus",
            "ar": "ara",
            "nl": "nld",
            "sv": "swe",
            "no": "nor",
            "pl": "pol",
            "ko": "kor",
            "hi": "hin",
        }
        return iso_map.get(lang, "eng")
    except Exception:
        return "eng"


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
        "all",  # Keep all audio tracks
        "-E",
        "av_aac,av_aac,av_aac",  # AAC (applies to selected tracks)
        "-B",
        "192,192,192",  # 192 kbps (applies to selected tracks)
        "-s",
        "all",  # Keep all subtitle tracks
    ]
    if srtfile:
        srt_lang = get_srt_lang(srtfile)
        cmd.extend(["--srt-file", str(srtfile), "--srt-lang", srt_lang])
    return cmd


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
    if args.exts:
        exts = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in args.exts}
        files = [p for p in files if p.suffix.lower() in exts]

    # Check HandBrakeCLI
    if shutil.which("HandBrakeCLI") is None:
        print("Error: HandBrakeCLI not found in PATH")
        return 1

    for infile in sorted(files):
        if input_path.is_file():
            outfile = output_dir / infile.with_suffix(".mkv").name
        else:
            outfile = output_dir / infile.relative_to(input_path).with_suffix(".mkv")
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
