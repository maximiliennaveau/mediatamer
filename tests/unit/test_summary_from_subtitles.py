import json
import unittest

from mediatamer.signals.summary_from_subtitles import extract_summary_from_subtitles


class TestSummaryFromSubtitles(unittest.TestCase):
    def setUp(self):
        # A sample transcript of a short space adventure story
        self.SAMPLE_SUBTITLES = """
        1
        00:00:05,000 --> 00:00:10,000
        Commander Zara: "Status report, Kael. How far from the Nebula?"

        2
        00:00:11,500 --> 00:00:15,000
        Kael: "Approaching now, Commander. But the scanners are picking up something... massive."

        3
        00:00:17,000 --> 00:00:22,000
        Zara: "Launch the drone. We need visual. If the rumors of the Star Forge are true..."

        4
        00:00:24,000 --> 00:00:28,000
        Kael: "Wait! It's not a forge. It's a ship. An ancient flagship from the First Era."

        5
        00:00:30,000 --> 00:00:35,000
        Zara: "The 'Eternity'? That ship vanished three centuries ago during the Siege of Aethel."

        6
        00:00:37,000 --> 00:00:41,000
        Kael: "And it's powering up weapons. They're targeting us, Commander!"

        7
        00:00:43,000 --> 00:00:48,000
        Zara: "Evasive maneuvers! They're not just ghosts... they're still protecting the gateway."
        """

    def test_summary_from_subtitles(self):
        print("--- Running Summary Generator on Sample Story ---")
        result = extract_summary_from_subtitles(self.SAMPLE_SUBTITLES)

        # We convert to dict for a pretty-printed view of the extracted data
        print(json.dumps(result.to_dict(), indent=2))
        if result.confidence > 70:
            print("\n✅ Verification Successful: High confidence extraction.")
        else:
            print(
                f"\n⚠️ Warning: Low confidence ({result.confidence}). Check prompt vs. sample text."
            )
        self.assertGreater(result.confidence, 70)


if __name__ == "__main__":
    unittest.main(verbosity=2)
