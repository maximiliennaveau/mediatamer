import argparse
from pathlib import Path

def add_common_arguments(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """Add common arguments like --config and --no-cache to a parser."""
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=None,
        help="Path to config file",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Ignore cached metadata and re-run all signals",
    )
    return parser
