from typing import Dict

from mediatamer.signals.ai_video_matcher import match_episode
from mediatamer.signals.cache import load_metadata, save_metadata
from mediatamer.signals.credits_extractor import extract_credits
from mediatamer.signals.guessit import infer_context_from_path
from mediatamer.signals.opensubtitles import OpenSubtitleSignals
from mediatamer.signals.subtitle import SubtitleSignals
from mediatamer.signals.summary_from_subtitles import extract_summary_from_subtitles
from mediatamer.signals.search_ovdb import search_ovdb
from mediatamer.signals.technical import extract_technical
from mediatamer.signals.video_metadata import VideoMetadata
from mediatamer.signals.metadata_verifier import MetadataVerifier


def extract_all_metadata(
    metadata: VideoMetadata, config: Dict, no_cache: bool = False
) -> VideoMetadata:
    """Perform all extractions and populate the provided metadata object."""
    if not no_cache:
        # Load cache and check if some cache entries should be ignored.
        ignore_cache_entries = config.get("ignore-cache-entries", [])
        metadata = load_metadata(metadata.path, config)
        if ignore_cache_entries:
            print(f"Ignoring cache for entries: {ignore_cache_entries}")
            for entry in ignore_cache_entries:
                assert hasattr(metadata, entry), (
                    f"Invalid cache entry to ignore: {entry}"
                )
                setattr(metadata, entry, {})  # Clear the ignored cache entry
    else:
        print("No-cache mode enabled, skipping cache loading.")

    # Print the correctly loaded metadata.
    print(f"Initial metadata for {metadata.path.name}:")
    print(f"  Technical: {'Yes' if metadata.technical else 'No'}")
    print(f"  GuessIt: {'Yes' if metadata.guessit else 'No'}")
    print(f"  Subtitles: {'Yes' if metadata.subtitles else 'No'}")
    print(f"  AI Match: {'Yes' if metadata.ai_match else 'No'}")
    print(f"  OpenSubtitles: {'Yes' if metadata.opensubtitles else 'No'}")
    print(f"  Cast Profile: {'Yes' if metadata.cast_profile else 'No'}")
    print(f"  Summary: {'Yes' if metadata.summary else 'No'}")
    print(f"  OVDB: {'Yes' if metadata.ovdb else 'No'}")
    print(f"  Final Result: {'Yes' if metadata.final_result else 'No'}")

    # Verifier
    metadata_verifier = MetadataVerifier(config["tmdb-api-key"], config["tvdb-api-key"])

    # Verify if we have the final result in cache and if it's valid.
    if metadata.final_result:
        print("Found final result in cache, verifying...")
        result = metadata_verifier.verify_against_providers(
            metadata.final_result["series_full_name"],
            metadata.final_result["seasonNumber"],
            metadata.final_result["number"],
        )
        if result:
            print("Cached final result is valid.")
            metadata.final_result = (
                result  # Update with any corrected info from providers
            )
            save_metadata(metadata, config)
            print("Using cached final result as final result.")
            return metadata
        else:
            print("Cached final result is invalid. Ignoring cached final result.")
            metadata.final_result = {}  # Clear invalid cached final result
    else:
        redo_ovdb_and_ai = True

    # Technical data
    if not metadata.technical:
        print("Extracting technical data...")
        extract_technical(metadata)
        save_metadata(metadata, config)
        print("Extracting technical data... Done")

    # GuessIt
    if not metadata.guessit:
        print("Extracting guessit metadata...")
        infer_context_from_path(metadata, config)
        save_metadata(metadata, config)
        print("Extracting guessit metadata... Done")

    # Verify guessit against TMDB and TVDB.
    print("Verifying guessit metadata...")
    g_data = metadata.guessit["guessit"]
    if g_data["season"] is not None and g_data["episode"] is not None:
        result = metadata_verifier.verify_against_providers(
            g_data["show"], g_data["season"], g_data["episode"]
        )
        if result:
            metadata.final_result = result
            save_metadata(metadata, config)
            print("Guessit metadata is valid. Using guessit result as final result.")
            return metadata
    print("Verifying guessit metadata... Done")

    # OpenSubtitles
    if not metadata.opensubtitles:
        print("Extracting opensubtitles metadata...")
        try:
            os_result = OpenSubtitleSignals(metadata, config).extract()
            save_metadata(metadata, config)
            if os_result:
                print(
                    "OpenSubtitles metadata is valid. Using OpenSubtitles result as final result."
                )
                return metadata
        except Exception as e:
            print(f"Failed to extract OpenSubtitles metadata: {e}")
        print("Extracting OpenSubtitles metadata... Done")

    # Credits
    print("Extracting credits metadata...")
    extract_credits(metadata, config)
    save_metadata(metadata, config)
    print("Extracting cast profile... Done")

    # Search OVDB with the credits informations
    if not metadata.ovdb or redo_ovdb_and_ai:
        print("Extracting OVDB metadata...")
        search_ovdb(metadata, config)
        save_metadata(metadata, config)
        print("Extracting OVDB metadata... Done")

    if metadata.ovdb and metadata.ovdb.get("best_episode"):
        best_ep = metadata.ovdb["best_episode"]
        result = metadata_verifier.verify_against_providers(
            best_ep["show_name"],
            best_ep["season"],
            best_ep["episode"],
        )
        if result:
            metadata.final_result = result
            save_metadata(metadata, config)
            print("OVDB best episode is valid. Using OVDB result as final result.")
            return metadata

    print("Fail to identify the video from guessit and credits.")

    # Subtitles
    if not metadata.subtitles:
        print("Extracting subtitle metadata...")
        SubtitleSignals(metadata, config).extract()
        save_metadata(metadata, config)
        print("Extracting subtitle metadata... Done")

    # Summary from subtitles
    if not metadata.summary:
        print("Extracting summary from subtitles...")
        extract_summary_from_subtitles(metadata, config)
        save_metadata(metadata, config)
        print("Extracting summary from subtitles... Done")

    # AI Episode Matcher
    if not metadata.ai_match or "error" in metadata.ai_match or redo_ovdb_and_ai:
        print("Extracting AI episode matcher metadata...")
        match_episode(metadata, config)
        print("Extracting AI episode matcher metadata... Done")

    # Verify AI episode matcher results if available.
    ai_result = metadata.ai_match and metadata.ai_match.get("best_match")
    if ai_result:
        result = metadata_verifier.verify_against_providers(
            ai_result["show_name"],
            ai_result["season"],
            ai_result["episode"],
        )
        if result:
            metadata.final_result = result
            save_metadata(metadata, config)
            print(
                "AI episode matcher result is valid. Using AI episode matcher result as final result."
            )
            return metadata

    metadata.final_result = {}
    print("Failed to extract valid metadata from all sources. Final result is empty.")
    return metadata
