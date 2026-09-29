import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from scripts.storage import init_db, resolve_record_ids, save_run


class StorageMigrationTests(unittest.TestCase):
    def test_existing_database_gets_additive_geography_columns(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.sqlite"
            with closing(sqlite3.connect(path)) as db, db:
                db.execute("CREATE TABLE places (record_id TEXT PRIMARY KEY, data_json TEXT)")
                db.execute("CREATE TABLE observations (run_id TEXT, record_id TEXT, data_json TEXT, PRIMARY KEY(run_id,record_id))")
                db.execute("CREATE TABLE runs (run_id TEXT PRIMARY KEY, month TEXT, scope TEXT, report_json TEXT)")
                db.execute("CREATE TABLE brands (brand_id TEXT PRIMARY KEY, data_json TEXT)")
                db.execute("CREATE TABLE brand_members (run_id TEXT, brand_id TEXT, record_id TEXT, PRIMARY KEY(run_id,record_id))")
                db.execute("INSERT INTO places VALUES ('legacy', '{\"record_id\":\"legacy\",\"future\":7}')")

            init_db(path)

            with closing(sqlite3.connect(path)) as db:
                columns = {row[1] for row in db.execute("PRAGMA table_info(places)")}
                payload = json.loads(db.execute("SELECT data_json FROM places WHERE record_id='legacy'").fetchone()[0])
            self.assertTrue({"municipality", "inside_core_periferico", "inside_urban_amg",
                             "inside_amg_full", "geography_source", "geography_verified_at"} <= columns)
            self.assertEqual(payload["future"], 7)

    def test_geography_is_filterable_and_observation_history_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "foodscan.sqlite"
            base = {"record_id": "p1", "brand_id": "b1", "municipality": "Zapopan",
                    "inside_core_periferico": True, "inside_urban_amg": None,
                    "inside_amg_full": True, "geography_source": ["IIEG"],
                    "geography_verified_at": "2026-09-24T00:00:00+00:00"}
            brand = {"brand_id": "b1"}
            save_run(path, {"run_id": "r1", "scope": "AMG_FULL"}, [base], [brand])
            changed = {**base, "municipality": "Guadalajara"}
            save_run(path, {"run_id": "r2", "scope": "AMG_FULL"}, [changed], [brand])

            with closing(sqlite3.connect(path)) as db:
                current = db.execute("SELECT municipality, inside_core_periferico, inside_urban_amg "
                                     "FROM places WHERE record_id='p1'").fetchone()
                history = db.execute("SELECT run_id, municipality FROM observations ORDER BY run_id").fetchall()
                source = db.execute("SELECT geography_source FROM places WHERE record_id='p1'").fetchone()[0]
            self.assertEqual(current, ("Guadalajara", 1, None))
            self.assertEqual(history, [("r1", "Zapopan"), ("r2", "Guadalajara")])
            self.assertEqual(json.loads(source), ["IIEG"])

    def test_persistent_identity_survives_new_stronger_source_id(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "foodscan.sqlite"
            first = [{"record_id": "legacy", "normalized_name": "cafe azul", "address": "Uno 1",
                      "latitude": 20.7, "longitude": -103.4}]
            resolved1 = resolve_record_ids(path, first, "r1")
            second = [{"record_id": "other", "place_id": "new-place-id",
                       "normalized_name": "cafe azul", "address": "Uno 1",
                       "latitude": 20.7, "longitude": -103.4}]
            resolved2 = resolve_record_ids(path, second, "r2")
            self.assertEqual(resolved1[0]["record_id"], resolved2[0]["record_id"])
            self.assertIn("place_id:new-place-id", resolved2[0]["source_aliases"])

    def test_conflicting_aliases_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "foodscan.sqlite"
            first = [{"place_id": "p1", "normalized_name": "uno", "address": "A"}]
            second = [{"cid": "c2", "normalized_name": "dos", "address": "B"}]
            resolve_record_ids(path, first, "r1")
            resolve_record_ids(path, second, "r2")
            conflict = [{"place_id": "p1", "cid": "c2",
                         "normalized_name": "tres", "address": "C"}]
            with self.assertRaises(ValueError):
                resolve_record_ids(path, conflict, "r3")

    def test_reprocessing_same_run_archives_previous_observation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "foodscan.sqlite"
            brand = {"brand_id": "b1"}
            first = {"record_id": "p1", "brand_id": "b1", "municipality": "Zapopan"}
            second = {**first, "municipality": "Guadalajara"}
            save_run(path, {"run_id": "same", "scope": "AMG_FULL"}, [first], [brand])
            save_run(path, {"run_id": "same", "scope": "AMG_FULL"}, [second], [brand])
            with closing(sqlite3.connect(path)) as db:
                archived = db.execute(
                    "SELECT data_json FROM observation_history WHERE run_id='same' AND record_id='p1'"
                ).fetchall()
            self.assertEqual(1, len(archived))
            self.assertEqual("Zapopan", json.loads(archived[0][0])["municipality"])


if __name__ == "__main__":
    unittest.main()
