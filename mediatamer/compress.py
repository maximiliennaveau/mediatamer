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


def is_already_compressed(path: Path, profile: Optional[str] = None) -> bool:
    """Return True if the first video stream is already H.264 or H.265-encoded.

    Uses ffprobe to inspect the codec (and optionally the profile) of the
    first video stream.  Returns False on any error so the caller falls back
    to re-encoding.
    """
    try:
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name,profile",
            "-of",
            "csv=p=0",
            str(path),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if res.returncode != 0:
            return False
        output = res.stdout.strip()
        if not output:
            return False
        parts = [p.strip() for p in output.split(",")]
        codec = parts[0].lower()
        if codec not in ("h264", "hevc", "h265"):
            return False
        if profile and codec == "h264" and len(parts) > 1:
            stream_profile = parts[1].lower().replace(" ", "")
            if profile.lower().replace(" ", "") not in stream_profile:
                return False
        return True
    except Exception:
        return False


def build_ffmpeg_cmd(
    infile: Path,
    outfile: Path,
    srtfile: Optional[Path],
    srt_lang: Optional[str],
    crf: int,
    preset: str,
    tune: Optional[str],
    profile: Optional[str],
    use_nvenc: bool = False,
) -> List[str]:
    """Build an ffmpeg command that re-encodes video and copies audio/subtitles.

    When *use_nvenc* is True the NVIDIA NVENC hardware encoder is used instead
    of libx265.  The quality parameter mapping is:

    * Encoder:  ``hevc_nvenc`` (NVENC H.265) instead of ``libx265``
    * Quality:  ``-rc constqp -qp <crf>`` — NVENC has no CRF mode; QP is the
      closest equivalent.  The same numeric value as the software CRF produces
      slightly different (but comparable) quality.
    * Preset:   NVENC uses ``p1``…``p7`` (p7 = best quality / slowest).
      The software preset name is mapped automatically.
    * Profile:  same ``-profile:v`` flag works for both encoders.
    * Tune:     NVENC does not support the same tune names; ignored when NVENC
      is active.

    The function returns a list suitable for ``subprocess.run``.
    """
    _NVENC_PRESET_MAP = {
        "ultrafast": "p1",
        "superfast": "p2",
        "veryfast": "p3",
        "faster": "p4",
        "fast": "p4",
        "medium": "p5",
        "slow": "p6",
        "slower": "p6",
        "veryslow": "p7",
    }

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

    if use_nvenc:
        nvenc_preset = _NVENC_PRESET_MAP.get(preset, "p7")
        video_args = [
            "-c:v",
            "hevc_nvenc",
            "-rc",
            "constqp",
            "-qp",
            str(crf),
            "-preset",
            nvenc_preset,
            "-surfaces",
            "64",  # increase concurrent surfaces for throughput
        ]
        if profile:
            video_args += ["-profile:v", profile]
        # tune is not supported by hevc_nvenc — omitted intentionally
    else:
        video_args = ["-c:v", "libx265", "-crf", str(crf), "-preset", preset]
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
    crf: int = 20,
    preset: str = "veryslow",
    tune: Optional[str] = None,
    profile: Optional[str] = "main",
    use_nvenc: bool = False,
    apply: bool = False,
) -> Tuple[List[str], Optional[subprocess.CompletedProcess]]:
    """Build (and optionally run) the ffmpeg command for a single file.

    Returns a tuple of (cmd, result) where ``result`` is the CompletedProcess
    when ``apply`` is True, otherwise ``None``.
    """
    if is_already_compressed(infile, profile=profile):
        return [], None
    base = infile.with_suffix("")
    srtfile = find_external_srt(base)
    srt_lang = get_srt_lang(srtfile) if srtfile else None
    cmd = build_ffmpeg_cmd(
        infile,
        outfile,
        srtfile,
        srt_lang,
        crf,
        preset,
        tune,
        profile,
        use_nvenc=use_nvenc,
    )
    if not apply:
        return cmd, None
    res = subprocess.run(cmd)
    return cmd, res
