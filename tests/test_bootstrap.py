import json
import tempfile
import unittest
from pathlib import Path

from scripts.bootstrap import prepare_local_workspace


class BootstrapTests(unittest.TestCase):
    def test_clean_clone_creates_local_config_and_runtime_layout(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'config').mkdir()
            example = {'concurrency': 1, 'batch_size': 50}
            (root / 'config' / 'settings.example.json').write_text(json.dumps(example))
            result = prepare_local_workspace(root)
            self.assertEqual(json.loads((root / 'config' / 'settings.json').read_text()), example)
            self.assertTrue((root / 'data').is_dir())
            self.assertTrue((root / '.runtime' / 'playwright').is_dir())
            self.assertTrue((root / 'config' / 'secrets' / 'proxies.txt').is_file())
            self.assertIn('config/settings.json', result['created'])

    def test_existing_local_config_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'config').mkdir()
            (root / 'config' / 'settings.example.json').write_text('{"concurrency": 1}')
            (root / 'config' / 'settings.json').write_text('{"concurrency": 7}')
            prepare_local_workspace(root)
            self.assertEqual(json.loads((root / 'config' / 'settings.json').read_text())['concurrency'], 7)


if __name__ == '__main__':
    unittest.main()
