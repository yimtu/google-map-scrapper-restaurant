import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.platform_verification import resolve_snapshot, verify_platforms


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else []
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


class PlatformVerificationTests(unittest.TestCase):
    def fixture(self, root):
        snapshot = root / "snapshots" / "2026-09"
        (snapshot / "processed").mkdir(parents=True)
        brand = {"brand_id": "b1", "brand_name": "Local", "branch_count_amg": 3,
                 "commercial_segment": "TARGET"}
        places = [
            {**brand, "branch_id": f"p{i}", "title": f"Local {i}", "address": f"Calle {i}"}
            for i in range(1, 4)
        ]
        (snapshot / "processed" / "places.json").write_text(json.dumps(places), encoding="utf-8")
        write_csv(snapshot / "brands.csv", [brand])
        (snapshot / "run_report.json").write_text(json.dumps({"run_id": "r1", "scope": "AMG_FULL"}), encoding="utf-8")
        (root / "config").mkdir()
        (root / "config" / "settings.json").write_text("{}", encoding="utf-8")
        return snapshot

    def test_resolve_snapshot_uses_latest_report(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            older = root / "snapshots" / "2026-08"
            newer = root / "snapshots" / "2026-09"
            older.mkdir(parents=True); newer.mkdir()
            (older / "run_report.json").write_text("{}")
            (newer / "run_report.json").write_text("{}")
            (older / "processed").mkdir()
            (older / "processed" / "places.json").write_text("[]")
            (newer / "processed").mkdir()
            (newer / "processed" / "places.json").write_text("[]")
            self.assertEqual(resolve_snapshot(root), newer)
            self.assertEqual(resolve_snapshot(root, month="2026-08"), older)

    @patch("scripts.platform_verification.generate_standard_reports")
    def test_pending_queue_is_regenerated_and_gate_stays_draft(self, reports):
        reports.return_value = {"report_status": "DRAFT", "pdf": Path("FoodScan_Report_DRAFT.pdf")}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            snapshot = self.fixture(root)
            result = verify_platforms(root, snapshot)
            self.assertEqual(result["expected_checks"], 9)
            self.assertEqual(result["completed_checks"], 0)
            self.assertEqual(result["pending_checks"], 9)
            self.assertEqual(result["report_status"], "DRAFT")
            with (snapshot / "platform_check_queue.csv").open(encoding="utf-8-sig") as stream:
                queue = list(csv.DictReader(stream))
            self.assertEqual(len(queue), 9)
            self.assertTrue(all(row["status"] == "PENDING" for row in queue))

    @patch("scripts.platform_verification.generate_standard_reports")
    def test_complete_evidence_allows_final_only_after_import(self, reports):
        reports.return_value = {"report_status": "FINAL", "pdf": Path("FoodScan_Report.pdf")}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            snapshot = self.fixture(root)
            rows = []
            for branch in ("p1", "p2", "p3"):
                for platform in ("UBER_EATS", "RAPPI", "DIDI_FOOD"):
                    rows.append({"brand_id": "b1", "branch_id": branch, "platform": platform,
                                 "status": "NOT_FOUND", "checked_at": "2026-09-24T12:00:00Z",
                                 "method": "browser: general+domain+location", "notes": "No confirmada",
                                 "search_queries": "general || site:platform || marca ubicación"})
            evidence = root / "agent-evidence.csv"
            write_csv(evidence, rows)
            result = verify_platforms(root, snapshot, evidence_path=evidence)
            self.assertEqual(result["completed_checks"], 9)
            self.assertEqual(result["pending_checks"], 0)
            self.assertEqual(result["report_status"], "FINAL")
            self.assertTrue((snapshot / "platform_evidence.csv").exists())

    @patch("scripts.platform_verification.generate_standard_reports")
    def test_partial_imports_merge_incrementally_and_preserve_audit_fields(self, reports):
        reports.return_value = {"report_status": "DRAFT", "pdf": Path("FoodScan_Report_DRAFT.pdf")}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            snapshot = self.fixture(root)
            first = root / "first.csv"
            second = root / "second.csv"
            base = {"brand_id": "b1", "platform": "UBER_EATS", "status": "NOT_FOUND",
                    "checked_at": "2026-09-24T12:00:00Z", "method": "integrated_browser",
                    "page_title": "Search results", "notes": "No confirmada",
                    "search_queries": "general || site:uber.com || marca ubicación"}
            write_csv(first, [{**base, "branch_id": "p1"}])
            write_csv(second, [{**base, "branch_id": "p2"}])
            first_result = verify_platforms(root, snapshot, evidence_path=first)
            second_result = verify_platforms(root, snapshot, evidence_path=second)
            self.assertEqual(1, first_result["completed_checks"])
            self.assertEqual(2, second_result["completed_checks"])
            with (snapshot / "platform_evidence.csv").open(encoding="utf-8-sig") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(2, len(rows))
            self.assertTrue(all(row["page_title"] == "Search results" for row in rows))
            self.assertTrue(all(row["search_queries"].count("||") == 2 for row in rows))


if __name__ == "__main__":
    unittest.main()
