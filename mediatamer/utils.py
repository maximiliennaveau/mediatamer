"""MediaTamer utility functions."""

import re
from langdetect import detect


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
