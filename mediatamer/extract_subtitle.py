from pathlib import Path
from typing import Optional
import subprocess

from .metadata import ffprobe_json


def extract_subtitle_text(path: Path, prefer_non_pgs: bool = True) -> Optional[str]:
    """Extract the first available text subtitle stream from a video as a string.

    - Uses ffprobe (via `ffprobe_json`) to discover subtitle streams.
    - Attempts to extract each subtitle stream with ffmpeg into SRT text.
    - Prefers non-PGS text subtitles when `prefer_non_pgs` is True.

    Returns the subtitle text or None if no extractable text subtitles found.
    """
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
        is_pgs = codec in ('hdmv_pgs_subtitle', 'pgs')
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

    return None



def extract_pgs_as_text(path: Path) -> Optional[str]:
    """Extract PGS subtitles and use OCR to convert them to text."""
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
    
    # 1. Identify PGS stream index
    j = ffprobe_json(path)
    pgs_idx = None
    for s in j.get('streams', []):
        if s.get('codec_type') == 'subtitle' and s.get('codec_name') in ('hdmv_pgs_subtitle', 'pgs'):
            pgs_idx = s.get('index')
            break
    
    if pgs_idx is None:
        return None

    text_content = []
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Extract frames. 
        # fps=0.1 means 1 frame every 10 seconds.
        # We need to map only the subtitle stream.
        # Note: ffmpeg can extract subtitle frames as images provided they are graphical.
        
        cmd = [
            'ffmpeg', '-loglevel', 'error', 
            '-i', str(path),
            '-map', f'0:{pgs_idx}',
            '-vf', 'fps=0.2',  # 1 frame every 5 seconds
            '-f', 'image2',
            f'{tmpdir}/sub_%03d.png'
        ]
        
        try:
            subprocess.run(cmd, check=True, timeout=120)  # 2 min max for extraction
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            pass

        # OCR each image
        # Provide a custom config to tesseract if needed, but default is usually okay for English.
        # We might want to restrict characters if we knew them, but we don't.
        
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

__all__ = ["extract_subtitle_text", "extract_pgs_as_text"]

