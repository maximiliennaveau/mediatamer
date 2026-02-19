import subprocess
import json
from pathlib import Path
from typing import Dict, Any

def extract_metadata_mediainfo(path: Path) -> Dict[str, Any]:
    """
    Extract metadata from a video file using mediainfo --Output=JSON and return it as a dictionary.
    
    Args:
        path: Path to the video file.
        
    Returns:
        A dictionary containing the JSON output from mediainfo.
    """
    if not path.exists():
        return {"error": f"File not found: {path}"}

    cmd = ["mediainfo", "--Output=JSON", str(path)]
    
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return json.loads(res.stdout)
    except subprocess.CalledProcessError as e:
        return {"error": "mediainfo failed", "stderr": e.stderr}
    except Exception as e:
        return {"error": str(e)}
