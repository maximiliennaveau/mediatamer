"""Organize module for MediaTamer (copied from jellyfin_tools.organize)."""
from pathlib import Path
import re
import argparse
import json
import subprocess
from shutil import move, copy2
from collections import defaultdict

VIDEO_EXTS = {'.mp4', '.mkv', '.mov', '.avi',
              '.m4v', '.ts', '.mpg', '.mpeg', '.flv'}

SE_EP_PATTERNS = [
    re.compile(
        r'[Ss](?P<season>\d{1,2})[ ._-]?[Ee](?P<ep1>\d{1,2})(?:[ ._-]*[-–—&][ ._-]*(?P<ep2>\d{1,2}))?'),
    re.compile(
        r'(?P<season>\d{1,2})[xX](?P<ep1>\d{1,2})(?:[-](?P<ep2>\d{1,2}))?'),
    re.compile(
        r'[Ss]eason[ ._-]?(?P<season>\d{1,2}).*?[Ee]p(?:isode)?[ ._-]?(?P<ep1>\d{1,2})(?:[ ._-]*[-–—&][ ._-]*(?P<ep2>\d{1,2}))?', re.I),
    re.compile(
        r'\b[Ee]p(?:isode)?[ ._-]?(?P<ep1>\d{1,2})(?:[ ._-]*[-–—&][ ._-]*(?P<ep2>\d{1,2}))?\b'),
    re.compile(r'\b(?P<ep1>\d{2})[-–—](?P<ep2>\d{2})\b'),
    re.compile(r'\b(?P<ep1>\d{2})\b')
]

SEASON_ONLY_PAT = re.compile(
    r'[Ss](?P<season>\d{1,2})|Season[ ._-]?(?P<season2>\d{1,2})', re.I)


def normalize_show_name(raw: str) -> str:
    s = raw.replace('_', ' ').replace('.', ' ').strip()
    s = re.sub(r'\b[Ss]\d{1,2}\b', '', s)
    s = re.sub(r'\bDVD[_ -]?\d+\b', '', s, flags=re.I)
    s = re.sub(r'\bD[_ -]?\d+\b', '', s, flags=re.I)
    s = re.sub(r'\bDisc[_ -]?\d+\b', '', s, flags=re.I)
    s = re.sub(r'\s+', ' ', s).strip()
    return s.title() if s else 'Unknown Show'


def extract_se_ep_from_name(name: str):
    lname = name
    for pat in SE_EP_PATTERNS:
        m = pat.search(lname)
        if m:
            gd = m.groupdict()
            season = None
            if 'season' in gd and gd.get('season'):
                try:
                    season = int(gd.get('season'))
                except Exception:
                    season = None
            ep1 = None
            ep2 = None
            if gd.get('ep1'):
                try:
                    ep1 = int(gd.get('ep1'))
                except Exception:
                    ep1 = None
            if gd.get('ep2'):
                try:
                    ep2 = int(gd.get('ep2'))
                except Exception:
                    ep2 = None
            return (season, ep1, ep2)

    if re.search(r'\b(special|sp|bonus|extra|ova|feature)\b', lname, re.I):
        m = re.search(r'(?:special|sp)[^0-9]*(\d{1,2})', lname, re.I)
        ep = int(m.group(1)) if m else None
        return (0, ep, None)

    return (None, None, None)


def extract_season_only(name: str):
    m = SEASON_ONLY_PAT.search(name)
    if m:
        season = m.groupdict().get('season') or m.groupdict().get('season2')
        if season:
            return int(season)
    return None


def find_parent_show_and_season(file_path: Path, input_root: Path):
    rel = file_path.relative_to(input_root)
    parts = rel.parts
    if len(parts) >= 2:
        top_dir = parts[0]
    else:
        top_dir = file_path.parent.name
    show_guess = normalize_show_name(top_dir)
    season = None
    p = file_path.parent
    while p != input_root and p != p.parent:
        s = extract_season_only(p.name)
        if s:
            season = s
            break
        p = p.parent
    return show_guess, season


