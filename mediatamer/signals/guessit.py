import guessit
import re
import json
from pathlib import Path
from typing import Dict, Any, Optional, List

from mediatamer.ai import run_ai
from mediatamer.utils import normalize_show_name
from mediatamer.signals.video_metadata import VideoMetadata


# MakeMKV output filename pattern: e.g. B2_t04.mkv, A1_t00.mkv
_MAKEMKV_PATTERN = re.compile(r"^[A-Za-z]\d+_t\d+", re.IGNORECASE)

# Common video extensions — self-contained to avoid circular imports.
_VIDEO_EXTS = frozenset(
    {".mkv", ".mp4", ".avi", ".m4v", ".mov", ".ts", ".mpg", ".mpeg", ".wmv"}
)


def _is_makemkv_filename(filename: str) -> bool:
    """Return True if the filename is a raw MakeMKV output (e.g. B2_t04.mkv)."""
    return bool(_MAKEMKV_PATTERN.match(Path(filename).stem))


def _to_int(val: Any) -> Optional[int]:
    """Helper to convert guessit result (possibly list) to int."""
    if val is None:
        return "unknown"
    if isinstance(val, (list, tuple)) and val:
        val = val[0]
    try:
        return int(val)
    except (ValueError, TypeError):
        return "unknown"


# ── MakeMKV disc analysis helpers ────────────────────────────────────────────


def _parse_makemkv_stem(stem: str) -> Optional[Dict[str, Any]]:
    """Parse a MakeMKV title stem like 'B2_t01' into its components.

    Returns:
        {letter, track_in_group (1-indexed ordinal within group),
         global_track (physical title index on the disc)}
    """
    m = re.match(r"^([A-Za-z])(\d+)_t(\d+)$", stem.strip(), re.IGNORECASE)
    if not m:
        return None
    return {
        "letter": m.group(1).upper(),
        "track_in_group": int(m.group(2)),
        "global_track": int(m.group(3)),
    }


def _scan_letter_groups(folder: Path) -> Dict[str, List[Dict[str, Any]]]:
    """Scan a folder and group all MakeMKV files by their letter prefix.

    Each entry includes the parsed track fields plus the file size in bytes,
    used later to discriminate episodes from bonus content.
    Returns a dict mapping letter -> list of track dicts.
    """
    groups: Dict[str, List[Dict[str, Any]]] = {}
    if not folder.is_dir():
        return groups
    for f in folder.iterdir():
        if not f.is_file() or f.suffix.lower() not in _VIDEO_EXTS:
            continue
        parsed = _parse_makemkv_stem(f.stem)
        if parsed:
            parsed["size_bytes"] = f.stat().st_size
            groups.setdefault(parsed["letter"], []).append(parsed)
    return groups


def _episode_letter_from_groups(
    letter_groups: Dict[str, List[Dict[str, Any]]],
) -> Optional[str]:
    """Return the letter group that represents main episodes.

    Episodes are substantially larger files than bonus/extra content.
    We use mean file size per group as the primary discriminator — it is
    reliable, free (no subprocess needed), and handles cases where MakeMKV
    assigns lower global_track numbers to bonus content.

    When only one group exists, it is trivially the episode group.
    When two groups have very similar mean sizes (within 20%), we fall back
    to the global_track tiebreaker (lowest starting track = episodes).
    """
    if not letter_groups:
        return None
    if len(letter_groups) == 1:
        return next(iter(letter_groups))

    def mean_size(grp: str) -> float:
        sizes = [t["size_bytes"] for t in letter_groups[grp]]
        return sum(sizes) / len(sizes)

    means = {grp: mean_size(grp) for grp in letter_groups}
    best = max(means, key=means.get)
    second = max((g for g in means if g != best), key=means.get)

    # If the largest group is at least 5x bigger than the next, it's unambiguous.
    if means[best] >= means[second] * 5:
        return best

    # Sizes are ambiguous (within 5x) — fall back to lowest global_track start.
    return min(
        letter_groups,
        key=lambda grp: min(t["global_track"] for t in letter_groups[grp]),
    )


def _count_episode_files_in_folder(folder: Path) -> int:
    """Return the number of main episode files in a MakeMKV rip folder."""
    groups = _scan_letter_groups(folder)
    ep_letter = _episode_letter_from_groups(groups)
    return len(groups.get(ep_letter, [])) if ep_letter else 0


