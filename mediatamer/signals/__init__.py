"""Signal extractors for mediatamer.

Each module implements one focused extractor returning a plain dict.
"""

from .filename import parse_filename
from .technical import get_technical_metadata
from .subtitle_hash import compute_file_hash, lookup_subtitle_hash

__all__ = [
    'parse_filename',
    'get_technical_metadata',
    'compute_file_hash',
    'lookup_subtitle_hash',
]
