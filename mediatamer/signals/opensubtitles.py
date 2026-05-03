import struct
import os
import requests
from pathlib import Path
from typing import Dict, Any, Optional

from mediatamer.signals.video_metadata import VideoMetadata


class OpenSubtitleSignals:
    def __init__(self, metadata: VideoMetadata, config: Dict[str, Any]):
        self.metadata = metadata
        self.config = config
        self.api_key = self.config.get("opensubtitles-api-key")

    def _compute_osdb_hash(self, file_path: Path) -> Optional[str]:
        try:
            longlongformat = "<q"
            bytesize = struct.calcsize(longlongformat)
            file_path_str = str(file_path)

            filesize = os.path.getsize(file_path_str)
            if filesize < 65536 * 2:
                return None

            hash_val = filesize

            with open(file_path_str, "rb") as f:
                for _ in range(65536 // bytesize):
                    buffer = f.read(bytesize)
                    (l_value,) = struct.unpack(longlongformat, buffer)
                    hash_val += l_value
                    hash_val = hash_val & 0xFFFFFFFFFFFFFFFF

                f.seek(max(0, filesize - 65536), 0)
                for _ in range(65536 // bytesize):
                    buffer = f.read(bytesize)
                    (l_value,) = struct.unpack(longlongformat, buffer)
                    hash_val += l_value
                    hash_val = hash_val & 0xFFFFFFFFFFFFFFFF

            return "%016x" % hash_val
        except Exception as e:
            print(f"Failed to compute OSDB hash: {e}")
            return None

    def _fetch_metadata(self, moviehash: str) -> Optional[Dict[str, Any]]:
        if not self.api_key:
            raise ValueError(
                "OpenSubtitles API key is missing from the configuration (opensubtitles-api-key)."
            )

        url = f"https://api.opensubtitles.com/api/v1/subtitles?moviehash={moviehash}"
        headers = {"Api-Key": self.api_key, "User-Agent": "MediaTamer v1.0"}

        # This will securely raise an exception on a failure to connect, as requested.
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        data = response.json()

        if data.get("data") and len(data["data"]) > 0:
            # We select the first hit because hash matches are deterministic scenes.
            first_hit = data["data"][0]
            feature = first_hit.get("attributes", {}).get("feature_details", {})

            return {
                "tmdb_id": feature.get("tmdb_id"),
                "imdb_id": feature.get("imdb_id"),
                "season_number": feature.get("season_number"),
                "episode_number": feature.get("episode_number"),
                "title": feature.get("title"),
            }

        return None

    def extract(self) -> bool:
        try:
            moviehash = self._compute_osdb_hash(self.metadata.path)
            if not moviehash:
                print(
                    "Could not compute OpenSubtitles hash (file too small or unavailable)."
                )
                self.metadata.opensubtitles = {"status": "hash_failed"}
                return False

            print(f"Computed OpenSubtitles hash: {moviehash}")
            result = self._fetch_metadata(moviehash)

            if result:
                self.metadata.opensubtitles = result
                print(f"Found OpenSubtitles match: {result}")
                return True

            self.metadata.opensubtitles = {"status": "no_match", "hash": moviehash}
            print("No match found on OpenSubtitles.")
            return False

        except Exception as e:
            print(f"Error during OpenSubtitles extraction: {e}")
            return False
