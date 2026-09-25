"""Platform-check queues and deterministic evidence integration; no web calls."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping

from .commercial import TARGET, WATCHLIST, classify_branch_count, branch_count

CONFIRMED = "CONFIRMED"
NOT_FOUND = "NOT_FOUND"
UNCERTAIN = "UNCERTAIN"
PENDING = "PENDING"
ERROR = "ERROR"
COMPLETED_STATUSES = frozenset({CONFIRMED, NOT_FOUND, UNCERTAIN})
PLATFORMS = ("UBER_EATS", "RAPPI", "DIDI_FOOD")

_ALIASES = {
    "uber": "UBER_EATS", "uber_eats": "UBER_EATS", "ubereats": "UBER_EATS",
    "rappi": "RAPPI", "didi": "DIDI_FOOD", "didi_food": "DIDI_FOOD",
    "didifood": "DIDI_FOOD",
}
_PREFIX = {"UBER_EATS": "uber", "RAPPI": "rappi", "DIDI_FOOD": "didi"}
EVIDENCE_FIELDS = (
    "brand_id", "brand_name", "branch_id", "branch_name", "platform", "status",
    "evidence_url", "evidence_type", "matched_name", "matched_address", "matched_phone",
    "page_title", "search_queries", "checked_at", "method", "confidence", "notes",
)


def normalize_platform(value: object) -> str:
    key = str(value or "").strip().casefold().replace(" ", "_").replace("-", "_")
    platform = _ALIASES.get(key)
    if platform is None:
        raise ValueError(f"unsupported platform: {value!r}")
    return platform


def normalize_platform_status(value: object) -> str:
    status = str(value or "").strip().upper().replace(" ", "_")
    if not status:
        return PENDING
    if status not in {CONFIRMED, NOT_FOUND, UNCERTAIN, PENDING, ERROR}:
        raise ValueError(f"unsupported platform status: {value!r}")
    return status


def executive_platform_label(status: object) -> str:
    normalized = normalize_platform_status(status)
    return {CONFIRMED: "Sí", NOT_FOUND: "No confirmada"}.get(normalized, "Requiere revisión")


def create_platform_check_queue(
    brands: Iterable[Mapping],
    branches: Iterable[Mapping],
    *,
    platforms: Iterable[str] = PLATFORMS,
    include_watchlist: bool = False,
) -> list[dict]:
    """Create a model-independent queue, defaulting to TARGET brands."""
    allowed = {TARGET, WATCHLIST} if include_watchlist else {TARGET}
    selected = {
        str(brand.get("brand_id")): brand
        for brand in brands
        if branch_count(brand) and classify_branch_count(branch_count(brand)) in allowed
    }
    canonical_platforms = tuple(dict.fromkeys(normalize_platform(item) for item in platforms))
    queue = []
    for branch in branches:
        brand_id = str(branch.get("brand_id", ""))
        brand = selected.get(brand_id)
        if not brand:
            continue
        for platform in canonical_platforms:
            queue.append({
                "brand_id": brand_id,
                "branch_id": branch.get("branch_id", ""),
                "brand": brand.get("brand_name", branch.get("brand_name", "")),
                "branch": branch.get("branch_name", branch.get("title", "")),
                "address": branch.get("address", ""),
                "phone": branch.get("phone", ""),
                "website": branch.get("website", ""),
                "platform": platform,
            })
    return queue


def _validate_evidence(source: Mapping) -> dict:
    row = {field: source.get(field, "") for field in EVIDENCE_FIELDS}
    row["platform"] = normalize_platform(source.get("platform"))
    row["status"] = normalize_platform_status(source.get("status"))
    missing = [field for field in ("brand_id", "branch_id") if not row[field]]
    if row["status"] in COMPLETED_STATUSES | {ERROR}:
        missing.extend(field for field in ("checked_at", "method") if not row[field])
    if row["status"] == CONFIRMED and not row["evidence_url"]:
        missing.append("evidence_url")
    if row["status"] == CONFIRMED:
        missing.extend(field for field in ("page_title", "matched_name", "matched_address") if not row[field])
    if row["status"] == NOT_FOUND:
        searches = [item.strip() for item in str(row.get("search_queries", "")).split("||") if item.strip()]
        if len(searches) < 3:
            missing.append("search_queries (general || domain || brand+location)")
    if missing:
        raise ValueError("platform evidence missing required fields: " + ", ".join(missing))
    return row


def _resolve_status(rows: list[Mapping]) -> str:
    if not rows:
        return PENDING
    statuses = {row["status"] for row in rows}
    if ERROR in statuses:
        return ERROR
    if PENDING in statuses:
        return PENDING
    if len(statuses) == 1:
        return next(iter(statuses))
    return UNCERTAIN


def integrate_platform_evidence(
    brands: Iterable[Mapping], branches: Iterable[Mapping], evidence: Iterable[Mapping]
) -> dict[str, list[dict]]:
    """Integrate imported evidence at branch and brand levels."""
    brand_rows = [dict(row) for row in brands]
    branch_rows = [dict(row) for row in branches]
    clean = [_validate_evidence(row) for row in evidence]
    known_brands = {str(row.get("brand_id", "")) for row in brand_rows}
    known_branches = {(str(row.get("brand_id", "")), str(row.get("branch_id", ""))) for row in branch_rows}
    orphans = [row for row in clean if str(row["brand_id"]) not in known_brands or
               (str(row["brand_id"]), str(row["branch_id"])) not in known_branches]
    if orphans:
        raise ValueError("platform evidence references an unknown brand_id or branch_id")
    by_branch: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for row in clean:
        by_branch[(str(row["brand_id"]), str(row["branch_id"]), row["platform"])].append(row)

    enriched_branches = []
    for branch in branch_rows:
        brand_id, branch_id = str(branch.get("brand_id", "")), str(branch.get("branch_id", ""))
        fields = {}
        for platform in PLATFORMS:
            observations = by_branch.get((brand_id, branch_id, platform), [])
            fields[f"{_PREFIX[platform]}_status"] = _resolve_status(observations)
        enriched_branches.append({**branch, **fields})

    branches_by_brand: dict[str, list[dict]] = defaultdict(list)
    for branch in enriched_branches:
        branches_by_brand[str(branch.get("brand_id", ""))].append(branch)
    enriched_brands = []
    for brand in brand_rows:
        members = branches_by_brand.get(str(brand.get("brand_id", "")), [])
        fields = {}
        for platform in PLATFORMS:
            prefix = _PREFIX[platform]
            statuses = [member[f"{prefix}_status"] for member in members]
            found = sum(status == CONFIRMED for status in statuses)
            if ERROR in statuses:
                status = ERROR
            elif PENDING in statuses or not statuses:
                status = PENDING
            elif found:
                status = CONFIRMED
            elif statuses and all(item == NOT_FOUND for item in statuses):
                status = NOT_FOUND
            else:
                status = UNCERTAIN
            fields.update({
                f"{prefix}_status": status,
                f"{prefix}_branches_found": found,
                f"{prefix}_branches_total": len(members),
            })
        enriched_brands.append({**brand, **fields})
    return {
        "platform_presence": enriched_brands,
        "brand_presence": enriched_brands,
        "branch_presence": enriched_branches,
        "platform_evidence": clean,
    }


def platform_quality_gate(queue: Iterable[Mapping], branch_presence: Iterable[Mapping], *, requested: bool) -> dict:
    """Validate every expected TARGET branch/platform check before a final report."""
    if not requested:
        return {"expected_checks": 0, "completed_checks": 0, "pending_checks": 0,
                "errors": 0, "report_status": "FINAL", "platform_section_included": False,
                "missing_checks": [], "error_checks": []}
    branches = {(str(row.get("brand_id", "")), str(row.get("branch_id", ""))): row
                for row in branch_presence}
    completed = pending = errors = 0
    missing_checks, error_checks = [], []
    for expected in queue:
        platform = normalize_platform(expected.get("platform"))
        key = (str(expected.get("brand_id", "")), str(expected.get("branch_id", "")))
        row = branches.get(key, {})
        status = normalize_platform_status(row.get(f"{_PREFIX[platform]}_status", PENDING))
        check = {"brand_id": key[0], "branch_id": key[1], "platform": platform}
        if status in COMPLETED_STATUSES:
            completed += 1
        elif status == ERROR:
            errors += 1
            error_checks.append(check)
        else:
            pending += 1
            missing_checks.append(check)
    expected_count = completed + pending + errors
    return {"expected_checks": expected_count, "completed_checks": completed,
            "pending_checks": pending, "errors": errors,
            "report_status": "FINAL" if expected_count == completed else "DRAFT",
            "platform_section_included": True, "missing_checks": missing_checks,
            "error_checks": error_checks}
