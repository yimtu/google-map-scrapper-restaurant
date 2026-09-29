import unittest

from scripts.categories import (
    ADDITIONAL,
    REQUESTED,
    UNCLASSIFIED,
    classify_requested_relationship,
    resolve_requested_categories,
)
from scripts.dedupe import deduplicate


class CategoryContractTests(unittest.TestCase):
    def base_config(self):
        return {
            "active_queries": ["restaurante"],
            "category_catalog": {
                "tacos": {
                    "request_aliases": ["taco", "taquería"],
                    "queries": ["tacos", "taquería"],
                    "google_category_aliases": ["taquería", "taco restaurant"],
                    "name_aliases": ["tacos", "taquería"],
                },
                "nieves": {
                    "request_aliases": ["helado", "heladería"],
                    "queries": ["nieves", "heladería"],
                    "google_category_aliases": ["heladería", "ice cream"],
                    "name_aliases": ["nieves", "helados", "heladería"],
                },
            },
        }

    def test_requested_categories_expand_queries_and_freeze_rules(self):
        resolved = resolve_requested_categories(self.base_config(), ["tacos", "nieves"])
        self.assertEqual(["tacos", "nieves"], resolved["requested_categories"])
        self.assertEqual(["tacos", "taquería", "nieves", "heladería"],
                         resolved["active_queries"])
        self.assertIn("google_category_aliases",
                      resolved["requested_category_rules"]["tacos"])

    def test_unknown_business_category_is_supported_without_food_assumptions(self):
        resolved = resolve_requested_categories(self.base_config(), ["ferreterías"])
        self.assertEqual(["ferreterías"], resolved["requested_categories"])
        self.assertEqual(["ferreterías"], resolved["active_queries"])
        decision = classify_requested_relationship({
            "title": "Ferretería Central",
            "google_category": "Ferretería",
        }, resolved)
        self.assertEqual(REQUESTED, decision["category_relationship"])

    def test_google_recommendations_are_preserved_as_additional(self):
        resolved = resolve_requested_categories(self.base_config(), ["tacos"])
        decision = classify_requested_relationship({
            "title": "Sushi Factory",
            "google_category": "Restaurante de sushi",
            "google_categories": ["Restaurante japonés", "Sushi"],
        }, resolved)
        self.assertEqual(ADDITIONAL, decision["category_relationship"])
        self.assertEqual([], decision["matched_requested_categories"])

    def test_generic_google_category_stays_unclassified(self):
        resolved = resolve_requested_categories(self.base_config(), ["tacos"])
        decision = classify_requested_relationship({
            "title": "El Güero",
            "google_category": "Restaurante",
        }, resolved)
        self.assertEqual(UNCLASSIFIED, decision["category_relationship"])

    def test_secondary_google_categories_can_prove_requested_match(self):
        resolved = resolve_requested_categories(self.base_config(), ["nieves"])
        decision = classify_requested_relationship({
            "title": "Dulce Frío",
            "google_category": "Cafetería",
            "google_categories": ["Cafetería", "Heladería"],
        }, resolved)
        self.assertEqual(REQUESTED, decision["category_relationship"])
        self.assertEqual(["nieves"], decision["matched_requested_categories"])

    def test_dedupe_never_loses_requested_match_seen_on_another_observation(self):
        rows = [
            {
                "place_id": "p1", "title": "Local", "normalized_name": "local",
                "address": "Uno", "category_relationship": "ADDITIONAL",
                "requested_categories": ["tacos"], "matched_requested_categories": [],
                "google_categories": ["Restaurante"], "category_evidence": "outside",
                "provenance": [],
            },
            {
                "place_id": "p1", "title": "Local", "normalized_name": "local",
                "address": "Uno", "category_relationship": "REQUESTED",
                "requested_categories": ["tacos"], "matched_requested_categories": ["tacos"],
                "google_categories": ["Taquería"], "category_evidence": "tacos:google_category=Taquería",
                "provenance": [],
            },
        ]
        result = deduplicate(rows)
        self.assertEqual(1, len(result))
        self.assertEqual("REQUESTED", result[0]["category_relationship"])
        self.assertEqual(["tacos"], result[0]["matched_requested_categories"])
        self.assertEqual({"Restaurante", "Taquería"}, set(result[0]["google_categories"]))


if __name__ == "__main__":
    unittest.main()
