import sys
from pathlib import Path
import os
import unittest
from unittest.mock import MagicMock, patch
import json

# Add mediatamer to path
sys.path.append(str(Path(__file__).parent.parent))

from mediatamer.cli.metadata import main


class TestMetadataCLI(unittest.TestCase):
    @patch("mediatamer.cli.metadata.HolisticAIMatcher")
    @patch("mediatamer.config.load_config")
    @patch("mediatamer.cli.metadata.check_ffprobe")
    @patch("pathlib.Path.rglob")
    def test_cli_ai_flag(self, mock_rglob, mock_check, mock_load, mock_ai_class):
        # Setup mocks
        mock_load.return_value = {"tmbd-api-key": "fake_key"}

        mock_file = MagicMock(spec=Path)
        mock_file.suffix = ".mkv"
        mock_file.name = "Test.mkv"
        mock_file.is_file.return_value = True
        mock_rglob.return_value = [mock_file]

        mock_matcher = MagicMock()
        mock_ai_class.return_value = mock_matcher
        mock_matcher.match.return_value = {
            "best_candidate": {"name": "Test Episode"},
            "score": 0.9,
            "filename": "Test.mkv",
            "filepath": "/path/to/Test.mkv",
        }

        # Mock write_json to avoid actual file creation
        with patch("mediatamer.cli.metadata.write_json") as mock_write:
            # Set sys.argv
            with patch.object(
                sys, "argv", ["metadata.py", "--ai", "--tmdb-api-key", "key"]
            ):
                main()

                # Verify AI Matcher was used
                mock_ai_class.assert_called_once_with(tmdb_api_key="key")
                mock_matcher.match.assert_called_once()
                mock_write.assert_called_once()


if __name__ == "__main__":
    unittest.main()
