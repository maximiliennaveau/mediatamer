import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
import os
import sys
import tempfile
import shutil

# Add the project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from mediatamer.cli.get_tv_shows_metadata import get_tv_shows_metadata


class TestPrefixDetection(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    @patch("mediatamer.signals.technical.get_technical_metadata")
    @patch("mediatamer.cli.get_tv_shows_metadata.EpisodeMatcher")
    def test_multi_prefix_detection_real_fs(self, mock_matcher_cls, mock_tech):
        """Test that A and B are detected as episodes, C as bonus using a real temp FS."""

        # Create dummy files: A1, A2, B1, B2, C1
        file_names = ["A1.mkv", "A2.mkv", "B1.mkv", "B2.mkv", "C1.mkv"]
        for name in file_names:
            (Path(self.test_dir) / name).touch()

        # Setup technical metadata mocks
        def technical_side_effect(path):
            name = Path(path).name
            if name.startswith("A"):
                return {"duration": 45 * 60}
            if name.startswith("B"):
                return {"duration": 43 * 60}
            return {"duration": 5 * 60}  # C

        mock_tech.side_effect = technical_side_effect

        # Setup Matcher mock to capture is_likely_episode calls
        matchers = []

        def matcher_init(path, api_key, **kwargs):
            m = MagicMock()
            m.candidates = []
            m.best_candidate = None
            m.show_name = "Show"
            m.season_number = 1
            m.episode_number = None
            # Store the path for easier assertions
            m._test_path = path
            matchers.append(m)
            return m

        mock_matcher_cls.side_effect = matcher_init

        # Run get_tv_shows_metadata
        get_tv_shows_metadata(Path(self.test_dir), "fake_key")

        # map m._test_path.name -> matcher
        results = {m._test_path.name: m for m in matchers}

        # Check results
        # A1, A2 (Should be likely)
        # B1, B2 (Should be likely, 43m is > 80% of 45m)
        # C1 (Should NOT be likely, 5m is < 80% of 45m)

        self.assertTrue(
            results["A1.mkv"].is_likely_episode, "A1 should be likely episode"
        )
        self.assertTrue(
            results["A2.mkv"].is_likely_episode, "A2 should be likely episode"
        )
        self.assertTrue(
            results["B1.mkv"].is_likely_episode, "B1 should be likely episode"
        )
        self.assertTrue(
            results["B2.mkv"].is_likely_episode, "B2 should be likely episode"
        )
        self.assertFalse(results["C1.mkv"].is_likely_episode, "C1 should be bonus")


if __name__ == "__main__":
    unittest.main()
