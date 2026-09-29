"""Run planning, approval, pilot calibration and reproducibility helpers."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def plan_payload(*, scope: str, territory_sha256: str, coverage: Mapping,
                 categories: Mapping, settings: Mapping, grid_points: list[Mapping],
                 jobs: list[Mapping], gosom_version: str | None,
                 gosom_sha256: str | None, proxy_file_sha256: str | None,
                 code_commit: str | None) -> dict:
    """Return the immutable execution payload whose hash identifies a plan."""
    return {
        "scope": scope,
        "territory_sha256": territory_sha256,
        "coverage": coverage,
        "categories": categories,
        "settings": settings,
        "grid_points": grid_points,
        "jobs": jobs,
        "gosom_version": gosom_version,
        "gosom_sha256": gosom_sha256,
        "proxy_file_sha256": proxy_file_sha256,
        "code_commit": code_commit,
    }


def attach_plan_identity(manifest: dict, payload: Mapping) -> dict:
    digest = sha256_json(payload)
    manifest["plan_sha256"] = digest
    manifest["plan_id"] = f"plan-{digest[:12]}"
    manifest["approval"] = {
        "required": manifest.get("kind") == "monthly",
        "approved": False,
        "approved_at": None,
        "approved_plan_sha256": None,
    }
    return manifest


def approve_manifest(manifest: dict) -> dict:
    approval = dict(manifest.get("approval") or {})
    approval.update({
        "required": True,
        "approved": True,
        "approved_at": utc_now(),
        "approved_plan_sha256": manifest.get("plan_sha256"),
    })
    manifest["approval"] = approval
    calibration = manifest.get("calibration") or {}
    recommended = int(calibration.get("recommended_concurrency", 1) or 1)
    frozen = manifest.get("frozen_config") or {}
    settings = frozen.get("settings") or {}
    if recommended > 1:
        manifest["approved_runtime"] = {
            "concurrency": min(recommended, int(settings.get("balanced_concurrency", 2))),
            "browser_pool": min(recommended, int(settings.get("balanced_browser_pool", 2))),
            "pages_per_browser": 1,
        }
    else:
        manifest["approved_runtime"] = {
            "concurrency": 1, "browser_pool": 1, "pages_per_browser": 1,
        }
    return manifest


def verify_approval(manifest: Mapping) -> None:
    approval = manifest.get("approval") or {}
    if not approval.get("required"):
        return
    if not approval.get("approved"):
        raise RuntimeError("La corrida requiere aprobación explícita del plan antes de iniciar")
    if not manifest.get("source_policy_acknowledged"):
        raise RuntimeError("La corrida aprobada carece de confirmación de política de fuente/licenciamiento")
    if approval.get("approved_plan_sha256") != manifest.get("plan_sha256"):
        raise RuntimeError("La aprobación no corresponde al plan actual; genera y aprueba un plan nuevo")


def stratified_pilot_jobs(jobs: Iterable[Mapping], *, max_jobs: int = 18,
                          query_limit: int = 6) -> list[dict]:
    """Select a deterministic small calibration set across zones/depths/queries."""
    rows = [dict(job) for job in jobs]
    if max_jobs < 1:
        raise ValueError("pilot max_jobs must be positive")
    if query_limit < 1:
        raise ValueError("pilot query_limit must be positive")
    if not rows:
        return []

    # Keep only a bounded number of representative query terms while preserving order.
    queries = list(dict.fromkeys(str(row.get("query", "")) for row in rows if row.get("query")))[:query_limit]
    filtered = [row for row in rows if row.get("query") in queries] or rows

    groups: dict[tuple[str, int], list[dict]] = {}
    for row in filtered:
        key = (str(row.get("zone", "unknown")), int(row.get("depth", 0) or 0))
        groups.setdefault(key, []).append(row)

    ordered = [groups[key] for key in sorted(groups)]
    selected: list[dict] = []
    # Round-robin one job at a time so a large zone cannot dominate the pilot.
    cursor = 0
    while len(selected) < max_jobs and ordered:
        next_round = []
        for group in ordered:
            if cursor < len(group):
                candidate = group[cursor]
                if candidate not in selected:
                    selected.append(candidate)
                    if len(selected) >= max_jobs:
                        break
            if cursor + 1 < len(group):
                next_round.append(group)
        cursor += 1
        ordered = next_round
    return selected[:max_jobs]


def summarize_pilot(manifest: Mapping) -> dict:
    batches = manifest.get("batches", [])
    elapsed = sum(float(b.get("elapsed_seconds", 0) or 0) for b in batches)
    completed = sum(int(b.get("jobs_completed", 0) or 0) for b in batches)
    total = sum(int(b.get("jobs_total", len(b.get("jobs", []))) or 0) for b in batches)
    failures = max(0, total - completed)
    seconds_per_job = elapsed / completed if completed else None
    return {
        "elapsed_seconds": round(elapsed, 2),
        "jobs_total": total,
        "jobs_completed": completed,
        "jobs_failed": failures,
        "seconds_per_job": round(seconds_per_job, 2) if seconds_per_job else None,
        "failure_rate": round(failures / total, 4) if total else 0.0,
    }


def estimate_run(*, jobs: int, seconds_per_job: float | None, concurrency: int = 1,
                 uncertainty_pct: float = 20.0, startup_seconds: float = 0.0) -> dict:
    if jobs < 0:
        raise ValueError("jobs cannot be negative")
    concurrency = max(1, int(concurrency))
    if not seconds_per_job or seconds_per_job <= 0:
        return {"available": False, "reason": "pilot_without_completed_jobs"}
    central = startup_seconds + jobs * seconds_per_job / concurrency
    spread = max(0.0, float(uncertainty_pct)) / 100.0
    low = max(0.0, central * (1 - spread))
    high = central * (1 + spread)
    return {
        "available": True,
        "jobs": jobs,
        "effective_concurrency": concurrency,
        "seconds_per_job": round(seconds_per_job, 2),
        "eta_seconds": round(central),
        "eta_low_seconds": round(low),
        "eta_high_seconds": round(high),
    }


def methodology_payload(manifest: Mapping) -> dict:
    frozen = manifest.get("frozen_config") or {}
    return {
        "scope": manifest.get("scope"),
        "territory_sha256": frozen.get("territory_sha256"),
        "categories": frozen.get("categories"),
        "coverage": frozen.get("coverage"),
        "settings_methodology": {
            key: (frozen.get("settings") or {}).get(key)
            for key in ("lang", "batch_size", "concurrency", "browser_pool", "pages_per_browser",
                        "brand_expansion_max_jobs")
        },
        "gosom_version": manifest.get("gosom_version"),
        "gosom_sha256": manifest.get("gosom_sha256"),
        "proxy_file_sha256": manifest.get("proxy_file_sha256"),
        "normalization_version": "2",
        "dedupe_version": "2",
        "brand_resolution_version": "2",
        "brand_expansion_policy_version": "1",
    }


def methodology_hash(manifest: Mapping) -> str:
    return sha256_json(methodology_payload(manifest))


def human_duration(seconds: int | float | None) -> str:
    if seconds is None:
        return "desconocido"
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes = math.ceil(remainder / 60) if remainder else 0
    if hours:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m"
