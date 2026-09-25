"""Operational bridge between Codex browser research and FoodScan reports.

This module deliberately performs no web requests.  It prepares the complete
TARGET queue, imports the evidence gathered by the agent, and enforces the
same deterministic quality gate used by the main pipeline.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from .exports import write_csv
from .platforms import (
    PLATFORMS,
    create_platform_check_queue,
    integrate_platform_evidence,
    platform_quality_gate,
    normalize_platform,
)
from .reporting import generate_standard_reports

_PREFIX = {"UBER_EATS": "uber", "RAPPI": "rappi", "DIDI_FOOD": "didi"}


def _read_json(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_csv(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def resolve_snapshot(root: Path, *, month: str | None = None,
                     snapshot: str | Path | None = None) -> Path:
    """Resolve an explicit path, a monthly snapshot, or the latest report."""
    root = Path(root)
    if snapshot:
        selected = Path(snapshot).expanduser()
        if not selected.is_absolute():
            selected = root / selected
    elif month:
        selected = root / "snapshots" / month
    else:
        candidates = [path.parent for path in (root / "snapshots").glob("*/run_report.json")]
        if not candidates:
            raise FileNotFoundError("No hay snapshots con run_report.json")
        selected = max(candidates, key=lambda path: (path.stat().st_mtime, path.name))
    selected = selected.resolve()
    if not (selected / "run_report.json").is_file():
        raise FileNotFoundError(f"Snapshot sin run_report.json: {selected}")
    if not (selected / "processed" / "places.json").is_file():
        raise FileNotFoundError(f"Snapshot sin processed/places.json: {selected}")
    return selected


def _brands(snapshot: Path, places: list[dict]) -> list[dict]:
    rows = _read_csv(snapshot / "brands.csv")
    if rows:
        return rows
    unique = {}
    for place in places:
        brand_id = str(place.get("brand_id", ""))
        if brand_id and brand_id not in unique:
            unique[brand_id] = dict(place)
    return list(unique.values())


def _queue_with_status(queue: list[dict], branches: list[dict]) -> list[dict]:
    indexed = {(str(row.get("brand_id", "")), str(row.get("branch_id", ""))): row
               for row in branches}
    result = []
    for check in queue:
        platform = str(check["platform"])
        branch = indexed.get((str(check.get("brand_id", "")),
                              str(check.get("branch_id", ""))), {})
        result.append({**check, "status": branch.get(f"{_PREFIX[platform]}_status", "PENDING")})
    return result


def _merge_evidence(canonical: list[dict], incoming: list[dict]) -> list[dict]:
    """Upsert current evidence by branch/platform so partial agent batches are resumable."""
    merged: dict[tuple[str, str, str], dict] = {}
    for row in [*canonical, *incoming]:
        key = (str(row.get("brand_id", "")), str(row.get("branch_id", "")),
               normalize_platform(row.get("platform")))
        merged[key] = dict(row)
    return list(merged.values())


def verify_platforms(root: Path, snapshot: Path, *,
                     evidence_path: str | Path | None = None) -> dict:
    """Import agent evidence, refresh queue/progress, gate, and reports."""
    root, snapshot = Path(root), Path(snapshot)
    places = list(_read_json(snapshot / "processed" / "places.json"))
    brands = _brands(snapshot, places)
    canonical_path = snapshot / "platform_evidence.csv"
    canonical = _read_csv(canonical_path)
    if evidence_path:
        incoming = _read_csv(Path(evidence_path))
        evidence = _merge_evidence(canonical, incoming)
    else:
        evidence = _merge_evidence([], canonical)

    # Validation is intentionally completed before replacing canonical evidence.
    platform = integrate_platform_evidence(brands, places, evidence)
    enriched_brands = platform["brand_presence"]
    enriched_places = platform["branch_presence"]
    queue = create_platform_check_queue(enriched_brands, enriched_places)
    gate = platform_quality_gate(queue, enriched_places, requested=True)
    queue_rows = _queue_with_status(queue, enriched_places)

    write_csv(snapshot / "platform_evidence.csv", platform["platform_evidence"])
    write_csv(snapshot / "platform_check_queue.csv", queue_rows)
    write_csv(snapshot / "platform_presence.csv", enriched_brands)
    write_csv(snapshot / "brands.csv", enriched_brands)
    (snapshot / "processed" / "places.json").write_text(
        json.dumps(enriched_places, ensure_ascii=False, indent=2), encoding="utf-8")

    report = dict(_read_json(snapshot / "run_report.json"))
    report.update({"platform_verification_requested": True, **gate})
    progress = f"Platform verification: {gate['completed_checks']}/{gate['expected_checks']} checks completed"
    report["platform_verification_progress"] = progress
    if gate["report_status"] == "DRAFT":
        detail = (f"Platform verification incomplete: {gate['pending_checks']} pending, "
                  f"{gate['errors']} errors.")
        warnings = [item for item in report.get("warnings", [])
                    if not str(item).startswith("Platform verification incomplete:")]
        report["warnings"] = [*warnings, detail]
    else:
        report["warnings"] = [item for item in report.get("warnings", [])
                              if not str(item).startswith("Platform verification incomplete:")]

    changes = _read_csv(snapshot / "changes.csv")
    settings_path = root / "config" / "settings.json"
    settings = _read_json(settings_path) if settings_path.is_file() else {}
    generated = generate_standard_reports(
        snapshot, enriched_places, enriched_brands, enriched_brands,
        platform["platform_evidence"], changes, report,
        charts_enabled=bool(settings.get("charts_enabled", False)),
    )
    if generated["report_status"] != gate["report_status"]:
        raise RuntimeError("El estado del reporte contradice el quality gate de plataformas")
    report["report_status"] = generated["report_status"]
    report["report_pdf"] = Path(generated["pdf"]).name
    (snapshot / "run_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
