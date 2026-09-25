import hashlib
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from scripts.gosom import binary_path, install_browser, install_gosom
from scripts.health import doctor


class _Response:
    status = 200
    def __enter__(self): return self
    def __exit__(self, *_args): return False


class HealthTests(unittest.TestCase):
    def prepared_root(self, folder):
        root = Path(folder)
        binary = binary_path(root)
        binary.parent.mkdir(parents=True)
        binary.write_bytes(b"known binary")
        digest = hashlib.sha256(binary.read_bytes()).hexdigest()
        (binary.parent / "VERSION.json").write_text(json.dumps({"version": "v-test", "sha256": digest}))
        (root / ".runtime" / "browsers" / "chromium-test").mkdir(parents=True)
        (root / ".runtime" / "browser-install.json").write_text("{}")
        (root / ".runtime" / "smoke-latest.json").write_text(json.dumps({"ok": True, "raw_records": 1}))
        (root / "territory" / "processed").mkdir(parents=True)
        (root / "territory" / "processed" / "territory.geojson").write_text(
            json.dumps({"type": "FeatureCollection", "features": [{"type": "Feature",
                "properties": {"zone": "TEST", "scope": "AMG_FULL", "density": "high", "approved": True},
                "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}}]})
        )
        (root / "config" / "secrets").mkdir(parents=True)
        (root / "config" / "settings.json").write_text(json.dumps({"concurrency": 1, "batch_size": 50}))
        (root / "config" / "secrets" / "proxies.txt").write_text("# optional\n")
        (root / "data").mkdir()
        with closing(sqlite3.connect(root / "data" / "foodscan.db")) as db:
            db.execute("create table ok(value text)")
            db.commit()
        return root

    def test_doctor_ready_without_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.prepared_root(folder)
            with patch("scripts.health.request", return_value=_Response()):
                report = doctor(root)
            self.assertTrue(report["ready"], report)
            self.assertTrue(any(c["name"] == "Latest successful snapshot" for c in report["checks"]))

    def test_doctor_accepts_release_asset_without_official_binary(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.prepared_root(folder)
            official = binary_path(root)
            official.unlink()
            (official.parent / "VERSION.json").unlink()
            patched = root / "tools" / "gosom-foodscan" / "gosom-foodscan.exe"
            patched.parent.mkdir(parents=True)
            patched.write_bytes(b"published patched binary")
            digest = hashlib.sha256(patched.read_bytes()).hexdigest()
            (patched.parent / "VERSION.json").write_text(json.dumps({
                "version": "0.1.0", "upstream_gosom_version": "v1.18.1", "sha256": digest,
            }))
            with patch("scripts.health.request", return_value=_Response()):
                report = doctor(root)
            self.assertTrue(report["ready"], report)

    def test_existing_install_is_pinned_and_browser_install_is_recorded(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.prepared_root(folder)
            self.assertEqual(install_gosom(root)["version"], "v-test")
            class Result: returncode = 0
            with patch("scripts.gosom.subprocess.run", return_value=Result()):
                result = install_browser(root)
            self.assertTrue(result["ok"])

    def test_doctor_rejects_an_incoherent_final_report_gate(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.prepared_root(folder)
            snapshot = root / "snapshots" / "2026-09"
            snapshot.mkdir(parents=True)
            (snapshot / "run_report.json").write_text(json.dumps({
                "status": "completed", "report_status": "FINAL", "expected_checks": 9,
                "completed_checks": 8, "pending_checks": 1, "errors": 0,
            }))
            with patch("scripts.health.request", return_value=_Response()):
                report = doctor(root)
            gate = next(check for check in report["checks"] if check["name"] == "Report quality gate")
            self.assertFalse(gate["ok"])
            self.assertFalse(report["ready"])


if __name__ == "__main__":
    unittest.main()
