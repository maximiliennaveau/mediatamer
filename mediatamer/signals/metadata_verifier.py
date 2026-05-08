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
            # Note: Use your existing TVDB v4 login function here
            resp = requests.post(
                "https://api4.thetvdb.com/v4/login", json={"apikey": self.tvdb_key}
            )
            self._tvdb_token = resp.json().get("data", {}).get("token")
        return {"Authorization": f"Bearer {self._tvdb_token}"}

    def verify_against_providers(
        self, show_name: str, season: int, episode: int
    ) -> Optional[Dict[str, Any]]:
        """
        Validate the existence of an episode and retrieve the TVDB-formatted name.
        """
        # 1. Quick validation via TMDB
        search_resp = requests.get(
            f"{self.tmdb_base}/search/tv",
            params={"api_key": self.tmdb_key, "query": show_name},
        ).json()

        results = search_resp.get("results", [])
        if not results:
            print(f"MetadataVerifier: No TMDB results for '{show_name}'")
            return None

        tmdb_show_id = results[0]["id"]

        ep_resp = requests.get(
            f"{self.tmdb_base}/tv/{tmdb_show_id}/season/{season}/episode/{episode}",
            params={"api_key": self.tmdb_key},
        )

        if ep_resp.status_code != 200:
            print(
                f"MetadataVerifier: No TMDB episode found for '{show_name}' S{season:02d}E{episode:02d}"
            )
            return None

        # 2. Extraction of TVDB metadata
        output = self.get_tvdb_metadata(show_name, season, episode)
        if not output or "seriesId" not in output:
            print(
                f"MetadataVerifier: No TVDB metadata found for '{show_name}' S{season:02d}E{episode:02d}"
            )
            return None

        # 3. Retrieval of the series title as managed by TVDB
        url = f"https://api4.thetvdb.com/v4/series/{output['seriesId']}"
        resp = requests.get(url, headers=self._get_tvdb_headers()).json()
        series_data = resp.get("data", {})

        # TVDB often provides "Doctor Who (2005)" or "Doctor Who (1963)" in .name
        # We store it as is for MKV tagging
        output["series_full_name"] = series_data.get("name")
        output["series_first_aired"] = series_data.get("firstAired")

        # Keep the year alone in case you need it for another field (e.g., DATE)
        if output["series_first_aired"]:
            output["series_year"] = output["series_first_aired"][:4]

        return output

    def get_tvdb_metadata(
        self, show_name: str, season: int, episode: int
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve the full TVDB metadata ready for MKV tagging.
        """
        headers = self._get_tvdb_headers()

        # Search for the series on TVDB
        search = requests.get(
            "https://api4.thetvdb.com/v4/search",
            params={"query": show_name, "type": "series"},
            headers=headers,
        ).json()

        if not search.get("data"):
            return None
        tvdb_id = search["data"][0]["tvdb_id"]

        # Retrieval of the extended episode
        # We use the official or DVD order here
        url = f"https://api4.thetvdb.com/v4/series/{tvdb_id}/episodes/official"
        params = {"season": season, "episodeNumber": episode}

        # Note: TVDB v4 often requires pagination or filtering.
        # For simplicity, we retrieve the specific episode if it exists.
        ep_data = requests.get(url, params=params, headers=headers).json()

        # Return the first match
        if ep_data.get("data", {}).get("episodes"):
            return ep_data["data"]["episodes"][0]

        return None
