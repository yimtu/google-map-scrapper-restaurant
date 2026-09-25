"""Create local-only runtime files without embedding workstation-specific paths."""
from __future__ import annotations

import shutil
from pathlib import Path


LOCAL_DIRECTORIES = (
    "tools/gosom", "config/secrets", "territory/input", "territory/processed",
    "generated/queries", "generated/batches", "data", "snapshots", "logs",
    "output", ".runtime/playwright", "tests/smoke",
)


def prepare_local_workspace(root: Path) -> dict:
    root = Path(root).resolve()
    created: list[str] = []
    for relative in LOCAL_DIRECTORIES:
        path = root / relative
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            created.append(relative)

    settings = root / "config" / "settings.json"
    example = root / "config" / "settings.example.json"
    if not settings.exists():
        if not example.is_file():
            raise FileNotFoundError("config/settings.example.json is missing from this distribution.")
        shutil.copyfile(example, settings)
        created.append("config/settings.json")

    proxies = root / "config" / "secrets" / "proxies.txt"
    if not proxies.exists():
        proxies.write_text("# One optional proxy URL per line\n", encoding="utf-8")
        created.append("config/secrets/proxies.txt")
    return {"root": str(root), "created": created}
