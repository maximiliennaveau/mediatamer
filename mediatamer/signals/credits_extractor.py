import subprocess
import os
import tempfile
import json
import re
import difflib
import shutil
import requests
from typing import List, Tuple, Optional, Dict, Any  # noqa: F401
from pathlib import Path

try:
    import pytesseract
    from PIL import Image
except ImportError:
    pytesseract = None

from mediatamer.ai import run_ai
from mediatamer.signals.video_metadata import VideoMetadata
from mediatamer.signals.cast_from_subtitles import CastProfile, _build_cast_prompt

# Valid human name: 2+ words, only letters (incl. accented), hyphens, apostrophes, periods
_NAME_RE = re.compile(
    r"^[A-Za-z\u00C0-\u024F][A-Za-z\u00C0-\u024F'\-.]*"
    r"(\s[A-Za-z\u00C0-\u024F][A-Za-z\u00C0-\u024F'\-.]*)+$"
)

# Session-level cache: avoids repeat network calls for the same name
_NAME_LOOKUP_CACHE: Dict[str, Optional[str]] = {}


def _lookup_name_online(name: str, tmdb_api_key: str) -> Optional[str]:
    """Verify *name* against TMDB (preferred) or Wikipedia (fallback).

    Returns the canonical name string on success, None if the name cannot
    be confirmed as a real person.
    """
    if name in _NAME_LOOKUP_CACHE:
        return _NAME_LOOKUP_CACHE[name]

    result = _lookup_via_tmdb(name, tmdb_api_key)
    if result is None:
        result = _lookup_via_wikipedia(name)

    _NAME_LOOKUP_CACHE[name] = result
    return result


def _tmdb_search_person(query: str, api_key: str) -> List[dict]:
    """Call TMDB /search/person and return the results list (or [] on failure)."""
    try:
        resp = requests.get(
            "https://api.themoviedb.org/3/search/person",
            params={"api_key": api_key, "query": query, "language": "en-US"},
            timeout=8,
        )
        if resp.ok:
            return resp.json().get("results", [])
    except Exception:
        pass
    return []


def _lookup_via_tmdb(name: str, api_key: str) -> Optional[str]:
    """Look up a person name on TMDB.

    Strategy:
    1. Search with the full name.
    2. If no results, try each individual token (surname, given name) as a
       fallback query — this emulates the web UI's perceived fuzziness for
       single-character OCR errors (e.g. 'Jerna' → surname query 'Coleman'
       yields Jenna Coleman as a candidate).
    3. Across all returned candidates, pick the one with the highest
       SequenceMatcher similarity to *name*; accept if ≥ 0.70.
    """
    # Collect candidate results, preserving insertion order, dedup by id.
    candidates: Dict[int, dict] = {}

    for result in _tmdb_search_person(name, api_key):
        candidates.setdefault(result["id"], result)

    if not candidates:
        # Fallback: search each word individually, aggregate results.
        tokens = name.split()
        for token in tokens:
            if len(token) < 3:
                continue
            for result in _tmdb_search_person(token, api_key):
                candidates.setdefault(result["id"], result)

    if not candidates:
        print(f"TMDB lookup error for {name!r}")
        return None

    # Pick the candidate whose name is closest to the OCR-extracted string.
    best_ratio = 0.0
    best_name = ""
    name_lower = name.lower()
    for result in candidates.values():
        candidate_name = result.get("name", "")
        ratio = difflib.SequenceMatcher(
            None, name_lower, candidate_name.lower()
        ).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_name = candidate_name

    if best_ratio < 0.70:
        print(
            f"TMDB lookup for {name!r} returned {best_name!r} "
            f"with low similarity ({best_ratio:.2f}), rejecting."
        )
        return None
    return best_name


def _lookup_via_wikipedia(name: str) -> Optional[str]:
    try:
        resp = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "opensearch",
                "search": name,
                "limit": 3,
                "format": "json",
            },
            timeout=8,
        )
    except Exception:
        return None
    if not resp.ok:
        return None
    # opensearch returns [query, [titles], [descriptions], [urls]]
    suggestions = resp.json()[1] if len(resp.json()) > 1 else []
    for suggestion in suggestions:
        ratio = difflib.SequenceMatcher(None, name.lower(), suggestion.lower()).ratio()
        if ratio >= 0.75:
            return suggestion
    return None


