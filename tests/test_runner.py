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
                "raw_file": str(raw), "depth": 5, "jobs": [{"job_id": "JOB_A"}]}]
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


if __name__ == "__main__":
    unittest.main()
