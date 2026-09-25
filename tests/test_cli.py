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
        for command in ("setup", "doctor", "territory", "plan", "pilot", "monthly",
                        "resume", "status", "export", "compare", "proxy", "update-gosom",
                        "verify-platforms"):
            self.assertIn(command, result.stdout)


if __name__ == "__main__":
    unittest.main()
