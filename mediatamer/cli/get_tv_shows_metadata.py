#!/usr/bin/env python3
"""Extract TV show metadata from video files using robust matching."""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
import requests
import argcomplete

from mediatamer.matcher import EpisodeMatcher
from mediatamer.cli.metadata import extract_metadata, find_parent_show_and_season
from mediatamer.parameters import get_extensions
from mediatamer.signals.guessit import infer_context_from_path
from mediatamer.signals.video_metadata import VideoMetadata


def get_next_bonus_number(show: str, season: int, sorted_dir: Optional[Path]) -> int:
    """Find the next available bonus episode number for a show/season.

    Scan sorted_dir for files matching '{Show} - bonus S{Season}E{Number}'.
    """
    max_num = 0
    if not sorted_dir or not sorted_dir.exists():
        return 1

    # Pattern: "Doctor Who - bonus S09E01" -> match 1
    # We look for "{show} - bonus" specifically for this mode
    bonus_show_name = f"{show} - bonus"

    # We scan recursively or just in the show folder if it exists
    # For now, let's scan the whole sorted_dir if it's not too big,
    # or just look for the show-bonus folder.
    potential_folders = list(sorted_dir.glob(f"*{bonus_show_name}*"))
    for folder in potential_folders:
        for f in folder.rglob("*.mkv"):
            # Check for SXXEXX in filename
            m = re.search(r"[sS](\d+)[eE](\d+)", f.name)
            if m:
                s = int(m.group(1))
                e = int(m.group(2))
                if s == season:
                    max_num = max(max_num, e)

    return max_num + 1


