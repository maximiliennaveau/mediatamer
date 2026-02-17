from pathlib import Path
from typing import Dict, Any


def parse_filename(path: Path) -> Dict[str, Any]:
    """Parse filename and parent folders to produce candidate metadata.

    This is a lightweight wrapper that tries to extract show, season and
    episode from the filename/path. If `guessit` is available it will be
    used; otherwise a simple fallback parser is applied.
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

    name = path.name
    try:
        from guessit import guessit
        gi = guessit(name)
        out['show'] = gi.get('title') or gi.get('series')
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
    except Exception:
        # basic fallback: look for Sxx or sxx patterns and t00 style
        import re
        m = re.search(r'[sS](\d{1,2})', name)
        if m:
            try:
                out['season'] = int(m.group(1))
                out['confidence'] += 0.3
            except Exception:
                pass
        m = re.search(r'[tT](\d{1,2})', name)
        if m:
            try:
                out['episode'] = int(m.group(1)) + 1
                out['episode_is_explicit'] = False
                out['confidence'] += 0.3
            except Exception:
                pass
        
        # Infer show and season from parent dir
        p = path.parent
        if p:
            pn = p.name
            
            # Robust pattern: Show_S9_DVD1 or Similar
            m = re.search(r'(.+?)_?[sS](\d+)(?:_?[dD][vV][dD](\d+))?', pn, re.I)
            if m:
                raw_show = m.group(1).replace('_', ' ')
                out['season'] = int(m.group(2))
                
                # Special case normalization
                if raw_show.lower() in ('dr who', 'doctor who'):
                    out['show'] = 'Doctor Who'
                else:
                    out['show'] = raw_show.title()
                out['confidence'] += 0.4
            else:
                # Basic fallback if regex fails
                if 'doctor' in pn.lower() or 'who' in pn.lower():
                    out['show'] = 'Doctor Who'
                    out['confidence'] += 0.1
                
                m2 = re.search(r'[sS](\d+)', pn)
                if m2:
                    out['season'] = int(m2.group(1))
                    out['confidence'] += 0.1

    return out
