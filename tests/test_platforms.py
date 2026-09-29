import unittest

from scripts.platforms import (
    CONFIRMED,
    ERROR,
    NOT_FOUND,
    PENDING,
    UNCERTAIN,
    create_platform_check_queue,
    executive_platform_label,
    gosom_platform_evidence,
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

    def test_queue_covers_any_confirmed_business_with_three_or_more_locations(self):
        brands = [
            {"brand_id": "target", "brand_name": "Tres", "branch_count_amg": 3,
             "brand_resolution_status": "CONFIRMED", "merchant_family": "Ferretería"},
            {"brand_id": "large", "brand_name": "Treinta", "branch_count_amg": 30,
             "brand_resolution_status": "CONFIRMED", "merchant_family": "Gimnasio"},
            {"brand_id": "watch", "brand_name": "Dos", "branch_count_amg": 2,
             "brand_resolution_status": "CONFIRMED"},
        ]
        branches = [
            {"brand_id": "target", "branch_id": f"t{i}", "branch_name": f"T{i}"}
            for i in range(3)
        ] + [
            {"brand_id": "large", "branch_id": f"l{i}", "branch_name": f"L{i}"}
            for i in range(30)
        ] + [
            {"brand_id": "watch", "branch_id": "w1", "branch_name": "W1"},
            {"brand_id": "watch", "branch_id": "w2", "branch_name": "W2"},
        ]
        queue = create_platform_check_queue(brands, branches)
        self.assertEqual(99, len(queue))
        self.assertEqual({"target", "large"}, {row["brand_id"] for row in queue})
        self.assertEqual({"UBER_EATS", "RAPPI", "DIDI_FOOD"},
                         {row["platform"] for row in queue})

    def test_one_positive_branch_resolves_business_platform_but_not_other_platforms(self):
        brands = [{"brand_id": "b", "brand_name": "Marca", "branch_count_amg": 3,
                   "brand_resolution_status": "CONFIRMED"}]
        branches = [
            {"brand_id": "b", "branch_id": "one", "branch_count_amg": 3,
             "brand_resolution_status": "CONFIRMED"},
            {"brand_id": "b", "branch_id": "two", "branch_count_amg": 3,
             "brand_resolution_status": "CONFIRMED"},
            {"brand_id": "b", "branch_id": "three", "branch_count_amg": 3,
             "brand_resolution_status": "CONFIRMED"},
        ]
        evidence = [{
            "brand_id": "b", "branch_id": "one", "platform": "uber",
            "status": "CONFIRMED", "evidence_url": "https://ubereats.example/one",
            "page_title": "Marca Uno | Uber Eats", "checked_at": "2026-09-25",
            "method": "integrated_browser", "matched_name": "Marca",
            "matched_address": "Calle Uno",
        }]
        result = integrate_platform_evidence(brands, branches, evidence)
        brand = result["brand_presence"][0]
        self.assertEqual(CONFIRMED, brand["uber_status"])
        self.assertEqual(PENDING, brand["rappi_status"])
        self.assertEqual(PENDING, brand["didi_status"])

        queue = create_platform_check_queue(result["brand_presence"], result["branch_presence"])
        self.assertNotIn("UBER_EATS", {row["platform"] for row in queue})
        self.assertEqual(6, len(queue))

        gate = platform_quality_gate(queue, result["branch_presence"], requested=True)
        self.assertEqual(3, gate["expected_checks"])
        self.assertEqual(1, gate["completed_checks"])
        self.assertEqual(2, gate["pending_checks"])
        self.assertEqual("DRAFT", gate["report_status"])

    def test_business_not_found_requires_all_observed_locations(self):
        brand = {"brand_id": "b", "brand_name": "Marca", "branch_count_amg": 3,
                 "brand_resolution_status": "CONFIRMED"}
        branches = [{**brand, "branch_id": value} for value in ("one", "two", "three")]
        base = {
            "brand_id": "b", "platform": "rappi", "status": "NOT_FOUND",
            "checked_at": "2026-09-25", "method": "browser",
            "search_queries": "general || domain || brand+location",
        }
        partial = integrate_platform_evidence([brand], branches, [
            {**base, "branch_id": "one"},
            {**base, "branch_id": "two"},
        ])
        self.assertEqual(PENDING, partial["brand_presence"][0]["rappi_status"])
        final = integrate_platform_evidence([brand], branches, [
            {**base, "branch_id": "one"},
            {**base, "branch_id": "two"},
            {**base, "branch_id": "three"},
        ])
        self.assertEqual(NOT_FOUND, final["brand_presence"][0]["rappi_status"])

    def test_gosom_order_online_creates_positive_provider_evidence_only(self):
        branch = {
            "brand_id": "b", "brand_name": "Marca", "branch_id": "one",
            "branch_name": "Marca Centro", "address": "Calle Uno", "phone": "33",
            "order_online": [
                {"link": "https://www.rappi.com.mx/restaurantes/123", "source": "Rappi"},
                {"link": "https://www.ubereats.com/store/x", "source": "Uber Eats"},
                {"link": "https://example.com/order", "source": "Sitio propio"},
            ],
        }
        rows = gosom_platform_evidence([branch], checked_at="2026-09-29T12:00:00Z")
        self.assertEqual({"RAPPI", "UBER_EATS"}, {row["platform"] for row in rows})
        self.assertTrue(all(row["status"] == CONFIRMED for row in rows))
        self.assertTrue(all(row["verifier_type"] == "gosom" for row in rows))
        self.assertFalse(any(row["status"] == NOT_FOUND for row in rows))

    def test_provider_label_on_unrelated_domain_never_auto_confirms(self):
        branch = {
            "brand_id": "b", "brand_name": "Marca", "branch_id": "one",
            "branch_name": "Marca Centro", "address": "Calle Uno",
            "order_online": [{"link": "https://example.com/order", "source": "Rappi"}],
        }
        self.assertEqual([], gosom_platform_evidence(
            [branch], checked_at="2026-09-29T12:00:00Z"
        ))

    def test_gosom_positive_link_without_branch_identity_stays_for_web_review(self):
        branch = {
            "brand_id": "b", "brand_name": "Marca", "branch_id": "one",
            "branch_name": "Marca Centro", "address": "",
            "order_online": [{"link": "https://www.rappi.com.mx/restaurantes/123", "source": "Rappi"}],
        }
        self.assertEqual([], gosom_platform_evidence(
            [branch], checked_at="2026-09-29T12:00:00Z"
        ))

    def test_integration_produces_branch_and_business_presence_with_evidence(self):
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
        presence = result["brand_presence"][0]
        self.assertEqual(presence["uber_status"], CONFIRMED)
        self.assertEqual(presence["uber_branches_found"], 1)
        self.assertEqual(presence["uber_branches_total"], 2)

    def test_conflicting_evidence_on_same_branch_is_uncertain(self):
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

    def test_quality_gate_is_three_independent_decisions_per_business(self):
        branches = [{
            "brand_id": "b", "branch_id": "one", "branch_count_amg": 3,
            "brand_resolution_status": "CONFIRMED",
            "uber_status": CONFIRMED, "rappi_status": PENDING, "didi_status": ERROR,
        }]
        gate = platform_quality_gate([], branches, requested=True)
        self.assertEqual({
            "expected_checks": 3, "completed_checks": 1,
            "pending_checks": 1, "errors": 1, "report_status": "DRAFT",
        }, {key: gate[key] for key in (
            "expected_checks", "completed_checks", "pending_checks", "errors", "report_status"
        )})
        self.assertNotIn("delivery_status", gate)

    def test_orphan_evidence_is_rejected(self):
        brands = [{"brand_id": "b", "branch_count_amg": 1}]
        branches = [{"brand_id": "b", "branch_id": "one"}]
        with self.assertRaises(ValueError):
            integrate_platform_evidence(brands, branches, [{
                "brand_id": "b", "branch_id": "missing", "platform": "rappi",
                "status": "NOT_FOUND", "checked_at": "2026-09-24", "method": "public_search",
            }])

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
