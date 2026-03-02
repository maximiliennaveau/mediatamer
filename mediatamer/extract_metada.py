from pathlib import Path
from typing import Optional

from mediatamer.signals.technical import TechnicalSignals
from mediatamer.signals.video_metadata import VideoMetadata
from mediatamer.signals.guessit import infer_context_from_path
from mediatamer.signals.subtitle import extract_subtitle_text
from mediatamer.signals.ai_episode_matcher import AIEpisodeMatcher


def extract_all_metadata(
    metadata: VideoMetadata, root_path: Optional[Path] = None
) -> VideoMetadata:
    """Perform all extractions and populate the provided metadata object."""

    # 1. Technical
    TechnicalSignals.from_metadata(metadata)

    # 2. GuessIt
    metadata.guessit = infer_context_from_path(metadata.path, metadata, root_path)

    # 3. Subtitles
    metadata.subtitles = extract_subtitle_text(metadata.path, metadata)

    # 4. AI Episode Matcher
    from mediatamer.signals.ai_episode_matcher import match_episode

    match_episode(metadata, {})

    return metadata
