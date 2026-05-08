import requests
import re
from difflib import SequenceMatcher
from pathlib import Path


from mediatamer.config import load_config
from mediatamer.signals.cache import load_metadata, save_metadata
from mediatamer.signals.credits_extractor import extract_credits
from mediatamer.signals.technical import extract_technical


class MetadataMatcher:
    def __init__(self, tmdb_api_key):
        print(f"Using API KEY: {tmdb_api_key}")
        self.api_key = tmdb_api_key
        self.base_url = "https://api.themoviedb.org/3"

    def _fuzzy_ratio(self, s1, s2):
        """Calcule la similitude entre deux chaînes pour gérer l'OCR sale."""
        return SequenceMatcher(None, s1.upper(), s2.upper()).ratio()

    def get_season_from_path(self, path):
        """Extrait le numéro de saison depuis le nom du dossier ou du fichier."""
        match = re.search(r"[sS]eason_?(\d+)|[sS](\d+)", str(path))
        if match:
            return int(match.group(1) or match.group(2))
        return None

    def clean_string(self, text):
        # Enlève tout ce qui n'est pas lettre ou espace et normalise
        return re.sub(r"[^a-zA-Z\s]", "", text).strip().upper()

    def find_best_episode(self, ocr_actors, path):
        season_hint = self.get_season_from_path(path)

        # DEBUG: On vérifie si la clé API fonctionne sur un endpoint simple
        # print(f"Using API KEY: {self.api_key[:4]}****")
        params = {
            "api_key": self.api_key,
            "query": "Doctor Who",
            "include_adult": "false",
            "language": "en-US",
        }

        resp = requests.get(f"{self.base_url}/search/tv", params=params)

        # DEBUG: Affiche l'URL finale pour la tester dans ton navigateur
        # print(f"DEBUG URL: {resp.url}")

        if not resp.ok:
            print(f"Erreur API TMDB: {resp.status_code} - {resp.text}")
            return None

        search_tv = resp.json()
        results = search_tv.get("results", [])
        print(f"Search TV {results}")
        if not results:
            return None

        best_overall_match = None
        # Nettoyage préventif des noms OCR
        clean_ocr_list = [self.clean_string(a) for a in ocr_actors if len(a) > 5]

        for show in results[:2]:
            show_id = show["id"]
            seasons_to_check = [0]
            if season_hint is not None:
                seasons_to_check.append(season_hint)

            for s_num in seasons_to_check:
                season_data = requests.get(
                    f"{self.base_url}/tv/{show_id}/season/{s_num}",
                    params={"api_key": self.api_key, "append_to_response": "credits"},
                ).json()

                if "episodes" not in season_data:
                    continue

                # Cast principal de la saison (indices faibles)
                main_cast = [
                    self.clean_string(c["name"])
                    for c in season_data.get("credits", {}).get("cast", [])
                ]

                for ep in season_data["episodes"]:
                    # Guest stars et Crew (indices forts)
                    guest_cast = [
                        self.clean_string(c["name"]) for c in ep.get("guest_stars", [])
                    ]
                    crew = [self.clean_string(c["name"]) for c in ep.get("crew", [])]

                    current_ep_score = 0
                    matches = []

                    for ocr_name in clean_ocr_list:
                        # 1. On check les Guest Stars (Priorité Max)
                        for g in guest_cast:
                            if self._fuzzy_ratio(ocr_name, g) > 0.85:
                                current_ep_score += 5
                                matches.append(g)
                                break

                        # 2. On check le Crew
                        for c in crew:
                            if self._fuzzy_ratio(ocr_name, c) > 0.85:
                                current_ep_score += 3
                                matches.append(c)
                                break

                        # 3. On check le Main Cast (Poids faible)
                        for m in main_cast:
                            if self._fuzzy_ratio(ocr_name, m) > 0.85:
                                current_ep_score += 1
                                matches.append(m)
                                break

                    if (
                        not best_overall_match
                        or current_ep_score > best_overall_match["score"]
                    ):
                        best_overall_match = {
                            "show_name": show["name"],
                            "series_air_date": show.get("first_air_date", ""),
                            "season": s_num,
                            "episode": ep["episode_number"],
                            "title": ep["name"],
                            "score": current_ep_score,
                            "matched_names": list(set(matches)),
                        }

        return best_overall_match


def process_video(file_path, ocr_cast, config):
    matcher = MetadataMatcher(config.get("tmdb-api-key"))

    print(f"Analyse de : {file_path}")
    result = matcher.find_best_episode(ocr_cast, file_path)

    if result and result["score"] > 1.5:  # On valide si on a au moins 2 matches solides
        print("--- MATCH TROUVÉ ---")
        print(f"Série    : {result['show_name']} ({result['series_air_date'][:4]})")
        print(
            f"Épisode  : S{result['season']:02d}E{result['episode']:02d} - {result['title']}"
        )
        print(f"Confiance: {result['score']:.2f}")
        print(f"Acteurs confirmés: {', '.join(result['matched_names'])}")
    else:
        print("Aucun match concluant trouvé.")


if __name__ == "__main__":
    path = Path("/data/videos/unsorted-compressed-tv/Doctor_Who_S9_DVD1/B1_t00.mkv")
    config = load_config()
    metadata = load_metadata(path, config)

    # print("Extracting credits metadata...")
    # extract_technical(metadata)
    # extract_credits(metadata, config)
    # save_metadata(metadata, config)

    print(f"Path : {metadata.path}")
    print(f"Cast Profile : {metadata.cast_profile.get('real_actors')}")

    process_video(metadata.path, metadata.cast_profile.get("real_actors"), config)
