import sys
import unittest
from pathlib import Path


HTML_CLEANER_DIR = Path(__file__).resolve().parent
if str(HTML_CLEANER_DIR) not in sys.path:
    sys.path.insert(0, str(HTML_CLEANER_DIR))

from html_cleaner import NEGATIVE, POSITIVE, classify_transcript_like, feature_extract, normalize_text


class HtmlCleanerTests(unittest.TestCase):
    def test_normalize_text_strips_urls_platforms_and_boilerplate(self):
        raw = "\n".join(
            [
                "Session 12 recap",
                "https://example.com/post",
                "reddit discussion thread",
                "comments (10)",
                "DM: The party enters the crypt.",
            ]
        )
        cleaned = normalize_text(raw)
        self.assertNotIn("https://example.com/post", cleaned)
        self.assertNotIn("reddit", cleaned.lower())
        self.assertNotIn("comments (10)", cleaned.lower())
        self.assertIn("DM: The party enters the crypt.", cleaned)

    def test_classifies_long_transcript_like_text_as_target(self):
        text = " ".join(
            [
                "Session 12 recap.",
                "DM: The torchlight shakes across the cave.",
                "Player: I roll 1d20 for initiative.",
                "We fought goblins and explored the lower tunnels.",
            ]
            * 40
        )
        feats = feature_extract(text, "Session 12", POSITIVE, NEGATIVE)
        is_target, conf, tag, debug = classify_transcript_like(feats)
        self.assertTrue(is_target)
        self.assertGreaterEqual(conf, 0.55)
        self.assertIn("bf10", debug)
        self.assertNotEqual(tag, "too-short")

    def test_rejects_statblock_like_text(self):
        text = " ".join(
            [
                "Armor Class 15. Hit Points 45. Speed 30 feet.",
                "STR 16 DEX 12 CON 14 INT 8 WIS 10 CHA 9.",
                "Damage Resistances fire. Senses: darkvision 60 feet.",
                "Actions: Multiattack. Legendary Actions.",
            ]
            * 30
        )
        feats = feature_extract(text, "Monster Statblock", POSITIVE, NEGATIVE)
        is_target, conf, tag, _debug = classify_transcript_like(feats)
        self.assertFalse(is_target)
        self.assertLess(conf, 0.55)
        self.assertIn("statblock", tag)


if __name__ == "__main__":
    unittest.main()
