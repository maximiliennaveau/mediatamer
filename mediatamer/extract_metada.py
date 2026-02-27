from pathlib import Path

from mediatamer.signals.technical import TechnicalSignals
from mediatamer.signals.video_metadata import VideoMetadata
from mediatamer.signals.guessit import infer_context_from_path
from mediatamer.signals.subtitle import extract_subtitle_text
from mediatamer.signals.ai_episode_matcher import AIEpisodeMatcher


def extract_all_metadata(path: Path) -> VideoMetadata:
    """Perform all extractions and populate the provided metadata object."""

    # Create metadata object
    metadata = VideoMetadata(path=path)

    # 1. Technical
    TechnicalSignals.from_metadata(metadata)

    # 2. GuessIt
    metadata.guessit = infer_context_from_path(metadata.path, metadata)

    # 3. Subtitles
    metadata.subtitles = extract_subtitle_text(metadata.path, metadata)

    # 4. AI Episode Matcher
    AIEpisodeMatcher.match(metadata)

    return metadata
