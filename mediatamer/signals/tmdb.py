import requests
from typing import List, Dict, Any, Optional


def lang_to_tmdb_locale(lang_code: Optional[str]) -> str:
    """Map an ISO 639-1 code to a TMDB locale string."""
    mapping = {
        "fr": "fr-FR",
        "de": "de-DE",
        "es": "es-ES",
        "it": "it-IT",
        "pt": "pt-PT",
        "nl": "nl-NL",
        "ja": "ja-JP",
        "zh": "zh-CN",
        "ko": "ko-KR",
    }
    return mapping.get(lang_code or "", "en-US")


def fetch_tmdb_episodes(
    show_name: str, season_number: int, api_key: str, locale: str = "en-US"
) -> tuple[str, List[Dict[str, Any]]]:
    """
    Fetch episodes and detailed credits from TMDB for a given show and season.

    Returns:
        A tuple of (normalized_show_name, list_of_episodes).
    """
    episodes_result = []
    final_show_name = show_name

    try:
        # 1. Search for Show ID
        search_query = show_name
        is_extras = " - Extras" in search_query
        if is_extras:
            search_query = search_query.replace(" - Extras", "")

        search_url = "https://api.themoviedb.org/3/search/tv"
        params = {"api_key": api_key, "query": search_query, "language": "en-US"}
        resp = requests.get(search_url, params=params, timeout=10)
        if not resp.ok:
            return final_show_name, []

        results = resp.json().get("results", [])

        # Collect all candidates with matching name (handles classic vs revival duplicates)
        candidate_shows = [
            s for s in results if s["name"].lower() == search_query.lower()
        ]

        if not candidate_shows and is_extras:
            candidate_shows = [s for s in results if "extra" in s["name"].lower()]

        if not candidate_shows and results:
            candidate_shows = [results[0]]

        if not candidate_shows:
            return final_show_name, []

        first_name = candidate_shows[0]["name"]
        final_show_name = (
            f"{first_name} - Extras"
            if (is_extras and "extra" not in first_name.lower())
            else first_name
        )

        # 2. Get Season Episodes from every candidate show
        def fetch_season(s_num, _show_id, _show_label):
            s_url = f"https://api.themoviedb.org/3/tv/{_show_id}/season/{s_num}"
            r = requests.get(s_url, params={"api_key": api_key, "language": locale})
            if r.ok:
                eps = r.json().get("episodes", [])
                for ep in eps:
                    ep["_show_name"] = _show_label
                    ep_num = ep.get("episode_number")
                    if ep_num:
                        # Fetch credits (crew & cast)
                        c_url = f"https://api.themoviedb.org/3/tv/{_show_id}/season/{s_num}/episode/{ep_num}/credits"
                        cr = requests.get(c_url, params={"api_key": api_key})
                        if cr.ok:
                            cr_data = cr.json()
                            ep["crew"] = cr_data.get("crew", [])
                            ep["cast"] = cr_data.get("cast", [])
                            ep["guest_stars"] = cr_data.get("guest_stars", [])
                return eps
            return []

        for candidate in candidate_shows:
            c_id = candidate["id"]
            year = (candidate.get("first_air_date") or "")[:4]
            label = f"{candidate['name']} ({year})" if year else candidate["name"]
            label = (
                f"{label} - Extras"
                if (is_extras and "extra" not in label.lower())
                else label
            )
            fetched = fetch_season(season_number, c_id, label)
            episodes_result.extend(fetched)
            if is_extras or not fetched:
                episodes_result.extend(fetch_season(0, c_id, label))

    except Exception as e:
        print(f"TMDB Fetch Error: {e}")

    return final_show_name, episodes_result


def fetch_tmdb_person_credits(
    person_name: str, api_key: str, locale: str = "en-US"
) -> List[Dict[str, Any]]:
    """
    Search TMDB for a person by name and return their TV (or movie) credits.
    Each credit entry includes: show_name, show_id, character, episode_count.
    """
    try:
        # 1. Search for Person ID
        search_url = "https://api.themoviedb.org/3/search/person"
        params = {
            "api_key": api_key,
            "query": person_name,
            "language": locale,
        }
        resp = requests.get(search_url, params=params, timeout=10)
        if not resp.ok:
            return []

        results = resp.json().get("results", [])
        if not results:
            return []

        # Take the top match
        person_id = results[0]["id"]

        # 2. Fetch TV credits
        credits_url = f"https://api.themoviedb.org/3/person/{person_id}/tv_credits"
        c_resp = requests.get(
            credits_url, params={"api_key": api_key, "language": locale}, timeout=10
        )
        if not c_resp.ok:
            return []

        credit_data = c_resp.json()
        cast_credits = credit_data.get("cast", [])
        crew_credits = credit_data.get("crew", [])

        # Combine and format credits
        all_credits = []
        for c in cast_credits:
            all_credits.append(
                {
                    "show_id": c.get("id"),
                    "show_name": c.get("name"),
                    "character": c.get("character"),
                    "episode_count": c.get("episode_count"),
                    "role_type": "cast",
                }
            )
        for c in crew_credits:
            all_credits.append(
                {
                    "show_id": c.get("id"),
                    "show_name": c.get("name"),
                    "job": c.get("job"),
                    "department": c.get("department"),
                    "episode_count": c.get("episode_count"),
                    "role_type": "crew",
                }
            )

        # Sort by episode count descending
        all_credits.sort(key=lambda x: x.get("episode_count", 0), reverse=True)
        return all_credits
    except Exception as e:
        print(f"TMDB Person Fetch Error: {e}")
        return []
