import requests
from typing import List, Dict, Any, Optional, Tuple
from difflib import SequenceMatcher

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
        "name": ep.get("name")
        or ep.get("translations", {}).get("nameTranslations", [{}])[0].get("name"),
        "overview": ep.get("overview") or "",
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

        # Collect all candidates with matching name (handles classic vs revival duplicates)
        candidate_shows = [
            s for s in results if search_query.lower() in (s.get("name") or "").lower()
        ]

        # 2. Fetch episodes from every candidate show
        def fetch_season_episodes(
            s_num: int, _show_id, _show_label: str
        ) -> List[Dict[str, Any]]:
            collected = []
            page = 0
            while True:
                r = requests.get(
                    f"{_TVDB_BASE}/series/{_show_id}/episodes/official",
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
                normalized = [_normalize_episode(ep, s_num) for ep in eps]
                for ep in normalized:
                    ep["_show_name"] = _show_label
                collected.extend(normalized)
                links = body.get("links") or {}
                if not links.get("next"):
                    break
                page += 1
            return collected

        for candidate in candidate_shows:
            c_id = candidate.get("tvdb_id") or candidate.get("id")
            year = str(candidate.get("year") or "")[:4]
            label = (
                f"{candidate.get('name', show_name)} ({year})"
                if year
                else candidate.get("name", show_name)
            )
            label = (
                f"{label} - Extras"
                if (is_extras and "extra" not in label.lower())
                else label
            )
            fetched = fetch_season_episodes(season_number, c_id, label)
            episodes_result.extend(fetched)
            if is_extras or not fetched:
                episodes_result.extend(fetch_season_episodes(0, c_id, label))

    except Exception as e:
        print(f"[TVDB] Fetch error: {e}")

    return final_show_name, episodes_result


# ---------------------------------------------------------------------------
# TVDB person cross-reference — parallel track for cast-based show matching
# ---------------------------------------------------------------------------

# Module-level caches: avoid re-fetching within a run.
# _person_chars_tvdb_cache stores raw character dicts from /people/{id}/extended.
# _person_credits_tvdb_cache stores the deduplicated series-level view (for show matching).
_person_chars_tvdb_cache: Dict[int, List[Dict[str, Any]]] = {}
_person_credits_tvdb_cache: Dict[int, List[Dict[str, Any]]] = {}
_episode_info_tvdb_cache: Dict[int, Optional[Dict[str, Any]]] = {}


def _fuzzy_ratio(s1: str, s2: str) -> float:
    return SequenceMatcher(None, s1.upper(), s2.upper()).ratio()


def search_person_tvdb(name: str, api_key: str) -> Optional[Tuple[int, str]]:
    """Search TVDB for a person by name.

    Returns ``(tvdb_person_id, canonical_name)`` for the best hit, or ``None``.
    The TVDB search endpoint accepts ``type=person`` which restricts results to
    people records only, avoiding false hits on series/movie titles.
    """
    token = _get_tvdb_token(api_key)
    if not token:
        return None
    try:
        resp = requests.get(
            f"{_TVDB_BASE}/search",
            params={"query": name, "type": "person"},
            headers=_tvdb_headers(token),
            timeout=10,
        )
        if not resp.ok:
            return None
        results = resp.json().get("data") or []
        if not results:
            return None
        # Pick the result with the best fuzzy name match
        best = max(
            results,
            key=lambda r: _fuzzy_ratio(name, r.get("name") or ""),
        )
        # tvdb_id is returned as a string like "people-12345"
        raw_id = best.get("tvdb_id", "")
        try:
            pid = int(raw_id.replace("people-", ""))
        except (ValueError, AttributeError):
            return None
        return pid, best.get("name", name)
    except Exception:
        return None


def _fetch_person_chars_tvdb(person_id: int, api_key: str) -> List[Dict[str, Any]]:
    """Fetch and cache raw character records from ``/people/{id}/extended``.

    Both ``get_person_series_tvdb`` and ``rank_episodes_by_tvdb_people`` call
    this helper so the HTTP request is made at most once per person per run.
    """
    if person_id in _person_chars_tvdb_cache:
        return _person_chars_tvdb_cache[person_id]
    token = _get_tvdb_token(api_key)
    if not token:
        _person_chars_tvdb_cache[person_id] = []
        return []
    try:
        resp = requests.get(
            f"{_TVDB_BASE}/people/{person_id}/extended",
            headers=_tvdb_headers(token),
            timeout=10,
        )
        if not resp.ok:
            _person_chars_tvdb_cache[person_id] = []
            return []
        chars = (resp.json().get("data") or {}).get("characters") or []
        _person_chars_tvdb_cache[person_id] = chars
        return chars
    except Exception:
        _person_chars_tvdb_cache[person_id] = []
        return []


def get_person_series_tvdb(person_id: int, api_key: str) -> List[Dict[str, Any]]:
    """Return TV series credits for a TVDB person (deduplicated by series).

    Uses ``/people/{id}/extended`` (cached via ``_fetch_person_chars_tvdb``).
    Only TV entries (``seriesId`` present) are returned — movie credits skipped.

    Each entry: ``{series_id, series_name, people_type, character}``.
    """
    if person_id in _person_credits_tvdb_cache:
        return _person_credits_tvdb_cache[person_id]

    chars = _fetch_person_chars_tvdb(person_id, api_key)
    results: List[Dict[str, Any]] = []
    seen: set = set()
    for char in chars:
        series_id = char.get("seriesId")
        if not series_id:
            continue  # movie credit — skip
        if series_id in seen:
            continue
        seen.add(series_id)
        series_info = char.get("series") or {}
        results.append(
            {
                "series_id": series_id,
                "series_name": series_info.get("name", ""),
                "people_type": char.get("peopleType", ""),
                "character": char.get("name", ""),
            }
        )
    _person_credits_tvdb_cache[person_id] = results
    return results


# Mapping from TVDB peopleType → credit_type used by downstream episode ranking.
_TVDB_PEOPLE_TYPE_TO_CREDIT: Dict[str, str] = {
    "Actor": "cast",
    "Guest Star": "guest",
    "Director": "crew",
    "Writer": "crew",
    "Producer": "crew",
    "Executive Producer": "crew",
    "Creator": "crew",
}


def rank_episodes_by_tvdb_people(
    tvdb_series_id: int,
    people: List[Dict[str, Any]],
    api_key: str,
) -> List[Dict[str, Any]]:
    """Rank TVDB episodes by how many OCR-resolved people appear in them.

    For each person entry (must have ``person_id`` = TVDB person ID), the raw
    character records are fetched (reusing the cache populated during show
    identification).  Each character record carries an ``episodeId`` when the
    credit is episode-specific (guest stars, directors, …).  Regular cast
    members credited at the series level have ``episodeId=None`` and are
    recorded separately — they contribute to every episode's ``match_count``
    as a baseline but are NOT used to discriminate between episodes (they
    appear in all episodes).

    Returns a list sorted by ``match_count`` descending.  Each entry:
      - ``episode_id``     : TVDB episode id (int)
      - ``match_count``    : number of distinct OCR names found in this episode
      - ``matched_people`` : list of {ocr_name, person_id, person_name,
                             credit_type, character, job}
    """
    # episode_id -> {ocr_name -> hit}
    episode_map: Dict[int, Dict[str, Dict[str, Any]]] = {}
    # People credited at series level (no episodeId) — regulars
    series_level: List[Dict[str, Any]] = []

    for person in people:
        pid = person.get("person_id")
        if not pid:
            continue
        ocr_name = person.get("ocr_name", "")

        chars = _fetch_person_chars_tvdb(pid, api_key)
        episode_ids_for_person: List[Tuple[int, Dict[str, Any]]] = []
        for char in chars:
            if char.get("seriesId") != tvdb_series_id:
                continue
            ep_id = char.get("episodeId")
            if ep_id:
                episode_ids_for_person.append((ep_id, char))

        if not episode_ids_for_person:
            # No episode-specific credit in this series — treat as series-level regular.
            series_level.append(
                {
                    "ocr_name": ocr_name,
                    "person_id": pid,
                    "person_name": person.get("person_name", ""),
                    "credit_type": _TVDB_PEOPLE_TYPE_TO_CREDIT.get(
                        person.get("people_type", ""), "cast"
                    ),
                    "character": person.get("character", ""),
                    "job": "",
                }
            )
            continue

        for ep_id, char in episode_ids_for_person:
            if ep_id not in episode_map:
                episode_map[ep_id] = {}
            if ocr_name not in episode_map[ep_id]:
                people_type = char.get("peopleType", "")
                episode_map[ep_id][ocr_name] = {
                    "ocr_name": ocr_name,
                    "person_id": pid,
                    "person_name": person.get("person_name", ""),
                    "credit_type": _TVDB_PEOPLE_TYPE_TO_CREDIT.get(people_type, "cast"),
                    "character": char.get("name", ""),
                    "job": "",
                }

    results: List[Dict[str, Any]] = []
    for ep_id, people_map in episode_map.items():
        # match_count uses ONLY episode-specific credits.
        # Series-level regulars (e.g. main cast with no episodeId) appear in every
        # episode equally — including them in the count would create a massive tie
        # across all episodes and prevent any conclusive winner.
        # They are still recorded in matched_people for downstream display.
        all_people = dict(people_map)
        for p in series_level:
            if p["ocr_name"] not in all_people:
                all_people[p["ocr_name"]] = p
        results.append(
            {
                "episode_id": ep_id,
                "match_count": len(people_map),  # episode-specific only
                "matched_people": list(all_people.values()),
            }
        )

    results.sort(key=lambda x: x["match_count"], reverse=True)
    return results


def get_tvdb_episode_info(episode_id: int, api_key: str) -> Optional[Dict[str, Any]]:
    """Fetch basic metadata for a TVDB episode id.

    Returns ``{season, episode, title, overview, air_date}`` or ``None``.
    Results are cached for the lifetime of the process.
    """
    if episode_id in _episode_info_tvdb_cache:
        return _episode_info_tvdb_cache[episode_id]
    token = _get_tvdb_token(api_key)
    if not token:
        _episode_info_tvdb_cache[episode_id] = None
        return None
    try:
        resp = requests.get(
            f"{_TVDB_BASE}/episodes/{episode_id}/extended",
            headers=_tvdb_headers(token),
            timeout=10,
        )
        if not resp.ok:
            _episode_info_tvdb_cache[episode_id] = None
            return None
        data = resp.json().get("data") or {}
        # seasonNumber may be directly on the record or nested under "season"
        season_num = data.get("seasonNumber")
        if season_num is None:
            season_num = (data.get("season") or {}).get("number")
        info: Optional[Dict[str, Any]] = {
            "season": season_num,
            "episode": data.get("number"),
            "title": data.get("name") or "",
            "overview": data.get("overview") or "",
            "air_date": data.get("aired") or "",
        }
        _episode_info_tvdb_cache[episode_id] = info
        return info
    except Exception:
        _episode_info_tvdb_cache[episode_id] = None
        return None


def crossreference_people_tvdb(
    names: List[str],
    api_key: str,
) -> List[Dict[str, Any]]:
    """Cross-reference OCR'd names against TVDB person credits.

    For every name, searches TVDB for the person then fetches their TV credits
    via ``/people/{id}/extended``.  Because TVDB character records carry an
    explicit ``seriesId`` (TV) vs ``movieId`` (film), no popularity heuristic
    is needed — movie-only people are naturally excluded.

    Returns a list sorted by ``match_count`` descending.  Each entry:
      - show_id     : TVDB series id
      - show_name   : series title
      - match_count : number of distinct OCR names whose resolved person
                      has a TV credit on this show
      - people      : list of {ocr_name, person_id, person_name,
                      people_type, character}
    """
    # tvdb_show_id -> {ocr_name -> credit entry}
    show_map: Dict[int, Dict[str, Any]] = {}

    for ocr_name in names:
        if not ocr_name or len(ocr_name) < 2:
            continue

        result = search_person_tvdb(ocr_name, api_key)
        if not result:
            continue
        pid, pname = result

        for credit in get_person_series_tvdb(pid, api_key):
            sid = credit["series_id"]
            if sid not in show_map:
                show_map[sid] = {
                    "show_id": sid,
                    "show_name": credit["series_name"],
                    "votes": {},
                }
            if ocr_name not in show_map[sid]["votes"]:
                show_map[sid]["votes"][ocr_name] = {
                    "ocr_name": ocr_name,
                    "person_id": pid,
                    "person_name": pname,
                    "people_type": credit["people_type"],
                    "character": credit["character"],
                }

    results: List[Dict[str, Any]] = []
    for sid, info in show_map.items():
        votes = info["votes"]
        match_count = len(votes)
        if match_count < 2:
            continue
        results.append(
            {
                "show_id": sid,
                "show_name": info["show_name"],
                "match_count": match_count,
                "people": list(votes.values()),
            }
        )

    results.sort(key=lambda x: x["match_count"], reverse=True)
    return results
