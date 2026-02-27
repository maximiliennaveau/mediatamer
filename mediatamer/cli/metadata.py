"""Extract MKV metadata (MediaTamer packaged module)."""

from pathlib import Path
import argparse
import json
import subprocess
import csv
import re
from typing import Dict, Any, List, Tuple, Optional
import requests

from mediatamer.parameters import get_extensions
from mediatamer.utils import normalize_show_name
from mediatamer.ai_matcher import HolisticAIMatcher
from mediatamer.signals.cache import get_or_create_metadata


SE_EP_PATTERNS = [
    re.compile(
        r"[Ss](?P<season>\d{1,2})[ ._-]?[Ee](?P<ep1>\d{1,2})(?:[ ._-]*[-–—&][ ._-]*(?P<ep2>\d{1,2}))?"
    ),
    re.compile(r"(?P<season>\d{1,2})[xX](?P<ep1>\d{1,2})(?:[-](?P<ep2>\d{1,2}))?"),
    re.compile(
        r"[Ss]eason[ ._-]?(?P<season>\d{1,2}).*?[Ee]p(?:isode)?[ ._-]?(?P<ep1>\d{1,2})(?:[ ._-]*[-–—&][ ._-]*(?P<ep2>\d{1,2}))?",
        re.I,
    ),
    re.compile(
        r"\b[Ee]p(?:isode)?[ ._-]?(?P<ep1>\d{1,2})(?:[ ._-]*[-–—&][ ._-]*(?P<ep2>\d{1,2}))?\b"
    ),
    re.compile(r"\b(?P<ep1>\d{2})[-–—](?P<ep2>\d{2})\b"),
    re.compile(r"\b(?P<ep1>\d{2})\b"),
    # DVD track patterns: t00, t01, etc.
    re.compile(r"[tT](?P<ep1>\d{1,2})"),
    # B1_t00, C2_t04 patterns (disc_track)
    re.compile(r"[A-Z]\d+_[tT](?P<ep1>\d{1,2})"),
]

SEASON_ONLY_PAT = re.compile(
    r"[Ss](?P<season>\d{1,2})|Season[ ._-]?(?P<season2>\d{1,2})", re.I
)


def extract_se_ep_from_name(
    name: str,
) -> Tuple[Optional[int], Optional[int], Optional[int]]:
    """Extract season and episode numbers from filename."""
    lname = name
    for pat in SE_EP_PATTERNS:
        m = pat.search(lname)
        if m:
            gd = m.groupdict()
            season = None
            if "season" in gd and gd.get("season"):
                try:
                    season = int(gd.get("season"))
                except Exception:
                    season = None
            ep1 = None
            ep2 = None
            if gd.get("ep1"):
                try:
                    ep1 = int(gd.get("ep1"))
                except Exception:
                    ep1 = None
            if gd.get("ep2"):
                try:
                    ep2 = int(gd.get("ep2"))
                except Exception:
                    ep2 = None

            # Special handling for DVD track patterns that don't have season info
            if not season and not gd.get("season") and ep1 is not None:
                # For patterns like t00, B1_t00, DVD tracks are typically 0-indexed but episodes are 1-indexed
                # So t00 -> episode 1, t01 -> episode 2, etc.
                ep1 += 1

            if ep1 is not None:
                return (season, ep1, ep2)

    # Handle special episodes
    if re.search(r"\b(special|sp|bonus|extra|ova|feature)\b", lname, re.I):
        m = re.search(r"(?:special|sp)[^0-9]*(\d{1,2})", lname, re.I)
        ep = int(m.group(1)) if m else None
        return (0, ep, None)

    return (None, None, None)


def extract_season_only(name: str) -> Optional[int]:
    """Extract season number from directory name."""
    m = SEASON_ONLY_PAT.search(name)
    if m:
        season = m.groupdict().get("season") or m.groupdict().get("season2")
        if season:
            return int(season)
    return None