def get_tv_shows_metadata(
    path: Path,
    api_key: str,
    language: str = "fr-FR",
    sorted_dir: Optional[Path] = None,
    jellyfin_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Analyze a video file or directory and return metadata plan.

    Args:
        path: File or Directory to analyze.
        api_key: TMDB API Key.
        language: Language for metadata (default fr-FR).
        sorted_dir: Optional path to scan for existing bonus numbering.
        jellyfin_config: Optional dict with (url, api_key) for Jellyfin probing.

    Returns:
        Dict containing processing results, candidates, and recommended actions.
    """
    if not path.exists():
        raise FileNotFoundError(f"Path {path} does not exist")

    # 1. Identify Files
    files = []
    if path.is_file():
        files = [path]
        root_context = path.parent
    else:
        exts = {e if e.startswith(".") else f".{e}" for e in get_extensions()}
        files = sorted(
            [p for p in path.rglob("*") if p.suffix.lower() in exts and p.is_file()]
        )
        root_context = path

    if len(files) == 0:
        raise FileNotFoundError(f"No video files found in {path}")
    assert type(files) is list
    print(f"Processing {len(files)} files:")
    for f in files:
        print(f"\t{f}")

    results = {
        "source": str(path),
        "files": [],
        "review_needed": False,
        "summary": {"analyzed": len(files), "matched": 0, "conflicts": 0},
    }

    assigned_episodes = {}  # (show, date, season, episode) -> filename

    # Pre-analysis: Gather durations and identify show/season groups
    files_info = []
    prefixes = {}  # prefix -> list of durations
    groups = {}  # (show, season) -> list of file indices

    for i, f in enumerate(files):
        vmeta = VideoMetadata(f)
        from mediatamer.signals.video_metadata import extract_all_metadata

        extract_all_metadata(vmeta, root_context)
        sig = vmeta.technical
        duration = sig.duration
        prefix = f.name[0].upper() if f.name else "?"
        if prefix not in prefixes:
            prefixes[prefix] = []
        prefixes[prefix].append(duration)

        # Infer context (show, season, dvd) for grouping and sorting
        meta = infer_context_from_path(f, vmeta, root_context)
        show = meta.get("show")
        season = meta.get("season")
        dvd = meta.get("dvd")
        group_key = (show, season)
        if group_key not in groups:
            groups[group_key] = []
        groups[group_key].append(i)

        files_info.append(
            {
                "path": f,
                "duration": duration,
                "prefix": prefix,
                "show": show,
                "season": season,
                "dvd": dvd or 0,
                "signals": sig,
                "metadata": vmeta,
            }
        )

    # Determine the "Main Episode" prefixes
    main_prefixes = set()
    medians = {}
    for p, durs in prefixes.items():
        if not durs:
            continue
        sorted_durs = sorted(durs)
        median = sorted_durs[len(sorted_durs) // 2]
        medians[p] = median

    if medians:
        max_median = max(medians.values())
        if max_median > 600:  # At least 10 minutes for a main episode
            for p, m in medians.items():
                if m >= (max_median * 0.8):
                    main_prefixes.add(p)

    if main_prefixes:
        print(
            f"Pre-analysis: Identified {sorted(list(main_prefixes))} as likely main episode prefixes (max median: {max_median / 60:.1f}m)"
        )

    # 3. Process each group
    for group_key, indices in groups.items():
        show_name, season_number = group_key
        print(
            f"\nProcessing Group: {show_name} Season {season_number} ({len(indices)} files)"
        )

        last_ep = None
        next_bonus_num = None

        # Sort indices by (dvd, filename) to maintain global season sequence
        indices.sort(
            key=lambda idx: (files_info[idx]["dvd"], files_info[idx]["path"].name)
        )

        # Identify if this group looks like a DVD set with global indices
        from mediatamer.signals.scoring import parse_disc_track

        group_files_info = [files_info[idx] for idx in indices]
        has_global_indices = all(
            parse_disc_track(info["path"].name) is not None
            for info in group_files_info
            if info["prefix"] in main_prefixes
        )

        for idx in indices:
            info = files_info[idx]
            f = info["path"]
            is_likely_episode = info["prefix"] in main_prefixes

            # Pass show and season from group for consistency
            matcher = EpisodeMatcher(
                f,
                api_key,
                show_name=show_name,
                season_number=season_number,
                scan_root=root_context,
            )
            matcher.is_likely_episode = is_likely_episode
            matcher.last_episode_matched = last_ep
            matcher.has_global_indices = has_global_indices
            matcher.find_metadata()

            if is_likely_episode and matcher.episode_number:
                last_ep = matcher.episode_number

            # -- New Bonus Labeling Logic --
            if not is_likely_episode and matcher.show_name:
                # Apply suffix as requested: "Show - bonus"
                original_show = matcher.show_name
                # If it already contains " - Extras" or similar from heuristic, replace it
                clean_show = original_show.split(" - ")[0]
                matcher.show_name = f"{clean_show} - bonus"

                # Use current season as requested
                # matcher.season_number is already set to current season by _infer_context

                # Sequential Numbering
                if next_bonus_num is None:
                    # Initialize next_bonus_num by scanning local/ext sources
                    local_max = get_next_bonus_number(
                        clean_show, matcher.season_number, sorted_dir
                    )

                    jelly_max = 0
                    if jellyfin_config:
                        client = JellyfinClient(
                            jellyfin_config["url"], jellyfin_config["api_key"]
                        )
                        jelly_max = client.get_max_bonus_number(
                            clean_show, matcher.season_number
                        )

                    next_bonus_num = max(
                        local_max, jelly_max + 1 if jelly_max > 0 else 1
                    )

                matcher.episode_number = next_bonus_num
                next_bonus_num += 1

                # Title override as requested
                # For bonuses, we might want to keep the original if matched, but user said:
                # "episode: No title?"
                # I'll set a generic title or "No title" if desired.
                bonus_ep = {
                    "episode_number": matcher.episode_number,
                    "name": "No title",
                    "id": None,
                }
                matcher.best_candidate = {
                    "episode": bonus_ep,
                    "score": 100.0,
                    "reasons": ["Sequential bonus assignment"],
                }
                # Also override candidates so the rest of the logic uses the clean data
                matcher.candidates = [matcher.best_candidate]

        entry = {
            "file": f.name,
            "path": str(f),
            "show_detected": matcher.show_name,
            "season_detected": matcher.season_number,
            "episode_detected": matcher.episode_number,
            "candidates": [],
            "selected_episode": None,
            "status": "NO_MATCH",
        }

        # Populate candidates info for review
        if matcher.candidates:
            import re

            for c in matcher.candidates[:3]:
                raw_name = c["episode"].get("name") or ""
                # Normalize: "Title (1)" -> "Title"
                clean_name = re.sub(r"\s*\(\d+\)$", "", raw_name)

                entry["candidates"].append(
                    {
                        "episode_number": c["episode"].get("episode_number"),
                        "name": clean_name,
                        "score": c["score"],
                        "reasons": c["reasons"],
                        "tmdb_id": c["episode"].get("id"),
                        "overview": c["episode"].get("overview"),
                        "air_date": c["episode"].get("air_date"),
                    }
                )

        # Logic for Selection & Status
        best = matcher.best_candidate
        if best:
            ep_num = best["episode"].get("episode_number")
            season = matcher.season_number
            show = matcher.show_name

            entry["selected_episode"] = entry["candidates"][
                0
            ]  # Best is always first if best_candidate is set

            # Conflict Check
            key = (show, season, ep_num)
            if key in assigned_episodes:
                entry["status"] = "CONFLICT"
                entry["conflict_with"] = assigned_episodes[key]
                results["review_needed"] = True
                results["summary"]["conflicts"] += 1
            else:
                entry["status"] = "MATCH"
                assigned_episodes[key] = f.name
                results["summary"]["matched"] += 1

        else:
            # No high confidence match
            results["review_needed"] = True
            if matcher.candidates:
                entry["status"] = "LOW_CONFIDENCE"
            else:
                entry["status"] = "NO_MATCH"

        results["files"].append(entry)

        best_name = "?"
        if entry["selected_episode"]:
            best_name = entry["selected_episode"]["name"]

        print(
            f"  [{entry['status']}] {f.name} -> {matcher.show_name} S{matcher.season_number}E{matcher.episode_number if matcher.episode_number else '?'} ({best_name})"
        )

        # Pipeline prints: Show what algorithm found what
        if matcher.best_candidate:
            for reason in matcher.best_candidate.get("reasons", []):
                print(f"      - {reason}")
        elif matcher.candidates:
            # Show best candidate's reasons even if low confidence
            top = matcher.candidates[0]
            # Normalize top name too if needed for print
            top_name = re.sub(r"\s*\(\d+\)$", "", top["episode"].get("name") or "?")
            print(f"      - Best candidate ({top_name}) reasons:")
            for reason in top.get("reasons", []):
                print(f"          - {reason}")

    return results


class JellyfinClient:
    """Helper to probe a Jellyfin instance for existing media."""

    def __init__(self, url: str, api_key: str):
        self.url = url.rstrip("/")
        self.api_key = api_key

    def get_max_bonus_number(self, show: str, season: int) -> int:
        """Probe Jellyfin for the highest episode number in the '- bonus' series."""
        try:
            bonus_show_name = f"{show} - bonus"

            # 1. Search for Series ID
            search_url = f"{self.url}/Items"
            headers = {"X-Emby-Token": self.api_key, "Content-Type": "application/json"}
            params = {
                "SearchTerm": bonus_show_name,
                "IncludeItemTypes": "Series",
                "Recursive": "true",
                "Fields": "Id,Name",
            }
            resp = requests.get(search_url, headers=headers, params=params, timeout=10)
            if not resp.ok:
                print(f"  [JELLYFIN] API Error: {resp.status_code}")
                return 0

            items = resp.json().get("Items", [])
            series_id = None
            for item in items:
                if item.get("Name") == bonus_show_name:
                    series_id = item.get("Id")
                    break

            if not series_id:
                return 0

            # 2. Get Episodes for Season
            episodes_url = f"{self.url}/Shows/{series_id}/Episodes"
            params = {"SeasonNumber": season, "Fields": "IndexNumber"}
            resp = requests.get(
                episodes_url, headers=headers, params=params, timeout=10
            )
            if not resp.ok:
                return 0

            episodes = resp.json().get("Items", [])
            max_num = 0
            for ep in episodes:
                num = ep.get("IndexNumber")
                if num is not None:
                    max_num = max(max_num, int(num))

            if max_num > 0:
                print(
                    f"  [JELLYFIN] Found max episode E{max_num} for '{bonus_show_name}' S{season}"
                )
            return max_num

        except Exception as e:
            print(f"  [JELLYFIN] Error: {e}")
            return 0


def get_argument_parser(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument(
        "--input-path", "-i", required=True, type=Path, help="Input file or directory"
    )
    parser.add_argument(
        "--tmdb-api-key",
        type=str,
        help="TMDB API Key (can be set in mediatamer-config.yml)",
    )
    parser.add_argument(
        "--language", type=str, default="fr-FR", help="Language for metadata"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not write metadata files, only review plan",
    )
    parser.add_argument(
        "--sorted-dir",
        type=Path,
        help="Path to organized library to detect next bonus number",
    )
    parser.add_argument(
        "--jellyfin-url", type=str, help="Jellyfin Server URL (can be set in config)"
    )
    parser.add_argument(
        "--jellyfin-api-key", type=str, help="Jellyfin API Key (can be set in config)"
    )
    return parser


def main():
    parser = argparse.ArgumentParser(description="Extract TV Show metadata")
    parser = get_argument_parser(parser)
    argcomplete.autocomplete(parser)
    args = parser.parse_args()

    # If running standalone, we might need to load config here too
    # but cli.py already does it if called via 'mediatamer'
    from mediatamer.config import load_config

    config = load_config()

    tmdb_key = args.tmdb_api_key or config.get("tmbd-api-key")
    if not tmdb_key:
        print(
            "Error: TMDB API Key is required. Provide it via --tmdb-api-key or in mediatamer-config.yml"
        )
        sys.exit(1)

    jellyfin_url = args.jellyfin_url or config.get("jellyfin-url")
    jellyfin_api_key = args.jellyfin_api_key or config.get("jellyfin-api-key")

    jellyfin_config = None
    if jellyfin_url and jellyfin_api_key:
        jellyfin_config = {"url": jellyfin_url, "api_key": jellyfin_api_key}

    # Call API
    try:
        data = get_tv_shows_metadata(
            args.input_path,
            tmdb_key,
            args.language,
            sorted_dir=args.sorted_dir,
            jellyfin_config=jellyfin_config,
        )
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

    # Output Logic
    output_dir = Path("/data/videos/metadata")
    output_dir.mkdir(parents=True, exist_ok=True)

    review_needed = data["review_needed"] or args.dry_run

    if review_needed:
        review_file = output_dir / "review_plan.json"
        with open(review_file, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print("\n" + "=" * 60)
        print(f"REVIEW REQUIRED. Plan written to {review_file}")
        print("Inspect the file, manually adjust 'selected_episode' if needed.")
    else:
        print("\nAll matches high confidence. Writing metadata...")
        for item in data["files"]:
            if item["status"] == "MATCH" and item["selected_episode"]:
                # Construct final metadata
                # We need technical metadata too.
                # Ideally, extract_metadata should support passing existing data to avoid re-probing?
                # For now, simplistic re-extraction or we should have returned tech data from API.

                # Fetch full metadata merging with what we found
                sel = item["selected_episode"]

                # Simple tech extract
                try:
                    vm = extract_metadata(Path(item["path"]), None, None, args.language)
                except:
                    vm = {}

                meta_entry = {
                    "filename": item["file"],
                    "filepath": item["path"],
                    "show_name": item["show_detected"],
                    "season": item["season_detected"],
                    "episode_number": sel["episode_number"],
                    "episode_title": sel["name"],
                    "tmdb_episode_id": sel["tmdb_id"],
                    "overview": sel.get("overview"),
                    "air_date": sel.get("air_date"),
                    "duration": vm.get("duration"),
                    "size": vm.get("size"),
                    "video_codec": vm.get("video", {}).get("codec_name"),
                }

                out_f = output_dir / f"{item['file']}.metadata.json"
                with open(out_f, "w") as f:
                    json.dump(meta_entry, f, indent=2, ensure_ascii=False)
                print(f"Wrote {out_f.name}")


if __name__ == "__main__":
    main()
