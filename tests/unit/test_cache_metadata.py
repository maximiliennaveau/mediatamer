import unittest
import tempfile
import copy
from pathlib import Path

from mediatamer.signals.video_metadata import VideoMetadata
from mediatamer.signals.technical import TechnicalSignals
from mediatamer.signals.cache import save_metadata, load_metadata


class TestMetadataCaching(unittest.TestCase):
    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_caching(self):
        # Create a temporary directory
        with tempfile.TemporaryDirectory() as tempdir:
            # Generate a random VideoMetadata object.
            video_metadata = VideoMetadata(path=Path(tempdir) / "test.mp4")

            # Save metadata
            save_metadata(video_metadata, {"cache-dir": tempdir})

            # Load metadata
            loaded_metadata = load_metadata(video_metadata.path, {"cache-dir": tempdir})

            # Verify contents
            self.assertIsNotNone(loaded_metadata)
            self.assertEqual(loaded_metadata.path, video_metadata.path)


if __name__ == "__main__":
    unittest.main()
