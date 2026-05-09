#!/usr/bin/env python3
"""
Debug helper: search TMDB /search/person for a name and print results + similarity.
Usage:
  - set TMDB_API_KEY env var or pass --key
  - python3 debug_tmdb_person_search.py "Jerna Coleman"
"""

import os
import sys
import json
import argparse
import requests
import difflib

from mediatamer.config import load_config

TMDB_SEARCH_URL = "https://api.themoviedb.org/3/search/person"


def search_person(api_key: str, query: str):
    resp = requests.get(
        TMDB_SEARCH_URL,
        params={"api_key": api_key, "query": query, "language": "en-US", "page": 1},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("query", nargs="?", default="Jerna Coleman")
    args = p.parse_args()

    api_key = load_config().get("tmdb-api-key")  # Load config to ensure env var is set
    assert api_key, (
        "TMDB API key not found in config or environment variable TMDB_API_KEY"
    )
    try:
        data = search_person(api_key, args.query)
    except Exception as e:
        print("TMDB request failed:", e)
        sys.exit(2)

    results = data.get("results", [])
    print(f"Total results: {len(results)}\n")
    print("Raw JSON (first 2000 chars):")
    print(json.dumps(data, indent=2, ensure_ascii=False)[:2000])
    print("\nTop results with similarity to query:")
    for i, r in enumerate(results[:10], start=1):
        name = r.get("name", "")
        ratio = difflib.SequenceMatcher(None, args.query.lower(), name.lower()).ratio()
        print(f"{i}. {name!r} (id={r.get('id')}) similarity={ratio:.3f}")
        known_for = [
            (k.get("title") or k.get("name")) for k in r.get("known_for", []) if k
        ]
        if known_for:
            print("   known_for:", ", ".join(known_for))

    if not results:
        print("No results returned by TMDB.")


if __name__ == "__main__":
    main()
