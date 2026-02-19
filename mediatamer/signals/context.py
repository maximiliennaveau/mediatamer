import re
from pathlib import Path
from typing import Optional, Tuple

def infer_context_from_path(file_path: Path) -> Tuple[Optional[str], Optional[int]]:
    """Infer Show Name and Season from directory structure.
    
    Example: "Doctor_Who_S9_DVD3" -> Show: Doctor Who, Season: 9
    """
    parent_dir = file_path.parent.name
    
    # Pattern: Show_S9_DVD3
    m = re.search(r'(.+?)_?[sS](\d+)(?:_?[dD][vV][dD](\d+))?', parent_dir, re.I)
    if m:
        raw_show = m.group(1).replace('_', ' ')
        season_number = int(m.group(2))
        
        # Special case normalization
        if raw_show.lower() in ('dr who', 'doctor who'):
            show_name = 'Doctor Who'
        else:
            show_name = raw_show.title()

        # Extras detection (heuristic: files starting with C)
        if file_path.name.startswith('C'):
            show_name += " - Extras"
            
        return show_name, season_number
    
    return None, None
