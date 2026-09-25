"""Lossless raw ingestion plus small, explicit normalization."""
import csv
import json
import math
import re
import unicodedata
from pathlib import Path


def normalize_name(value):
    value = unicodedata.normalize('NFKD', str(value or '').casefold())
    return ' '.join(re.sub(r'[^\w\s]', ' ', ''.join(c for c in value if not unicodedata.combining(c))).split())


def coordinate(value, maximum):
    try:
        number = float(value)
        return number if math.isfinite(number) and abs(number) <= maximum else None
    except (TypeError, ValueError):
        return None


def normalize_record(raw, source=None):
    record = dict(raw)
    record.update(title=str(raw.get('title') or raw.get('name') or '').strip(),
                  latitude=coordinate(raw.get('latitude'), 90),
                  longitude=coordinate(raw.get('longitude'), 180),
                  normalized_name=normalize_name(raw.get('title') or raw.get('name')),
                  google_category=raw.get('category', ''),
                  google_categories=raw.get('categories', []),
                  provenance=[source or {}])
    return record


def read_raw(path):
    path = Path(path)
    with path.open(encoding='utf-8-sig', newline='') as stream:
        if path.suffix.lower() == '.csv':
            return list(csv.DictReader(stream))
        text = stream.read().strip()
    if not text:
        return []
    if text.startswith('['):
        rows = json.loads(text)
    else:
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError(f'Raw must contain objects: {path.name}')
    return rows
