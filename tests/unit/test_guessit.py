import unittest
from pathlib import Path

from mediatamer.signals.guessit import (
  _extract_guessit,
  _extract_heuristics,
  _is_makemkv_filename
)
from mediatamer.signals.video_metadata import VideoMetadata


class TestGuessit(unittest.TestCase):
    def test_Doctor_Who_S9_DVD1_B1_t00(self):
        # Test against a known path
        path = Path("/data/videos/Doctor_Who_S9_DVD1/B1_t00.mkv")

        metadata = VideoMetadata(path=path)
        _extract_guessit(metadata)
        _extract_heuristics(metadata)

        self.assertEqual(metadata.guessit["heuristics"]["show"], "Doctor Who")
        self.assertEqual(metadata.guessit["heuristics"]["season"], 9)
        # self.assertEqual(metadata.guessit["heuristics"]["episode"], None)
        # self.assertEqual(metadata.guessit["heuristics"]["dvd"], 1)
        # self.assertEqual(metadata.guessit["heuristics"]["part"], None)
        # self.assertEqual(metadata.guessit["heuristics"]["title"], None)

    def test_Doctor_Who_S9_DVD1_B1_t01(self):
        # Test against a known path
        path = Path("/data/videos/Doctor_Who_S9_DVD1/B1_t01.mkv")

        metadata = VideoMetadata(path=path)
        _extract_guessit(metadata)
        _extract_heuristics(metadata)

        assert metadata.guessit["heuristics"]["show"] == "Doctor Who"
        assert metadata.guessit["heuristics"]["season"] == 9
        # assert metadata.guessit["heuristics"]["episode"] is None
        # assert metadata.guessit["heuristics"]["dvd"] == 1
        # assert metadata.guessit["heuristics"]["part"] is None
        # assert metadata.guessit["heuristics"]["title"] is None

    def test_Doctor_Who_S9_DVD1_B1_t02(self):
        # Test against a known path
        path = Path("/data/videos/Doctor_Who_S9_DVD1/B1_t02.mkv")

        metadata = VideoMetadata(path=path)
        _extract_guessit(metadata)
        _extract_heuristics(metadata)

        assert metadata.guessit["heuristics"]["show"] == "Doctor Who"
        assert metadata.guessit["heuristics"]["season"] == 9
        # assert metadata.guessit["heuristics"]["episode"] is None
        # assert metadata.guessit["heuristics"]["dvd"] == 1
        # assert metadata.guessit["heuristics"]["part"] is None
        # assert metadata.guessit["heuristics"]["title"] is None

    def test_Doctor_Who_S9_DVD1_B1_t03(self):
        # Test against a known path
        path = Path("/data/videos/Doctor_Who_S9_DVD1/B1_t03.mkv")

        metadata = VideoMetadata(path=path)
        _extract_guessit(metadata)
        _extract_heuristics(metadata)

        assert metadata.guessit["heuristics"]["show"] == "Doctor Who"
        assert metadata.guessit["heuristics"]["season"] == 9
        # assert metadata.guessit["heuristics"]["episode"] is None
        # assert metadata.guessit["heuristics"]["dvd"] == 1
        # assert metadata.guessit["heuristics"]["part"] is None
        # assert metadata.guessit["heuristics"]["title"] is None

    def test_is_makemkv_filename(self):
        self.assertTrue(_is_makemkv_filename("B1_t00.mkv"))
        self.assertTrue(_is_makemkv_filename("B2_t01.mkv"))
        self.assertFalse(_is_makemkv_filename("Doctor_Who_S9_DVD1_B1_t00.mkv"))
        self.assertFalse(_is_makemkv_filename("random_video.mkv"))


if __name__ == "__main__":
    unittest.main()
