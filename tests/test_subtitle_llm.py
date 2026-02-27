import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
import os
import json

from mediatamer.signals.subtitle import compare_subtitle_to_description
from mediatamer.signals.scoring import score_episode_match
from mediatamer.signals.technical import TechnicalSignals


class TestSubtitleLLM(unittest.TestCase):
    def setUp(self):
        os.environ["LLM_API_KEY"] = "fake-key"
        self.subtitle = "The doctor says the virus is spreading fast. We need to find the patient zero."
        self.description = "A mysterious virus breaks out in the city. The team races to find patient zero."

    @patch("requests.post")
    def test_compare_subtitle_to_description_success(self, mock_post):
        # Mock successful LLM response
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": json.dumps({"score": 0.85})}}]
        }
        mock_post.return_value = mock_resp

        score = compare_subtitle_to_description(self.subtitle, self.description)
        self.assertEqual(score, 0.85)

    @patch("requests.post")
    def test_compare_subtitle_to_description_failure(self, mock_post):
        # Mock failed LLM response
        mock_post.side_effect = Exception("API Connection Error")

        score = compare_subtitle_to_description(self.subtitle, self.description)
        self.assertEqual(score, 0.0)

    @patch("mediatamer.signals.scoring.compare_subtitle_to_description")
    def test_scoring_integration(self, mock_compare):
        mock_compare.return_value = 0.8

        ep = {"name": "The Virus", "overview": self.description, "runtime": 45}
        # Mock technical signals
        tech = MagicMock()
        tech.duration = 45 * 60
        tech.suggested_ocr_ranges = []

        res = score_episode_match(ep, Path("B1_t01.mkv"), tech, sub_text=self.subtitle)

        # 0.8 * 150 = 120
        # Plus duration match (50) = 170
        self.assertGreaterEqual(res["score"], 120.0)
        found_llm_reason = any(
            "LLM Subtitle/Description similarity" in r for r in res["reasons"]
        )
        self.assertTrue(found_llm_reason)


if __name__ == "__main__":
    unittest.main()
