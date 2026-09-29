"""Raw to scoped snapshot, preserving original files and canonical JSON."""
import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from .normalize import normalize_record, normalize_name, read_raw
from .categories import classify_requested_relationship, REQUESTED, ADDITIONAL, UNCLASSIFIED
from .dedupe import deduplicate, identity
from .brands import group_brands
from .exports import write_csv, export_mymaps, compare_records, compare_snapshots
from .storage import save_run, resolve_record_ids
from .geography import GeographyIndex
from .commercial import LARGE, TARGET, WATCHLIST, plan_branch_network_completion, segment_brands
from .platforms import (
    create_platform_check_queue, gosom_platform_evidence,
    integrate_platform_evidence, platform_quality_gate,
)
from .reporting import generate_standard_reports
from .territory import zones_for_point


def classify(row, categories):
    text = normalize_name(str(row.get('google_category', '')) + ' ' + str(row.get('google_categories', '')))
    for family, terms in categories.get('merchant_families', {}).items():
        if any(normalize_name(term) in text for term in terms):
            return family
    return categories.get('default_family', 'Otros alimentos')


def ingest(root, snapshot, manifest):
    rows, warnings = [], []
    for batch in manifest.get('batches', []):
        raw = batch.get('raw_file')
        if not raw:
            continue
        path = Path(raw)
        if not path.is_absolute():
            path = root / path
        if not path.exists():
            warnings.append(f"Missing raw batch: {batch.get('batch_id')}")
            continue
        jobs = {str(j.get('job_id')): j for j in batch.get('jobs', [])}
        for line, row in enumerate(read_raw(path), 1):
            job = jobs.get(str(row.get('input_id', row.get('input', ''))), {})
            source = {'raw_file': str(path.relative_to(root)) if path.is_relative_to(root) else path.name,
                      'raw_row': line, 'batch_id': batch.get('batch_id'), **job}
            rows.append(normalize_record(row, source))
    return rows, warnings


def history(snapshot, manifest):
    previous, historical_ids = [], set()
    for folder in sorted(snapshot.parent.iterdir()):
        canonical, report = folder / 'processed/places.json', folder / 'run_report.json'
        if folder.name >= snapshot.name or not canonical.exists() or not report.exists():
            continue
        info = json.loads(report.read_text(encoding='utf-8'))
        if info.get('scope') != manifest.get('scope') or info.get('incomplete', True):
            continue
        current_method = manifest.get('methodology_hash')
        if not current_method or info.get('methodology_hash') != current_method:
            continue
        rows = json.loads(canonical.read_text(encoding='utf-8'))
        historical_ids.update(str(row.get('record_id') or identity(row)) for row in rows)
        previous = rows
    return previous, historical_ids


def coverage(rows):
    groups = defaultdict(set)
    for row in rows:
        for source in row.get('provenance', []):
            key = (source.get('zone', 'unknown'), source.get('query', 'unknown'), source.get('pass', 1))
            groups[key].add(str(row.get('record_id') or identity(row)))
    return [{'zone': k[0], 'query': k[1], 'pass': k[2], 'unique_places': len(ids)} for k, ids in groups.items()]


def place_in_scope(row, scope, territory, geography):
    fields = {
        'AMG_FULL': 'inside_amg_full',
        'URBAN_AMG': 'inside_urban_amg',
        'CORE_PERIFERICO': 'inside_core_periferico',
        'CORE_GDL': 'inside_core_periferico',
    }
    if scope not in fields:
        raise ValueError(f'Unknown processing scope: {scope}')
    if scope == 'CORE_GDL':
        legacy_features = [feature for feature in territory.get('features', [])
                           if (feature.get('properties') or {}).get('scope') == 'CORE_GDL']
        if legacy_features:
            return any(zone.get('scope') == 'CORE_GDL' for zone in
                       zones_for_point({'type': 'FeatureCollection', 'features': legacy_features},
                                       row.get('latitude'), row.get('longitude'))) \
                if row.get('latitude') is not None and row.get('longitude') is not None else False
    value = row.get(fields[scope])
    layer = 'CORE_PERIFERICO' if scope == 'CORE_GDL' else scope
    if geography.layer_status.get(layer) == 'approved':
        return bool(value)
    # Compatibility for historical CORE_GDL fixtures/snapshots and old AMG
    # territory files. New unresolved layers remain unevaluated and exclude.
    if scope in {'AMG_FULL', 'CORE_GDL'} and row.get('latitude') is not None and row.get('longitude') is not None:
        return any(zone.get('scope') == scope or (scope == 'AMG_FULL' and zone.get('scope') == 'CORE_GDL')
                   for zone in zones_for_point(territory, row['latitude'], row['longitude']))
    return False


