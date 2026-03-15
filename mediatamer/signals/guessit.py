import guessit
import re
from pathlib import Path
from typing import Dict, Any, Optional

from mediatamer.ai import run_ai
from mediatamer.utils import normalize_show_name
from mediatamer.signals.video_metadata import VideoMetadata


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


def infer_context_from_path(metadata: VideoMetadata) -> Dict[str, Any]:
    """Robustly infer show metadata by walking up the directory tree and parsing the filename.

    Returns a dictionary with:
        - show: Optional[str]
        - season: Optional[int]
        - episode: Optional[int]
        - dvd: Optional[int] (disc number)
        - part: Optional[int] (part number)
        - title: Optional[str] (episode title)
        - guessit: Dict[str, Any] (raw guessit result)
    """
    out = {
        "show": None,
        "season": None,
        "episode": None,
        "dvd": None,
        "part": None,
        "title": None,
        "guessit": {},
    }

    # 1. Filename-specific parsing.
    file_path = metadata.path
    gi_file = guessit.guessit(file_path.name)

    out["episode"] = _to_int(gi_file.get("episode") or gi_file.get("episode_number"))
    out["season"] = _to_int(gi_file.get("season"))
    out["dvd"] = _to_int(gi_file.get("disc"))
    out["part"] = _to_int(gi_file.get("part"))
    out["title"] = gi_file.get("episode_title")
    out["confidence"] = float(gi_file.get("confidence", 0.0))
    out["guessit"] = gi_file

    # 2. Path-walking for Context (Show, Season, DVD)
    curr = file_path.resolve().parent
    limit = Path("/")

    path_parts = []
    tmp = curr
    while tmp != limit and tmp != tmp.parent:
        path_parts.append(tmp)
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

    run_ai(f"""
        You are a video metadata parser.
        You are given a video file path and you need to extract the show name, season, episode, dvd, part and title if possible.
        Find below the reusult of a pre-analysis from the sofware guessit:
        {gi_file}

        Here is the path to analyse:
        {file_path}

        The output format must be a json object with the following keys:
        - show: Optional[str]
        - season: Optional[int]
        - episode: Optional[int]
        - dvd: Optional[int]
        - part: Optional[int]
        - title: Optional[str]
        - confidence: Optional[float]
        - guessit: Dict[str, Any]

        You can use the guessit output but it is not always correct, so use your best judgement.
        Return only the json object.
    """)

    metadata.guessit = out
    return out
