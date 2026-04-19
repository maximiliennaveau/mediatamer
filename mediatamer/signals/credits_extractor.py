import subprocess
import os
import tempfile
import json
import shutil
from typing import List, Tuple, Optional, Dict, Any
from pathlib import Path

try:
    import pytesseract
    from PIL import Image
except ImportError:
    pytesseract = None

from mediatamer.ai import run_ai
from mediatamer.signals.video_metadata import VideoMetadata
from mediatamer.signals.cast_from_subtitles import CastProfile, _build_cast_prompt


def extract_credits(
    meta: VideoMetadata, config: Optional[Dict[str, Any]] = None
) -> CastProfile:
    """Main entry point to extract credits from a video file."""
    extractor = VideoCreditsExtractor(config)
    meta.cast_profile = extractor.extract(meta)
    return meta.cast_profile


class VideoCreditsExtractor:
    """
    Extracts cast and crew information from video frames (opening/closing credits).
    Uses ffmpeg for frame extraction and Tesseract for OCR.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.fps = self.config.get("credits-scan-fps", 0.2)  # 1 frame every 5 seconds
        self.start_duration = self.config.get(
            "credits-start-duration", 120
        )  # first 2 mins
        self.end_duration = self.config.get("credits-end-duration", 300)  # last 5 mins

    def extract(self, meta: VideoMetadata) -> CastProfile:
        """
        Extracts credits from video frames and returns a CastProfile.
        """
        if not pytesseract or not shutil.which("tesseract"):
            print("[Credits Extractor] Tesseract not found. Skipping.")
            return CastProfile()

        if not meta.technical or not meta.technical["duration"]:
            print("[Credits Extractor] Video duration unknown. Skipping.")
            return CastProfile()

        duration = meta.technical["duration"]

        # Define ranges: [0, start_duration] and [duration - end_duration, duration]
        ranges = []
        ranges.append((0, min(duration, self.start_duration)))
        ranges.append((max(0, duration - self.end_duration), duration))

        print(
            f"[Credits Extractor] Scanning video frames for credits in {len(ranges)} ranges:\n\t{ranges}"
        )

        raw_text = self._extract_text_from_frames(meta.path, ranges)
        if not raw_text.strip():
            return CastProfile()

        filtered_text = self._filter_ocr_text(raw_text)
        if not filtered_text.strip():
            return CastProfile()

        return self._refine_with_ai(filtered_text).to_dict()

    def _extract_text_from_frames(
        self, video_path: Path, ranges: List[Tuple[float, float]]
    ) -> str:
        """
        Use ffmpeg to extract frames and OCR them.
        """
        all_text = []

        with tempfile.TemporaryDirectory() as tmpdir:
            for i, (start, dur) in enumerate(ranges):
                # Filter chain explanation:
                # - fps: sample at low rate
                # - scale: ensure enough resolution for OCR but not too huge
                # - format=gray: grayscale for OCR
                # - lutyuv: thresholding to make text pop (assume white on dark)
                # - negate: convert to black on white for better Tesseract performance
                filter_chain = (
                    f"fps={self.fps},scale=1280:-1,format=gray,"
                    f"lutyuv=y='if(gt(val,128),255,0)',negate"
                )

                cmd = [
                    "ffmpeg",
                    "-loglevel",
                    "error",
                    "-ss",
                    str(start),
                    "-i",
                    str(video_path),
                    "-t",
                    str(dur),
                    "-vf",
                    filter_chain,
                    "-f",
                    "image2",
                    os.path.join(tmpdir, f"range_{i}_%04d.png"),
                ]

                try:
                    subprocess.run(cmd, check=True, timeout=120)
                except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                    print(f"[Credits Extractor] FFmpeg error/timeout in range {i}: {e}")
                    continue

            # Process extracted images
            images = sorted([f for f in os.listdir(tmpdir) if f.endswith(".png")])
            for img_name in images:
                try:
                    img_path = os.path.join(tmpdir, img_name)
                    text = pytesseract.image_to_string(Image.open(img_path))
                    if text.strip():
                        all_text.append(text.strip())
                except Exception as e:
                    print(f"[Credits Extractor] OCR error on {img_name}: {e}")
                    continue

        return "\n---\n".join(all_text)

    def _filter_ocr_text(self, text: str) -> str:
        """Filter noise from raw OCR output (short lines, digit-only lines, duplicates)."""
        seen_previous = None
        cleaned: List[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if len(stripped) < 3:
                continue
            alpha_chars = [c for c in stripped if c.isalpha()]
            if len(alpha_chars) < len(stripped) * 0.4:
                continue
            non_ascii = [c for c in stripped if ord(c) > 127]
            if len(non_ascii) > len(stripped) * 0.4:
                continue
            if stripped == seen_previous:
                continue
            cleaned.append(stripped)
            seen_previous = stripped
        return "\n".join(cleaned)

    def _refine_with_ai(self, raw_text: str) -> CastProfile:
        """
        Use the LLM to clean up the noisy OCR text into a structured profile.
        """
        # Limit input to avoid token overflow
        snip = raw_text[:8000] if len(raw_text) > 8000 else raw_text
        prompt = _build_cast_prompt(snip)
        response = run_ai(prompt, self.config, json_mode=True)
        try:
            data = json.loads(response)
            return CastProfile.from_dict(data)
        except Exception as e:
            print(f"[Credits Extractor] AI parsing error: {e}")
            return CastProfile()
