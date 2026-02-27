import guessit
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from mediatamer.utils import normalize_show_name


def infer_context_from_path(
    file_path: Path, root_path: Optional[Path] = None
) -> Tuple[Optional[str], Optional[int], Optional[int]]:
    """Infer Show Name, Season and DVD by walking up the directory tree.

    Returns: (show_name, season_number, dvd_number)
    """
    show_name = None
    season_number = None
    dvd_number = None

    # Resolve paths
    curr = file_path.resolve().parent
    root = root_path.resolve() if root_path else None
    limit = root.parent if root else Path("/")

    path_parts = []
    tmp = curr
    while tmp != limit and tmp != tmp.parent:
        path_parts.append(tmp)
        if root and tmp == root:
            break
        tmp = tmp.parent

    # Search from deepest to shallowest
    for d in path_parts:
        name = d.name
        gi = guessit.guessit(name)

        # 1. Show Name
        series = gi.get("series") or gi.get("title")
        if not show_name and series:
            show_name = normalize_show_name(series)

        # 2. Season Number
        s = gi.get("season")
        if season_number is None and s is not None:
            season_number = int(s)

        # 3. DVD Number (often mapped to 'disc' in guessit or found via regex fallback)
        d_num = gi.get("disc")
        if dvd_number is None and d_num is not None:
            dvd_number = int(d_num)

        # Fallback for DVD if guessit didn't catch it (common for "DVD1" folder names)
        if dvd_number is None:
            import re

            m_d = re.search(r"(?:DVD|Disc|D)[._-]?(\d+)", name, re.I)
            if m_d:
                dvd_number = int(m_d.group(1))

        # If we have show name and season, we can stop early if it's the deepest part,
        # but usually we want to keep going to find show name if season was found in a subfolder.
        if show_name and season_number is not None:
            # If we found season in a folder, the show name should be in the parent
            pass

    show_name = normalize_show_name(show_name)

    return show_name, season_number, dvd_number


def extract_from_guessit(path: Path) -> Dict[str, Any]:
    """Parse filename and parent folders to produce candidate metadata.

    This is a lightweight wrapper that tries to extract show, season and
    episode from the filename/path.
    """
    out = {
        "show": None,
        "season": None,
        "episode": None,
        "episode_is_explicit": False,
        "title": None,
        "source": "filename",
        "confidence": 0.0,
    }

    # Use just the filename part for guessit to avoid path-based confusion
    # but include parent folder name if possible for context
    if path.parent and path.parent.name:
        name = f"{path.parent.name}_{path.name}"
    else:
        name = path.name

    gi = guessit.guessit(name)
    out["show"] = gi.get("series") or gi.get("title")
    out["season"] = gi.get("season")
    out["episode"] = None
    # guessit can return episode/numeric or episodes list
    ep = gi.get("episode") or gi.get("episode_number")
    if isinstance(ep, (list, tuple)) and ep:
        out["episode"] = ep[0]
    elif ep:
        out["episode"] = ep
    out["episode_is_explicit"] = True if out["episode"] else False
    out["title"] = gi.get("episode_title") or gi.get("title")
    out["confidence"] = (
        float(gi.get("confidence", 0.0)) if gi.get("confidence") is not None else 0.0
    )
    out["source"] = "guessit"
    return out
