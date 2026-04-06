import hashlib
import json
from pathlib import Path
from typing import Optional

from mediatamer.signals.video_metadata import (
    VideoMetadata,
    metadata_from_dict,
    metadata_to_dict,
)

CACHE_DIR = Path.home() / ".cache" / "mediatamer" / "metadata"


def _get_cache_path(video_path: Path, config: dict = None) -> Path:
    """Generate a stable cache path based on the file's absolute path."""
    if config is None:
        cache_dir = CACHE_DIR
    else:
        cache_dir = Path(config.get("cache-dir", CACHE_DIR))

    file_id = hashlib.sha256(str(video_path.resolve()).encode()).hexdigest()
    return cache_dir / f"{file_id}.json"


def load_metadata(video_path: Path, config: dict = None) -> Optional[VideoMetadata]:
    """Load cached metadata for a video file if it exists."""
    cache_path = _get_cache_path(video_path, config)
    if cache_path.exists():
        try:
            print(f"Loading cache for {video_path.name} from {cache_path}")
            with cache_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
                return metadata_from_dict(data)
        except Exception as e:
            print(f"Error loading cache for {video_path.name}: {e}")
    else:
        print(f"Cache file not found for {video_path.name}.")
    return None


def save_metadata(metadata: VideoMetadata, config: dict = None):
    """Save metadata to the centralized cache."""
    cache_path = _get_cache_path(metadata.path, config)
    cache_dir = cache_path.parent
    if not cache_dir.exists():
        cache_dir.mkdir(parents=True)
        print(f"Created cache directory: {cache_dir}")
    try:
        data = metadata_to_dict(metadata)
        print(f"Saving cache for {metadata.path.name} to {cache_path}")
        with cache_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving cache for {metadata.path.name}: {e}")
