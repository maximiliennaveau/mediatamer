import requests
from typing import Optional, Dict, Any


class MetadataVerifier:
    def __init__(self, tmdb_key: str, tvdb_key: str):
        self.tmdb_key = tmdb_key
        self.tvdb_key = tvdb_key
        self.tmdb_base = "https://api.themoviedb.org/3"
        self._tvdb_token = None

    def _get_tvdb_headers(self):
        if not self._tvdb_token:
            # Note: Utilisez votre fonction de login TVDB v4 existante ici
            resp = requests.post(
                "https://api4.thetvdb.com/v4/login", json={"apikey": self.tvdb_key}
            )
            self._tvdb_token = resp.json().get("data", {}).get("token")
        return {"Authorization": f"Bearer {self._tvdb_token}"}

    def verify_against_providers(
        self, show_name: str, season: int, episode: int
    ) -> Optional[Dict[str, Any]]:
        """
        Valide l'existence d'un épisode et récupère le nom formaté par TVDB.
        """
        # 1. Validation rapide via TMDB
        search_resp = requests.get(
            f"{self.tmdb_base}/search/tv",
            params={"api_key": self.tmdb_key, "query": show_name},
        ).json()

        results = search_resp.get("results", [])
        if not results:
            return None

        tmdb_show_id = results[0]["id"]

        ep_resp = requests.get(
            f"{self.tmdb_base}/tv/{tmdb_show_id}/season/{season}/episode/{episode}",
            params={"api_key": self.tmdb_key},
        )

        if ep_resp.status_code != 200:
            return None

        # 2. Extraction des métadonnées TVDB
        output = self.get_tvdb_metadata(show_name, season, episode)
        if not output or "seriesId" not in output:
            return None

        # 3. Récupération du titre de la série tel que TVDB le gère
        url = f"https://api4.thetvdb.com/v4/series/{output['seriesId']}"
        resp = requests.get(url, headers=self._get_tvdb_headers()).json()
        series_data = resp.get("data", {})

        # TVDB fournit souvent "Doctor Who (2005)" ou "Doctor Who (1963)" dans .name
        # On le stocke tel quel pour le tagging MKV
        output["series_full_name"] = series_data.get("name")
        output["series_first_aired"] = series_data.get("firstAired")

        # On garde l'année seule au cas où tu en aurais besoin pour un autre champ (ex: DATE)
        if output["series_first_aired"]:
            output["series_year"] = output["series_first_aired"][:4]

        return output

    def get_tvdb_metadata(
        self, show_name: str, season: int, episode: int
    ) -> Optional[Dict[str, Any]]:
        """
        Récupère les métadonnées complètes de TVDB prêtes pour le tagging MKV.
        """
        headers = self._get_tvdb_headers()

        # Recherche de la série sur TVDB
        search = requests.get(
            "https://api4.thetvdb.com/v4/search",
            params={"query": show_name, "type": "series"},
            headers=headers,
        ).json()

        if not search.get("data"):
            return None
        tvdb_id = search["data"][0]["tvdb_id"]

        # Récupération de l'épisode étendu
        # On utilise l'ordre officiel ou DVD ici
        url = f"https://api4.thetvdb.com/v4/series/{tvdb_id}/episodes/official"
        params = {"season": season, "episodeNumber": episode}

        # Note: TVDB v4 nécessite souvent de paginer ou de filtrer.
        # Pour faire simple, on récupère l'épisode spécifique s'il existe.
        ep_data = requests.get(url, params=params, headers=headers).json()

        # On renvoie le premier match
        if ep_data.get("data", {}).get("episodes"):
            return ep_data["data"]["episodes"][0]

        return None
