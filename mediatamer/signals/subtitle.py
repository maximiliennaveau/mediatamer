from typing import Optional, Dict, List, Tuple
import struct
import os
from pathlib import Path
import subprocess
import json
import hashlib
import requests

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
    existing = _check_subtitle_cache(path) or {}
    existing.update(data)

    try:
        with cache_file.open("w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def extract_subtitle_text(
    path: Path, prefer_non_pgs: bool = True, duration_limit: float = 600.0
) -> Optional[str]:
    """Extract first available text subtitle stream."""
    cached = _check_subtitle_cache(path)
    if cached and cached.get("subtitle_text"):
        return cached["subtitle_text"]

    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    j = extract_metadata_ffprobe(path)
    candidates = []
    for s in j.get("streams", []):
        if s.get("codec_type") != "subtitle":
            continue
        codec = (s.get("codec_name") or "").lower()
        is_pgs = codec in ("hdmv_pgs_subtitle", "pgs", "dvd_subtitle")
        candidates.append((is_pgs, codec, s.get("index")))

    if not candidates:
        return None

    if prefer_non_pgs:
        candidates.sort(key=lambda x: (x[0],))

    # Try text extraction first
    for is_pgs, codec, idx in candidates:
        if is_pgs:
            continue
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
                _save_to_subtitle_cache(path, {"subtitle_text": out})
                return out
        except Exception:
            continue

    # Fallback to OCR if requested
    if prefer_non_pgs:
        out = extract_pgs_as_text(path, duration_limit=duration_limit)
        if out:
            _save_to_subtitle_cache(path, {"subtitle_text": out})
        return out
    return None


def extract_pgs_as_text(path: Path, duration_limit: float = 600.0) -> Optional[str]:
    """OCR PGS/DVD subtitles."""
    # This is a wrapper around extract_credits_text but for a single range
    return extract_credits_text(path, custom_ranges=[(0.0, duration_limit)])


def extract_credits_text(
    path: Path,
    opening_duration: float = 180.0,
    closing_duration: float = 180.0,
    custom_ranges: Optional[List[Tuple[float, float]]] = None,
) -> Optional[str]:
    """Extract text from specified ranges using OCR."""
    cached = _check_subtitle_cache(path)
    if cached and cached.get("credits_text"):
        return cached["credits_text"]

    if not path.exists():
        return None

    import shutil

    if not shutil.which("tesseract"):
        return None

    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return None

    import tempfile

    # 1. Identify PGS/DVD stream
    j = extract_metadata_ffprobe(path)
    pgs_idx = None
    width, height = 1920, 1080
    for s in j.get("streams", []):
        if s.get("codec_type") == "subtitle" and s.get("codec_name") in (
            "hdmv_pgs_subtitle",
            "pgs",
            "dvd_subtitle",
        ):
            pgs_idx = s.get("index")
            width = s.get("width") or (
                720 if s.get("codec_name") == "dvd_subtitle" else 1920
            )
            height = s.get("height") or (
                576 if s.get("codec_name") == "dvd_subtitle" else 1080
            )
            break

    if pgs_idx is None:
        return None

    # 2. Determine ranges
    ranges = custom_ranges
    if not ranges:
        total_duration = float(j.get("format", {}).get("duration", 0))
        ranges = [
            (0.0, opening_duration),
            (max(0.0, total_duration - closing_duration), closing_duration),
        ]

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
                f"[1:v][0:{pgs_idx}]overlay,fps=0.2",
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
        _save_to_subtitle_cache(path, {"credits_text": out})
    return out


def compute_file_hash(path: str) -> Optional[str]:
    """Compute OpenSubtitles compatible hash for a video file."""
    if not os.path.exists(path):
        return None

    try:
        longlongformat = "<q"  # little-endian long long
        bytesize = struct.calcsize(longlongformat)

        with open(path, "rb") as f:
            filesize = os.path.getsize(path)
            hash_val = filesize

            if filesize < 65536 * 2:
                return None

            for _ in range(65536 // bytesize):
                buffer = f.read(bytesize)
                (l_value,) = struct.unpack(longlongformat, buffer)
                hash_val += l_value
                hash_val = hash_val & 0xFFFFFFFFFFFFFFFF  # to remain as 64bit

            f.seek(max(0, filesize - 65536), 0)
            for _ in range(65536 // bytesize):
                buffer = f.read(bytesize)
                (l_value,) = struct.unpack(longlongformat, buffer)
                hash_val += l_value
                hash_val = hash_val & 0xFFFFFFFFFFFFFFFF

        return "{:016x}".format(hash_val)
    except Exception:
        return None


def lookup_subtitle_hash(hash_str: str) -> Optional[Dict]:
    """
    Placeholder for subtitle-hash database lookup.
    Ideally this would query an API (OpenSubtitles, etc).
    """
    # TODO: Implement actual API lookup given a hash
    # For now, this is a no-op that returns None.
    return None


def compare_subtitle_to_description(subtitle: str, description: str) -> float:
    """Compare subtitle to description and return a similarity score (0.0 to 1.0)."""
    api_key = os.environ.get("LLM_API_KEY")
    api_url = os.environ.get(
        "LLM_API_URL", "https://api.openai.com/v1/chat/completions"
    )
    model = os.environ.get("LLM_MODEL", "gpt-4o-mini")

    if not api_key or not subtitle or not description:
        return 0.0

    # Narrow down subtitle snippet to avoid token limits and focus on content
    # Taking middle portion might be better for plot points
    subtitle_snippet = subtitle[:3000]

    prompt = f"""You are an expert TV show episode matcher. I will provide you with a snippet of extracted subtitles from a video file and an episode description. 
Your task is to determine if the subtitles match the episode description.

Subtitle Snippet:
---
{subtitle_snippet}
---

Episode Description:
---
{description}
---

Return a JSON object with a single key "score" containing a float between 0.0 and 1.0, where 1.0 is a perfect match and 0.0 is no match. Only return the JSON object."""

    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
        }
        resp = requests.post(api_url, headers=headers, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        result = json.loads(content)
        return float(result.get("score", 0.0))
    except Exception as e:
        # Fallback to 0.0 on error
        print(f"LLM Comparison Error: {e}")
        return 0.0


__all__ = [
    "extract_subtitle_text",
    "extract_pgs_as_text",
    "extract_credits_text",
    "compute_file_hash",
    "lookup_subtitle_hash",
    "compare_subtitle_to_description",
]
