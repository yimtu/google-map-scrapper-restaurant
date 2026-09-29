"""Durable Gosom batch execution with frozen settings, bounded retries and safe resume."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .gosom import active_binary_path, gosom_env, sha256


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


def _settings(manifest: dict[str, Any]) -> dict[str, Any]:
    frozen = manifest.get("frozen_config") or {}
    settings = dict(frozen.get("settings") or {})
    approved_runtime = manifest.get("approved_runtime") or {}
    for key in ("concurrency", "browser_pool", "pages_per_browser"):
        if key in approved_runtime:
            settings[key] = approved_runtime[key]
    # Calibration runs are intentionally conservative regardless of later approved runtime.
    if manifest.get("kind") == "pilot":
        settings["concurrency"] = 1
        settings["browser_pool"] = 1
        settings["pages_per_browser"] = 1
    return settings


def _redact(message: str) -> str:
    import re
    return re.sub(r"(?i)(https?|socks5h?)://[^\s/@:]+:[^\s/@]+@", r"\1://***:***@", str(message))


def diagnose_output(message: str, return_code: int) -> str:
    value = str(message).casefold()
    if any(term in value for term in ("captcha", "unusual traffic", "recaptcha")):
        return "google_block"
    if any(term in value for term in ("target closed", "page, context or browser has been closed",
                                      "unexpected page type", "browser_runtime_bug")):
        return "browser_transient"
    if any(term in value for term in ("connection refused", "no such host", "net::err_",
                                      "timeout exceeded", "batch timeout", "temporarily unavailable")):
        return "network_transient"
    if return_code != 0:
        return "process_error"
    return "incomplete_unknown"


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except (OSError, ProcessLookupError):
        return False


def _acquire_lock(lock: Path, run_id: str) -> None:
    if lock.exists():
        try:
            current = json.loads(lock.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            current = {}
        same_host = current.get("hostname") == socket.gethostname()
        if same_host and _pid_alive(int(current.get("pid", 0) or 0)):
            raise RuntimeError("Esta corrida ya está siendo ejecutada")
        # Stale or unreadable locks are recoverable on a local product.
        lock.unlink(missing_ok=True)

    payload = {"pid": os.getpid(), "hostname": socket.gethostname(),
               "run_id": run_id, "created_at": utc_now()}
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream)
    except FileExistsError as exc:
        raise RuntimeError("Esta corrida ya está siendo ejecutada") from exc


def _validate_binary(binary: Path, manifest: dict[str, Any]) -> None:
    expected = manifest.get("gosom_sha256")
    if expected and sha256(binary) != expected:
        raise RuntimeError("El binario Gosom cambió desde que se creó el plan; no se reanuda con otro motor")


def _validate_proxy(root: Path, manifest: dict[str, Any]) -> None:
    expected = manifest.get("proxy_file_sha256")
    if not expected:
        return
    path = root / "config" / "secrets" / "proxies.txt"
    if not path.is_file():
        raise RuntimeError("El plan fue aprobado con proxy y el archivo ya no existe")
    import hashlib
    current = hashlib.sha256(path.read_bytes()).hexdigest()
    if current != expected:
        raise RuntimeError("La configuración de proxy cambió desde la aprobación; genera/aprueba un plan nuevo")


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
    _validate_binary(binary, manifest)
    _validate_proxy(root, manifest)

    settings = _settings(manifest)
    max_retries = max(0, int(settings.get("batch_max_retries", 2)))
    batch_timeout = max(30, int(settings.get("batch_timeout_seconds", 1800)))
    pilot = manifest.get("kind") == "pilot"
    wall_limit = max(60, int(settings.get("pilot_wall_clock_seconds", 900))) if pilot else None
    scrape_limit = max(30, int(settings.get("pilot_scrape_budget_seconds", 720))) if pilot else None
    run_started = time.monotonic()
    deadline = run_started + wall_limit if wall_limit else None

    lock = manifest_path.with_suffix(manifest_path.suffix + ".lock")
    _acquire_lock(lock, str(manifest.get("run_id", "unknown")))
    manifest["status"] = "running"
    manifest.setdefault("started_at", utc_now())
    atomic_json(manifest_path, manifest)

    global_block = False
    try:
        for batch in manifest["batches"]:
            done, total, pending = batch_progress(batch)
            if only_incomplete and not pending:
                batch["status"] = "completed"
                continue
            if deadline is not None and time.monotonic() >= deadline:
                batch["status"] = "not_started_budget_exhausted"
                break

            raw = Path(batch["raw_file"])
            raw.parent.mkdir(parents=True, exist_ok=True)
            batch["status"] = "running"
            batch["started_at"] = batch.get("started_at") or utc_now()
            batch["jobs_completed"] = done
            batch.setdefault("attempts", [])
            atomic_json(manifest_path, manifest)

            for attempt in range(1, max_retries + 2):
                done, total, pending = batch_progress(batch)
                if not pending:
                    break
                if deadline is not None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    timeout = min(batch_timeout, int(max(1, remaining)))
                    if scrape_limit is not None:
                        timeout = min(timeout, scrape_limit)
                else:
                    timeout = batch_timeout

                args = [
                    str(binary), "-resume", "-input", str(Path(batch["input"])),
                    "-results", str(raw),
                    "-lang", str(settings.get("lang", settings.get("language", "es"))),
                    "-depth", str(batch.get("depth", 5)),
                    "-c", str(max(1, int(settings.get("concurrency", 1)))),
                    "-browser-pool-size", str(max(1, int(settings.get("browser_pool", 1)))),
                    "-pages-per-browser", str(max(1, int(settings.get("pages_per_browser", 1)))),
                    "-exit-on-inactivity", str(settings.get("exit_on_inactivity", "4m")),
                ]
                proxies = root / "config" / "secrets" / "proxies.txt"
                if proxies.exists() and any(
                    line.strip() and not line.lstrip().startswith("#")
                    for line in proxies.read_text(encoding="utf-8").splitlines()
                ):
                    args.extend(["-proxies-file", str(proxies)])

                started = time.monotonic()
                try:
                    result = subprocess.run(
                        args, cwd=root, env=gosom_env(root), capture_output=True, text=True,
                        encoding="utf-8", errors="replace", timeout=timeout,
                    )
                    output = result.stdout + "\n" + result.stderr
                    return_code = result.returncode
                except subprocess.TimeoutExpired as exc:
                    output = (exc.stdout or "") + "\n" + (exc.stderr or "") + "\nBatch timeout"
                    return_code = -1

                elapsed = round(time.monotonic() - started, 2)
                done, total, pending = batch_progress(batch)
                diagnosis = "ok" if not pending else diagnose_output(output, return_code)
                attempt_row = {
                    "attempt": attempt, "started_at": batch.get("started_at"),
                    "finished_at": utc_now(), "elapsed_seconds": elapsed,
                    "exit_code": return_code, "diagnosis": diagnosis,
                    "jobs_completed": done, "jobs_total": total, "jobs_pending": len(pending),
                }
                batch["attempts"].append(attempt_row)

                log_path = root / "logs" / str(manifest["run_id"]) / str(batch["batch_id"]) / f"attempt_{attempt:02d}.log"
                log_path.parent.mkdir(parents=True, exist_ok=True)
                log_path.write_text(_redact(output), encoding="utf-8")

                batch.update({
                    "finished_at": utc_now(),
                    "elapsed_seconds": round(sum(float(row["elapsed_seconds"]) for row in batch["attempts"]), 2),
                    "jobs_total": total, "jobs_completed": done, "jobs_failed": len(pending),
                    "pending_job_ids": pending, "exit_code": return_code,
                    "last_diagnosis": diagnosis,
                    "status": "completed" if not pending else "incomplete",
                })
                atomic_json(manifest_path, manifest)

                if not pending:
                    break
                if diagnosis == "google_block":
                    global_block = True
                    break
                if diagnosis not in {"browser_transient", "network_transient"}:
                    break
                if attempt <= max_retries:
                    time.sleep(min(30, 2 ** attempt))

            if global_block:
                manifest["stop_reason"] = "google_block"
                break
            # A persistently bad batch no longer blocks independent later batches.
            if deadline is not None and time.monotonic() >= deadline:
                manifest["stop_reason"] = "pilot_wall_clock_limit"
                break

        for batch in manifest["batches"]:
            done, total, pending = batch_progress(batch)
            if not pending:
                batch["status"] = "completed"
            batch["jobs_total"] = total
            batch["jobs_completed"] = done
            batch["jobs_failed"] = len(pending)
            batch["pending_job_ids"] = pending

        incomplete = [item for item in manifest["batches"] if item.get("status") != "completed"]
        manifest["status"] = "incomplete" if incomplete else "completed"
        manifest["finished_at"] = utc_now()
        manifest["elapsed_seconds"] = round(time.monotonic() - run_started, 2)
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