def ffprobe_tags(path: Path):
    try:
        cmd = ["ffprobe", "-v", "error", "-print_format",
               "json", "-show_format", str(path)]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            return {}
        j = json.loads(res.stdout)
        return {k.lower(): v for k, v in (j.get('format', {}).get('tags') or {}).items()}
    except Exception:
        return {}


def int_from_tag(val):
    if val is None:
        return None
    try:
        return int(re.search(r"\d+", str(val)).group())
    except Exception:
        return None


def zero_pad(n):
    return f"{n:02d}"


def main():
    parser = argparse.ArgumentParser(
        description="Organize video files into Jellyfin layout (Show/Season XX/Show - SXXEXX.ext)")
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
    parser.add_argument("--number-missing", action="store_true",
                        help="If episode not found, assign sequential episode numbers per season")
    args = parser.parse_args()

    input_root = args.input.resolve()
    output_root = args.output.resolve()
    if args.exts:
        exts = {e.lower() if e.startswith(
            '.') else f".{e.lower()}" for e in args.exts}
    else:
        exts = VIDEO_EXTS

    files = [p for p in input_root.rglob(
        "*") if p.suffix.lower() in exts and p.is_file()]
    if not files:
        print("No video files found under", input_root)
        return

    groups = defaultdict(list)
    file_infos = []

    for p in sorted(files):
        filename = p.name
        name_no_ext = p.stem
        show_guess, season_from_parent = find_parent_show_and_season(
            p, input_root)

        season, ep_start, ep_end = extract_se_ep_from_name(filename)

        tags = ffprobe_tags(p)
        if tags:
            show_tag = tags.get('show') or tags.get(
                'series') or tags.get('album') or tags.get('title')
            if show_tag:
                show_guess = normalize_show_name(show_tag)
            season_tag = int_from_tag(
                tags.get('season_number') or tags.get('season'))
            episode_tag = int_from_tag(tags.get('episode_id') or tags.get(
                'episode_number') or tags.get('episode') or tags.get('track'))
            if season_tag is not None:
                season = season_tag
            if episode_tag is not None:
                ep_start = episode_tag
                ep_end = None

        if season is None:
            season = season_from_parent
        if season is None:
            season = extract_season_only(p.parent.name)

        file_infos.append({
            'path': p,
            'show': show_guess,
            'season': season,
            'ep_start': ep_start,
            'ep_end': ep_end
        })
        key = (show_guess, season if season is not None else 0)
        groups[key].append(p)

    sequential_counters = {}
    for (show, season), plist in groups.items():
        existing = []
        for p in plist:
            for fi in file_infos:
                if fi['path'] == p:
                    if fi.get('ep_start'):
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
            if args.number_missing:
                ep = sequential_counters[(show, season)]
                sequential_counters[(show, season)] += 1
                ep_start = ep
                ep_end = None
            else:
                actions.append((p, None, None, f"SKIP (no episode found)"))
                continue

        season_str = zero_pad(season)
        episode_str = zero_pad(ep_start)
        episode_end_str = zero_pad(ep_end) if ep_end else None
        show_dir_name = show
        dest_dir = output_root / show_dir_name / f"Season {season_str}"
        dest_dir.mkdir(parents=True, exist_ok=True)
        if episode_end_str and ep_end and ep_end != ep_start:
            dest_name = f"{show_dir_name} - S{season_str}E{episode_str}-E{episode_end_str}{p.suffix.lower()}"
        else:
            dest_name = f"{show_dir_name} - S{season_str}E{episode_str}{p.suffix.lower()}"
        dest_path = dest_dir / dest_name

        counter = 1
        candidate = dest_path
        while candidate.exists():
            candidate = dest_dir / \
                f"{show_dir_name} - S{season_str}E{episode_str} ({counter}){p.suffix.lower()}"
            counter += 1
        actions.append((p, candidate, args.move if args.apply else None,
                       "MOVE" if args.apply and args.move else ("COPY" if args.apply else "DRY")))

    print("Planned actions:")
    for src, dest, move_flag, action in actions:
        if dest is None:
            print(
                f"  SKIP: {src} -> no episode detected (use --number-missing to auto-assign)")
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
