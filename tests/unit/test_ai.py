import unittest
from pathlib import Path

from mediatamer.signals.ai import run_ai


class TestAIEpisodeMatcher(unittest.TestCase):
    def setUp(self):
        self.config = {"tmbd-api-key": "test"}
        self.matcher = AIEpisodeMatcher(self.config)

    @patch("mediatamer.signals.ai_episode_matcher.run_ai")
    @patch("mediatamer.signals.tmdb.fetch_tmdb_episodes")
    def test_match(self, mock_fetch, mock_run_ai):
        # Mock dependencies
        mock_fetch.return_value = (None, [])
        mock_run_ai.return_value = "{}"

        # Create a dummy VideoMetadata object
        meta = MagicMock()
        meta.path = Path("test.mkv")
        meta.guessit = {"show": "Test Show", "season": 1}
        meta.technical = MagicMock()
        meta.technical.to_legacy_dict.return_value = {}
        meta.subtitles = ""

        self.matcher.match(meta)

        self.assertIn("error", meta.ai_match)
        self.assertIn("No TMDB candidates found", meta.ai_match["error"])


if __name__ == "__main__":
    unittest.main()
