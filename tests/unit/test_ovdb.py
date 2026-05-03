from pathlib import Path
import unittest

from mediatamer.config import load_config
from mediatamer.signals.cache import load_metadata
import mediatamer.signals.search_ovdb as search_ovdb
import mediatamer.signals.tvdb as tvdb
import mediatamer.signals.tmdb as tmdb


class TestOVDB(unittest.TestCase):
    def test_tvdb_functionality(self):
        # Episode search:
        path = Path("/data/videos/unsorted-compressed-tv/Doctor_Who_S9_DVD1/B2_t01.mkv")
        self.assertTrue(path.exists(), "Test video file should exist for OVDB search")
        config = load_config()
        metadata = load_metadata(path, config)
        self.assertIsNotNone(metadata, "Metadata should not be None")
        tvdb_key = config.get("tvdb-api-key")
        res_tvdb = tvdb.fetch_tvdb_info(
            "Doctor Who", season_number=9, api_key=tvdb_key, locale="eng"
        )
        print(f"TVDB results: {res_tvdb}")
        show_names = set()
        for episode in res_tvdb[1]:
            self.assertIn("name", episode, "Episode should have a name")
            self.assertIn("air_date", episode, "Episode should have an air date")
            show_names.add(episode["_show_name"])

        self.assertEqual(
            len(show_names),
            2,
            "We should find the 2 series here. The historical doctor who 1963 one and the modern one 2005",
        )
        self.assertIn(
            "Doctor Who", show_names, "One of the shows should be 'Doctor Who'"
        )
        self.assertIn(
            "Doctor Who (1963)", show_names, "One of the shows should be 'Doctor Who'"
        )
        self.assertIn(
            "Doctor Who (2005)", show_names, "One of the shows should be 'Doctor Who'"
        )

    def test_tmdb_extraction(self):
        path = Path("/data/videos/unsorted-compressed-tv/Doctor_Who_S9_DVD1/B2_t01.mkv")
        self.assertTrue(path.exists(), "Test video file should exist for OVDB search")
        config = load_config()
        metadata = load_metadata(path, config)
        self.assertIsNotNone(metadata, "Metadata should not be None")

        tmdb_key = config.get("tmdb-api-key")
        res_tmdb = tmdb.fetch_tmdb_episodes(
            "Doctor Who", season_number=9, api_key=tmdb_key, locale="eng"
        )
        print(f"TMDB results: {res_tmdb}")


if __name__ == "__main__":
    unittest.main()
