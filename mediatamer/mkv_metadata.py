"""Helpers to write TV/show metadata into an existing MKV file.

Provides a small, well-tested function to write common global tags
and (optionally) set track language tags using `mkvpropedit`.

The function accepts either the project's `VideoMetadata` dataclass or a
plain dictionary that contains a `final_result` mapping produced by the
metadata extraction pipeline.
"""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
from typing import Any, Dict, Iterable, List, Optional, Union

from mediatamer.signals.video_metadata import VideoMetadata, metadata_to_dict


def _to_dict(meta: Union[VideoMetadata, Dict[str, Any]]) -> Dict[str, Any]:
    if isinstance(meta, VideoMetadata):
        return metadata_to_dict(meta)
    return dict(meta)


def _safe(value: object) -> str:
    return "" if value is None else str(value)


def write_mkv_metadata(
    mkv_path: Union[str, Path],
    metadata: Union[VideoMetadata, Dict[str, Any]],
    set_title: bool = True,
    audio_langs: Optional[Iterable[str]] = None,
    subtitle_langs: Optional[Iterable[str]] = None,
) -> bool:
    """Write extracted metadata into an existing MKV file.

    - `mkv_path` is the target MKV file to edit.
    - `metadata` is either a `VideoMetadata` instance or a dictionary
      (as returned by `metadata_to_dict` or the metadata extraction pipeline).
    - `set_title` if True will set the container title based on the
      discovered series/season/episode information when available.
    - `audio_langs` / `subtitle_langs` are optional iterables of ISO639-2
      language codes to apply to audio/subtitle tracks respectively.

    Returns True on success, False on failure.
    """
    mkv = Path(mkv_path)
    if not mkv.exists():
        print(f"Error: target file does not exist: {mkv}")
        return False

    if shutil.which("mkvpropedit") is None:
        print("Error: mkvpropedit not found in PATH; cannot write tags")
        return False

    data = _to_dict(metadata)
    final = data.get("final_result") or {}

    # Build a human-friendly title if possible
    title = None
    try:
        if set_title and final:
            series = final.get("series_full_name")
            season = final.get("seasonNumber")
            episode = final.get("number")
            name = final.get("name")
            if series and season is not None and episode is not None and name:
                title = f"{series} - S{int(season):02d}E{int(episode):02d} - {name}"
    except Exception:
        title = None

    if title is None:
        # Fallback to a best-effort title
        title = final.get("name") or data.get("guessit", {}).get("title") or mkv.stem

    # Prepare mkvpropedit arguments
    cmd: List[str] = [
        "mkvpropedit",
        str(mkv),
        "--edit",
        "info",
        "--set",
        f"title={_safe(title)}",
    ]

    # Common global tags to write (only when values are present)
    tags = {
        "TITLE": final.get("name"),
        "SUMMARY": final.get("overview"),
        "DESCRIPTION": final.get("overview"),
        "DATE_RELEASED": final.get("aired"),
        "YEAR": final.get("year"),
        "IMDB": final.get("imdbId"),
        "TVDB": final.get("id"),
        "SEASON_NUMBER": (
            str(final.get("seasonNumber"))
            if final.get("seasonNumber") is not None
            else None
        ),
        "EPISODE_NUMBER": (
            str(final.get("number")) if final.get("number") is not None else None
        ),
        "SERIES_TITLE": final.get("series_full_name"),
    }

    # First set the segment title (segment info)
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode != 0:
            out = (res.stdout or "").strip()
            err = (res.stderr or "").strip()
            print("mkvpropedit command:", " ".join(cmd))
            if out:
                print("mkvpropedit stdout:", out)
            if err:
                print("mkvpropedit stderr:", err)
            if not out and not err:
                print("mkvpropedit returned non-zero with no output")
            return False
    except Exception as e:
        print(f"Failed to run mkvpropedit: {e}")
        return False

    # Write global tags using a temporary tags XML and mkvpropedit --tags global:FILE
    non_empty_tags = {k: v for k, v in tags.items() if v is not None and v != ""}
    if non_empty_tags:
        import tempfile
        import xml.sax.saxutils as sax

        try:
            with tempfile.NamedTemporaryFile("w", delete=False, suffix=".xml") as fh:
                fh.write('<?xml version="1.0" encoding="UTF-8"?>\n<Tags>\n  <Tag>\n')
                for name, val in non_empty_tags.items():
                    fh.write("    <Simple>\n")
                    fh.write("      <Name>" + sax.escape(str(name)) + "</Name>\n")
                    fh.write("      <String>" + sax.escape(str(val)) + "</String>\n")
                    fh.write("    </Simple>\n")
                fh.write("  </Tag>\n</Tags>\n")
                tmpname = fh.name

            res2 = subprocess.run(
                ["mkvpropedit", str(mkv), "--tags", f"global:{tmpname}"],
                capture_output=True,
                text=True,
                check=False,
            )
            if res2.returncode != 0:
                out = (res2.stdout or "").strip()
                err = (res2.stderr or "").strip()
                print(
                    "mkvpropedit tags command: mkvpropedit",
                    str(mkv),
                    "--tags",
                    f"global:{tmpname}",
                )
                if out:
                    print("mkvpropedit stdout:", out)
                if err:
                    print("mkvpropedit stderr:", err)
                return False
        except Exception as e:
            print(f"Failed to write tags XML or run mkvpropedit: {e}")
            return False

    # Optionally set per-track languages if the user provided lists.
    # Use mkvmerge to discover counts of audio/subtitle tracks and then
    # set languages using the audio/subtitle ordinal selectors (track:aN / track:sN).
    if (audio_langs or subtitle_langs) and shutil.which("mkvmerge"):
        try:
            mkvmerge_out = subprocess.run(
                ["mkvmerge", "-i", str(mkv)],
                capture_output=True,
                text=True,
                check=False,
            )
            lines = mkvmerge_out.stdout.splitlines()
            audio_count = sum(1 for l in lines if "audio" in l.lower())
            subtitle_count = sum(
                1 for l in lines if "subtitles" in l.lower() or "subtitle" in l.lower()
            )

            if audio_langs:
                for idx, lang in enumerate(list(audio_langs)):
                    if idx >= audio_count:
                        break
                    cmd2 = [
                        "mkvpropedit",
                        str(mkv),
                        "--edit",
                        f"track:a{idx + 1}",
                        "--set",
                        f"language={lang}",
                    ]
                    subprocess.run(cmd2, capture_output=True, text=True)

            if subtitle_langs:
                for idx, lang in enumerate(list(subtitle_langs)):
                    if idx >= subtitle_count:
                        break
                    cmd2 = [
                        "mkvpropedit",
                        str(mkv),
                        "--edit",
                        f"track:s{idx + 1}",
                        "--set",
                        f"language={lang}",
                    ]
                    subprocess.run(cmd2, capture_output=True, text=True)

        except Exception:
            # Non-fatal: if we can't parse tracks just skip track-level edits
            pass

    return True


__all__ = ["write_mkv_metadata"]
