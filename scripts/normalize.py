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
    """Normalize stable aliases while preserving every raw Gosom field."""
    record = dict(raw)
    categories = raw.get('categories', [])
    if isinstance(categories, str):
        try:
            parsed = json.loads(categories)
            categories = parsed if isinstance(parsed, list) else [categories]
        except (json.JSONDecodeError, TypeError):
            categories = [part.strip() for part in categories.split(',') if part.strip()]
    longitude = raw.get('longitude')
    if longitude in (None, ''):
        longitude = raw.get('longtitude')
    website = raw.get('website')
    if website in (None, ''):
        website = raw.get('web_site')
    description = raw.get('descriptions')
    if description in (None, ''):
        description = raw.get('description')
    record.update(
        title=str(raw.get('title') or raw.get('name') or '').strip(),
        latitude=coordinate(raw.get('latitude'), 90),
        longitude=coordinate(longitude, 180),
        normalized_name=normalize_name(raw.get('title') or raw.get('name')),
        website=website or '',
        descriptions=description or '',
        google_category=raw.get('category', ''),
        google_categories=categories or [],
        provenance=[source or {}],
    )
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
