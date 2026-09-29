"""Requested-category contract: discovery queries are not inclusion filters."""
from __future__ import annotations

from collections.abc import Iterable, Mapping

from .normalize import normalize_name

REQUESTED = "REQUESTED"
ADDITIONAL = "ADDITIONAL"
UNCLASSIFIED = "UNCLASSIFIED"


def _list(value) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Iterable) and not isinstance(value, Mapping):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]


def _normalized_terms(values) -> list[str]:
    return list(dict.fromkeys(
        term for term in (normalize_name(value) for value in _list(values)) if term
    ))


def resolve_requested_categories(config: Mapping, requested: Iterable[str] | None) -> dict:
    """Freeze a human category request into explicit queries and matching rules.

    Known catalog entries can expand a human category into several discovery
    queries and Google-category aliases. Unknown categories remain valid and use
    the literal term, so FoodScan is not limited to restaurants or food.
    """
    result = dict(config)
    catalog = config.get("category_catalog") or {}
    names = [str(item).strip() for item in (requested or []) if str(item).strip()]
    if not names:
        names = [str(item).strip() for item in config.get("requested_categories", [])
                 if str(item).strip()]
    if not names:
        # Backwards-compatible default: active query terms are also the requested
        # universe until the operator explicitly supplies --categories.
        names = [str(item).strip() for item in config.get("active_queries", [])
                 if str(item).strip()]

    rules = {}
    queries = []
    for raw_name in names:
        key = normalize_name(raw_name)
        entry = None
        canonical = raw_name
        for candidate, value in catalog.items():
            aliases = [candidate] + _list((value or {}).get("request_aliases"))
            if key in _normalized_terms(aliases):
                canonical = candidate
                entry = value or {}
                break
        entry = entry or {}
        discovery = _list(entry.get("queries")) or [raw_name]
        category_aliases = _list(entry.get("google_category_aliases")) or [raw_name]
        name_aliases = _list(entry.get("name_aliases")) or [raw_name]
        rules[canonical] = {
            "queries": list(dict.fromkeys(discovery)),
            "google_category_aliases": list(dict.fromkeys(category_aliases)),
            "name_aliases": list(dict.fromkeys(name_aliases)),
        }
        queries.extend(discovery)

    result["requested_categories"] = list(rules)
    result["requested_category_rules"] = rules
    result["active_queries"] = list(dict.fromkeys(queries))
    return result


def _contains(text: str, term: str) -> bool:
    text, term = normalize_name(text), normalize_name(term)
    if not text or not term:
        return False
    # Normalized phrase containment is intentional: Google categories are short
    # labels ("Taquería", "Tienda de postres", etc.), not arbitrary prose.
    return term in text


def classify_requested_relationship(row: Mapping, categories: Mapping) -> dict:
    """Classify a result without deleting it.

    Google category/tags are strong evidence. Name matching is accepted only
    through the frozen per-category name aliases. Generic/blank Google
    categories with no requested signal remain UNCLASSIFIED; explicit
    nonmatching categories are ADDITIONAL.
    """
    rules = categories.get("requested_category_rules") or {}
    requested = list(categories.get("requested_categories") or rules)
    if not requested:
        return {
            "requested_categories": [],
            "matched_requested_categories": [],
            "category_relationship": UNCLASSIFIED,
            "category_evidence": "requested_universe_not_defined",
            "category_rule_version": "2",
        }
    google_values = [
        str(row.get("google_category") or row.get("category") or "")
    ] + _list(row.get("google_categories") or row.get("categories"))
    google_values = [value for value in google_values if value.strip()]
    title = str(row.get("title") or row.get("name") or "")

    matches, evidence = [], []
    for category in requested:
        rule = rules.get(category) or {
            "google_category_aliases": [category],
            "name_aliases": [category],
        }
        category_hits = [
            value for value in google_values
            if any(_contains(value, alias) for alias in rule.get("google_category_aliases", []))
        ]
        if category_hits:
            matches.append(category)
            evidence.append(f"{category}:google_category={category_hits[0]}")
            continue
        name_hits = [
            alias for alias in rule.get("name_aliases", [])
            if _contains(title, alias)
        ]
        if name_hits:
            matches.append(category)
            evidence.append(f"{category}:name={name_hits[0]}")

    if matches:
        relationship = REQUESTED
    elif not google_values or all(normalize_name(value) in {
        "", "negocio", "establecimiento", "tienda", "restaurant", "restaurante"
    } for value in google_values):
        relationship = UNCLASSIFIED
        evidence.append("generic_or_missing_google_category")
    else:
        relationship = ADDITIONAL
        evidence.append("explicit_google_category_outside_requested_universe")

    return {
        "requested_categories": requested,
        "matched_requested_categories": list(dict.fromkeys(matches)),
        "category_relationship": relationship,
        "category_evidence": "; ".join(evidence),
        "category_rule_version": "2",
    }
