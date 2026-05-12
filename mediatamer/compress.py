"""Compression API helpers used by the CLI.

Provides helpers to locate external SRTs, detect SRT language, build ffmpeg
commands and optionally run them. This module is independent of CLI parsing so
it can be used programmatically.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Optional, Tuple, List

from mediatamer.utils import detect_language


def find_external_srt(base: Path) -> Optional[Path]:
    """Find external SRT file with same base name.

    Returns the first matching SRT path or ``None``.
    """
    suffixes = ["", ".vostfr", ".VOSTFR", ".fr", ".FR", ".fra", ".FRA"]
    suffixes += [".eng", ".ENG", ".en", ".EN", ".english", ".ENGLISH"]
    for suf in suffixes:
        srt_path = base.with_suffix(f"{suf}.srt")
        if srt_path.exists():
            return srt_path
    return None


def get_srt_lang(srt_path: Path) -> str:
    """Detect language of an SRT file and return a 3-letter ISO639-2 code.

    Falls back to 'eng' on error or unknown language.
    """
    try:
        lines: list[str] = []
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


def count_subtitle_streams(path: Path) -> int:
    """Return the number of subtitle streams in a container using ffprobe.

    Returns 0 on error.
    """
    try:
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "s",
            "-show_entries",
            "stream=index",
            "-of",
            "csv=p=0",
            str(path),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if res.returncode != 0:
            return 0
        lines = [l for l in res.stdout.splitlines() if l.strip()]
        return len(lines)
    except Exception:
        return 0


def build_ffmpeg_cmd(
    infile: Path,
    outfile: Path,
    srtfile: Optional[Path],
    srt_lang: Optional[str],
    crf: int,
    preset: str,
    tune: Optional[str],
    profile: Optional[str],
) -> List[str]:
    """Build an ffmpeg command that re-encodes video and copies audio/subtitles.

    The function returns a list suitable for ``subprocess.run``.
    """
    cmd: list[str] = [
        "ffmpeg",
        "-hide_banner",
        "-y",
        "-threads",
        "0",
        "-i",
        str(infile),
    ]
    if srtfile:
        cmd += ["-i", str(srtfile)]
    cmd += ["-map", "0"]
    if srtfile:
        cmd += ["-map", "1"]

    video_args = ["-c:v", "libx264", "-crf", str(crf), "-preset", preset]
    if tune:
        video_args += ["-tune", tune]
    if profile:
        video_args += ["-profile:v", profile]

    cmd += video_args + ["-c:a", "copy", "-c:s", "copy"]

    if srtfile:
        idx = count_subtitle_streams(infile)
        lang = srt_lang or get_srt_lang(srtfile)
        cmd += [f"-metadata:s:s:{idx}", f"language={lang}"]
    cmd += [str(outfile)]
    return cmd


def compress_file(
    infile: Path,
    outfile: Path,
    crf: int = 18,
    preset: str = "slow",
    tune: Optional[str] = None,
    profile: Optional[str] = "high",
    apply: bool = False,
) -> Tuple[List[str], Optional[subprocess.CompletedProcess]]:
    """Build (and optionally run) the ffmpeg command for a single file.

    Returns a tuple of (cmd, result) where ``result`` is the CompletedProcess
    when ``apply`` is True, otherwise ``None``.
    """
    base = infile.with_suffix("")
    srtfile = find_external_srt(base)
    srt_lang = get_srt_lang(srtfile) if srtfile else None
    cmd = build_ffmpeg_cmd(
        infile, outfile, srtfile, srt_lang, crf, preset, tune, profile
    )
    if not apply:
        return cmd, None
    res = subprocess.run(cmd)
    return cmd, res
