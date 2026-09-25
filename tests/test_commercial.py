import unittest

from scripts.commercial import (
    LARGE,
    SINGLE,
    TARGET,
    WATCHLIST,
    classify_branch_count,
    filter_commercial_brands,
    plan_branch_network_completion,
    segment_brands,
)


class CommercialTests(unittest.TestCase):
    def test_exact_segment_boundaries(self):
        expected = {1: SINGLE, 2: WATCHLIST, 3: TARGET, 20: TARGET, 21: LARGE}
        self.assertEqual({count: classify_branch_count(count) for count in expected}, expected)
        with self.assertRaises(ValueError):
            classify_branch_count(0)

    def test_segmentation_preserves_rows_and_adds_bucket(self):
        rows = [{"brand_id": str(n), "branch_count_amg": n} for n in (1, 2, 3, 20, 21)]
        segmented = segment_brands(rows)
        self.assertEqual([row["commercial_segment"] for row in segmented],
                         [SINGLE, WATCHLIST, TARGET, TARGET, LARGE])
        self.assertNotIn("commercial_segment", rows[0])

    def test_branch_network_plan_only_uses_detected_chains_and_audits_decision(self):
        brands = [
            {"brand_id": "ok", "brand_name": "Café Luna", "branches_detected": 2,
             "confidence": "high"},
            {"brand_id": "one", "brand_name": "Solo", "branches_detected": 1},
            {"brand_id": "generic", "brand_name": "Cafetería", "branches_detected": 3},
            {"brand_id": "large", "brand_name": "Cadena Grande", "branches_detected": 21},
            {"brand_id": "excluded", "brand_name": "Marca Excluida", "branches_detected": 3},
        ]
        planned = plan_branch_network_completion(
            brands, expansion_jobs=9, excluded_brand_ids={"excluded"}
        )
        by_id = {row["brand_id"]: row for row in planned}
        self.assertTrue(by_id["ok"]["complete_branch_network"])
        self.assertEqual(by_id["ok"]["discovery_branch_count"], 2)
        self.assertEqual(by_id["ok"]["expanded_branch_count"], 2)
        self.assertEqual(by_id["ok"]["expansion_jobs"], 9)
        self.assertEqual(by_id["ok"]["expansion_confidence"], "high")
        for brand_id in ("one", "generic", "large", "excluded"):
            self.assertFalse(by_id[brand_id]["complete_branch_network"])
            self.assertEqual(by_id[brand_id]["expansion_jobs"], 0)
            self.assertTrue(by_id[brand_id]["expansion_exclusion_reason"])

    def test_network_plan_accepts_completed_counts_without_losing_discovery_count(self):
        row = plan_branch_network_completion([{
            "brand_id": "x", "brand_name": "Xocolatl", "branches_amg": 2,
            "expanded_branch_count": 5, "expansion_jobs": 12, "expansion_confidence": "verified",
        }])[0]
        self.assertEqual(row["discovery_branch_count"], 2)
        self.assertEqual(row["expanded_branch_count"], 5)
        self.assertEqual(row["expansion_jobs"], 12)

    def test_filters_can_be_combined_without_scraping(self):
        rows = [
            {"brand_id": "a", "branch_count_amg": 4, "municipalities": "Guadalajara; Zapopan",
             "inside_core_periferico": True, "merchant_family": "Cafetería",
             "uber_status": "CONFIRMED"},
            {"brand_id": "b", "branch_count_amg": 2, "municipalities": ["Zapopan"],
             "inside_core_periferico": False, "merchant_family": "Sushi",
             "uber_status": "NOT_FOUND"},
        ]
        result = filter_commercial_brands(
            rows, municipalities={"Guadalajara"}, layer="core", min_branches=3,
            max_branches=10, merchant_families={"cafeteria"},
            platform_statuses={"uber": {"CONFIRMED"}},
        )
        self.assertEqual([row["brand_id"] for row in result], ["a"])
        self.assertEqual(len(filter_commercial_brands(rows, platform_statuses={"uber": {"NOT_FOUND"}})), 1)
        self.assertEqual(len(filter_commercial_brands(rows, platform_statuses={"Uber Eats": {"CONFIRMED"}})), 1)


if __name__ == "__main__":
    unittest.main()
