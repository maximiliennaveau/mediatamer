"""Unit tests for mediatamer.mkv_metadata.write_mkv_metadata.

The test converts a resource MP4 to a temporary MKV (using mkvmerge),
writes metadata into it, then reads the tags back with mkvpropedit/mkvinfo
to verify they were actually persisted.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from mediatamer.mkv_metadata import write_mkv_metadata
from mediatamer.signals.video_metadata import VideoMetadata

RESOURCE_DIR = Path(__file__).parent.parent / "resource"
SOURCE_MP4 = RESOURCE_DIR / "BigBuckBunny.mp4"

SAMPLE_FINAL_RESULT = {
    "series_full_name": "Test Show (2024)",
    "seasonNumber": 3,
    "number": 7,
    "name": "The Episode Title",
    "overview": "A brief summary of the test episode.",
    "aired": "2024-06-15",
    "year": "2024",
    "imdbId": "tt9999999",
    "id": 12345678,
}


def _read_mkv_tags(mkv_path: Path) -> dict[str, str]:
    """Extract global tags from an MKV file using mkvextract and parse the XML."""
    result = subprocess.run(
        ["mkvextract", str(mkv_path), "tags", "/dev/stdout"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return {}
    try:
        root = ET.fromstring(result.stdout)
    except ET.ParseError:
        return {}
    tags: dict[str, str] = {}
    for simple in root.iter("Simple"):
        name_el = simple.find("Name")
        val_el = simple.find("String")
        if name_el is not None and val_el is not None:
            tags[name_el.text or ""] = val_el.text or ""
    return tags


def _read_mkv_title(mkv_path: Path) -> str:
    """Read the segment title from MKV info output."""
    result = subprocess.run(
        ["mkvinfo", str(mkv_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    for line in result.stdout.splitlines():
        if "Title:" in line:
            return line.split("Title:", 1)[-1].strip()
    return ""


@unittest.skipUnless(shutil.which("mkvmerge"), "mkvmerge not found in PATH")
@unittest.skipUnless(shutil.which("mkvpropedit"), "mkvpropedit not found in PATH")
@unittest.skipUnless(SOURCE_MP4.exists(), f"Test resource not found: {SOURCE_MP4}")
class TestWriteMkvMetadata(unittest.TestCase):
    """Integration-style unit tests that write real tags into a temp MKV."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="mediatamer_test_")
        tmp_mkv = Path(self.tmp_dir) / "test_video.mkv"
        result = subprocess.run(
            ["mkvmerge", "-o", str(tmp_mkv), str(SOURCE_MP4)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode not in (0, 1):  # 1 = warnings, still OK
            self.skipTest(f"mkvmerge failed to create test MKV: {result.stderr}")
        self.mkv_path = tmp_mkv

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _write_and_read(self, metadata, **kwargs) -> tuple[bool, dict, str]:
        ok = write_mkv_metadata(self.mkv_path, metadata, **kwargs)
        tags = _read_mkv_tags(self.mkv_path)
        title = _read_mkv_title(self.mkv_path)
        return ok, tags, title

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------

    def test_returns_true_on_success(self):
        ok, _, _ = self._write_and_read({"final_result": SAMPLE_FINAL_RESULT})
        self.assertTrue(ok)

    def test_segment_title_is_set(self):
        _, _, title = self._write_and_read({"final_result": SAMPLE_FINAL_RESULT})
        self.assertEqual(title, "Test Show (2024) - S03E07 - The Episode Title")

    def test_tags_written_correctly(self):
        _, tags, _ = self._write_and_read({"final_result": SAMPLE_FINAL_RESULT})
        self.assertEqual(tags.get("TITLE"), "The Episode Title")
        self.assertEqual(tags.get("SERIES_TITLE"), "Test Show (2024)")
        self.assertEqual(tags.get("SEASON_NUMBER"), "3")
        self.assertEqual(tags.get("EPISODE_NUMBER"), "7")
        self.assertEqual(tags.get("YEAR"), "2024")
        self.assertEqual(tags.get("DATE_RELEASED"), "2024-06-15")
        self.assertEqual(tags.get("IMDB"), "tt9999999")
        self.assertEqual(tags.get("TVDB"), "12345678")

    def test_summary_and_description_written(self):
        _, tags, _ = self._write_and_read({"final_result": SAMPLE_FINAL_RESULT})
        self.assertEqual(tags.get("SUMMARY"), "A brief summary of the test episode.")
        self.assertEqual(
            tags.get("DESCRIPTION"), "A brief summary of the test episode."
        )

    def test_video_metadata_dataclass_accepted(self):
        meta = VideoMetadata(
            path=self.mkv_path,
            final_result=SAMPLE_FINAL_RESULT,
        )
        ok, tags, title = self._write_and_read(meta)
        self.assertTrue(ok)
        self.assertEqual(tags.get("TITLE"), "The Episode Title")
        self.assertEqual(title, "Test Show (2024) - S03E07 - The Episode Title")

    def test_returns_false_for_nonexistent_file(self):
        ok = write_mkv_metadata(
            "/tmp/does_not_exist_xyz.mkv", {"final_result": SAMPLE_FINAL_RESULT}
        )
        self.assertFalse(ok)

    def test_set_title_false_still_writes_tags(self):
        ok, tags, _ = self._write_and_read(
            {"final_result": SAMPLE_FINAL_RESULT}, set_title=False
        )
        self.assertTrue(ok)
        self.assertEqual(tags.get("TITLE"), "The Episode Title")

    def test_empty_final_result_does_not_crash(self):
        ok = write_mkv_metadata(self.mkv_path, {"final_result": {}})
        self.assertTrue(ok)

    def test_plain_dict_without_final_result_key(self):
        """Passing a dict with no 'final_result' should not crash."""
        ok = write_mkv_metadata(self.mkv_path, {})
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()
