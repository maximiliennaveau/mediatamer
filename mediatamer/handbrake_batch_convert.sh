#!/usr/bin/env bash
set -euo pipefail

# Batch convert videos in a folder using HandBrakeCLI with the requested settings
# Target settings (DS418 + LG 1080p):
# - Format: MKV
# - Video: H.265 (x265), Constant framerate, Same as source, RF 20
# - Audio: AAC, bitrate 160-320 kbps (default 192kbps), drop other audio tracks
# - Subtitles: prefer external SRT; if none and VOSTFR present, include non-PGS embedded French subtitle
#
# Usage:
#   ./handbrake_batch_convert.sh /path/to/input-dir [--dry-run] [--no-vostfr]
#
# By default the script will try to keep a VOSTFR subtitle when no external SRT exists.
# Pass --no-vostfr to disable that behavior.

HAND_BRAKE_CMD="HandBrakeCLI"
INPUT_DIR="${1:-.}"
DRY_RUN=false
KEEP_VOSTFR=true

# parse args simply (support --dry-run and --no-vostfr anywhere)
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    --no-vostfr) KEEP_VOSTFR=false ;;
  esac
done

# File extensions to process (case-insensitive)
EXTENSIONS="mp4 mkv mov avi m4v ts mpg mpeg flv"

if ! command -v "$HAND_BRAKE_CMD" >/dev/null 2>&1; then
  echo "Error: $HAND_BRAKE_CMD not found in PATH. Install HandBrakeCLI first." >&2
  exit 1
fi

shopt -s nocaseglob
for ext in $EXTENSIONS; do
  for infile in "$INPUT_DIR"/*."$ext"; do
    [ -e "$infile" ] || continue
    base="${infile%.*}"
    outfile="${base}-h265.mkv"

    # Find external SRT with same base name (common patterns)
    srtfile=""
    for suf in "" ".vostfr" ".VOSTFR" ".fr" ".FR" ".fra" ".FRA"; do
      if [ -f "${base}${suf}.srt" ]; then
        srtfile="${base}${suf}.srt"
        break
      fi
    done
    # also accept plain .srt if present
    if [ -z "$srtfile" ] && [ -f "${base}.srt" ]; then
      srtfile="${base}.srt"
    fi

    # If no external SRT and KEEP_VOSTFR enabled, scan for embedded non-PGS French subtitle
    embedded_sub_track=""
    if [ -z "$srtfile" ] && [ "$KEEP_VOSTFR" = true ]; then
      scan_out=$("$HAND_BRAKE_CMD" -i "$infile" --scan 2>&1 || true)
      # Look for subtitle lines that are NOT pgs and that contain french/fre/fra or vost
      candidate_line=$(printf '%s\n' "$scan_out" \
        | grep -i 'subtitle' \
        | grep -vi 'pgs' || true)
      if [ -n "$candidate_line" ]; then
        # filter for lines mentioning French / VOST / fra / fre
        candidate_line=$(printf '%s\n' "$candidate_line" | grep -Ei 'fra|fre|french|vost' | sed -n '1p' || true)
      fi
      if [ -n "$candidate_line" ]; then
        # Extract track number (match 'track <num>' or similar)
        embedded_sub_track=$(printf '%s\n' "$candidate_line" | grep -oP 'track\\s*\\K[0-9]+' | sed -n '1p' || true)
      fi
    fi

    # Build HandBrakeCLI command
    # - encoder x265, quality 20 (RF), format mkv
    # - framerate: same (+ request constant framerate)
    # - select first audio track (-a 1) and encode to AAC (-E av_aac) at 192 kbps (-B 192)
    # - do NOT include PGS subtitles; include external SRT when present; else include embedded selected track
    cmd=( "$HAND_BRAKE_CMD" -i "$infile" -o "$outfile" -f mkv -e x265 -q 20 -r "same" --pfr -a 1 -E av_aac -B 192 )

    if [ -n "$srtfile" ]; then
      cmd+=( --srt-file "$srtfile" --srt-lang eng )
    elif [ -n "$embedded_sub_track" ]; then
      # HandBrakeCLI subtitle indexes are 1-based; use -s to select the embedded subtitle track
      cmd+=( -s "$embedded_sub_track" )
    fi

    echo "Converting: $infile -> $outfile"
    if [ "$DRY_RUN" = true ]; then
      printf 'DRY RUN: %q ' "${cmd[@]}"
      echo
    else
      "${cmd[@]}"
      rc=$?
      if [ $rc -ne 0 ]; then
        echo "HandBrakeCLI failed for: $infile (exit $rc)" >&2
      fi
    fi
  done
done

echo "Done."