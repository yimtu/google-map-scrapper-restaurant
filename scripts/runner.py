"""Durable Gosom batch execution with authoritative resume tracking."""
from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .gosom import active_binary_path, gosom_env


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def load_manifest(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data.get("batches"), list):
        raise ValueError("El manifiesto no contiene batches válidos")
    return data


def batch_progress(batch: dict[str, Any]) -> tuple[int, int, list[str]]:
    expected = [str(job["job_id"]) for job in batch.get("jobs", [])]
    sidecar = Path(str(batch["raw_file"]) + ".resume.json")
    completed: set[str] = set()
    if sidecar.exists():
        try:
            payload = json.loads(sidecar.read_text(encoding="utf-8"))
            completed = {str(item) for item in payload.get("completed_inputs", [])}
        except (OSError, json.JSONDecodeError):
            completed = set()
    pending = [job_id for job_id in expected if job_id not in completed]
    return len(expected) - len(pending), len(expected), pending


def _settings(root: Path) -> dict[str, Any]:
    path = root / "config" / "settings.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _redact(message: str) -> str:
    import re
    return re.sub(r"(?i)(https?|socks5h?)://[^\s/@:]+:[^\s/@]+@", r"\1://***:***@", message)


def execute_manifest(
    root: Path, manifest_path: Path, *, binary: Path | None = None,
    only_incomplete: bool = True,
) -> dict[str, Any]:
    root = root.resolve()
    manifest_path = manifest_path.resolve()
    manifest = load_manifest(manifest_path)
    job_ids = [str(job["job_id"]) for batch in manifest["batches"] for job in batch.get("jobs", [])]
    if len(job_ids) != len(set(job_ids)):
        raise ValueError("El plan contiene job_id duplicados; no es seguro reanudarlo")
    binary = (binary or active_binary_path(root)).resolve()
    if not binary.is_file():
        raise FileNotFoundError("Gosom no está instalado; ejecuta foodscan setup")
    settings = _settings(root)
    lock = manifest_path.with_suffix(manifest_path.suffix + ".lock")
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(descriptor)
    except FileExistsError as exc:
        raise RuntimeError("Esta corrida ya está siendo ejecutada") from exc
    manifest["status"] = "running"
    manifest.setdefault("started_at", utc_now())
    atomic_json(manifest_path, manifest)
    try:
        for batch in manifest["batches"]:
            done, total, pending = batch_progress(batch)
            if only_incomplete and not pending:
                batch["status"] = "completed"
                continue
            raw = Path(batch["raw_file"])
            raw.parent.mkdir(parents=True, exist_ok=True)
            batch["status"] = "running"
            batch["started_at"] = batch.get("started_at") or utc_now()
            batch["jobs_completed"] = done
            atomic_json(manifest_path, manifest)
            args = [str(binary), "-resume", "-input", str(Path(batch["input"])),
                    "-results", str(raw), "-lang", str(settings.get("lang", settings.get("language", "es"))),
                    "-depth", str(batch.get("depth", 5)), "-c", str(settings.get("concurrency", 1)),
                    "-browser-pool-size", str(settings.get("browser_pool", settings.get("browser_pool_size", 1))),
                    "-pages-per-browser", str(settings.get("pages_per_browser", 1)),
                    "-exit-on-inactivity", str(settings.get("exit_on_inactivity", "4m"))]
            proxies = root / "config" / "secrets" / "proxies.txt"
            if proxies.exists() and any(line.strip() and not line.lstrip().startswith("#") for line in proxies.read_text(encoding="utf-8").splitlines()):
                args.extend(["-proxies-file", str(proxies)])
            environment = gosom_env(root)
            started = time.monotonic()
            try:
                result = subprocess.run(
                    args, cwd=root, env=environment, capture_output=True, text=True,
                    encoding="utf-8", errors="replace",
                    timeout=int(settings.get("batch_timeout_seconds", 7200)),
                )
                output = result.stdout + "\n" + result.stderr
                return_code = result.returncode
            except subprocess.TimeoutExpired as exc:
                output = (exc.stdout or "") + "\n" + (exc.stderr or "") + "\nBatch timeout"
                return_code = -1
            done, total, pending = batch_progress(batch)
            batch.update({"finished_at": utc_now(), "elapsed_seconds": round(time.monotonic() - started, 2),
                          "jobs_total": total, "jobs_completed": done, "jobs_failed": len(pending),
                          "pending_job_ids": pending, "exit_code": return_code,
                          "status": "completed" if not pending else "incomplete"})
            log_path = root / "logs" / f"{manifest['run_id']}_{batch['batch_id']}.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(_redact(output), encoding="utf-8")
            atomic_json(manifest_path, manifest)
            if pending:
                break
        incomplete = [item for item in manifest["batches"] if item.get("status") != "completed"]
        manifest["status"] = "incomplete" if incomplete else "completed"
        manifest["finished_at"] = utc_now()
        atomic_json(manifest_path, manifest)
        return manifest
    finally:
        lock.unlink(missing_ok=True)


def latest_manifest(root: Path, month: str | None = None) -> Path:
    if month:
        path = root / "snapshots" / month / "run_manifest.json"
        if not path.exists():
            raise FileNotFoundError(f"No existe una corrida para {month}")
        return path
    candidates = sorted((root / "snapshots").glob("????-??/run_manifest.json"), reverse=True)
    if not candidates:
        raise FileNotFoundError("No hay corridas mensuales")
    return candidates[0]