def process_snapshot(root: Path, snapshot: Path, territory: dict, manifest: dict):
    root, snapshot = Path(root), Path(snapshot)
    snapshot.mkdir(parents=True, exist_ok=True)
    frozen = manifest.get('frozen_config') or {}
    categories = dict(frozen.get('categories') or {})
    settings = dict(frozen.get('settings') or {})
    if not categories:
        raise ValueError('Snapshot is missing frozen categories; refusing non-reproducible processing')
    geography = GeographyIndex(territory)
    raw, warnings = ingest(root, snapshot, manifest)
    valid, excluded = [], []
    verified_at = datetime.now(timezone.utc).isoformat()
    for row in geography.assign_many(raw, verified_at):
        scope = manifest.get('scope', 'AMG_FULL')
        in_scope = place_in_scope(row, scope, territory, geography)
        if not in_scope or not row['title']:
            excluded.append({**row, 'exclusion_reason': 'outside_scope_or_missing_coordinates_or_title'})
            continue
        category_contract = classify_requested_relationship(row, categories)
        valid.append({**row, **category_contract,
                      'zones': [row.get('municipality', 'UNKNOWN')],
                      'in_core': bool(row.get('inside_core_periferico')),
                      'merchant_family': classify(row, categories)})
    unique = deduplicate(valid)
    production = snapshot.parent.resolve() == (root / 'snapshots').resolve()
    identity_db = root / 'data/foodscan.db' if production else snapshot / 'processed/foodscan.db'
    unique = resolve_record_ids(identity_db, unique, manifest['run_id'])
    places, brands, ambiguous = group_brands(unique)
    brands = plan_branch_network_completion(segment_brands(brands))
    brand_by_id = {row['brand_id']: row for row in brands}
    places = [{**row, **brand_by_id[row['brand_id']]} for row in places]
    evidence_path = snapshot / 'platform_evidence.csv'
    imported_evidence = []
    if evidence_path.exists():
        with evidence_path.open(encoding='utf-8-sig', newline='') as stream:
            imported_evidence = list(csv.DictReader(stream))
    gosom_evidence = gosom_platform_evidence(places, checked_at=verified_at)
    # Gosom links are positive evidence only; imported/web evidence fills the
    # remaining branch×platform checks. Never infer absence from a missing link.
    all_evidence = gosom_evidence + imported_evidence
    platform = integrate_platform_evidence(brands, places, all_evidence)
    brands, places = platform['brand_presence'], platform['branch_presence']
    queue = create_platform_check_queue(brands, places, min_locations=3)
    platform_requested = bool(manifest.get('platform_verification_requested', bool(imported_evidence)))
    gate = platform_quality_gate(queue, places, requested=platform_requested)
    expansion_required = any(
        b.get('brand_resolution_status') == 'CONFIRMED'
        and b.get('commercial_segment') in {WATCHLIST, TARGET}
        for b in brands
    )
    expansion_pending = expansion_required and not bool(manifest.get('brand_expansion_completed'))
    if expansion_pending:
        gate['report_status'] = 'DRAFT'
    previous, historical_ids = history(snapshot, manifest)
    changes = compare_records(previous, places, historical_ids)
    batches = manifest.get('batches', [])
    incomplete = manifest.get('status') not in {'completed', 'complete'} or any(b.get('status') not in {'completed', 'complete'} for b in batches)
    if incomplete:
        warnings.append('Incomplete acquisition: missing_this_run is not evidence of closure.')
    if not raw:
        warnings.append('No raw records acquired; check scraper health.')
    candidates = [b for b in brands
                  if b['commercial_segment'] in {WATCHLIST, TARGET}
                  and b.get('brand_resolution_status') == 'CONFIRMED']
    coverage_rows = coverage(places)
    report = {'run_id': manifest['run_id'], 'month': manifest.get('month', snapshot.name),
              'date': datetime.now(timezone.utc).isoformat(), 'gosom_version': manifest.get('gosom_version'),
              'scope': manifest.get('scope'), 'proxy_enabled': manifest.get('proxy_enabled', False),
              'elapsed': sum(b.get('elapsed_seconds', b.get('metrics', {}).get('elapsed_seconds', 0)) or 0 for b in batches),
              'jobs': sum(len(b.get('jobs', [])) for b in batches), 'batches': len(batches),
              'failures': sum(b.get('status') not in {'completed', 'complete'} for b in batches),
              'raw_records': len(raw), 'unique_places': len(places), 'excluded_records': len(excluded),
              'requested_places': sum(p.get('category_relationship') == REQUESTED for p in places),
              'additional_places': sum(p.get('category_relationship') == ADDITIONAL for p in places),
              'unclassified_places': sum(p.get('category_relationship') == UNCLASSIFIED for p in places),
              'requested_categories': categories.get('requested_categories', []),
              'duplicate_rate': (len(valid) - len(places)) / len(valid) if valid else 0,
              'places_core': sum(bool(p.get('inside_core_periferico')) for p in places), 'places_amg': len(places),
              'brands_detected': len(brands), 'brands_2_20': len(candidates), 'ambiguous_brands': len(ambiguous),
              'watchlist_brands_2': sum(b['commercial_segment'] == WATCHLIST for b in brands),
              'target_brands_3_20': sum(b['commercial_segment'] == TARGET for b in brands),
              'large_brands_21_plus': sum(b['commercial_segment'] == LARGE for b in brands),
              'geography_layers': geography.layer_status,
              'methodology_hash': manifest.get('methodology_hash'),
              'plan_id': manifest.get('plan_id'), 'plan_sha256': manifest.get('plan_sha256'),
              'territory_sha256': frozen.get('territory_sha256'),
              'source_policy_acknowledged': bool(manifest.get('source_policy_acknowledged')),
              'source_policy_acknowledged_at': manifest.get('source_policy_acknowledged_at'),
              'query_yield': manifest.get('query_yield', []), 'coverage_by_zone': coverage_rows,
              'marginal_gain_by_pass': manifest.get('marginal_gain_by_pass', []),
              'brand_expansion_required': expansion_required,
              'brand_expansion_pending': expansion_pending,
              'brand_expansion_completed': bool(manifest.get('brand_expansion_completed')),
              'brand_expansion_jobs': int(manifest.get('brand_expansion_jobs', 0) or 0),
              'gosom_platform_evidence': len(gosom_evidence),
              'warnings': warnings, 'incomplete': incomplete, 'status': manifest.get('status', 'unknown')}
    report.update({'platform_verification_requested': platform_requested, **gate})
    if expansion_pending:
        warnings.append('Brand expansion pending: confirmed 2–20 branch chains require directed enrichment.')
    if gate['report_status'] == 'DRAFT':
        warnings.append(f"Platform verification incomplete: {gate['pending_checks']} pending, {gate['errors']} errors.")
    processed = snapshot / 'processed'
    processed.mkdir(exist_ok=True)
    (processed / 'places.json').write_text(json.dumps(places, ensure_ascii=False, indent=2), encoding='utf-8')
    write_csv(processed / 'excluded.csv', excluded)
    for filename, rows in [('master', places), ('brands', brands), ('prospects', candidates),
                           ('ambiguous_brands', ambiguous), ('changes', changes), ('coverage_report', coverage_rows)]:
        write_csv(snapshot / (filename + '.csv'), rows)
    write_csv(snapshot / 'platform_check_queue.csv', queue)
    prospect_ids = {b['brand_id'] for b in candidates}
    if settings.get('mymaps_enabled', False):
        export_mymaps(snapshot / 'mymaps', [p for p in places if p['brand_id'] in prospect_ids])
    (snapshot / 'run_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    metadata = {
        'snapshot_id': report['month'], 'generated_at': report['date'],
        'gosom_version': report.get('gosom_version'), 'gosom_sha256': manifest.get('gosom_sha256'),
        'foodscan_version': '0.3.0',
        'territory_sha256': frozen.get('territory_sha256'),
        'territory_source': 'territory/processed/territory.geojson',
        'source_policy_version': settings.get('source_policy_version', 'unknown'),
        'source_policy_acknowledged': bool(manifest.get('source_policy_acknowledged')),
        'source_policy_acknowledged_at': manifest.get('source_policy_acknowledged_at'),
        'plan_id': manifest.get('plan_id'), 'plan_sha256': manifest.get('plan_sha256'),
        'methodology_hash': manifest.get('methodology_hash'),
        'source_run_ids': [manifest['run_id']], 'geography_layers': geography.layer_status,
    }
    (snapshot / 'metadata.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    report.update(metadata)
    report_result = generate_standard_reports(snapshot, places, brands, platform['brand_presence'],
                                              platform['platform_evidence'], changes, report,
                                              charts_enabled=settings.get('charts_enabled', False))
    report['report_status'] = report_result['report_status']
    report['report_pdf'] = report_result['pdf'].name
    (snapshot / 'run_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    save_run(identity_db, report, places, brands)
    return report