def find_parent_show_and_season(
    file_path: Path, input_root: Path
) -> Tuple[str, Optional[int]]:
    """Find show name and season from file path relative to input root."""
    # Find the show directory (parent of season directories)
    show_dir = None
    season = None

    # Walk backwards from the file to find season and show
    current = file_path.parent
    while current != input_root and current != current.parent:
        dir_name = current.name

        # Skip the file's own directory if it's not a season
        if current == file_path.parent and not extract_season_only(dir_name):
            current = current.parent
            continue

        # Check if this directory name contains both show and season info
        # Patterns like "DOCTOR_WHO_S10_D1", "Doctor_Who_S9_DVD1", etc.
        show_season_match = re.search(r"(.+?)_?[sS](\d+)", dir_name, re.I)
        if show_season_match:
            potential_show = show_season_match.group(1).replace("_", " ")
            potential_season = int(show_season_match.group(2))

            # Clean up the show name
            potential_show = normalize_show_name(potential_show)

            if not show_dir:
                show_dir = potential_show
            if not season:
                season = potential_season
            break

        # Check if this is a season directory
        if not season:
            season = extract_season_only(dir_name)
            if season:
                # The parent of a season directory should be the show
                show_parent = current.parent
                if show_parent != input_root:
                    show_dir = show_parent.name
                else:
                    # If show_parent == input_root, then input_root is the show directory
                    show_dir = input_root.name

        current = current.parent

    # If we didn't find season in directory names, try filename
    if not season:
        _, season, _ = extract_se_ep_from_name(file_path.name)

    # Fallback for show name
    if not show_dir:
        # Look for a directory that doesn't look like a season
        candidates = []
        current = file_path.parent
        while current != input_root and current != current.parent:
            dir_name = current.name
            if not extract_season_only(dir_name) and dir_name.lower() not in [
                "tv-shows",
                "tv_shows",
                "shows",
                "series",
                "movies",
                "films",
                "videos",
                "media",
                "unsorted_videos",
                "unsorted",
            ]:
                candidates.append(dir_name)
            current = current.parent
        if candidates:
            show_dir = candidates[-1]  # Take the highest level candidate

    show_guess = normalize_show_name(show_dir) if show_dir else "Unknown Show"

    return show_guess, season


def parse_special_season(name: str) -> Optional[float]:
    """Parse special season numbers like 4.5 for episodes between seasons."""
    # Look for patterns like "4.5", "S4.5", "Season 4.5"
    m = re.search(r"[Ss]eason\s*(\d+)\.(\d+)", name, re.I)
    if m:
        major = int(m.group(1))
        minor = int(m.group(2))
        return major + minor / 10

    m = re.search(r"[Ss](\d+)\.(\d+)", name, re.I)
    if m:
        major = int(m.group(1))
        minor = int(m.group(2))
        return major + minor / 10

    return None


def lookup_episode_info(
    show_name: str,
    season: int,
    episode: int,
    api_key: str = None,
    language: str = "en-US",
):
    """Look up episode information from TMDB API."""
    if not requests:
        print("Warning: requests not available, skipping web lookup")
        return None

    if not api_key:
        print(
            "Warning: No TMDB API key provided. Get one at https://www.themoviedb.org/settings/api and use --tmdb-api-key"
        )
        return None

    try:
        # First, search for the TV show
        search_url = "https://api.themoviedb.org/3/search/tv"
        params = {
            "api_key": api_key,
            "query": show_name,
            "first_air_date_year": None,  # Could be enhanced to filter by year
            "language": language,
        }
        response = requests.get(search_url, params=params, timeout=10)
        response.raise_for_status()
        search_results = response.json()

        if not search_results.get("results"):
            print(f"Warning: No TV show found for '{show_name}'")
            return None

        # Take the first (most popular) result
        show_id = search_results["results"][0]["id"]
        show_title = search_results["results"][0]["name"]

        # Get episode details
        episode_url = f"https://api.themoviedb.org/3/tv/{show_id}/season/{season}/episode/{episode}"
        params = {"api_key": api_key, "language": language}
        response = requests.get(episode_url, params=params, timeout=10)
        response.raise_for_status()
        episode_data = response.json()

        return {
            "title": episode_data.get("name", ""),
            "overview": episode_data.get("overview", ""),
            "air_date": episode_data.get("air_date", ""),
            "episode_number": episode_data.get("episode_number"),
            "season_number": episode_data.get("season_number"),
            "show_name": show_title,
        }

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            print(
                "Warning: Invalid TMDB API key. Get one at https://www.themoviedb.org/settings/api"
            )
        else:
            print(f"Warning: TMDB API error: {e}")
        return None
    except Exception as e:
        print(
            f"Warning: Failed to lookup episode info for {show_name} S{season:02d}E{episode:02d}: {e}"
        )
        return None


