import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
from mediatamer.signals.guessit import infer_context_from_path
from mediatamer.signals.technical import TechnicalSignals
from mediatamer.signals.video_metadata import VideoMetadata


class TestSignalsModules(unittest.TestCase):
    def test_parse_filename_basic(self):
        # Mock pathlib.Path.exists to return True
        with patch("pathlib.Path.exists", return_value=True):
            p = Path("/data/videos/unsorted_videos/Doctor_Who_S9_DVD1/B1_t00.mkv")
            metadata = VideoMetadata(path=p)

        # Test the parsing logic directly (mocking AI to avoid network)
        with patch(
            "mediatamer.signals.guessit.run_ai",
            return_value='{"type": "episode", "show": "Doctor Who", "season": 9}',
        ):
            r = infer_context_from_path(metadata)

        self.assertIsInstance(r, dict)
        self.assertEqual(r.get("season"), 9)
        self.assertEqual(r.get("show"), "Doctor Who")

    def test_technical_metadata(self):
        # Mock subprocess.run in technical module
        with patch("mediatamer.signals.technical.subprocess.run") as mock_run:
            mock_run.return_value.stdout = '{"format": {"duration": "120.0"}}'
            mock_run.return_value.returncode = 0

            p = Path("/dummy/path.mkv")
            with patch.object(Path, "exists", return_value=True):
                metadata = VideoMetadata(path=p)
                tech = TechnicalSignals.from_metadata(metadata)

            self.assertIsInstance(tech, TechnicalSignals)
            self.assertEqual(tech.duration, 120.0)
