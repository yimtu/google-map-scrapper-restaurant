"""Pinned native Gosom installation and a deliberately tiny live smoke test."""
import csv
import hashlib
import json
import os
import platform
import shutil
import sqlite3
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

RELEASE_API = 'https://api.github.com/repos/gosom/google-maps-scraper/releases/latest'


def now():
    return datetime.now(timezone.utc).isoformat()


def select_asset(assets, system=None, machine=None):
    system = (system or platform.system()).lower()
    machine = (machine or platform.machine()).lower()
    arch = {'x86_64': 'amd64', 'amd64': 'amd64', 'aarch64': 'arm64', 'arm64': 'arm64'}.get(machine, machine)
    suffix = f'-{system}-{arch}' + ('.exe' if system == 'windows' else '')
    found = [a for a in assets if a['name'].endswith(suffix)]
    if len(found) != 1:
        raise ValueError(f'No native release for {system}/{arch}. Diagnose native source compilation; Docker is not installed automatically.')
    return found[0]


def platform_key(system=None, machine=None):
    system = (system or platform.system()).lower()
    machine = (machine or platform.machine()).lower()
    arch = {'x86_64': 'amd64', 'amd64': 'amd64', 'aarch64': 'arm64', 'arm64': 'arm64'}.get(machine, machine)
    return f'{system}-{arch}'


def has_foodscan_asset(root, system=None, machine=None):
    metadata = Path(root).resolve() / 'tools' / 'gosom-foodscan' / 'VERSION.json'
    if not metadata.is_file():
        return False
    info = json.loads(metadata.read_text(encoding='utf-8'))
    return platform_key(system, machine) in info.get('release_assets', {})


def binary_path(root):
    return Path(root).resolve() / 'tools' / 'gosom' / ('gosom.exe' if os.name == 'nt' else 'gosom')


def patched_binary_path(root):
    return Path(root).resolve() / 'tools' / 'gosom-foodscan' / ('gosom-foodscan.exe' if os.name == 'nt' else 'gosom-foodscan')


def active_binary_path(root):
    patched = patched_binary_path(root)
    metadata = patched.parent / 'VERSION.json'
    if patched.is_file() and metadata.is_file():
        info = json.loads(metadata.read_text(encoding='utf-8'))
        if sha256(patched) != info.get('sha256'):
            raise ValueError('Patched Gosom integrity mismatch; rebuild or restore the validated executable.')
        return patched
    return binary_path(root)


def gosom_env(root):
    runtime = Path(root).resolve() / '.runtime'
    return {**os.environ, 'DISABLE_TELEMETRY': '1',
            'PLAYWRIGHT_BROWSERS_PATH': str(runtime / 'browsers'),
            'PLAYWRIGHT_DRIVER_PATH': str(runtime / 'playwright-driver')}


def request(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'FoodScan-AMG/0.1'}), timeout=90)


