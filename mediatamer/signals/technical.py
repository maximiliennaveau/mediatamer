from pathlib import Path
from typing import Dict, Any

from mediatamer.metadata import ffprobe_json


from mediatamer.signals.unified import MediaSignals


def get_technical_metadata(path: Path) -> Dict[str, Any]:
    """Return technical metadata extracted with multiple tools (unified).

    Returns a dict compatible with legacy calls, but enriched with
    new signals like chapter counts.
    """
    signals = MediaSignals.from_path(path)
    return signals.to_legacy_dict()
