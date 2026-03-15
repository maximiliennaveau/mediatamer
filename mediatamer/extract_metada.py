from typing import Dict

from mediatamer.signals.cache import load_metadata, save_metadata
from mediatamer.signals.technical import TechnicalSignals
from mediatamer.signals.video_metadata import VideoMetadata
from mediatamer.signals.guessit import infer_context_from_path
from mediatamer.signals.subtitle import SubtitleSignals
from mediatamer.ai_episode_matcher import match_episode


def extract_all_metadata(
    metadata: VideoMetadata, config: Dict, no_cache: bool = False
) -> VideoMetadata:
    """Perform all extractions and populate the provided metadata object."""

    # Check if the cache contains the metadata
    if not no_cache:
        meta = load_metadata(metadata.path)
        if meta:
            return meta

    # 1. Technical
    TechnicalSignals.from_metadata(metadata)

    # 2. GuessIt
    infer_context_from_path(metadata)

    # 3. Subtitles
    SubtitleSignals(metadata, config).extract()

    # 4. AI Episode Matcher
    match_episode(metadata)

    # Dump the found metada
    save_metadata(metadata)

    return metadata
