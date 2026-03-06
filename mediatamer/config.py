"""MediaTamer configuration loading."""

import yaml
from pathlib import Path
from typing import Dict, Any, Optional

DEFAULT_CONFIG_LOCATIONS = [
    Path(__file__).parent.parent / "secrets" / "mediatamer-config.yml",
    Path.home() / ".config" / "mediatamer" / "config.yml",
    Path("/data/videos/secrets/mediatamer-config.yml"),
]


def load_config(path: Optional[Path] = None) -> Dict[str, Any]:
    """Load configuration from a YAML file."""
    if path is None:
        path = find_config()
        if path is None:
            return {}

    if not path.exists():
        return {}

    try:
        with open(path, "r") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        print(f"Warning: Failed to load config from {path}: {e}")
        return {}


def find_config() -> Optional[Path]:
    """Search for a config file in default locations."""
    for loc in DEFAULT_CONFIG_LOCATIONS:
        if loc.exists():
            return loc
    return None
