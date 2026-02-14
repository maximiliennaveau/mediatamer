"""Organize module for MediaTamer."""
from pathlib import Path
import argparse
from shutil import move, copy2
from collections import defaultdict
import argcomplete

from .metadata import (
    extract_metadata
)
from .parameters import get_extensions


def sanitize_filename(name: str) -> str:
    """Sanitize string for use in filenames."""
    import re
    # Replace invalid chars with space or dash
    name = re.sub(r'[<>:"/\\|?*]', '-', name)
    # Collapse multiple spaces/dashes
    name = re.sub(r'[- ]+', ' ', name).strip()
    return name


def zero_pad(n):
    return f"{n:02d}"


def get_argument_parser(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument("--input", "-i", type=Path,
                        default=Path.cwd(), help="Input root to scan")
    parser.add_argument("--output", "-o", type=Path,
                        default=Path.cwd() / "Jellyfin_Organized", help="Output root")
    parser.add_argument("--apply", action="store_true",
                        help="Actually move/copy files. If not set, runs as dry-run and prints actions")
    parser.add_argument("--move", action="store_true",
                        help="Move files instead of copying when --apply is used")
    parser.add_argument("--exts", nargs="*",
                        help="Video extensions to include (example: .mp4 .mkv)")
    parser.add_argument("--tmdb-api-key", type=str,
                        help="TMDB API key for episode title lookup")
    return parser


def main():
    parser = argparse.ArgumentParser(
        description="Organize video files into Jellyfin layout (Show/Season XX/Show - SXXEXX.ext - Title)")
    parser = get_argument_parser(parser)
    argcomplete.autocomplete(parser)
    args = parser.parse_args()

    check_ffprobe()

    input_root = args.input.resolve()
    output_root = args.output.resolve()
    if args.exts:
        exts = {e.lower() if e.startswith(
            '.') else f".{e.lower()}" for e in args.exts}
    else:
        exts = {e if e.startswith('.') else f".{e}" for e in get_extensions()}

    files = [p for p in input_root.rglob(
        "*") if p.suffix.lower() in exts and p.is_file()]
    if not files:
        print("No video files found under", input_root)
        return

    file_infos = []
    planned_dests = set()

    for p in sorted(files):
        # Use extract_metadata from metadata.py for all metadata extraction
        meta = extract_metadata(p, input_root, args.tmdb_api_key)

        title = sanitize_filename(meta.get('episode_title', '')) if meta.get(
            'episode_title') else ''

        file_infos.append({
            'path': p,
            'show': meta.get('show_name'),
            'season': meta.get('season'),
            'ep_start': meta.get('episode_start'),
            'ep_end': meta.get('episode_end'),
            'title': title
        })

    # Group files by show and season for sequential numbering
    groups = defaultdict(list)
    for fi in file_infos:
        key = (fi['show'], fi['season'] if fi['season'] is not None else 0)
        groups[key].append(fi['path'])

    sequential_counters = {}
    for (show, season), plist in groups.items():
        existing = []
        for p in plist:
            for fi in file_infos:
                if fi['path'] == p and fi.get('ep_start'):
                    existing.append(fi.get('ep_start'))
                    break
        counter = 1
        if existing:
            counter = max(existing) + 1
        sequential_counters[(show, season)] = counter

    actions = []
    for fi in file_infos:
        p = fi['path']
        show = fi['show']
        season = fi['season']
        ep_start = fi.get('ep_start')
        ep_end = fi.get('ep_end')

        if season is None:
            season = 1

        if ep_start is None:
            ep = sequential_counters[(show, season)]
            sequential_counters[(show, season)] += 1
            ep_start = ep
            ep_end = None

        season_str = zero_pad(season)
        episode_str = zero_pad(ep_start)
        episode_end_str = zero_pad(ep_end) if ep_end else None
        show_dir_name = show
        dest_dir = output_root / show_dir_name / f"Season {season_str}"
        if episode_end_str and ep_end and ep_end != ep_start:
            dest_name = f"{show_dir_name} - S{season_str}E{episode_str}-E{episode_end_str}{p.suffix.lower()}"
        else:
            title_part = f" - {fi['title']}" if fi.get('title') else ""
            dest_name = f"{show_dir_name} - S{season_str}E{episode_str}{title_part}{p.suffix.lower()}"
        dest_path = dest_dir / dest_name

        counter = 1
        candidate = dest_path
        while candidate.exists() or candidate in planned_dests:
            candidate = dest_dir / \
                f"{show_dir_name} - S{season_str}E{episode_str} ({counter}){p.suffix.lower()}"
            counter += 1
        planned_dests.add(candidate)
        actions.append((p, candidate, args.move if args.apply else None,
                       "MOVE" if args.apply and args.move else ("COPY" if args.apply else "DRY")))

    print("Planned actions:")
    for src, dest, move_flag, action in actions:
        if dest is None:
            print(
                f"  SKIP: {src} -> no episode detected")
        else:
            print(f"  {action}: {src} -> {dest}")

    if not args.apply:
        print("\nDry-run mode. To apply changes, re-run with --apply and optionally --move to move files.")
        return

    for src, dest, move_flag, action in actions:
        if dest is None:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        if move_flag:
            move(str(src), str(dest))
        else:
            copy2(str(src), str(dest))
    print("Done. Files organized under:", output_root)


if __name__ == '__main__':
    main()
