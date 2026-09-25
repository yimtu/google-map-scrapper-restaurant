"""Deterministic commercial exports and a traceable three-page PDF report.

This module only renders data supplied by the processing pipeline. It performs no
acquisition, matching, or platform inference.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .exports import write_csv
from .platforms import executive_platform_label


BRAND_FIELDS = [
    "brand_id", "brand_name", "branch_count_amg", "branch_count_core",
    "branch_count_urban_amg", "municipalities", "merchant_family", "rating_avg",
    "reviews_total", "website", "phones", "uber_status", "uber_branches_found",
    "rappi_status", "rappi_branches_found", "didi_status", "didi_branches_found",
    "brand_scope", "confidence", "last_verified",
]
BRANCH_FIELDS = [
    "brand_id", "brand_name", "branch_id", "branch_name", "municipality",
    "inside_core_periferico", "inside_urban_amg", "inside_amg_full", "address",
    "latitude", "longitude", "phone", "website", "rating", "review_count",
    "place_id", "uber_status", "rappi_status", "didi_status", "last_verified",
]
EVIDENCE_FIELDS = [
    "brand_id", "brand_name", "branch_id", "branch_name", "platform", "status",
    "evidence_url", "evidence_type", "matched_name", "matched_address", "matched_phone",
    "page_title", "search_queries", "checked_at", "method", "confidence", "notes",
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
        "rating_avg": row.get("rating_avg", ""),
        "reviews_total": row.get("reviews_total", ""),
        "website": row.get("website", ""),
        "phones": row.get("phones", ""),
        "brand_scope": row.get("brand_scope", ""),
        "confidence": row.get("confidence", ""),
        "last_verified": row.get("last_verified", ""),
    }
    for platform in ("uber", "rappi", "didi"):
        evidence = platform_rows.get((brand_id, platform), {})
        output[f"{platform}_status"] = executive_platform_label(
            evidence.get("status", row.get(f"{platform}_status", "")))
        output[f"{platform}_branches_found"] = evidence.get("branches_found", row.get(f"{platform}_branches_found", ""))
    return output


def _commercial_branch(row: dict, platform_rows: dict[tuple[str, str], dict]) -> dict:
    brand_id = str(row.get("brand_id", ""))
    branch_id = str(_first(row, "branch_id", "record_id", "place_id"))
    output = {
        "brand_id": brand_id, "brand_name": row.get("brand_name", ""),
        "branch_id": branch_id, "branch_name": _first(row, "branch_name", "title"),
        "municipality": row.get("municipality", ""),
        "inside_core_periferico": _first(row, "inside_core_periferico", "in_core", default=False),
        "inside_urban_amg": row.get("inside_urban_amg", ""),
        "inside_amg_full": row.get("inside_amg_full", ""),
        "address": row.get("address", ""), "latitude": row.get("latitude", ""),
        "longitude": row.get("longitude", ""), "phone": row.get("phone", ""),
        "website": row.get("website", ""),
        "rating": _first(row, "rating", "review_rating"), "review_count": row.get("review_count", ""),
        "place_id": row.get("place_id", ""), "last_verified": row.get("last_verified", ""),
    }
    for platform in ("uber", "rappi", "didi"):
        detail = platform_rows.get((brand_id, platform), {})
        output[f"{platform}_status"] = executive_platform_label(
            row.get(f"{platform}_status", detail.get("status", "")))
    return output


def _count(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _metric(metric_id, value, source_file, logic, snapshot, generated_at):
    return {"metric_id": metric_id, "display_value": value, "source_file": source_file,
            "logic": logic, "snapshot": snapshot, "generated_at": generated_at}


def _short(value, length=30):
    text = str(value or "")
    return text if len(text) <= length else text[:length - 3] + "..."


def _table(data, widths, font_size=7):
    table = Table(data, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#183B4E")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), font_size),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CBD5E1")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F4F7F8")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return table


def _build_pdf(path: Path, prospects: list[dict], watchlist: list[dict], metrics: dict,
               report: dict, trace: dict, include_platforms: bool):
    path.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    title = ParagraphStyle("FS_Title", parent=styles["Title"], fontName="Helvetica-Bold",
                           fontSize=19, leading=22, textColor=colors.HexColor("#183B4E"), alignment=TA_CENTER)
    heading = ParagraphStyle("FS_Heading", parent=styles["Heading2"], fontName="Helvetica-Bold",
                             fontSize=11, leading=14, textColor=colors.HexColor("#183B4E"), spaceAfter=6)
    body = ParagraphStyle("FS_Body", parent=styles["BodyText"], fontName="Helvetica",
                          fontSize=8, leading=11, textColor=colors.HexColor("#334155"))
    doc = SimpleDocTemplate(str(path), pagesize=letter, rightMargin=14 * mm, leftMargin=14 * mm,
                            topMargin=12 * mm, bottomMargin=13 * mm,
                            title="FoodScan AMG - Resumen ejecutivo trazable")

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#64748B"))
        canvas.drawString(14 * mm, 8 * mm, f"Snapshot: {trace['snapshot_id']}")
        canvas.drawRightString(letter[0] - 14 * mm, 8 * mm, f"Pagina {document.page}")
        canvas.restoreState()

    updated = str(report.get('date') or trace['generated_at'])[:10]
    report_title = "FoodScan AMG" if report.get("report_status") == "FINAL" else "FoodScan AMG - BORRADOR"
    story = [Paragraph(report_title, title),
             Paragraph(f"Periodo: {_short(report.get('month') or trace['snapshot_id'], 40)} | Actualizacion: {updated}", body),
             Spacer(1, 7 * mm), Paragraph("Resumen", heading)]
    summary_rows = [["Metrica", "Valor"],
                    ["Establecimientos unicos", metrics["unique_places"]],
                    ["Marcas con 2+", metrics["brands_2_plus"]],
                    ["TARGET 3-20", metrics["target_brands_3_20"]],
                    ["WATCHLIST exactamente 2", metrics["watchlist_brands_2"]],
                    ["LARGE 21+", metrics["large_brands_21_plus"]]]
    story.extend([_table(summary_rows, [105 * mm, 55 * mm], 9), Spacer(1, 6 * mm),
                  Paragraph("Cobertura de establecimientos", heading),
                  _table([["CORE Periferico", "URBAN AMG", "AMG FULL", "Municipios"],
                          [metrics["places_core"], metrics["places_urban_amg"], metrics["places_amg_full"], metrics["municipalities_observed"]]],
                         [42 * mm, 42 * mm, 42 * mm, 39 * mm], 8), Spacer(1, 6 * mm)])
    if include_platforms:
        story.append(Paragraph("Presencia en plataformas para TARGET", heading))
        platform_rows = [["Plataforma", "Sí", "No confirmada", "Requiere revisión"]]
        for key, label in (("uber", "Uber Eats"), ("rappi", "Rappi"), ("didi", "DiDi Food")):
            platform_rows.append([label, metrics[f"{key}_confirmed"], metrics[f"{key}_not_found"], metrics[f"{key}_requires_review"]])
        story.extend([_table(platform_rows, [55 * mm, 35 * mm, 40 * mm, 35 * mm], 8), Spacer(1, 6 * mm)])
    story.extend([Paragraph(f"Territorio: {_short(report.get('scope', ''), 80)}. Municipios observados: {metrics['municipalities_observed']}.", body),
                  PageBreak(), Paragraph("Prospectos 3-20", title), Spacer(1, 4 * mm)])
    prospect_data = [["Marca", "Suc.", "Municipios", "Categoria"]]
    if include_platforms:
        prospect_data[0].extend(["Uber", "Rappi", "DiDi"])
    prospect_data[0].append("Conf.")
    for row in prospects[:18]:
        data = [_short(row["brand_name"], 23), row["branch_count_amg"], _short(row["municipalities"], 24),
                _short(row["merchant_family"], 17)]
        if include_platforms:
            data.extend([row["uber_status"], row["rappi_status"], row["didi_status"]])
        data.append(row["confidence"])
        prospect_data.append(data)
    widths = [31*mm, 10*mm, 32*mm, 25*mm, 14*mm]
    if include_platforms:
        widths = [31*mm, 10*mm, 32*mm, 25*mm, 20*mm, 19*mm, 19*mm, 14*mm]
    story.append(_table(prospect_data, widths, 6.4))
    if len(prospects) > 18:
        story.extend([Spacer(1, 3 * mm), Paragraph("Listado completo disponible en prospects_3_20.csv. Criterio visible: sucursales descendente y nombre ascendente.", body)])
    story.extend([PageBreak(), Paragraph("Radar y metodologia", title), Spacer(1, 4 * mm),
                  Paragraph("Marcas con exactamente 2 sucursales", heading)])
    watch_data = [["Marca", "Municipios", "Categoria", "Confianza"]]
    for row in watchlist[:12]:
        watch_data.append([_short(row["brand_name"], 32), _short(row["municipalities"], 35),
                           _short(row["merchant_family"], 24), row["confidence"]])
    story.extend([_table(watch_data, [48*mm, 55*mm, 42*mm, 25*mm], 7), Spacer(1, 5 * mm),
                  Paragraph("Metodologia", heading),
                  Paragraph("Resultados adquiridos por Gosom, normalizados y deduplicados por FoodScan. Las marcas se segmentan por sucursales dentro del territorio. La verificacion de plataformas ocurre despues de la segmentacion y conserva evidencia separada.", body),
                  Spacer(1, 3 * mm),
                  Paragraph(f"Fuente: CSV del snapshot. Gosom: {_short(report.get('gosom_version', ''), 30)}. Territorio: {_short(report.get('scope', ''), 40)}. Advertencias: {_short('; '.join(report.get('warnings') or []), 170)}", body),
                  Spacer(1, 3 * mm)])
    if include_platforms:
        story.append(Paragraph("Sí = evidencia verificable encontrada. No confirmada = no se encontro evidencia en la revision realizada; no prueba ausencia. Requiere revisión = la evidencia fue ambigua o la comprobacion no pudo completarse.", body))
    doc.build(story, onFirstPage=footer, onLaterPages=footer)


def generate_standard_reports(snapshot: Path, places: Iterable[dict], brands: Iterable[dict],
                              platform_presence: Iterable[dict] = (), platform_evidence: Iterable[dict] = (),
                              changes: Iterable[dict] = (), run_report: dict | None = None,
                              pdf_path: Path | None = None, charts_enabled: bool = False) -> dict:
    """Write standard exports, traceability metadata, and an exact three-page PDF."""
    if charts_enabled:
        raise ValueError("FoodScan v0.1 reporting requires charts_enabled=false")
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
    target_ids = {row["brand_id"] for row in prospects}
    branches = [_commercial_branch(row, platform_rows) for row in places if str(row.get("brand_id", "")) in target_ids]

    write_csv(snapshot / "master_places.csv", places)
    write_csv(snapshot / "brands_master.csv", commercial, BRAND_FIELDS)
    write_csv(snapshot / "prospects_3_20.csv", prospects, BRAND_FIELDS)
    write_csv(snapshot / "watchlist_2.csv", watchlist, BRAND_FIELDS)
    write_csv(snapshot / "large_21_plus.csv", large, BRAND_FIELDS)
    write_csv(snapshot / "prospect_branches.csv", branches, BRANCH_FIELDS)
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
        values = [str(row[f"{platform}_status"]) for row in prospects]
        status_counts[f"{platform}_confirmed"] = sum(value == "Sí" for value in values)
        status_counts[f"{platform}_not_found"] = sum(value == "No confirmada" for value in values)
        status_counts[f"{platform}_requires_review"] = sum(value == "Requiere revisión" for value in values)
    municipalities = sorted({str(row.get("municipality")) for row in places if row.get("municipality") not in (None, "", "UNKNOWN")})
    metric_values = {
        "unique_places": len(places), "brands_2_plus": sum(_count(r["branch_count_amg"]) >= 2 for r in commercial),
        "target_brands_3_20": len(prospects), "watchlist_brands_2": len(watchlist),
        "large_brands_21_plus": len(large), "municipalities_observed": len(municipalities),
        "places_core": sum(bool(_first(row, "inside_core_periferico", "in_core", default=False)) for row in places),
        "places_urban_amg": sum(bool(row.get("inside_urban_amg")) for row in places),
        "places_amg_full": sum(bool(row.get("inside_amg_full")) for row in places), **status_counts,
    }
    metrics = [
        _metric("unique_places", len(places), "master_places.csv", "count(rows)", snapshot_id, generated_at),
        _metric("brands_2_plus", metric_values["brands_2_plus"], "brands_master.csv", "branch_count_amg >= 2", snapshot_id, generated_at),
        _metric("target_brands_3_20", len(prospects), "prospects_3_20.csv", "branch_count_amg >= 3 AND branch_count_amg <= 20", snapshot_id, generated_at),
        _metric("watchlist_brands_2", len(watchlist), "watchlist_2.csv", "branch_count_amg = 2", snapshot_id, generated_at),
        _metric("large_brands_21_plus", len(large), "large_21_plus.csv", "branch_count_amg >= 21", snapshot_id, generated_at),
        _metric("municipalities_observed", len(municipalities), "master_places.csv", "count(distinct municipality excluding blank and UNKNOWN)", snapshot_id, generated_at),
        _metric("places_core", metric_values["places_core"], "master_places.csv", "inside_core_periferico = true OR in_core = true", snapshot_id, generated_at),
        _metric("places_urban_amg", metric_values["places_urban_amg"], "master_places.csv", "inside_urban_amg = true", snapshot_id, generated_at),
        _metric("places_amg_full", metric_values["places_amg_full"], "master_places.csv", "inside_amg_full = true", snapshot_id, generated_at),
    ]
    if include_platforms:
        for platform in ("uber", "rappi", "didi"):
            for status in ("confirmed", "not_found", "requires_review"):
                key = f"{platform}_{status}"
                metrics.append(_metric(key, metric_values[key], "prospects_3_20.csv",
                                       f"user-facing {platform} result = {status}", snapshot_id, generated_at))
    trace = {
        "snapshot_id": snapshot_id, "generated_at": generated_at, "charts_enabled": False,
        "provenance": {"gosom_version": run_report.get("gosom_version", ""),
                       "foodscan_version": run_report.get("foodscan_version", ""),
                       "territory_version": run_report.get("territory_version", ""),
                       "source_run_ids": run_report.get("source_run_ids", [run_report.get("run_id")] if run_report.get("run_id") else [])},
        "metrics": metrics,
        "tables": [
            {"table_id": "prospects_3_20", "source_file": "prospects_3_20.csv", "filters": "3 <= branch_count_amg <= 20", "sort": "branch_count_amg DESC, brand_name ASC", "row_count_total": len(prospects), "rows_displayed": min(18, len(prospects)), "displayed_brand_ids": [row["brand_id"] for row in prospects[:18]]},
            {"table_id": "watchlist_2", "source_file": "watchlist_2.csv", "filters": "branch_count_amg = 2", "sort": "branch_count_amg DESC, brand_name ASC", "row_count_total": len(watchlist), "rows_displayed": min(12, len(watchlist)), "displayed_brand_ids": [row["brand_id"] for row in watchlist[:12]]},
        ],
        "platform_evidence": {"requested": include_platforms, "included_in_report": include_platforms,
                              "source_file": "platform_presence.csv", "evidence_file": "platform_evidence.csv"},
        "expected_checks": int(run_report.get("expected_checks", 0)),
        "completed_checks": int(run_report.get("completed_checks", 0)),
        "pending_checks": int(run_report.get("pending_checks", 0)),
        "errors": int(run_report.get("errors", 0)),
        "report_status": report_status,
    }
    (snapshot / "report_traceability.json").write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")
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
    _build_pdf(pdf_path, prospects, watchlist, metric_values, run_report, trace, include_platforms)
    return {"pdf": pdf_path, "traceability": snapshot / "report_traceability.json",
            "prospects": snapshot / "prospects_3_20.csv", "watchlist": snapshot / "watchlist_2.csv",
            "report_status": report_status}
