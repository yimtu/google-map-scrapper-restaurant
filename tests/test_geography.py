import json
import unittest
from pathlib import Path

from scripts.geography import GeographyIndex


def feature(name, scope, bounds, **properties):
    west, south, east, north = bounds
    return {
        "type": "Feature",
        "properties": {"scope": scope, "municipality": name, **properties},
        "geometry": {"type": "Polygon", "coordinates": [[
            [west, south], [east, south], [east, north], [west, north], [west, south]
        ]]},
    }


class GeographyTests(unittest.TestCase):
    def test_assigns_one_municipality_and_all_available_layers(self):
        geography = GeographyIndex({"type": "FeatureCollection", "features": [
            feature("Guadalajara", "AMG_FULL", (-104, 20, -103, 21),
                    approved=True, source="official municipalities"),
            feature(None, "CORE_PERIFERICO", (-103.8, 20.2, -103.2, 20.8),
                    approved=True, source="approved core"),
            feature(None, "URBAN_AMG", (-103.9, 20.1, -103.1, 20.9),
                    approved=True, source="official urban footprint"),
        ]})

        result = geography.assign({"latitude": 20.5, "longitude": -103.5})

        self.assertEqual(result["municipality"], "Guadalajara")
        self.assertIs(result["inside_core_periferico"], True)
        self.assertIs(result["inside_urban_amg"], True)
        self.assertIs(result["inside_amg_full"], True)
        self.assertIn("official municipalities", result["geography_source"])
        self.assertTrue(result["geography_verified_at"].endswith("+00:00"))

    def test_ambiguous_or_invalid_point_is_unknown(self):
        geography = GeographyIndex({"type": "FeatureCollection", "features": [
            feature("Guadalajara", "AMG_FULL", (-104, 20, -103, 21), approved=True),
            feature("Zapopan", "AMG_FULL", (-103.7, 20.3, -103.2, 20.8), approved=True),
        ]})
        ambiguous = geography.assign({"latitude": 20.5, "longitude": -103.5})
        invalid = geography.assign({"latitude": None, "longitude": -103.5})

        self.assertEqual(ambiguous["municipality"], "UNKNOWN")
        self.assertIs(ambiguous["inside_amg_full"], True)
        self.assertEqual(invalid["municipality"], "UNKNOWN")
        self.assertIs(invalid["inside_amg_full"], False)

    def test_missing_layers_are_explicitly_pending_not_invented(self):
        geography = GeographyIndex({"type": "FeatureCollection", "features": [
            feature("Guadalajara", "AMG_FULL", (-104, 20, -103, 21),
                    approved=True, source="official municipalities"),
        ]})
        result = geography.assign({"latitude": 20.5, "longitude": -103.5})

        self.assertIsNone(result["inside_core_periferico"])
        self.assertIsNone(result["inside_urban_amg"])
        self.assertEqual(geography.layer_status["CORE_PERIFERICO"], "unapproved")
        self.assertEqual(geography.layer_status["URBAN_AMG"], "pending_source")

    def test_existing_official_file_has_nine_municipal_features(self):
        path = Path(__file__).parents[1] / "territory/processed/territory.geojson"
        territory = json.loads(path.read_text(encoding="utf-8-sig"))
        geography = GeographyIndex(territory)
        result = geography.assign({"latitude": 20.67, "longitude": -103.35})

        self.assertEqual(len(geography.municipal_features), 9)
        self.assertEqual(result["municipality"], "Guadalajara")
        self.assertIs(result["inside_amg_full"], True)


if __name__ == "__main__":
    unittest.main()
