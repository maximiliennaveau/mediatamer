import unittest
from pathlib import Path

from mediatamer.signals.guessit import infer_context_from_path
from mediatamer.signals.video_metadata import VideoMetadata


class TestGuessit(unittest.TestCase):
    def test_infer_context_from_path(self):
        # Test against a known path
        path = Path("/data/videos/Doctor_Who_S9_DVD1/B1_t00.mkv")

        metadata = VideoMetadata(path=path)
        infer_context_from_path(metadata)

        self.assertEqual(metadata.guessit["show"], "Doctor Who")
        self.assertEqual(metadata.guessit["season"], 9)
        self.assertEqual(metadata.guessit["episode"], None)
        self.assertEqual(metadata.guessit["dvd"], 1)
        self.assertEqual(metadata.guessit["part"], None)
        self.assertEqual(metadata.guessit["title"], None)


if __name__ == "__main__":
    unittest.main()
