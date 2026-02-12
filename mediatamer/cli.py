"""Top-level `mediatamer` CLI that dispatches subcommands to bundled tools.

Usage:
  mediatamer organize [args...]   # calls mediatamer.organize:main
  mediatamer metadata [args...]   # calls mediatamer.extract_mkv_metadata:main
"""
from __future__ import annotations

import sys
import importlib


def _call_module_main(module_name: str, argv: list[str]) -> int | None:
    mod = importlib.import_module(module_name)
    old_argv = sys.argv
    try:
        sys.argv = [old_argv[0]] + argv
        if hasattr(mod, "main"):
            return mod.main()
        raise SystemExit(f"Module {module_name} has no main() entry")
    finally:
        sys.argv = old_argv


def main() -> int | None:
    if len(sys.argv) <= 1:
        print("Usage: mediatamer <organize|metadata> [args...]")
        return 2

    cmd = sys.argv[1].lower()
    rest = sys.argv[2:]

    if cmd == "organize":
        return _call_module_main("mediatamer.organize", rest)
    if cmd in ("metadata", "meta"):
        return _call_module_main("mediatamer.metadata", rest)

    print(
        f"Unknown command: {cmd}\nUsage: mediatamer <organize|metadata> [args...]")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
