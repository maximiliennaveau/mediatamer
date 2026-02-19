import unittest
from unittest import skip
from unittest.mock import MagicMock, patch
from pathlib import Path

from mediatamer.matcher import EpisodeMatcher

class TestMatcher(unittest.TestCase):
    DATA_DIR = Path('/data/videos/unsorted_videos/Doctor_Who_S9_DVD3')
    TMDB_API_KEY = "DUMMY_KEY" # Mocked

    @patch('mediatamer.matcher.requests.get')
    def setUp(self, mock_get):
        # Mock the API responses needed for finding metadata
        # 1. Search for Show -> Doctor Who
        # 2. Episode Group -> Season 9 Episodes
        
        self.mock_show_search = {
            'results': [{'id': 57243, 'name': 'Doctor Who', 'first_air_date': '2005-03-26'}]
        }
        self.mock_group_episodes = {
            'episodes': [
                 {'show': 'Doctor Who', 'episode_number': 7, 'season_number': 9, 'name': 'The Zygon Invasion', 'id': 1, 'runtime': 45},
                 {'show': 'Doctor Who', 'episode_number': 8, 'season_number': 9, 'name': 'The Zygon Inversion', 'id': 2, 'runtime': 45},
                 {'show': 'Doctor Who', 'episode_number': 9, 'season_number': 9, 'name': 'Sleep No More', 'id': 3, 'runtime': 45},
            ]
        }

        # Configure the mock to return these responses in order
        # 1. Search show
        # 2. Get season
        # 3. Get credits for E7
        # 4. Get credits for E8
        # 5. Get credits for E9
        mock_get.side_effect = [
            MagicMock(ok=True, json=lambda: self.mock_show_search),
            MagicMock(ok=True, json=lambda: self.mock_group_episodes),
            MagicMock(ok=True, json=lambda: {'crew': []}),
            MagicMock(ok=True, json=lambda: {'crew': []}),
            MagicMock(ok=True, json=lambda: {'crew': []}),
        ]

        # Setup Matcher with a mock path
        self.mock_path = MagicMock(spec=Path)
        self.mock_path.exists.return_value = True
        self.mock_path.parent.name = "Doctor_Who_S9_DVD3"
        self.mock_path.name = "B1_t00.mkv"
        self.mock_path.__str__.return_value = "/data/videos/unsorted_videos/Doctor_Who_S9_DVD3/B1_t00.mkv"

        # Mock signal extractors to avoid real FS access during init/find
        with patch('mediatamer.signals.unified.MediaSignals.from_path') as mock_media_signals, \
             patch('mediatamer.matcher.parse_filename') as mock_parse, \
             patch('mediatamer.matcher.extract_subtitle_text') as mock_sub, \
             patch('mediatamer.matcher.extract_credits_text') as mock_credits:
            
            m = MagicMock()
            m.duration = 45 * 60
            m.has_chapters = False
            m.chapters = []
            m.embedded_title = "The Zygon Invasion"
            mock_media_signals.return_value = m

            mock_parse.return_value = {'season': None, 'episode': None}
            mock_sub.return_value = "The Zygon Invasion"
            mock_credits.return_value = "The Zygon Invasion\nDoctor Who"

            self.matcher = EpisodeMatcher(self.mock_path, tmdb_api_key=self.TMDB_API_KEY)
            self.matcher.find_metadata()

    def test_find_season_number(self):
        """Test inferred season number."""
        self.assertEqual(self.matcher.season_number, 9)

    def test_find_episode_number(self):
        """Test matched episode number (based on mocked subtitle match)."""
        self.assertEqual(self.matcher.episode_number, 7)

    def test_find_show_name(self):
        """Test fetched show name."""
        self.assertEqual(self.matcher.show_name, "Doctor Who")

    @patch('mediatamer.matcher.requests.get')
    @patch('mediatamer.signals.unified.MediaSignals.from_path')
    @patch('mediatamer.matcher.extract_subtitle_text')
    @patch('mediatamer.matcher.extract_credits_text')
    def test_global_index_matching(self, mock_credits, mock_sub, mock_media_signals, mock_get):
        """Test that has_global_indices hint correctly boosts global index match."""
        # 1. Setup mock path with a global index (t04 -> Episode 5)
        path = MagicMock(spec=Path)
        path.exists.return_value = True
        path.name = "B2_t04.mkv"
        path.parent.name = "Doctor_Who_S10_DVD2"
        
        # 2. Mock TMDB response for Season 10
        mock_get.side_effect = [
            MagicMock(ok=True, json=lambda: {'results': [{'id': 57243, 'name': 'Doctor Who'}]}),
            MagicMock(ok=True, json=lambda: {'episodes': [{'episode_number': 5, 'name': 'Oxygen', 'id': 50, 'runtime': 45}]}),
            MagicMock(ok=True, json=lambda: {'crew': []}), # credits for E5
        ]
        
        m = MagicMock()
        m.duration = 45 * 60
        m.has_chapters = False
        m.chapters = []
        m.embedded_title = ""
        mock_media_signals.return_value = m

        mock_sub.return_value = "" # No text match
        mock_credits.return_value = "" # No credit match
        
        # 3. Test WITH global index hint
        matcher = EpisodeMatcher(path, tmdb_api_key="KEY", show_name="Doctor Who", season_number=10)
        matcher.has_global_indices = True
        matcher.find_metadata()
        
        self.assertEqual(matcher.episode_number, 5)
        # Verify score is high due to global index verified boost
        self.assertTrue(any("Global index match" in r for r in matcher.best_candidate['reasons']))

if __name__ == '__main__':
    unittest.main()
