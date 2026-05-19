"""
Compare the cached (AI-produced) cast profile for B2_t01.mkv
against a fresh run of the deterministic heuristic extractor
on the same cached OCR filtered_text.

Usage:
    python tmp/compare_cast_profile.py
"""

import json
import sys
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

CACHE_FILE = Path(
    "/data/videos/mediatamer_cache"
    "/39a38db272c3feabf41b8ac754d243a76b8e57350269cd807744489889b8e7fd.json"
)

# ── Load cache ─────────────────────────────────────────────────────────────────
cache = json.loads(CACHE_FILE.read_text())
cast_profile = cache["cast_profile"]
filtered_text = cast_profile["ocr_cache"]["filtered_text"]

# Backward compat: old cache uses real_actors + crew_names
cached_names = cast_profile.get("credits_names") or (
    cast_profile.get("real_actors", []) + cast_profile.get("crew_names", [])
)
cached_chars = cast_profile.get("fictional_characters", [])

# ── Run heuristic extractor on the same filtered_text ─────────────────────────
from mediatamer.signals.credits_extractor import VideoCreditsExtractor

extractor = VideoCreditsExtractor(config={})
heuristic = extractor._extract_with_heuristics(filtered_text)
heur_names = heuristic.get("credits_names", [])

# Simulate the union (same logic as the updated extract() method)
seen: set = set()
union_names = []
for name in heur_names + cached_names:
    key = name.lower()
    if key not in seen:
        seen.add(key)
        union_names.append(name)


# ── Pretty diff helper ─────────────────────────────────────────────────────────
def _compare(label: str, cached: list, heuristic: list) -> None:
    cached_set = {n.lower() for n in cached}
    heur_set = {n.lower() for n in heuristic}

    only_cached = sorted(n for n in cached if n.lower() not in heur_set)
    only_heur = sorted(n for n in heuristic if n.lower() not in cached_set)
    common = sorted(n for n in cached if n.lower() in heur_set)

    print(f"\n{'═' * 60}")
    print(f"  {label}")
    print(f"{'═' * 60}")
    print(
        f"  Cached     : {len(cached):3d}  |  Heuristic: {len(heuristic):3d}  |  Common: {len(common):3d}"
    )

    if common:
        print(f"\n  ✔ Common ({len(common)}):")
        for n in common:
            print(f"      {n}")

    if only_cached:
        print(f"\n  ← Only in CACHE (AI-produced, {len(only_cached)}):")
        for n in only_cached:
            print(f"      {n}")

    if only_heur:
        print(f"\n  → Only in HEURISTIC ({len(only_heur)}):")
        for n in only_heur:
            print(f"      {n}")


# ── Print heuristic compact text for inspection ────────────────────────────────
print("\n" + "═" * 60)
print("  HEURISTIC COMPACT TEXT (sent to AI as pre-filter)")
print("═" * 60)
compact = heuristic.get("_compact_text", "")
if compact.strip():
    for line in compact.splitlines():
        print(f"  {line}")
else:
    print("  (empty)")

# ── Side-by-side comparison ────────────────────────────────────────────────────
_compare("CACHED (AI only)", cached_names, heur_names)
_compare("HEURISTIC only", heur_names, cached_names)
_compare("UNION vs CACHED", union_names, cached_names)

# Characters are only from AI; show them for reference
print(f"\n{'═' * 60}")
print(f"  FICTIONAL CHARACTERS (AI only)")
print(f"{'═' * 60}")
for c in sorted(cached_chars):
    print(f"  {c}")

print()
