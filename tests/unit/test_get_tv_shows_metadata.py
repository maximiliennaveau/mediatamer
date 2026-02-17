import unittest
from pathlib import Path

from mediatamer.get_tv_shows_metadata import get_tv_shows_metadata


class TestGetTvShowsMetadata(unittest.TestCase):

    DATA_DIR = Path("/data/videos/unsorted_videos/Doctor_Who_S9_DVD3")
    API_KEY = Path("/data/videos/mediatamer/secrets/tmdb.pub").read_text().strip()

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
            "show": "Doctor Who - Extras",
            "season": 9,
            "episode": 1,
            "title": "Doctor Who Extra",
        },
        "C2_t04.mkv": {
            "show": "Doctor Who - Extras",
            "season": 9,
            "episode": 2,
            "title": "Doctor Who Extra",
        },
        "C3_t05.mkv": {
            "show": "Doctor Who - Extras",
            "season": 9,
            "episode": 3,
            "title": "Doctor Who Extra",
        },
        "C4_t06.mkv": {
            "show": "Doctor Who - Extras",
            "season": 9,
            "episode": 4,
            "title": "Doctor Who Extra",
        },
        "C5_t07.mkv": {
            "show": "Doctor Who - Extras",
            "season": 9,
            "episode": 5,
            "title": "Doctor Who Extra",
        },
    }

    def test_parsing_doctor_who_season_9_dvd3(self):
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
                self.assertEqual(file_data['selected_episode']['name'], expected["title"])
                if "score" in expected:
                    self.assertEqual(file_data['selected_episode']['score'], expected["score"])

if __name__ == '__main__':
    unittest.main()
