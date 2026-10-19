"""Source-aware category priority, independent operating status and colour use."""
import unittest


from design import legend_position
from model import active_counts
from settings import SCHEDULE_CATEGORIES, classify_scheduled


class CategoryTests(unittest.TestCase):
    def test_superfast_source_overrides_generic_express_name(self):
        self.assertEqual(classify_scheduled("MADGAON ERS EXP", "Superfast"), "superfast")
        self.assertEqual(classify_scheduled("Some Express", "SF"), "superfast")
        self.assertEqual(classify_scheduled("Some Express", "Mail/Express"), "express")

    def test_explicit_service_type_precedes_fallback_name(self):
        self.assertEqual(classify_scheduled("Intercity Express", "Passenger"), "regional")
        self.assertEqual(classify_scheduled("Example Passenger", "Superfast"), "superfast")
        self.assertEqual(classify_scheduled("MEMU Express", "Mail/Express"), "express")

    def test_named_families_take_priority_without_making_every_brand_superfast(self):
        for name, expected in (("Vande Bharat Express", "vande"), ("Rajdhani SF", "rajdhani"),
                               ("Jan Shatabdi Express", "shatabdi")):
            self.assertEqual(classify_scheduled(name, "Superfast"), expected)
        for name in ("Duronto", "Tejas", "Garib Rath", "Humsafar", "Amrit Bharat"):
            self.assertEqual(classify_scheduled(name, name), "express")
            self.assertEqual(classify_scheduled(name+" SF", name), "superfast")

    def test_special_is_not_a_service_category(self):
        for name, expected in (("Example SF SPL", "superfast"), ("Example EXP SPL", "express"),
                               ("Example PGR SPL", "regional"), ("Example LOCAL SPECIAL", "local"),
                               ("AAA BBB SPL", "unknown")):
            self.assertEqual(classify_scheduled(name, "Special"), expected)

    def test_local_and_regional_units_are_not_substring_matches(self):
        for kind, expected in (("EMU", "local"), ("MEMU", "regional"), ("DEMU", "regional"),
                               ("DMU", "regional"), ("Suburban", "local")):
            self.assertEqual(classify_scheduled("Example", kind), expected)
            self.assertEqual(classify_scheduled("Example "+kind, "unclassified"), expected)
        self.assertEqual(classify_scheduled("NAMO BHARAT RAPID RAIL", "Vande Bharat Metro"), "regional")

    def test_unknowns_stay_visible_and_freight_is_rejected(self):
        self.assertEqual(classify_scheduled("AAA BBB", "unclassified"), "unknown")
        self.assertEqual(classify_scheduled("AAA BBB", "Tourist"), "unknown")
        self.assertIsNone(classify_scheduled("Parcel Express", "Superfast"))
        journey = {"category": "unknown", "segments": [{"start": 0, "end": 1000, "from": 0, "to": 100}]}
        self.assertEqual(active_counts([journey], 500, SCHEDULE_CATEGORIES)["unknown"], 1)

    def test_eight_category_legend_fits_without_touching_activity_chart(self):
        self.assertEqual(len(SCHEDULE_CATEGORIES), 8)
        self.assertEqual(len({v[1] for v in SCHEDULE_CATEGORIES.values()}), 8)
        for i in range(8):
            x, y = legend_position(i, SCHEDULE_CATEGORIES)
            self.assertTrue(44 < x < 1036)
            self.assertTrue(1388 < y < y+42 < 1620)
