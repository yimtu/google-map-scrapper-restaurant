import os
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts.gosom import (active_binary_path, diagnose_scraper_error, select_asset, gosom_env,
                           has_foodscan_asset, install_foodscan_gosom)
from scripts.health import parse_proxies, redact

class GosomTests(unittest.TestCase):
    def test_platform_selection(self):
        assets = [{'name': 'google_maps_scraper-1.18.1-windows-amd64.exe'}]
        self.assertEqual(select_asset(assets, 'Windows', 'AMD64'), assets[0])
        with self.assertRaises(ValueError): select_asset(assets, 'Linux', 'arm64')

    def test_environment_isolated(self):
        before = dict(os.environ)
        env = gosom_env(Path('local').resolve())
        self.assertEqual(env['DISABLE_TELEMETRY'], '1')
        self.assertIn('.runtime', env['PLAYWRIGHT_BROWSERS_PATH'])
        self.assertEqual(dict(os.environ), before)

    def test_proxy_credentials_never_in_error(self):
        self.assertEqual(len(parse_proxies('http://user:secret@localhost:8080\n#comment')), 1)
        with self.assertRaises(ValueError) as ctx: parse_proxies('bad://user:secret@localhost:8080')
        self.assertNotIn('secret', str(ctx.exception))
        self.assertNotIn('secret', redact('failed http://user:secret@localhost:8080'))

    def test_bad_proxy_port(self):
        for value in ['http://localhost:bad', 'http://localhost', 'http://host:99/path']:
            with self.assertRaises(ValueError): parse_proxies(value)

    def test_scraper_error_categories(self):
        self.assertEqual(diagnose_scraper_error('unexpected page type'), 'browser_runtime_bug')
        self.assertEqual(diagnose_scraper_error('playwright: target closed'), 'target_closed')
        self.assertEqual(diagnose_scraper_error('Google CAPTCHA unusual traffic'), 'captcha_or_google_block')
        self.assertEqual(diagnose_scraper_error('net::ERR_CONNECTION_REFUSED'), 'network_error')
        self.assertEqual(diagnose_scraper_error('failed to parse selector'), 'parser_error')

    def test_validated_patched_binary_is_selected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            patched = root / 'tools' / 'gosom-foodscan' / ('gosom-foodscan.exe' if os.name == 'nt' else 'gosom-foodscan')
            patched.parent.mkdir(parents=True)
            patched.write_bytes(b'patched')
            digest = hashlib.sha256(b'patched').hexdigest()
            (patched.parent / 'VERSION.json').write_text(json.dumps({'sha256': digest}))
            self.assertEqual(active_binary_path(root), patched)
            patched.write_bytes(b'corrupt')
            with self.assertRaises(ValueError):
                active_binary_path(root)

    def test_patched_release_asset_is_downloaded_and_verified(self):
        class Response:
            def __init__(self): self.stream = io.BytesIO(b'patched-release')
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def read(self, *args): return self.stream.read(*args)

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target = root / 'tools' / 'gosom-foodscan'
            target.mkdir(parents=True)
            digest = hashlib.sha256(b'patched-release').hexdigest()
            (target / 'VERSION.json').write_text(json.dumps({
                'version': '0.2.0', 'sha256': digest,
                'release_assets': {'windows-amd64': 'https://example.invalid/gosom-foodscan.exe'},
            }))
            completed = type('Completed', (), {'stdout': 'v1.18.1', 'stderr': ''})()
            with patch('scripts.gosom.request', return_value=Response()), \
                 patch('scripts.gosom.subprocess.run', return_value=completed):
                info = install_foodscan_gosom(root, system='Windows', machine='AMD64')
            self.assertEqual(info['sha256'], digest)
            self.assertEqual(active_binary_path(root).read_bytes(), b'patched-release')

    def test_missing_patched_asset_has_an_actionable_error(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target = root / 'tools' / 'gosom-foodscan'
            target.mkdir(parents=True)
            (target / 'VERSION.json').write_text(json.dumps({
                'version': '0.2.0', 'sha256': '0' * 64, 'release_assets': {},
            }))
            with self.assertRaisesRegex(ValueError, 'release asset'):
                install_foodscan_gosom(root, system='Windows', machine='AMD64')
            self.assertFalse(has_foodscan_asset(root, system='Linux', machine='arm64'))
