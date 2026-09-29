"""Small transactional SQLite snapshot store."""
import json
import sqlite3
from contextlib import closing
from pathlib import Path


GEOGRAPHY_COLUMNS = {
    'municipality': "TEXT NOT NULL DEFAULT 'UNKNOWN'",
    'inside_core_periferico': 'INTEGER',
    'inside_urban_amg': 'INTEGER',
    'inside_amg_full': 'INTEGER NOT NULL DEFAULT 0',
    'geography_source': 'TEXT',
    'geography_verified_at': 'TEXT',
}


def _add_missing_columns(db, table, columns):
    existing = {row[1] for row in db.execute(f'PRAGMA table_info({table})')}
    for name, declaration in columns.items():
        if name not in existing:
            db.execute(f'ALTER TABLE {table} ADD COLUMN {name} {declaration}')


def _geography_values(row):
    source = row.get('geography_source')
    if source is not None and not isinstance(source, str):
        source = json.dumps(source, ensure_ascii=False)
    return (
        row.get('municipality') or 'UNKNOWN',
        row.get('inside_core_periferico'),
        row.get('inside_urban_amg'),
        bool(row.get('inside_amg_full', False)),
        source,
        row.get('geography_verified_at'),
    )


def init_db(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as db, db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            description TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, month TEXT, scope TEXT, report_json TEXT);
        CREATE TABLE IF NOT EXISTS places (record_id TEXT PRIMARY KEY, data_json TEXT);
        CREATE TABLE IF NOT EXISTS observations (run_id TEXT, record_id TEXT, data_json TEXT, PRIMARY KEY(run_id,record_id));
        CREATE TABLE IF NOT EXISTS brands (brand_id TEXT PRIMARY KEY, data_json TEXT);
        CREATE TABLE IF NOT EXISTS brand_members (run_id TEXT, brand_id TEXT, record_id TEXT, PRIMARY KEY(run_id,record_id));
        CREATE TABLE IF NOT EXISTS source_aliases (
            alias TEXT PRIMARY KEY, record_id TEXT NOT NULL,
            first_seen_run TEXT, last_seen_run TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_source_aliases_record ON source_aliases(record_id);
        CREATE TABLE IF NOT EXISTS run_history (
            history_id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, month TEXT, scope TEXT,
            report_json TEXT, archived_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS observation_history (
            history_id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, record_id TEXT,
            data_json TEXT, archived_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS brand_member_history (
            history_id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, brand_id TEXT,
            record_id TEXT, archived_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_observations_record ON observations(record_id);
        CREATE INDEX IF NOT EXISTS idx_brand_members_brand_run ON brand_members(brand_id,run_id);
        ''')
        _add_missing_columns(db, 'places', GEOGRAPHY_COLUMNS)
        _add_missing_columns(db, 'observations', GEOGRAPHY_COLUMNS)
        db.execute('CREATE INDEX IF NOT EXISTS idx_places_municipality ON places(municipality)')
        db.execute('CREATE INDEX IF NOT EXISTS idx_observations_municipality ON observations(municipality)')
        db.execute('INSERT OR IGNORE INTO schema_migrations(version,description) VALUES (?,?)',
                   (2, 'Add filterable multi-layer geography columns and indexes'))
        db.execute('PRAGMA user_version=2')


def save_run(path, report, places, brands):
    init_db(path)
    dump = lambda obj: json.dumps(obj, ensure_ascii=False)
    with closing(sqlite3.connect(path)) as db, db:
        db.execute('''INSERT INTO run_history(run_id,month,scope,report_json)
                      SELECT run_id,month,scope,report_json FROM runs WHERE run_id=?''', (report['run_id'],))
        db.execute('''INSERT INTO observation_history(run_id,record_id,data_json)
                      SELECT run_id,record_id,data_json FROM observations WHERE run_id=?''', (report['run_id'],))
        db.execute('''INSERT INTO brand_member_history(run_id,brand_id,record_id)
                      SELECT run_id,brand_id,record_id FROM brand_members WHERE run_id=?''', (report['run_id'],))
        db.execute('INSERT OR REPLACE INTO runs VALUES (?,?,?,?)',
                   (report['run_id'], report.get('month'), report.get('scope'), dump(report)))
        db.execute('DELETE FROM observations WHERE run_id=?', (report['run_id'],))
        db.execute('DELETE FROM brand_members WHERE run_id=?', (report['run_id'],))
        for row in places:
            geography = _geography_values(row)
            db.execute('''INSERT OR REPLACE INTO places
                (record_id,data_json,municipality,inside_core_periferico,inside_urban_amg,
                 inside_amg_full,geography_source,geography_verified_at)
                VALUES (?,?,?,?,?,?,?,?)''', (row['record_id'], dump(row), *geography))
            db.execute('''INSERT INTO observations
                (run_id,record_id,data_json,municipality,inside_core_periferico,inside_urban_amg,
                 inside_amg_full,geography_source,geography_verified_at)
                VALUES (?,?,?,?,?,?,?,?,?)''', (report['run_id'], row['record_id'], dump(row), *geography))
            db.execute('INSERT INTO brand_members VALUES (?,?,?)', (report['run_id'], row['brand_id'], row['record_id']))
        db.executemany('INSERT OR REPLACE INTO brands VALUES (?,?)', [(b['brand_id'], dump(b)) for b in brands])


def _row_aliases(row):
    """Return stable source aliases from strongest to weakest."""
    import hashlib
    aliases = []
    for field in ("place_id", "cid", "data_id", "link"):
        value = str(row.get(field) or "").strip()
        if value:
            aliases.append(f"{field}:{value}")
    name = str(row.get("normalized_name") or "").strip()
    address = str(row.get("address") or "").strip().casefold()
    lat, lon = row.get("latitude"), row.get("longitude")
    if name and address:
        payload = f"{name}|{address}"
        aliases.append("name_address:" + hashlib.sha256(payload.encode()).hexdigest()[:24])
    if name and lat is not None and lon is not None:
        try:
            payload = f"{name}|{float(lat):.5f}|{float(lon):.5f}"
            aliases.append("name_coord:" + hashlib.sha256(payload.encode()).hexdigest()[:24])
        except (TypeError, ValueError):
            pass
    return list(dict.fromkeys(aliases))


def resolve_record_ids(path, rows, run_id):
    """Assign persistent internal record IDs using an alias table.

    Source IDs remain aliases. A newly observed stronger identifier never changes
    an already known internal record_id when any existing alias still matches.
    """
    import hashlib
    path = Path(path)
    init_db(path)
    output = []
    with closing(sqlite3.connect(path)) as db, db:
        for source in rows:
            row = dict(source)
            aliases = _row_aliases(row)
            existing = []
            for alias in aliases:
                found = db.execute("SELECT record_id FROM source_aliases WHERE alias=?", (alias,)).fetchone()
                if found:
                    existing.append(found[0])
            existing = list(dict.fromkeys(existing))
            if len(existing) > 1:
                raise ValueError(
                    "Conflicting persistent source aliases map this observation to multiple entities; "
                    "manual identity review required"
                )
            elif existing:
                record_id = existing[0]
            else:
                seed = aliases[0] if aliases else str(row.get("record_id") or json.dumps(row, sort_keys=True, default=str))
                record_id = "R_" + hashlib.sha256(seed.encode()).hexdigest()[:24]
            row["record_id"] = record_id
            row["source_aliases"] = aliases
            for alias in aliases:
                db.execute(
                    """INSERT INTO source_aliases(alias,record_id,first_seen_run,last_seen_run)
                       VALUES (?,?,?,?)
                       ON CONFLICT(alias) DO UPDATE SET last_seen_run=excluded.last_seen_run""",
                    (alias, record_id, run_id, run_id),
                )
            output.append(row)
    return output
