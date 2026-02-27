"""Signal extractors for mediatamer.

Each module implements one focused extractor returning a plain dict.
"""

from .guessit import infer_context_from_path
from .technical import get_technical_metadata
from .subtitle import compute_file_hash, lookup_subtitle_hash

__all__ = [
    "infer_context_from_path",
    "get_technical_metadata",
    "compute_file_hash",
    "lookup_subtitle_hash",
]
