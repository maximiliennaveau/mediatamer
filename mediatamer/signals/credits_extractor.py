import subprocess
import os
import tempfile
import json
import re
import math
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
from mediatamer.signals.cast_from_subtitles import _build_cast_prompt

# Valid human name: 2+ words, only letters (incl. accented), hyphens, apostrophes, periods
_NAME_RE = re.compile(
    r"^[A-Za-z\u00C0-\u024F][A-Za-z\u00C0-\u024F'\-.]*"
    r"(\s[A-Za-z\u00C0-\u024F][A-Za-z\u00C0-\u024F'\-.]*)+$"
)

# Keywords that introduce a CAST section (names that follow are actors).
# Bilingual: English and French (common on dubbed DVDs).
_CAST_HEADERS: frozenset = frozenset(
    [
        "cast",
        "avec",
        "avec les voix de",
        "starring",
        "featuring",
        "elenco",
        "reparto",
        "distribution des roles",
        "distribution des rôles",
        "with",
    ]
)

# Keywords that introduce a CREW section.
_CREW_HEADERS: frozenset = frozenset(
    [
        "directed by",
        "réalisé par",
        "réalisateur",
        "director",
        "produced by",
        "producteur",
        "productenrs exeutifs",
        "productenrs",
        "executive producer",
        "producteur exécutif",
        "written by",
        "écrit par",
        "scénario",
        "music by",
        "musique",
        "original music",
        "edited by",
        "montage",
        "montage des effets visuels",
        "director of photography",
        "directeur de la photographie",
        "cinematography",
        "chef opérateur",
        "costume design",
        "costumes",
        "supervision des costumes",
        "make-up",
        "maquillage",
        "supervision maquillage",
        "visual effects",
        "effets visuels",
        "stunt coordinator",
        "cascadeurs",
        "sound",
        "son",
        "mixage",
        "casting",
        "distribution",
        "set decorator",
        "décorateur",
        "art director",
        "chef décorateur",
        "production designer",
        "chef décorateur",
        "script supervisor",
        "scripte",
        "assistant director",
        "assistants realisation",
        "assistants réalisation",
        "production manager",
        "directeur de production",
        "régisseur",
        "régissear",
        "location manager",
        "régisseur des extérieurs",
        "régissear des extériears",
        "electrician",
        "chef electricien",
        "électriciens",
        "electriciens",
        "gaffer",
        "chef éclairagiste",
        "props",
        "accessoiriste",
        "chef accessoiriste",
        "wardrobe",
        "habilleuse",
        "habillage",
        "construction",
        "fabrication",
        "composer",
        "orchestre",
        "dubbing",
        "mixage doublage",
        "mixage doublage original",
        "post-production",
        "postproduction",
        "supervising producer",
        "producteur superviseur",
    ]
)

# Tokens that indicate a line is an organization/brand, never a person name.
_ORG_TOKENS: frozenset = frozenset(
    [
        "bbc",
        "inc",
        "ltd",
        "llc",
        "gmbh",
        "s.a.",
        "s.l.",
        "productions",
        "entertainment",
        "studios",
        "studio",
        "pictures",
        "films",
        "television",
        "tv",
        "foundation",
        "fund",
        "institute",
        "graphics",
        "fx",
        "dolby",
        "divx",
        "imax",
        "dts",
    ]
)


def _line_is_org(line: str) -> bool:
    """Return True if the line looks like an organization / brand, not a person."""
    tokens = {w.lower().rstrip(".,") for w in line.split()}
    return bool(tokens & _ORG_TOKENS)


def _extract_name_suffix(line: str) -> Optional[str]:
    """Try to extract a personal name from the *tail* of a credits line.

    Credits lines often look like::

        Chef Electricien Mark Keeling
        Cascadeurs Belinda McGinley
        DIRECTED BY Paul Wilmshurst

    This function strips leading role/keyword tokens until the remainder
    matches the name pattern, then returns the candidate name string.
    Returns ``None`` if no name-like suffix is found.
    """
    words = line.split()
    # Try progressively shorter suffixes (minimum 2 words for a name).
    for start in range(len(words) - 1):
        candidate = " ".join(words[start:])
        if _NAME_RE.match(candidate) and not _line_is_org(candidate):
            return candidate
    return None


# Session-level cache: avoids repeat network calls for the same name
_NAME_LOOKUP_CACHE: Dict[str, Optional[str]] = {}


