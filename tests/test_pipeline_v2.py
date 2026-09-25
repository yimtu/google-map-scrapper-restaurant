import csv
import json
import tempfile
import unittest
from pathlib import Path

from scripts.geography import GeographyIndex
from scripts.pipeline import place_in_scope, process_snapshot


class PipelineV2Tests(unittest.TestCase):
    def test_scope_mapping_is_explicit_for_urban_and_core(self):
        features = []
        for scope, bounds in (("AMG_FULL", (-2, -2, 2, 2)),
                              ("URBAN_AMG", (-1, -1, 1, 1)),
                              ("CORE_PERIFERICO", (-.5, -.5, .5, .5))):
            west, south, east, north = bounds
            features.append({"type": "Feature", "properties": {
                "zone": scope, "scope": scope, "density": "high", "approved": True,
                "municipality": "Test" if scope == "AMG_FULL" else None,
            }, "geometry": {"type": "Polygon", "coordinates": [[
                [west,south],[east,south],[east,north],[west,north],[west,south]
            ]]}})
        territory = {"type": "FeatureCollection", "features": features}
        geography = GeographyIndex(territory)
        urban_only = geography.assign({"latitude": .75, "longitude": .75})
        self.assertTrue(place_in_scope(urban_only, "URBAN_AMG", territory, geography))
        self.assertFalse(place_in_scope(urban_only, "CORE_PERIFERICO", territory, geography))

    def test_legacy_core_gdl_polygon_wins_over_core_periferico_alias(self):
        def layer(scope, bounds):
            west, south, east, north = bounds
            return {"type": "Feature", "properties": {
                "zone": scope, "scope": scope, "density": "high", "approved": True,
                "municipality": "Test" if scope == "AMG_FULL" else None,
            }, "geometry": {"type": "Polygon", "coordinates": [[
                [west,south],[east,south],[east,north],[west,north],[west,south]
            ]]}}
        territory = {"type": "FeatureCollection", "features": [
            layer("AMG_FULL", (-2,-2,2,2)), layer("CORE_PERIFERICO", (-1,-1,1,1)),
            layer("CORE_GDL", (-.25,-.25,.25,.25)),
        ]}
        geography = GeographyIndex(territory)
        place = geography.assign({"latitude": .75, "longitude": .75})
        self.assertTrue(place_in_scope(place, "CORE_PERIFERICO", territory, geography))
        self.assertFalse(place_in_scope(place, "CORE_GDL", territory, geography))

    def test_processing_emits_geography_commercial_platform_and_traceable_reports(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            snapshot = root / "snapshots" / "2026-09"
            raw = snapshot / "raw" / "batch.csv"
            raw.parent.mkdir(parents=True)
            rows = []
            for index in range(3):
                rows.append({
                    "input_id": f"j{index}", "title": "Cafe Prueba",
                    "place_id": f"p{index}", "latitude": 20.5 + index * .01,
                    "longitude": -103.5, "category": "Cafeteria",
                    "website": "https://cafe-prueba.example", "review_rating": "4.5",
                    "review_count": "10", "address": f"Calle {index}",
                })
            with raw.open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=rows[0]); writer.writeheader(); writer.writerows(rows)
            (root / "config").mkdir()
            (root / "config" / "categories.json").write_text(json.dumps({
                "merchant_families": {"Cafeteria": ["cafeteria"]}, "default_family": "Otros"
            }), encoding="utf-8")
            (root / "config" / "settings.json").write_text(json.dumps({
                "charts_enabled": False, "mymaps_enabled": False
            }), encoding="utf-8")
            territory = {"type": "FeatureCollection", "features": [{
                "type": "Feature",
                "properties": {"zone": "AMG_14039", "scope": "AMG_FULL", "density": "high",
                               "approved": True, "municipality": "Guadalajara", "source": "IIEG"},
                "geometry": {"type": "Polygon", "coordinates": [[
                    [-104, 20], [-103, 20], [-103, 21], [-104, 21], [-104, 20]
                ]]},
            }]}
            manifest = {
                "run_id": "fixture", "month": "2026-09", "scope": "AMG_FULL",
                "status": "completed", "gosom_version": "fixture", "batches": [{
                    "batch_id": "b1", "status": "completed", "raw_file": str(raw),
                    "jobs": [{"job_id": f"j{i}", "query": "cafeteria", "zone": "AMG_14039"}
                             for i in range(3)],
                }],
            }

            report = process_snapshot(root, snapshot, territory, manifest)

            self.assertEqual(1, report["target_brands_3_20"])
            self.assertEqual("pending_source", report["geography_layers"]["URBAN_AMG"])
            expected = {
                "master_places.csv", "brands_master.csv", "prospects_3_20.csv", "watchlist_2.csv",
                "large_21_plus.csv", "prospect_branches.csv", "platform_check_queue.csv",
                "platform_presence.csv", "platform_evidence.csv", "report_traceability.json",
                "metadata.json", "FoodScan_Report.pdf",
            }
            self.assertTrue(expected <= {path.name for path in snapshot.iterdir()})
            with (snapshot / "master_places.csv").open(encoding="utf-8-sig") as stream:
                place = next(csv.DictReader(stream))
            self.assertEqual("Guadalajara", place["municipality"])
            self.assertEqual("True", place["inside_amg_full"])
            self.assertEqual("", place["inside_urban_amg"])
            with (snapshot / "prospects_3_20.csv").open(encoding="utf-8-sig") as stream:
                prospect = next(csv.DictReader(stream))
            self.assertEqual("3", prospect["branch_count_amg"])
            self.assertEqual("Requiere revisión", prospect["uber_status"])
            with (snapshot / "platform_check_queue.csv").open(encoding="utf-8-sig") as stream:
                self.assertEqual(9, len(list(csv.DictReader(stream))))
            trace = json.loads((snapshot / "report_traceability.json").read_text(encoding="utf-8"))
            self.assertFalse(trace["charts_enabled"])
            self.assertEqual("FINAL", trace["report_status"])
            self.assertEqual(0, trace["expected_checks"])
            self.assertFalse(trace["platform_evidence"]["included_in_report"])


if __name__ == "__main__":
    unittest.main()
