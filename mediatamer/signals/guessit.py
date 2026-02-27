import guessit
import re
from pathlib import Path
from typing import Dict, Any, Optional
from mediatamer.utils import normalize_show_name


def _to_int(val: Any) -> Optional[int]:
    """Helper to convert guessit result (possibly list) to int."""
    if val is None:
        return None
    if isinstance(val, (list, tuple)) and val:
        val = val[0]
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def infer_context_from_path(
    file_path: Path, root_path: Optional[Path] = None
) -> Dict[str, Any]:
    """Robustly infer show metadata by walking up the directory tree and parsing the filename.

    Returns a dictionary with:
        - show: Optional[str]
        - season: Optional[int]
        - episode: Optional[int]
        - dvd: Optional[int] (disc number)
        - part: Optional[int] (part number)
        - title: Optional[str] (episode title)
        - confidence: float
    """
    out = {
        "show": None,
        "season": None,
        "episode": None,
        "dvd": None,
        "part": None,
        "title": None,
        "confidence": 0.0,
    }

    # 1. Filename-specific parsing (Highest precision for Episode/Title/Part)
    gi_file = guessit.guessit(file_path.name)

    out["episode"] = _to_int(gi_file.get("episode") or gi_file.get("episode_number"))
    out["season"] = _to_int(gi_file.get("season"))
    out["dvd"] = _to_int(gi_file.get("disc"))
    out["part"] = _to_int(gi_file.get("part"))
    out["title"] = gi_file.get("episode_title")
    out["confidence"] = float(gi_file.get("confidence", 0.0))

    # 2. Path-walking for Context (Show, Season, DVD)
    curr = file_path.resolve().parent
    root = root_path.resolve() if root_path else None
    # Don't walk above root if provided, otherwise stop at /
    limit = root.parent if root else Path("/")

    path_parts = []
    tmp = curr
    while tmp != limit and tmp != tmp.parent:
        path_parts.append(tmp)
        if root and tmp == root:
            break
        tmp = tmp.parent

    # Search from deepest (subfolder) to shallowest (show folder)
    for d in path_parts:
        name = d.name
        gi = guessit.guessit(name)

        # Show Name logic
        series = gi.get("series") or gi.get("title")
        if not out["show"] and series:
            out["show"] = normalize_show_name(series)

        # Season logic
        if out["season"] is None:
            out["season"] = _to_int(gi.get("season"))

        # DVD/Disc logic
        if out["dvd"] is None:
            out["dvd"] = _to_int(gi.get("disc"))

        # Regex fallback for DVD ("DVD1", "Disc 2")
        if out["dvd"] is None:
            m_d = re.search(r"(?:DVD|Disc|D)[._-]?(\d+)", name, re.I)
            if m_d:
                out["dvd"] = int(m_d.group(1))

    # Final cleanup
    if out["show"]:
        out["show"] = normalize_show_name(out["show"])

    # Filename series overrules path-based ones for precision if found
    f_series = gi_file.get("series")
    if f_series:
        out["show"] = normalize_show_name(f_series)

    return out
