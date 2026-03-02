import json
from pathlib import Path
from typing import Optional

from mediatamer.signals.video_metadata import (
    VideoMetadata,
    metadata_from_dict,
    metadata_to_dict,
)
from mediatamer.extract_metada import extract_all_metadata

CACHE_DIR = Path.home() / ".cache" / "mediatamer" / "metadata"


def _get_cache_path(video_path: Path) -> Path:
    """Generate a stable cache path based on the file's absolute path."""
    import hashlib

    file_id = hashlib.sha256(str(video_path.resolve()).encode()).hexdigest()
    return CACHE_DIR / f"{file_id}.json"


def load_metadata(video_path: Path) -> Optional[VideoMetadata]:
    """Load cached metadata for a video file if it exists."""
    cache_path = _get_cache_path(video_path)
    if cache_path.exists():
        try:
            with cache_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
                return metadata_from_dict(data)
        except Exception as e:
            print(f"Error loading cache for {video_path.name}: {e}")
    return None


def save_metadata(metadata: VideoMetadata):
    """Save metadata to the centralized cache."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = _get_cache_path(metadata.path)
    try:
        data = metadata_to_dict(metadata)
        with cache_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving cache for {metadata.path.name}: {e}")


def get_or_create_metadata(
    video_path: Path, scan_root: Optional[Path] = None
) -> VideoMetadata:
    """Retrieve metadata from cache, or extract and cache it if missing."""
    meta = load_metadata(video_path)
    if meta:
        return meta

    meta = VideoMetadata(path=video_path)
    extract_all_metadata(meta, scan_root)
    save_metadata(meta)
    return meta
