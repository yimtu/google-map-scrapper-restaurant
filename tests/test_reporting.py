import csv
import json
import tempfile
import unittest
from pathlib import Path

from pypdf import PdfReader

from scripts.reporting import generate_standard_reports


class ReportingTests(unittest.TestCase):
    def _fixture(self):
        brands = [
            {"brand_id": "target", "brand_name": "Marca Target", "branches_amg": 3,
             "branches_core": 2, "branches_urban_amg": 3, "municipalities": "Guadalajara; Zapopan",
             "merchant_family": "Restaurante", "category_scope": "REQUESTED",
             "requested_branch_count": 3, "additional_branch_count": 0, "unclassified_branch_count": 0,
             "rating_avg": 4.5, "reviews_total": 100, "website": "https://target.example",
             "phones": "3312345678", "brand_scope": "local", "confidence": 0.99,
             "brand_resolution_status": "CONFIRMED"},
            {"brand_id": "watch", "brand_name": "Marca Radar", "branches_amg": 2,
             "branches_core": 1, "branches_urban_amg": 2, "municipalities": "Zapopan",
             "merchant_family": "Cafe", "category_scope": "REQUESTED",
             "requested_branch_count": 2, "confidence": 0.99,
             "brand_resolution_status": "CONFIRMED"},
            {"brand_id": "large", "brand_name": "Marca Grande", "branches_amg": 21,
             "branches_core": 10, "branches_urban_amg": 18, "municipalities": "AMG",
             "merchant_family": "Ferretería", "category_scope": "ADDITIONAL",
             "additional_branch_count": 21, "confidence": 0.99,
             "brand_resolution_status": "CONFIRMED"},
        ]
        places = []
        for brand in brands:
            for index in range(brand["branches_amg"]):
                relationship = brand.get("category_scope", "UNCLASSIFIED")
                places.append({
                    "brand_id": brand["brand_id"], "brand_name": brand["brand_name"],
                    "record_id": f'{brand["brand_id"]}-{index}',
                    "branch_id": f'{brand["brand_id"]}-{index}',
                    "place_id": f'p-{brand["brand_id"]}-{index}',
                    "title": f'{brand["brand_name"]} {index + 1}',
                    "branch_name": f'{brand["brand_name"]} {index + 1}',
                    "municipality": "Zapopan", "inside_core_periferico": index == 0,
                    "inside_urban_amg": index < 3, "inside_amg_full": True,
                    "address": f'Calle {index + 1}', "latitude": 20.7, "longitude": -103.4,
                    "review_rating": 4.5, "review_count": 10,
                    "merchant_family": brand["merchant_family"],
                    "google_category": brand["merchant_family"],
                    "category_relationship": relationship,
                    "matched_requested_categories": ["tacos"] if relationship == "REQUESTED" else [],
                    "brand_resolution_status": "CONFIRMED",
                    "branch_count_amg": brand["branches_amg"],
                    "uber_status": "CONFIRMED" if index == 0 else "PENDING",
                    "rappi_status": "NOT_FOUND",
                    "didi_status": "UNCERTAIN",
                })
        presence = [
            {"brand_id": "target", "brand_name": "Marca Target",
             "uber_status": "CONFIRMED", "uber_branches_found": 1, "uber_branches_total": 3,
             "rappi_status": "NOT_FOUND", "rappi_branches_found": 0, "rappi_branches_total": 3,
             "didi_status": "UNCERTAIN", "didi_branches_found": 0, "didi_branches_total": 3},
            {"brand_id": "large", "brand_name": "Marca Grande",
             "uber_status": "CONFIRMED", "uber_branches_found": 1, "uber_branches_total": 21,
             "rappi_status": "NOT_FOUND", "rappi_branches_found": 0, "rappi_branches_total": 21,
             "didi_status": "UNCERTAIN", "didi_branches_found": 0, "didi_branches_total": 21},
        ]
        evidence = [{
            "brand_id": "target", "brand_name": "Marca Target", "branch_id": "target-0",
            "branch_name": "Marca Target 1", "platform": "UBER_EATS", "status": "CONFIRMED",
            "evidence_url": "https://evidence.example", "evidence_type": "listing",
            "matched_name": "Marca Target", "matched_address": "Calle 1",
            "checked_at": "2026-09-29", "method": "gosom_order_online",
            "confidence": "high", "notes": "", "verifier_type": "gosom", "protocol_version": "2",
        }]
        report = {
            "month": "2026-09", "date": "2026-09-29T12:00:00Z", "gosom_version": "1.18.1",
            "scope": "AMG_FULL", "warnings": ["Fixture controlado"], "run_id": "fixture-run",
            "requested_categories": ["tacos", "postres", "nieves"],
            "platform_verification_requested": True,
            "expected_checks": 6, "completed_checks": 6, "pending_checks": 0, "errors": 0,
            "report_status": "FINAL", "plan_id": "plan-test", "methodology_hash": "method-test",
        }
        return places, brands, presence, evidence, report

    def test_single_pdf_contains_complete_contract_and_support_files(self):
        places, brands, presence, evidence, report = self._fixture()
        with tempfile.TemporaryDirectory() as folder:
            snapshot = Path(folder)
            result = generate_standard_reports(
                snapshot, places, brands, presence, evidence, [], report, charts_enabled=False)
            expected = {
                "master_places.csv", "brands_master.csv", "prospects_3_20.csv", "watchlist_2.csv",
                "large_21_plus.csv", "multi_location_3_plus.csv", "multi_location_branches.csv",
                "requested_places.csv", "additional_findings.csv", "unclassified_findings.csv",
                "platform_presence.csv", "platform_evidence.csv", "changes.csv",
                "report_traceability.json", "FoodScan_Report.pdf",
            }
            self.assertTrue(expected.issubset({path.name for path in snapshot.iterdir()}))

            trace = json.loads((snapshot / "report_traceability.json").read_text(encoding="utf-8"))
            table = next(row for row in trace["tables"] if row["table_id"] == "multi_location_3_plus")
            self.assertEqual(2, table["row_count_total"])
            self.assertEqual(2, table["rows_displayed"])
            self.assertEqual(
                "every confirmed business with >=3 observed locations; category-independent",
                trace["platform_evidence"]["selection_rule"],
            )

            text = "\n".join(page.extract_text() or "" for page in PdfReader(str(result["pdf"])).pages)
            for expected_text in (
                "Categorías solicitadas", "tacos, postres, nieves",
                "Hallazgos adicionales", "No clasificados",
                "Uber Eats", "Rappi", "DiDi Food",
                "Marca Target", "Marca Grande",
                "Negocios confirmados con 3+ locales",
            ):
                self.assertIn(expected_text, text)
            self.assertNotIn("delivery_status", text)

    def test_large_nonrestaurant_business_gets_three_independent_platform_columns(self):
        places, brands, presence, evidence, report = self._fixture()
        with tempfile.TemporaryDirectory() as folder:
            snapshot = Path(folder)
            generate_standard_reports(snapshot, places, brands, presence, evidence, [], report)
            with (snapshot / "multi_location_3_plus.csv").open(encoding="utf-8-sig") as stream:
                rows = {row["brand_id"]: row for row in csv.DictReader(stream)}
            large = rows["large"]
            self.assertEqual("21", large["branch_count_amg"])
            self.assertEqual("Sí", large["uber_status"])
            self.assertEqual("No confirmada", large["rappi_status"])
            self.assertEqual("Requiere revisión", large["didi_status"])

    def test_report_does_not_truncate_after_eighteen_brands(self):
        places, brands, _, _, report = self._fixture()
        places, brands = [], []
        presence = []
        for index in range(19):
            brand_id = f"b{index:02d}"
            brands.append({
                "brand_id": brand_id, "brand_name": f"Marca {index:02d}",
                "branches_amg": 3, "branch_count_amg": 3,
                "municipalities": "AMG", "merchant_family": "Servicio",
                "category_scope": "REQUESTED", "requested_branch_count": 3,
                "brand_resolution_status": "CONFIRMED", "confidence": 0.99,
            })
            presence.append({
                "brand_id": brand_id, "brand_name": f"Marca {index:02d}",
                "uber_status": "NOT_FOUND", "rappi_status": "NOT_FOUND", "didi_status": "NOT_FOUND",
                "uber_branches_found": 0, "rappi_branches_found": 0, "didi_branches_found": 0,
            })
            for branch in range(3):
                places.append({
                    "brand_id": brand_id, "brand_name": f"Marca {index:02d}",
                    "branch_id": f"{brand_id}-{branch}", "record_id": f"{brand_id}-{branch}",
                    "title": f"Marca {index:02d} {branch}", "branch_name": f"Marca {index:02d} {branch}",
                    "branch_count_amg": 3, "brand_resolution_status": "CONFIRMED",
                    "category_relationship": "REQUESTED", "matched_requested_categories": ["servicios"],
                    "google_category": "Servicio", "municipality": "Zapopan", "address": f"Calle {branch}",
                    "inside_amg_full": True, "review_rating": 4.0, "review_count": 5,
                    "uber_status": "NOT_FOUND", "rappi_status": "NOT_FOUND", "didi_status": "NOT_FOUND",
                })
        report.update({"requested_categories": ["servicios"], "expected_checks": 57,
                       "completed_checks": 57, "report_status": "FINAL"})
        with tempfile.TemporaryDirectory() as folder:
            snapshot = Path(folder)
            result = generate_standard_reports(snapshot, places, brands, presence, [], [], report)
            trace = json.loads((snapshot / "report_traceability.json").read_text())
            table = next(row for row in trace["tables"] if row["table_id"] == "multi_location_3_plus")
            self.assertEqual(19, table["rows_displayed"])
            text = "\n".join(page.extract_text() or "" for page in PdfReader(str(result["pdf"])).pages)
            self.assertIn("Marca 18", text)

    def test_pending_business_platform_decision_forces_draft(self):
        places, brands, presence, evidence, report = self._fixture()
        report.update({"expected_checks": 6, "completed_checks": 5, "pending_checks": 1,
                       "errors": 0, "report_status": "FINAL"})
        with tempfile.TemporaryDirectory() as folder:
            result = generate_standard_reports(Path(folder), places, brands, presence, evidence, [], report)
            self.assertEqual("DRAFT", result["report_status"])
            self.assertEqual("FoodScan_Report_DRAFT.pdf", result["pdf"].name)

    def test_platform_section_is_omitted_only_when_verification_was_not_requested(self):
        places, brands, presence, evidence, report = self._fixture()
        report.update({"platform_verification_requested": False, "expected_checks": 0,
                       "completed_checks": 0, "pending_checks": 0, "errors": 0,
                       "report_status": "FINAL"})
        with tempfile.TemporaryDirectory() as folder:
            result = generate_standard_reports(Path(folder), places, brands, presence, evidence, [], report)
            text = "\n".join(page.extract_text() or "" for page in PdfReader(str(result["pdf"])).pages)
            self.assertNotIn("decisiones independientes", text)


if __name__ == "__main__":
    unittest.main()
