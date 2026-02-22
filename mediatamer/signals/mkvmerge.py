import subprocess
import json
from pathlib import Path
from typing import Dict, Any


def extract_metadata_mkvmerge(path: Path) -> Dict[str, Any]:
    """
    Extract metadata from an MKV file using mkvmerge -J and return it as a dictionary.

    Args:
        path: Path to the MKV file.

    Returns:
        A dictionary containing the JSON output from mkvmerge.
    """
    if not path.exists():
        return {"error": f"File not found: {path}"}

    cmd = ["mkvmerge", "-J", str(path)]

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return json.loads(res.stdout)
    except subprocess.CalledProcessError as e:
        return {"error": "mkvmerge failed", "stderr": e.stderr}
    except Exception as e:
        return {"error": str(e)}
