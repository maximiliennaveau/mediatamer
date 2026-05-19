"""
Run the full episode-ranking pipeline independently on TMDB and TVDB,
then compare the top-N results side by side.

Uses the cached credits_names for B2_t01.mkv (Doctor_Who_S9_DVD2, the
mismatch episode) so no OCR/AI work is needed.

Usage:
    python tmp/compare_tmdb_vs_tvdb.py
"""

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

CACHE_FILE = Path(
    "/data/videos/mediatamer_cache"
    "/39a38db272c3feabf41b8ac754d243a76b8e57350269cd807744489889b8e7fd.json"
)
TOP_N = 8  # how many ranked episodes to show per track

# ── Config ────────────────────────────────────────────────────────────────────
from mediatamer.config import load_config

config = load_config(None)
TMDB_KEY = config["tmdb-api-key"]
TVDB_KEY = config.get("tvdb-api-key")

# ── Load cached credits_names ─────────────────────────────────────────────────
cache = json.loads(CACHE_FILE.read_text())
cp = cache["cast_profile"]
people: list = cp.get("credits_names") or (
    cp.get("real_actors", []) + cp.get("crew_names", [])
)
print(f"People from cache ({len(people)}): {people}\n")

# ── TMDB track ────────────────────────────────────────────────────────────────
from mediatamer.signals.search_ovdb import MetadataMatcher

matcher = MetadataMatcher(TMDB_KEY)

print("=" * 70)
print("TMDB TRACK")
print("=" * 70)

tmdb_shows = matcher.crossreference_people(people)
if not tmdb_shows:
    print("  No TMDB show found.")
    tmdb_ranked = []
else:
    best_tmdb = tmdb_shows[0]
    print(
        f"Best show: {best_tmdb['show_name']}  id:{best_tmdb['show_id']}"
        f"  ({best_tmdb['match_count']} people)"
    )
    for p in best_tmdb["people"]:
        print(
            f"  {p['ocr_name']!r:30s} → {p['person_name']}"
            f" ({p['credit_type']}, {p['episode_count']} eps)"
        )

    path_hint = "/data/videos/unsorted-uncompressed-tv/Doctor_Who_S9_DVD2/B2_t01.mkv"
    season_hint = matcher.get_season_from_path(path_hint)
    episodes = matcher.get_show_episodes(best_tmdb["show_id"], season_hint=season_hint)
    tmdb_ranked = matcher.rank_episodes_by_cast(
        episodes, best_tmdb["people"], season_hint=season_hint
    )

    print(f"\nTop {TOP_N} episodes:")
    for ep in tmdb_ranked[:TOP_N]:
        wscore = ep.get("weighted_match_count", ep.get("match_count", 0))
        hits = ", ".join(
            f"{p['person_name']}({p['credit_type']})"
            for p in ep.get("matched_people", [])
        )
        print(
            f"  S{ep['season']:02d}E{ep['episode']:02d}"
            f" {ep['title']!r:45s}"
            f"  score={wscore} raw={ep['match_count']}"
            + (f"\n    {hits}" if hits else "")
        )

# ── TVDB track ────────────────────────────────────────────────────────────────
from mediatamer.signals.tvdb import (
    crossreference_people_tvdb,
    rank_episodes_by_tvdb_people,
    get_tvdb_episode_info,
)

print()
print("=" * 70)
print("TVDB TRACK")
print("=" * 70)

if not TVDB_KEY:
    print("  No TVDB API key configured.")
    tvdb_ranked_enriched = []
else:
    tvdb_shows = crossreference_people_tvdb(people, TVDB_KEY)
    if not tvdb_shows:
        print("  No TVDB show found.")
        tvdb_ranked_enriched = []
    else:
        best_tvdb = tvdb_shows[0]
        print(
            f"Best show: {best_tvdb['show_name']}  id:{best_tvdb['show_id']}"
            f"  ({best_tvdb['match_count']} people)"
        )
        for p in best_tvdb["people"]:
            print(
                f"  {p['ocr_name']!r:30s} → {p['person_name']}"
                f" ({p['people_type']}, char={p['character']!r})"
            )

        raw_ranked = rank_episodes_by_tvdb_people(
            best_tvdb["show_id"], best_tvdb["people"], TVDB_KEY
        )

        # Enrich with episode metadata
        tvdb_ranked_enriched = []
        for r in raw_ranked:
            info = get_tvdb_episode_info(r["episode_id"], TVDB_KEY)
            tvdb_ranked_enriched.append(
                {
                    **r,
                    "season": info["season"] if info else None,
                    "episode": info["episode"] if info else None,
                    "title": info["title"] if info else "",
                }
            )

        tvdb_ranked_enriched.sort(key=lambda x: x["match_count"], reverse=True)

        print(f"\nTop {TOP_N} episodes:")
        for ep in tvdb_ranked_enriched[:TOP_N]:
            hits = ", ".join(
                f"{p['person_name']}({p['credit_type']})"
                for p in ep.get("matched_people", [])
            )
            s = ep.get("season")
            e = ep.get("episode")
            sxe = f"S{s:02d}E{e:02d}" if s is not None and e is not None else "S??E??"
            print(
                f"  {sxe}"
                f" {ep['title']!r:45s}"
                f"  score={ep['match_count']}" + (f"\n    {hits}" if hits else "")
            )

# ── Head-to-head comparison ───────────────────────────────────────────────────
print()
print("=" * 70)
print("HEAD-TO-HEAD: top pick")
print("=" * 70)


def _top_pick(ranked, label):
    if not ranked:
        print(f"  {label}: no candidates")
        return
    best = ranked[0]
    s = best.get("season")
    e = best.get("episode")
    sxe = f"S{s:02d}E{e:02d}" if s is not None and e is not None else "S??E??"
    score = best.get("weighted_match_count", best.get("match_count", 0))
    # Strict winner?
    if len(ranked) > 1:
        second = ranked[1].get("weighted_match_count", ranked[1].get("match_count", 0))
        winner = (
            "✔ strict winner"
            if score > second
            else f"✗ TIE with {len([r for r in ranked if r.get('weighted_match_count', r.get('match_count', 0)) == score])} episode(s)"
        )
    else:
        winner = "✔ only candidate"
    print(f"  {label}: {sxe} '{best['title']}'  score={score}  {winner}")


_top_pick(tmdb_ranked if tmdb_shows else [], "TMDB")
_top_pick(tvdb_ranked_enriched, "TVDB")
print()
