import unittest
from pathlib import Path
import re

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
    }

    @patch("mediatamer.signals.technical.TechnicalSignals.from_path")
    @patch("mediatamer.matcher.requests.get")
    @patch("mediatamer.signals.context.infer_context_from_path")
    def test_parsing_doctor_who_season_9_dvd3(
        self, mock_infer, mock_get, mock_technical_signals
    ):
        # 1. Mock MediaSignals for all files
        def mock_signals(path, **kwargs):
            m = MagicMock()
            m.duration = 2700 if path.name.startswith("B") else 600
            m.has_chapters = False
            m.chapters = []
            m.embedded_title = None
            return m

        mock_technical_signals.side_effect = mock_signals

        # 2. Mock TMDB responses
        def mock_tmdb_responses(url, params=None, **kwargs):
            mock = MagicMock()
            mock.ok = True
            if "search/tv" in url:
                mock.json.return_value = {
                    "results": [{"id": 57243, "name": "Doctor Who"}]
                }
            elif "season/9" in url and "episode" not in url:
                mock.json.return_value = {
                    "episodes": [
                        {
                            "episode_number": 7,
                            "name": "The Zygon Invasion",
                            "id": 1,
                            "runtime": 45,
                        },
                        {
                            "episode_number": 8,
                            "name": "The Zygon Inversion",
                            "id": 2,
                            "runtime": 45,
                        },
                        {
                            "episode_number": 9,
                            "name": "Sleep No More",
                            "id": 3,
                            "runtime": 45,
                        },
                    ]
                }
            elif "credits" in url:
                mock.json.return_value = {"crew": []}
            else:
                mock.json.return_value = {}
            return mock

        mock_get.side_effect = mock_tmdb_responses
        mock_infer.return_value = ("Doctor Who", 9, 3)

        # 3. Mock file system for recursive scan
        with (
            patch("pathlib.Path.rglob") as mock_rglob,
            patch("pathlib.Path.exists") as mock_exists,
            patch("pathlib.Path.is_file") as mock_is_file,
            patch("pathlib.Path.is_dir") as mock_is_dir,
        ):
            mock_exists.return_value = True
            mock_is_dir.return_value = True

            mock_files = []
            for fname in self.results.keys():
                p = self.DATA_DIR / fname
                mock_files.append(p)

            mock_rglob.return_value = sorted(mock_files)

            data = get_tv_shows_metadata(self.DATA_DIR, api_key=self.API_KEY)
        self.assertIsInstance(data, dict)


if __name__ == "__main__":
    unittest.main()
