from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field

from mediatamer.signals.ffprobe import extract_metadata_ffprobe
from mediatamer.signals.mkvmerge import extract_metadata_mkvmerge
from mediatamer.signals.mediainfo import extract_metadata_mediainfo


@dataclass
class TechnicalSignals:
    path: Path
    ffprobe: Dict[str, Any] = field(default_factory=dict)
    mkvmerge: Dict[str, Any] = field(default_factory=dict)
    mediainfo: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_path(cls, path: Path):
        """Factory to create signals."""
        signals = cls(path=path)
        signals.ffprobe = extract_metadata_ffprobe(path)
        signals.mkvmerge = extract_metadata_mkvmerge(path)
        signals.mediainfo = extract_metadata_mediainfo(path)
        return signals

    def to_legacy_dict(self) -> Dict[str, Any]:
        """Convert to the dictionary format expected by legacy code."""
        return {
            "duration": self.duration,
            "chapters": self.chapters,
            "has_chapters": self.has_chapters,
            "embedded_title": self.embedded_title,
            "ffprobe": self.ffprobe,
            "mkvmerge": self.mkvmerge,
            "mediainfo": self.mediainfo,
        }

    @property
    def duration(self) -> float:
        """Normalized duration in seconds."""
        fmt = self.ffprobe.get("format", {})
        if fmt.get("duration"):
            return float(fmt["duration"])
        return (
            float(
                self.mkvmerge.get("container", {})
                .get("properties", {})
                .get("duration", 0)
            )
            / 1_000_000_000
        )

    @property
    def duration_minutes(self) -> float:
        return self.duration / 60.0

    @property
    def chapters(self) -> List[Dict[str, Any]]:
        return self.mkvmerge.get("chapters", [])

    @property
    def has_chapters(self) -> bool:
        return len(self.chapters) > 0

    @property
    def is_multi_episode(self) -> bool:
        """Heuristic: Long duration + many chapters + many tracks often means multi-episode."""
        # Rule: > 60 min and has chapters
        if self.duration_minutes > 60 and self.has_chapters:
            return True
        return False

    @property
    def estimated_episode_count(self) -> int:
        """Estimate number of episodes in this file."""
        if not self.is_multi_episode:
            return 1
        # Typical 30 min episodes in a 90 min movie-style rip
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

        # If multi-episode, scan around chapters
        if self.is_multi_episode:
            # Heuristic: chapters at 1/3, 2/3 of duration are likely episode boundaries
            # Let's scan 90s before and after each chapter boundary for safety
            for chap in self.chapters:
                start_ms = float(
                    chap.get("num_entries", 0)
                )  # wait, mkvmerge -J chapter format?
                # Need to check mkvmerge -J chapter format.
                # Usually it is 'start_time' in nanoseconds.
                start_ns = chap.get("start")
                if start_ns:
                    start_sec = float(start_ns) / 1_000_000_000
                    if (
                        300 < start_sec < (duration - 300)
                    ):  # Avoid start/end already covered
                        ranges.append((max(0.0, start_sec - 90.0), 180.0))

        return ranges

    @property
    def embedded_title(self) -> Optional[str]:
        return self.ffprobe.get("format", {}).get("tags", {}).get("title")

    @property
    def encoding_date(self) -> Optional[str]:
        if not self.mediainfo:
            self.mediainfo = extract_metadata_mediainfo(self.path)
        for track in self.mediainfo.get("media", {}).get("track", []):
            if track.get("@type") == "General":
                return track.get("Encoded_Date")
        return None


def get_technical_metadata(path: Path) -> Dict[str, Any]:
    """Return technical metadata extracted with multiple tools (unified)."""
    signals = TechnicalSignals.from_path(path)
    return signals.to_legacy_dict()