def extract_credits(
    meta: VideoMetadata, config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
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
        self.start_fraction = self.config.get("credits-start-fraction", -1.0)
        self.end_fraction = self.config.get("credits-end-fraction", -1.0)
        if (
            self.start_fraction + self.end_fraction >= 1.0
            or self.start_fraction < 0
            or self.end_fraction < 0
        ):
            self.start_fraction = 1.0
            self.end_fraction = 0.0

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

        # Scale windows with episode length, capped at the hard limits.
        # This prevents over-scanning short episodes and under-scanning long ones.
        start_window = max(self.start_duration, duration * self.start_fraction)
        end_window = max(self.end_duration, duration * self.end_fraction)

        # Build ranges, ensuring the two windows never overlap.
        end_start = max(start_window, duration - end_window)
        ranges = [
            (0, start_window),
            (end_start, duration),
        ]
        # Deduplicate when the two ranges collapse into one (very short content)
        if end_start <= start_window:
            ranges = [(0, duration)]

        print(
            f"[Credits Extractor] Scanning video frames for credits in {len(ranges)} ranges:\n\t{ranges}"
        )

        total_scan_duration = sum(abs(end - start) for start, end in ranges)
        # use meta.cast_profile["ocr_cache"]
        cached = meta.cast_profile.get("ocr_cache", {})
        if cached and cached.get("scanned_duration", 0) >= total_scan_duration:
            print(
                f"[Credits Extractor] Using cached OCR text "
                f"(cached: {cached['scanned_duration']:.1f}s"
                f" >= requested: {total_scan_duration:.1f}s)"
            )
            raw_text = cached["raw_text"]
        else:
            print("[Credits Extractor] Running OCR on video frames...")
            raw_text = self._extract_text_from_frames(meta.path, ranges)
            if raw_text.strip():
                meta.cast_profile["ocr_cache"] = {
                    "scanned_duration": total_scan_duration,
                    "raw_text": raw_text,
                }
            print("[Credits Extractor] Running OCR on video frames... Done.")

        if not raw_text.strip():
            return CastProfile()

        filtered_text = self._filter_ocr_text(raw_text)
        if not filtered_text.strip():
            return CastProfile()

        cast_profile = self._refine_with_ai(filtered_text)
        for attr in ("real_actors", "crew_names", "fictional_characters"):
            setattr(
                cast_profile,
                attr,
                self._validate_names(getattr(cast_profile, attr)),
            )
        result = cast_profile.to_dict()
        # Preserve the ocr_cache so it survives the assignment back to
        # meta.cast_profile and is available on the next call.
        if "ocr_cache" in meta.cast_profile:
            result["ocr_cache"] = meta.cast_profile["ocr_cache"]
        return result

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

    # ------------------------------------------------------------------
    # Name validation
    # ------------------------------------------------------------------

    def _is_valid_name(self, name: str) -> bool:
        """Return True if the name looks like a real human name (no digits/symbols, 2+ words)."""
        stripped = name.strip()
        words = stripped.split()
        if len(words) < 2:
            return False
        if any(len(w) < 2 for w in words):
            return False
        return bool(_NAME_RE.match(stripped))

    def _validate_names(self, names: List[str]) -> List[str]:
        """Validate names, canonicalize, and deduplicate.

        Resolution order:
        1. TMDB person search (with tokenized fallback for OCR typos).
        2. Wikipedia opensearch (last resort).
        """
        tmdb_api_key = self.config.get("tmdb-api-key")

        canonical: List[str] = []
        for name in names:
            stripped = name.strip()
            if not self._is_valid_name(stripped):
                continue

            resolved = _lookup_name_online(stripped, tmdb_api_key)

            if resolved is None:
                print(f"[Credits Extractor] Discarding unverified: {stripped!r}")
                continue
            if stripped.lower() != resolved.lower():
                print(f"[Credits Extractor] Corrected: {stripped!r} → {resolved!r}")
            canonical.append(resolved)

        kept: List[str] = []
        for name in canonical:
            merged = False
            for i, existing in enumerate(kept):
                ratio = difflib.SequenceMatcher(
                    None, name.lower(), existing.lower()
                ).ratio()
                if ratio >= 0.85:
                    if sum(c.isalpha() for c in name) > sum(
                        c.isalpha() for c in existing
                    ):
                        kept[i] = name
                    merged = True
                    break
            if not merged:
                kept.append(name)
        return kept

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
