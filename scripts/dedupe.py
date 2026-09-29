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


def _merge_list(left, right):
    values = []
    for source in (left, right):
        if isinstance(source, str):
            source = [source] if source else []
        for item in source or []:
            if item not in values:
                values.append(item)
    return values


def _merge_relationship(left, right):
    order = {"UNCLASSIFIED": 0, "ADDITIONAL": 1, "REQUESTED": 2}
    return max((str(left or "UNCLASSIFIED"), str(right or "UNCLASSIFIED")),
               key=lambda value: order.get(value, -1))


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
            merged = {**row, **{k: v for k, v in old.items() if v not in ('', None, [])},
                      'provenance': old['provenance'] + row.get('provenance', [{}])}
            merged['google_categories'] = _merge_list(old.get('google_categories'), row.get('google_categories'))
            merged['requested_categories'] = _merge_list(old.get('requested_categories'), row.get('requested_categories'))
            merged['matched_requested_categories'] = _merge_list(
                old.get('matched_requested_categories'), row.get('matched_requested_categories')
            )
            merged['category_relationship'] = _merge_relationship(
                old.get('category_relationship'), row.get('category_relationship')
            )
            merged['category_evidence'] = '; '.join(dict.fromkeys(
                part for part in (
                    str(old.get('category_evidence') or '').split('; ')
                    + str(row.get('category_evidence') or '').split('; ')
                ) if part
            ))
            result[match] = merged
        for key in keys:
            indexes.setdefault(key, []).append(match)
    return result
