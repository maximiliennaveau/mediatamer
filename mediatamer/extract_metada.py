from typing import Dict

from mediatamer.signals.ai_video_matcher import match_episode
from mediatamer.signals.cache import load_metadata, save_metadata
from mediatamer.signals.credits_extractor import VideoCreditsExtractor
from mediatamer.signals.guessit import infer_context_from_path
from mediatamer.signals.opensubtitles import OpenSubtitleSignals
from mediatamer.signals.subtitle import SubtitleSignals
from mediatamer.signals.summary_from_subtitles import extract_summary_from_subtitles
from mediatamer.signals.technical import TechnicalSignals
from mediatamer.signals.video_metadata import VideoMetadata


def extract_all_metadata(
    metadata: VideoMetadata, config: Dict, no_cache: bool = False
) -> VideoMetadata:
    """Perform all extractions and populate the provided metadata object."""

    # Check if the cache contains the metadata
    if not no_cache:
        cached_meta = load_metadata(metadata.path)
        if cached_meta:
            metadata = cached_meta

    # 1. Technical
    if metadata.technical is None:
        print("Extracting technical metadata...")
        TechnicalSignals.from_metadata(metadata)
        save_metadata(metadata)

    # 2. GuessIt
    if metadata.guessit is None or not metadata.guessit:
        print("Extracting guessit metadata...")
        infer_context_from_path(metadata)
        save_metadata(metadata)

    # 2.5 OpenSubtitles
    if metadata.opensubtitles is None or not metadata.opensubtitles:
        print("Extracting opensubtitles metadata...")
        try:
            OpenSubtitleSignals(metadata, config).extract()
            save_metadata(metadata)
        except Exception as e:
            print(f"Failed to extract OpenSubtitles metadata: {e}")

    # 3. Subtitles
    if metadata.subtitles is None:
        print("Extracting subtitle metadata...")
        SubtitleSignals(metadata, config).extract()
        save_metadata(metadata)

    # 4 Credits
    if metadata.cast_profile is None or not metadata.cast_profile:
        print("Extracting credits metadata...")
        VideoCreditsExtractor(config).extract(metadata)
        save_metadata(metadata)

    # 5. Summary from subtitles
    if metadata.summary is None or not metadata.summary:
        print("Extracting summary from subtitles...")
        extract_summary_from_subtitles(metadata, config)
        save_metadata(metadata)

    # 6. AI Episode Matcher
    print("Extracting AI episode matcher metadata...")
    match_episode(metadata, config)

    # Dump the found metada
    print("Saving metadata...")
    save_metadata(metadata)

    return metadata
