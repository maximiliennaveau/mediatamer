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
        metadata = load_metadata(metadata.path)
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

    # Verifier
    metadata_verifier = MetadataVerifier(config["tmdb-api-key"], config["tvdb-api-key"])

    # Technical data
    if not metadata.technical:
        print("Extracting technical data...")
        extract_technical(metadata)
        save_metadata(metadata)
        print("Extracting technical data... Done")

    # GuessIt
    if not metadata.guessit:
        print("Extracting guessit metadata...")
        infer_context_from_path(metadata, config)
        save_metadata(metadata)
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
            save_metadata(metadata)
            return metadata
    print("Verifying guessit metadata... Done")

    # OpenSubtitles
    if not metadata.opensubtitles:
        print("Extracting opensubtitles metadata...")
        try:
            os_result = OpenSubtitleSignals(metadata, config).extract()
            save_metadata(metadata)
            if os_result:
                return metadata
        except Exception as e:
            print(f"Failed to extract OpenSubtitles metadata: {e}")
        print("Extracting OpenSubtitles metadata... Done")

    # Credits
    print("Extracting cast profile...")
    if not metadata.cast_profile:
        print("Extracting credits metadata...")
        extract_credits(metadata, config)
        save_metadata(metadata)
    print("Extracting cast profile... Done")

    # Search OVDB with the credits informations
    if not metadata.ovdb:
        print("Extracting OVDB metadata...")
        search_ovdb(metadata, config)
        save_metadata(metadata)
        print("Extracting OVDB metadata... Done")

    if (
        metadata.ovdb
        and metadata.ovdb["ordered_candidates"]
        and metadata.ovdb["ordered_candidates"][0]["score"] > 10.0
    ):
        result = metadata_verifier.verify_against_providers(
            metadata.ovdb["show_name"],
            metadata.ovdb["season"],
            metadata.ovdb["episode"],
        )
        if result:
            metadata.final_result = result
            save_metadata(metadata)
            return metadata

    print("Fail to identify the video from guessit and credits.")
    metadata.final_result = {}
    return metadata

    # # Subtitles
    # if not metadata.subtitles:
    #     print("Extracting subtitle metadata...")
    #     SubtitleSignals(metadata, config).extract()
    #     save_metadata(metadata)

    # # Summary from subtitles
    # if not metadata.summary:
    #     print("Extracting summary from subtitles...")
    #     extract_summary_from_subtitles(metadata, config)
    #     save_metadata(metadata)

    # # Inspect TVDB and TMDB from credits and actors and summaries.
    # # if not metadata.ovdb:
    # #     print("Extracting OVDB metadata...")
    # #     extract_ovdb_info(metadata, config)
    # #     save_metadata(metadata)

    # # AI Episode Matcher
    # if not metadata.ai_match or "error" in metadata.ai_match:
    #     print("Extracting AI episode matcher metadata...")
    #     match_episode(metadata, config)
    # else:
    #     print("AI episode matcher metadata already cached, skipping.")

    # # Dump the found metadata for debugging.
    # print("Saving metadata...")
    # save_metadata(metadata)

    return metadata


def verify_metadata(metadata: VideoMetadata, config: dict) -> VideoMetadata:
    """Verify metadata against TVDB and TMDB for consistency."""

    # --- ÉTAPE 1 : GUESSIT ---
    g = metadata.guessit["guessit"]
    if g["show"] != "unknown" and g["season"] and g["episode"]:
        result = verifier.verify_against_providers(g["show"], g["season"], g["episode"])
        if result:
            return result  # HIT !

    # --- ÉTAPE 2 : CASTING SEARCH (Votre algo précédent) ---
    print("Guessit failed or invalid episode. Trying Casting Search...")
    match = matcher.find_best_episode(
        metadata.cast_profile["real_actors"], metadata.path
    )
    if match and match["score"] > 2.0:
        return verifier.get_tvdb_metadata(
            match["show_name"], match["season"], match["episode"]
        )

    # --- ÉTAPE 3 : SUMMARY / SUBTITLES ---
    # Si le casting échoue, on prend le résumé OCR et on cherche sur le web.
    print("Casting search failed. Trying Semantic Search...")
    summary = metadata.summary.get("summary")
    if summary:
        # Ici, vous pouvez utiliser l'API "Google Custom Search" ou
        # plus simplement envoyer le résumé à un LLM (via API) pour demander :
        # "Quel épisode de Doctor Who correspond à ce résumé ?"
        pass

    return None
