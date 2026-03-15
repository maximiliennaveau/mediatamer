from typing import Optional, Dict, List, Tuple, Any, TYPE_CHECKING
import os
from pathlib import Path
import subprocess
import re
from datetime import timedelta

if TYPE_CHECKING:
    from mediatamer.signals.video_metadata import VideoMetadata


class SRTParser:
    """Helper to parse and filter SRT content."""

    def __init__(self, srt_content: str):
        self.srt_content = srt_content
        self.entries = self._parse(srt_content)

    def _parse_time(self, time_str: str) -> float:
        """Parse SRT time format (00:00:20,000) to seconds."""
        try:
            h, m, s_ms = time_str.split(":")
            s, ms = s_ms.split(",")
            return timedelta(
                hours=int(h),
                minutes=int(m),
                seconds=int(s),
                milliseconds=int(ms),
            ).total_seconds()
        except (ValueError, IndexError):
            return 0.0

    def _parse(self, content: str) -> List[Dict]:
        entries = []
        # Basic SRT regex: index, time range, and text block
        pattern = re.compile(
            r"(\d+)\s*\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\s*\n(.*?)(?=\n\d+\s*\n\d{2}:\d{2}:\d{2},\d{3} -->|\Z)",
            re.DOTALL,
        )
        matches = list(pattern.finditer(content))
        if not matches and content.strip():
            # Fallback for plain text (no SRT structure)
            return [{"index": 0, "start": 0.0, "end": 99999.0, "text": content.strip()}]

        for match in matches:
            idx, start, end, text = match.groups()
            entries.append(
                {
                    "index": int(idx),
                    "start": self._parse_time(start),
                    "end": self._parse_time(end),
                    "text": text.strip(),
                }
            )
        return entries

    def get_range_text(
        self, start_time: Optional[float] = None, end_time: Optional[float] = None
    ) -> str:
        """Filter text by time range."""
        filtered = self.entries
        if start_time is not None:
            filtered = [e for e in filtered if e["end"] >= start_time]
        if end_time is not None:
            filtered = [e for e in filtered if e["start"] <= end_time]

        return "\n".join(e["text"] for e in filtered)


class SubtitleSignals:
    """Refactored subtitle extraction using existing VideoMetadata."""

    def __init__(
        self, metadata: "VideoMetadata", config: Optional[Dict[str, Any]] = None
    ):
        self.metadata = metadata
        self.config = config or {}
        self.path = metadata.path

    def extract(self) -> "VideoMetadata":
        """
        Extract subtitles for the entire video and populate the metadata object.
        Outputs the VideoMetadata object filled with extracted subtitles.
        """
        if self.metadata.subtitles:
            return self.metadata

        # 1. Try text-based subtitle streams (SRT/ASS/etc).
        out = self._extract_text_sub_streams()
        if out:
            self.metadata.subtitles = out
            return self.metadata

        # 2. Perform OCR for the entire video.
        res = self._ocr_subtitle_ranges([(0.0, self.metadata.technical.duration)])
        if res:
            self.metadata.subtitles = res

        return self.metadata

    def _get_ffprobe_data(self) -> Dict[str, Any]:
        """Retrieve ffprobe data from VideoMetadata without re-running tools."""
        if self.metadata.technical and self.metadata.technical.ffprobe:
            return self.metadata.technical.ffprobe

        # Fallback to manual extraction ONLY if the metadata is missing technical signals
        # This shouldn't happen based on the requirement that technical metadata is already present.
        from mediatamer.signals.technical import TechnicalSignals

        return TechnicalSignals._extract_metadata_ffprobe(self.path)

    def _find_subtitle_stream(self, pgs_only: bool = False) -> Optional[Dict]:
        """Find a suitable subtitle stream index using existing metadata."""
        j = self._get_ffprobe_data()
        streams = j.get("streams", [])

        candidates = []
        for s in streams:
            if s.get("codec_type") != "subtitle":
                continue
            codec = (s.get("codec_name") or "").lower()
            is_pgs = codec in ("hdmv_pgs_subtitle", "pgs", "dvd_subtitle")
            if pgs_only and not is_pgs:
                continue
            candidates.append(s)

        if not candidates:
            return None

        if not pgs_only:
            # Sort to prefer non-PGS (higher priority)
            candidates.sort(
                key=lambda s: s.get("codec_name", "").lower()
                in ("hdmv_pgs_subtitle", "pgs", "dvd_subtitle")
            )

        return candidates[0]

    def _extract_text_sub_streams(self) -> Optional[str]:
        """Try to extract a text-based subtitle stream (SRT/ASS/etc) as SRT string."""
        j = self._get_ffprobe_data()
        for s in j.get("streams", []):
            if s.get("codec_type") != "subtitle":
                continue
            codec = (s.get("codec_name") or "").lower()
            if codec in ("hdmv_pgs_subtitle", "pgs", "dvd_subtitle"):
                continue

            idx = s.get("index")
            try:
                cmd = [
                    "ffmpeg",
                    "-loglevel",
                    "error",
                    "-i",
                    str(self.path),
                    "-map",
                    f"0:{idx}",
                    "-c:s",
                    "srt",
                    "-f",
                    "srt",
                    "-",
                ]
                res = subprocess.run(cmd, capture_output=True, text=True, check=True)
                if res.stdout.strip():
                    return res.stdout.strip()
            except Exception:
                continue
        return None

    def _ocr_subtitle_ranges(self, ranges: List[Tuple[float, float]]) -> Optional[str]:
        """Internal OCR engine for specific ranges."""
        import shutil

        if not shutil.which("tesseract"):
            return None
        try:
            import pytesseract
            from PIL import Image
        except ImportError:
            return None

        import tempfile

        stream = self._find_subtitle_stream(pgs_only=True)
        if not stream:
            return None

        idx = stream.get("index")
        codec = stream.get("codec_name", "")
        # DVD subtitles are often 720x576, PGS are usually 1920x1080
        width = stream.get("width") or (720 if codec == "dvd_subtitle" else 1920)
        height = stream.get("height") or (576 if codec == "dvd_subtitle" else 1080)

        text_content = []
        with tempfile.TemporaryDirectory() as tmpdir:
            for i, (start, dur) in enumerate(ranges):
                cmd = [
                    "ffmpeg",
                    "-loglevel",
                    "error",
                    "-ss",
                    str(start),
                    "-i",
                    str(self.path),
                    "-f",
                    "lavfi",
                    "-i",
                    f"color=size={width}x{height}:rate=24:color=black",
                    "-filter_complex",
                    f"[1:v][0:{idx}]overlay,fps=0.2",
                    "-t",
                    str(dur),
                    "-f",
                    "image2",
                    f"{tmpdir}/range_{i}_%03d.png",
                ]
                try:
                    subprocess.run(cmd, check=True, timeout=90)
                except Exception:
                    continue

            images = sorted([f for f in os.listdir(tmpdir) if f.endswith(".png")])
            for img_name in images:
                try:
                    text = pytesseract.image_to_string(
                        Image.open(os.path.join(tmpdir, img_name))
                    )
                    if text.strip():
                        text_content.append(text.strip())
                except Exception:
                    continue

        return "\n".join(text_content)


__all__ = [
    "SubtitleSignals",
    "SRTParser",
]