def check_ffprobe():
    from shutil import which

    if which("ffprobe") is None:
        raise SystemExit("ffprobe not found in PATH. Install ffmpeg.")


def ffprobe_json(path: Path) -> Dict[str, Any]:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {path}: {res.stderr.strip()}")
    return json.loads(res.stdout)


def stream_info_summary(stream: Dict[str, Any]) -> Dict[str, Any]:
    info = {}
    info["index"] = stream.get("index")
    info["codec_name"] = stream.get("codec_name")
    info["codec_long_name"] = stream.get("codec_long_name")
    info["type"] = stream.get("codec_type")
    info["language"] = (
        stream.get("tags", {}).get("language") if stream.get("tags") else None
    )
    info["title"] = stream.get("tags", {}).get("title") if stream.get("tags") else None
    if stream.get("codec_type") == "video":
        info["width"] = stream.get("width")
        info["height"] = stream.get("height")
        fr = stream.get("r_frame_rate") or stream.get("avg_frame_rate") or "0/1"
        try:
            num, den = fr.split("/")
            info["frame_rate"] = float(num) / float(den) if float(den) != 0 else None
        except Exception:
            info["frame_rate"] = None
    if stream.get("codec_type") == "audio":
        info["channels"] = stream.get("channels")
        info["sample_rate"] = stream.get("sample_rate")
        info["bit_rate"] = stream.get("bit_rate")
    if stream.get("codec_type") == "subtitle":
        info["is_pgs"] = stream.get("codec_name", "").lower() in (
            "hdmv_pgs_subtitle",
            "pgs",
        )
    return info


def extract_metadata(
    path: Path, input_root: Path = None, api_key: str = None, language: str = "en-US"
) -> Dict[str, Any]:
    """Simplified metadata extraction using unified signals and cache."""
    # 1. Use the unified metadata object (with cache)
    meta = get_or_create_metadata(path, input_root)

    # 2. Re-map to the legacy dictionary format expected by the CLI outputs
    out = {}
    guess = meta.guessit
    tech = meta.technical

    out["filename"] = path.name
    out["filepath"] = str(path)
    out["show_name"] = guess.get("show")
    out["season"] = guess.get("season")
    out["episode_start"] = guess.get("episode")
    out["episode_end"] = guess.get("episode_end")

    if tech:
        out["duration"] = tech.duration
        out["size"] = tech.ffprobe.get("format", {}).get("size")
        out["bit_rate"] = tech.ffprobe.get("format", {}).get("bit_rate")

        # Stream info for legacy CSV
        streams = tech.ffprobe.get("streams", [])
        out["video"] = None
        out["audios"] = []
        out["subtitles"] = []
        for s in streams:
            si = stream_info_summary(s)
            if s.get("codec_type") == "video" and out["video"] is None:
                out["video"] = si
            elif s.get("codec_type") == "audio":
                out["audios"].append(si)
            elif s.get("codec_type") == "subtitle":
                out["subtitles"].append(si)

    # Note: TMDB enrichment for title/overview could be added here if needed,
    # but the HolisticAIMatcher handles the best matching logic now.
    return out


