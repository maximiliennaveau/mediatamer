import pytest
from pathlib import Path

from mediatamer.extract_subtitle import extract_subtitle_text


DATA_DIR = Path('/data/videos/unsorted_videos/Doctor_Who_S9_DVD3')


def test_b1_t00_extracts_or_returns_none():
    p = DATA_DIR / 'B1_t00.mkv'
    if not p.exists():
        pytest.skip(f"Test file missing: {p}")
        return
    res = extract_subtitle_text(p)
    assert (res is None) or (isinstance(res, str) and len(res) > 0)


def test_all_files_do_not_raise():
    for f in sorted(DATA_DIR.glob('*.mkv')):
        res = extract_subtitle_text(f)
        assert (res is None) or isinstance(res, str)
