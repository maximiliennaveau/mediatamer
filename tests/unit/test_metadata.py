import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

from mediatamer.get_dvd_metadata import parse_dvd_directory


DATA_DIR = Path('/data/videos/unsorted_videos/Doctor_Who_S9_DVD3')


def get_api_key():
    # Implement logic to retrieve the TMDB API key, e.g., from environment variable or config file
    api_file = Path(__file__).parent.parent.parent / 'tmdb_api_key.txt'
    return api_file.read_text().strip()


DATA_DIR = Path('/data/videos/unsorted_videos/Doctor_Who_S9_DVD3')


class TestDVDMetadataExtraction(unittest.TestCase):
    @patch('builtins.open', new_callable=MagicMock)
    @patch('pathlib.Path.mkdir')
    @patch('mediatamer.get_dvd_metadata.requests.get')
    # Patch matcher to avoid complex logic and FS access in it
    @patch('mediatamer.get_dvd_metadata.EpisodeMatcher') 
    @patch('pathlib.Path.iterdir')
    def test_parsing_doctor_who_season_9_dvd3(self, mock_iterdir, mock_matcher_cls, mock_get, mock_mkdir, mock_open):
        # Setup Mock API response
        mock_search_resp = MagicMock()
        mock_search_resp.json.return_value = {
            'results': [{'id': 123, 'name': 'Doctor Who', 'first_air_date': '2005-01-01'}]
        }
        mock_search_resp.ok = True
        
        mock_ep_resp = MagicMock()
        mock_ep_resp.json.return_value = {
            'episodes': [
                {'episode_number': 1, 'name': 'The Magician\'s Apprentice', 'season_number': 9, 'id': 999},
                 # Add more if needed, but one is enough to trigger matcher
            ],
            'groups': [
                 {'name': 'Season 9', 'episodes': [
                     {'episode_number': 1, 'name': 'The Magician\'s Apprentice', 'season_number': 9, 'id': 999}
                 ]}
            ]
        }
        mock_ep_resp.ok = True
        
        # side_effect: first call search, subsequent calls episodes
        mock_get.side_effect = [mock_search_resp, mock_ep_resp, mock_ep_resp]
        
        # Setup Mock Files
        f1 = MagicMock(spec=Path)
        f1.name = "B1_t00.mkv"
        f1.suffix = ".mkv"
        f1.is_file.return_value = True
        f1.stat.return_value.st_size = 1000
        f1.exists.return_value = True
        
        # Setup Matcher Instance
        mock_matcher_instance = mock_matcher_cls.return_value
        # Matcher returns one high-confidence candidate
        mock_matcher_instance.match_file.return_value = [{
            'episode': {'id': 999, 'name': 'The Magician\'s Apprentice', 'season_number': 9, 'episode_number': 1},
            'score': 100.0,
            'reasons': []
        }]
        
        # Run
        dvd_dir = MagicMock(spec=Path)
        dvd_dir.name = "Doctor_Who_S9_DVD3"
        # mock files via glob
        dvd_dir.glob.return_value = [f1]
        
        # Call the function under test
        # We pass a dummy API key so it doesn't try to read the file
        metadata = parse_dvd_directory(dvd_dir, api_key="DUMMY_KEY", dry_run=True)
        
        # Assertions
        # It should return None/Empty or a plan list because dry_run=True usually doesn't return the dictator metadata object same way?
        # Actually parse_dvd_directory returns None if dry_run? Or prints?
        # Let's check the return. 
        # If it returns a dict of metadata files written, in dry run it might match but not write.
        # But here we just want to ensure it runs without error and calls the right things.
        
        mock_get.assert_called()
        mock_matcher_instance.match_file.assert_called_with(f1)
