import requests
from typing import List, Dict, Any, Optional, Tuple

_TVDB_BASE = "https://api4.thetvdb.com/v4"

# Module-level token cache: avoids re-authenticating on every call within a session.
_token_cache: Dict[str, Optional[str]] = {"api_key": None, "token": None}


def _get_tvdb_token(api_key: str) -> Optional[str]:
    """Authenticate with TVDB v4 and return a bearer token (cached per api_key)."""
    if _token_cache["api_key"] == api_key and _token_cache["token"]:
        return _token_cache["token"]
    try:
        resp = requests.post(
            f"{_TVDB_BASE}/login",
            json={"apikey": api_key},
            timeout=10,
        )
        if not resp.ok:
            print(f"[TVDB] Login failed: HTTP {resp.status_code}")
            return None
        token = resp.json().get("data", {}).get("token")
        _token_cache["api_key"] = api_key
        _token_cache["token"] = token
        return token
    except Exception as e:
        print(f"[TVDB] Login error: {e}")
        return None


def _tvdb_headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _normalize_episode(ep: Dict[str, Any], season_number: int) -> Dict[str, Any]:
    """Normalize a TVDB v4 episode record to the TMDB-compatible dict shape used by scoring."""
    return {
        "episode_number": ep.get("number"),
        "season_number": season_number,
        "name": ep.get("name") or ep.get("translations", {}).get("nameTranslations", [{}])[0].get("name"),
        "overview": ep.get("overview", ""),
        "runtime": ep.get("runtime"),  # TVDB already stores this in minutes
        "air_date": ep.get("aired"),
        "id": ep.get("id"),
        # TVDB basic episode records do not include per-episode credits; leave empty.
        "crew": [],
        "cast": [],
        "guest_stars": [],
    }


def fetch_tvdb_info(
    show_name: str, season_number: int, api_key: str, locale: str = "eng"
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Fetch episodes from TVDB v4 for a given show and season.

    Returns:
        A tuple of (normalized_show_name, list_of_TMDB-compatible episode dicts).
    """
    final_show_name = show_name
    episodes_result: List[Dict[str, Any]] = []

    token = _get_tvdb_token(api_key)
    if not token:
        return final_show_name, []

    headers = _tvdb_headers(token)

    try:
        is_extras = " - Extras" in show_name
        search_query = show_name.replace(" - Extras", "") if is_extras else show_name

        # 1. Search for the series
        resp = requests.get(
            f"{_TVDB_BASE}/search",
            params={"query": search_query, "type": "series"},
            headers=headers,
            timeout=10,
        )
        if not resp.ok:
            print(f"[TVDB] Search failed: HTTP {resp.status_code}")
            return final_show_name, []

        results = resp.json().get("data") or []
        best_show = None

        for s in results:
            if (s.get("name") or "").lower() == search_query.lower():
                best_show = s
                break

        if not best_show and is_extras:
            for s in results:
                if "extra" in (s.get("name") or "").lower():
                    best_show = s
                    break

        if not best_show and results:
            best_show = results[0]

        if not best_show:
            return final_show_name, []

        show_id = best_show.get("tvdb_id") or best_show.get("id")
        tvdb_name = best_show.get("name", show_name)
        final_show_name = f"{tvdb_name} - Extras" if (is_extras and "extra" not in tvdb_name.lower()) else tvdb_name

        # 2. Fetch episodes for the requested season (paginated, page 0 covers most seasons)
        def fetch_season_episodes(s_num: int) -> List[Dict[str, Any]]:
            collected = []
            page = 0
            while True:
                r = requests.get(
                    f"{_TVDB_BASE}/series/{show_id}/episodes/official",
                    params={"season": s_num, "page": page},
                    headers=headers,
                    timeout=10,
                )
                if not r.ok:
                    break
                body = r.json()
                eps = (body.get("data") or {}).get("episodes") or []
                if not eps:
                    break
                collected.extend(_normalize_episode(ep, s_num) for ep in eps)
                # Stop if there is no next page
                links = body.get("links") or {}
                if not links.get("next"):
                    break
                page += 1
            return collected

        episodes_result.extend(fetch_season_episodes(season_number))

        # Also pull Season 0 (specials) when looking for extras or if nothing was found
        if is_extras or not episodes_result:
            episodes_result.extend(fetch_season_episodes(0))

    except Exception as e:
        print(f"[TVDB] Fetch error: {e}")

    return final_show_name, episodes_result
