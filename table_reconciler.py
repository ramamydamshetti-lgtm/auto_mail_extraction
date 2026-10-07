"""
Client/Table Cross-check and Reconciliation Engine (Priority 4 Accuracy Rules 4.2 - 4.4).
Reconciles general parser results with specialized table structure extractions.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple
from models import RequirementItem, RequirementParseResult

_LOG = logging.getLogger(__name__)


def has_expected_table_structure(client_name: str | None, text: str) -> bool:
    """
    Triggers special table extractor ONLY when the corresponding client and expected table structure are detected.
    Supported for KPMG, LTTS, ITC, Accenture, Deloitte, and new clients with structured tables.
    """
    if not text:
        return False

    blob = text.lower()

    # Check for KPMG-style table headers: Sr. No / Role / Requirement / Comments
    kpmg_table_headers = ("sr. no", "sr no", "role", "requirement", "comments")
    header_count = sum(1 for h in kpmg_table_headers if h in blob)

    if header_count >= 3:
        return True

    # Generic tabular pattern: Sl No / Position / Experience / Skills
    if ("sl no" in blob or "s.no" in blob or "sr.no" in blob) and ("position" in blob or "role" in blob) and ("skills" in blob or "experience" in blob):
        return True

    return False


def reconcile_parser_results(
    parse_result: RequirementParseResult,
    special_table_results: list[dict[str, Any]],
    client_name: str = "",
) -> tuple[RequirementParseResult, dict[str, Any]]:
    """
    Reconciles General Parser results with Special Table Extractor results.

    Rules:
    - If general parser and table extractor agree on roles: accept seamlessly.
    - If there is a conflict (e.g. general parser extracted Title A, special parser extracted Title B):
      flag for human review (`reconciliation_status = 'conflict_review_flagged'`).
    - NEVER automatically replace general parser results with special parser results on conflict.
    """
    reconciliation_meta: dict[str, Any] = {
        "ran_special_extractor": bool(special_table_results),
        "reconciliation_status": "agreed",
        "conflict_count": 0,
        "processing_note": None,
    }

    if not special_table_results:
        return parse_result, reconciliation_meta

    if not parse_result.requirements:
        # If general parser found nothing but special table found rows, flag for review
        reconciliation_meta["reconciliation_status"] = "conflict_review_flagged"
        reconciliation_meta["conflict_count"] = len(special_table_results)
        note = f"Reconciliation conflict: General parser found 0 roles while special table found {len(special_table_results)} roles. Flagged for review."
        reconciliation_meta["processing_note"] = note
        
        # Return updated parse result envelope with processing note
        d = parse_result.model_dump()
        d["processing_note"] = note
        return RequirementParseResult.model_validate(d), reconciliation_meta

    # Extract job titles for comparison
    gen_titles = [str(r.job_title or "").strip().lower() for r in parse_result.requirements if r.job_title]
    spec_roles = [
        str(row.get("role") or row.get("job_title") or "").strip().lower()
        for row in special_table_results
        if row.get("role") or row.get("job_title")
    ]

    if not gen_titles or not spec_roles:
        return parse_result, reconciliation_meta

    # Check for agreement (fuzzy match between title sets)
    agreed = False
    for gt in gen_titles:
        for st in spec_roles:
            if gt in st or st in gt:
                agreed = True
                break
        if agreed:
            break

    if agreed:
        reconciliation_meta["reconciliation_status"] = "agreed"
        return parse_result, reconciliation_meta

    # Conflict detected! Do NOT overwrite general parser results. Flag for review.
    reconciliation_meta["reconciliation_status"] = "conflict_review_flagged"
    reconciliation_meta["conflict_count"] += 1
    note = (
        f"Reconciliation conflict: General parser extracted '{gen_titles}' "
        f"while special table extractor found roles '{spec_roles}'. Flagged for review."
    )
    reconciliation_meta["processing_note"] = note

    d = parse_result.model_dump()
    d["processing_note"] = note
    return RequirementParseResult.model_validate(d), reconciliation_meta


def run_client_table_reconciliation(
    client_name: str | None,
    body_text: str,
    parse_result: RequirementParseResult,
    graph_id: str | None = None,
    store: Any | None = None,
) -> tuple[RequirementParseResult, dict[str, Any]]:
    """
    Priority 4 Rules 4.2 - 4.4: Client/Table Cross-check and Reconciliation orchestrator.

    Rule 4.2: Run special extractor ONLY when BOTH are true:
      (a) client_name is identified (detected client), and
      (b) has_expected_table_structure(client_name, text) is True.
    For all other emails, return parse_result unchanged.

    Rule 4.3 & 4.4: Compare general vs special extractor and reconcile.
    Wrapped in try/except so failures in special extraction never crash the pipeline.
    """
    default_meta: dict[str, Any] = {
        "ran_special_extractor": False,
        "reconciliation_status": "not_applicable",
        "conflict_count": 0,
        "processing_note": None,
    }

    if not client_name or not has_expected_table_structure(client_name, body_text):
        return parse_result, default_meta

    from job_table_extractor import extract_kpmg_style_roles

    special_res = None
    try:
        special_res = extract_kpmg_style_roles(body_text)
    except Exception as exc:
        _LOG.warning("Special table extractor failed for graph_id=%s: %s", graph_id or "unknown", exc)
        return parse_result, default_meta

    # Adapt data passed to reconcile_parser_results()
    table_rows: list[dict[str, Any]] = []
    if isinstance(special_res, dict):
        table_rows = special_res.get("roles", [])
    elif isinstance(special_res, list):
        table_rows = special_res

    reconciled_result, meta = reconcile_parser_results(
        parse_result=parse_result,
        special_table_results=table_rows,
        client_name=client_name,
    )

    status = meta.get("reconciliation_status", "agreed")
    conflict_count = meta.get("conflict_count", 0)
    note = meta.get("processing_note")
    _LOG.info(
        "Client/Table Cross-check outcome graph_id=%s client=%s: status=%s conflict_count=%d note=%s",
        graph_id or "N/A",
        client_name,
        status,
        conflict_count,
        note,
    )

    if store and graph_id and hasattr(store, "pipeline_mark_processing"):
        detail_msg = f"reconciliation_status={status}, conflict_count={conflict_count}"
        if note:
            detail_msg += f", note={note}"
        store.pipeline_mark_processing(graph_id, detail=detail_msg)

    return reconciled_result, meta