def _lookup_name_online(
    name: str, tmdb_api_key: str, tvdb_api_key: Optional[str] = None
) -> Optional[str]:
    """Verify *name* against TMDB, then TVDB, then Wikipedia.

    Returns the canonical name string on success, None if the name cannot
    be confirmed as a real person.
    """
    if name in _NAME_LOOKUP_CACHE:
        return _NAME_LOOKUP_CACHE[name]

    result = _lookup_via_tmdb(name, tmdb_api_key)
    if result is None and tvdb_api_key:
        result = _lookup_via_tvdb(name, tvdb_api_key)
    if result is None:
        result = _lookup_via_wikipedia(name)

    _NAME_LOOKUP_CACHE[name] = result
    return result


def _lookup_via_tvdb(name: str, api_key: str) -> Optional[str]:
    """Look up a person name on TVDB using its /search?type=person endpoint.

    Returns the canonical name on a confident match (≥ 0.75 similarity),
    or None.
    """
    from mediatamer.signals.tvdb import search_person_tvdb

    hit = search_person_tvdb(name, api_key)
    if not hit:
        return None
    _, canonical = hit
    ratio = difflib.SequenceMatcher(None, name.lower(), canonical.lower()).ratio()
    if ratio < 0.75:
        return None
    return canonical


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

    found_via_token_fallback = False
    if not candidates:
        # Fallback: search each word individually, aggregate results.
        # We track this because token-fallback matches require a stricter
        # similarity threshold (the query is weaker evidence).
        tokens = name.split()
        for token in tokens:
            if len(token) < 3:
                continue
            for result in _tmdb_search_person(token, api_key):
                candidates.setdefault(result["id"], result)
        if candidates:
            found_via_token_fallback = True

    if not candidates:
        # print(f"TMDB lookup error for {name!r}")
        return None

    # Pick the candidate whose name is closest to the OCR-extracted string.
    # The similarity is ALWAYS measured against the full original *name*,
    # even when the candidate was surfaced via a single-token fallback query.
    # This prevents token queries like 'Andrew' (from 'Andrew Gaine') from
    # accepting 'Andrew Garfield' just because 'Andrew' matches well.
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

    # Require a higher threshold when evidence came only from a token search,
    # since the match is inherently less reliable.
    threshold = 0.85 if found_via_token_fallback else 0.75
    if best_ratio < threshold:
        # print(
        #     f"TMDB lookup for {name!r} returned {best_name!r} "
        #     f"with low similarity ({best_ratio:.2f}, threshold {threshold:.2f}), rejecting."
        # )
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
        self.fps = self.config.get("credits-scan-fps", 0.5)  # 1 frame every 2 seconds
        self.start_fraction = self.config.get("credits-start-fraction", 0.02)
        self.end_fraction = self.config.get("credits-end-fraction", 0.15)
        if (
            self.start_fraction + self.end_fraction >= 1.0
            or self.start_fraction < 0
            or self.end_fraction < 0
        ):
            self.start_fraction = 1.0
            self.end_fraction = 0.0

    def extract(self, meta: VideoMetadata) -> dict:
        """
        Extracts credits from video frames and returns a CastProfile.
        """
        if not pytesseract or not shutil.which("tesseract"):
            print("[Credits Extractor] Tesseract not found. Skipping.")
            return {}

        if not meta.technical or not meta.technical["duration"]:
            print("[Credits Extractor] Video duration unknown. Skipping.")
            return {}

        result = {}
        duration = meta.technical["duration"]

        # Scale windows with episode length, capped at the hard limits.
        # This prevents over-scanning short episodes and under-scanning long ones.
        start_window = duration * self.start_fraction
        end_window = duration * self.end_fraction

        # Build ranges, ensuring the two windows never overlap.
        end_start = max(start_window, duration - end_window)
        end_duration = duration - end_start
        ranges = [
            (0, start_window),
            (end_start, end_duration),
        ]
        # Deduplicate when the two ranges collapse into one (very short content)
        if end_start <= start_window:
            ranges = [(0, duration)]

        print(
            f"[Credits Extractor] Scanning video frames for credits in {len(ranges)} ranges:\n\t{ranges}"
        )

        total_scan_duration = sum(abs(end - start) for start, end in ranges)
        # use meta.cast_profile["ocr_cache"]
        result["ocr_cache"] = meta.cast_profile.get("ocr_cache", {})
        is_cache_loaded = not bool(result["ocr_cache"])
        is_fps_higher_than_cached = self.fps > result["ocr_cache"].get("scanned_fps", 0)
        is_duration_ask_greater_than_cached = total_scan_duration - 0.1 >= result[
            "ocr_cache"
        ].get("scanned_duration", 0)
        print(
            f"[Credits Extractor] Cache status: {'miss' if is_cache_loaded else 'hit'}, "
            f"asked duration: {total_scan_duration:.1f}s, "
            f"cached duration: {result['ocr_cache'].get('scanned_duration', 0):.1f}s, "
            f"asked FPS: {self.fps}, "
            f"cached FPS: {result['ocr_cache'].get('scanned_fps', 0)}, "
            f"Running OCR: {'yes' if is_cache_loaded or is_duration_ask_greater_than_cached or is_fps_higher_than_cached else 'no'}"
        )
        if (
            is_cache_loaded
            or is_duration_ask_greater_than_cached
            or is_fps_higher_than_cached
        ):
            print("[Credits Extractor] Running OCR on video frames...")
            raw_text = self._extract_text_from_frames(meta.path, ranges)
            if not raw_text.strip():
                print(
                    "[Credits Extractor] No text extracted from frames. Skipping AI refinement."
                )
                return {}
            filtered_text = self._filter_ocr_text(raw_text)
            if not filtered_text.strip():
                print(
                    "[Credits Extractor] No text remaining after filtering. Skipping AI refinement."
                )
                return {}
            result["ocr_cache"] = {
                "scanned_duration": total_scan_duration,
                "raw_text": raw_text,
                "filtered_text": filtered_text,
                "scanned_fps": self.fps,
            }
            print("[Credits Extractor] Running OCR on video frames... Done.")
        else:
            print(
                f"[Credits Extractor] Using cached OCR data. Scanned duration: {result['ocr_cache'].get('scanned_duration', 0)}"
            )

        filtered_text = result["ocr_cache"]["filtered_text"]

        # Step A: heuristic extraction (always runs — fast, no API calls).
        print("[Credits Extractor] Extracting names with heuristics...")
        heuristic_result = self._extract_with_heuristics(filtered_text)
        heur_names: List[str] = heuristic_result.get("credits_names", [])
        compact_text = heuristic_result.get("_compact_text", "")
        print(f"[Credits Extractor] Heuristics found {len(heur_names)} candidate(s).")

        # Step B: AI refinement — feed compact heuristic text when available,
        # otherwise fall back to the full filtered OCR text.
        print("[Credits Extractor] Refining with AI...")
        ai_input = compact_text.strip() if compact_text.strip() else filtered_text
        cast_profile = self._refine_with_ai(ai_input)
        ai_names: List[str] = cast_profile.get("credits_names", [])
        print(f"[Credits Extractor] AI found {len(ai_names)} candidate(s).")

        # Step C: union — merge both lists, preserving order (heuristics first),
        # deduplicating case-insensitively so neither source loses unique finds.
        seen: set = set()
        merged: List[str] = []
        for name in heur_names + ai_names:
            key = name.lower()
            if key not in seen:
                seen.add(key)
                merged.append(name)
        print(
            f"[Credits Extractor] Union: {len(heur_names)} heuristic"
            f" + {len(ai_names)} AI → {len(merged)} unique candidate(s)."
        )

        # Validate and canonicalize names, with online lookup and session caching.
        print("[Credits Extractor] Validating and canonicalizing names...")
        result["credits_names"] = self._validate_names(merged)
        # Fictional characters are story names — not validated against TMDB.
        result["fictional_characters"] = cast_profile.get("fictional_characters", [])
        print("[Credits Extractor] Validating and canonicalizing names... Done.")
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
                # - scale to 1920px wide: sharper glyphs at higher resolution
                # - format=gray: grayscale for OCR
                # - unsharp: sharpen before thresholding so thin strokes survive
                # - lutyuv: hard binary threshold (white-on-dark credits → invert)
                # - negate: flip to black-on-white for Tesseract
                filter_chain = (
                    f"fps={self.fps},scale=1920:-1,format=gray,"
                    f"unsharp=5:5:1.5:5:5:0.0,"
                    f"lutyuv=y='if(gt(val,140),255,0)',negate"
                )

                out_pattern = os.path.join(tmpdir, f"range_{i}_%04d.png")
                expected_count = int(math.ceil(self.fps * dur)) if self.fps > 0 else 0
                print(
                    f"[Credits Extractor] Extracting ~{expected_count} image(s) for range {i} into {out_pattern}"
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
                    out_pattern,
                ]

                try:
                    subprocess.run(cmd, check=True, timeout=60 * 5)
                except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                    print(f"[Credits Extractor] FFmpeg error/timeout in range {i}: {e}")
                    continue

            # Process extracted images
            images = sorted([f for f in os.listdir(tmpdir) if f.endswith(".png")])
            if images:
                print(
                    f"[Credits Extractor] Extracted {len(images)} image(s) to {tmpdir}"
                )
            else:
                print(f"[Credits Extractor] No images extracted to {tmpdir}")

            for img_name in images:
                try:
                    img_path = os.path.join(tmpdir, img_name)
                    # PSM 3 = fully automatic page segmentation (default): Tesseract
                    # detects multiple isolated text regions on the page, which is
                    # correct for credits frames where names are scattered on a dark
                    # background.  PSM 6 (single block) and PSM 11 (sparse words) both
                    # perform worse here — PSM 6 misses most isolated names, PSM 11
                    # fragments them into single words.
                    # OEM 1 = LSTM neural-net engine only (more accurate than legacy).
                    tess_config = "--oem 1 --psm 3"
                    text = pytesseract.image_to_string(
                        Image.open(img_path), config=tess_config
                    )
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
        tvdb_api_key = self.config.get("tvdb-api-key")

        canonical: List[str] = []
        for name in names:
            stripped = name.strip()
            if not self._is_valid_name(stripped):
                continue

            resolved = _lookup_name_online(stripped, tmdb_api_key, tvdb_api_key)

            if resolved is None:
                # print(f"[Credits Extractor] Discarding unverified: {stripped!r}")
                continue
            if stripped.lower() != resolved.lower():
                # print(f"[Credits Extractor] Corrected: {stripped!r} → {resolved!r}")
                pass
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

    def _extract_with_heuristics(self, filtered_text: str) -> dict:
        """Deterministic name extractor — no LLM required.

        Extracts all real person name candidates from OCR text into a flat
        ``credits_names`` list without any actor/crew classification.
        Also returns ``_compact_text`` for LLM pre-filtering.
        """
        # Pre-process: normalise lines and drop obvious noise.
        clean_lines: List[str] = []
        for raw_line in filtered_text.splitlines():
            line = raw_line.strip()
            if not line or len(line) < 4:
                continue
            line = re.sub(r"\s+", " ", line).rstrip(".,;:-")
            alpha = sum(c.isalpha() for c in line)
            if alpha < len(line) * 0.5 or alpha < 3:
                continue
            if _line_is_org(line):
                continue
            clean_lines.append(line)

        # (role_hint, name) pairs
        entries: List[Tuple[str, str]] = []
        for line in clean_lines:
            normalized = line.title() if line.isupper() else line
            if _NAME_RE.match(normalized) and not _line_is_org(normalized):
                entries.append(("", normalized))
            else:
                raw_candidate = _extract_name_suffix(line)
                if raw_candidate:
                    candidate = (
                        raw_candidate.title()
                        if raw_candidate.isupper()
                        else raw_candidate
                    )
                    prefix = line[: line.rfind(raw_candidate)].strip().rstrip(":-")
                    entries.append((prefix.title() if prefix else "", candidate))

        # Deduplicate by name (case-insensitive), preserve first occurrence.
        seen: set = set()
        names: List[str] = []
        compact_lines: List[str] = []
        for hint, name in entries:
            key = name.lower()
            if key not in seen:
                seen.add(key)
                names.append(name)
                compact_lines.append(f"{hint}: {name}" if hint else name)

        compact_text = "\n".join(compact_lines)
        print(
            f"[Credits Extractor] Heuristics: {len(names)} candidate(s) before TMDB validation."
        )
        return {
            "credits_names": names,
            "fictional_characters": [],
            "_compact_text": compact_text,
        }

    def _refine_with_ai(self, raw_text: str) -> dict:
        """
        Use the LLM to clean up the noisy OCR text into a structured profile.
        """
        # Limit input to avoid token overflow
        snip = raw_text[:8000] if len(raw_text) > 8000 else raw_text
        prompt = _build_cast_prompt(snip)
        response = run_ai(prompt, self.config, json_mode=True)
        try:
            data = json.loads(response)
            return data
        except Exception as e:
            print(f"[Credits Extractor] AI parsing error: {e}")
            return {}
