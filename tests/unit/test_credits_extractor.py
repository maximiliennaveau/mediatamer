from pathlib import Path
import unittest

from mediatamer.signals.credits_extractor import VideoCreditsExtractor
from mediatamer.signals.video_metadata import VideoMetadata
from mediatamer.signals.technical import TechnicalSignals


SINTEL = Path(__file__).parent.parent / "resource" / "Sintel.mp4"

# Config that keeps the test fast on the 52s Sintel clip:
# start=1s to grab the opening title card, end=5s to grab closing credits.
FAST_CONFIG = {
    "credits-scan-fps": 0.2,
    "credits-start-duration": 1,
    "credits-end-duration": 5,
}

# Config used when we want the full OCR text for raw-output assertions.
OCR_CONFIG = {
    "credits-scan-fps": 0.2,
    "credits-start-duration": 5,
    "credits-end-duration": 5,
}

# Known strings that must appear in the raw OCR output.
EXPECTED_OCR_FRAGMENTS = [
    "SINTEL",
    "BLENDER FOUNDATION",
    "HALINA REIJN",
    "THOM HOFFMAN",
    "JAN MORGENSTERN",
    "NETHERLANDS FILM FUND",
]

# Known organizations that should be captured as producers/funders.
EXPECTED_FUNDERS = [
    "BLENDER FOUNDATION",
    "NETHERLANDS FILM FUND",
    "CINEGRID",
    "BLENDER INSTITUTE",
]

# Real human beings who must appear somewhere in the people-facing fields
# (real_actors OR crew_names — bucket may vary across LLM runs).
EXPECTED_PEOPLE = [
    "HALINA REIJN",
    "THOM HOFFMAN",
    "JAN MORGENSTERN",
]


def _all_people(profile) -> list[str]:
    """Return all names from the person-oriented fields, uppercased."""
    names = (
        profile.fictional_characters
        + profile.real_actors
        + profile.crew_names
    )
    return [n.upper() for n in names]


def _all_funders(profile) -> list[str]:
    return [n.upper() for n in profile.producers_and_funders]


class TestCreditsExtractorOCR(unittest.TestCase):
    """Test the raw frame-extraction + OCR layer (no AI)."""

    def setUp(self):
        if not SINTEL.exists():
            self.skipTest(f"Test resource missing: {SINTEL}")
        meta = VideoMetadata(path=SINTEL)
        TechnicalSignals.from_metadata(meta)
        extractor = VideoCreditsExtractor(OCR_CONFIG)
        duration = meta.technical.duration
        ranges = [
            (0, min(duration, extractor.start_duration)),
            (max(0, duration - extractor.end_duration), duration),
        ]
        self.raw_text = extractor._extract_text_from_frames(SINTEL, ranges)
        print(f"\n[OCR] Full text ({len(self.raw_text)} chars):\n{self.raw_text}")

    def test_ocr_is_non_empty(self):
        self.assertIsInstance(self.raw_text, str)
        self.assertGreater(len(self.raw_text.strip()), 0, "OCR must produce text")

    def test_ocr_contains_title(self):
        self.assertIn("SINTEL", self.raw_text.upper())

    def test_ocr_contains_blender_foundation(self):
        self.assertIn("BLENDER FOUNDATION", self.raw_text.upper())

    def test_ocr_contains_all_known_fragments(self):
        missing = [f for f in EXPECTED_OCR_FRAGMENTS if f not in self.raw_text.upper()]
        self.assertEqual(
            missing,
            [],
            f"These expected strings were missing from OCR output: {missing}",
        )


class TestCreditsExtractorAI(unittest.TestCase):
    """Test the full pipeline: OCR + AI-refined CastProfile."""

    @classmethod
    def setUpClass(cls):
        if not SINTEL.exists():
            raise unittest.SkipTest(f"Test resource missing: {SINTEL}")
        meta = VideoMetadata(path=SINTEL)
        TechnicalSignals.from_metadata(meta)
        extractor = VideoCreditsExtractor(FAST_CONFIG)
        cls.profile = extractor.extract(meta)
        print(f"\n[AI] CastProfile: {cls.profile}")

    def test_profile_is_returned(self):
        self.assertIsNotNone(self.profile)

    def test_confidence_is_reasonable(self):
        self.assertGreaterEqual(
            self.profile.confidence, 50,
            "Confidence should be ≥ 50 for a clean credit roll like Sintel",
        )

    def test_show_name_is_sintel(self):
        hints_upper = [h.upper() for h in self.profile.show_name_hints]
        self.assertIn(
            "SINTEL", hints_upper,
            f"show_name_hints should contain 'SINTEL', got: {self.profile.show_name_hints}",
        )

    def test_known_people_appear_in_profile(self):
        """Each known person must appear in at least one people-oriented field."""
        found = _all_people(self.profile)
        missing = [p for p in EXPECTED_PEOPLE if p not in found]
        self.assertEqual(
            missing,
            [],
            f"These people were not found in any person field: {missing}\n"
            f"Got: {found}",
        )

    def test_funders_captured(self):
        """Known funding organisations must appear in producers_and_funders."""
        found = _all_funders(self.profile)
        missing = [f for f in EXPECTED_FUNDERS if not any(f in entry for entry in found)]
        self.assertEqual(
            missing,
            [],
            f"These funders were missing from producers_and_funders: {missing}\n"
            f"Got: {found}",
        )

    def test_no_brand_names_in_people_fields(self):
        """Brand/codec names such as DIVX must not appear in person fields."""
        brands = ["DIVX", "DOLBY", "CINEGRID"]
        found = _all_people(self.profile)
        falsely_included = [b for b in brands if b in found]
        self.assertEqual(
            falsely_included,
            [],
            f"Brand names should not appear in person fields: {falsely_included}",
        )

    def test_title_not_in_people_fields(self):
        """The film title should not be classified as a person."""
        found = _all_people(self.profile)
        self.assertNotIn(
            "SINTEL", found,
            "'SINTEL' is the film title and must not appear in person fields",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
