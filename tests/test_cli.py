import subprocess
import sys
import unittest
from pathlib import Path


class CliTests(unittest.TestCase):
    def test_help_lists_operational_commands(self):
        root = Path(__file__).parents[1]
        result = subprocess.run([sys.executable, str(root / "foodscan.py"), "--help"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        for command in ("setup", "doctor", "territory", "plan", "pilot", "approve", "monthly",
                        "resume", "status", "export", "compare", "proxy", "update-gosom",
                        "expand-brands", "verify-platforms"):
            self.assertIn(command, result.stdout)

    def test_plan_help_exposes_human_categories_not_internal_scraper_knobs(self):
        root = Path(__file__).parents[1]
        result = subprocess.run(
            [sys.executable, str(root / "foodscan.py"), "plan", "--help"],
            capture_output=True, text=True,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("--categories", result.stdout)
        self.assertNotIn("--depth", result.stdout)
        self.assertNotIn("--zoom", result.stdout)
        self.assertNotIn("--workers", result.stdout)


if __name__ == "__main__":
    unittest.main()
