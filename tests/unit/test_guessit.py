import unittest
from pathlib import Path

from mediatamer.signals.guessit import extract_guessit, extract_heuristics
from mediatamer.signals.video_metadata import VideoMetadata


class TestGuessit(unittest.TestCase):
    def test_Doctor_Who_S9_DVD1_B1_t00(self):
        # Test against a known path
        path = Path("/data/videos/Doctor_Who_S9_DVD1/B1_t00.mkv")

        metadata = VideoMetadata(path=path)
        extract_guessit(metadata)
        extract_heuristics(metadata)

        self.assertEqual(metadata.heuristics["show"], "Doctor Who")
        self.assertEqual(metadata.heuristics["season"], 9)
        self.assertEqual(metadata.heuristics["episode"], None)
        self.assertEqual(metadata.heuristics["dvd"], 1)
        self.assertEqual(metadata.heuristics["part"], None)
        self.assertEqual(metadata.heuristics["title"], None)


def test_Doctor_Who_S9_DVD1_B1_t01(self):
    # Test against a known path
    path = Path("/data/videos/Doctor_Who_S9_DVD1/B1_t01.mkv")

    metadata = VideoMetadata(path=path)
    extract_guessit(metadata)
    extract_heuristics(metadata)

    assert metadata.heuristics["show"] == "Doctor Who"
    assert metadata.heuristics["season"] == 9
    assert metadata.heuristics["episode"] is None
    assert metadata.heuristics["dvd"] == 1
    assert metadata.heuristics["part"] is None
    assert metadata.heuristics["title"] is None


def test_Doctor_Who_S9_DVD1_B1_t02(self):
    # Test against a known path
    path = Path("/data/videos/Doctor_Who_S9_DVD1/B1_t02.mkv")

    metadata = VideoMetadata(path=path)
    extract_guessit(metadata)
    extract_heuristics(metadata)

    assert metadata.heuristics["show"] == "Doctor Who"
    assert metadata.heuristics["season"] == 9
    assert metadata.heuristics["episode"] is None
    assert metadata.heuristics["dvd"] == 1
    assert metadata.heuristics["part"] is None
    assert metadata.heuristics["title"] is None


if __name__ == "__main__":
    unittest.main()
