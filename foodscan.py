#!/usr/bin/env python3
"""FoodScan AMG: a small, durable operator around Gosom."""
from __future__ import annotations

import argparse
import hashlib
import json
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


def build_plan(scope: str, destination: Path, *, pilot: bool = False, month: str | None = None) -> dict:
    from scripts.grid import generate_grid, write_grid
    from scripts.queries import make_jobs, write_batches
    from scripts.territory import load_territory
    territory_path = ROOT / "territory" / "processed" / "territory.geojson"
    territory = load_territory(territory_path)
    coverage = read_json(ROOT / "config" / "coverage.json")
    categories = read_json(ROOT / "config" / "categories.json")
    settings = read_json(ROOT / "config" / "settings.json")
    points = generate_grid(territory, coverage, scope=scope)
    if pilot:
        grouped: dict[str, list] = {}
        for point in points:
            grouped.setdefault(point.get("density", point.get("zone", "other")), []).append(point)
        selected = []
        for values in grouped.values():
            selected.extend(values[: max(1, 15 // max(1, len(grouped)))])
        points = selected[:20] or points[:20]
    destination.mkdir(parents=True, exist_ok=True)
    write_grid(points, destination / "grid.csv", destination / "grid_preview.geojson")
    jobs = make_jobs(points, categories, pilot=pilot)
    batches = write_batches(jobs, destination / "batches", int(settings.get("batch_size", 50)))
    for batch in batches:
        batch["raw_file"] = str((destination / "raw" / f"{batch['batch_id']}.csv").resolve())
        batch["status"] = "planned"
    patched_version = ROOT / "tools" / "gosom-foodscan" / "VERSION.json"
    official_version = ROOT / "tools" / "gosom" / "VERSION.json"
    if patched_version.exists():
        details = read_json(patched_version)
        version = details.get("upstream_gosom_version", "unknown") + "+foodscan-patch"
    else:
        version = read_json(official_version).get("version") if official_version.exists() else None
    proxy_file = ROOT / "config" / "secrets" / "proxies.txt"
    proxy_enabled = proxy_file.exists() and any(
        line.strip() and not line.lstrip().startswith("#")
        for line in proxy_file.read_text(encoding="utf-8").splitlines()
    )
    frozen = {"coverage": coverage, "categories": categories, "settings": settings,
              "territory_sha256": hashlib.sha256(territory_path.read_bytes()).hexdigest()}
    run_id = f"{'pilot' if pilot else month}-{scope}"
    manifest = {"run_id": run_id, "month": month, "scope": scope, "kind": "pilot" if pilot else "monthly",
                "created_at": datetime.now(timezone.utc).isoformat(), "status": "planned",
                "platform_verification_requested": not pilot,
                "gosom_version": version, "proxy_enabled": proxy_enabled,
                "grid_points": len(points), "jobs": len(jobs),
                "batches": batches, "frozen_config": frozen}
    write_json(destination / "run_manifest.json", manifest)
    return manifest


def print_plan(manifest: dict) -> None:
    print(f"Scope: {manifest['scope']}")
    print(f"Grid points: {manifest['grid_points']}")
    print(f"Jobs estimados: {manifest['jobs']}")
    print(f"Batches: {len(manifest['batches'])}")
    print(f"Gosom: {manifest.get('gosom_version') or 'NO INSTALADO'}")


def command_plan(args) -> int:
    manifest = build_plan(args.scope, ROOT / "generated", pilot=False,
                          month=month_value(args.month))
    print_plan(manifest)
    return 0


def command_pilot(args) -> int:
    from scripts.runner import execute_manifest
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destination = ROOT / "generated" / "pilots" / stamp
    manifest = build_plan(args.scope, destination, pilot=True)
    print_plan(manifest)
    if args.plan_only:
        return 0
    result = execute_manifest(ROOT, destination / "run_manifest.json")
    yields = create_query_yield(result, destination)
    result["query_yield"] = yields
    write_json(destination / "run_manifest.json", result)
    return 0 if result["status"] == "completed" else 3


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
            if query: failed[query] += 1
        raw = Path(batch.get("raw_file", ""))
        if raw.is_file():
            for row in read_raw(raw):
                query = job_to_query.get(str(row.get("input_id", row.get("input", ""))))
                if query: records[query].append(normalize_record(row))
    seen: set[str] = set()
    result = []
    for query, rows in records.items():
        unique = {identity(row) for row in rows}
        new = unique - seen
        result.append({"query": query, "raw_results": len(rows), "unique_places": len(unique),
                       "new_unique_places": len(new),
                       "marginal_yield_pct": round(100 * len(new) / max(1, len(seen)), 3),
                       "jobs_failed": failed[query]})
        seen.update(unique)
    write_csv(destination / "query_yield.csv", result)
    write_csv(ROOT / "generated" / "query_yield.csv", result)
    return result


def finish_snapshot(path: Path) -> dict:
    from scripts.pipeline import process_snapshot
    from scripts.territory import load_territory
    manifest = read_json(path / "run_manifest.json")
    territory = load_territory(ROOT / "territory" / "processed" / "territory.geojson")
    return process_snapshot(ROOT, path, territory, manifest)


def command_monthly(args) -> int:
    from scripts.runner import execute_manifest
    month = month_value(args.month)
    destination = ROOT / "snapshots" / month
    manifest_path = destination / "run_manifest.json"
    if manifest_path.exists():
        existing = read_json(manifest_path)
        if existing.get("status") == "completed":
            raise ValueError(f"El snapshot {month} ya está completo; no se sobrescribe")
        manifest = existing
    else:
        manifest = build_plan(args.scope, destination, month=month)
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
        if report.get("report_status") == "DRAFT":
            print(f"Adquisición completa; verificación de plataformas pendiente: {destination}")
            print(f"Ejecuta: foodscan verify-platforms --month {month}")
            return 3
        print(f"Snapshot completo: {destination}")
        return 0
    print("Corrida incompleta. Usa: foodscan resume")
    return 3


def command_resume(args) -> int:
    from scripts.runner import execute_manifest, latest_manifest
    path = latest_manifest(ROOT, args.month)
    result = execute_manifest(ROOT, path)
    if result["status"] == "completed":
        report = finish_snapshot(path.parent)
        if report.get("report_status") == "DRAFT":
            print(f"Adquisición completa; verificación de plataformas pendiente: {path.parent}")
            print(f"Ejecuta: foodscan verify-platforms --month {report.get('month', path.parent.name)}")
            return 3
        print(f"Corrida completada: {path.parent}")
        return 0
    print("Aún quedan trabajos pendientes; revisa logs y ejecuta resume de nuevo.")
    return 3


def command_status(args) -> int:
    from scripts.runner import batch_progress, latest_manifest
    manifest = read_json(latest_manifest(ROOT, args.month))
    done = total = 0
    for batch in manifest["batches"]:
        batch_done, batch_total, _ = batch_progress(batch)
        done += batch_done; total += batch_total
    print(f"{manifest['run_id']}: {manifest['status']} — {done}/{total} jobs")
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
    changes = compare_snapshots(months[-1], current)
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
    print(f"Archivo local: {path}")
    return 0


def command_update(_args) -> int:
    from scripts.gosom import has_foodscan_asset, install_foodscan_gosom, install_gosom
    metadata = (install_foodscan_gosom(ROOT, update=True) if has_foodscan_asset(ROOT)
                else install_gosom(ROOT, update=True))
    print(f"Gosom actualizado y validado: {metadata['version']}")
    return 0


def command_verify_platforms(args) -> int:
    from scripts.platform_verification import resolve_snapshot, verify_platforms
    snapshot = resolve_snapshot(ROOT, month=args.month, snapshot=args.snapshot)
    report = verify_platforms(ROOT, snapshot, evidence_path=args.evidence)
    print(report["platform_verification_progress"])
    print(f"Report status: {report['report_status']}")
    print(f"Queue: {snapshot / 'platform_check_queue.csv'}")
    if report["report_status"] == "DRAFT":
        print(f"Pendientes: {report['pending_checks']}; errores: {report['errors']}")
        return 3
    print(f"PDF final: {snapshot / report['report_pdf']}")
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="foodscan", description="Censo mensual FoodScan AMG")
    commands = result.add_subparsers(dest="command", required=True)
    for name, function in (("setup", command_setup), ("doctor", command_doctor),
                           ("status", command_status),
                           ("update-gosom", command_update)):
        item = commands.add_parser(name); item.set_defaults(function=function)
        if name == "status": item.add_argument("--month")
    item = commands.add_parser("proxy"); item.set_defaults(function=command_proxy)
    item.add_argument("--configure", action="store_true", help="pedir y guardar una URL mediante entrada oculta")
    item = commands.add_parser("territory"); item.set_defaults(function=command_territory)
    item.add_argument("--file"); item.add_argument("--scope", choices=["CORE_GDL", "AMG_FULL"])
    item.add_argument("--density", choices=["high", "medium", "periphery", "rural"], default="high")
    item.add_argument("--approve", action="store_true"); item.add_argument("--allow-unapproved", action="store_true")
    for name, function in (("plan", command_plan), ("pilot", command_pilot), ("monthly", command_monthly)):
        item = commands.add_parser(name); item.set_defaults(function=function)
        item.add_argument("--scope", choices=["CORE_GDL", "AMG_FULL"], default="AMG_FULL")
        item.add_argument("--month")
        if name in ("pilot", "monthly"): item.add_argument("--plan-only", action="store_true")
    item = commands.add_parser("resume"); item.set_defaults(function=command_resume); item.add_argument("--month")
    item = commands.add_parser("export"); item.set_defaults(function=command_export); item.add_argument("--month")
    item = commands.add_parser("compare"); item.set_defaults(function=command_compare); item.add_argument("--month")
    item = commands.add_parser("verify-platforms")
    item.set_defaults(function=command_verify_platforms)
    item.add_argument("--month", help="snapshot mensual YYYY-MM")
    item.add_argument("--snapshot", help="ruta explícita del snapshot")
    item.add_argument("--evidence", help="CSV de evidencia producido por el agente")
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
