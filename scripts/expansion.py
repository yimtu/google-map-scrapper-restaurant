"""Directed second-phase brand expansion jobs."""
from __future__ import annotations

import hashlib
from urllib.parse import quote


def expansion_candidates(brands):
    result = []
    for row in brands:
        try:
            count = int(row.get("branch_count_amg", row.get("branches_amg", 0)) or 0)
        except (TypeError, ValueError):
            count = 0
        if not 2 <= count <= 20:
            continue
        if row.get("brand_resolution_status") != "CONFIRMED":
            continue
        name = str(row.get("brand_name") or "").strip()
        if not name:
            continue
        result.append(dict(row))
    return result


def representative_points(base_jobs):
    """Pick one deterministic search point per zone from already approved plan geometry."""
    by_zone = {}
    for job in base_jobs:
        zone = str(job.get("zone", "unknown"))
        if zone not in by_zone and job.get("latitude") is not None and job.get("longitude") is not None:
            by_zone[zone] = {
                "zone": zone,
                "scope": job.get("scope"),
                "point_id": job.get("point_id"),
                "latitude": float(job["latitude"]),
                "longitude": float(job["longitude"]),
                "zoom": int(job.get("zoom", 15)),
                "depth": min(int(job.get("depth", 5)), 5),
                "pass": int(job.get("pass", 1)),
            }
    return [by_zone[key] for key in sorted(by_zone)]


def make_expansion_jobs(brands, base_jobs):
    points = representative_points(base_jobs)
    jobs = []
    for brand in expansion_candidates(brands):
        term = str(brand["brand_name"]).strip()
        for point in points:
            job_id = "E_" + hashlib.sha256(
                f"{brand['brand_id']}|{point['zone']}|{term}".encode()
            ).hexdigest()[:24]
            url = (
                f"https://www.google.com/maps/search/{quote(term, safe='')}/"
                f"@{point['latitude']:.7f},{point['longitude']:.7f},{point['zoom']}z"
            )
            jobs.append({
                "job_id": job_id,
                "url": url,
                "point_id": point["point_id"],
                "zone": point["zone"],
                "scope": point["scope"],
                "query": term,
                "query_type": "brand_expansion",
                "brand_id": brand["brand_id"],
                "brand_name": term,
                "depth": point["depth"],
                "zoom": point["zoom"],
                "pass": point["pass"],
                "latitude": point["latitude"],
                "longitude": point["longitude"],
            })
    return jobs
