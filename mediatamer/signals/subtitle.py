from typing import Optional, Dict, List, Tuple
import os
from pathlib import Path
import subprocess
import json
import hashlib
import re
from datetime import timedelta

from mediatamer.signals.ffprobe import extract_metadata_ffprobe


def _get_file_hash(path: Path) -> str:
    """Get a hash of the file for cache key."""
    stat = path.stat()
    return hashlib.md5(
        f"{path.name}_{stat.st_size}_{stat.st_mtime}".encode()
    ).hexdigest()


def _check_subtitle_cache(path: Path) -> Optional[dict]:
    """Check if subtitles are cached for this file."""
    cache_dir = os.environ.get("SUBTITLE_CACHE_DIR")
    if not cache_dir:
        return None
    cache_path = Path(cache_dir)
    if not cache_path.exists():
        return None
    file_hash = _get_file_hash(path)
    cache_file = cache_path / f"{file_hash}.json"
    if not cache_file.exists():
        return None
    try:
        with cache_file.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _save_to_subtitle_cache(path: Path, data: dict):
    """Save metadata to cache."""
    cache_dir = os.environ.get("SUBTITLE_CACHE_DIR")
    if not cache_dir:
        return
    cache_path = Path(cache_dir)
    try:
        cache_path.mkdir(parents=True, exist_ok=True)
    except Exception:
        return

    file_hash = _get_file_hash(path)
    cache_file = cache_path / f"{file_hash}.json"

    # Merge with existing data if present
    existing = {}
    if cache_file.exists():
        try:
            with cache_file.open("r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            pass

    existing.update(data)

    try:
        with cache_file.open("w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


class SRTParser:
    """Helper to parse and filter SRT content."""

    def __init__(self, srt_content: str):
        self.srt_content = srt_content
        self.entries = self._parse(srt_content)

    def _parse_time(self, time_str: str) -> float:
        """Parse SRT time format (00:00:20,000) to seconds."""
        try:
            h, m, s_ms = time_str.split(":")
            s, ms = s_ms.split(",")
            return timedelta(
                hours=int(h),
                minutes=int(m),
                seconds=int(s),
                milliseconds=int(ms),
            ).total_seconds()
        except (ValueError, IndexError):
            return 0.0

    def _parse(self, content: str) -> List[Dict]:
        entries = []
        # Basic SRT regex: index, time range, and text block
        # Using a more robust regex that handles extra newlines
        pattern = re.compile(
            r"(\d+)\s*\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\s*\n(.*?)(?=\n\d+\s*\n\d{2}:\d{2}:\d{2},\d{3} -->|\Z)",
            re.DOTALL,
        )
        matches = list(pattern.finditer(content))
        if not matches and content.strip():
            # Fallback for plain text (no SRT structure)
            return [{"index": 0, "start": 0.0, "end": 99999.0, "text": content.strip()}]

        for match in matches:
            idx, start, end, text = match.groups()
            entries.append(
                {
                    "index": int(idx),
                    "start": self._parse_time(start),
                    "end": self._parse_time(end),
                    "text": text.strip(),
                }
            )
        return entries

    def get_range_text(
        self, start_time: Optional[float] = None, end_time: Optional[float] = None
    ) -> str:
        """Filter text by time range."""
        filtered = self.entries
        if start_time is not None:
            filtered = [e for e in filtered if e["end"] >= start_time]
        if end_time is not None:
            filtered = [e for e in filtered if e["start"] <= end_time]

        return "\n".join(e["text"] for e in filtered)


def get_cached_subtitles(path: Path) -> Optional[str]:
    """Retrieve full SRT content from cache if available."""
    cached = _check_subtitle_cache(path)
    if cached:
        return cached.get("subtitle_srt") or cached.get("subtitle_text")
    return None


def get_subtitle_segment(
    path: Path, start_time: Optional[float] = None, end_time: Optional[float] = None
) -> Optional[str]:
    """Get text from a specific time segment using cached SRT or targeted OCR."""
    if not path.exists():
        return None

    # 1. Try Cache
    srt_content = get_cached_subtitles(path)
    if srt_content:
        return SRTParser(srt_content).get_range_text(start_time, end_time)

    # 2. Try Text Streams
    srt_content = _extract_text_sub_streams(path)
    if srt_content:
        return SRTParser(srt_content).get_range_text(start_time, end_time)

    # 3. Targeted OCR
    if start_time is None and end_time is None:
        # Full content requested but we must OCR; take a larger 10m chunk
        return extract_pgs_as_text(path, duration_limit=600.0)

    start = start_time or 0.0
    dur = 60.0  # Default chunk if end not specified
    if end_time is not None:
        dur = max(0.0, end_time - start)

    return _ocr_subtitle_ranges(path, [(start, dur)])


def _find_subtitle_stream(path: Path, pgs_only: bool = False) -> Optional[Dict]:
    """Find a suitable subtitle stream index and metadata."""
    j = extract_metadata_ffprobe(path)
    streams = j.get("streams", [])

    candidates = []
    for s in streams:
        if s.get("codec_type") != "subtitle":
            continue
        codec = (s.get("codec_name") or "").lower()
        is_pgs = codec in ("hdmv_pgs_subtitle", "pgs", "dvd_subtitle")
        if pgs_only and not is_pgs:
            continue
        candidates.append(s)

    if not candidates:
        return None

    # Sort to prefer non-PGS if multiple available and pgs_only is False
    if not pgs_only:
        candidates.sort(
            key=lambda s: s.get("codec_name", "").lower()
            in ("hdmv_pgs_subtitle", "pgs", "dvd_subtitle")
        )

    return candidates[0]


def _extract_text_sub_streams(path: Path) -> Optional[str]:
    """Try to extract a text-based subtitle stream (SRT/ASS/etc) as SRT."""
    j = extract_metadata_ffprobe(path)
    for s in j.get("streams", []):
        if s.get("codec_type") != "subtitle":
            continue
        codec = (s.get("codec_name") or "").lower()
        if codec in ("hdmv_pgs_subtitle", "pgs", "dvd_subtitle"):
            continue

        idx = s.get("index")
        try:
            cmd = [
                "ffmpeg",
                "-loglevel",
                "error",
                "-i",
                str(path),
                "-map",
                f"0:{idx}",
                "-c:s",
                "srt",
                "-f",
                "srt",
                "-",
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            if res.stdout.strip():
                out = res.stdout.strip()
                _save_to_subtitle_cache(path, {"subtitle_srt": out})
                return out
        except Exception:
            continue
    return None


def _ocr_subtitle_ranges(
    path: Path, ranges: List[Tuple[float, float]]
) -> Optional[str]:
    """Internal OCR engine for specific ranges."""
    import shutil

    if not shutil.which("tesseract"):
        return None
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return None

    import tempfile

    stream = _find_subtitle_stream(path, pgs_only=True)
    if not stream:
        return None

    idx = stream.get("index")
    codec = stream.get("codec_name", "")
    width = stream.get("width") or (720 if codec == "dvd_subtitle" else 1920)
    height = stream.get("height") or (576 if codec == "dvd_subtitle" else 1080)

    text_content = []
    with tempfile.TemporaryDirectory() as tmpdir:
        for i, (start, dur) in enumerate(ranges):
            cmd = [
                "ffmpeg",
                "-loglevel",
                "error",
                "-ss",
                str(start),
                "-i",
                str(path),
                "-f",
                "lavfi",
                "-i",
                f"color=size={width}x{height}:rate=24:color=black",
                "-filter_complex",
                f"[1:v][0:{idx}]overlay,fps=0.2",
                "-t",
                str(dur),
                "-f",
                "image2",
                f"{tmpdir}/range_{i}_%03d.png",
            ]
            try:
                subprocess.run(cmd, check=True, timeout=90)
            except Exception:
                continue

        images = sorted([f for f in os.listdir(tmpdir) if f.endswith(".png")])
        for img_name in images:
            try:
                text = pytesseract.image_to_string(
                    Image.open(os.path.join(tmpdir, img_name))
                )
                if text.strip():
                    text_content.append(text.strip())
            except Exception:
                continue

    out = "\n".join(text_content)
    if out:
        # We don't save full subtitle_srt here because it's only a fragment.
        # But we could save it as a specific fragment if we want.
        pass
    return out


def extract_subtitle_text(
    path: Path, prefer_non_pgs: bool = True, duration_limit: float = 600.0
) -> Optional[str]:
    """Extract first available text subtitle stream, or fallback to OCR."""
    cached = get_cached_subtitles(path)
    if cached:
        return cached

    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    # 1. Try text streams
    out = _extract_text_sub_streams(path)
    if out:
        return out

    # 2. Fallback to OCR if requested
    if prefer_non_pgs:
        return extract_pgs_as_text(path, duration_limit=duration_limit)
    return None


def get_subtitle_beginning(path: Path, duration: float = 300.0) -> Optional[str]:
    """Convenience to get the first few minutes of subtitles."""
    return get_subtitle_segment(path, start_time=0.0, end_time=duration)


def get_subtitle_credits(path: Path, duration: float = 300.0) -> Optional[str]:
    """Convenience to get the last few minutes of subtitles."""
    j = extract_metadata_ffprobe(path)
    total_duration = float(j.get("format", {}).get("duration", 0))
    if total_duration <= 0:
        return None
    return get_subtitle_segment(
        path, start_time=max(0.0, total_duration - duration), end_time=total_duration
    )


def extract_pgs_as_text(path: Path, duration_limit: float = 600.0) -> Optional[str]:
    """OCR PGS/DVD subtitles."""
    # This is a wrapper around _ocr_subtitle_ranges but for a single range
    out = _ocr_subtitle_ranges(path, [(0.0, duration_limit)])
    if out:
        _save_to_subtitle_cache(path, {"credits_text": out})
    return out


def extract_credits_text(
    path: Path,
    opening_duration: float = 180.0,
    closing_duration: float = 180.0,
    custom_ranges: Optional[List[Tuple[float, float]]] = None,
) -> Optional[str]:
    """Extract text from specified ranges using cached SRT or OCR."""
    cached = _check_subtitle_cache(path)
    if cached and cached.get("credits_text"):
        return cached["credits_text"]

    if not path.exists():
        return None

    # 1. Determine ranges
    ranges = custom_ranges
    if not ranges:
        j = extract_metadata_ffprobe(path)
        total_duration = float(j.get("format", {}).get("duration", 0))
        ranges = [
            (0.0, opening_duration),
            (max(0.0, total_duration - closing_duration), closing_duration),
        ]

    # 2. Try to get from existing SRT/Text streams first (fast)
    srt_content = get_cached_subtitles(path) or _extract_text_sub_streams(path)
    if srt_content:
        parser = SRTParser(srt_content)
        results = [parser.get_range_text(r[0], r[0] + r[1]) for r in ranges]
        out = "\n".join(filter(None, results))
        if out:
            _save_to_subtitle_cache(path, {"credits_text": out})
            return out

    # 3. Fallback to OCR
    out = _ocr_subtitle_ranges(path, ranges)
    if out:
        _save_to_subtitle_cache(path, {"credits_text": out})
    return out


__all__ = [
    "extract_subtitle_text",
    "extract_pgs_as_text",
    "extract_credits_text",
    "get_cached_subtitles",
    "get_subtitle_segment",
    "get_subtitle_beginning",
    "get_subtitle_credits",
    "SRTParser",
]
