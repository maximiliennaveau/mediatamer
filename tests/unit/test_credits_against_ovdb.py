import unittest
from pathlib import Path

from mediatamer.config import load_config
from mediatamer.signals.cache import load_metadata

import requests
from collections import Counter

BASE_URL = "https://api.themoviedb.org/3"


def extract_precise_metadata(ocr_actors: list, config: dict) -> dict:
    """Extract show/season/episode information using cast profile and duration."""
    tmdb_api_key = config.get("tmdb-api-key")

    # 1. Sélectionner 2-3 acteurs "forts" (Guest stars > Main actors)
    # Jenna Coleman est dans 40 épisodes, Clare Higgins (Ohila) dans seulement 3.
    # Les acteurs uniques permettent de trouver l'épisode immédiatement.
    sample_actors = [a for a in ocr_actors if len(a) > 5][:4]

    potential_matches = []

    for actor in sample_actors:
        # Trouver l'ID de l'acteur
        search = requests.get(
            f"{BASE_URL}/search/person",
            params={"api_key": tmdb_api_key, "query": actor},
        ).json()
        if not search.get("results"):
            continue
        person_id = search["results"][0]["id"]

        # Récupérer TOUS les crédits (Films + TV)
        credits = requests.get(
            f"{BASE_URL}/person/{person_id}/combined_credits",
            params={"api_key": tmdb_api_key},
        ).json()

        print(f"Credits for {actor}: {credits}")

        for entry in credits.get("cast", []):
            if entry.get("media_type") == "tv":
                # On capture les infos critiques pour discriminer
                potential_matches.append(
                    {
                        "id": entry.get("id"),
                        "name": entry.get("name"),  # Nom de la série
                        "first_air_date": entry.get(
                            "first_air_date", ""
                        ),  # Ex: 1963-11-23 vs 2005-03-26
                        "character": entry.get("character", ""),
                        "episode_count": entry.get("episode_count", 0),
                    }
                )

    # 2. Discriminer la série (Vote majoritaire)
    # On groupe par ID de série pour éviter les confusions de noms
    series_counts = Counter([m["id"] for m in potential_matches])
    if not series_counts:
        return None

    best_series_id = series_counts.most_common(1)[0][0]
    series_info = next(m for m in potential_matches if m["id"] == best_series_id)

    # 3. Récupérer l'épisode spécifique
    # Pour avoir le SXXEXX, on interroge les crédits détaillés de l'acteur pour CETTE série
    # TMDB permet de voir les épisodes spécifiques via l'ID de crédit
    return {
        "show_name": series_info["name"],
        "series_start_date": series_info["first_air_date"][
            :4
        ],  # Discriminateur 1963 vs 2005
        "probable_character": series_info["character"],
        "tmdb_id": best_series_id,
        "is_classic": int(series_info["first_air_date"][:4]) < 2000,
    }


def extract_precise_metadata_2(
    ocr_actors: list, config: dict, path_hint: str = "S9"
) -> dict:
    tmdb_api_key = config.get("tmdb-api-key")

    # 1. Identifier la série d'abord (Doctor Who)
    # On fait une recherche simple sur le nom de la série
    search_series = requests.get(
        f"{BASE_URL}/search/tv",
        params={"api_key": tmdb_api_key, "query": "Doctor Who"},
    ).json()

    # On récupère les deux versions principales pour comparer
    # Doctor Who (2005) ID: 121
    # Doctor Who (1963) ID: 57243
    results = search_series.get("results", [])

    # 2. Extraire le numéro de saison depuis le chemin (S9 -> 9)
    import re

    season_match = re.search(r"[sS](\d+)", path_hint)
    target_season = int(season_match.group(1)) if season_match else 1

    best_match = None
    highest_score = 0

    for show in results[
        :3
    ]:  # On teste les 3 meilleurs résultats (souvent 1963 et 2005)
        show_id = show["id"]

        # 3. Charger les crédits de la saison complète
        # Cet endpoint contient TOUS les acteurs (Main + Guest) de TOUS les épisodes de la saison
        season_url = f"{BASE_URL}/tv/{show_id}/season/{target_season}"
        season_data = requests.get(
            season_url,
            params={"api_key": tmdb_api_key, "append_to_response": "credits"},
        ).json()

        if "episodes" not in season_data:
            continue

        # 4. Comparer l'OCR avec chaque épisode de cette saison
        for episode in season_data["episodes"]:
            # On fusionne le cast principal de l'épisode et les guest stars
            ep_cast = [c["name"].upper() for c in episode.get("guest_stars", [])]
            # On ajoute le cast principal de la saison
            ep_cast += [
                c["name"].upper()
                for c in season_data.get("credits", {}).get("cast", [])
            ]

            # Calcul du score d'intersection
            matches = set([a.upper() for a in ocr_actors]).intersection(set(ep_cast))
            score = len(matches)

            if score > highest_score:
                highest_score = score
                best_match = {
                    "show_name": show["name"],
                    "series_start_date": show["first_air_date"][:4],
                    "episode_number": episode["episode_number"],
                    "episode_title": episode["name"],
                    "tmdb_id": show_id,
                    "is_classic": int(show["first_air_date"][:4]) < 2000,
                    "confidence": score,
                }

    return best_match


class TestCreditsAgainstOVDB(unittest.TestCase):
    def test_credits_against_tvdb(self):
        # Episode search:
        path = Path("/data/videos/unsorted-compressed-tv/Doctor_Who_S9_DVD1/B2_t01.mkv")
        self.assertTrue(path.exists(), "Test video file should exist for OVDB search")
        config = load_config()
        metadata = load_metadata(path, config)
        self.assertIsNotNone(metadata, "Metadata should not be None")

        extracted = extract_precise_metadata(
            metadata.cast_profile["real_actors"], config
        )
        print(f"Extracted: {extracted}")


if __name__ == "__main__":
    unittest.main()
