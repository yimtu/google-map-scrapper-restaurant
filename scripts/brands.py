"""Precision-first brand resolution; same name alone never proves a chain."""
import hashlib
from collections import Counter
from urllib.parse import urlparse

from .normalize import normalize_name

AGGREGATORS = {
    "facebook.com", "instagram.com", "google.com", "maps.google.com", "ubereats.com",
    "rappi.com", "rappi.com.mx", "whatsapp.com", "wa.me", "linktr.ee", "tripadvisor.com",
}
GENERIC_NAMES = {
    "cafe", "cafeteria", "panaderia", "pasteleria", "sushi", "restaurant",
    "restaurante", "comida", "comida para llevar", "supermercado", "tienda", "abarrotes",
    "la casa", "el sazon", "los compadres", "cocina economica", "el rincon",
    "la esquina", "el patio",
}


def domain(value):
    if not isinstance(value, str):
        return ""
    host = (urlparse(value if "://" in value else "https://" + value).hostname or "").lower().removeprefix("www.")
    return "" if any(host == d or host.endswith("." + d) for d in AGGREGATORS) else host


def _brand_row(brand_id, members, evidence, confidence, resolution_status):
    municipalities = sorted({
        r.get("municipality") for r in members
        if r.get("municipality") not in (None, "", "UNKNOWN")
    })
    families = Counter(r.get("merchant_family") for r in members if r.get("merchant_family"))
    ratings = [float(r["review_rating"]) for r in members
               if str(r.get("review_rating", "")).replace(".", "", 1).isdigit()]
    reviews = [int(float(r["review_count"])) for r in members
               if str(r.get("review_count", "")).replace(".", "", 1).isdigit()]
    websites = sorted({r.get("website") for r in members if r.get("website")})
    phones = sorted({r.get("phone") for r in members if r.get("phone")})
    return {
        "brand_id": brand_id,
        "brand_name": members[0].get("title", ""),
        "branches_amg": len(members),
        "branch_count_amg": len(members),
        "branches_core": sum(bool(r.get("inside_core_periferico", r.get("in_core"))) for r in members),
        "branch_count_core": sum(bool(r.get("inside_core_periferico", r.get("in_core"))) for r in members),
        "branch_count_urban_amg": sum(bool(r.get("inside_urban_amg")) for r in members),
        "municipalities": "; ".join(municipalities),
        "merchant_family": families.most_common(1)[0][0] if families else "",
        "rating_avg": round(sum(ratings) / len(ratings), 2) if ratings else "",
        "reviews_total": sum(reviews),
        "website": websites[0] if websites else "",
        "phones": "; ".join(phones),
        "brand_scope": "uncertain",
        "confidence": confidence,
        "brand_resolution_status": resolution_status,
        "evidence": evidence,
    }


def group_brands(rows):
    """Group only when there is strong chain evidence.

    Exact normalized name by itself is intentionally insufficient. Homonyms are
    preserved as separate brands and emitted to the ambiguity queue so a later
    directed web/brand-enrichment pass can resolve them.
    """
    rows = list(rows)
    by_name = {}
    for row in rows:
        name = row.get("normalized_name") or normalize_name(row.get("title"))
        by_name.setdefault(name, []).append(row)

    groups = []
    ambiguous = []
    for name, members in by_name.items():
        hosts = {domain(row.get("website", "")) for row in members} - {""}

        confirmed_members = []
        residual_members = list(members)
        if name and name not in GENERIC_NAMES and len(members) > 1 and len(hosts) == 1:
            host = next(iter(hosts))
            explicit_host_members = [
                row for row in members if domain(row.get("website", "")) == host
            ]
            # Precision-first: at least two establishments must independently carry
            # the same private domain, and only those evidenced rows auto-join.
            if len(explicit_host_members) >= 2:
                confirmed_members = explicit_host_members
                residual_members = [row for row in members if row not in explicit_host_members]
                groups.append(("confirmed", ("domain_name", host, name), confirmed_members))

        # Same-name rows without per-establishment evidence remain independent and
        # visible for review, even when a confirmed chain with that name exists.
        if name and name not in GENERIC_NAMES and len(residual_members) > 0 and (
            len(members) > 1 or confirmed_members
        ):
            ambiguous.append({
                "name": name,
                "candidate_count": len(residual_members),
                "member_record_ids": ";".join(str(row.get("record_id", "")) for row in residual_members),
                "confirmed_member_count": len(confirmed_members),
                "reason": "same_name_without_per_establishment_chain_evidence",
                "resolution_status": "AMBIGUOUS",
            })
        for row in residual_members:
            groups.append(("single", ("individual", row["record_id"]), [row]))

    places, brands = [], []
    for status, key, members in groups:
        brand_id = hashlib.sha256(repr(key).encode()).hexdigest()[:20]
        if status == "confirmed":
            evidence = "same_name_private_domain"
            confidence = 0.99
            resolution_status = "CONFIRMED"
        else:
            evidence = "single_establishment"
            confidence = 0.5
            resolution_status = "SINGLE"
        brand = _brand_row(brand_id, members, evidence, confidence, resolution_status)
        brands.append(brand)
        for row in members:
            places.append({
                **row, **brand,
                "branch_id": row["record_id"],
                "branch_name": row.get("title", ""),
            })
    return places, brands, ambiguous[:1000]
