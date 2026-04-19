from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import subprocess

from mediatamer.signals.video_metadata import VideoMetadata


def extract_technical(metadata: VideoMetadata) -> dict:
    """Extract technical metadata using ffprobe."""
    from mediatamer.signals.technical import TechnicalSignals

    metadata.technical = TechnicalSignals.from_metadata(metadata).to_dict()
    return metadata.technical


@dataclass
class TechnicalSignals:
    ffprobe: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_metadata(cls, metadata: VideoMetadata) -> "TechnicalSignals":
        """Factory to create signals using the unified metadata context."""
        signals = cls()
        signals.ffprobe = cls._extract_metadata_ffprobe(metadata.path)
        metadata.technical = signals
        return signals

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Serialize raw source data for caching. Properties are recomputed on load."""
        return {
            "ffprobe": self.ffprobe,
            "duration": self.duration,
            "chapters": self.chapters,
            "is_multi_episode": self.is_multi_episode,
            "estimated_episode_count": self.estimated_episode_count,
            "suggested_ocr_ranges": self.suggested_ocr_ranges,
            "embedded_title": self.embedded_title,
            "encoding_date": self.encoding_date,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TechnicalSignals":
        """Reconstruct from a cached dictionary."""
        return cls(
            ffprobe=data.get("ffprobe", {}),
        )

    # ------------------------------------------------------------------
    # Computed properties
    # ------------------------------------------------------------------

    @property
    def duration(self) -> float:
        """Normalized duration in seconds."""
        raw = self.ffprobe.get("format", {}).get("duration")
        if raw:
            return float(raw)
        return 0.0

    @property
    def duration_minutes(self) -> float:
        return self.duration / 60.0

    @property
    def chapters(self) -> List[Dict[str, Any]]:
        """Chapter list from ffprobe. Each chapter has 'start_time' as a float string (seconds)."""
        return self.ffprobe.get("chapters", [])

    @property
    def has_chapters(self) -> bool:
        return len(self.chapters) > 0

    @property
    def is_multi_episode(self) -> bool:
        """Heuristic: long duration + many chapters often means multi-episode."""
        if self.duration_minutes > 60 and self.has_chapters:
            return True
        return False

    @property
    def estimated_episode_count(self) -> int:
        """Estimate number of episodes in this file."""
        if not self.is_multi_episode:
            return 1
        if self.duration_minutes > 150:
            return 6
        if self.duration_minutes > 100:
            return 4
        if self.duration_minutes > 70:
            return 3
        if self.duration_minutes > 40:
            return 2
        return 1

    @property
    def suggested_ocr_ranges(self) -> List[Tuple[float, float]]:
        """Identify potential credit segments (start/end of episodes)."""
        duration = self.duration
        ranges = []

        # Always scan the very beginning and very end
        ranges.append((0.0, 180.0))
        ranges.append((max(0.0, duration - 180.0), 180.0))

        # If multi-episode, scan around chapter boundaries
        if self.is_multi_episode:
            for chap in self.chapters:
                # ffprobe chapters use 'start_time' in seconds (as a float string)
                start_time = chap.get("start_time")
                if start_time is not None:
                    start_sec = float(start_time)
                    if 300 < start_sec < (duration - 300):
                        ranges.append((max(0.0, start_sec - 90.0), 180.0))

        return ranges

    @property
    def embedded_title(self) -> Optional[str]:
        return self.ffprobe.get("format", {}).get("tags", {}).get("title")

    @property
    def encoding_date(self) -> Optional[str]:
        """Creation/encoding date from ffprobe format tags (ISO 8601)."""
        tags = self.ffprobe.get("format", {}).get("tags", {})
        # ffprobe stores it as 'creation_time'; some containers use 'date'
        return tags.get("creation_time") or tags.get("date")

    # ------------------------------------------------------------------
    # Extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_metadata_ffprobe(path: Path) -> Dict[str, Any]:
        """
        Extract metadata from a video file using ffprobe.

        Returns a dictionary with format, streams, and chapters.
        """
        if not path.exists():
            return {"error": f"File not found: {path}"}

        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            "-show_chapters",
            str(path),
        ]

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return json.loads(res.stdout)
        except subprocess.CalledProcessError as e:
            return {"error": "ffprobe failed", "stderr": e.stderr}
        except Exception as e:
            return {"error": str(e)}
