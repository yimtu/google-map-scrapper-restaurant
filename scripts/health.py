"""Operational health checks; errors and summaries never reveal proxy secrets."""
import hashlib
import json
import re
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from contextlib import closing
from pathlib import Path
from urllib.parse import urlsplit
from .gosom import active_binary_path, sha256, request
from .territory import load_territory


def parse_proxies(text):
    proxies = []
    for number, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        try:
            parsed = urlsplit(line)
            valid = (parsed.scheme in {'http', 'https', 'socks5', 'socks5h'} and parsed.hostname
                     and parsed.port and not parsed.path and not parsed.query and not parsed.fragment
                     and not any(char.isspace() for char in line))
            if not valid:
                raise ValueError()
        except ValueError:
            raise ValueError(f'Invalid proxy on line {number}; expected scheme://[user:password@]host:port.') from None
        proxies.append(line)
    return proxies


def redact(text):
    return re.sub(r'(?i)\b(?:https?|socks5h?)://[^\s\"\']+', '[proxy/url redacted]', str(text))


def doctor(root, network=True):
    root = Path(root).resolve()
    checks = []
    def add(name, ok, detail, required=True):
        checks.append({'name': name, 'ok': bool(ok), 'detail': detail, 'required': required})
    add('Python', sys.version_info >= (3, 11), sys.version.split()[0])
    try:
        active = active_binary_path(root)
        info = json.loads((active.parent / 'VERSION.json').read_text(encoding='utf-8'))
        add('Gosom', active.exists() and sha256(active) == info['sha256'],
            info.get('version') or info.get('upstream_gosom_version', 'unknown'))
    except (OSError, ValueError, KeyError):
        add('Gosom', False, 'Run foodscan setup: native binary/version missing or invalid.')
    try:
        active = active_binary_path(root)
        patched = active.parent.name == 'gosom-foodscan'
        add('Gosom engine', active.is_file(), 'Patched FoodScan build' if patched else 'Official build')
    except (OSError, ValueError, KeyError) as error:
        add('Gosom engine', False, str(error))
    settings_path = root / 'config' / 'settings.json'
    try:
        settings = json.loads(settings_path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        settings = {}

    browser = root / '.runtime' / 'browser-install.json'
    binaries = list((root / '.runtime' / 'browsers').glob('chromium*'))
    add('Browser', browser.exists() and bool(binaries), 'Chromium in .runtime' if browser.exists() else 'Run foodscan setup.')
    smoke = root / '.runtime' / 'smoke-latest.json'
    try:
        smoke_info = json.loads(smoke.read_text(encoding='utf-8'))
        current_binary = active_binary_path(root)
        binary_matches = smoke_info.get('gosom_sha256') == sha256(current_binary)
        settings_matches = (
            not settings_path.is_file()
            or smoke_info.get('settings_sha256') == hashlib.sha256(settings_path.read_bytes()).hexdigest()
        )
        stamp = datetime.fromisoformat(str(smoke_info.get('date', '')).replace('Z', '+00:00'))
        age_hours = (datetime.now(timezone.utc) - stamp.astimezone(timezone.utc)).total_seconds() / 3600
        max_age = float(settings.get('smoke_max_age_hours', 24))
        fresh = 0 <= age_hours <= max_age
        smoke_ok = bool(smoke_info.get('ok')) and binary_matches and settings_matches and fresh
        smoke_detail = (
            f"OK: {smoke_info.get('raw_records', 0)} records; age={age_hours:.1f}h"
            if smoke_ok else
            f"Stale/mismatched smoke: binary={binary_matches}, settings={settings_matches}, age={age_hours:.1f}h"
        )
        add('Scraper smoke', smoke_ok, smoke_detail)
    except (OSError, ValueError, KeyError):
        add('Scraper smoke', False, 'Run foodscan setup to perform a fresh live browser check.')
    territory = root / 'territory' / 'processed' / 'territory.geojson'
    try:
        data = load_territory(territory, require_approved=True)
        scopes = sorted({feature['properties']['scope'] for feature in data['features']})
        add('Territory', bool(scopes), 'Approved scopes: ' + ', '.join(scopes))
    except (OSError, ValueError):
        add('Territory', False, 'ONE-TIME HUMAN INPUT REQUIRED: import approved GeoJSON/KML/KMZ.')
    if settings:
        concurrency = int(settings.get('concurrency', 1))
        balanced = int(settings.get('balanced_concurrency', 2))
        browser_pool = int(settings.get('browser_pool', 1))
        config_ok = 1 <= concurrency <= balanced <= 2 and 1 <= browser_pool <= 2 and int(settings.get('batch_size', 0)) > 0
        add('Config', config_ok, f'Conservative runtime: c={concurrency}, balanced<={balanced}, pool={browser_pool}.')
    else:
        add('Config', False, 'Run setup; settings.json missing/invalid.')
    try:
        secret = root / 'config' / 'secrets' / 'proxies.txt'
        proxies = parse_proxies(secret.read_text(encoding='utf-8-sig') if secret.exists() else '')
        add('Proxy', True, f'{len(proxies)} configured' if proxies else 'Not configured - optional')
    except ValueError as error:
        add('Proxy', False, str(error))
    try:
        with tempfile.TemporaryFile(dir=root):
            pass
        add('Write permissions', True, 'OK')
    except OSError:
        add('Write permissions', False, 'Project folder is not writable.')
    free = shutil.disk_usage(root).free / (1024 ** 3)
    add('Disk', free >= 5, f'{free:.1f} GB free (5 GB recommended)')
    db = root / 'data' / 'foodscan.db'
    try:
        if not db.exists():
            raise OSError()
        with closing(sqlite3.connect(f'{db.as_uri()}?mode=ro', uri=True)) as connection:
            ok = connection.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
        add('Database', ok, 'SQLite quick_check')
    except (OSError, sqlite3.Error):
        add('Database', False, 'Run foodscan setup: database unavailable.')
    if network:
        try:
            with request('https://www.google.com/maps') as response:
                add('Internet', response.status == 200, 'Google Maps reachable; scraper health requires smoke/pilot.')
        except OSError:
            add('Internet', False, 'Could not reach Google Maps; check internet/proxy.')
    successful = []
    latest_report = None
    for path in sorted((root / 'snapshots').glob('*/run_report.json')):
        try:
            report = json.loads(path.read_text(encoding='utf-8'))
            latest_report = report
            if report.get('status') in {'completed', 'success'}:
                successful.append(path.parent.name)
        except (OSError, ValueError):
            continue
    add('Latest successful snapshot', True, successful[-1] if successful else 'None yet', False)
    if latest_report is None:
        add('Report quality gate', True, 'No report generated yet.', False)
    else:
        report_status = latest_report.get('report_status', 'DRAFT')
        expected = int(latest_report.get('expected_checks', 0) or 0)
        completed = int(latest_report.get('completed_checks', 0) or 0)
        pending = int(latest_report.get('pending_checks', 0) or 0)
        errors = int(latest_report.get('errors', 0) or 0)
        coherent = report_status != 'FINAL' or (pending == 0 and errors == 0 and completed == expected)
        add('Report quality gate', coherent,
            f'{report_status}: expected={expected}, completed={completed}, pending={pending}, errors={errors}',
            report_status == 'FINAL')
    return {'ready': all(c['ok'] for c in checks if c['required']), 'checks': checks}