def sha256(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def install_gosom(root, update=False):
    binary = binary_path(root)
    metadata = binary.parent / 'VERSION.json'
    if binary.exists() and metadata.exists() and not update:
        pinned = json.loads(metadata.read_text(encoding='utf-8'))
        if sha256(binary) != pinned['sha256']:
            raise ValueError('Gosom integrity mismatch. Run update-gosom to reinstall deliberately.')
        return pinned
    with request(RELEASE_API) as response:
        release = json.load(response)
    asset = select_asset(release['assets'])
    binary.parent.mkdir(parents=True, exist_ok=True)
    temporary = binary.with_suffix('.download' + binary.suffix)
    try:
        with request(asset['browser_download_url']) as source, temporary.open('wb') as target:
            shutil.copyfileobj(source, target)
        digest = sha256(temporary)
        upstream = asset.get('digest')
        if upstream and upstream != 'sha256:' + digest:
            raise ValueError('Downloaded Gosom does not match the upstream SHA256 digest.')
        temporary.chmod(0o755)
        checked = subprocess.run([str(temporary), '-version'], env=gosom_env(root), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30, check=True)
        temporary.replace(binary)
        info = {'version': release['tag_name'], 'release_date': release['published_at'],
                'download_url': asset['browser_download_url'], 'download_date': now(),
                'sha256': digest, 'upstream_digest_verified': bool(upstream),
                'os': platform.system(), 'architecture': platform.machine(),
                'version_output': (checked.stdout + checked.stderr).strip()}
        metadata.write_text(json.dumps(info, indent=2) + '\n', encoding='utf-8')
        return info
    finally:
        temporary.unlink(missing_ok=True)


def install_foodscan_gosom(root, update=False, system=None, machine=None):
    """Install the pinned patched build from a published, hash-verified release asset."""
    root = Path(root).resolve()
    binary = patched_binary_path(root)
    metadata = binary.parent / 'VERSION.json'
    if not metadata.is_file():
        raise FileNotFoundError('tools/gosom-foodscan/VERSION.json is missing from this distribution.')
    info = json.loads(metadata.read_text(encoding='utf-8'))
    if binary.is_file() and not update:
        if sha256(binary) != info.get('sha256'):
            raise ValueError('Patched Gosom integrity mismatch; reinstall the release asset.')
        return info

    key = platform_key(system, machine)
    configured = info.get('release_assets', {}).get(key)
    if not configured:
        raise ValueError(f'No FoodScan release asset is configured for {key}; use a supported asset or reproduce the build from tools/gosom-foodscan/patch.')
    if isinstance(configured, str):
        url, expected = configured, info.get('sha256')
    else:
        url, expected = configured.get('url'), configured.get('sha256')
    if not url or not expected:
        raise ValueError(f'FoodScan release asset metadata for {key} must include URL and SHA-256.')

    binary.parent.mkdir(parents=True, exist_ok=True)
    temporary = binary.with_suffix('.download' + binary.suffix)
    try:
        with request(url) as source, temporary.open('wb') as target:
            shutil.copyfileobj(source, target)
        digest = sha256(temporary)
        if digest != expected:
            raise ValueError('Downloaded FoodScan Gosom does not match the pinned SHA-256.')
        temporary.chmod(0o755)
        checked = subprocess.run([str(temporary), '-version'], env=gosom_env(root),
                                 capture_output=True, text=True, encoding='utf-8',
                                 errors='replace', timeout=30, check=True)
        temporary.replace(binary)
        return {**info, 'sha256': digest, 'installed_asset': url,
                'installed_at': now(), 'version_output': (checked.stdout + checked.stderr).strip()}
    finally:
        temporary.unlink(missing_ok=True)


def install_browser(root):
    root = Path(root).resolve()
    (root / '.runtime').mkdir(parents=True, exist_ok=True)
    logs = root / 'logs'
    logs.mkdir(parents=True, exist_ok=True)
    env = {**gosom_env(root), 'PLAYWRIGHT_INSTALL_ONLY': '1'}
    with (logs / 'browser-install.log').open('w', encoding='utf-8') as log:
        result = subprocess.run([str(active_binary_path(root))], cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=900)
    if result.returncode:
        raise RuntimeError('Chromium installation failed. See logs/browser-install.log for native dependency diagnosis.')
    active = active_binary_path(root)
    report = {'ok': True, 'installed_at': now(), 'gosom_sha256': sha256(active), 'binary': str(active)}
    (root / '.runtime' / 'browser-install.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


def smoke_test(root):
    root = Path(root).resolve()
    folder = root / 'tests' / 'smoke' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    folder.mkdir(parents=True)
    queries = folder / 'input.txt'
    raw = folder / 'raw.csv'
    queries.write_text('https://www.google.com/maps/search/cafeteria+Guadalajara/@20.6736,-103.344,14z #!# SMOKE_ONLY\n', encoding='utf-8')
    active = active_binary_path(root)
    command = [str(active), '-input', str(queries), '-results', str(raw), '-c', '1',
               '-browser-pool-size', '1', '-pages-per-browser', '1', '-lang', 'es', '-depth', '1',
               '-exit-on-inactivity', '1m', '-resume']
    with (folder / 'gosom.log').open('w', encoding='utf-8') as log:
        result = subprocess.run(command, cwd=root, env=gosom_env(root), stdout=log, stderr=subprocess.STDOUT, timeout=240)
    rows = []
    if raw.exists():
        with raw.open(encoding='utf-8-sig', newline='') as handle:
            rows = list(csv.DictReader(handle))
    from .normalize import read_raw, normalize_record
    from .dedupe import deduplicate
    from .brands import group_brands
    from .storage import save_run
    rows = read_raw(raw) if raw.exists() else []
    valid = [row for row in rows if row.get('title') and row.get('category')]
    places, brands, _ = group_brands(deduplicate([normalize_record(row, {'smoke': True}) for row in rows]))
    save_run(folder / 'pipeline.db', {'run_id': folder.name, 'scope': 'SMOKE_ONLY'}, places, brands)
    with sqlite3.connect(folder / 'smoke.db') as connection:
        connection.execute('CREATE TABLE observations (raw_json TEXT NOT NULL)')
        connection.executemany('INSERT INTO observations VALUES (?)', [(json.dumps(row, ensure_ascii=False),) for row in rows])
        count = connection.execute('SELECT COUNT(*) FROM observations').fetchone()[0]
    log_text = (folder / 'gosom.log').read_text(encoding='utf-8', errors='replace')
    report = {'ok': result.returncode == 0 and bool(valid) and count == len(rows),
              'returncode': result.returncode, 'raw_records': len(rows), 'valid_title_category': len(valid),
              'sqlite_records': count, 'pipeline_places': len(places), 'raw_path': str(raw), 'folder': str(folder), 'date': now(), 'production_data': False}
    report['binary'] = str(active)
    report['diagnosis'] = diagnose_scraper_error(log_text) if not report['ok'] else 'ok'
    (folder / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    (root / '.runtime' / 'smoke-latest.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


def diagnose_scraper_error(text):
    value = str(text).casefold()
    if 'unexpected page type' in value:
        return 'browser_runtime_bug'
    if 'target closed' in value or 'page, context or browser has been closed' in value:
        return 'target_closed'
    if 'captcha' in value or 'unusual traffic' in value or 'recaptcha' in value:
        return 'captcha_or_google_block'
    if any(term in value for term in ('connection refused', 'no such host', 'net::err_', 'timeout exceeded')):
        return 'network_error'
    if any(term in value for term in ('selector', 'parse', 'extract')):
        return 'parser_error'
    return 'unknown_error'
