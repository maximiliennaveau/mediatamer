from pathlib import Path
from typing import Dict, Any

from mediatamer.metadata import ffprobe_json


def get_technical_metadata(path: Path) -> Dict[str, Any]:
    """Return technical metadata extracted with ffprobe.

    Returns a dict with keys: duration (seconds), format_name, size, bit_rate,
    video (stream dict), audios (list), subtitles (list), streams (raw list).
    """
    j = ffprobe_json(path)
    fmt = j.get('format', {})
    out = {
        'duration': float(fmt.get('duration')) if fmt.get('duration') else None,
        'format_name': fmt.get('format_name'),
        'size': int(fmt.get('size')) if fmt.get('size') else None,
        'bit_rate': int(fmt.get('bit_rate')) if fmt.get('bit_rate') else None,
        'streams': j.get('streams', []),
        'video': None,
        'audios': [],
        'subtitles': [],
    }

    for s in j.get('streams', []):
        t = s.get('codec_type')
        if t == 'video' and out['video'] is None:
            out['video'] = s
        elif t == 'audio':
            out['audios'].append(s)
        elif t == 'subtitle':
            out['subtitles'].append(s)

    return out
