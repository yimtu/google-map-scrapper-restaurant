"""Deterministic single-PDF reporting with complete category and platform disclosure."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import LongTable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .exports import write_csv
from .platforms import executive_platform_label


BRAND_FIELDS = [
    "brand_id", "brand_name", "branch_count_amg", "branch_count_core",
    "branch_count_urban_amg", "municipalities", "merchant_family", "category_scope",
    "requested_branch_count", "additional_branch_count", "unclassified_branch_count",
    "matched_requested_categories", "rating_avg", "reviews_total", "website", "phones",
    "uber_status", "uber_branches_found", "rappi_status", "rappi_branches_found",
    "didi_status", "didi_branches_found", "brand_scope", "confidence",
    "brand_resolution_status", "last_verified",
]
BRANCH_FIELDS = [
    "brand_id", "brand_name", "branch_id", "branch_name", "category_relationship",
    "matched_requested_categories", "google_category", "google_categories", "municipality",
    "inside_core_periferico", "inside_urban_amg", "inside_amg_full", "address",
    "latitude", "longitude", "phone", "website", "review_rating", "review_count",
    "price_range", "open_hours", "order_online", "place_id",
    "uber_status", "rappi_status", "didi_status", "last_verified",
]
EVIDENCE_FIELDS = [
    "brand_id", "brand_name", "branch_id", "branch_name", "platform", "status",
    "evidence_url", "evidence_type", "matched_name", "matched_address", "matched_phone",
    "page_title", "search_queries", "checked_at", "method", "confidence", "notes",
    "verifier_type", "protocol_version",
]
PRESENCE_FIELDS = [
    "brand_id", "brand_name", "uber_status", "uber_branches_found", "uber_branches_total",
    "rappi_status", "rappi_branches_found", "rappi_branches_total", "didi_status",
    "didi_branches_found", "didi_branches_total", "branch_id", "branch_name", "platform",
    "status", "branches_found", "branches_total", "checked_at", "method", "confidence", "notes",
]


def _first(row: dict, *keys, default=""):
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return default


def _count(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _text(value, limit=120):
    if value in (None, ""):
        return ""
    if isinstance(value, (dict, list, tuple)):
        value = json.dumps(value, ensure_ascii=False)
    value = str(value)
    return value if len(value) <= limit else value[:limit - 3] + "..."


def _platform_key(value: object) -> str:
    text = str(value or "").casefold()
    if "uber" in text:
        return "uber"
    if "rappi" in text:
        return "rappi"
    if "didi" in text:
        return "didi"
    return ""


def _platform_summary(presence: list[dict]) -> dict[tuple[str, str], dict]:
    result = {}
    for row in presence:
        platform = _platform_key(row.get("platform"))
        brand_id = str(row.get("brand_id", ""))
        if platform and brand_id:
            result[(brand_id, platform)] = row
        elif brand_id:
            for prefix in ("uber", "rappi", "didi"):
                if f"{prefix}_status" in row:
                    result[(brand_id, prefix)] = {
                        "status": row.get(f"{prefix}_status", ""),
                        "branches_found": row.get(f"{prefix}_branches_found", ""),
                        "branches_total": row.get(f"{prefix}_branches_total", ""),
                    }
    return result


def _commercial_brand(row: dict, platform_rows: dict[tuple[str, str], dict]) -> dict:
    brand_id = str(row.get("brand_id", ""))
    output = {
        "brand_id": brand_id,
        "brand_name": row.get("brand_name", ""),
        "branch_count_amg": _first(row, "branch_count_amg", "branches_amg", default=0),
        "branch_count_core": _first(row, "branch_count_core", "branches_core", default=0),
        "branch_count_urban_amg": _first(row, "branch_count_urban_amg", "branches_urban_amg", default=0),
        "municipalities": row.get("municipalities", ""),
        "merchant_family": row.get("merchant_family", ""),
        "category_scope": row.get("category_scope", ""),
        "requested_branch_count": row.get("requested_branch_count", ""),
        "additional_branch_count": row.get("additional_branch_count", ""),
        "unclassified_branch_count": row.get("unclassified_branch_count", ""),
        "matched_requested_categories": row.get("matched_requested_categories", ""),
        "rating_avg": row.get("rating_avg", ""),
        "reviews_total": row.get("reviews_total", ""),
        "website": row.get("website", ""),
        "phones": row.get("phones", ""),
        "brand_scope": row.get("brand_scope", ""),
        "confidence": row.get("confidence", ""),
        "brand_resolution_status": row.get("brand_resolution_status", ""),
        "last_verified": row.get("last_verified", ""),
    }
    for platform in ("uber", "rappi", "didi"):
        evidence = platform_rows.get((brand_id, platform), {})
        output[f"{platform}_status"] = executive_platform_label(
            evidence.get("status", row.get(f"{platform}_status", "")))
        output[f"{platform}_branches_found"] = evidence.get(
            "branches_found", row.get(f"{platform}_branches_found", ""))
    return output


def _commercial_branch(row: dict) -> dict:
    output = {field: row.get(field, "") for field in BRANCH_FIELDS}
    output["branch_id"] = str(_first(row, "branch_id", "record_id", "place_id"))
    output["branch_name"] = _first(row, "branch_name", "title")
    output["review_rating"] = _first(row, "review_rating", "rating")
    for platform in ("uber", "rappi", "didi"):
        output[f"{platform}_status"] = executive_platform_label(row.get(f"{platform}_status", ""))
    return output


def _metric(metric_id, value, source_file, logic, snapshot, generated_at):
    return {"metric_id": metric_id, "display_value": value, "source_file": source_file,
            "logic": logic, "snapshot": snapshot, "generated_at": generated_at}


def _cell(value, body_style, limit=100):
    return Paragraph(_text(value, limit).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"),
                     body_style)


def _table(data, widths, body_style, font_size=6.4):
    converted = []
    for row_index, row in enumerate(data):
        if row_index == 0:
            converted.append([Paragraph(f"<b>{_text(value, 80)}</b>", body_style) for value in row])
        else:
            converted.append([_cell(value, body_style) for value in row])
    table = LongTable(converted, colWidths=widths, repeatRows=1, splitByRow=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#183B4E")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), font_size),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F9FA")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 2.5), ("RIGHTPADDING", (0, 0), (-1, -1), 2.5),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]))
    return table


def _relationship_label(value: object) -> str:
    return {
        "REQUESTED": "Solicitado",
        "ADDITIONAL": "Hallazgo adicional",
        "UNCLASSIFIED": "No clasificado",
        "MIXED": "Mixto",
    }.get(str(value or "").upper(), str(value or ""))


def _build_pdf(path: Path, places: list[dict], commercial: list[dict], metrics: dict,
               report: dict, trace: dict, include_platforms: bool):
    path.parent.mkdir(parents=True, exist_ok=True)
    page_size = landscape(letter)
    styles = getSampleStyleSheet()
    title = ParagraphStyle("FS_Title", parent=styles["Title"], fontName="Helvetica-Bold",
                           fontSize=18, leading=21, textColor=colors.HexColor("#183B4E"),
                           alignment=TA_CENTER)
    heading = ParagraphStyle("FS_Heading", parent=styles["Heading2"], fontName="Helvetica-Bold",
                             fontSize=11, leading=14, textColor=colors.HexColor("#183B4E"),
                             spaceBefore=5, spaceAfter=5)
    body = ParagraphStyle("FS_Body", parent=styles["BodyText"], fontName="Helvetica",
                          fontSize=7.2, leading=9.2, textColor=colors.HexColor("#334155"))
    small = ParagraphStyle("FS_Small", parent=body, fontSize=6.2, leading=7.5)
    doc = SimpleDocTemplate(str(path), pagesize=page_size, rightMargin=9 * mm, leftMargin=9 * mm,
                            topMargin=10 * mm, bottomMargin=12 * mm,
                            title="FoodScan - Reporte completo trazable")

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont("Helvetica", 6.5)
        canvas.setFillColor(colors.HexColor("#64748B"))
        canvas.drawString(9 * mm, 7 * mm, f"Snapshot: {trace['snapshot_id']}")
        canvas.drawRightString(page_size[0] - 9 * mm, 7 * mm, f"Página {document.page}")
        canvas.restoreState()

    requested_places = [p for p in places if p.get("category_relationship") == "REQUESTED"]
    additional_places = [p for p in places if p.get("category_relationship") == "ADDITIONAL"]
    unclassified_places = [p for p in places if p.get("category_relationship") == "UNCLASSIFIED"]
    multi = [b for b in commercial if _count(b["branch_count_amg"]) >= 3
             and b.get("brand_resolution_status") == "CONFIRMED"]
    target = [b for b in commercial if 3 <= _count(b["branch_count_amg"]) <= 20]
    watchlist = [b for b in commercial if _count(b["branch_count_amg"]) == 2]

    updated = str(report.get("date") or trace["generated_at"])[:10]
    status = "FINAL" if report.get("report_status") == "FINAL" else "BORRADOR"
    requested_categories = ", ".join(report.get("requested_categories") or []) or "No especificadas"
    story = [
        Paragraph(f"FoodScan — Reporte completo ({status})", title),
        Paragraph(
            f"Periodo: {_text(report.get('month') or trace['snapshot_id'], 40)} | "
            f"Actualización: {updated} | Territorio: {_text(report.get('scope', ''), 50)}",
            body,
        ),
        Spacer(1, 3 * mm),
        Paragraph("Alcance aprobado", heading),
        Paragraph(f"<b>Categorías solicitadas:</b> {_text(requested_categories, 400)}", body),
        Paragraph(
            "Google Maps puede devolver recomendaciones ajenas a las búsquedas. FoodScan no las elimina: "
            "las conserva y las separa como Hallazgos adicionales o No clasificados. Sólo los resultados "
            "Solicitados alimentan los KPIs de categoría; todos permanecen trazables.",
            body,
        ),
        Spacer(1, 4 * mm),
        Paragraph("Auditoría de adquisición", heading),
    ]
    acquisition = [
        ["Etapa", "Cantidad"],
        ["Resultados crudos Gosom", report.get("raw_records", 0)],
        ["Establecimientos únicos en territorio", len(places)],
        ["Solicitados", len(requested_places)],
        ["Hallazgos adicionales", len(additional_places)],
        ["No clasificados", len(unclassified_places)],
        ["Marcas detectadas", len(commercial)],
        ["Negocios confirmados con 3+ locales", len(multi)],
        ["WATCHLIST (2 locales)", len(watchlist)],
        ["TARGET (3–20)", len(target)],
    ]
    story.extend([_table(acquisition, [80*mm, 35*mm], body, 8), Spacer(1, 4 * mm)])

    if include_platforms:
        story.append(Paragraph("Uber Eats, Rappi y DiDi Food — decisiones independientes", heading))
        story.append(Paragraph(
            "Cada negocio confirmado con 3 o más locales se evalúa por separado en las tres plataformas. "
            "“Sí” requiere evidencia positiva. “No confirmada” significa que el protocolo terminó sin "
            "evidencia suficiente y no demuestra ausencia absoluta. Nunca se colapsan las tres plataformas "
            "en un único campo de delivery.",
            body,
        ))
        platform_rows = [["Plataforma", "Sí", "No confirmada", "Requiere revisión"]]
        for key, label in (("uber", "Uber Eats"), ("rappi", "Rappi"), ("didi", "DiDi Food")):
            platform_rows.append([
                label, metrics[f"{key}_confirmed"], metrics[f"{key}_not_found"],
                metrics[f"{key}_requires_review"],
            ])
        story.extend([Spacer(1, 2*mm), _table(platform_rows, [50*mm, 30*mm, 38*mm, 38*mm], body, 7.5)])

    # Complete 3+ business table, irrespective of category or upper size.
    story.extend([PageBreak(), Paragraph("Negocios confirmados con 3+ locales", title),
                  Paragraph("Incluye cualquier giro. Uber Eats, Rappi y DiDi Food son columnas independientes.", body),
                  Spacer(1, 3*mm)])
    multi_rows = [["Negocio", "Locales", "Origen", "Categoría / giro", "Municipios", "Rating",
                   "Reviews", "Uber Eats", "Rappi", "DiDi Food"]]
    for row in multi:
        multi_rows.append([
            row["brand_name"], row["branch_count_amg"], _relationship_label(row.get("category_scope")),
            row.get("merchant_family", ""), row.get("municipalities", ""), row.get("rating_avg", ""),
            row.get("reviews_total", ""), row.get("uber_status", ""), row.get("rappi_status", ""),
            row.get("didi_status", ""),
        ])
    story.append(_table(multi_rows, [38*mm, 12*mm, 22*mm, 30*mm, 39*mm, 14*mm, 17*mm, 22*mm, 20*mm, 20*mm], small, 5.9))

    # Branch detail for every confirmed 3+ brand.
    by_brand = {}
    for place in places:
        by_brand.setdefault(str(place.get("brand_id", "")), []).append(place)
    for brand in multi:
        members = by_brand.get(str(brand.get("brand_id", "")), [])
        story.extend([PageBreak(), Paragraph(
            f"{_text(brand['brand_name'], 90)} — {len(members)} locales", title),
            Paragraph(
                f"Origen: {_relationship_label(brand.get('category_scope'))}. "
                f"Municipios: {_text(brand.get('municipalities', ''), 180)}.",
                body,
            ), Spacer(1, 3*mm)])
        rows = [["Local", "Categoría Google", "Relación", "Municipio", "Dirección", "Rating",
                 "Reviews", "Teléfono", "Uber", "Rappi", "DiDi"]]
        for place in members:
            rows.append([
                _first(place, "branch_name", "title"),
                place.get("google_category", ""), _relationship_label(place.get("category_relationship")),
                place.get("municipality", ""), place.get("address", ""),
                _first(place, "review_rating", "rating"), place.get("review_count", ""),
                place.get("phone", ""), executive_platform_label(place.get("uber_status", "")),
                executive_platform_label(place.get("rappi_status", "")),
                executive_platform_label(place.get("didi_status", "")),
            ])
        story.append(_table(rows, [30*mm, 27*mm, 21*mm, 25*mm, 50*mm, 12*mm, 14*mm, 24*mm, 18*mm, 18*mm, 18*mm], small, 5.6))

    def directory_section(title_text, rows, explanation):
        story.extend([PageBreak(), Paragraph(title_text, title), Paragraph(explanation, body), Spacer(1, 3*mm)])
        data = [["Nombre", "Categoría Google", "Categoría solicitada", "Municipio", "Dirección",
                 "Rating", "Reviews", "Teléfono", "Website"]]
        for row in rows:
            data.append([
                row.get("title", ""), row.get("google_category", ""),
                ", ".join(row.get("matched_requested_categories") or []),
                row.get("municipality", ""), row.get("address", ""),
                _first(row, "review_rating", "rating"), row.get("review_count", ""),
                row.get("phone", ""), row.get("website", ""),
            ])
        story.append(_table(data, [34*mm, 30*mm, 31*mm, 25*mm, 54*mm, 12*mm, 14*mm, 25*mm, 42*mm], small, 5.7))

    directory_section(
        "Directorio — categorías solicitadas",
        requested_places,
        "Todos los establecimientos clasificados como pertenecientes al universo solicitado; no se trunca la lista.",
    )
    directory_section(
        "Hallazgos adicionales",
        additional_places,
        "Google Maps los devolvió durante las búsquedas, pero su categoría explícita está fuera del universo solicitado. Se conservan; no alteran los KPIs solicitados.",
    )
    directory_section(
        "No clasificados",
        unclassified_places,
        "Resultados con categoría insuficiente o genérica para afirmar si pertenecen o no al universo solicitado. Se conservan sin inventar una decisión.",
    )

    story.extend([PageBreak(), Paragraph("Metodología y trazabilidad", title), Spacer(1, 3*mm)])
    methodology = [
        "Gosom ejecuta consultas textuales sobre Google Maps; las consultas no son filtros duros de categoría.",
        "FoodScan conserva la salida cruda en JSON Lines para preservar category y categories[] cuando Gosom los entrega.",
        "La relación de categoría se clasifica como REQUESTED, ADDITIONAL o UNCLASSIFIED sin borrar resultados válidos.",
        "La deduplicación conserva identificadores y evidencia; la resolución de cadenas no usa el nombre por sí solo.",
        "Toda marca confirmada con 3+ locales entra a verificación independiente de Uber Eats, Rappi y DiDi Food, sin importar el giro ni el número máximo de locales.",
        "Links explícitos de order_online capturados por Gosom sirven como evidencia positiva; la ausencia de link nunca equivale a No.",
        "Los estados públicos son Sí, No confirmada y Requiere revisión. No confirmada no prueba ausencia absoluta.",
    ]
    for item in methodology:
        story.append(Paragraph("• " + item, body))
    story.extend([
        Spacer(1, 3*mm),
        Paragraph(
            f"Plan: {_text(report.get('plan_id', ''), 60)} | "
            f"Metodología: {_text(report.get('methodology_hash', ''), 80)} | "
            f"Gosom: {_text(report.get('gosom_version', ''), 40)}",
            body,
        ),
        Paragraph(f"Advertencias: {_text('; '.join(report.get('warnings') or []), 600)}", body),
    ])
    doc.build(story, onFirstPage=footer, onLaterPages=footer)


def generate_standard_reports(snapshot: Path, places: Iterable[dict], brands: Iterable[dict],
                              platform_presence: Iterable[dict] = (), platform_evidence: Iterable[dict] = (),
                              changes: Iterable[dict] = (), run_report: dict | None = None,
                              pdf_path: Path | None = None, charts_enabled: bool = False) -> dict:
    """Write machine-readable support files and one complete human-facing PDF."""
    if charts_enabled:
        raise ValueError("FoodScan reporting requires charts_enabled=false")
    snapshot = Path(snapshot)
    snapshot.mkdir(parents=True, exist_ok=True)
    places, brands = list(places), list(brands)
    presence, evidence, changes = list(platform_presence), list(platform_evidence), list(changes)
    run_report = dict(run_report or {})
    generated_at = datetime.now(timezone.utc).isoformat()
    snapshot_id = str(run_report.get("month") or snapshot.name)
    platform_rows = _platform_summary(presence)
    commercial = [_commercial_brand(row, platform_rows) for row in brands]
    commercial.sort(key=lambda r: (-_count(r["branch_count_amg"]), str(r["brand_name"]).casefold()))

    prospects = [row for row in commercial if 3 <= _count(row["branch_count_amg"]) <= 20]
    watchlist = [row for row in commercial if _count(row["branch_count_amg"]) == 2]
    large = [row for row in commercial if _count(row["branch_count_amg"]) >= 21]
    multi = [row for row in commercial if _count(row["branch_count_amg"]) >= 3
             and row.get("brand_resolution_status") == "CONFIRMED"]
    multi_ids = {row["brand_id"] for row in multi}
    branches = [_commercial_branch(row) for row in places if str(row.get("brand_id", "")) in multi_ids]

    write_csv(snapshot / "master_places.csv", places)
    write_csv(snapshot / "brands_master.csv", commercial, BRAND_FIELDS)
    write_csv(snapshot / "prospects_3_20.csv", prospects, BRAND_FIELDS)
    write_csv(snapshot / "watchlist_2.csv", watchlist, BRAND_FIELDS)
    write_csv(snapshot / "large_21_plus.csv", large, BRAND_FIELDS)
    write_csv(snapshot / "multi_location_3_plus.csv", multi, BRAND_FIELDS)
    write_csv(snapshot / "multi_location_branches.csv", branches, BRANCH_FIELDS)
    # Backwards-compatible alias: prospect_branches now contains all confirmed 3+ branches.
    write_csv(snapshot / "prospect_branches.csv", branches, BRANCH_FIELDS)
    write_csv(snapshot / "requested_places.csv",
              [row for row in places if row.get("category_relationship") == "REQUESTED"])
    write_csv(snapshot / "additional_findings.csv",
              [row for row in places if row.get("category_relationship") == "ADDITIONAL"])
    write_csv(snapshot / "unclassified_findings.csv",
              [row for row in places if row.get("category_relationship") == "UNCLASSIFIED"])
    write_csv(snapshot / "platform_presence.csv", presence, PRESENCE_FIELDS)
    write_csv(snapshot / "platform_evidence.csv", evidence, EVIDENCE_FIELDS)
    write_csv(snapshot / "changes.csv", changes)

    include_platforms = bool(run_report.get("platform_verification_requested", False))
    report_status = str(run_report.get("report_status", "FINAL")).upper()
    if report_status not in {"FINAL", "DRAFT"}:
        raise ValueError("report_status must be FINAL or DRAFT")
    expected_checks = int(run_report.get("expected_checks", 0) or 0)
    completed_checks = int(run_report.get("completed_checks", 0) or 0)
    pending_checks = int(run_report.get("pending_checks", 0) or 0)
    error_count = int(run_report.get("errors", 0) or 0)
    if min(expected_checks, completed_checks, pending_checks, error_count) < 0:
        raise ValueError("quality-gate counts cannot be negative")
    if include_platforms and (pending_checks or error_count or completed_checks != expected_checks):
        report_status = "DRAFT"
    run_report["report_status"] = report_status

    status_counts = {}
    for platform in ("uber", "rappi", "didi"):
        values = [str(row[f"{platform}_status"]) for row in multi]
        status_counts[f"{platform}_confirmed"] = sum(value == "Sí" for value in values)
        status_counts[f"{platform}_not_found"] = sum(value == "No confirmada" for value in values)
        status_counts[f"{platform}_requires_review"] = sum(value == "Requiere revisión" for value in values)

    municipalities = sorted({str(row.get("municipality")) for row in places
                             if row.get("municipality") not in (None, "", "UNKNOWN")})
    metric_values = {
        "unique_places": len(places),
        "requested_places": sum(row.get("category_relationship") == "REQUESTED" for row in places),
        "additional_places": sum(row.get("category_relationship") == "ADDITIONAL" for row in places),
        "unclassified_places": sum(row.get("category_relationship") == "UNCLASSIFIED" for row in places),
        "multi_location_3_plus": len(multi),
        "target_brands_3_20": len(prospects),
        "watchlist_brands_2": len(watchlist),
        "large_brands_21_plus": len(large),
        "municipalities_observed": len(municipalities),
        **status_counts,
    }
    metrics = [
        _metric("unique_places", len(places), "master_places.csv", "count(rows)", snapshot_id, generated_at),
        _metric("requested_places", metric_values["requested_places"], "requested_places.csv",
                "category_relationship = REQUESTED", snapshot_id, generated_at),
        _metric("additional_places", metric_values["additional_places"], "additional_findings.csv",
                "category_relationship = ADDITIONAL", snapshot_id, generated_at),
        _metric("unclassified_places", metric_values["unclassified_places"], "unclassified_findings.csv",
                "category_relationship = UNCLASSIFIED", snapshot_id, generated_at),
        _metric("multi_location_3_plus", len(multi), "multi_location_3_plus.csv",
                "confirmed brand AND branch_count_amg >= 3", snapshot_id, generated_at),
        _metric("target_brands_3_20", len(prospects), "prospects_3_20.csv",
                "3 <= branch_count_amg <= 20", snapshot_id, generated_at),
        _metric("watchlist_brands_2", len(watchlist), "watchlist_2.csv",
                "branch_count_amg = 2", snapshot_id, generated_at),
        _metric("large_brands_21_plus", len(large), "large_21_plus.csv",
                "branch_count_amg >= 21", snapshot_id, generated_at),
    ]
    if include_platforms:
        for platform in ("uber", "rappi", "didi"):
            for status in ("confirmed", "not_found", "requires_review"):
                key = f"{platform}_{status}"
                metrics.append(_metric(
                    key, metric_values[key], "multi_location_3_plus.csv",
                    f"independent {platform} result for confirmed businesses with 3+ locations = {status}",
                    snapshot_id, generated_at,
                ))

    trace = {
        "snapshot_id": snapshot_id,
        "generated_at": generated_at,
        "charts_enabled": False,
        "provenance": {
            "gosom_version": run_report.get("gosom_version", ""),
            "foodscan_version": run_report.get("foodscan_version", ""),
            "territory_sha256": run_report.get("territory_sha256", ""),
            "plan_id": run_report.get("plan_id", ""),
            "methodology_hash": run_report.get("methodology_hash", ""),
            "source_run_ids": run_report.get(
                "source_run_ids", [run_report.get("run_id")] if run_report.get("run_id") else []),
        },
        "metrics": metrics,
        "tables": [
            {"table_id": "multi_location_3_plus", "source_file": "multi_location_3_plus.csv",
             "filters": "confirmed brand AND branch_count_amg >= 3",
             "row_count_total": len(multi), "rows_displayed": len(multi),
             "displayed_brand_ids": [row["brand_id"] for row in multi]},
            {"table_id": "requested_places", "source_file": "requested_places.csv",
             "filters": "category_relationship = REQUESTED",
             "row_count_total": metric_values["requested_places"],
             "rows_displayed": metric_values["requested_places"]},
            {"table_id": "additional_findings", "source_file": "additional_findings.csv",
             "filters": "category_relationship = ADDITIONAL",
             "row_count_total": metric_values["additional_places"],
             "rows_displayed": metric_values["additional_places"]},
            {"table_id": "unclassified_findings", "source_file": "unclassified_findings.csv",
             "filters": "category_relationship = UNCLASSIFIED",
             "row_count_total": metric_values["unclassified_places"],
             "rows_displayed": metric_values["unclassified_places"]},
        ],
        "platform_evidence": {
            "requested": include_platforms,
            "included_in_report": include_platforms,
            "selection_rule": "every confirmed business with >=3 observed locations; category-independent",
            "platforms": ["UBER_EATS", "RAPPI", "DIDI_FOOD"],
            "source_file": "platform_presence.csv",
            "evidence_file": "platform_evidence.csv",
        },
        "expected_checks": expected_checks,
        "completed_checks": completed_checks,
        "pending_checks": pending_checks,
        "errors": error_count,
        "report_status": report_status,
    }
    (snapshot / "report_traceability.json").write_text(
        json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")

    requested_path = Path(pdf_path) if pdf_path is not None else snapshot / "FoodScan_Report.pdf"
    if report_status == "DRAFT":
        stale_final = snapshot / "FoodScan_Report.pdf"
        if stale_final.exists():
            archived = snapshot / "FoodScan_Report_PREVIOUS.pdf"
            if archived.exists():
                archived = snapshot / f"FoodScan_Report_PREVIOUS_{generated_at[:19].replace(':', '-')}.pdf"
            stale_final.replace(archived)
        pdf_path = requested_path.with_name("FoodScan_Report_DRAFT.pdf")
    else:
        stale_draft = snapshot / "FoodScan_Report_DRAFT.pdf"
        if stale_draft.exists():
            archived = snapshot / "FoodScan_Report_DRAFT_PREVIOUS.pdf"
            if archived.exists():
                archived = snapshot / f"FoodScan_Report_DRAFT_PREVIOUS_{generated_at[:19].replace(':', '-')}.pdf"
            stale_draft.replace(archived)
        pdf_path = requested_path

    _build_pdf(pdf_path, places, commercial, metric_values, run_report, trace, include_platforms)
    return {
        "pdf": pdf_path,
        "traceability": snapshot / "report_traceability.json",
        "prospects": snapshot / "prospects_3_20.csv",
        "watchlist": snapshot / "watchlist_2.csv",
        "multi_location": snapshot / "multi_location_3_plus.csv",
        "report_status": report_status,
    }
