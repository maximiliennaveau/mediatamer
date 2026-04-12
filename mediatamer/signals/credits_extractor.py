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
from mediatamer.signals.cast_from_subtitles import CastProfile


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

        if not meta.technical or not meta.technical.duration:
            print("[Credits Extractor] Video duration unknown. Skipping.")
            return CastProfile()

        duration = meta.technical.duration

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

        meta.cast_profile = self._refine_with_ai(raw_text)
        return meta.cast_profile

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

    def _refine_with_ai(self, raw_text: str) -> CastProfile:
        """
        Use the LLM to clean up the noisy OCR text into a structured profile.
        """
        # Limit input to avoid token overflow
        snip = raw_text[:8000] if len(raw_text) > 8000 else raw_text

        prompt = f"""
You are a media credits parser. Your job is to classify names from raw OCR text extracted from video credits.

STRICT CLASSIFICATION RULES — read carefully before assigning any name:

1. fictional_characters:
   - ONLY names of story characters that appear in the narrative (e.g. "Walter White", "Sherlock Holmes", "Sintel").
   - Do NOT include real person names here, even if they appear alongside character names.
   - Do NOT include production company names, sponsors, or technology/brand names (e.g. "DivX", "Dolby" are NOT characters).

2. real_actors:
   - ONLY real human beings who perform in the show/film (voice actors accepted).
   - These are the people listed next to character names, or in the cast section.
   - Do NOT include directors, editors, composers, or other crew here.
   - Do NOT include organization names (e.g. "Blender Foundation" is NOT an actor).

3. crew_names:
   - Real individual HUMAN BEINGS who worked behind the camera: directors, producers, composers, writers, editors, cinematographers.
   - Do NOT include company or organization names here.
   - If you are unsure whether a name belongs in real_actors or crew_names, prefer crew_names.

4. producers_and_funders:
   - Names of production companies, studios, foundations, funds, or sponsors that provided financial or production support.
   - These are ORGANIZATIONS, not people (e.g. "Blender Foundation", "Netherlands Film Fund").

5. show_name_hints:
   - The primary display title of the show or film (e.g. "Sintel", "Doctor Who").
   - Do NOT use project codenames, subtitles, or descriptions (e.g. "The Durian Open Movie Project" is a codename, NOT a title).
   - Return a list of strings.

6. confidence: integer 0-100 reflecting your overall confidence in the extraction quality.

IMPORTANT DISAMBIGUATION TIPS:
- Brand names (DivX, Dolby, IMAX, etc.) are NEVER people — omit them from all person fields.
- A name appearing on its own line, in ALL CAPS, as the only text, is more likely a title than a character.
- Names preceded by "PRESENTS", "FOUNDATION", "INSTITUTE", "FUND", "PROJECT" are organizations.
- Names preceded by "DIRECTED BY", "MUSIC BY", "EDITED BY", "PRODUCED BY" are individual crew members.
- Names appearing between dashes (e.g. "ALICE SMITH - BOB JONES") are typically cast or crew pairs.

Return ONLY a valid JSON object with exactly these keys:
fictional_characters, real_actors, crew_names, producers_and_funders, show_name_hints, confidence.
No extra text, no markdown.

### RAW OCR TEXT:
{snip}
"""
        response = run_ai(prompt, json_mode=True)
        try:
            data = json.loads(response)
            return CastProfile.from_dict(data)
        except Exception as e:
            print(f"[Credits Extractor] AI parsing error: {e}")
            return CastProfile()
