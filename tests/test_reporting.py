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
             "merchant_family": "Restaurante", "rating_avg": 4.5, "reviews_total": 100,
             "website": "https://target.example", "phones": "3312345678", "brand_scope": "local",
             "confidence": 0.9, "last_verified": "2026-09-24"},
            {"brand_id": "watch", "brand_name": "Marca Radar", "branches_amg": 2,
             "branches_core": 1, "branches_urban_amg": 2, "municipalities": "Zapopan",
             "merchant_family": "Cafe", "confidence": 0.8},
            {"brand_id": "large", "brand_name": "Marca Grande", "branches_amg": 21,
             "branches_core": 10, "branches_urban_amg": 18, "municipalities": "AMG",
             "merchant_family": "Panaderia", "confidence": 0.95},
        ]
        places = []
        for brand in brands:
            for index in range(brand["branches_amg"]):
                places.append({"brand_id": brand["brand_id"], "brand_name": brand["brand_name"],
                               "record_id": f'{brand["brand_id"]}-{index}', "place_id": f'p-{brand["brand_id"]}-{index}',
                               "title": f'{brand["brand_name"]} {index + 1}', "municipality": "Zapopan",
                               "inside_core_periferico": index == 0, "inside_urban_amg": index < 3,
                               "inside_amg_full": True, "address": f'Calle {index + 1}',
                               "latitude": 20.7, "longitude": -103.4, "review_rating": 4.5,
                               "review_count": 10, "merchant_family": brand["merchant_family"]})
        presence = [{"brand_id": "target", "platform": "Uber Eats", "status": "CONFIRMED",
                     "branches_found": 2, "branches_total": 3}]
        evidence = [{"brand_id": "target", "brand_name": "Marca Target", "branch_id": "target-0",
                     "branch_name": "Marca Target 1", "platform": "Uber Eats", "status": "CONFIRMED",
                     "evidence_url": "https://evidence.example", "evidence_type": "listing",
                     "matched_name": "Marca Target", "matched_address": "Calle 1", "matched_phone": "3312345678",
                     "checked_at": "2026-09-24", "method": "manual", "confidence": "high", "notes": ""}]
        report = {"month": "2026-09", "date": "2026-09-24T12:00:00Z", "gosom_version": "1.18.1",
                  "scope": "AMG_FULL", "warnings": ["Fixture controlado"], "run_id": "fixture-run"}
        return places, brands, presence, evidence, report

    def test_exports_pdf_and_traceability_are_reconstructible(self):
        places, brands, presence, evidence, report = self._fixture()
        with tempfile.TemporaryDirectory() as folder:
            snapshot = Path(folder)
            pdf = snapshot / "custom.pdf"
            result = generate_standard_reports(snapshot, places, brands, presence, evidence, [], report,
                                               pdf_path=pdf, charts_enabled=False)
            self.assertEqual(pdf, result["pdf"])
            expected = {"master_places.csv", "brands_master.csv", "prospects_3_20.csv", "watchlist_2.csv",
                        "large_21_plus.csv", "prospect_branches.csv", "platform_presence.csv",
                        "platform_evidence.csv", "changes.csv", "report_traceability.json"}
            self.assertTrue(expected.issubset({path.name for path in snapshot.iterdir()}))

            trace = json.loads((snapshot / "report_traceability.json").read_text(encoding="utf-8"))
            self.assertFalse(trace["charts_enabled"])
            metrics = {item["metric_id"]: item for item in trace["metrics"]}
            self.assertEqual(1, metrics["target_brands_3_20"]["display_value"])
            self.assertEqual("branch_count_amg >= 3 AND branch_count_amg <= 20",
                             metrics["target_brands_3_20"]["logic"])
            with (snapshot / metrics["target_brands_3_20"]["source_file"]).open(encoding="utf-8-sig") as stream:
                self.assertEqual(metrics["target_brands_3_20"]["display_value"], sum(1 for _ in csv.DictReader(stream)))
            self.assertEqual("platform_evidence.csv", trace["platform_evidence"]["evidence_file"])
            self.assertEqual(["target"], trace["tables"][0]["displayed_brand_ids"])

            reader = PdfReader(str(pdf))
            self.assertEqual(3, len(reader.pages))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            self.assertIn("Establecimientos unicos", text)
            self.assertIn(str(len(places)), text)
            self.assertIn("Marca Target", text)
            self.assertIn("Marca Radar", text)
            self.assertNotIn("PLACEHOLDER", text.upper())
            self.assertNotIn("GRAFICA", text.upper())

    def test_rejects_charts_and_never_invents_platform_rows(self):
        places, brands, _, _, report = self._fixture()
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                generate_standard_reports(Path(folder), places, brands, [], [], [], report, charts_enabled=True)
            generate_standard_reports(Path(folder), places, brands, [], [], [], report, charts_enabled=False)
            with (Path(folder) / "platform_presence.csv").open(encoding="utf-8-sig") as stream:
                self.assertEqual([], list(csv.DictReader(stream)))

    def test_accepts_integrated_brand_presence_shape(self):
        places, brands, _, evidence, report = self._fixture()
        presence = [{"brand_id": "target", "brand_name": "Marca Target",
                     "uber_status": "CONFIRMED", "uber_branches_found": 2, "uber_branches_total": 3,
                     "rappi_status": "NOT_FOUND", "rappi_branches_found": 0, "rappi_branches_total": 3,
                     "didi_status": "UNCERTAIN", "didi_branches_found": 0, "didi_branches_total": 3}]
        with tempfile.TemporaryDirectory() as folder:
            generate_standard_reports(Path(folder), places, brands, presence, evidence, [], report)
            with (Path(folder) / "prospects_3_20.csv").open(encoding="utf-8-sig") as stream:
                row = next(csv.DictReader(stream))
            self.assertEqual("Sí", row["uber_status"])
            self.assertEqual("No confirmada", row["rappi_status"])
            self.assertEqual("Requiere revisión", row["didi_status"])

    def test_pending_gate_creates_only_draft_and_never_final(self):
        places, brands, presence, evidence, report = self._fixture()
        report.update({"platform_verification_requested": True, "expected_checks": 9,
                       "completed_checks": 1, "pending_checks": 8, "errors": 0,
                       "report_status": "DRAFT"})
        with tempfile.TemporaryDirectory() as folder:
            snapshot = Path(folder)
            (snapshot / "FoodScan_Report.pdf").write_bytes(b"stale final")
            result = generate_standard_reports(snapshot, places, brands, presence, evidence, [], report)
            self.assertEqual("DRAFT", result["report_status"])
            self.assertEqual("FoodScan_Report_DRAFT.pdf", result["pdf"].name)
            self.assertFalse((snapshot / "FoodScan_Report.pdf").exists())
            self.assertTrue((snapshot / "FoodScan_Report_PREVIOUS.pdf").exists())

    def test_platform_section_is_omitted_when_not_evaluated(self):
        places, brands, presence, evidence, report = self._fixture()
        report.update({"platform_verification_requested": False, "expected_checks": 0,
                       "completed_checks": 0, "pending_checks": 0, "errors": 0,
                       "report_status": "FINAL"})
        with tempfile.TemporaryDirectory() as folder:
            result = generate_standard_reports(Path(folder), places, brands, presence, evidence, [], report)
            text = "\n".join(page.extract_text() or "" for page in PdfReader(str(result["pdf"])).pages)
            self.assertNotIn("Presencia en plataformas", text)
            self.assertNotIn("UNCERTAIN", text)
            self.assertNotIn("PENDING", text)
            self.assertNotIn("ERROR", text)

    def test_incomplete_counts_force_draft_even_without_explicit_pending(self):
        places, brands, presence, evidence, report = self._fixture()
        report.update({"platform_verification_requested": True, "expected_checks": 9,
                       "completed_checks": 8, "pending_checks": 0, "errors": 0,
                       "report_status": "FINAL"})
        with tempfile.TemporaryDirectory() as folder:
            result = generate_standard_reports(Path(folder), places, brands, presence, evidence, [], report)
            self.assertEqual("DRAFT", result["report_status"])
            self.assertEqual("FoodScan_Report_DRAFT.pdf", result["pdf"].name)

    def test_final_archives_a_stale_draft(self):
        places, brands, presence, evidence, report = self._fixture()
        report.update({"platform_verification_requested": True, "expected_checks": 9,
                       "completed_checks": 9, "pending_checks": 0, "errors": 0,
                       "report_status": "FINAL"})
        with tempfile.TemporaryDirectory() as folder:
            snapshot = Path(folder)
            (snapshot / "FoodScan_Report_DRAFT.pdf").write_bytes(b"stale draft")
            result = generate_standard_reports(snapshot, places, brands, presence, evidence, [], report)
            self.assertEqual("FoodScan_Report.pdf", result["pdf"].name)
            self.assertFalse((snapshot / "FoodScan_Report_DRAFT.pdf").exists())
            self.assertTrue((snapshot / "FoodScan_Report_DRAFT_PREVIOUS.pdf").exists())


if __name__ == "__main__":
    unittest.main()