def _parse_folder_disc_number(folder_name: str) -> Optional[int]:
    """Extract DVD/disc number from a folder name.

    Handles patterns like: DVD1, Disc2, _D4 (trailing single-letter D).
    """
    # Priority 1: explicit DVD or Disc prefix  e.g. DVD1, Disc2
    m = re.search(r"(?:DVD|Disc)[_\s]?(\d+)", folder_name, re.IGNORECASE)
    if m:
        return int(m.group(1))
    # Priority 2: trailing _D\d+ pattern  e.g. _D4 at end or before underscore
    m = re.search(r"(?:_|^)D(\d+)(?:[_\s]|$)", folder_name, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return None


def _parse_folder_season(folder_name: str) -> Optional[int]:
    """Extract season number from a folder name.

    Handles: S10, S9, Season 01, etc.
    """
    m = re.search(
        r"(?:Season[_\s]?|(?<![A-Za-z])S)(\d{1,2})(?:[_\s\.]|$)",
        folder_name,
        re.IGNORECASE,
    )
    if m:
        return int(m.group(1))
    return None


def _analyze_disc_context(video_path: Path) -> Optional[Dict[str, Any]]:
    """Full DVD disc analysis for a MakeMKV rip file.

    Computes:
    - Which letter group = main episodes vs bonus/extras
    - This file's role (episode or bonus) and 1-indexed position on the disc
    - Episode offset from prior discs in the same season (by scanning sibling folders)
    - Estimated season episode number and probable episode range for this disc

    Returns None if the file does not match the MakeMKV naming pattern or if the
    folder contains no recognisable MakeMKV siblings.
    """
    folder = video_path.parent
    stem = video_path.stem

    this_parsed = _parse_makemkv_stem(stem)
    if not this_parsed:
        return None

    this_letter = this_parsed["letter"]
    this_track_in_group = this_parsed["track_in_group"]
    this_global_track = this_parsed["global_track"]

    # ── 1. Analyse all sibling MakeMKV files on this disc ────────────────────
    letter_groups = _scan_letter_groups(folder)
    if not letter_groups:
        return None

    episode_letter = _episode_letter_from_groups(letter_groups)
    bonus_letters = sorted(grp for grp in letter_groups if grp != episode_letter)

    disc_episode_count = len(letter_groups[episode_letter])
    disc_bonus_count = sum(len(letter_groups[grp]) for grp in bonus_letters)

    is_episode = this_letter == episode_letter
    is_bonus = not is_episode

    # Position within episode group — track_in_group is 1-indexed and sequential
    disc_position: Optional[int] = this_track_in_group if is_episode else None

    # ── 2. Parse disc number and season from the folder name ─────────────────
    dvd_number = _parse_folder_disc_number(folder.name)
    folder_season = _parse_folder_season(folder.name)

    # ── 3. Count episodes on prior discs to establish season episode offset ──
    episode_offset = 0
    prior_dvds_analyzed: List[int] = []
    total_discs_found = 1  # at minimum this disc
    offset_is_exact = False

    if dvd_number is not None and folder_season is not None:
        parent = folder.parent
        for sibling in parent.iterdir():
            if not sibling.is_dir() or sibling == folder:
                continue
            sib_dvd = _parse_folder_disc_number(sibling.name)
            sib_season = _parse_folder_season(sibling.name)
            if sib_dvd is None or sib_season != folder_season:
                continue
            total_discs_found += 1
            if sib_dvd < dvd_number:
                ep_count = _count_episode_files_in_folder(sibling)
                episode_offset += ep_count
                prior_dvds_analyzed.append(sib_dvd)

        prior_dvds_analyzed.sort()
        # Offset is exact when every disc numbered 1..(dvd_number-1) was found
        offset_is_exact = prior_dvds_analyzed == list(range(1, dvd_number))

    # ── 4. Derive estimated episode number for this file ─────────────────────
    estimated_episode_number: Optional[int] = None
    estimated_episode_range: List[int] = []
    if is_episode and disc_position is not None:
        estimated_episode_number = episode_offset + disc_position
        estimated_episode_range = list(
            range(episode_offset + 1, episode_offset + disc_episode_count + 1)
        )

    return {
        # Disc letter classification
        "episode_letter": episode_letter,
        "bonus_letters": bonus_letters,
        # This file's role
        "is_episode": is_episode,
        "is_bonus": is_bonus,
        # Position information
        "disc_position": disc_position,
        "disc_episode_count": disc_episode_count,
        "disc_bonus_count": disc_bonus_count,
        "this_letter": this_letter,
        "this_track_in_group": this_track_in_group,
        "this_global_track": this_global_track,
        # Season / disc context
        "dvd_number": dvd_number,
        "folder_season": folder_season,
        "total_discs_found": total_discs_found,
        "prior_dvds_analyzed": prior_dvds_analyzed,
        "episode_offset": episode_offset,
        "offset_is_exact": offset_is_exact,
        # Search targets
        "estimated_episode_number": estimated_episode_number,
        "estimated_episode_range": estimated_episode_range,
    }


def _extract_guessit(metadata: VideoMetadata) -> None:
    """Pure guessit extraction.

    When the filename matches the MakeMKV output pattern (e.g. B2_t04.mkv),
    all filename-derived fields are set to None to avoid injecting noise into
    the pipeline. Context will be recovered by path-walking in extract_heuristics().
    """
    gi = guessit.guessit(metadata.path.name, options={"type": "episode"})

    # Normalize output.
    res = {
        "show": gi.get("series") or gi.get("title") or "unknown",
        "season": gi.get("season"),
        "episode": None,
        "episode_list": [],
        "disc": gi.get("disc") or gi.get("cd"),
        "title": gi.get("episode_title"),
        "is_special": False,
    }

    # Multi-episode handling.
    ep = gi.get("episode")
    if isinstance(ep, list):
        res["episode"] = ep[0]
        res["episode_list"] = ep
    elif ep:
        res["episode"] = ep
        res["episode_list"] = [ep]

    # 3. FALLBACK : Si la saison est absente (cas typique de B2_t01.mkv)
    # On cherche dans le chemin complet (ex: .../Doctor_Who_S9_DVD1/...)
    if res["season"] is None:
        # Regex pour capturer S09, Season 9, etc.
        path_match = re.search(r"[sS]eason_?(\d+)|[sS](\d+)", str(metadata.path))
        if path_match:
            res["season"] = int(path_match.group(1) or path_match.group(2))

    # 4. Détection des épisodes Spéciaux
    if res["season"] == 0 or "special" in metadata.path.name.lower():
        res["is_special"] = True

    metadata.guessit["guessit"] = res


def _extract_heuristics(metadata: VideoMetadata) -> None:
    """Heuristics analysis based on path walking and, for MakeMKV rips, disc
    structure analysis.

    For well-named files guessit output seeds the result, then parent directories
    are walked to fill any gaps.

    For MakeMKV rips (e.g. B2_t01.mkv) the filename contributes nothing useful;
    context is recovered from the folder name (show, season, DVD number) and from
    sibling-folder counting to estimate the season episode number.
    """
    heuristics = {}
    # Exctract show name and season from parent folder
    parent = metadata.path.parent
    heuristics["show"] = normalize_show_name(parent.name)
    heuristics["season"] = _parse_folder_season(parent.name)

    # ── MakeMKV disc analysis ────────────────────────────────────────────────
    disc = _analyze_disc_context(metadata.path)
    if disc:
        heuristics["disc_analysis"] = disc

        # Promote disc-derived season to top level if not found via path walking
        if heuristics.get("season") is None and disc.get("folder_season"):
            heuristics["season"] = disc["folder_season"]

        # Promote disc-derived DVD number to top level
        if heuristics.get("dvd") is None and disc.get("dvd_number"):
            heuristics["dvd"] = disc["dvd_number"]

        # For main episodes, expose estimated episode at top level so the
        # agent can pick it up immediately without digging into disc_analysis
        if disc.get("is_episode") and disc.get("estimated_episode_number"):
            heuristics["episode"] = disc["estimated_episode_number"]

        # Bonus/extra files belong in Season 0 by convention
        if disc.get("is_bonus"):
            heuristics["is_episode"] = False
            heuristics["type"] = "bonus"

    metadata.guessit["heuristics"] = heuristics


def _build_best_context_with_ai(
    metadata: VideoMetadata, config: dict
) -> Dict[str, Any]:
    """Merge guessit, heuristics, and disc_analysis into a single flat context
    object for the agentic AI.

    Every field carries a 'source' string so the AI knows how much to trust it:

    - ``"filename"``      : parsed directly from the filename (guessit) — high confidence
    - ``"path_folder"``   : inferred from a parent directory name — medium confidence
    - ``"disc_analysis_high"`` : MakeMKV disc position + all prior discs found
    - ``"disc_analysis_medium"``: MakeMKV disc position, some prior discs missing
    - ``"unknown"``       : not found — agent should search broadly

    The returned dict is also stored as ``metadata.heuristics["context"]``.
    """
    prompt = f"""
Given the following information extracted from the filename and path of a video file.
Determine the most likely show name, season number, episode number, and whether it's a bonus/extra episode.

Metadata extracted analytically:
{metadata.guessit}

The results is a json object with the following fields:
- show: the inferred show name, or null if unknown
- season: the inferred season number, or null if unknown
- episode: the inferred episode number, or null if unknown
- type: "episode", "movie", "bonus", or "unknown"
- source: one of "filename", "path_folder", "disc_analysis_high", "disc_analysis_medium", or "unknown" indicating the source of the inference and confidence level
- confidence: a confidence level from 0 to 100 based on the source and consistency.
"""
    print(
        "[guessit AI]",
        "Running AI to merge guessit and heuristics into final context.",
        f"Prompt:\n{prompt}",
    )
    response = run_ai(prompt, config, json_mode=True)
    try:
        ctx: Dict[str, Any] = json.loads(response)
    except Exception as e:
        print(f"[guessit AI] LLM discrimination error: {e}")
        ctx: Dict[str, Any] = {}

    metadata.guessit["context"] = ctx


# ── Main extraction functions ────────────────────────────────────────────────


def infer_context_from_path(metadata: VideoMetadata, config: dict) -> Dict[str, Any]:
    """Robustly infer show metadata by walking up the directory tree and
    parsing the filename.

    For MakeMKV rips, additionally performs full disc analysis to estimate the
    season episode number from disc position and sibling DVD folders.

    Populates guessit, heuristics (and optionally ai_guess) on the metadata
    object.
    """
    metadata.guessit = {}
    metadata.guessit["is_makemkv"] = _is_makemkv_filename(metadata.path.name)
    _extract_guessit(metadata)

    return metadata
