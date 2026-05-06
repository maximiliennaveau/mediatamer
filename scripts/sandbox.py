from pathlib import Path

from mediatamer.signals.video_metadata import VideoMetadata
from mediatamer.config import load_config
from mediatamer.signals.guessit import infer_context_from_path

path = Path("/data/videos/unsorted-compressed-tv/Doctor_Who_S9_DVD1/")
metadata = VideoMetadata(path=path)
config = load_config()

infer_context_from_path(metadata, config)

print(metadata.guessit)
