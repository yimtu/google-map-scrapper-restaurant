import unittest

from scripts.platforms import (
    CONFIRMED,
    ERROR,
    NOT_FOUND,
    PENDING,
    UNCERTAIN,
    create_platform_check_queue,
    executive_platform_label,
    integrate_platform_evidence,
    normalize_platform_status,
    platform_quality_gate,
)


class PlatformTests(unittest.TestCase):
    def test_statuses_are_strict_and_not_found_is_not_a_definitive_no(self):
        self.assertEqual(normalize_platform_status("confirmed"), CONFIRMED)
        self.assertEqual(normalize_platform_status("NOT_FOUND"), NOT_FOUND)
        self.assertEqual(normalize_platform_status(""), PENDING)
        self.assertEqual(executive_platform_label(CONFIRMED), "Sí")
        self.assertEqual(executive_platform_label(NOT_FOUND), "No confirmada")
        self.assertEqual(executive_platform_label(UNCERTAIN), "Requiere revisión")
        self.assertEqual(executive_platform_label(PENDING), "Requiere revisión")
        self.assertEqual(executive_platform_label(ERROR), "Requiere revisión")
        self.assertNotEqual(executive_platform_label(NOT_FOUND).casefold(), "no")
        with self.assertRaises(ValueError):
            normalize_platform_status("NO")

    def test_queue_defaults_to_target_and_has_one_row_per_branch_platform(self):
        brands = [
            {"brand_id": "target", "brand_name": "Tres", "branch_count_amg": 3},
            {"brand_id": "watch", "brand_name": "Dos", "branch_count_amg": 2},
        ]
        branches = [
            {"brand_id": "target", "branch_id": "t1", "branch_name": "Centro", "address": "A"},
            {"brand_id": "target", "branch_id": "t2", "branch_name": "Norte", "address": "B"},
            {"brand_id": "watch", "branch_id": "w1", "branch_name": "Uno", "address": "C"},
        ]
        queue = create_platform_check_queue(brands, branches)
        self.assertEqual(len(queue), 6)
        self.assertEqual({row["platform"] for row in queue}, {"UBER_EATS", "RAPPI", "DIDI_FOOD"})
        self.assertEqual({row["brand_id"] for row in queue}, {"target"})
        watch_queue = create_platform_check_queue(brands, branches, include_watchlist=True)
        self.assertEqual(len(watch_queue), 9)

    def test_integration_produces_branch_and_brand_presence_with_evidence(self):
        brands = [{"brand_id": "b", "brand_name": "Marca", "branch_count_amg": 2}]
        branches = [
            {"brand_id": "b", "branch_id": "one", "branch_name": "Uno"},
            {"brand_id": "b", "branch_id": "two", "branch_name": "Dos"},
        ]
        evidence = [
            {"brand_id": "b", "brand_name": "Marca", "branch_id": "one", "branch_name": "Uno",
             "platform": "uber", "status": "CONFIRMED", "evidence_url": "https://example.test/uno",
             "evidence_type": "direct_listing", "checked_at": "2026-09-24T12:00:00Z",
             "method": "public_search", "confidence": "high", "page_title": "Marca Uno",
             "matched_name": "Marca", "matched_address": "Uno"},
            {"brand_id": "b", "brand_name": "Marca", "branch_id": "two", "branch_name": "Dos",
             "platform": "uber", "status": "NOT_FOUND", "evidence_url": "",
             "evidence_type": "search_completed", "checked_at": "2026-09-24T12:01:00Z",
             "method": "public_search", "confidence": "medium",
             "search_queries": "general || dominio || marca ubicacion"},
        ]
        result = integrate_platform_evidence(brands, branches, evidence)
        self.assertEqual(result["platform_presence"], result["brand_presence"])
        presence = result["brand_presence"][0]
        self.assertEqual(presence["uber_status"], CONFIRMED)
        self.assertEqual(presence["uber_branches_found"], 1)
        self.assertEqual(presence["uber_branches_total"], 2)
        branch_two = next(row for row in result["branch_presence"] if row["branch_id"] == "two")
        self.assertEqual(branch_two["uber_status"], NOT_FOUND)
        self.assertEqual(len(result["platform_evidence"]), 2)

    def test_conflicting_or_incomplete_evidence_is_uncertain(self):
        brands = [{"brand_id": "b", "brand_name": "Marca", "branch_count_amg": 1}]
        branches = [{"brand_id": "b", "branch_id": "one", "branch_name": "Uno"}]
        evidence = [
            {"brand_id": "b", "branch_id": "one", "platform": "didi", "status": "CONFIRMED",
             "evidence_url": "https://example.test", "page_title": "Marca Uno",
             "matched_name": "Marca", "matched_address": "Calle Uno",
             "checked_at": "2026-09-24", "method": "search"},
            {"brand_id": "b", "branch_id": "one", "platform": "didi", "status": "NOT_FOUND",
             "checked_at": "2026-09-25", "method": "search",
             "search_queries": "general || dominio || marca ubicacion"},
        ]
        result = integrate_platform_evidence(brands, branches, evidence)
        self.assertEqual(result["branch_presence"][0]["didi_status"], UNCERTAIN)
        with self.assertRaises(ValueError):
            integrate_platform_evidence(brands, branches, [{
                "brand_id": "b", "branch_id": "one", "platform": "uber", "status": "CONFIRMED"
            }])

    def test_pending_never_becomes_uncertain_and_uncertain_requires_an_executed_search(self):
        brands = [{"brand_id": "b", "brand_name": "Marca", "branch_count_amg": 1}]
        branches = [{"brand_id": "b", "branch_id": "one", "branch_name": "Uno"}]
        result = integrate_platform_evidence(brands, branches, [])
        self.assertEqual(PENDING, result["branch_presence"][0]["uber_status"])
        self.assertEqual(PENDING, result["brand_presence"][0]["uber_status"])
        with self.assertRaises(ValueError):
            integrate_platform_evidence(brands, branches, [{
                "brand_id": "b", "branch_id": "one", "platform": "uber",
                "status": "UNCERTAIN",
            }])

    def test_quality_gate_blocks_pending_and_error_checks(self):
        queue = [{"brand_id": "b", "branch_id": "one", "platform": platform}
                 for platform in ("UBER_EATS", "RAPPI", "DIDI_FOOD")]
        branch_presence = [{"brand_id": "b", "branch_id": "one",
                            "uber_status": CONFIRMED, "rappi_status": PENDING,
                            "didi_status": ERROR}]
        gate = platform_quality_gate(queue, branch_presence, requested=True)
        self.assertEqual({"expected_checks": 3, "completed_checks": 1,
                          "pending_checks": 1, "errors": 1, "report_status": "DRAFT"},
                         {key: gate[key] for key in ("expected_checks", "completed_checks",
                                                    "pending_checks", "errors", "report_status")})
        omitted = platform_quality_gate(queue, branch_presence, requested=False)
        self.assertEqual("FINAL", omitted["report_status"])
        self.assertFalse(omitted["platform_section_included"])

    def test_orphan_evidence_is_rejected(self):
        brands = [{"brand_id": "b", "branch_count_amg": 1}]
        branches = [{"brand_id": "b", "branch_id": "one"}]
        with self.assertRaises(ValueError):
            integrate_platform_evidence(brands, branches, [{
                "brand_id": "b", "branch_id": "missing", "platform": "rappi",
                "status": "NOT_FOUND", "checked_at": "2026-09-24", "method": "public_search",
            }])

    def test_confirmed_requires_direct_evidence_url_and_does_not_complete_other_branch(self):
        brands = [{"brand_id": "b", "brand_name": "Marca", "branch_count_amg": 3}]
        branches = [{"brand_id": "b", "branch_id": "one"},
                    {"brand_id": "b", "branch_id": "two"},
                    {"brand_id": "b", "branch_id": "three"}]
        evidence = [{"brand_id": "b", "branch_id": "one", "platform": "uber",
                     "status": "CONFIRMED", "evidence_url": "https://ubereats.example/one",
                     "page_title": "Marca Uno | Uber Eats", "checked_at": "2026-09-25",
                     "method": "integrated_browser", "matched_name": "Marca",
                     "matched_address": "Calle Uno"}]
        result = integrate_platform_evidence(brands, branches, evidence)
        one, two, three = result["branch_presence"]
        self.assertEqual(CONFIRMED, one["uber_status"])
        self.assertEqual(PENDING, two["uber_status"])
        queue = create_platform_check_queue(brands, branches, platforms=["uber"])
        gate = platform_quality_gate(queue, result["branch_presence"], requested=True)
        self.assertEqual(1, gate["completed_checks"])
        self.assertEqual(2, gate["pending_checks"])
        self.assertEqual("DRAFT", gate["report_status"])

    def test_not_found_requires_three_documented_searches(self):
        brands = [{"brand_id": "b", "brand_name": "Marca", "branch_count_amg": 1}]
        branches = [{"brand_id": "b", "branch_id": "one"}]
        with self.assertRaises(ValueError):
            integrate_platform_evidence(brands, branches, [{
                "brand_id": "b", "branch_id": "one", "platform": "rappi",
                "status": "NOT_FOUND", "checked_at": "2026-09-25",
                "method": "integrated_browser", "search_queries": "solo una",
            }])


if __name__ == "__main__":
    unittest.main()
