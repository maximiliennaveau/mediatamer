"""Organize module for MediaTamer."""

from pathlib import Path
import argparse
from shutil import move, copy2
import argcomplete
from mediatamer.cli.argparse_utils import add_common_arguments

from mediatamer.parameters import get_extensions
from mediatamer.utils import sanitize_filename, zero_pad


def get_argument_parser(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument(
        "--input", "-i", type=Path, default=Path.cwd(), help="Input root to scan"
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path.cwd() / "Jellyfin_Organized",
        help="Output root",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually move/copy files. If not set, runs as dry-run and prints actions",
    )
    parser.add_argument(
        "--move",
        action="store_true",
        help="Move files instead of copying when --apply is used",
    )
    parser.add_argument(
        "--exts",
        nargs="*",
        default=get_extensions(),
        help="Video extensions to include (example: .mp4 .mkv)",
    )
    parser.add_argument(
        "--tmdb-api-key",
        type=str,
        help="TMDB API key for episode title lookup (can be set in config)",
    )
    parser.add_argument(
        "--language", type=str, default="fr-FR", help="Language for metadata lookup"
    )
    parser = add_common_arguments(parser)
    return parser


def main():
    parser = argparse.ArgumentParser(
        description="Organize video files into Jellyfin layout (Show/Season XX/Show - SXXEXX.ext - Title)"
    )
    parser = get_argument_parser(parser)
    argcomplete.autocomplete(parser)
    args = parser.parse_args()

    # Load config for fallback
    from mediatamer.config import load_config

    config = load_config()
    tmdb_key = args.tmdb_api_key or config.get("tmbd-api-key")

    input_root = args.input.resolve()
    output_root = args.output.resolve()

    # Use the robust metadata engine
    from .get_tv_shows_metadata import get_tv_shows_metadata

    print(f"Scanning {input_root}...")
    results = get_tv_shows_metadata(
        input_root,
        tmdb_key,
        language=args.language,
        recursive=True,
        sorted_dir=output_root,  # Use output as reference for bonus numbering
    )

    planned_dests = set()
    actions = []

    for entry in results.get("files", []):
        src = Path(entry["path"])
        show = entry.get("show_detected") or "Unknown Show"
        season = entry.get("season_detected")
        episode = entry.get("episode_detected")

        if season is None:
            season = 1  # Fallback

        if not episode:
            # Skip files with no detected episode number
            actions.append((src, None, None, "SKIP (No Episode)"))
            continue

        selected = entry.get("selected_episode")
        title = ""
        if selected and selected.get("name"):
            title = sanitize_filename(selected["name"])

        season_str = zero_pad(season)
        episode_str = zero_pad(episode)

        show_dir_name = sanitize_filename(show)
        dest_dir = output_root / show_dir_name / f"Season {season_str}"

        title_part = f" - {title}" if title else ""
        dest_name = f"{show_dir_name} - S{season_str}E{episode_str}{title_part}{src.suffix.lower()}"
        dest_path = dest_dir / dest_name

        # Handle collisions
        counter = 1
        candidate = dest_path
        while candidate.exists() or candidate in planned_dests:
            candidate = (
                dest_dir
                / f"{show_dir_name} - S{season_str}E{episode_str} ({counter}){src.suffix.lower()}"
            )
            counter += 1

        planned_dests.add(candidate)
        actions.append(
            (
                src,
                candidate,
                args.move if args.apply else None,
                "MOVE"
                if args.apply and args.move
                else ("COPY" if args.apply else "DRY"),
            )
        )

    print("\nPlanned actions:")
    for src, dest, move_flag, action in actions:
        if dest is None:
            print(f"  {action}: {src.name}")
        else:
            print(f"  {action}: {src.name} -> {dest.relative_to(output_root)}")

    if not args.apply:
        print(
            "\nDry-run mode. To apply changes, re-run with --apply and optionally --move to move files."
        )
        return

    for src, dest, move_flag, action in actions:
        if dest is None:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            if move_flag:
                move(str(src), str(dest))
            else:
                copy2(str(src), str(dest))
        except Exception as e:
            print(f"Error processing {src}: {e}")

    print("\nDone. Files organized under:", output_root)


if __name__ == "__main__":
    main()
