import unittest
from pathlib import Path

from mediatamer.get_tv_shows_metadata import get_tv_shows_metadata


from unittest.mock import patch, MagicMock

class TestGetTvShowsMetadata(unittest.TestCase):

    DATA_DIR = Path("/data/videos/unsorted_videos/Doctor_Who_S9_DVD3")
    
    @patch("pathlib.Path.read_text")
    def setUp(self, mock_read_text):
        mock_read_text.return_value = "DUMMY_KEY"
        self.API_KEY = "DUMMY_KEY"

    results = {
        "B1_t00.mkv": {
            "show": "Doctor Who",
            "season": 9,
            "episode": 7,
            "title": "The Zygon Invasion",
            "source": "guessit",
            "confidence": 0.0,
        },
        "B2_t01.mkv": {
            "show": "Doctor Who",
            "season": 9,
            "episode": 8,
            "title": "The Zygon Inversion",
            "source": "guessit",
            "confidence": 0.0,
        },
        "B3_t02.mkv": {
            "show": "Doctor Who",
            "season": 9,
            "episode": 9,
            "title": "Sleep No More",
            "source": "guessit",
            "confidence": 0.0,
        },
        "C1_t03.mkv": {
            "show": "Doctor Who - bonus",
            "season": 9,
            "episode": 1,
            "title": "No title",
        },
        "C2_t04.mkv": {
            "show": "Doctor Who - bonus",
            "season": 9,
            "episode": 2,
            "title": "No title",
        },
        "C3_t05.mkv": {
            "show": "Doctor Who - bonus",
            "season": 9,
            "episode": 3,
            "title": "No title",
        },
        "C4_t06.mkv": {
            "show": "Doctor Who - bonus",
            "season": 9,
            "episode": 4,
            "title": "No title",
        },
        "C5_t07.mkv": {
            "show": "Doctor Who - bonus",
            "season": 9,
            "episode": 5,
            "title": "No title",
        },
    }

    @patch("mediatamer.signals.unified.MediaSignals.from_path")
    @patch("mediatamer.matcher.requests.get")
    def test_parsing_doctor_who_season_9_dvd3(self, mock_get, mock_media_signals):
        # 1. Mock MediaSignals for all files
        def mock_signals(path, **kwargs):
            m = MagicMock()
            m.duration = 2700 if path.name.startswith('B') else 600
            m.has_chapters = False
            m.chapters = []
            m.embedded_title = None
            return m
        mock_media_signals.side_effect = mock_signals
        
        # 2. Mock TMDB responses
        def mock_tmdb_responses(url, params=None, **kwargs):
            mock = MagicMock()
            mock.ok = True
            if "search/tv" in url:
                mock.json.return_value = {'results': [{'id': 57243, 'name': 'Doctor Who'}]}
            elif "season/9" in url and "episode" not in url:
                 mock.json.return_value = {'episodes': [
                     {'episode_number': 7, 'name': 'The Zygon Invasion', 'id': 1, 'runtime': 45},
                     {'episode_number': 8, 'name': 'The Zygon Inversion', 'id': 2, 'runtime': 45},
                     {'episode_number': 9, 'name': 'Sleep No More', 'id': 3, 'runtime': 45},
                 ]}
            elif "credits" in url:
                 mock.json.return_value = {'crew': []}
            else:
                 mock.json.return_value = {}
            return mock
            
        mock_get.side_effect = mock_tmdb_responses
        
        # 3. Mock file system for recursive scan
        with patch("pathlib.Path.rglob") as mock_rglob, \
             patch("pathlib.Path.exists") as mock_exists, \
             patch("pathlib.Path.is_file") as mock_is_file, \
             patch("pathlib.Path.is_dir") as mock_is_dir:
            
            mock_exists.return_value = True
            mock_is_dir.return_value = True
            
            # Simulate the files in DATA_DIR
            mock_files = []
            for fname in self.results.keys():
                p = self.DATA_DIR / fname
                mock_files.append(p)
                
            mock_rglob.return_value = sorted(mock_files)
            
            data = get_tv_shows_metadata(self.DATA_DIR, api_key=self.API_KEY)
        self.assertIsInstance(data, dict)

        for file_data in data['files']:
            expected = self.results.get(file_data["file"])
            if not expected:
                continue
            self.assertEqual(file_data['show_detected'], expected["show"])
            self.assertEqual(file_data['season_detected'], expected["season"])
            self.assertEqual(file_data['episode_detected'], expected["episode"])
            
            if file_data['selected_episode']:
                self.assertEqual(file_data['selected_episode']['episode_number'], expected["episode"])
                if "score" in expected:
                    self.assertEqual(file_data['selected_episode']['score'], expected["score"])

if __name__ == '__main__':
    unittest.main()
