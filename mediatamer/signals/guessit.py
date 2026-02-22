from pathlib import Path
from typing import Dict, Any
import guessit


def extract_from_guessit(path: Path) -> Dict[str, Any]:
    """Parse filename and parent folders to produce candidate metadata.

    This is a lightweight wrapper that tries to extract show, season and
    episode from the filename/path.
    """
    out = {
        'show': None,
        'season': None,
        'episode': None,
        'episode_is_explicit': False,
        'title': None,
        'source': 'filename',
        'confidence': 0.0,
    }

    # Create the full path as a fake filename to help guessit
    name = str(path).replace('/', '_')
    gi = guessit(name)
    out['show'] = gi.get('series')
    out['season'] = gi.get('season')
    out['episode'] = None
    # guessit can return episode/numeric or episodes list
    ep = gi.get('episode') or gi.get('episode_number')
    if isinstance(ep, (list, tuple)) and ep:
        out['episode'] = ep[0]
    elif ep:
        out['episode'] = ep
    out['episode_is_explicit'] = True if out['episode'] else False
    out['title'] = gi.get('episode_title') or gi.get('title')
    out['confidence'] = float(gi.get('confidence', 0.0)) if gi.get(
        'confidence') is not None else 0.0
    out['source'] = 'guessit'
    return out
