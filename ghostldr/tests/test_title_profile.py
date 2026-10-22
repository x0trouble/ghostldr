"""title_profile.py: the shipped CUSA11456.json must encode to exactly
the constants profile.c carries as its built-in profile — the data
file and the C fallback can never drift apart silently.

    python3 -m unittest discover -s ghostldr/tests
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ghostldr/tools"))
import title_profile as tp  # noqa: E402


class TitleProfile(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.words = tp.load_words(ROOT / "titles/CUSA11456.json")

    def test_shape(self) -> None:
        self.assertEqual(len(self.words), 48)
        self.assertEqual(self.words[0], tp.MAGIC)
        self.assertEqual(self.words[1], 1)

    def test_builtin_values(self) -> None:
        w = self.words
        self.assertEqual(w[2], 0x3534313141535543)  # "CUSA1145" little-endian
        self.assertEqual(w[3], 1)                   # builtin hooks allowed
        self.assertEqual(w[4], 3)                   # knobs
        self.assertEqual(w[5], 0x111CD50)           # streaming pool table
        self.assertEqual(w[6:12], [0x46000000, 0x46000000, 0x46000000,
                                   0x84800000, 0x125800000, 0x125800000])
        self.assertEqual(w[12:24], [0x111CE10, 4, 0, 0,
                                    0x111CDE0, 6, 1, 0,
                                    0x111CD20, 7, 2, 320])
        self.assertEqual(w[28:35], [3946, 48, 32, 1824, 1704, 100, 128])
        self.assertEqual(w[35], 3)
        self.assertEqual(w[36:39], [0x896126, 0x89614A, 0xEEE2CF])
        self.assertEqual(w[44:46], [0x16B2930, 0x16B29F8])

    def test_rejects_bad_shapes(self) -> None:
        base = {"title_id": "CUSA00000", "stream_pool_table": 1,
                "stream_pool": [1] * 6, "fixed_mib": 1, "remainder_mib": 1,
                "slack_mib": 1, "lazy_total_mib": 1, "lazy_reserve_mib": 1,
                "movie_reserve_mib": 1, "min_pool_mib": 1}
        with self.assertRaises(ValueError):
            tp.encode({**base, "stream_pool": [1] * 7})
        with self.assertRaises(ValueError):
            tp.encode({**base, "lazy_sites": [1] * 9})
        with self.assertRaises(ValueError):
            tp.encode({**base, "knobs": [{"table": 1, "knob_slot": 4,
                                          "name": "general GPU heap"}] * 5})


if __name__ == "__main__":
    unittest.main()
