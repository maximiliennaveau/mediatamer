from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, field

from mediatamer.signals.technical import TechnicalSignals


@dataclass
class VideoMetadata:
    """
    Unified metadata for a video file, aggregating all signals.
    Pure data class for serialization.
    """

    path: Path
    technical: Optional[TechnicalSignals] = None
    guessit: Dict[str, Any] = field(default_factory=dict)
    subtitles: Optional[str] = None
    ai_match: Dict[str, Any] = field(default_factory=dict)


def metadata_to_dict(metadata: VideoMetadata) -> Dict[str, Any]:
    """Convert VideoMetadata to a serializable dictionary."""
    return {
        "path": str(metadata.path),
        "technical": metadata.technical.to_legacy_dict() if metadata.technical else {},
        "guessit": metadata.guessit,
        "subtitles": metadata.subtitles,
        "ai_match": metadata.ai_match,
    }


def metadata_from_dict(data: Dict[str, Any]) -> VideoMetadata:
    """Reconstruct VideoMetadata from a dictionary."""
    path = Path(data["path"])
    guessit = data.get("guessit", {})
    subtitles = data.get("subtitles")
    ai_match = data.get("ai_match", {})

    # Note: technical is currently re-mapped to dict on save.
    # If we need full reconstructed objects, we'd need TechnicalSignals.from_dict
    return VideoMetadata(
        path=path, guessit=guessit, subtitles=subtitles, ai_match=ai_match
    )
