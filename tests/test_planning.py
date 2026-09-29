import unittest

from scripts.planning import (
    approve_manifest,
    estimate_run,
    methodology_hash,
    stratified_pilot_jobs,
    verify_approval,
)


class PlanningTests(unittest.TestCase):
    def jobs(self):
        rows = []
        for zone in ("A", "B", "C", "D"):
            for depth in (5, 7):
                for query in ("restaurante", "cafe", "tacos", "sushi", "pizza", "pan", "extra"):
                    rows.append({
                        "job_id": f"{zone}-{depth}-{query}",
                        "zone": zone, "depth": depth, "query": query,
                        "point_id": f"{zone}-{depth}", "pass": 1,
                    })
        return rows

    def test_pilot_is_bounded_and_stratified(self):
        selected = stratified_pilot_jobs(self.jobs(), max_jobs=18, query_limit=6)
        self.assertLessEqual(len(selected), 18)
        self.assertGreaterEqual(len({row["zone"] for row in selected}), 4)
        self.assertLessEqual(len({row["query"] for row in selected}), 6)

    def test_eta_uses_observed_runtime_and_concurrency(self):
        eta = estimate_run(jobs=120, seconds_per_job=40, concurrency=2, uncertainty_pct=20)
        self.assertTrue(eta["available"])
        self.assertEqual(eta["eta_seconds"], 2400)
        self.assertEqual(eta["eta_low_seconds"], 1920)
        self.assertEqual(eta["eta_high_seconds"], 2880)

    def test_approval_freezes_runtime_and_hash(self):
        manifest = {
            "plan_sha256": "abc",
            "calibration": {"recommended_concurrency": 2},
            "frozen_config": {"settings": {"balanced_concurrency": 2, "balanced_browser_pool": 2}},
            "approval": {"required": True, "approved": False},
        }
        approve_manifest(manifest)
        verify_approval(manifest)
        self.assertEqual(manifest["approved_runtime"],
                         {"concurrency": 2, "browser_pool": 2, "pages_per_browser": 1})
        manifest["plan_sha256"] = "changed"
        with self.assertRaises(RuntimeError):
            verify_approval(manifest)

    def test_methodology_hash_changes_with_territory(self):
        base = {
            "scope": "AMG_FULL", "gosom_version": "v1", "gosom_sha256": "g",
            "frozen_config": {
                "territory_sha256": "one", "categories": {"active_queries": ["a"]},
                "coverage": {"densities": {}},
                "settings": {"lang": "es", "batch_size": 25, "concurrency": 1,
                             "browser_pool": 1, "pages_per_browser": 1},
            },
        }
        other = {**base, "frozen_config": {**base["frozen_config"], "territory_sha256": "two"}}
        self.assertNotEqual(methodology_hash(base), methodology_hash(other))


if __name__ == "__main__":
    unittest.main()
