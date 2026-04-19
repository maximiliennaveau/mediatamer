"""Build a metadata result set for all video files under a directory."""

from pathlib import Path
from typing import Any, Dict, List, Optional

from mediatamer.extract_metada import extract_all_metadata
from mediatamer.parameters import get_extensions
from mediatamer.signals.video_metadata import VideoMetadata


def get_tv_shows_metadata(
    input_root: Path,
    tmdb_api_key: Optional[str],
    language: str = "en-US",
    recursive: bool = True,
    sorted_dir: Optional[Path] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Run the full metadata extraction pipeline on every video file under *input_root*
    and return a result dict consumed by the organize command.

    Returns:
        {
            "files": [
                {
                    "path": str,
                    "show_detected": str | None,
                    "season_detected": int | None,
                    "episode_detected": int | None,
                    "selected_episode": dict | None,  # TMDB episode record from ai_match
                },
                ...
            ]
        }
    """
    from mediatamer.config import load_config

    config = load_config()
    if tmdb_api_key:
        config["tmdb-api-key"] = tmdb_api_key

    extensions = get_extensions()
    pattern = "**/*" if recursive else "*"
    video_files = [
        f
        for f in input_root.glob(pattern)
        if f.is_file() and f.suffix.lower() in extensions
    ]

    entries: List[Dict[str, Any]] = []
    for video_path in sorted(video_files):
        print(f"[Organize] Processing {video_path.name}...")
        metadata = VideoMetadata(path=video_path)
        try:
            metadata = extract_all_metadata(metadata, config)
        except Exception as e:
            print(f"[Organize] Failed to extract metadata for {video_path.name}: {e}")

        ai_match = metadata.ai_match or {}
        heuristics = metadata.heuristics or {}

        show = ai_match.get("show") or heuristics.get("show")
        season = ai_match.get("season") or heuristics.get("season")
        episode = ai_match.get("episode") or heuristics.get("episode")
        selected_episode = ai_match.get("best_candidate")
        if selected_episode is None and ai_match.get("title"):
            selected_episode = {"name": ai_match["title"]}

        entries.append(
            {
                "path": str(video_path),
                "show_detected": show,
                "season_detected": season,
                "episode_detected": episode,
                "selected_episode": selected_episode,
            }
        )

    return {"files": entries}
