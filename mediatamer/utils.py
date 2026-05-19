"""MediaTamer utility functions."""

from collections import defaultdict
from pathlib import Path
from langdetect import detect
import re
from typing import Dict, Any

from mediatamer.parameters import get_extensions


def sanitize_filename(name: str) -> str:
    """Sanitize string for use in filenames."""
    if not name:
        return ""
    # Replace invalid chars with space or dash
    name = re.sub(r'[<>:"/\\|?*]', "-", name)
    # Collapse multiple spaces/dashes
    name = re.sub(r"[- ]+", " ", name).strip()
    return name


def zero_pad(n) -> str:
    """Zero pad a number to 2 digits."""
    try:
        if n is None:
            return "00"
        return f"{int(n):02d}"
    except (ValueError, TypeError):
        return "00"


def normalize_show_name(raw: str) -> str:
    """Normalize show names by cleaning up common patterns."""
    if not raw:
        return "Unknown Show"
    s = raw.replace("_", " ").replace(".", " ").strip()
    s = re.sub(r"\b[Ss]\d{1,2}\b", "", s)
    s = re.sub(r"\bDVD[_ -]?\d+\b", "", s, flags=re.I)
    s = re.sub(r"\bD[_ -]?\d+\b", "", s, flags=re.I)
    s = re.sub(r"\bDisc[_ -]?\d+\b", "", s, flags=re.I)
    s = re.sub(r"\s+", " ", s).strip()
    # Handle common abbreviations
    if s.lower() == "dr who":
        s = "Doctor Who"
    return s.title() if s else "Unknown Show"


def detect_language(text: str) -> str:
    """Detect the language of a text string using langdetect.

    Returns an ISO 639-1 language code (e.g. 'fr', 'en') or 'en'.
    """
    if not text or len(text.strip()) < 50:
        return "en"
    return detect(text)


def extract_files_to_process(input_dir: Path, config: Dict[str, Any]):
    if input_dir.is_file():
        assert input_dir.suffix.lower() in get_extensions()
        return [input_dir]
    exts = {e if e.startswith(".") else f".{e}" for e in get_extensions()}
    files = sorted(
        [p for p in input_dir.rglob("*") if p.suffix.lower() in exts and p.is_file()]
    )
    if not files:
        print("No files found in", input_dir)
        return None

    # Per-folder bonus filtering: within each folder, skip files whose size
    # is below (threshold * max_file_size_in_folder).  This reliably removes
    # small bonus/extra clips without touching genuine episode files.
    threshold = config.get("bonus-size-threshold", 0.4)
    by_folder: Dict[Path, list] = defaultdict(list)
    for f in files:
        by_folder[f.parent].append(f)

    filtered = []
    total_skipped = 0
    for folder, folder_files in by_folder.items():
        max_size = max(f.stat().st_size for f in folder_files)
        limit = max_size * float(threshold)
        kept = [f for f in folder_files if f.stat().st_size >= limit]
        skipped = len(folder_files) - len(kept)
        if skipped:
            print(
                f"[Bonus filter] Skipped {skipped} file(s) in {folder} "
                f"(below {threshold * 100:.0f}% of largest file)"
            )
        filtered.extend(kept)
        total_skipped += skipped

    files = sorted(filtered)

    print(f"Found {len(files)} files to process (skipped {total_skipped} bonus/extra):")
    for file in files:
        print(f"\t- {file}")

    return files
