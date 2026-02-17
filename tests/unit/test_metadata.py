import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

from mediatamer.get_tv_shows_metadata import get_tv_shows_metadata


DATA_DIR = Path('/data/videos/unsorted_videos/Doctor_Who_S9_DVD3')


def get_api_key():
    # Implement logic to retrieve the TMDB API key, e.g., from environment variable or config file
    api_file = Path(__file__).parent.parent.parent / 'tmdb_api_key.txt'
    return api_file.read_text().strip()


DATA_DIR = Path('/data/videos/unsorted_videos/Doctor_Who_S9_DVD3')


class TestDVDMetadataExtraction(unittest.TestCase):
    @patch('builtins.open', new_callable=MagicMock)
    @patch('pathlib.Path.mkdir')
    @patch('mediatamer.get_tv_shows_metadata.EpisodeMatcher') 
    @patch('pathlib.Path.iterdir')
    def test_parsing_doctor_who_season_9_dvd3(self, mock_iterdir, mock_matcher_cls, mock_mkdir, mock_open):
        # Setup Matcher Instance
        mock_matcher_instance = mock_matcher_cls.return_value
        mock_matcher_instance.show_name = "Doctor Who"
        mock_matcher_instance.season_number = 9
        mock_matcher_instance.episode_number = 1
        
        best_cand = {
            'episode': {'id': 999, 'name': 'The Magician\'s Apprentice', 'season_number': 9, 'episode_number': 1},
            'score': 100.0,
            'reasons': []
        }
        mock_matcher_instance.best_candidate = best_cand
        mock_matcher_instance.candidates = [best_cand]
        
        # Setup Mock Files
        f1 = MagicMock(spec=Path)
        f1.name = "B1_t00.mkv"
        f1.suffix = ".mkv"
        f1.is_file.return_value = True
        f1.stat.return_value.st_size = 1000
        f1.exists.return_value = True
        f1.__str__.return_value = str(DATA_DIR / "B1_t00.mkv")
        
        # Run
        dvd_dir = MagicMock(spec=Path)
        dvd_dir.name = "Doctor_Who_S9_DVD3"
        dvd_dir.exists.return_value = True
        dvd_dir.is_file.return_value = False
        dvd_dir.is_dir.return_value = True
        # mock files via glob
        dvd_dir.glob.return_value = [f1]
        
        # Call the function under test (API)
        data = get_tv_shows_metadata(dvd_dir, api_key="DUMMY_KEY")
        
        # Assertions
        self.assertIsInstance(data, dict)
        self.assertEqual(data['summary']['analyzed'], 1)
        mock_matcher_instance.find_metadata.assert_called()
        self.assertEqual(data['files'][0]['status'], 'MATCH')

if __name__ == '__main__':
    unittest.main()
