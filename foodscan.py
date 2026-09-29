#!/usr/bin/env python3
"""FoodScan AMG: a small, durable operator around Gosom."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def month_value(value: str | None) -> str:
    value = value or date.today().strftime("%Y-%m")
    try:
        datetime.strptime(value, "%Y-%m")
    except ValueError as exc:
        raise ValueError("El mes debe tener formato YYYY-MM") from exc
    return value


def ensure_layout() -> None:
    from scripts.bootstrap import prepare_local_workspace
    prepare_local_workspace(ROOT)


def command_setup(_args) -> int:
    ensure_layout()
    from scripts.storage import init_db
    from scripts.gosom import has_foodscan_asset, install_browser, install_foodscan_gosom, install_gosom, smoke_test
    init_db(ROOT / "data" / "foodscan.db")
    metadata = install_foodscan_gosom(ROOT) if has_foodscan_asset(ROOT) else install_gosom(ROOT)
    browser = install_browser(ROOT)
    smoke = smoke_test(ROOT)
    print(f"Gosom {metadata.get('version', 'desconocido')} instalado")
    print(f"Browser: {'OK' if browser.get('ok') else 'ERROR'}")
    print(f"Smoke test: {'OK' if smoke.get('ok') else 'ERROR'}")
    return command_doctor(_args)


def command_doctor(_args) -> int:
    ensure_layout()
    from scripts.health import doctor
    result = doctor(ROOT)
    print("FoodScan Doctor\n")
    for item in result.get("checks", []):
        status = "OK" if item.get("ok") else ("OPTIONAL" if not item.get("required", True) else "ERROR")
        print(f"{item['name']:<27} {status} - {item.get('detail', '')}")
    print("\nREADY" if result.get("ready") else "\nNOT READY")
    return 0 if result.get("ready") else 2


def command_territory(args) -> int:
    from scripts.territory import import_territory, load_territory
    target = ROOT / "territory" / "processed" / "territory.geojson"
    if args.file:
        result = import_territory(Path(args.file).resolve(), target, scope=args.scope,
                                  density=args.density, approved=args.approve)
    else:
        result = load_territory(target, require_approved=not args.allow_unapproved)
    print(f"Territorio: {len(result['features'])} polígono(s) en {target}")
    if not args.approve and args.file:
        print("ONE-TIME HUMAN INPUT REQUIRED: revisa y vuelve a importar con --approve")
    return 0


def _gosom_identity() -> tuple[str | None, str | None]:
    from scripts.gosom import active_binary_path, sha256
    patched_version = ROOT / "tools" / "gosom-foodscan" / "VERSION.json"
    official_version = ROOT / "tools" / "gosom" / "VERSION.json"
    if patched_version.exists():
        details = read_json(patched_version)
        version = details.get("upstream_gosom_version", "unknown") + "+foodscan-patch"
    else:
        version = read_json(official_version).get("version") if official_version.exists() else None
    try:
        active = active_binary_path(ROOT)
        digest = sha256(active) if active.is_file() else None
    except (OSError, ValueError, KeyError):
        digest = None
    return version, digest


def build_plan(scope: str, destination: Path, *, month: str | None = None) -> dict:
    from scripts.grid import generate_grid, write_grid
    from scripts.queries import make_jobs, write_batches
    from scripts.planning import attach_plan_identity, code_identity, methodology_hash, plan_payload

    territory_path = ROOT / "territory" / "processed" / "territory.geojson"
    from scripts.territory import load_territory
    territory = load_territory(territory_path)
    coverage = read_json(ROOT / "config" / "coverage.json")
    categories = read_json(ROOT / "config" / "categories.json")
    settings = read_json(ROOT / "config" / "settings.json")
    points = generate_grid(territory, coverage, scope=scope)
    jobs = make_jobs(points, categories, pilot=False)

    destination.mkdir(parents=True, exist_ok=True)
    write_grid(points, destination / "grid.csv", destination / "grid_preview.geojson")
    batches = write_batches(jobs, destination / "batches", int(settings.get("batch_size", 25)))
    for batch in batches:
        batch["raw_file"] = str((destination / "raw" / f"{batch['batch_id']}.csv").resolve())
        batch["status"] = "planned"

    version, binary_sha = _gosom_identity()
    proxy_file = ROOT / "config" / "secrets" / "proxies.txt"
    proxy_enabled = proxy_file.exists() and any(
        line.strip() and not line.lstrip().startswith("#")
        for line in proxy_file.read_text(encoding="utf-8").splitlines()
    )
    proxy_file_sha256 = hashlib.sha256(proxy_file.read_bytes()).hexdigest() if proxy_enabled else None
    territory_sha = hashlib.sha256(territory_path.read_bytes()).hexdigest()
    frozen_territory = destination / "territory.geojson"
    shutil.copyfile(territory_path, frozen_territory)
    code_sha = code_identity(ROOT)
    frozen = {
        "coverage": coverage,
        "categories": categories,
        "settings": settings,
        "territory_sha256": territory_sha,
    }
    run_id = f"{month}-{scope}" if month else f"plan-{scope}"
    manifest = {
        "run_id": run_id,
        "month": month,
        "scope": scope,
        "kind": "monthly",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "planned",
        "platform_verification_requested": True,
        "gosom_version": version,
        "gosom_sha256": binary_sha,
        "code_sha256": code_sha,
        "proxy_enabled": proxy_enabled,
        "proxy_file_sha256": proxy_file_sha256,
        "grid_points": len(points),
        "jobs": len(jobs),
        "batches": batches,
        "frozen_config": frozen,
        "calibration": None,
    }
    payload = plan_payload(
        scope=scope, territory_sha256=territory_sha, coverage=coverage, categories=categories,
        settings=settings, grid_points=points, jobs=jobs, gosom_version=version,
        gosom_sha256=binary_sha, proxy_file_sha256=proxy_file_sha256, code_sha256=code_sha,
    )
    attach_plan_identity(manifest, payload)
    manifest["methodology_hash"] = methodology_hash(manifest)
    write_json(destination / "run_manifest.json", manifest)
    return manifest


def _manifest_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    if path.is_dir():
        path = path / "run_manifest.json"
    if not path.is_file():
        raise FileNotFoundError(f"No existe el plan: {path}")
    return path.resolve()


def print_plan(manifest: dict) -> None:
    from scripts.planning import human_duration
    categories = manifest.get("frozen_config", {}).get("categories", {})
    active = categories.get("active_queries") or []
    calibration = manifest.get("calibration") or {}
    eta = calibration.get("eta") or {}
    print(f"Plan: {manifest.get('plan_id', 'sin-id')}")
    print(f"Scope: {manifest['scope']}")
    print(f"Grid points: {manifest['grid_points']}")
    print(f"Jobs estimados: {manifest['jobs']}")
    print(f"Batches: {len(manifest['batches'])}")
    print(f"Consultas activas ({len(active)}): {', '.join(active) if active else 'perfil completo'}")
    print(f"Proxy: {'CONFIGURED' if manifest.get('proxy_enabled') else 'NOT CONFIGURED'}")
    print(f"Gosom: {manifest.get('gosom_version') or 'NO INSTALADO'}")
    if eta.get("available"):
        print(f"ETA estimada base: {human_duration(eta.get('eta_low_seconds'))}–{human_duration(eta.get('eta_high_seconds'))}")
        max_eta = calibration.get("eta_with_expansion_budget") or {}
        if max_eta.get("available"):
            print(f"ETA con presupuesto máximo de expansión: {human_duration(max_eta.get('eta_low_seconds'))}–{human_duration(max_eta.get('eta_high_seconds'))}")
    else:
        print("ETA estimada: pendiente de piloto")
    settings = manifest.get("frozen_config", {}).get("settings", {})
    print(f"Presupuesto expansión de marcas: <= {int(settings.get('brand_expansion_max_jobs', 250))} jobs")
    approval = manifest.get("approval") or {}
    print(f"Aprobación: {'APROBADO' if approval.get('approved') else 'PENDIENTE'}")


def command_plan(args) -> int:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = ROOT / "generated" / "plans" / f"{stamp}-{args.scope}"
    manifest = build_plan(args.scope, destination, month=month_value(args.month))
    print_plan(manifest)
    print(f"Plan guardado: {destination / 'run_manifest.json'}")
    print("Siguiente paso: ejecutar el piloto de calibración sobre este plan.")
    return 0


def _pilot_from_plan(plan_path: Path, destination: Path) -> dict:
    from scripts.queries import write_batches
    from scripts.planning import stratified_pilot_jobs

    source = read_json(plan_path)
    settings = source.get("frozen_config", {}).get("settings", {})
    jobs = [dict(job) for batch in source.get("batches", []) for job in batch.get("jobs", [])]
    selected = stratified_pilot_jobs(
        jobs,
        max_jobs=int(settings.get("pilot_max_jobs", 18)),
        query_limit=int(settings.get("pilot_query_limit", 6)),
    )
    batches = write_batches(selected, destination / "batches", int(settings.get("batch_size", 25)))
    for batch in batches:
        batch["raw_file"] = str((destination / "raw" / f"{batch['batch_id']}.csv").resolve())
        batch["status"] = "planned"
    run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-pilot-{source['scope']}"
    pilot = {
        "run_id": run_id,
        "month": source.get("month"),
        "scope": source["scope"],
        "kind": "pilot",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "planned",
        "source_plan_id": source.get("plan_id"),
        "source_plan_sha256": source.get("plan_sha256"),
        "platform_verification_requested": False,
        "gosom_version": source.get("gosom_version"),
        "gosom_sha256": source.get("gosom_sha256"),
        "code_sha256": source.get("code_sha256"),
        "proxy_enabled": source.get("proxy_enabled", False),
        "proxy_file_sha256": source.get("proxy_file_sha256"),
        "grid_points": len({job.get("point_id") for job in selected}),
        "jobs": len(selected),
        "batches": batches,
        "frozen_config": source.get("frozen_config", {}),
    }
    write_json(destination / "run_manifest.json", pilot)
    return pilot


def create_query_yield(manifest: dict, destination: Path) -> list[dict]:
    from scripts.dedupe import identity
    from scripts.exports import write_csv
    from scripts.normalize import normalize_record, read_raw

    job_to_query = {str(job["job_id"]): job["query"]
                    for batch in manifest.get("batches", []) for job in batch.get("jobs", [])}
    records: dict[str, list[dict]] = {query: [] for query in dict.fromkeys(job_to_query.values())}
    failed: dict[str, int] = {query: 0 for query in records}
    for batch in manifest.get("batches", []):
        for job_id in batch.get("pending_job_ids", []):
            query = job_to_query.get(str(job_id))
            if query:
                failed[query] += 1
        raw = Path(batch.get("raw_file", ""))
        if raw.is_file():
            for row in read_raw(raw):
                query = job_to_query.get(str(row.get("input_id", row.get("input", ""))))
                if query:
                    records[query].append(normalize_record(row))

    sets = {query: {identity(row) for row in rows} for query, rows in records.items()}
    all_places = set().union(*sets.values()) if sets else set()
    result = []
    for query, rows in records.items():
        others = set().union(*(values for name, values in sets.items() if name != query)) if len(sets) > 1 else set()
        exclusive = sets[query] - others
        result.append({
            "query": query,
            "raw_results": len(rows),
            "unique_places": len(sets[query]),
            "exclusive_places": len(exclusive),
            "exclusive_contribution_pct": round(100 * len(exclusive) / max(1, len(all_places)), 3),
            "overlap_pct": round(100 * (len(sets[query]) - len(exclusive)) / max(1, len(sets[query])), 3),
            "jobs_failed": failed[query],
        })
    write_csv(destination / "query_yield.csv", result)
    write_csv(ROOT / "generated" / "query_yield.csv", result)
    return result


def command_pilot(args) -> int:
    from scripts.runner import execute_manifest
    from scripts.planning import estimate_run, summarize_pilot

    plan_path = _manifest_path(args.plan)
    source = read_json(plan_path)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = ROOT / "generated" / "pilots" / f"{stamp}-{source['scope']}"
    pilot = _pilot_from_plan(plan_path, destination)
    print_plan({**source, "jobs": pilot["jobs"], "grid_points": pilot["grid_points"],
                "batches": pilot["batches"], "approval": {"approved": False}})
    if args.plan_only:
        return 0
    result = execute_manifest(ROOT, destination / "run_manifest.json")
    result["query_yield"] = create_query_yield(result, destination)
    calibration = summarize_pilot(result)
    settings = source.get("frozen_config", {}).get("settings", {})
    safe_concurrency = int(settings.get("concurrency", 1))
    minimum_completed = min(int(pilot.get("jobs", 0)), 12)
    calibration["acceptable"] = (
        calibration["jobs_completed"] >= minimum_completed
        and calibration["failure_rate"] <= 0.05
        and result.get("stop_reason") != "google_block"
    )
    if (calibration["acceptable"] and calibration["failure_rate"] == 0
            and calibration["jobs_completed"] == calibration["jobs_total"]
            and calibration["jobs_completed"] >= minimum_completed):
        recommended_concurrency = min(
            int(settings.get("balanced_concurrency", 2)),
            max(1, safe_concurrency + 1),
        )
    else:
        recommended_concurrency = safe_concurrency
    calibration["recommended_concurrency"] = recommended_concurrency
    calibration["eta"] = estimate_run(
        jobs=int(source.get("jobs", 0)),
        seconds_per_job=calibration.get("seconds_per_job"),
        concurrency=recommended_concurrency,
        uncertainty_pct=float(settings.get("eta_uncertainty_pct", 20)),
    )
    calibration["eta_with_expansion_budget"] = estimate_run(
        jobs=int(source.get("jobs", 0)) + int(settings.get("brand_expansion_max_jobs", 250)),
        seconds_per_job=calibration.get("seconds_per_job"),
        concurrency=recommended_concurrency,
        uncertainty_pct=float(settings.get("eta_uncertainty_pct", 20)),
    )
    result["calibration"] = calibration
    write_json(destination / "run_manifest.json", result)

    source["calibration"] = calibration
    write_json(plan_path, source)
    print(f"Piloto: {calibration['jobs_completed']}/{calibration['jobs_total']} jobs, "
          f"{calibration.get('seconds_per_job') or 'n/a'} s/job")
    print_plan(source)
    print(f"Plan actualizado: {plan_path}")
    print("La corrida completa sigue bloqueada hasta aprobación explícita.")
    return 0 if result["status"] == "completed" else 3


def command_approve(args) -> int:
    from scripts.planning import approve_manifest
    path = _manifest_path(args.plan)
    manifest = read_json(path)
    if not args.ack_source_policy:
        raise RuntimeError("Debes confirmar la política de fuente/licenciamiento con --ack-source-policy")
    calibration = manifest.get("calibration") or {}
    if not calibration.get("eta", {}).get("available"):
        raise RuntimeError("No se aprueba una corrida grande sin piloto y ETA disponibles")
    if not calibration.get("acceptable"):
        raise RuntimeError("El piloto no alcanzó el gate mínimo de salud/cobertura; no se aprueba la corrida")
    manifest["source_policy_acknowledged"] = True
    manifest["source_policy_acknowledged_at"] = datetime.now(timezone.utc).isoformat()
    approve_manifest(manifest)
    write_json(path, manifest)
    print_plan(manifest)
    print("Plan aprobado. La corrida completa puede ejecutarse exactamente con este plan.")
    return 0


def _materialize_plan(plan_path: Path, destination: Path) -> Path:
    plan = read_json(plan_path)
    destination.mkdir(parents=True, exist_ok=True)
    batches_dir = destination / "batches"
    batches_dir.mkdir(parents=True, exist_ok=True)
    materialized = dict(plan)
    materialized["run_id"] = f"{plan.get('month')}-{plan['scope']}-{plan.get('plan_id', 'plan')}"
    materialized["status"] = "planned"
    materialized["batches"] = []
    source_territory = plan_path.parent / "territory.geojson"
    if not source_territory.is_file():
        raise RuntimeError("El plan no conserva su territorio congelado")
    territory_bytes = source_territory.read_bytes()
    if hashlib.sha256(territory_bytes).hexdigest() != plan.get("frozen_config", {}).get("territory_sha256"):
        raise RuntimeError("El territorio congelado del plan fue modificado")
    (destination / "territory.geojson").write_bytes(territory_bytes)
    for source_batch in plan.get("batches", []):
        batch = dict(source_batch)
        target_input = batches_dir / Path(source_batch["input"]).name
        expected_input = "".join(
            f"{job['url']} #!# {job['job_id']}\n" for job in batch.get("jobs", [])
        )
        target_input.write_text(expected_input, encoding="utf-8")
        batch["input"] = str(target_input.resolve())
        batch["raw_file"] = str((destination / "raw" / f"{batch['batch_id']}.csv").resolve())
        batch["status"] = "planned"
        materialized["batches"].append(batch)
    path = destination / "run_manifest.json"
    write_json(path, materialized)
    return path


def finish_snapshot(path: Path) -> dict:
    from scripts.pipeline import process_snapshot
    from scripts.territory import load_territory
    manifest = read_json(path / "run_manifest.json")
    territory_path = path / "territory.geojson"
    if not territory_path.is_file():
        raise RuntimeError("El snapshot no conserva el territorio congelado del plan")
    expected = manifest.get("frozen_config", {}).get("territory_sha256")
    if expected and hashlib.sha256(territory_path.read_bytes()).hexdigest() != expected:
        raise RuntimeError("El territorio del snapshot no coincide con el plan aprobado")
    territory = load_territory(territory_path)
    return process_snapshot(ROOT, path, territory, manifest)


def command_monthly(args) -> int:
    from scripts.runner import execute_manifest
    from scripts.planning import verify_approval

    plan_path = _manifest_path(args.plan)
    plan = read_json(plan_path)
    verify_approval(plan)
    month = month_value(plan.get("month") or args.month)
    destination = ROOT / "snapshots" / month
    manifest_path = destination / "run_manifest.json"
    if manifest_path.exists():
        existing = read_json(manifest_path)
        if existing.get("plan_sha256") != plan.get("plan_sha256"):
            raise RuntimeError("El snapshot existente pertenece a otro plan; no se mezcla")
        if existing.get("status") == "completed":
            raise ValueError(f"El snapshot {month} ya está completo; no se sobrescribe")
    else:
        manifest_path = _materialize_plan(plan_path, destination)
    manifest = read_json(manifest_path)
    print_plan(manifest)
    if args.plan_only:
        return 0

    from scripts.health import doctor
    health = doctor(ROOT)
    if not health.get("ready"):
        failed = ", ".join(item["name"] for item in health["checks"]
                           if item.get("required", True) and not item.get("ok"))
        raise RuntimeError(f"La corrida mensual no inicia hasta resolver doctor: {failed}")

    result = execute_manifest(ROOT, manifest_path)
    if result["status"] == "completed":
        report = finish_snapshot(destination)
        if report.get("brand_expansion_pending"):
            print(f"Adquisición base completa; expansión dirigida de marcas pendiente: {destination}")
            print(f"Ejecuta: foodscan expand-brands --month {month}")
            return 3
        if report.get("report_status") == "DRAFT":
            print(f"Adquisición completa; verificación de plataformas pendiente: {destination}")
            print(f"Ejecuta: foodscan verify-platforms --month {month}")
            return 3
        print(f"Snapshot completo: {destination}")
        return 0
    print("Corrida incompleta. Usa: foodscan resume --run <ruta-del-snapshot>")
    return 3


def command_resume(args) -> int:
    from scripts.runner import execute_manifest, latest_manifest
    path = _manifest_path(args.run) if args.run else latest_manifest(ROOT, args.month)
    result = execute_manifest(ROOT, path)
    if result["status"] == "completed" and path.parent.parent.name == "snapshots":
        report = finish_snapshot(path.parent)
        if report.get("brand_expansion_pending"):
            print(f"Adquisición base completa; expansión dirigida de marcas pendiente: {path.parent}")
            return 3
        if report.get("report_status") == "DRAFT":
            print(f"Adquisición completa; verificación de plataformas pendiente: {path.parent}")
            return 3
    print(f"{result['run_id']}: {result['status']}")
    return 0 if result["status"] == "completed" else 3


def command_status(args) -> int:
    from scripts.runner import batch_progress, latest_manifest
    path = _manifest_path(args.run) if args.run else latest_manifest(ROOT, args.month)
    manifest = read_json(path)
    done = total = 0
    elapsed = 0.0
    for batch in manifest["batches"]:
        batch_done, batch_total, _ = batch_progress(batch)
        done += batch_done
        total += batch_total
        elapsed += float(batch.get("elapsed_seconds", 0) or 0)
    rate = done / elapsed if elapsed > 0 else 0
    remaining = total - done
    eta = remaining / rate if rate > 0 else None
    from scripts.planning import human_duration
    print(f"{manifest['run_id']}: {manifest['status']} — {done}/{total} jobs"
          + (f" — ETA {human_duration(eta)}" if eta is not None else ""))
    return 0


def command_export(args) -> int:
    path = ROOT / "snapshots" / month_value(args.month)
    report = finish_snapshot(path)
    print(f"Exportados {report.get('unique_places', 0)} establecimientos en {path}")
    return 0


def command_compare(args) -> int:
    from scripts.exports import compare_snapshots
    current = ROOT / "snapshots" / month_value(args.month)
    months = sorted(p for p in (ROOT / "snapshots").glob("????-??") if p < current)
    if not months:
        raise ValueError("No existe un snapshot anterior comparable")
    previous_report = read_json(months[-1] / "run_report.json")
    current_report = read_json(current / "run_report.json")
    if previous_report.get("scope") != current_report.get("scope"):
        raise ValueError("Los snapshots tienen alcances distintos y no son comparables")
    if previous_report.get("incomplete") or current_report.get("incomplete"):
        raise ValueError("No se comparan snapshots incompletos como si fueran censos completos")
    if previous_report.get("methodology_hash") != current_report.get("methodology_hash"):
        raise ValueError("Los snapshots tienen distinta metodología; no se presentan como tendencia directa")
    compare_snapshots(months[-1], current)
    print(f"Comparación creada: {current / 'changes.csv'}")
    return 0


def command_proxy(args) -> int:
    import getpass
    from scripts.health import parse_proxies
    path = ROOT / "config" / "secrets" / "proxies.txt"
    ensure_layout()
    if args.configure:
        value = getpass.getpass("Proxy URL (entrada oculta): ").strip()
        parse_proxies(value)
        path.write_text(value + "\n", encoding="utf-8")
        print("Proxy guardado localmente; las credenciales no se muestran.")
        return 0
    configured = any(x.strip() and not x.lstrip().startswith("#") for x in path.read_text(encoding="utf-8").splitlines())
    print(f"Proxy: {'CONFIGURED' if configured else 'OPTIONAL / NOT CONFIGURED'}")
    return 0


def command_update(_args) -> int:
    from scripts.gosom import has_foodscan_asset, install_foodscan_gosom, install_gosom
    metadata = (install_foodscan_gosom(ROOT, update=True) if has_foodscan_asset(ROOT)
                else install_gosom(ROOT, update=True))
    # Any previous smoke is tied to the old binary and must not certify the new one.
    (ROOT / ".runtime" / "smoke-latest.json").unlink(missing_ok=True)
    print(f"Gosom actualizado y validado: {metadata['version']}. Ejecuta setup/doctor para un smoke nuevo.")
    return 0


def command_expand_brands(args) -> int:
    import csv
    from scripts.expansion import make_expansion_jobs
    from scripts.queries import write_batches
    from scripts.runner import execute_manifest

    snapshot = ROOT / "snapshots" / month_value(args.month)
    manifest_path = snapshot / "run_manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"No existe snapshot para {args.month}")
    manifest = read_json(manifest_path)
    if manifest.get("status") != "completed":
        raise RuntimeError("La expansión de marcas requiere adquisición base completa")
    if manifest.get("brand_expansion_completed"):
        print("Expansión de marcas ya completada para este snapshot.")
        return 0

    brands_path = snapshot / "brands.csv"
    if not brands_path.is_file():
        finish_snapshot(snapshot)
    with brands_path.open(encoding="utf-8-sig", newline="") as stream:
        brands = list(csv.DictReader(stream))

    base_jobs = [
        job for batch in manifest.get("batches", [])
        for job in batch.get("jobs", [])
        if job.get("query_type") != "brand_expansion"
    ]
    jobs = make_expansion_jobs(brands, base_jobs)
    settings = manifest.get("frozen_config", {}).get("settings", {})
    limit = int(settings.get("brand_expansion_max_jobs", 250))
    if len(jobs) > limit:
        raise RuntimeError(
            f"La expansión requiere {len(jobs)} jobs y excede el presupuesto aprobado de {limit}; "
            "genera un plan nuevo con un presupuesto explícito mayor"
        )
    if not jobs:
        manifest["brand_expansion_completed"] = True
        manifest["brand_expansion_jobs"] = 0
        write_json(manifest_path, manifest)
        finish_snapshot(snapshot)
        print("No hay marcas confirmadas 2–20 que requieran expansión dirigida.")
        return 0

    folder = snapshot / "brand_expansion"
    expansion_path = folder / "run_manifest.json"
    if expansion_path.exists():
        expansion = read_json(expansion_path)
    else:
        batches = write_batches(jobs, folder / "batches", int(settings.get("batch_size", 25)))
        for batch in batches:
            batch["raw_file"] = str((folder / "raw" / f"{batch['batch_id']}.csv").resolve())
            batch["status"] = "planned"
        expansion = {
            "run_id": f"{manifest['run_id']}-brand-expansion",
            "month": manifest.get("month"),
            "scope": manifest.get("scope"),
            "kind": "brand_expansion",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "planned",
            "gosom_version": manifest.get("gosom_version"),
            "gosom_sha256": manifest.get("gosom_sha256"),
            "code_sha256": manifest.get("code_sha256"),
            "proxy_enabled": manifest.get("proxy_enabled", False),
            "proxy_file_sha256": manifest.get("proxy_file_sha256"),
            "approved_runtime": manifest.get("approved_runtime", {}),
            "frozen_config": manifest.get("frozen_config", {}),
            "batches": batches,
            "jobs": len(jobs),
        }
        write_json(expansion_path, expansion)

    result = execute_manifest(ROOT, expansion_path)
    if result["status"] != "completed":
        print("Expansión incompleta; usa foodscan resume --run <brand_expansion/run_manifest.json>.")
        return 3

    existing = {batch.get("batch_id") for batch in manifest.get("batches", [])}
    for batch in result.get("batches", []):
        copied = dict(batch)
        copied["batch_id"] = f"expansion_{batch['batch_id']}"
        if copied["batch_id"] not in existing:
            manifest["batches"].append(copied)
    manifest["brand_expansion_completed"] = True
    manifest["brand_expansion_jobs"] = len(jobs)
    write_json(manifest_path, manifest)
    report = finish_snapshot(snapshot)
    print(f"Expansión dirigida completa: {len(jobs)} jobs. Marcas detectadas: {report.get('brands_detected', 0)}")
    return 0


def command_verify_platforms(args) -> int:
    from scripts.platform_verification import resolve_snapshot, verify_platforms
    snapshot = resolve_snapshot(ROOT, month=args.month, snapshot=args.snapshot)
    report = verify_platforms(ROOT, snapshot, evidence_path=args.evidence)
    print(report["platform_verification_progress"])
    print(f"Report status: {report['report_status']}")
    if report["report_status"] == "DRAFT":
        print(f"Pendientes: {report['pending_checks']}; errores: {report['errors']}")
        return 3
    print(f"PDF final: {snapshot / report['report_pdf']}")
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="foodscan", description="Censo mensual FoodScan AMG")
    commands = result.add_subparsers(dest="command", required=True)
    for name, function in (("setup", command_setup), ("doctor", command_doctor),
                           ("status", command_status), ("update-gosom", command_update)):
        item = commands.add_parser(name)
        item.set_defaults(function=function)
        if name == "status":
            item.add_argument("--month")
            item.add_argument("--run")

    item = commands.add_parser("proxy")
    item.set_defaults(function=command_proxy)
    item.add_argument("--configure", action="store_true")

    item = commands.add_parser("territory")
    item.set_defaults(function=command_territory)
    item.add_argument("--file")
    item.add_argument("--scope", choices=["CORE_GDL", "AMG_FULL"])
    item.add_argument("--density", choices=["high", "medium", "periphery", "rural"], default="high")
    item.add_argument("--approve", action="store_true")
    item.add_argument("--allow-unapproved", action="store_true")

    item = commands.add_parser("plan")
    item.set_defaults(function=command_plan)
    item.add_argument("--scope", choices=["CORE_GDL", "AMG_FULL"], default="AMG_FULL")
    item.add_argument("--month")

    item = commands.add_parser("pilot")
    item.set_defaults(function=command_pilot)
    item.add_argument("--plan", required=True)
    item.add_argument("--plan-only", action="store_true")

    item = commands.add_parser("approve")
    item.set_defaults(function=command_approve)
    item.add_argument("--plan", required=True)
    item.add_argument("--ack-source-policy", action="store_true",
                      help="confirma que la organización revisó y autoriza la fuente/uso")

    item = commands.add_parser("monthly")
    item.set_defaults(function=command_monthly)
    item.add_argument("--plan", required=True)
    item.add_argument("--month")
    item.add_argument("--plan-only", action="store_true")

    item = commands.add_parser("resume")
    item.set_defaults(function=command_resume)
    item.add_argument("--month")
    item.add_argument("--run")

    item = commands.add_parser("export")
    item.set_defaults(function=command_export)
    item.add_argument("--month")

    item = commands.add_parser("compare")
    item.set_defaults(function=command_compare)
    item.add_argument("--month")

    item = commands.add_parser("expand-brands")
    item.set_defaults(function=command_expand_brands)
    item.add_argument("--month", required=True)

    item = commands.add_parser("verify-platforms")
    item.set_defaults(function=command_verify_platforms)
    item.add_argument("--month")
    item.add_argument("--snapshot")
    item.add_argument("--evidence")
    return result


def main(argv=None) -> int:
    try:
        args = parser().parse_args(argv)
        return args.function(args)
    except (ValueError, FileNotFoundError, RuntimeError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
