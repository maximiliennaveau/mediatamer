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


_HW_ENCODER_CANDIDATES = [
    "hevc_nvenc",  # NVIDIA
    "hevc_qsv",  # Intel Quick Sync
    "hevc_amf",  # AMD AMF
    "hevc_vaapi",  # Linux generic VA-API (Intel/AMD)
    "hevc_videotoolbox",  # macOS
]

_HW_ENCODER_TEST_CMDS: dict[str, list[str]] = {
    "hevc_nvenc": [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        "nullsrc=s=64x64:d=1",
        "-c:v",
        "hevc_nvenc",
        "-f",
        "null",
        "-",
    ],
    "hevc_qsv": [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        "nullsrc=s=64x64:d=1",
        "-c:v",
        "hevc_qsv",
        "-f",
        "null",
        "-",
    ],
    "hevc_amf": [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        "nullsrc=s=64x64:d=1",
        "-c:v",
        "hevc_amf",
        "-f",
        "null",
        "-",
    ],
    "hevc_vaapi": [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-vaapi_device",
        "/dev/dri/renderD128",
        "-f",
        "lavfi",
        "-i",
        "nullsrc=s=64x64:d=1",
        "-vf",
        "format=nv12,hwupload",
        "-c:v",
        "hevc_vaapi",
        "-f",
        "null",
        "-",
    ],
    "hevc_videotoolbox": [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        "nullsrc=s=64x64:d=1",
        "-c:v",
        "hevc_videotoolbox",
        "-f",
        "null",
        "-",
    ],
}


def detect_hw_encoder() -> Optional[str]:
    """Return the first working H.265 hardware encoder name, or None for software fallback.

    Tries each candidate by running a short null encode.  The first encoder
    whose test command exits with code 0 is returned.
    """
    for encoder in _HW_ENCODER_CANDIDATES:
        test_cmd = _HW_ENCODER_TEST_CMDS.get(encoder)
        if not test_cmd:
            continue
        try:
            result = subprocess.run(
                test_cmd, capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                return encoder
        except Exception:
            continue
    return None


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
    hw_encoder: Optional[str] = None,
) -> List[str]:
    """Build an ffmpeg command that re-encodes video and copies audio/subtitles.

    When *hw_encoder* is set to a hardware encoder name (e.g. ``hevc_nvenc``,
    ``hevc_qsv``, ``hevc_amf``, ``hevc_vaapi``), that encoder is used instead
    of the software ``libx265``.  Pass ``None`` to force software encoding.

    Quality / preset mapping per encoder family:

    * **nvenc / qsv / amf**: ``-rc constqp -qp <crf>``; NVENC preset mapped to
      ``p1``–``p7``; QSV/AMF accept the same software preset names.
    * **vaapi**: requires ``-vaapi_device`` before the input and a
      ``format=nv12,hwupload`` filter; quality via ``-qp``.
    * **videotoolbox**: quality via ``-q:v``.
    * **software (None)**: ``libx265 -crf``.

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

    cmd: list[str] = ["ffmpeg", "-hide_banner", "-y", "-threads", "0"]

    # VAAPI requires the device to be declared before the input
    if hw_encoder == "hevc_vaapi":
        cmd += ["-vaapi_device", "/dev/dri/renderD128"]

    cmd += ["-i", str(infile)]
    if srtfile:
        cmd += ["-i", str(srtfile)]
    cmd += ["-map", "0"]
    if srtfile:
        cmd += ["-map", "1"]

    if hw_encoder == "hevc_nvenc":
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
            "64",
        ]
        if profile:
            video_args += ["-profile:v", profile]
        # tune not supported by hevc_nvenc — omitted intentionally
    elif hw_encoder == "hevc_qsv":
        video_args = [
            "-c:v",
            "hevc_qsv",
            "-global_quality",
            str(crf),
            "-preset",
            preset,
        ]
        if profile:
            video_args += ["-profile:v", profile]
    elif hw_encoder == "hevc_amf":
        video_args = [
            "-c:v",
            "hevc_amf",
            "-rc",
            "cqp",
            "-qp_i",
            str(crf),
            "-qp_p",
            str(crf),
        ]
        if profile:
            video_args += ["-profile:v", profile]
    elif hw_encoder == "hevc_vaapi":
        video_args = [
            "-vf",
            "format=nv12,hwupload",
            "-c:v",
            "hevc_vaapi",
            "-qp",
            str(crf),
        ]
    elif hw_encoder == "hevc_videotoolbox":
        video_args = [
            "-c:v",
            "hevc_videotoolbox",
            "-q:v",
            str(crf),
        ]
        if profile:
            video_args += ["-profile:v", profile]
    else:
        # Software fallback
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
    hw_encoder: Optional[str] = None,
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
        hw_encoder=hw_encoder,
    )
    if not apply:
        return cmd, None
    res = subprocess.run(cmd)
    return cmd, res
