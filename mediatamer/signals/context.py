import re
from pathlib import Path
from typing import Optional, Tuple
from mediatamer.utils import normalize_show_name

def extract_season_and_dvd(name: str) -> Tuple[Optional[int], Optional[int]]:
    """Extract season and DVD numbers from a string."""
    season = None
    dvd = None
    
    # Season: S09 or Season 9
    m_s = re.search(r'[Ss](?P<season>\d{1,2})|Season[ ._-]?(?P<season2>\d{1,2})', name, re.I)
    if m_s:
        val = m_s.group('season') or m_s.group('season2')
        season = int(val) if val else None
        
    # DVD: DVD1 or Disc 1
    m_d = re.search(r'(?:DVD|Disc|D)[._-]?(\d+)', name, re.I)
    if m_d:
        dvd = int(m_d.group(1))
        
    return season, dvd

def infer_context_from_path(file_path: Path, root_path: Optional[Path] = None) -> Tuple[Optional[str], Optional[int], Optional[int]]:
    """Infer Show Name, Season and DVD by walking up the directory tree.
    
    Returns: (show_name, season_number, dvd_number)
    """
    show_name = None
    season_number = None
    dvd_number = None
    
    # Resolve paths
    curr = file_path.resolve().parent
    root = root_path.resolve() if root_path else None
    limit = root.parent if root else Path('/')
    
    path_parts = []
    tmp = curr
    while tmp != limit and tmp != tmp.parent:
        path_parts.append(tmp)
        if root and tmp == root:
            break
        tmp = tmp.parent

    # Search from deepest to shallowest
    for d in path_parts:
        name = d.name
        
        # Pattern: Show_S9_DVD3
        m = re.search(r'(.+?)_?[sS](\d+)(?:_?[dD][vV][dD](\d+))?', name, re.I)
        if m:
            potential_show = m.group(1)
            potential_season = int(m.group(2))
            potential_dvd = int(m.group(3)) if m.group(3) else None
            
            if not show_name:
                show_name = normalize_show_name(potential_show)
            if season_number is None:
                season_number = potential_season
            if dvd_number is None:
                dvd_number = potential_dvd
            break

        # Fallback: Individual parts
        s, d_num = extract_season_and_dvd(name)
        if s is not None and season_number is None:
            season_number = s
            if not show_name and d.parent != limit:
                 show_name = normalize_show_name(d.parent.name)
        if d_num is not None and dvd_number is None:
            dvd_number = d_num

    show_name = normalize_show_name(show_name)
    
    return show_name, season_number, dvd_number
