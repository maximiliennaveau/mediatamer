from pathlib import Path
import unittest

from mediatamer.extract_subtitle import extract_subtitle_text


class TestExtractSubtitle(unittest.TestCase):
    DATA_DIR = Path("/data/videos/unsorted_videos/Doctor_Who_S9_DVD3")

    def test_b1_t00_extracts(self):
        p = self.DATA_DIR / "B1_t00.mkv"
        if not p.exists():
            self.skipTest(f"Test file missing: {p}")
            return
        res = extract_subtitle_text(p)
        # print(f"Extracted subtitles for the file {p}:\n{res}")
        self.assertTrue(isinstance(res, str) and len(res) > 0)

    def test_all_files_extract(self):
        for f in sorted(self.DATA_DIR.glob("*.mkv")):
            res = extract_subtitle_text(f)
            # print(f"Extracted subtitles for the file {f}:\n{res}")
            self.assertTrue(isinstance(res, str) and len(res) > 0)


if __name__ == "__main__":
    unittest.main()
