import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
from mediatamer.signals.guessit import infer_context_from_path as parse_filename
from mediatamer.signals.technical import get_technical_metadata


class TestSignalsModules(unittest.TestCase):
    def test_parse_filename_basic(self):
        # Mock pathlib.Path.exists to return True
        with patch("pathlib.Path.exists", return_value=True):
            p = Path("/data/videos/unsorted_videos/Doctor_Who_S9_DVD1/B1_t00.mkv")

        # Test the parsing logic directly (mocking internal guessit if needed, but basic should work)
        r = parse_filename(p)
        self.assertIsInstance(r, dict)
        self.assertEqual(r["season"], 9)
        self.assertEqual(r["show"], "Doctor Who")

    def test_technical_metadata(self):
        # Mock subprocess.run in metadata module
        with patch("mediatamer.cli.metadata.subprocess.run") as mock_run:
            mock_run.return_value.stdout = '{"format": {"duration": "120.0"}}'
            mock_run.return_value.returncode = 0

            p = MagicMock()
            p.__str__.return_value = "/dummy/path.mkv"
            p.exists.return_value = True

            meta = get_technical_metadata(p)
            self.assertIsInstance(meta, dict)
            self.assertIn("duration", meta)
