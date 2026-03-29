import guessit
import re
import json
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


def extract_guessit(metadata: VideoMetadata) -> None:
    """Pure guessit extraction."""
    gi_file = guessit.guessit(metadata.path.name)
    metadata.guessit = {
        "show": normalize_show_name(gi_file.get("series") or gi_file.get("title"))
        if (gi_file.get("series") or gi_file.get("title"))
        else None,
        "season": _to_int(gi_file.get("season")),
        "episode": _to_int(gi_file.get("episode") or gi_file.get("episode_number")),
        "dvd": _to_int(gi_file.get("disc")),
        "part": _to_int(gi_file.get("part")),
        "title": gi_file.get("episode_title"),
        "raw": gi_file,
    }
    if metadata.guessit["season"] is None and metadata.guessit["episode"] is None:
        metadata.guessit["type"] = "movie"
    else:
        metadata.guessit["type"] = "episode"


def extract_heuristics(metadata: VideoMetadata) -> None:
    """Heuristics analysis based on path walking."""
    first_guess: Dict[str, Any] = {
        "show": metadata.guessit.get("show"),
        "season": metadata.guessit.get("season"),
        "episode": metadata.guessit.get("episode"),
        "dvd": metadata.guessit.get("dvd"),
        "part": metadata.guessit.get("part"),
        "title": metadata.guessit.get("title"),
        "file_list": [str(f) for f in metadata.path.parent.glob("*")],
        "type": metadata.guessit.get("type", "unknown"),
    }

    # Path-walking for Context (Show, Season, DVD)
    curr = metadata.path.resolve().parent
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
        if not first_guess["show"] and series:
            first_guess["show"] = normalize_show_name(series)

        # Season logic
        if first_guess["season"] is None:
            first_guess["season"] = _to_int(gi.get("season"))

        # DVD/Disc logic
        if first_guess["dvd"] is None:
            first_guess["dvd"] = _to_int(gi.get("disc"))

        # Regex fallback for DVD ("DVD1", "Disc 2")
        if first_guess["dvd"] is None:
            m_d = re.search(r"(?:DVD|Disc|D)[._-]?(\d+)", name, re.I)
            if m_d:
                first_guess["dvd"] = int(m_d.group(1))

    # Final cleanup
    if first_guess["show"]:
        first_guess["show"] = normalize_show_name(first_guess["show"])

    # Filename series overrules path-based ones for precision if found
    f_series = metadata.guessit.get("raw", {}).get("series")
    if f_series:
        first_guess["show"] = normalize_show_name(f_series)

    metadata.heuristics = first_guess


def extract_ai_guess(metadata: VideoMetadata) -> None:
    """Ask AI for parsing."""
    ai_result_raw = run_ai(
        f"""
        You are a video metadata parser. 
        Extract the following information from this video file path:
        {metadata.path}

        Here are the results of a previous analysis:
        {metadata.heuristics}
        and the raw output of guessit:
        {metadata.guessit}

        Please analyse these data all together and correct them if needed.

        Return a JSON object with:
        - "show": (string) show name if the type is "episode"
        - "season": (int) season number
        - "episode": (int) episode number
        - "dvd": (int) disc number
        - "part": (int) part number
        - "title": (string) episode or movie title
        - "type": (string) one of ["episode", "movie", "unknown"]

        Heuristics:
        - If the path contains "S9", "DVD1", or similar, it's likely an episode or a disc of a show.
        - If the title is "B1 t00", it's likely an episode or a disc of a show.
        - If the file name is similar to "B1_t00" it is not the title of the episode or the movie it is the standard makemkv output name. So use null for the title.
        - If it's a TV show, set "type" to "episode".
        
        If a field is missing, set it to null. 
        Output ONLY a valid JSON object.
    """,
        json_mode=True,
    )

    # Trust ai output
    ai_data = json.loads(ai_result_raw)
    metadata.ai_guess = ai_data


def infer_context_from_path(metadata: VideoMetadata) -> Dict[str, Any]:
    """Robustly infer show metadata by walking up the directory tree and parsing the filename.

    Populates guessit, heuristics, and ai_guess on the metadata object.
    Returns the ai_guess dictionary as the overarching 'best' context.
    """
    extract_guessit(metadata)
    extract_heuristics(metadata)
    # extract_ai_guess(metadata)

    return metadata
