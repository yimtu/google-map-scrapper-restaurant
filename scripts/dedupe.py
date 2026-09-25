"""Conservative establishment identity; shared chain phones never suffice."""
import hashlib
import json
from .normalize import normalize_name

IDENTIFIERS = ('place_id', 'cid', 'data_id', 'link')


def identity(row):
    for field in IDENTIFIERS:
        if row.get(field):
            return f'{field}:{row[field]}'
    payload = [row.get('normalized_name') or normalize_name(row.get('title')),
               normalize_name(row.get('address')), row.get('latitude'), row.get('longitude')]
    return 'fallback:' + hashlib.sha256(json.dumps(payload).encode()).hexdigest()[:24]


def compatible(left, right):
    return all(not left.get(k) or not right.get(k) or str(left[k]) == str(right[k]) for k in IDENTIFIERS[:3])


def deduplicate(rows):
    result, indexes = [], {}
    for row in rows:
        keys = [(k, str(row[k])) for k in IDENTIFIERS if row.get(k)]
        name, address = row.get('normalized_name'), normalize_name(row.get('address'))
        if name and address:
            keys.append(('name_address', name + '|' + address))
        candidates = {i for key in keys for i in indexes.get(key, [])}
        match = next((i for i in sorted(candidates) if compatible(result[i], row)), None)
        if match is None:
            match = len(result)
            result.append({**row, 'record_id': identity(row), 'provenance': list(row.get('provenance', [{}]))})
        else:
            old = result[match]
            result[match] = {**row, **{k: v for k, v in old.items() if v not in ('', None, [])},
                             'provenance': old['provenance'] + row.get('provenance', [{}])}
        for key in keys:
            indexes.setdefault(key, []).append(match)
    return result
