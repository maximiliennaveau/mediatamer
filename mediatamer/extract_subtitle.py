from pathlib import Path
from typing import Optional
import subprocess
import os
import json
import hashlib

from .metadata import ffprobe_json


def _get_file_hash(path: Path) -> str:
    """Get a hash of the file for cache key."""
    stat = path.stat()
    return hashlib.md5(f"{path.name}_{stat.st_size}_{stat.st_mtime}".encode()).hexdigest()


def _check_subtitle_cache(path: Path) -> Optional[dict]:
    """Check if subtitles are cached for this file."""
    cache_dir = os.environ.get('SUBTITLE_CACHE_DIR')
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
        with cache_file.open('r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def extract_subtitle_text(path: Path, prefer_non_pgs: bool = True, duration_limit: float = 200.0) -> Optional[str]:
    """Extract the first available text subtitle stream from a video as a string.

    - Uses ffprobe (via `ffprobe_json`) to discover subtitle streams.
    - Attempts to extract each subtitle stream with ffmpeg into SRT text.
    - Prefers non-PGS text subtitles when `prefer_non_pgs` is True.

    Returns the subtitle text or None if no extractable text subtitles found.
    """
    # Check cache first
    cached = _check_subtitle_cache(path)
    if cached and cached.get('subtitle_text'):
        return cached['subtitle_text']
    
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    j = ffprobe_json(path)
    streams = j.get('streams', [])

    candidates = []
    for s in streams:
        if s.get('codec_type') != 'subtitle':
            continue
        codec = (s.get('codec_name') or '').lower()
        # PGS subtitle codec names
        is_pgs = codec in ('hdmv_pgs_subtitle', 'pgs', 'dvd_subtitle')
        idx = s.get('index')
        candidates.append((is_pgs, codec, idx))

    if not candidates:
        return None

    # Sort candidates: prefer non-pgs if requested
    if prefer_non_pgs:
        candidates.sort(key=lambda x: (x[0],))

    for is_pgs, codec, idx in candidates:
        if idx is None:
            continue
        try:
            cmd = [
                'ffmpeg', '-loglevel', 'error', '-i', str(path),
                '-map', f'0:{idx}', '-c:s', 'srt', '-f', 'srt', '-'
            ]
            res = subprocess.run(cmd, capture_output=True,
                                 text=True, check=True)
            out = res.stdout.strip()
            if out:
                return out
        except Exception:
            # ignore and try next stream
            continue

    if prefer_non_pgs:
        # If we failed to extract text (or didn't find any text streams), try OCR.
        # This handles the case where only bitmap subtitles (PGS/DVD) exist.
        pgs_text = extract_pgs_as_text(path, duration_limit=duration_limit)
        if pgs_text:
            return pgs_text

    return None



def extract_pgs_as_text(path: Path, duration_limit: float = 200.0) -> Optional[str]:
    """Extract PGS/DVD subtitles and use OCR to convert them to text."""
    if not path.exists():
        return None

    import shutil
    if not shutil.which("tesseract"):
        # Fail silently/log warning if tesseract is missing, as we might be in an env without it
        return None

    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return None

    import tempfile
    import os

    # Strategy: Extract 1 frame every 10 seconds to catch most dialogue/titles without
    # generating thousands of images.
    # PGS is image-based. 
    
    # 1. Identify PGS/DVD stream index
    j = ffprobe_json(path)
    pgs_idx = None
    for s in j.get('streams', []):
        if s.get('codec_type') == 'subtitle' and s.get('codec_name') in ('hdmv_pgs_subtitle', 'pgs', 'dvd_subtitle'):
            pgs_idx = s.get('index')
            break
    
    if pgs_idx is None:
        return None

    # Get duration for the collection
    duration = 100.0 # Default
    try:
        duration = float(j.get('format', {}).get('duration', 100.0))
        # Cap duration to avoid processing full movies excessively
        if duration > duration_limit:
            duration = duration_limit
    except (ValueError, TypeError):
        pass

    # Get dimensions
    sub_stream = next((s for s in j.get('streams', []) if s.get('index') == pgs_idx), None)
    width = 1920
    height = 1080
    if sub_stream:
        w = sub_stream.get('width')
        h = sub_stream.get('height')
        if w and h:
            width = w
            height = h
        # If standard DVD size is not present but it is dvd_subtitle, default to PAL/NTSC
        elif sub_stream.get('codec_name') == 'dvd_subtitle':
            width = 720
            height = 576

    text_content = []
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Extract frames by rendering subtitle on black background
        # This works for both PGS and DVD bitmaps
        
        # Limit extraction to first 10 minutes or full duration if shorter, 
        # to avoid processing entire movies if not needed.
        # User wants "robust" checks. Let's do a sampling passed on duration.
        # We stick to fps=0.1 (every 10s) to be faster.
        
        cmd = [
            'ffmpeg', '-loglevel', 'error', 
            '-i', str(path),
            '-f', 'lavfi', '-i', f'color=size={width}x{height}:rate=24:color=black',
            '-filter_complex', f'[1:v][0:{pgs_idx}]overlay,fps=0.1',
            '-t', '600', # Scan 10 minutes
            '-f', 'image2',
            f'{tmpdir}/sub_%03d.png'
        ]
        
        try:
            subprocess.run(cmd, check=True, timeout=120)  # 2 min max
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            # If it fails, we might have partial images
            pass

        # OCR each image
        # Provide a custom config to tesseract if needed, but default is usually okay for English.
        
        images = sorted([f for f in os.listdir(tmpdir) if f.endswith('.png')])
        for img_name in images:
            img_path = os.path.join(tmpdir, img_name)
            try:
                # Use simple image_to_string
                text = pytesseract.image_to_string(Image.open(img_path))
                clean_text = text.strip()
                if clean_text:
                    text_content.append(clean_text)
            except Exception:
                continue

    return "\n".join(text_content)

def extract_credits_text(path: Path, opening_duration: float = 180.0, closing_duration: float = 180.0) -> Optional[str]:
    """Extract text from opening and closing credits using OCR.
    
    This is more targeted than full subtitle extraction and focuses on where
    episode titles typically appear in TV shows.
    
    Args:
        path: Path to video file
        opening_duration: Seconds to scan from start (default 3 minutes)
        closing_duration: Seconds to scan from end (default 3 minutes)
    
    Returns:
        Combined text from opening and closing credits, or None if extraction fails
    """
    # Check cache first
    cached = _check_subtitle_cache(path)
    if cached and cached.get('credits_text'):
        return cached['credits_text']
    
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
    import os

    # Get total duration first
    j = ffprobe_json(path)
    total_duration = float(j.get('format', {}).get('duration', 0))
    
    if total_duration == 0:
        return None

    # Identify PGS/DVD stream
    pgs_idx = None
    for s in j.get('streams', []):
        if s.get('codec_type') == 'subtitle' and s.get('codec_name') in ('hdmv_pgs_subtitle', 'pgs', 'dvd_subtitle'):
            pgs_idx = s.get('index')
            break
    
    if pgs_idx is None:
        return None

    # Get dimensions
    sub_stream = next((s for s in j.get('streams', []) if s.get('index') == pgs_idx), None)
    width = 1920
    height = 1080
    if sub_stream:
        w = sub_stream.get('width')
        h = sub_stream.get('height')
        if w and h:
            width = w
            height = h
        elif sub_stream.get('codec_name') == 'dvd_subtitle':
            width = 720
            height = 576

    text_content = []
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Extract opening credits (first N seconds)
        opening_cmd = [
            'ffmpeg', '-loglevel', 'error',
            '-i', str(path),
            '-f', 'lavfi', '-i', f'color=size={width}x{height}:rate=24:color=black',
            '-filter_complex', f'[1:v][0:{pgs_idx}]overlay,fps=0.2',  # 1 frame every 5 seconds
            '-t', str(opening_duration),
            '-f', 'image2',
            f'{tmpdir}/opening_%03d.png'
        ]
        
        try:
            subprocess.run(opening_cmd, check=True, timeout=60)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            pass

        # Extract closing credits (last N seconds)
        start_time = max(0, total_duration - closing_duration)
        closing_cmd = [
            'ffmpeg', '-loglevel', 'error',
            '-ss', str(start_time),
            '-i', str(path),
            '-f', 'lavfi', '-i', f'color=size={width}x{height}:rate=24:color=black',
            '-filter_complex', f'[1:v][0:{pgs_idx}]overlay,fps=0.2',
            '-t', str(closing_duration),
            '-f', 'image2',
            f'{tmpdir}/closing_%03d.png'
        ]
        
        try:
            subprocess.run(closing_cmd, check=True, timeout=60)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            pass

        # OCR all extracted frames
        images = sorted([f for f in os.listdir(tmpdir) if f.endswith('.png')])
        for img_name in images:
            img_path = os.path.join(tmpdir, img_name)
            try:
                text = pytesseract.image_to_string(Image.open(img_path))
                clean_text = text.strip()
                if clean_text:
                    text_content.append(clean_text)
            except Exception:
                continue

    return "\n".join(text_content)

__all__ = ["extract_subtitle_text", "extract_pgs_as_text", "extract_credits_text"]

