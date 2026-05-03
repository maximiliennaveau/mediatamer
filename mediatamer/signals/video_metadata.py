from pathlib import Path
from typing import Dict, Any
from dataclasses import dataclass, field


@dataclass
class VideoMetadata:
    """
    Unified metadata for a video file, aggregating all signals.
    Pure data class for serialization.
    """

    path: Path
    technical: Dict[str, Any] = field(default_factory=dict)
    guessit: Dict[str, Any] = field(default_factory=dict)
    subtitles: Dict[str, Any] = field(default_factory=dict)
    ai_match: Dict[str, Any] = field(default_factory=dict)
    opensubtitles: Dict[str, Any] = field(default_factory=dict)
    cast_profile: Dict[str, Any] = field(default_factory=dict)
    ovdb: Dict[str, Any] = field(default_factory=dict)
    summary: Dict[str, Any] = field(default_factory=dict)
    final_result: Dict[str, Any] = field(default_factory=dict)


def metadata_to_dict(metadata: VideoMetadata) -> Dict[str, Any]:
    """Convert VideoMetadata to a serializable dictionary."""
    return {
        "path": str(metadata.path),
        "technical": metadata.technical,
        "guessit": metadata.guessit,
        "subtitles": metadata.subtitles,
        "ai_match": metadata.ai_match,
        "opensubtitles": metadata.opensubtitles,
        "cast_profile": metadata.cast_profile,
        "ovdb": metadata.ovdb,
        "summary": metadata.summary,
        "final_result": metadata.final_result,
    }


def metadata_from_dict(data: Dict[str, Any]) -> VideoMetadata:
    """Reconstruct VideoMetadata from a dictionary."""
    path = Path(data["path"])
    return VideoMetadata(
        path=path,
        guessit=data.get("guessit", {}),
        subtitles=data.get("subtitles", {}),
        ai_match=data.get("ai_match", {}),
        opensubtitles=data.get("opensubtitles", {}),
        cast_profile=data.get("cast_profile", {}),
        technical=data.get("technical", {}),
        ovdb=data.get("ovdb", {}),
        summary=data.get("summary", {}),
        final_result=data.get("final_result", {}),
    )
