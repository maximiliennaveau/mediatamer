# MKV Parsing Tools in MediaTamer

MediaTamer integrates three powerful open-source tools to extract technical and descriptive metadata from MKV files. These tools are available in the Nix development environment and have dedicated Python modules in `mediatamer/signals/`.

## 1. ffprobe (FFmpeg)
Used for low-level technical analysis of media streams and packets.

- **Module**: `mediatamer/signals/ffprobe.py`
- **Function**: `extract_metadata_ffprobe(path: Path) -> Dict[str, Any]`
- **Best for**: 
    - Identifying codecs, bitrates, and resolutions.
    - Extracting stream-level technical metadata.
    - Integration with other FFmpeg operations (like OCR).

## 2. mkvmerge (MKVToolNix)
The standard for Matroska structure. It is the most reliable tool for reading the container's internal layout.

- **Module**: `mediatamer/signals/mkvmerge.py`
- **Function**: `extract_metadata_mkvmerge(path: Path) -> Dict[str, Any]`
- **Best for**:
    - Precise Track IDs (consistent with `mkvextract`).
    - Reading MKV-specific flags (Default track, Forced track).
    - Handling attachments and chapters.
    - High-performance JSON identification (`-J`).

## 3. MediaInfo
Focused on high-level descriptive metadata and encoding parameters.

- **Module**: `mediatamer/signals/mediainfo.py`
- **Function**: `extract_metadata_mediainfo(path: Path) -> Dict[str, Any]`
- **Best for**:
    - Reading encoding settings (x264/x265 params).
    - Detailed language and title tags.
    - Identifying the specific software used for muxing (e.g., MakeMKV version).

## Usage Example

```python
from pathlib import Path
from mediatamer.signals.mkvmerge import extract_metadata_mkvmerge

video_path = Path("Show_S01E01.mkv")
metadata = extract_metadata_mkvmerge(video_path)

if "error" not in metadata:
    print(f"File: {metadata['file_name']}")
    for track in metadata['tracks']:
        print(f"Track {track['id']}: {track['type']} ({track['codec']})")
```

## Nix Environment
All three tools are automatically installed when using the project's Nix flake:
```bash
nix develop
```
