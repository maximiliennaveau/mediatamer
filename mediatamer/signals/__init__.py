"""Signal extractors for mediatamer.

Each module implements one focused extractor returning a plain dict.
"""

from .guessit import extract_from_guessit
from .technical import get_technical_metadata
from .subtitle_hash import compute_file_hash, lookup_subtitle_hash

__all__ = [
    "extract_from_guessit",
    "get_technical_metadata",
    "compute_file_hash",
    "lookup_subtitle_hash",
]
