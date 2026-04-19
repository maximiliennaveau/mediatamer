"""
Uses heuristics and AI to extract the video information from cast and summary.
"""

import json
from typing import Any, Dict, List

from mediatamer.ai import run_ai
from mediatamer.signals.cast_from_subtitles import CastProfile
from mediatamer.signals.technical import TechnicalSignals
from mediatamer.signals.tmdb import fetch_tmdb_episodes
from mediatamer.signals.tvdb import fetch_tvdb_info
from mediatamer.signals.video_metadata import VideoMetadata


def extract_ovdb_info(meta: VideoMetadata, config: dict) -> VideoMetadata:
    """Extract show/season/episode information using cast profile, duration, and AI."""

    # 1. Gather show name hints from cast profile and guessit context
    cast = (
        CastProfile.from_dict(meta.cast_profile) if meta.cast_profile else CastProfile()
    )
    guessit_ctx = (meta.guessit or {}).get("context") or {}

    show_hints: List[str] = list(cast.show_name_hints)
    guessit_show = guessit_ctx.get("show")
    if guessit_show and guessit_show != "unknown" and guessit_show not in show_hints:
        show_hints.append(guessit_show)

    if not show_hints:
        print("[OVDB Extractor] No show name hints available.")
        return meta

    # 2. Determine season number from guessit context
    raw_season = guessit_ctx.get("season")
    try:
        season_number = int(raw_season) if raw_season is not None else 1
    except (ValueError, TypeError):
        season_number = 1

    # 3. Get duration from technical signals
    tech = (
        TechnicalSignals.from_dict(meta.technical)
        if isinstance(meta.technical, dict)
        else meta.technical
    )
    duration_sec: float = tech.duration if tech else 0.0

    tmdb_key = config.get("tmdb-api-key")
    tvdb_key = config.get("tvdb-api-key")

    # 4. Fetch episode candidates from TMDB and/or TVDB
    candidates: List[Dict[str, Any]] = []

    for hint in show_hints[:3]:
        print(f"[OVDB Extractor] Fetching episodes for '{hint}' S{season_number}...")
        if tmdb_key:
            resolved_name, tmdb_eps = fetch_tmdb_episodes(hint, season_number, tmdb_key)
            for ep in tmdb_eps:
                ep.setdefault("_show_name", resolved_name)
                ep.setdefault("_source", "tmdb")
                candidates.append(ep)
        if tvdb_key:
            resolved_name, tvdb_eps = fetch_tvdb_info(hint, season_number, tvdb_key)
            for ep in tvdb_eps:
                ep.setdefault("_show_name", resolved_name)
                ep.setdefault("_source", "tvdb")
                candidates.append(ep)

    if not candidates:
        print("[OVDB Extractor] No episode candidates found.")
        return meta

    # 5. Score each candidate by duration + cast overlap
    scored = _score_candidates(candidates, duration_sec, cast)
    scored.sort(key=lambda x: x["score"], reverse=True)

    # 6. Keep candidates within 50 points of the top score
    best_score = scored[0]["score"]
    top = [s for s in scored if s["score"] >= best_score - 50.0]

    # 7. Disambiguate with LLM when multiple plausible candidates remain
    if len(top) > 1 and meta.summary:
        best = _discriminate_with_llm(top, meta.summary, config)
    else:
        best = top[0]["episode"]

    meta.ovdb = {
        "show": best.get("_show_name"),
        "season": best.get("season_number"),
        "episode": best.get("episode_number"),
        "title": best.get("name"),
        "overview": best.get("overview", ""),
        "source": best.get("_source"),
    }

    print(
        f"[OVDB Extractor] Matched: {best.get('_show_name')} "
        f"S{best.get('season_number')}E{best.get('episode_number')} - {best.get('name')}"
    )
    return meta


def _score_candidates(
    candidates: List[Dict[str, Any]],
    duration_sec: float,
    cast: CastProfile,
) -> List[Dict[str, Any]]:
    """Score episode candidates by duration match and cast overlap."""
    real_actors_lower = {a.lower() for a in cast.real_actors}
    scored = []

    for ep in candidates:
        score = 0.0
        reasons: List[str] = []

        # Duration scoring
        ep_runtime = ep.get("runtime")
        if duration_sec and ep_runtime:
            diff = abs(duration_sec - ep_runtime * 60)
            if diff < 60:
                score += 100.0
                reasons.append(f"Duration match ({diff:.0f}s diff)")
            elif diff < 300:
                score += 50.0
                reasons.append(f"Loose duration match ({diff:.0f}s diff)")
            elif diff > 900:
                score -= 100.0
                reasons.append(f"Duration mismatch ({diff / 60:.1f}m diff)")

        # Cast overlap: real_actors from credits vs episode cast and guest stars
        if real_actors_lower:
            ep_cast_names = {
                (p.get("name") or "").lower()
                for p in ep.get("cast", []) + ep.get("guest_stars", [])
            }
            matches = real_actors_lower & ep_cast_names
            if matches:
                score += len(matches) * 40.0
                reasons.append(f"Cast overlap: {', '.join(list(matches)[:3])}")

        scored.append({"episode": ep, "score": score, "reasons": reasons})

    return scored


def _discriminate_with_llm(
    top: List[Dict[str, Any]],
    summary: Dict[str, Any],
    config: dict,
) -> Dict[str, Any]:
    """Use the LLM to pick the best episode from top candidates using the video summary."""
    episode_list = []
    for i, s in enumerate(top[:8]):
        ep = s["episode"]
        overview = (ep.get("overview") or "")[:300]
        episode_list.append(
            f"{i + 1}. S{ep.get('season_number')}E{ep.get('episode_number')} "
            f"'{ep.get('name')}': {overview}"
        )

    video_summary = summary.get("summary", "")
    characters = ", ".join(
        c.get("name", "") for c in summary.get("main_characters", [])
    )

    prompt = f"""You are a TV episode identification assistant. Given the synopsis extracted from a video's subtitles and a list of candidate episodes with their official overviews, identify which candidate best matches the video.

## VIDEO SYNOPSIS
{video_summary}

## MAIN CHARACTERS IN VIDEO
{characters}

## CANDIDATE EPISODES
{chr(10).join(episode_list)}

Return ONLY a JSON object with exactly two keys:
- "choice": the 1-based index of the best matching candidate (integer)
- "reasoning": one sentence explaining the match

Example: {{"choice": 2, "reasoning": "The synopsis strongly matches the overview of candidate 2."}}
"""

    response = run_ai(prompt, config, json_mode=True)
    try:
        data = json.loads(response)
        choice = max(0, min(int(data.get("choice", 1)) - 1, len(top) - 1))
        print(
            f"[OVDB Extractor] LLM picked candidate {choice + 1}: {data.get('reasoning', '')}"
        )
        return top[choice]["episode"]
    except Exception as e:
        print(f"[OVDB Extractor] LLM discrimination error: {e}")
        return top[0]["episode"]
