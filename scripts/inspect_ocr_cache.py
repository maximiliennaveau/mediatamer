#!/usr/bin/env python3
"""Inspect OCR filtered_text from a cache file to assess heuristic feasibility."""

import json
import re
import sys

cache_file = (
    sys.argv[1]
    if len(sys.argv) > 1
    else (
        "/data/videos/mediatamer_cache/"
        "aafc4d1fc1e16d300b7ceefae2ceb4159a24b8d308e0aa49df2d1f03dcae7c0d.json"
    )
)

with open(cache_file) as f:
    data = json.load(f)

ft = data["cast_profile"]["ocr_cache"]["filtered_text"]
lines = ft.split("\n")
print(f"Total chars in filtered_text: {len(ft)}")
print(f"Total lines: {len(lines)}")

name_re = re.compile(
    r"^[A-Za-z\u00C0-\u024F][A-Za-z\u00C0-\u024F'\-.]*"
    r"(\s[A-Za-z\u00C0-\u024F][A-Za-z\u00C0-\u024F'\-.]*)+$"
)

clean = [l.strip() for l in lines if name_re.match(l.strip()) and len(l.strip()) >= 5]
print(f"\nLines matching strict name pattern ({len(clean)} total):")
for l in clean:
    print(" ", repr(l))
