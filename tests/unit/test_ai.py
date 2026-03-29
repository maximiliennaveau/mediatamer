import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from mediatamer.signals.ai_episode_matcher import AIEpisodeMatcher
from mediatamer.signals.video_metadata import VideoMetadata

class TestAIEpisodeMatcher(unittest.TestCase):
    def setUp(self):
        self.matcher = AIEpisodeMatcher()

    @patch("mediatamer.signals.ai_episode_matcher.run_ai")
    @patch("mediatamer.signals.tmdb.fetch_tmdb_episodes")
    def test_match(self, mock_fetch, mock_run_ai):
        # Mock dependencies
        mock_fetch.return_value = (None, [])
        mock_run_ai.return_value = "{}"

        # Create a dummy VideoMetadata object
        p = Path("test.mkv")
        meta = VideoMetadata(path=p)
        meta.guessit = {"show": "Test Show", "season": 1}
        meta.technical = MagicMock()
        meta.technical.to_legacy_dict.return_value = {"duration": 1200}
        meta.subtitles = "Some subtitle text"

        self.matcher.match(meta)

        self.assertIn("error", meta.ai_match)
        self.assertIn("No TMDB candidates found", meta.ai_match["error"])


if __name__ == "__main__":
    unittest.main()
