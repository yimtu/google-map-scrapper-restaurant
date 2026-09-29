import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.runner import batch_progress, execute_manifest, load_manifest


class RunnerTests(unittest.TestCase):
    def test_batch_progress_uses_resume_sidecar(self):
        with tempfile.TemporaryDirectory() as td:
            raw = Path(td) / "batch.csv"
            sidecar = Path(str(raw) + ".resume.json")
            sidecar.write_text(json.dumps({"version": 1, "completed_inputs": ["JOB_A"]}))
            batch = {"jobs": [{"job_id": "JOB_A"}, {"job_id": "JOB_B"}], "raw_file": str(raw)}
            self.assertEqual(batch_progress(batch), (1, 2, ["JOB_B"]))

    def test_execute_always_uses_resume_and_persists_status(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            binary = root / "gosom.exe"
            binary.touch()
            input_file = root / "input.txt"
            input_file.write_text("https://example.invalid #!# JOB_A\n")
            raw = root / "raw.csv"
            manifest_path = root / "run.json"
            manifest_path.write_text(json.dumps({
                "run_id": "2026-09-AMG_FULL", "scope": "AMG_FULL", "month": "2026-09",
                "status": "planned", "batches": [{"batch_id": "batch_001", "input": str(input_file),
                "raw_file": str(raw), "depth": 5, "jobs": [{"job_id": "JOB_A", "url": "https://example.invalid"}]}]
            }))

            def fake_run(args, **kwargs):
                self.assertIn("-resume", args)
                Path(str(raw) + ".resume.json").write_text(
                    json.dumps({"version": 1, "completed_inputs": ["JOB_A"]})
                )
                class Result:
                    returncode = 0
                    stdout = ""
                    stderr = ""
                return Result()

            with patch("scripts.runner.subprocess.run", side_effect=fake_run):
                result = execute_manifest(root, manifest_path, binary=binary)
            self.assertEqual(result["status"], "completed")
            self.assertEqual(load_manifest(manifest_path)["batches"][0]["status"], "completed")

    def test_runner_uses_frozen_settings_not_live_config(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "config").mkdir()
            (root / "config" / "settings.json").write_text(json.dumps({
                "concurrency": 9, "browser_pool": 9, "pages_per_browser": 9
            }))
            binary = root / "gosom"
            binary.write_bytes(b"binary")
            import hashlib
            digest = hashlib.sha256(binary.read_bytes()).hexdigest()
            input_file = root / "input.txt"
            input_file.write_text("https://example.invalid #!# JOB_A\n")
            raw = root / "raw.csv"
            manifest_path = root / "run.json"
            manifest_path.write_text(json.dumps({
                "run_id": "frozen", "status": "planned", "gosom_sha256": digest,
                "frozen_config": {"settings": {
                    "concurrency": 2, "browser_pool": 2, "pages_per_browser": 1,
                    "batch_max_retries": 0, "batch_timeout_seconds": 60,
                }},
                "batches": [{"batch_id": "batch_001", "input": str(input_file),
                             "raw_file": str(raw), "depth": 5,
                             "jobs": [{"job_id": "JOB_A", "url": "https://example.invalid"}]}],
            }))

            def fake_run(args, **kwargs):
                self.assertEqual("2", args[args.index("-c") + 1])
                self.assertEqual("2", args[args.index("-browser-pool-size") + 1])
                self.assertEqual("1", args[args.index("-pages-per-browser") + 1])
                Path(str(raw) + ".resume.json").write_text(
                    json.dumps({"completed_inputs": ["JOB_A"]})
                )
                class Result:
                    returncode = 0
                    stdout = ""
                    stderr = ""
                return Result()

            with patch("scripts.runner.subprocess.run", side_effect=fake_run):
                result = execute_manifest(root, manifest_path, binary=binary)
            self.assertEqual("completed", result["status"])

    def test_runner_rejects_changed_binary(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            binary = root / "gosom"
            binary.write_bytes(b"new")
            input_file = root / "input.txt"
            input_file.write_text("x #!# JOB_A\n")
            manifest_path = root / "run.json"
            manifest_path.write_text(json.dumps({
                "run_id": "mismatch", "status": "planned", "gosom_sha256": "0" * 64,
                "frozen_config": {"settings": {}},
                "batches": [{"batch_id": "b", "input": str(input_file),
                             "raw_file": str(root / "raw.csv"), "depth": 5,
                             "jobs": [{"job_id": "JOB_A", "url": "x"}]}],
            }))
            with self.assertRaises(RuntimeError):
                execute_manifest(root, manifest_path, binary=binary)

    def test_runner_rejects_mutated_batch_input(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            binary = root / "gosom"
            binary.write_bytes(b"binary")
            import hashlib
            digest = hashlib.sha256(binary.read_bytes()).hexdigest()
            input_file = root / "input.txt"
            input_file.write_text("tampered #!# JOB_A\n")
            manifest_path = root / "run.json"
            manifest_path.write_text(json.dumps({
                "run_id": "tampered", "status": "planned", "gosom_sha256": digest,
                "frozen_config": {"settings": {}},
                "batches": [{"batch_id": "b", "input": str(input_file),
                             "raw_file": str(root / "raw.csv"), "depth": 5,
                             "jobs": [{"job_id": "JOB_A", "url": "approved"}]}],
            }))
            with self.assertRaises(RuntimeError):
                execute_manifest(root, manifest_path, binary=binary)

    def test_google_block_stops_before_later_batches(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            binary = root / "gosom"
            binary.write_bytes(b"binary")
            import hashlib
            digest = hashlib.sha256(binary.read_bytes()).hexdigest()
            batches = []
            for index in (1, 2):
                inp = root / f"input{index}.txt"
                inp.write_text(f"x #!# JOB_{index}\n")
                batches.append({
                    "batch_id": f"b{index}", "input": str(inp),
                    "raw_file": str(root / f"raw{index}.csv"), "depth": 5,
                    "jobs": [{"job_id": f"JOB_{index}", "url": "x"}],
                })
            manifest_path = root / "run.json"
            manifest_path.write_text(json.dumps({
                "run_id": "blocked", "status": "planned", "gosom_sha256": digest,
                "frozen_config": {"settings": {
                    "batch_max_retries": 2, "batch_timeout_seconds": 60,
                    "concurrency": 1, "browser_pool": 1, "pages_per_browser": 1,
                }},
                "batches": batches,
            }))
            calls = []
            def fake_run(*args, **kwargs):
                calls.append(1)
                class Result:
                    returncode = 1
                    stdout = "CAPTCHA unusual traffic"
                    stderr = ""
                return Result()
            with patch("scripts.runner.subprocess.run", side_effect=fake_run):
                result = execute_manifest(root, manifest_path, binary=binary)
            self.assertEqual(1, len(calls))
            self.assertEqual("google_block", result.get("stop_reason"))
            self.assertEqual("incomplete", result["status"])


if __name__ == "__main__":
    unittest.main()
