"""
Uses heuristics and AI to extract the video information from cast and summary.
"""

import requests
import re
from difflib import SequenceMatcher
from typing import List, Dict, Any

from mediatamer.signals.video_metadata import VideoMetadata
from mediatamer.signals.tvdb import (
    crossreference_people_tvdb,
    rank_episodes_by_tvdb_people,
    get_tvdb_episode_info,
)

BASE_URL = "https://api.themoviedb.org/3"


class MetadataMatcher:
    def __init__(self, tmdb_api_key: str):
        self.api_key = tmdb_api_key
        self.base_url = "https://api.themoviedb.org/3"
        # simple in-memory cache for person tv credits to avoid repeated API calls
        self._person_credits_cache: Dict[int, Dict[str, Any]] = {}

    def _fuzzy_ratio(self, s1: str, s2: str) -> float:
        """Calcule la similitude entre deux chaînes pour gérer l'OCR sale."""
        return SequenceMatcher(None, s1.upper(), s2.upper()).ratio()

    def get_season_from_path(self, path):
        """Extrait le numéro de saison depuis le nom du dossier ou du fichier."""
        match = re.search(r"[sS]eason_?(\d+)|[sS](\d+)", str(path))
        if match:
            return int(match.group(1) or match.group(2))
        return None

    def clean_string(self, text):
        """Remove non-alphanumeric characters and convert to uppercase."""
        return re.sub(r"[^a-zA-Z\s]", "", text).strip().upper()

    def person_tv_credits(self, person_id: int) -> Dict[str, Any]:
        """Fetch and cache `/person/{id}/tv_credits` for a person.

        Returns a dict containing `cast` and `crew` lists (empty dict on error).
        """
        if not person_id:
            return {"cast": [], "crew": []}
        if person_id in self._person_credits_cache:
            return self._person_credits_cache[person_id]
        try:
            resp = requests.get(
                f"{self.base_url}/person/{person_id}/tv_credits",
                params={"api_key": self.api_key, "language": "en-US"},
                timeout=10,
            )
        except Exception:
            return {"cast": [], "crew": []}

        if not resp.ok:
            return {"cast": [], "crew": []}

        data = resp.json()
        self._person_credits_cache[person_id] = data
        return data

    def search_person(
        self,
        name: str,
        min_popularity: float | None = None,
    ) -> List[Dict[str, Any]]:
        """Return the top TMDB person hits for *name*.

        Args:
            name:           Person name to search (may contain OCR noise).
            max_results:    Maximum number of hits to return (default 3).
            min_popularity: When set, discard candidates whose TMDB popularity
                            is strictly below this threshold. Candidates that
                            survive the filter are still capped at max_results.

        Each returned entry contains:
          - id                   : TMDB person id
          - name                 : canonical name as stored in TMDB
          - popularity           : TMDB popularity score
          - known_for_department : e.g. "Acting", "Directing", …
          - known_for            : list of show/movie titles they are best known for
        """
        params = {"api_key": self.api_key, "query": name, "language": "en-US"}
        try:
            resp = requests.get(
                f"{self.base_url}/search/person", params=params, timeout=10
            )
        except Exception:
            return []

        if not resp.ok:
            return []

        hits = []
        for r in resp.json().get("results", []):
            popularity = r.get("popularity", 0.0)
            if min_popularity is not None and popularity < min_popularity:
                continue
            hits.append(
                {
                    "id": r.get("id"),
                    "name": r.get("name", ""),
                    "popularity": popularity,
                    "known_for_department": r.get("known_for_department", ""),
                    "known_for": [
                        {
                            "title": kf.get("title") or kf.get("name", ""),
                            "media_type": kf.get("media_type", ""),
                        }
                        for kf in r.get("known_for", [])
                    ],
                }
            )
        return hits

    def get_tv_episodes_for_person(
        self,
        name: str,
        min_popularity: float | None = None,
    ) -> List[Dict[str, Any]]:
        """Return every TV show credit for the best TMDB match of *name*.

        Resolves *name* via ``search_person`` (respecting *min_popularity*),
        picks the top candidate, then fetches their full TV credits via
        ``person_tv_credits``.

        Each entry in the returned list contains:
          - person_id      : TMDB person id that was resolved
          - person_name    : canonical TMDB name
          - show_id        : TMDB show id
          - show_name      : show title
          - character      : character name (cast credits only, "" for crew)
          - department     : crew department (crew credits only, "" for cast)
          - job            : crew job title (crew credits only, "" for cast)
          - episode_count  : total episodes credited on TMDB
          - first_air_date : show first air date string
          - credit_type    : "cast" or "crew"
        """
        candidates = self.search_person(name, min_popularity=min_popularity)
        if not candidates:
            return []

        best = candidates[0]
        pid = best["id"]
        pname = best["name"]
        credits = self.person_tv_credits(pid)

        episodes: List[Dict[str, Any]] = []
        for entry in credits.get("cast", []):
            episodes.append(
                {
                    "person_id": pid,
                    "person_name": pname,
                    "show_id": entry.get("id"),
                    "show_name": entry.get("name", ""),
                    "character": entry.get("character", ""),
                    "department": "",
                    "job": "",
                    "episode_count": entry.get("episode_count", 0),
                    "first_air_date": entry.get("first_air_date", ""),
                    "credit_type": "cast",
                }
            )
        for entry in credits.get("crew", []):
            episodes.append(
                {
                    "person_id": pid,
                    "person_name": pname,
                    "show_id": entry.get("id"),
                    "show_name": entry.get("name", ""),
                    "character": "",
                    "department": entry.get("department", ""),
                    "job": entry.get("job", ""),
                    "episode_count": entry.get("episode_count", 0),
                    "first_air_date": entry.get("first_air_date", ""),
                    "credit_type": "crew",
                }
            )

        # Sort by episode_count descending so the most recurring shows come first
        episodes.sort(key=lambda x: x["episode_count"], reverse=True)
        return episodes

    def crossreference_people(
        self,
        names: List[str],
        min_popularity: float | None = None,
    ) -> List[Dict[str, Any]]:
        """Return TV shows ranked by how many names from *names* co-appear.

        For each OCR name all TMDB person candidates are tried (not just the
        top hit). A show earns exactly one vote per OCR name regardless of how
        many candidates matched — the wrong homonym simply won't co-appear with
        the other people in the credits.

        Returns a list sorted by ``match_count`` descending. Each entry:
          - show_id        : TMDB show id
          - show_name      : show title
          - first_air_date : show first air date string
          - match_count    : number of distinct OCR names that co-appear
          - people         : list of {ocr_name, person_id, person_name,
                             episode_count, credit_type, character, job}
                             (best-matching credit per OCR name)
        """
        # show_id -> { ocr_name -> best_credit_entry }
        show_map: Dict[int, Dict[str, Any]] = {}

        for ocr_name in names:
            if not ocr_name or len(ocr_name) < 2:
                continue

            candidates = self.search_person(ocr_name, min_popularity=min_popularity)
            if not candidates:
                continue

            # Try every candidate; a show gets at most one vote for this ocr_name
            for cand in candidates:
                # Skip candidates whose known_for is non-empty but entirely movies.
                # A person known only for films is almost certainly the wrong match
                # for a TV credit search (e.g. "Ben Foster" the movie actor vs the
                # Doctor Who camera editor with the same name).
                known_for_types = {
                    kf.get("media_type", "") for kf in cand.get("known_for", [])
                }
                if known_for_types and known_for_types.issubset({"movie"}):
                    continue

                pid = cand["id"]
                pname = cand["name"]
                credits = self.person_tv_credits(pid)

                for credit_type, entries in (
                    ("cast", credits.get("cast", [])),
                    ("crew", credits.get("crew", [])),
                ):
                    for entry in entries or []:
                        sid = entry.get("id")
                        if not sid:
                            continue

                        if sid not in show_map:
                            show_map[sid] = {
                                "show_id": sid,
                                "show_name": entry.get("name", ""),
                                "first_air_date": entry.get("first_air_date", ""),
                                "votes": {},  # ocr_name -> best credit
                            }

                        existing = show_map[sid]["votes"].get(ocr_name)
                        ep_count = entry.get("episode_count", 0)
                        if existing is None or ep_count > existing["episode_count"]:
                            show_map[sid]["votes"][ocr_name] = {
                                "ocr_name": ocr_name,
                                "person_id": pid,
                                "person_name": pname,
                                "episode_count": ep_count,
                                "credit_type": credit_type,
                                "character": entry.get("character", "")
                                if credit_type == "cast"
                                else "",
                                "job": entry.get("job", "")
                                if credit_type == "crew"
                                else "",
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
                    "first_air_date": info["first_air_date"],
                    "match_count": match_count,
                    "people": sorted(
                        votes.values(),
                        key=lambda x: x["episode_count"],
                        reverse=True,
                    ),
                }
            )

        results.sort(key=lambda x: x["match_count"], reverse=True)
        return results

    def get_show_episodes(
        self,
        show: int | str,
        season_hint: int | None = None,
    ) -> List[Dict[str, Any]]:
        """Return episode metadata for a TV show.

        Args:
            show:         TMDB show id (int) **or** a show name string to
                          resolve first via TMDB search.
            season_hint:  When set, only fetch this season number.  When
                          omitted, all seasons are fetched.

        Each returned entry contains:
          - show_id        : TMDB show id
          - show_name      : show title
          - season         : season number
          - episode        : episode number
          - title          : episode title
          - air_date       : episode air date string
          - overview       : episode synopsis
          - runtime        : episode runtime in minutes (or None)
          - guest_stars    : list of {id, name, character}
          - crew           : list of {id, name, job, department}
        """
        # Resolve a name to show_id if needed
        if isinstance(show, str):
            params = {
                "api_key": self.api_key,
                "query": show,
                "language": "en-US",
                "include_adult": "false",
            }
            try:
                resp = requests.get(
                    f"{self.base_url}/search/tv", params=params, timeout=10
                )
            except Exception:
                return []
            if not resp.ok:
                return []
            results = resp.json().get("results", [])
            if not results:
                return []
            # pick best textual match
            results.sort(
                key=lambda r: self._fuzzy_ratio(
                    self.clean_string(show), self.clean_string(r.get("name", ""))
                ),
                reverse=True,
            )
            show_id = results[0]["id"]
            show_name = results[0].get("name", "")
        else:
            show_id = show
            show_name = ""

        # Fetch show details to get the season list (unless a hint is given).
        # Season 0 (specials / Christmas episodes) is always included alongside
        # the hinted season so that specials are never silently skipped.
        if season_hint is not None:
            seasons_to_fetch = sorted({0, season_hint})
            # Ensure we still populate `show_name` when the caller provided a
            # season hint (we previously skipped fetching show details and
            # left `show_name` empty). Fetch the show detail but continue to
            # only request the hinted seasons.
            try:
                detail_resp = requests.get(
                    f"{self.base_url}/tv/{show_id}",
                    params={"api_key": self.api_key, "language": "en-US"},
                    timeout=10,
                )
                if detail_resp.ok:
                    detail = detail_resp.json()
                    if not show_name:
                        show_name = detail.get("name", "")
            except Exception:
                # Best-effort only — if this fails we can still proceed with
                # seasons fetched, but the returned episodes may have an
                # empty `show_name`.
                pass
        else:
            try:
                detail_resp = requests.get(
                    f"{self.base_url}/tv/{show_id}",
                    params={"api_key": self.api_key, "language": "en-US"},
                    timeout=10,
                )
            except Exception:
                return []
            if not detail_resp.ok:
                return []
            detail = detail_resp.json()
            if not show_name:
                show_name = detail.get("name", "")
            seasons_to_fetch = [s["season_number"] for s in detail.get("seasons", [])]

        episodes: List[Dict[str, Any]] = []
        for s_num in seasons_to_fetch:
            try:
                s_resp = requests.get(
                    f"{self.base_url}/tv/{show_id}/season/{s_num}",
                    params={
                        "api_key": self.api_key,
                        "language": "en-US",
                        "append_to_response": "credits",
                    },
                    timeout=10,
                )
            except Exception:
                continue
            if not s_resp.ok:
                continue
            season_data = s_resp.json()
            # Main cast is season-level; share across all episodes in this season
            main_cast = [
                {
                    "id": p.get("id"),
                    "name": p.get("name", ""),
                    "character": p.get("character", ""),
                }
                for p in (season_data.get("credits", {}).get("cast") or [])
            ]
            for ep in season_data.get("episodes", []):
                episodes.append(
                    {
                        "show_id": show_id,
                        "show_name": show_name,
                        "season": s_num,
                        "episode": ep.get("episode_number"),
                        "title": ep.get("name", ""),
                        "air_date": ep.get("air_date", ""),
                        "overview": ep.get("overview", ""),
                        "runtime": ep.get("runtime"),
                        "main_cast": main_cast,
                        "guest_stars": [
                            {
                                "id": g.get("id"),
                                "name": g.get("name", ""),
                                "character": g.get("character", ""),
                            }
                            for g in (ep.get("guest_stars") or [])
                        ],
                        "crew": [
                            {
                                "id": c.get("id"),
                                "name": c.get("name", ""),
                                "job": c.get("job", ""),
                                "department": c.get("department", ""),
                            }
                            for c in (ep.get("crew") or [])
                        ],
                    }
                )
        return episodes

    def rank_episodes_by_cast(
        self,
        episodes: List[Dict[str, Any]],
        show_people: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Cross-reference episode metadata against a resolved people list.

        Args:
            episodes:     Output of ``get_show_episodes`` — each entry must
                          have ``guest_stars`` and ``crew`` lists with ``id``
                          fields.
            show_people:  Output of ``crossreference_people[*]["people"]`` —
                          each entry must have ``person_id`` and ``ocr_name``.

        Returns a copy of *episodes* sorted by ``match_count`` descending.
        Each entry gains two extra keys:
          - match_count   : number of distinct OCR names found in this episode
          - matched_people: list of {ocr_name, person_id, person_name,
                            credit_type, character, job} for every hit
        """
        # Build a lookup: person_id -> {ocr_name, person_name}
        pid_to_ocr: Dict[int, Dict[str, str]] = {}
        for p in show_people:
            pid = p.get("person_id")
            if pid:
                pid_to_ocr[pid] = {
                    "ocr_name": p.get("ocr_name", ""),
                    "person_name": p.get("person_name", ""),
                }

        ranked: List[Dict[str, Any]] = []
        for ep in episodes:
            matched: Dict[str, Dict[str, Any]] = {}  # ocr_name -> hit detail

            # Priority: guest > main cast > crew
            for g in ep.get("guest_stars") or []:
                pid = g.get("id")
                if pid and pid in pid_to_ocr:
                    ocr = pid_to_ocr[pid]["ocr_name"]
                    matched[ocr] = {
                        "ocr_name": ocr,
                        "person_id": pid,
                        "person_name": pid_to_ocr[pid]["person_name"],
                        "credit_type": "guest",
                        "character": g.get("character", ""),
                        "job": "",
                    }

            for m in ep.get("main_cast") or []:
                pid = m.get("id")
                if pid and pid in pid_to_ocr:
                    ocr = pid_to_ocr[pid]["ocr_name"]
                    if ocr not in matched:  # guest takes priority
                        matched[ocr] = {
                            "ocr_name": ocr,
                            "person_id": pid,
                            "person_name": pid_to_ocr[pid]["person_name"],
                            "credit_type": "main",
                            "character": m.get("character", ""),
                            "job": "",
                        }

            for c in ep.get("crew") or []:
                pid = c.get("id")
                if pid and pid in pid_to_ocr:
                    ocr = pid_to_ocr[pid]["ocr_name"]
                    if ocr not in matched:  # guest/main take priority
                        matched[ocr] = {
                            "ocr_name": ocr,
                            "person_id": pid,
                            "person_name": pid_to_ocr[pid]["person_name"],
                            "credit_type": "crew",
                            "character": "",
                            "job": c.get("job", ""),
                        }

            ranked.append(
                {
                    **ep,
                    "match_count": len(matched),
                    "matched_people": sorted(
                        matched.values(),
                        key=lambda x: x["credit_type"],  # guest before crew
                    ),
                }
            )

        ranked.sort(key=lambda x: x["match_count"], reverse=True)
        return ranked

    def resolve_person_candidates(
        self,
        ocr_name: str,
        max_results: int = 3,
        preferred_show_ids: List[int] | None = None,
    ) -> List[Dict[str, Any]]:
        """Try to resolve an OCR'd person name to TMDB person candidates.

        Returns a list of candidates with `id`, `name` and a local fuzzy `score`.
        """
        params = {"api_key": self.api_key, "query": ocr_name, "language": "en-US"}
        try:
            resp = requests.get(
                f"{self.base_url}/search/person", params=params, timeout=10
            )
        except Exception:
            return []

        if not resp.ok:
            return []

        results = resp.json().get("results", [])[:max_results]
        candidates: List[Dict[str, Any]] = []
        for r in results:
            name = r.get("name", "")
            pid = r.get("id")
            score = self._fuzzy_ratio(
                self.clean_string(ocr_name), self.clean_string(name)
            )

            appears_in_show = False
            matched_show_ids: List[int] = []
            if preferred_show_ids and pid:
                credits = self.person_tv_credits(pid)
                # tv_credits has 'cast' and 'crew' arrays where each entry has an 'id' (show id)
                for entry in (credits.get("cast", []) or []) + (
                    credits.get("crew", []) or []
                ):
                    if entry.get("id") in preferred_show_ids:
                        appears_in_show = True
                        matched_show_ids.append(entry.get("id"))

            # boost score if the candidate actually appears in one of the preferred shows
            adj_score = min(1.0, score + (0.4 if appears_in_show else 0.0))

            candidates.append(
                {
                    "id": pid,
                    "name": name,
                    "score": adj_score,
                    "raw_score": score,
                    "known_for": r.get("known_for", []),
                    "appears_in_show": appears_in_show,
                    "matched_show_ids": matched_show_ids,
                }
            )

        # prefer candidates who are known to appear in the chosen show, then by score
        candidates.sort(
            key=lambda x: (1 if x.get("appears_in_show") else 0, x["score"]),
            reverse=True,
        )
        return candidates

    def resolve_all_ocr(
        self, ocr_list: List[str], preferred_show_ids: List[int] | None = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        mapping: Dict[str, List[Dict[str, Any]]] = {}
        for o in ocr_list:
            if not o or len(o) < 3:
                mapping[o] = []
                continue
            mapping[o] = self.resolve_person_candidates(
                o, max_results=3, preferred_show_ids=preferred_show_ids
            )
        return mapping

    def find_best_episodes(self, show, ocr_actors, path):
        """Search TV show seasons/episodes and rank episodes by how many OCR'd people appear.

        Returns a dict with `ordered_candidates` (list), `person_episode_map` and `person_candidates_map`.
        """
        season_hint = self.get_season_from_path(path)
        params = {
            "api_key": self.api_key,
            "query": show,
            "include_adult": "false",
            "language": "en-US",
        }
        resp = requests.get(f"{self.base_url}/search/tv", params=params)

        if not resp.ok:
            print(f"Erreur API TMDB: {resp.status_code} - {resp.text}")
            return {
                "ordered_candidates": [],
                "person_episode_map": {},
                "person_candidates_map": {},
            }

        search_tv = resp.json()
        results = search_tv.get("results", [])
        if not results:
            print("No result found for the TV search.")
            return {
                "ordered_candidates": [],
                "person_episode_map": {},
                "person_candidates_map": {},
            }

        # Score TV search results against the guessed show name and prefer the best match.
        clean_show_query = self.clean_string(show) if show else ""
        show_scores = []
        for r in results:
            cname = r.get("name", "")
            ratio = self._fuzzy_ratio(clean_show_query, self.clean_string(cname))
            show_scores.append((r, ratio))

        show_scores.sort(key=lambda x: x[1], reverse=True)
        if show_scores:
            print("search_ovdb: TMDB show candidates (name - id - match):")
            for r, ratio in show_scores[:5]:
                print(
                    f"search_ovdb:   {r.get('name')} (id:{r.get('id')}) ratio={ratio:.2f}"
                )

            if show_scores[0][1] >= 0.75:
                # take only the best-matching show when similarity is high
                results = [show_scores[0][0]]
            else:
                # otherwise prefer the two best textual matches
                results = [r for r, _ in show_scores[:2]]

        ordered_candidates: List[Dict[str, Any]] = []

        # Resolve OCR names to TMDB person candidates (helps with OCR typos)
        preferred_show_ids = [r.get("id") for r in results if r.get("id")]
        person_candidates_map = self.resolve_all_ocr(
            ocr_actors, preferred_show_ids=preferred_show_ids
        )
        # Debug: print resolved TMDB person candidates for each OCR name
        for o, cands in person_candidates_map.items():
            if not cands:
                print(f"search_ovdb: No TMDB person candidates for OCR '{o}'")
            else:
                cand_parts = []
                for c in cands:
                    part = f"{c['name']}(id:{c['id']} score:{c['score']:.2f})"
                    if c.get("appears_in_show"):
                        part += "[in-show]"
                    cand_parts.append(part)
                cand_str = ", ".join(cand_parts)
                print(f"search_ovdb: Candidates for '{o}': {cand_str}")

        # pick the top candidate id for quick id-based matching when confident
        best_person_by_ocr: Dict[str, Any] = {}
        for o, candidates in person_candidates_map.items():
            chosen = None
            if candidates:
                # prefer a candidate known to appear in the chosen show
                for c in candidates:
                    if c.get("appears_in_show"):
                        chosen = c.get("id")
                        break
                # otherwise fall back to the top fuzzy candidate if it's confident
                if not chosen and candidates[0]["score"] >= 0.75:
                    chosen = candidates[0]["id"]
            best_person_by_ocr[o] = chosen

        # Per-person episode lists
        person_episode_map: Dict[str, List[Dict[str, Any]]] = {
            o: [] for o in ocr_actors
        }

        for show in results:
            show_id = show["id"]
            # Build a sensible list of seasons to check: prefer hinted season, otherwise first two
            seasons_to_check = []
            if season_hint is not None:
                seasons_to_check.append(season_hint)
            seasons_to_check.extend([1, 2])
            # ensure uniqueness and sane values
            seasons_to_check = [
                s
                for s in dict.fromkeys(seasons_to_check)
                if s and isinstance(s, int) and s > 0
            ]

            for s_num in seasons_to_check:
                try:
                    season_resp = requests.get(
                        f"{self.base_url}/tv/{show_id}/season/{s_num}",
                        params={
                            "api_key": self.api_key,
                            "append_to_response": "credits",
                        },
                        timeout=10,
                    )
                except Exception:
                    continue

                if not season_resp.ok:
                    continue

                season_data = season_resp.json()

                if "episodes" not in season_data:
                    continue

                # Season-level main cast (we'll use ids when present)
                season_cast = season_data.get("credits", {}).get("cast", [])

                for ep in season_data["episodes"]:
                    guest_cast = ep.get("guest_stars", []) or []
                    crew = ep.get("crew", []) or []

                    current_ep_score = 0
                    matched_names = []
                    matched_ocr_for_ep = set()

                    for ocr_name in ocr_actors:
                        if not ocr_name or len(ocr_name) < 2:
                            continue

                        # Prefer id-based matching when we have a confident candidate
                        candidate_id = best_person_by_ocr.get(ocr_name)
                        matched_flag = False

                        if candidate_id:
                            for g in guest_cast:
                                if g.get("id") == candidate_id:
                                    current_ep_score += 5
                                    matched_names.append(
                                        g.get("name") or str(candidate_id)
                                    )
                                    matched_ocr_for_ep.add(ocr_name)
                                    person_episode_map.setdefault(ocr_name, []).append(
                                        {
                                            "show": show["name"],
                                            "season": s_num,
                                            "episode": ep.get("episode_number"),
                                            "title": ep.get("name"),
                                            "match_type": "guest_id",
                                        }
                                    )
                                    matched_flag = True
                                    break
                            if matched_flag:
                                continue

                            for c in crew:
                                if c.get("id") == candidate_id:
                                    current_ep_score += 3
                                    matched_names.append(
                                        c.get("name") or str(candidate_id)
                                    )
                                    matched_ocr_for_ep.add(ocr_name)
                                    person_episode_map.setdefault(ocr_name, []).append(
                                        {
                                            "show": show["name"],
                                            "season": s_num,
                                            "episode": ep.get("episode_number"),
                                            "title": ep.get("name"),
                                            "match_type": "crew_id",
                                        }
                                    )
                                    matched_flag = True
                                    break
                            if matched_flag:
                                continue

                            for m in season_cast:
                                if m.get("id") == candidate_id:
                                    current_ep_score += 1
                                    matched_names.append(
                                        m.get("name") or str(candidate_id)
                                    )
                                    matched_ocr_for_ep.add(ocr_name)
                                    person_episode_map.setdefault(ocr_name, []).append(
                                        {
                                            "show": show["name"],
                                            "season": s_num,
                                            "episode": ep.get("episode_number"),
                                            "title": ep.get("name"),
                                            "match_type": "main_id",
                                        }
                                    )
                                    matched_flag = True
                                    break

                        # Fallback to fuzzy name matching against episode lists
                        if not matched_flag:
                            ocr_clean = self.clean_string(ocr_name)
                            for g in guest_cast:
                                if (
                                    self._fuzzy_ratio(
                                        ocr_clean, self.clean_string(g.get("name", ""))
                                    )
                                    > 0.85
                                ):
                                    current_ep_score += 5
                                    matched_names.append(g.get("name"))
                                    matched_ocr_for_ep.add(ocr_name)
                                    person_episode_map.setdefault(ocr_name, []).append(
                                        {
                                            "show": show["name"],
                                            "season": s_num,
                                            "episode": ep.get("episode_number"),
                                            "title": ep.get("name"),
                                            "match_type": "guest_fuzzy",
                                        }
                                    )
                                    matched_flag = True
                                    break
                            if matched_flag:
                                continue

                            for c in crew:
                                if (
                                    self._fuzzy_ratio(
                                        ocr_clean, self.clean_string(c.get("name", ""))
                                    )
                                    > 0.85
                                ):
                                    current_ep_score += 3
                                    matched_names.append(c.get("name"))
                                    matched_ocr_for_ep.add(ocr_name)
                                    person_episode_map.setdefault(ocr_name, []).append(
                                        {
                                            "show": show["name"],
                                            "season": s_num,
                                            "episode": ep.get("episode_number"),
                                            "title": ep.get("name"),
                                            "match_type": "crew_fuzzy",
                                        }
                                    )
                                    matched_flag = True
                                    break
                            if matched_flag:
                                continue

                            for m in season_cast:
                                if (
                                    self._fuzzy_ratio(
                                        ocr_clean, self.clean_string(m.get("name", ""))
                                    )
                                    > 0.85
                                ):
                                    current_ep_score += 1
                                    matched_names.append(m.get("name"))
                                    matched_ocr_for_ep.add(ocr_name)
                                    person_episode_map.setdefault(ocr_name, []).append(
                                        {
                                            "show": show["name"],
                                            "season": s_num,
                                            "episode": ep.get("episode_number"),
                                            "title": ep.get("name"),
                                            "match_type": "main_fuzzy",
                                        }
                                    )
                                    matched_flag = True
                                    break

                    candidate = {
                        "show_name": show["name"],
                        "series_air_date": show.get("first_air_date", ""),
                        "season": s_num,
                        "episode": ep.get("episode_number"),
                        "title": ep.get("name"),
                        "score": current_ep_score,
                        "matched_names": list(set(matched_names)),
                        "matched_ocr_names": list(matched_ocr_for_ep),
                    }
                    ordered_candidates.append(candidate)

        # sort by score then by number of matched OCR names
        ordered_candidates.sort(
            key=lambda x: (x["score"], len(x.get("matched_ocr_names", []))),
            reverse=True,
        )

        # compute episode with the most matched OCR names
        best_overlap = None
        if ordered_candidates:
            best_overlap = max(
                ordered_candidates, key=lambda x: len(x.get("matched_ocr_names", []))
            )

        return {
            "ordered_candidates": ordered_candidates,
            "person_episode_map": person_episode_map,
            "person_candidates_map": person_candidates_map,
            "best_overlap": best_overlap,
        }


def _fuzzy_show_match(name1: str, name2: str) -> float:
    """Case-insensitive fuzzy ratio between two show names."""
    return SequenceMatcher(None, name1.upper().strip(), name2.upper().strip()).ratio()


def search_ovdb(metadata: VideoMetadata, config: dict) -> bool:
    matcher = MetadataMatcher(config.get("tmdb-api-key"))
    people = metadata.cast_profile["real_actors"] + metadata.cast_profile["crew_names"]
    print(f"search_ovdb: People extracted: {people}")

    if not people:
        print("search_ovdb: No people found, skipping.")
        metadata.ovdb = {"shows": [], "ranked_episodes": [], "best_episode": None}
        return False

    # Step 1a: TMDB cross-reference
    shows = matcher.crossreference_people(people)

    # Step 1b: TVDB parallel track — explicit TV/movie split, no heuristics needed
    tvdb_api_key = config.get("tvdb-api-key")
    tvdb_shows = (
        crossreference_people_tvdb(people, tvdb_api_key) if tvdb_api_key else []
    )

    if tvdb_shows:
        best_tvdb = tvdb_shows[0]
        print(
            f"search_ovdb: TVDB track best show: {best_tvdb['show_name']}"
            f" — {best_tvdb['match_count']} people matched"
        )
        for p in best_tvdb["people"][:5]:
            print(
                f"search_ovdb: TVDB  '{p['ocr_name']}' → {p['person_name']}"
                f" ({p['people_type']}, char='{p['character']}')"
            )
    else:
        best_tvdb = None
        print("search_ovdb: TVDB track found no matches.")

    # Merge: pick the show with the most votes, using the other track to confirm.
    # If both tracks agree (same show name, fuzzy ≥ 0.8) boost confidence.
    # If TVDB has strictly more matches, prefer it (TVDB's TV/movie split is cleaner).
    if not shows and not best_tvdb:
        print("search_ovdb: No matching show found on either track.")
        metadata.ovdb = {"shows": [], "ranked_episodes": [], "best_episode": None}
        return False

    if shows:
        best_show = shows[0]
        tmdb_count = best_show["match_count"]
    else:
        best_show = None
        tmdb_count = 0

    tvdb_count = best_tvdb["match_count"] if best_tvdb else 0

    if best_show and best_tvdb:
        agreement = _fuzzy_show_match(best_show["show_name"], best_tvdb["show_name"])
        print(
            f"search_ovdb: Track agreement: TMDB='{best_show['show_name']}' ({tmdb_count} votes)"
            f" vs TVDB='{best_tvdb['show_name']}' ({tvdb_count} votes)"
            f" — name similarity {agreement:.2f}"
        )
        if agreement >= 0.8:
            print("search_ovdb: Both tracks agree — high confidence.")
        elif tvdb_count > tmdb_count:
            # TVDB found more co-appearing people; trust it for show name lookup.
            # Update show_id/show_name to the TVDB show name so get_show_episodes()
            # resolves the correct TMDB entry via its name-search path.
            # Crucially: keep best_show["people"] unchanged — those entries carry
            # TMDB person IDs which rank_episodes_by_cast needs to match against
            # TMDB episode cast data.  Replacing them with TVDB person IDs breaks
            # episode ranking (the two ID spaces are unrelated).
            print(
                f"search_ovdb: TVDB track has more matches ({tvdb_count} > {tmdb_count})"
                f" — preferring TVDB show name '{best_tvdb['show_name']}' for lookup."
            )
            best_show["show_id"] = best_tvdb[
                "show_name"
            ]  # string → resolved by get_show_episodes
            best_show["show_name"] = best_tvdb["show_name"]
            best_show["match_count"] = tvdb_count
            # best_show["people"] intentionally unchanged (TMDB IDs for episode ranking)
        else:
            print(
                "search_ovdb: Tracks disagree — keeping TMDB result (more matches or equal)."
            )
    elif not best_show:
        # Only TVDB found something
        print(
            f"search_ovdb: Only TVDB track matched — using '{best_tvdb['show_name']}'."
        )
        best_show = {
            "show_id": best_tvdb["show_name"],
            "show_name": best_tvdb["show_name"],
            "first_air_date": "",
            "match_count": tvdb_count,
            "people": [
                {
                    "ocr_name": p["ocr_name"],
                    "person_id": p["person_id"],
                    "person_name": p["person_name"],
                    "episode_count": 0,
                    "credit_type": "cast",
                    "character": p["character"],
                    "job": "",
                }
                for p in best_tvdb["people"]
            ],
        }

    year = best_show["first_air_date"][:4] if best_show.get("first_air_date") else "?"
    print(
        f"search_ovdb: Best show: {best_show['show_name']} ({year})"
        f" id:{best_show['show_id']} — {best_show['match_count']} people matched"
    )
    for p in best_show["people"]:
        print(
            f"search_ovdb:   '{p['ocr_name']}' → {p['person_name']}"
            f" ({p.get('credit_type', p.get('people_type', ''))},"
            f" {p.get('episode_count', p.get('character', ''))})"
        )

    # Step 2+3: rank episodes by co-appearing people.
    # Try TVDB first: it stores episodeId on each character record, giving a
    # direct per-episode cast lookup that is often more complete than TMDB.
    # Fall back to TMDB if TVDB returns no useful results.
    ranked: list = []
    if best_tvdb and isinstance(best_tvdb.get("show_id"), int) and tvdb_api_key:
        tvdb_ep_ranked = rank_episodes_by_tvdb_people(
            best_tvdb["show_id"], best_tvdb["people"], tvdb_api_key
        )
        tvdb_has_strict_winner = (
            tvdb_ep_ranked
            and tvdb_ep_ranked[0]["match_count"] > 0
            and all(
                tvdb_ep_ranked[0]["match_count"] > ep["match_count"]
                for ep in tvdb_ep_ranked[1:]
            )
        )
        if tvdb_has_strict_winner:
            # Enrich every ranked entry with episode metadata (season/ep/title).
            for r in tvdb_ep_ranked:
                info = get_tvdb_episode_info(r["episode_id"], tvdb_api_key)
                r["show_name"] = best_show["show_name"]
                r["show_id"] = best_tvdb["show_id"]
                r["season"] = info["season"] if info else None
                r["episode"] = info["episode"] if info else None
                r["title"] = info["title"] if info else ""
                r["air_date"] = info["air_date"] if info else ""
            ranked = tvdb_ep_ranked
            print(
                f"search_ovdb: TVDB episode ranking used"
                f" ({tvdb_ep_ranked[0]['match_count']} people in top episode)."
            )
        elif tvdb_ep_ranked:
            top = tvdb_ep_ranked[0]["match_count"]
            n_tied = sum(1 for ep in tvdb_ep_ranked if ep["match_count"] == top)
            print(
                f"search_ovdb: TVDB episode ranking inconclusive"
                f" ({top} people, {n_tied} episodes tied) — falling back to TMDB."
            )

    if not ranked:
        # Fall back to TMDB: fetch all episodes and match TMDB person IDs.
        season_hint = matcher.get_season_from_path(metadata.path)
        episodes = matcher.get_show_episodes(
            best_show["show_id"], season_hint=season_hint
        )
        ranked = matcher.rank_episodes_by_cast(episodes, best_show["people"])

    # Check if the best episode has strictly the highest number of matched OCR names
    # and that this number is > 0
    best_episode = (
        ranked[0]
        if ranked
        and ranked[0]["match_count"] > 0
        and all(ranked[0]["match_count"] > ep["match_count"] for ep in ranked[1:])
        else {}
    )

    if best_episode and best_episode["match_count"] > 0:
        print("search_ovdb: --- MATCH FOUND ---")
        print(f"search_ovdb: Show   : {best_episode['show_name']} ({year})")
        print(
            f"search_ovdb: Episode: S{best_episode['season']:02d}E{best_episode['episode']:02d}"
            f" - {best_episode['title']}"
        )
        hits = ", ".join(
            f"{p['person_name']}({p['credit_type']})"
            for p in best_episode["matched_people"]
        )
        print(f"search_ovdb: People : {best_episode['match_count']} matched — {hits}")
    else:
        print("search_ovdb: No conclusive match found.")

    metadata.ovdb = {
        "shows": shows,
        "ranked_episodes": ranked,
        "best_episode": best_episode,
    }
