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
    heuristics: Dict[str, Any] = field(default_factory=dict)
    ai_guess: Dict[str, Any] = field(default_factory=dict)
    subtitles: Optional[str] = None
    ai_match: Dict[str, Any] = field(default_factory=dict)
    opensubtitles: Dict[str, Any] = field(default_factory=dict)


def metadata_to_dict(metadata: VideoMetadata) -> Dict[str, Any]:
    """Convert VideoMetadata to a serializable dictionary."""
    return {
        "path": str(metadata.path),
        "technical": metadata.technical.to_dict() if metadata.technical else {},
        "guessit": metadata.guessit,
        "heuristics": metadata.heuristics,
        "ai_guess": metadata.ai_guess,
        "subtitles": metadata.subtitles,
        "ai_match": metadata.ai_match,
        "opensubtitles": metadata.opensubtitles,
    }


def metadata_from_dict(data: Dict[str, Any]) -> VideoMetadata:
    """Reconstruct VideoMetadata from a dictionary."""
    path = Path(data["path"])
    guessit = data.get("guessit", {})
    heuristics = data.get("heuristics", {})
    ai_guess = data.get("ai_guess", {})
    subtitles = data.get("subtitles")
    ai_match = data.get("ai_match", {})
    opensubtitles = data.get("opensubtitles", {})
    technical = data.get("technical", {})

    return VideoMetadata(
        path=path,
        guessit=guessit,
        heuristics=heuristics,
        ai_guess=ai_guess,
        subtitles=subtitles,
        ai_match=ai_match,
        opensubtitles=opensubtitles,
        technical=TechnicalSignals.from_dict(technical) if technical else None,
    )
