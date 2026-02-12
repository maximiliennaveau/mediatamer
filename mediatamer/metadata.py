"""Extract MKV metadata (MediaTamer packaged module)."""
from pathlib import Path
import argparse
import json
import subprocess
import csv
from typing import Dict, Any, List


def check_ffprobe():
    from shutil import which
    if which("ffprobe") is None:
        raise SystemExit("ffprobe not found in PATH. Install ffmpeg.")


def ffprobe_json(path: Path) -> Dict[str, Any]:
    cmd = [
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path)
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {path}: {res.stderr.strip()}")
    return json.loads(res.stdout)


def stream_info_summary(stream: Dict[str, Any]) -> Dict[str, Any]:
    info = {}
    info['index'] = stream.get('index')
    info['codec_name'] = stream.get('codec_name')
    info['codec_long_name'] = stream.get('codec_long_name')
    info['type'] = stream.get('codec_type')
    info['language'] = stream.get('tags', {}).get(
        'language') if stream.get('tags') else None
    info['title'] = stream.get('tags', {}).get(
        'title') if stream.get('tags') else None
    if stream.get('codec_type') == 'video':
        info['width'] = stream.get('width')
        info['height'] = stream.get('height')
        fr = stream.get('r_frame_rate') or stream.get(
            'avg_frame_rate') or '0/1'
        try:
            num, den = fr.split('/')
            info['frame_rate'] = float(
                num) / float(den) if float(den) != 0 else None
        except Exception:
            info['frame_rate'] = None
    if stream.get('codec_type') == 'audio':
        info['channels'] = stream.get('channels')
        info['sample_rate'] = stream.get('sample_rate')
        info['bit_rate'] = stream.get('bit_rate')
    if stream.get('codec_type') == 'subtitle':
        info['is_pgs'] = stream.get('codec_name', '').lower() in (
            'hdmv_pgs_subtitle', 'pgs')
    return info


def extract_metadata(path: Path) -> Dict[str, Any]:
    j = ffprobe_json(path)
    out = {}
    fmt = j.get('format', {})
    out['filename'] = path.name
    out['filepath'] = str(path)
    out['format_name'] = fmt.get('format_name')
    out['format_long_name'] = fmt.get('format_long_name')
    out['duration'] = float(fmt.get('duration')) if fmt.get(
        'duration') else None
    out['size'] = int(fmt.get('size')) if fmt.get('size') else None
    out['bit_rate'] = int(fmt.get('bit_rate')) if fmt.get('bit_rate') else None

    streams = j.get('streams', [])
    out['video'] = None
    out['audios'] = []
    out['subtitles'] = []
    for s in streams:
        si = stream_info_summary(s)
        if s.get('codec_type') == 'video' and out['video'] is None:
            out['video'] = si
        elif s.get('codec_type') == 'audio':
            out['audios'].append(si)
        elif s.get('codec_type') == 'subtitle':
            out['subtitles'].append(si)
    return out


def write_json(outdir: Path, meta: Dict[str, Any]):
    outdir.mkdir(parents=True, exist_ok=True)
    p = outdir / (meta['filename'] + ".metadata.json")
    with p.open("w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2, ensure_ascii=False)


def write_csv_summary(outdir: Path, rows: List[Dict[str, Any]]):
    p = outdir / "metadata_summary.csv"
    keys = [
        'filename', 'duration', 'size', 'bit_rate',
        'video_codec', 'width', 'height', 'frame_rate',
        'audio_codecs', 'audio_langs', 'subtitle_types', 'subtitle_langs', 'has_pgs_subtitles'
    ]
    with p.open("w", newline='', encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=keys)
        writer.writeheader()
        for r in rows:
            video = r.get('video') or {}
            audio_codecs = ",".join(
                [a.get('codec_name', '') or '' for a in r.get('audios', [])])
            audio_langs = ",".join(
                [a.get('language') or '' for a in r.get('audios', [])])
            subtitle_types = ",".join([('PGS' if s.get('is_pgs') else (
                s.get('codec_name') or 'text')) for s in r.get('subtitles', [])])
            subtitle_langs = ",".join(
                [s.get('language') or '' for s in r.get('subtitles', [])])
            has_pgs = any([s.get('is_pgs') for s in r.get('subtitles', [])])
            row = {
                'filename': r.get('filename'),
                'duration': r.get('duration'),
                'size': r.get('size'),
                'bit_rate': r.get('bit_rate'),
                'video_codec': video.get('codec_name') if video else '',
                'width': video.get('width') if video else '',
                'height': video.get('height') if video else '',
                'frame_rate': video.get('frame_rate') if video else '',
                'audio_codecs': audio_codecs,
                'audio_langs': audio_langs,
                'subtitle_types': subtitle_types,
                'subtitle_langs': subtitle_langs,
                'has_pgs_subtitles': has_pgs
            }
            writer.writerow(row)


def main():
    parser = argparse.ArgumentParser(
        description="Extract MKV metadata using ffprobe")
    parser.add_argument("-i", "--input", type=Path,
                        default=Path.cwd(), help="Input directory to scan")
    parser.add_argument("-o", "--output", type=Path, default=Path.cwd() /
                        "mkv_metadata", help="Output directory for metadata")
    parser.add_argument("--csv", action="store_true",
                        help="Write a combined CSV summary")
    parser.add_argument("--extensions", nargs="*",
                        default=[".mkv"], help="Extensions to scan (default .mkv)")
    args = parser.parse_args()

    check_ffprobe()
    input_dir = args.input.resolve()
    out_dir = args.output.resolve()
    exts = {e if e.startswith('.') else f".{e}" for e in args.extensions}

    files = sorted([p for p in input_dir.rglob(
        "*") if p.suffix.lower() in exts and p.is_file()])
    if not files:
        print("No MKV files found in", input_dir)
        return

    rows = []
    for f in files:
        try:
            meta = extract_metadata(f)
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


if __name__ == '__main__':
    main()
