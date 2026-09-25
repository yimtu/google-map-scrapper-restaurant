"""Spreadsheet-safe exports and cautious temporal comparisons."""
import csv
import json
from pathlib import Path
from .dedupe import identity


def cell(value):
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@', '\t', '\r')):
        return "'" + value
    return value


def write_csv(path, rows, fields=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fields or list(dict.fromkeys(k for row in rows for k in row)) or ['record_id']
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows({k: cell(row.get(k, '')) for k in fields} for row in rows)


def export_mymaps(folder, rows):
    folder = Path(folder)
    files = []
    columns = ['brand', 'branch_name', 'merchant_family', 'branches_amg', 'phone', 'rating', 'latitude', 'longitude']
    for scope, selected in [('amg', rows), ('core', [r for r in rows if r.get('in_core')])]:
        for start in range(0, len(selected), 2000):
            path = folder / f'mymaps_{scope}_{start // 2000 + 1:03}.csv'
            mapped = [{**r, 'brand': r.get('brand_name', ''), 'branch_name': r.get('title', ''),
                       'rating': r.get('review_rating', '')} for r in selected[start:start + 2000]]
            write_csv(path, mapped, columns)
            files.append(path)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'README_IMPORT.md').write_text('1. Abrir Google My Maps y crear un mapa.\n2. Importar cada CSV en una capa.\n3. Elegir latitude/longitude.\n4. Usar branch_name como título.\n5. Estilizar por merchant_family.\nCada archivo tiene máximo 2,000 filas.\n', encoding='utf-8')
    return files


def compare_records(previous, current, historical_ids=None):
    old, new = {identity(r): r for r in previous}, {identity(r): r for r in current}
    historical_ids = historical_ids or set()
    fields = ('title', 'address', 'phone', 'website', 'status', 'review_rating', 'review_count', 'category')
    changes = []
    for key, row in new.items():
        status = str(row.get('status', '')).casefold()
        closed = status in {'closed', 'permanently closed', 'cerrado permanentemente'}
        changed = [f for f in fields if str(old.get(key, {}).get(f, '')) != str(row.get(f, ''))]
        event = ('closed' if closed and (key not in old or old[key].get('status') != row.get('status')) else
                 'reappeared' if key not in old and key in historical_ids else
                 'new' if key not in old else 'changed' if changed else '')
        if event:
            changes.append({'record_id': key, 'title': row.get('title', ''), 'change': event, 'fields': changed})
    changes.extend({'record_id': key, 'title': row.get('title', ''), 'change': 'missing_this_run', 'fields': []}
                   for key, row in old.items() if key not in new)
    return changes


def compare_snapshots(previous, current):
    def load(path):
        path = Path(path)
        canonical = path / 'processed' / 'places.json'
        return json.loads(canonical.read_text(encoding='utf-8'))
    changes = compare_records(load(previous), load(current))
    write_csv(Path(current) / 'changes.csv', changes, ['record_id', 'title', 'change', 'fields'])
    return changes
