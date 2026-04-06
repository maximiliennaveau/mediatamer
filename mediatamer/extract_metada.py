from typing import Dict

from mediatamer.signals.cache import load_metadata, save_metadata
from mediatamer.signals.technical import TechnicalSignals
from mediatamer.signals.video_metadata import VideoMetadata
from mediatamer.signals.guessit import infer_context_from_path
from mediatamer.signals.subtitle import SubtitleSignals
from mediatamer.signals.opensubtitles import OpenSubtitleSignals
from mediatamer.signals.ai_video_matcher import match_episode


def extract_all_metadata(
    metadata: VideoMetadata, config: Dict, no_cache: bool = False
) -> VideoMetadata:
    """Perform all extractions and populate the provided metadata object."""

    # Check if the cache contains the metadata
    meta = None
    if not no_cache:
        meta = load_metadata(metadata.path)
        metadata = meta

    # 1. Technical
    if meta is None:
        print("Extracting technical metadata...")
        TechnicalSignals.from_metadata(metadata)

    # 2. GuessIt
    if meta is None:
        print("Extracting guessit metadata...")
        infer_context_from_path(metadata)

    # 2.5 OpenSubtitles
    if meta is None:
        print("Extracting opensubtitles metadata...")
        try:
            OpenSubtitleSignals(metadata, config).extract()
        except Exception as e:
            print(f"Failed to extract OpenSubtitles metadata: {e}")

    # 3. Subtitles
    if meta is None:
        print("Extracting subtitle metadata...")
        SubtitleSignals(metadata, config).extract()

    # 4. AI Episode Matcher
    print("Extracting AI episode matcher metadata...")
    match_episode(metadata)

    # Dump the found metada
    print("Saving metadata...")
    save_metadata(metadata)

    return metadata