def write_json(outdir: Path, meta: Dict[str, Any]):
    outdir.mkdir(parents=True, exist_ok=True)
    p = outdir / (meta["filename"] + ".metadata.json")
    with p.open("w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2, ensure_ascii=False)


def write_csv_summary(outdir: Path, rows: List[Dict[str, Any]]):
    p = outdir / "metadata_summary.csv"
    keys = [
        "filename",
        "filepath",
        "show_name",
        "season",
        "episode_start",
        "episode_end",
        "is_special",
        "episode_title",
        "duration",
        "size",
        "bit_rate",
        "video_codec",
        "width",
        "height",
        "frame_rate",
        "audio_codecs",
        "audio_langs",
        "subtitle_types",
        "subtitle_langs",
        "has_pgs_subtitles",
    ]
    with p.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=keys)
        writer.writeheader()
        for r in rows:
            video = r.get("video") or {}
            audio_codecs = ",".join(
                [a.get("codec_name", "") or "" for a in r.get("audios", [])]
            )
            audio_langs = ",".join(
                [a.get("language") or "" for a in r.get("audios", [])]
            )
            subtitle_types = ",".join(
                [
                    ("PGS" if s.get("is_pgs") else (s.get("codec_name") or "text"))
                    for s in r.get("subtitles", [])
                ]
            )
            subtitle_langs = ",".join(
                [s.get("language") or "" for s in r.get("subtitles", [])]
            )
            has_pgs = any([s.get("is_pgs") for s in r.get("subtitles", [])])
            row = {
                "filename": r.get("filename"),
                "filepath": r.get("filepath"),
                "show_name": r.get("show_name", ""),
                "season": r.get("season", ""),
                "episode_start": r.get("episode_start", ""),
                "episode_end": r.get("episode_end", ""),
                "is_special": r.get("is_special", ""),
                "episode_title": r.get("episode_title", ""),
                "duration": r.get("duration"),
                "size": r.get("size"),
                "bit_rate": r.get("bit_rate"),
                "video_codec": video.get("codec_name") if video else "",
                "width": video.get("width") if video else "",
                "height": video.get("height") if video else "",
                "frame_rate": video.get("frame_rate") if video else "",
                "audio_codecs": audio_codecs,
                "audio_langs": audio_langs,
                "subtitle_types": subtitle_types,
                "subtitle_langs": subtitle_langs,
                "has_pgs_subtitles": has_pgs,
            }
            writer.writerow(row)


def get_agument_parser(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument(
        "-i", "--input", type=Path, default=Path.cwd(), help="Input directory to scan"
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path.cwd() / "mkv_metadata",
        help="Output directory for metadata",
    )
    parser.add_argument(
        "--csv", action="store_true", help="Write a combined CSV summary"
    )
    parser.add_argument(
        "--extensions",
        nargs="*",
        default=get_extensions(),
        help="Extensions to scan (default .mkv)",
    )
    parser.add_argument(
        "--tmdb-api-key",
        type=str,
        help="TMDB API key for episode title lookup (can be set in config)",
    )
    parser.add_argument(
        "--language",
        type=str,
        default="en-US",
        help="Language for TMDB lookup (e.g., fr-FR, en-US)",
    )
    parser.add_argument(
        "--ai",
        action="store_true",
        help="Use Holistic AI Matcher for episode detection",
    )
    return parser


def main():
    parser = argparse.ArgumentParser(description="Extract metadata from videos.")
    parser = get_agument_parser(parser)
    args = parser.parse_args()

    # Load config for fallback
    from mediatamer.config import load_config

    config = load_config()
    tmdb_key = args.tmdb_api_key or config.get("tmbd-api-key")

    check_ffprobe()
    input_dir = args.input.resolve()
    out_dir = args.output.resolve()
    exts = {e if e.startswith(".") else f".{e}" for e in args.extensions}

    files = sorted(
        [p for p in input_dir.rglob("*") if p.suffix.lower() in exts and p.is_file()]
    )
    if not files:
        print("No MKV files found in", input_dir)
        return

    rows = []
    ai_matcher = None
    if args.ai:
        if not tmdb_key:
            print("Error: --ai requires --tmdb-api-key or config setting.")
            return
        ai_matcher = HolisticAIMatcher(tmdb_api_key=tmdb_key)

    for f in files:
        try:
            if args.ai:
                from mediatamer.signals.cache import save_metadata

                meta_obj = get_or_create_metadata(f, input_dir)
                ai_matcher.match(meta_obj)
                save_metadata(meta_obj)

                # Convert to the legacy dictionary format for output
                meta = extract_metadata(f, input_dir, tmdb_key, args.language)
                # Add AI match info to the dict
                meta["ai_match"] = meta_obj.ai_match
            else:
                meta = extract_metadata(f, input_dir, tmdb_key, args.language)
        except Exception as e:
            print(f"Error extracting metadata for {f}: {e}")
            continue
        write_json(out_dir, meta)
        rows.append(meta)

    if args.csv:
        write_csv_summary(out_dir, rows)

    print(f"Metadata written to {out_dir} (per-file JSON).")
    if args.csv:
        print(f"CSV summary: {out_dir / 'metadata_summary.csv'}")


if __name__ == "__main__":
    main()
