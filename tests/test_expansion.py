import unittest

from scripts.expansion import expansion_candidates, make_expansion_jobs, representative_points


class ExpansionTests(unittest.TestCase):
    def test_only_confirmed_two_to_twenty_branch_chains_expand(self):
        brands = [
            {"brand_id": "ok", "brand_name": "Cadena Uno", "branch_count_amg": 2,
             "brand_resolution_status": "CONFIRMED"},
            {"brand_id": "single", "brand_name": "Solo", "branch_count_amg": 1,
             "brand_resolution_status": "CONFIRMED"},
            {"brand_id": "amb", "brand_name": "Ambigua", "branch_count_amg": 3,
             "brand_resolution_status": "AMBIGUOUS"},
            {"brand_id": "large", "brand_name": "Grande", "branch_count_amg": 21,
             "brand_resolution_status": "CONFIRMED"},
        ]
        self.assertEqual(["ok"], [row["brand_id"] for row in expansion_candidates(brands)])

    def test_expansion_reuses_one_approved_plan_point_per_zone(self):
        base = [
            {"job_id": "a1", "point_id": "p1", "zone": "A", "scope": "AMG_FULL",
             "latitude": 20.1, "longitude": -103.1, "zoom": 16, "depth": 8, "pass": 1},
            {"job_id": "a2", "point_id": "p2", "zone": "A", "scope": "AMG_FULL",
             "latitude": 20.2, "longitude": -103.2, "zoom": 16, "depth": 8, "pass": 1},
            {"job_id": "b1", "point_id": "p3", "zone": "B", "scope": "AMG_FULL",
             "latitude": 20.3, "longitude": -103.3, "zoom": 15, "depth": 7, "pass": 1},
        ]
        points = representative_points(base)
        self.assertEqual(["A", "B"], [row["zone"] for row in points])
        brand = [{"brand_id": "ok", "brand_name": "Cadena Uno", "branch_count_amg": 2,
                  "brand_resolution_status": "CONFIRMED"}]
        jobs = make_expansion_jobs(brand, base)
        self.assertEqual(2, len(jobs))
        self.assertTrue(all(job["query_type"] == "brand_expansion" for job in jobs))
        self.assertEqual({"A", "B"}, {job["zone"] for job in jobs})
        self.assertTrue(all(job["brand_id"] == "ok" for job in jobs))
        self.assertTrue(all(job["latitude"] is not None and job["longitude"] is not None for job in jobs))


if __name__ == "__main__":
    unittest.main()
