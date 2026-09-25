"""Deterministic commercial segmentation and branch-network planning."""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping

SINGLE = "SINGLE"
WATCHLIST = "WATCHLIST"
TARGET = "TARGET"
LARGE = "LARGE"

GENERIC_BRAND_NAMES = frozenset({
    "cafe", "cafeteria", "panaderia", "pasteleria", "restaurant", "restaurante",
    "sushi", "comida", "comida para llevar", "supermercado", "tienda", "abarrotes",
})


def _key(value: object) -> str:
    value = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value.casefold())).strip()


def _integer(value: object, *, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be an integer")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer") from exc
    if number < 0:
        raise ValueError(f"{field} cannot be negative")
    return number


def branch_count(row: Mapping) -> int:
    for field in ("branch_count_amg", "branches_amg", "expanded_branch_count",
                  "branches_detected", "discovery_branch_count"):
        if row.get(field) not in (None, ""):
            return _integer(row[field], field=field)
    return 0


def classify_branch_count(count: object) -> str:
    """Return the exact commercial bucket for a positive branch count."""
    count = _integer(count, field="branch_count")
    if count < 1:
        raise ValueError("branch_count must be at least 1")
    if count == 1:
        return SINGLE
    if count == 2:
        return WATCHLIST
    if count <= 20:
        return TARGET
    return LARGE


def segment_brands(brands: Iterable[Mapping]) -> list[dict]:
    """Copy brand rows and add their commercial segment."""
    result = []
    for brand in brands:
        count = branch_count(brand)
        if count < 1:
            raise ValueError(f"brand {brand.get('brand_id', '')!r} has no branches")
        result.append({**brand, "commercial_segment": classify_branch_count(count)})
    return result


def plan_branch_network_completion(
    brands: Iterable[Mapping],
    *,
    expansion_jobs: int = 1,
    excluded_brand_ids: Iterable[str] = (),
    excluded_brand_names: Iterable[str] = (),
    generic_names: Iterable[str] = GENERIC_BRAND_NAMES,
    large_threshold: int = 21,
) -> list[dict]:
    """Plan explicit brand searches and retain audit fields for every decision.

    Existing expansion results are preserved. New work is planned only for a
    discovered brand with at least two branches and no exclusion reason.
    """
    default_jobs = _integer(expansion_jobs, field="expansion_jobs")
    excluded_ids = {str(item) for item in excluded_brand_ids}
    excluded_names = {_key(item) for item in excluded_brand_names}
    generic = {_key(item) for item in generic_names}
    planned = []
    for source in brands:
        row = dict(source)
        brand_id = str(row.get("brand_id", ""))
        name = _key(row.get("brand_name") or row.get("brand_candidate"))
        discovery = next((row.get(field) for field in (
            "discovery_branch_count", "branches_detected", "branches_amg", "branch_count_amg"
        ) if row.get(field) not in (None, "")), 0)
        discovery = _integer(discovery, field="discovery_branch_count")
        expanded = _integer(row.get("expanded_branch_count", discovery), field="expanded_branch_count")
        reasons = []
        if discovery < 2:
            reasons.append("fewer_than_two_discovery_branches")
        if not name or name in generic:
            reasons.append("generic_or_empty_name")
        if brand_id in excluded_ids or name in excluded_names or row.get("excluded_from_expansion"):
            reasons.append("user_or_source_exclusion")
        if discovery >= large_threshold or row.get("is_large_chain"):
            reasons.append("large_chain")
        eligible = not reasons
        has_existing_expansion = any(field in source for field in (
            "expanded_branch_count", "expansion_jobs", "expansion_confidence"
        ))
        jobs = _integer(row.get("expansion_jobs", default_jobs if eligible else 0), field="expansion_jobs")
        if not eligible and not has_existing_expansion:
            jobs = 0
        confidence = str(row.get("expansion_confidence") or row.get("confidence") or "uncertain")
        planned.append({
            **row,
            "discovery_branch_count": discovery,
            "expanded_branch_count": expanded,
            "expansion_jobs": jobs,
            "expansion_confidence": confidence,
            "complete_branch_network": eligible,
            "expansion_exclusion_reason": ";".join(reasons),
        })
    return planned


def _values(value: object) -> set[str]:
    if isinstance(value, str):
        return {_key(part) for part in re.split(r"[;,|]", value) if _key(part)}
    if isinstance(value, Iterable) and not isinstance(value, (bytes, Mapping)):
        return {_key(part) for part in value if _key(part)}
    return {_key(value)} if _key(value) else set()


def filter_commercial_brands(
    brands: Iterable[Mapping],
    *,
    municipalities: Iterable[str] | None = None,
    layer: str | None = None,
    min_branches: int | None = None,
    max_branches: int | None = None,
    merchant_families: Iterable[str] | None = None,
    platform_statuses: Mapping[str, Iterable[str]] | None = None,
) -> list[dict]:
    """Filter existing brand data; this function never performs acquisition."""
    wanted_municipalities = {_key(item) for item in municipalities or ()}
    wanted_families = {_key(item) for item in merchant_families or ()}
    lower = _integer(min_branches, field="min_branches") if min_branches is not None else None
    upper = _integer(max_branches, field="max_branches") if max_branches is not None else None
    if lower is not None and upper is not None and lower > upper:
        raise ValueError("min_branches cannot exceed max_branches")
    layer_fields = {
        "core": "inside_core_periferico", "core_periferico": "inside_core_periferico",
        "urban": "inside_urban_amg", "urban_amg": "inside_urban_amg",
        "amg": "inside_amg_full", "amg_full": "inside_amg_full",
    }
    layer_field = layer_fields.get(_key(layer)) if layer else None
    if layer and not layer_field:
        raise ValueError(f"unsupported geography layer: {layer}")
    platform_prefixes = {
        "uber": "uber", "uber eats": "uber", "ubereats": "uber",
        "rappi": "rappi", "didi": "didi", "didi food": "didi", "didifood": "didi",
    }
    wanted_platforms = {
        platform_prefixes.get(_key(platform), _key(platform)): {str(status).upper() for status in statuses}
        for platform, statuses in (platform_statuses or {}).items()
    }
    result = []
    for source in brands:
        count = branch_count(source)
        if lower is not None and count < lower or upper is not None and count > upper:
            continue
        if wanted_municipalities and not (_values(source.get("municipalities")) & wanted_municipalities):
            continue
        if layer_field and not bool(source.get(layer_field)):
            continue
        if wanted_families and not (_values(source.get("merchant_family")) & wanted_families):
            continue
        if any(str(source.get(f"{platform}_status", "PENDING")).upper() not in statuses
               for platform, statuses in wanted_platforms.items()):
            continue
        result.append(dict(source))
    return result
