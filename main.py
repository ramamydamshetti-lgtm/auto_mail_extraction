"""
MetaForge recruitment pipeline: Graph inbox → filter → AI classify/extract → MetaForge.
Legacy ``dump`` subcommand keeps the original JSON/CSV/SQLite export behavior.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import os
import re
from pathlib import Path
import shutil
import sys
import time
from dataclasses import asdict
from datetime import date, datetime, timezone
from typing import Any

from dotenv import load_dotenv

from attachment_handler import extract_text_from_attachment
from body_normalizer import html_to_plain, normalize_body, scrub_pii
from client_detector import ClientMatch, detect_client, resolve_idexcel_client_for_requirement
from config import Settings, is_strict_field_mapping
from email_filter import (
    apply_email_filter,
    has_requirement_structure,
    is_sender_allowlisted,
)
from field_mapper import EmailContext, check_ui_readiness, map_to_metaforge
from strict_validator import validate_requirement_before_save
from historical_autofill import autofill_from_history
from metaforge_api import IdAllocator, send_to_metaforge
from outlook_graph import (
    OutlookMessage,
    acquire_token_from_env,
    fetch_attachment_detail,
    fetch_attachments,
    iter_inbox_messages,
    message_to_outlook,
)
from processed_store import ProcessedStore
from requirement_classifier import classify_email, heuristic_obvious_client_requirement
from requirement_parser import parse_requirements_from_email
from table_reconciler import run_client_table_reconciliation
from models import RequirementItem
from requirement_identity import clean_client_jd_id, compute_requirement_identity, normalize_client_key
from requirement_comparator import (
    build_requirement_profile,
    compare_requirements,
    normalize_city,
)
from utils import (
    bind_log_context,
    clear_log_context,
    decode_graph_attachment_bytes,
    setup_logging,
)

_LOG = logging.getLogger(__name__)


def _parse_to_utc_dt(dt_val: Any) -> datetime:
    """Parse any datetime value into a timezone-aware UTC datetime object."""
    if not dt_val:
        return datetime.min.replace(tzinfo=timezone.utc)
    s = str(dt_val).strip()
    if not s or s.lower() in ("none", "null", "n/a"):
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        if s.endswith("Z"):
            return datetime.fromisoformat(s[:-1] + "+00:00").astimezone(timezone.utc)
        if "+" in s[10:] or ("-" in s[10:] and len(s) > 16):
            return datetime.fromisoformat(s).astimezone(timezone.utc)
        if len(s) == 10:
            return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if " " in s[:19]:
            s = s[:10] + "T" + s[11:]
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)


def get_effective_cutoff_iso(settings: Settings, store: ProcessedStore) -> str | None:
    """
    Compute effective cutoff: max(cutoff, watermark - 5 minutes) formatted as UTC ISO string.
    Never processes mail older than cutoff.
    """
    from datetime import timedelta

    cutoff_dt = None
    if settings.ingest_start_datetime:
        cutoff_dt = _parse_to_utc_dt(settings.ingest_start_datetime)
        if cutoff_dt == datetime.min.replace(tzinfo=timezone.utc):
            cutoff_dt = None

    watermark_dt = None
    wm_str = store.get_watermark()
    if wm_str:
        w_parsed = _parse_to_utc_dt(wm_str)
        if w_parsed != datetime.min.replace(tzinfo=timezone.utc):
            watermark_dt = w_parsed - timedelta(minutes=5)

    effective_dt = None
    if cutoff_dt and watermark_dt:
        effective_dt = max(cutoff_dt, watermark_dt)
    elif cutoff_dt:
        effective_dt = cutoff_dt
    elif watermark_dt:
        effective_dt = watermark_dt

    if effective_dt:
        return effective_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return None



# --- Legacy dump (original export) -------------------------------------------------


def _msg_dict(om: OutlookMessage) -> dict[str, object]:
    return asdict(om)


def _structured_email(row: dict[str, object], *, body_mode: str) -> dict[str, object]:
    attachments = row.get("attachments") or []
    extracted: dict[str, object] = {}
    requirement = build_requirement_struct(
        subject=str(row.get("subject") or ""),
        from_email=str(row.get("from_email") or ""),
        from_name=str(row.get("from_name") or ""),
        body_normalized=str(row.get("body_normalized") or ""),
        job_table=None,
    )

    content: dict[str, object] = {"normalized": row.get("body_normalized") or ""}
    if body_mode == "full":
        content["plain"] = row.get("body_plain") or ""
        content["html"] = row.get("body_html") or ""

    return {
        "id": {
            "graph_id": row.get("graph_id") or "",
            "internet_message_id": row.get("internet_message_id") or "",
        },
        "metadata": {
            "subject": row.get("subject") or "",
            "from": {
                "email": row.get("from_email") or "",
                "name": row.get("from_name") or "",
            },
            "to": row.get("to_recipients") or [],
            "cc": row.get("cc_recipients") or [],
            "received_date_time": row.get("received_date_time") or "",
            "is_read": bool(row.get("is_read")),
        },
        "content": content,
        "attachments": attachments,
        "extracted": extracted,
        "requirement": requirement,
    }


def _build_row(
    raw: dict[str, object], token: str, mailbox: str
) -> tuple[dict[str, object], OutlookMessage]:
    body_obj = raw.get("body") or {}
    ctype = (body_obj.get("contentType") or "").lower()
    content = body_obj.get("content") or ""
    plain, html = "", ""
    if "html" in ctype:
        html = content
        plain = html_to_plain(html)
    else:
        plain = content
    norm = normalize_body(plain, html)
    mid = raw.get("id") or ""
    atts: list = []
    if raw.get("hasAttachments") and mid:
        try:
            atts = fetch_attachments(token, mailbox, mid)
        except Exception:
            atts = []
    om = message_to_outlook(
        raw,
        body_plain=plain,
        body_html=html,
        body_normalized=norm,
        attachments=atts,
    )
    row = _msg_dict(om)
    return row, om


def run_legacy_dump(args: argparse.Namespace) -> int:
    import os
    import sqlite3
    from datetime import datetime, timezone

    default_mailbox = os.getenv(
        "MAILBOX_UPN",
        "recruitment.application@metaforgeit.com",
    ).strip()

    mailbox = args.mailbox or default_mailbox
    try:
        token = acquire_token_from_env()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 1

    rows: list[dict[str, object]] = []
    with ProcessedStore(args.processed_db) as store:
        for raw in iter_inbox_messages(token, mailbox, limit=args.limit):
            gid = raw.get("id")
            if not gid:
                continue
            if not args.no_skip_processed and store.is_processed(gid):
                continue
            try:
                row, _ = _build_row(raw, token, mailbox)
            except Exception as ex:
                print(f"Skip message {gid}: {ex}", file=sys.stderr)
                continue
            rows.append(row)
            store.mark(gid)

    if args.format == "json":
        with open(args.output, "w", encoding="utf-8") as f:
            structured = [_structured_email(r, body_mode=args.body_mode) for r in rows]
            json.dump(structured, f, ensure_ascii=False, indent=2)
    elif args.format == "csv":
        base_fields = [
            "graph_id",
            "internet_message_id",
            "subject",
            "from_email",
            "from_name",
            "source_vendor_key",
            "source_vendor_display",
            "sender_domain",
            "to_recipients",
            "received_date_time",
            "is_read",
            "requirement_summary",
            "locations_joined",
            "key_points_count",
            "key_points_json",
            "experience_mentions_joined",
            "requirement_json",
            "body_char_count",
            "body_normalized",
            "attachment_count",
            "attachments_json",
            "job_locations",
            "job_roles_count",
            "job_roles_json",
            "candidate_submissions_count",
            "candidate_submissions_json",
        ]
        if args.body_mode == "full":
            base_fields.extend(["body_plain", "body_html"])

        with open(args.output, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=base_fields)
            w.writeheader()

            for r in rows:
                to_list = r.get("to_recipients")
                to_s = ";".join(to_list) if isinstance(to_list, list) else str(to_list or "")

                attachments = r.get("attachments") or []
                attachment_count = len(attachments) if isinstance(attachments, list) else 0

                jt: dict[str, Any] = {}
                locs = []
                roles = []
                csubs = []
                job_locations = ""
                job_roles_count = 0

                body_full = str(r.get("body_normalized") or "")
                body_char_count = len(body_full)
                if args.csv_body_full:
                    body_out = body_full
                else:
                    cap = 3000
                    body_out = (
                        body_full
                        if len(body_full) <= cap
                        else body_full[: cap - 1].rstrip() + "…"
                    )

                req = build_requirement_struct(
                    subject=str(r.get("subject") or ""),
                    from_email=str(r.get("from_email") or ""),
                    from_name=str(r.get("from_name") or ""),
                    body_normalized=body_full,
                    job_table=None,
                )
                src = req.get("source") or {}
                locs_all = req.get("locations") or []
                locs_joined = ";".join(locs_all) if isinstance(locs_all, list) else ""
                kpts = req.get("key_points") or []
                kpt_count = len(kpts) if isinstance(kpts, list) else 0
                exp = req.get("experience_mentions") or []
                exp_joined = ";".join(exp) if isinstance(exp, list) else ""

                row_out: dict[str, object] = {
                    "graph_id": r.get("graph_id") or "",
                    "internet_message_id": r.get("internet_message_id") or "",
                    "subject": r.get("subject") or "",
                    "from_email": r.get("from_email") or "",
                    "from_name": r.get("from_name") or "",
                    "source_vendor_key": src.get("vendor_key") or "",
                    "source_vendor_display": src.get("vendor_display") or "",
                    "sender_domain": src.get("sender_domain") or "",
                    "to_recipients": to_s,
                    "received_date_time": r.get("received_date_time") or "",
                    "is_read": bool(r.get("is_read")),
                    "requirement_summary": req.get("summary") or "",
                    "locations_joined": locs_joined,
                    "key_points_count": kpt_count,
                    "key_points_json": json.dumps(
                        kpts if isinstance(kpts, list) else [], ensure_ascii=False
                    ),
                    "experience_mentions_joined": exp_joined,
                    "requirement_json": json.dumps(req, ensure_ascii=False),
                    "body_char_count": body_char_count,
                    "body_normalized": body_out,
                    "attachment_count": attachment_count,
                    "attachments_json": json.dumps(attachments, ensure_ascii=False),
                    "job_locations": job_locations,
                    "job_roles_count": job_roles_count,
                    "job_roles_json": json.dumps(
                        roles if isinstance(roles, list) else [], ensure_ascii=False
                    ),
                    "candidate_submissions_count": len(csubs),
                    "candidate_submissions_json": json.dumps(csubs, ensure_ascii=False),
                }
                if args.body_mode == "full":
                    row_out["body_plain"] = r.get("body_plain") or ""
                    row_out["body_html"] = r.get("body_html") or ""

                w.writerow(row_out)
    else:
        db_path = args.output
        parent = os.path.dirname(os.path.abspath(db_path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        conn = sqlite3.connect(db_path)
        conn.execute(
            """CREATE TABLE IF NOT EXISTS extractions (
                graph_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                extracted_at TEXT NOT NULL
            )"""
        )
        now = datetime.now(timezone.utc).isoformat()
        for r in rows:
            payload = _structured_email(r, body_mode=args.body_mode)
            conn.execute(
                "INSERT OR REPLACE INTO extractions (graph_id, payload, extracted_at) VALUES (?,?,?)",
                (r["graph_id"], json.dumps(payload, ensure_ascii=False), now),
            )
        conn.commit()
        conn.close()

    print(f"Wrote {len(rows)} message(s) to {args.output}", file=sys.stderr)
    return 0


# --- MetaForge pipeline ------------------------------------------------------------


def _attachment_text_extras(
    token: str, mailbox: str, message_id: str, attachments: list[Any]
) -> str:
    """Download supported attachments and append extracted text for AI context."""
    chunks: list[str] = []
    for att in attachments:
        name = (getattr(att, "name", None) or "")
        lower_name = name.lower()
        ct = (getattr(att, "content_type", None) or "")
        # Ignore obvious non-JD binaries.
        if lower_name.endswith((".zip", ".rar", ".7z", ".mp4", ".avi", ".mp3")):
            continue
        aid = getattr(att, "id", None)
        if not aid:
            continue
        try:
            detail = fetch_attachment_detail(token, mailbox, message_id, aid)
        except Exception as exc:
            _LOG.warning("Attachment fetch failed %s: %s", name, exc)
            continue
        if detail.get("@odata.type") != "#microsoft.graph.fileAttachment":
            continue
        data = decode_graph_attachment_bytes(detail)
        if not data:
            continue
        text = extract_text_from_attachment(
            data,
            name=name,
            content_type=ct,
        )
        if text:
            chunks.append(f"\n--- Attachment: {name or 'file'} ---\n{text}")
    return "\n".join(chunks)


def _body_from_raw(raw: dict[str, Any]) -> tuple[str, str, str]:
    body_obj = raw.get("body") or {}
    ctype = (body_obj.get("contentType") or "").lower()
    content = body_obj.get("content") or ""
    plain, html = "", ""
    if "html" in ctype:
        html = content
        plain = html_to_plain(html)
    else:
        plain = content
    norm = normalize_body(plain, html)
    return plain, html, norm


def extract_and_map(
    raw: dict[str, Any],
    *,
    token: str,
    mailbox: str,
    settings: Settings,
    allocator: IdAllocator | None = None,
    skip_classifier: bool = False,
) -> tuple[str, list[dict[str, Any]], str]:
    """
    Single-pass extraction flow:
    read body + attachments -> classify/filter -> parse -> map to dashboard payload(s).
    Returns (status, payloads, body_for_ai).
    """
    subject = str(raw.get("subject") or "")
    plain, html_body, norm = _body_from_raw(raw)
    gid = str(raw.get("id") or "").strip()
    has_att = bool(raw.get("hasAttachments"))

    atts: list = []
    if has_att and gid:
        try:
            atts = fetch_attachments(token, mailbox, gid)
        except Exception as exc:
            _LOG.warning("List attachments failed: %s", exc)

    attachment_context = ""
    if atts and gid:
        attachment_context = _attachment_text_extras(token, mailbox, gid, atts)

    stitched_context = (
        f"ATTACHMENT_PRIMARY_CONTEXT:\n{attachment_context}\n\n"
        f"EMAIL_BODY_METADATA_CONTEXT:\n{norm or plain}"
        if attachment_context
        else (norm or plain)
    )
    body_for_ai = scrub_pii(stitched_context)

    from_obj = raw.get("from") or {}
    ea = (from_obj.get("emailAddress") or {}) if isinstance(from_obj, dict) else {}
    fe = (ea.get("address") or "").strip()
    fn = (ea.get("name") or "").strip()

    fe_clean = fe.strip().lower()
    is_internal_mf = (
        fe_clean.endswith("@metaforgeit.com")
        or fe_clean.endswith(".metaforgeit.com")
        or ("@metaforgeit.com" in fe_clean)
    )
    if is_internal_mf and fe_clean != "rkarnam@metaforgeit.com":
        _LOG.info("Completely blocked internal sender %s (only rkarnam@metaforgeit.com permitted)", fe)
        return "sender_not_allowlisted", [], body_for_ai

    if not is_sender_allowlisted(fe):
        return "sender_not_allowlisted", [], body_for_ai

    client = detect_client(subject, body_for_ai, fe)
    if client is None:
        return "unknown_client", [], body_for_ai

    if not has_requirement_structure(body_for_ai):
        # N3: Emails from allowed client domains that fail body gate go to AI classifier; not dropped
        if is_sender_allowlisted(fe):
            _LOG.info("Allowed client sender failed body gate; routing to AI classifier per N3: %s", fe)
        else:
            return "no_requirement_structure_in_body", [], body_for_ai

    filt = apply_email_filter(
        from_email=fe,
        body=body_for_ai,
    )
    if not filt.allowed:
        return f"filter:{filt.reason}", [], body_for_ai

    is_classifier_uncertain = False
    if not skip_classifier:
        if heuristic_obvious_client_requirement(subject, body_for_ai):
            _LOG.info(
                "Heuristic client-requirement gate passed (vendor JD pattern); skipping LLM classifier"
            )
        else:
            cls_res = classify_email(body_for_ai, subject=subject, settings=settings, from_email=fe)
            if cls_res.label == "NOT_A_REQUIREMENT":
                return "ai_classifier_no", [], body_for_ai

    parsed = parse_requirements_from_email(
        subject=subject, body=body_for_ai, settings=settings, message_id=gid or None, from_email=fe
    )

    client_name = client.display_name if client else None
    parsed, recon_meta = run_client_table_reconciliation(
        client_name=client_name,
        body_text=body_for_ai,
        parse_result=parsed,
        graph_id=gid,
    )

    # N4: Table emails: rows detected = requirements extracted + duplicates + flagged. A mismatch goes to review.
    if recon_meta and recon_meta.get("ran_special_extractor"):
        spec_rows = recon_meta.get("special_rows") or []
        spec_count = recon_meta.get("special_rows_count") or len(spec_rows)
        if spec_count > 0 and len(parsed.requirements) != spec_count:
            _LOG.warning("Table rows mismatch (N4): detected=%s, extracted=%s. Flagged for review.", spec_count, len(parsed.requirements))
            for r in parsed.requirements:
                r.raw_status = "PENDING_REVIEW"
                r.possible_miss = True

    kept: list[RequirementItem] = []
    for item in parsed.requirements:
        conf = float(item.confidence)
        if conf < settings.openai_min_confidence:
            _LOG.info(
                "Drop sub-requirement (confidence %.2f < %.2f)",
                conf,
                settings.openai_min_confidence,
            )
            continue
        kept.append(item)
    if not kept:
        return (parsed.processing_note or "no_requirements_after_parse"), [], body_for_ai

    om = message_to_outlook(
        raw,
        body_plain=plain,
        body_html=html_body,
        body_normalized=norm,
        attachments=atts,
    )
    ctx = EmailContext(
        graph_message_id=gid,
        internet_message_id=om.internet_message_id,
        to_emails=om.to_recipients,
        cc_emails=om.cc_recipients,
        from_email=fe,
        from_name=fn,
    )

    recv_raw = str(raw.get("receivedDateTime") or "").strip()
    recv_date = date.today()
    if recv_raw:
        try:
            recv_date = date.fromisoformat(recv_raw[:10])
        except ValueError:
            recv_date = date.today()

    payloads: list[dict[str, Any]] = []
    for idx, ext in enumerate(kept):
        ext_obj = ext.model_dump(mode="json", by_alias=True)

        req_client = client
        if ext.client_name:
            c_key = normalize_client_key(ext.client_name)
            req_client = ClientMatch(key=c_key, display_name=ext.client_name)
        elif fe and fe.lower().endswith("@idexcel.com"):
            req_text = (ext.job_title or "") + " " + " ".join(ext.mandatory_skills or [])
            req_client, idexcel_note = resolve_idexcel_client_for_requirement(
                subject=subject,
                body=body_for_ai,
                requirement_text=req_text,
                role_index=idx,
            )
            if idexcel_note:
                existing_note = ext_obj.get("processing_note")
                ext_obj["processing_note"] = (
                    f"{idexcel_note} | {existing_note}" if existing_note else idexcel_note
                )
                ext_obj["idexcel_unresolved"] = True

        if parsed.processing_note and not ext_obj.get("processing_note"):
            ext_obj["processing_note"] = parsed.processing_note

        if recon_meta.get("reconciliation_status"):
            ext_obj["reconciliation_status"] = recon_meta["reconciliation_status"]

        if is_classifier_uncertain or req_client.key == "idexcel_unresolved":
            ext_obj["is_classifier_uncertain"] = True

        job_id = allocator.next_job_id(recv_date) if allocator is not None else ""
        # Bug B fix: record the ID source so disagreements between LLM-extracted
        # client_jd_id and allocator-generated IDs are visible and auditable.
        # ext.req_id is what the parser explicitly found in the email text.
        # If the LLM wrote a client_jd_id field in its raw output but it doesn't
        # match ext.req_id (e.g. it read a neighbouring row's ID), flag it.
        llm_raw_cjd = str(ext_obj.get("client_jd_id") or ext_obj.get("client_req_id") or getattr(ext, "client_jd_id", None) or "").strip() or None
        cjd = ext.req_id or llm_raw_cjd or (allocator.next_client_jd_id(req_client.key) if allocator is not None else None)
        if llm_raw_cjd and ext.req_id and llm_raw_cjd != ext.req_id:
            _LOG.warning(
                "client_jd_id_disagreement gid=%s llm_extracted=%r parser_req_id=%r allocator_cjd=%r — "
                "LLM and parser read different IDs for the same email row; using parser req_id.",
                gid, llm_raw_cjd, ext.req_id, cjd,
            )
        payload = map_to_metaforge(
            ext_obj,
            ctx=ctx,
            client_display_name=req_client.display_name,
            job_id=job_id,
            client_jd_id=cjd,
            body_text=body_for_ai,
            internal_poc_default=settings.internal_poc_default,
            jd_count=len(kept),
            demand_received_date=recv_date,
            email_subject=subject,
            email_body_plain=plain,
            email_body_html=html_body,
            email_received_iso=recv_raw,
        )
        payload["client_key"] = req_client.key
        if req_client.key == "idexcel_unresolved":
            payload["idexcel_unresolved"] = True
        chosen_id = ext.req_id or llm_raw_cjd
        if chosen_id:
            payload["_has_req_id"] = True
            payload["client_jd_id"] = chosen_id
            # Bug B: record ID provenance for audit
            payload.setdefault("_provenance", {})
            if isinstance(payload["_provenance"], dict):
                payload["_provenance"]["client_jd_id_source"] = "llm_parser"
                if llm_raw_cjd and ext.req_id and llm_raw_cjd != ext.req_id:
                    payload["_provenance"]["client_jd_id_llm_raw"] = llm_raw_cjd
                    payload["_provenance"]["client_jd_id_disagreement"] = True
            if ext.raw_status:
                raw_st = ext.raw_status.lower()
                if "hold" in raw_st:
                    payload["job_status"] = "hold"
                    if not is_strict_field_mapping():
                        payload["priority"] = "Low"
                else:
                    payload["job_status"] = "open"
        conv_id = str(raw.get("conversationId") or "")
        payload.setdefault("_provenance", {})
        if isinstance(payload["_provenance"], dict):
            if conv_id:
                payload["_provenance"]["conversation_id"] = conv_id
            if is_classifier_uncertain:
                payload["_provenance"]["classifier_uncertain"] = True
        if is_classifier_uncertain:
            payload["is_classifier_uncertain"] = True
        payloads.append(payload)
    return "ok", payloads, body_for_ai


def process_single_message(
    raw: dict[str, Any],
    token: str,
    mailbox: str,
    settings: Settings,
    allocator: IdAllocator,
    store: ProcessedStore,
    skip_classifier: bool = False,
    sync_via_task: bool = False,
) -> int:
    """
    Process one raw Graph message through filter + AI + single-storage identity pipeline.
    Returns number of synced requirement rows for this message.
    """
    gid = raw.get("id")
    if not gid:
        return 0
    bind_log_context(message_id=gid)
    inet_id = str(raw.get("internetMessageId") or "").strip()

    # Step 1: Check if message already finalized or seen
    if store.pipeline_should_skip(gid, inet_id):
        _LOG.debug("Skip already finalized message %s", gid)
        clear_log_context()
        return 0

    # Cutoff guard: never process mail older than the ingest cutoff
    if settings.ingest_start_datetime:
        recv_str = str(raw.get("receivedDateTime") or "")
        if recv_str:
            try:
                msg_dt = _parse_to_utc_dt(recv_str)
                cutoff_dt = _parse_to_utc_dt(settings.ingest_start_datetime)
                if msg_dt < cutoff_dt:
                    _LOG.info("Skip message %s older than cutoff (%s < %s)", gid, recv_str, settings.ingest_start_datetime)
                    store.mark_message_seen(gid, inet_id, str(raw.get("subject") or ""), source="cutoff_skip")
                    clear_log_context()
                    return 0
            except Exception:
                pass

    store.pipeline_mark_processing(gid, "pipeline_processing")

    from_obj = raw.get("from") or {}
    ea = (from_obj.get("emailAddress") or {}) if isinstance(from_obj, dict) else {}
    fe = (ea.get("address") or "").strip()

    if not is_sender_allowlisted(fe):
        _LOG.info("SKIP %s: sender_not_allowlisted (%s)", gid, fe)
        store.pipeline_mark_skipped(gid, "sender_not_allowlisted")
        store.mark_message_seen(gid, inet_id, str(raw.get("subject") or ""), source="skipped")
        store.record_email_disposition(
            message_id=gid,
            graph_id=gid,
            internet_message_id=inet_id,
            subject=str(raw.get("subject") or ""),
            from_email=fe,
            received_date_time=str(raw.get("receivedDateTime") or ""),
            disposition="filtered",
            reason="sender_not_allowlisted",
        )
        store.log_filtered(
            graph_id=gid,
            subject=str(raw.get("subject") or ""),
            from_email=fe,
            reason="sender_not_allowlisted",
            stage="allowlist",
        )
        clear_log_context()
        return 0

    # Step 2: Extract requirements without burning REQ IDs
    status, payloads, body_for_ai = extract_and_map(
        raw,
        token=token,
        mailbox=mailbox,
        settings=settings,
        allocator=None,
        skip_classifier=skip_classifier,
    )
    if status != "ok":
        _LOG.info("SKIP %s: %s", gid, status)
        store.pipeline_mark_skipped(gid, status)
        store.mark_message_seen(gid, inet_id, str(raw.get("subject") or ""), source="skipped")

        subj = str(raw.get("subject") or "")
        fe = ""
        from_dict = raw.get("from")
        if isinstance(from_dict, dict) and "emailAddress" in from_dict:
            fe = str(from_dict["emailAddress"].get("address") or "")

        disp = "filtered" if status.startswith("filter:") else ("not_a_requirement" if status in ("ai_classifier_no", "no_requirement_structure_in_body") else "failed")
        store.record_email_disposition(
            message_id=gid,
            graph_id=gid,
            internet_message_id=inet_id,
            subject=subj,
            from_email=fe,
            received_date_time=str(raw.get("receivedDateTime") or ""),
            disposition=disp,
            reason=status,
        )

        if status.startswith("filter:"):
            reason = status.split("filter:", 1)[1]
            stage = (
                "junk_detector"
                if reason in {"promotional_email", "job_seeker_self_application", "popup_notification"}
                else "email_filter"
            )
            store.log_filtered(graph_id=gid, subject=subj, from_email=fe, reason=reason, stage=stage)
        elif status == "ai_classifier_no":
            store.log_filtered(graph_id=gid, subject=subj, from_email=fe, reason="ai_classifier_no", stage="classifier")

        clear_log_context()
        return 0

    # Step 3: Inside one email: compare all extracted requirements with each other using W3-W4 first;
    # keep one of each identical group. Rows that differ in city or client ID stay separate (W6).
    unique_payloads: list[dict[str, Any]] = []
    accepted_profiles: list[dict[str, Any]] = []

    rules_cfg = {
        "similarity_weights": getattr(settings, "similarity_weights", None) if settings else None,
        "similarity_thresholds": getattr(settings, "similarity_thresholds", None) if settings else None,
    }

    raw_body_text = str(raw.get("bodyNormalized") or (raw.get("body") or {}).get("content") or "")

    for payload in payloads:
        cjd = clean_client_jd_id(payload.get("client_jd_id"))
        client = normalize_client_key(payload.get("requirement_from") or payload.get("client_key") or "unknown")
        body_text = str(payload.get("bodyText") or raw_body_text or "")
        prof = build_requirement_profile(payload, body_text=body_text)

        is_intra_dup = False
        for acc_p in accepted_profiles:
            dec, score, rule = compare_requirements(prof, acc_p, rules_config=rules_cfg)
            if dec == "DUPLICATE":
                _LOG.info(
                    "Collapsed intra-email duplicate requirement (score=%.2f, rule=%s): client=%s, title=%s, city=%s",
                    score, rule, prof["client"], prof["title"], prof["city"]
                )
                is_intra_dup = True
                break

        if not is_intra_dup:
            ident = compute_requirement_identity(
                client=client,
                client_jd_id=cjd,
                job_title=payload.get("job_title"),
                location=payload.get("location"),
                experience=payload.get("overall_experience") or payload.get("experience_level"),
                mandatory_skills=payload.get("mandatory_skills"),
            )
            payload["identity"] = ident
            payload["_profile"] = prof
            accepted_profiles.append(prof)
            unique_payloads.append(payload)

    payloads = unique_payloads

    recv_raw = str(raw.get("receivedDateTime") or "").strip()
    recv_date = date.today()
    if recv_raw:
        try:
            recv_date = date.fromisoformat(recv_raw[:10])
        except ValueError:
            recv_date = date.today()

    # R4: Sort by first_arrival_at ascending, then by position in email
    for idx, p in enumerate(payloads):
        p.setdefault("_email_position", idx)
        if not p.get("first_arrival_at"):
            p["first_arrival_at"] = p.get("receivedDateTime") or p.get("email_received_iso") or recv_raw

    payloads.sort(key=lambda p: (
        _parse_to_utc_dt(p.get("first_arrival_at") or p.get("receivedDateTime") or ""),
        p.get("_email_position", 0),
    ))

    synced_for_message = 0
    pending_review_count = 0
    try:
        for payload in payloads:
            # P1: autofill from history is prohibited under strict field mapping
            if not is_strict_field_mapping():
                payload = autofill_from_history(payload, store)
            ident = payload["identity"]
            cjd = clean_client_jd_id(payload.get("client_jd_id"))
            client = normalize_client_key(payload.get("requirement_from") or payload.get("client_key") or "unknown")
            body_text = str(payload.get("bodyText") or raw_body_text or "")
            prof = payload.get("_profile") or build_requirement_profile(payload, body_text=body_text)
            city = prof.get("city")

            title = str(payload.get("job_title") or "").strip().lower()
            location = str(payload.get("location") or "").strip().lower()
            key_seed = f"{gid}|{title}|{location}"
            payload["idempotencyKey"] = hashlib.sha256(key_seed.encode("utf-8")).hexdigest()
            payload["graphMessageId"] = gid
            if inet_id:
                payload["internetMessageId"] = inet_id
                payload.setdefault("_provenance", {})
                if isinstance(payload["_provenance"], dict):
                    payload["_provenance"]["internet_message_id"] = inet_id
                    payload["_provenance"]["graph_message_id"] = gid

            with store.atomic_claim():
                # Step 4: Candidate deduplication check inside atomic claim (W1-W5, W8)
                decision, matched_cand, score, deciding_rule = store.find_requirement_duplicate(
                    prof, rules_config=rules_cfg
                )

                if decision == "DUPLICATE" and matched_cand:
                    matched_id = matched_cand.get("identity") or matched_cand.get("original_record_ref") or ident
                    _LOG.info(
                        "DUPLICATE requirement detected for %s (score=%.2f, rule=%s, matched=%s)",
                        ident, score, deciding_rule, matched_id
                    )
                    store.log_duplicate_decision(
                        source_email_id=gid,
                        matched_requirement_id=matched_id,
                        score=score,
                        deciding_rule=deciding_rule,
                        decision=decision,
                    )
                    store.update_identity_seen(matched_cand["identity"], graph_id=gid, seen_at=recv_raw)

                    # Check if email carries a status phrase (hold / reopen / closed) via whole-phrase match (W7)
                    email_status = payload.get("job_status") or payload.get("raw_status")
                    subj_body = (str(raw.get("subject") or "") + " " + body_text).lower()
                    status_to_update = None
                    if email_status and str(email_status).lower() in ("hold", "on hold", "on-hold", "reopen", "re-open", "closed", "active"):
                        st_raw = str(email_status).lower()
                        status_to_update = "hold" if "hold" in st_raw else ("open" if "reopen" in st_raw or "active" in st_raw else "closed")
                    elif re.search(r"\b(?:on\s+hold|hold|put\s+on\s+hold)\b", subj_body):
                        status_to_update = "hold"
                    elif re.search(r"\b(?:reopened?|re-opened?|active)\b", subj_body):
                        status_to_update = "open"
                    elif re.search(r"\b(?:closed?)\b", subj_body):
                        status_to_update = "closed"

                    target_ref = matched_cand.get("original_record_ref") or matched_cand.get("client_jd_id") or matched_cand["identity"]
                    if status_to_update:
                        payload["job_status"] = status_to_update
                        payload["requirement_status"] = status_to_update
                        store.update_requirement_status(
                            requirement_id=target_ref,
                            new_status=status_to_update,
                            source_email_id=gid,
                            changed_by="RULE_ENGINE",
                        )

                    # In-place modification: update existing requirement with new/modified fields
                    store.update_requirement_fields_in_place(
                        requirement_id=target_ref,
                        incoming_payload=payload,
                        source_email_id=gid,
                    )
                    continue

                if decision == "POSSIBLE_DUPLICATE" and matched_cand:
                    matched_id = matched_cand.get("identity") or matched_cand.get("original_record_ref") or ident
                    _LOG.info(
                        "POSSIBLE DUPLICATE requirement detected for %s (score=%.2f, rule=%s, matched=%s)",
                        ident, score, deciding_rule, matched_id
                    )
                    store.log_duplicate_decision(
                        source_email_id=gid,
                        matched_requirement_id=matched_id,
                        score=score,
                        deciding_rule=deciding_rule,
                        decision=decision,
                    )
                    store.register_requirement_identity(
                        identity=ident,
                        client=client,
                        client_jd_id=cjd,
                        city=city,
                        profile=prof,
                        state="pending_review",
                        original_record_ref=matched_cand.get("original_record_ref") or matched_id,
                        graph_id=gid,
                        seen_at=recv_raw,
                    )
                    store.add_pending_review(
                        graph_id=gid,
                        job_id="",
                        client_jd_id=str(cjd or ""),
                        payload_json=json.dumps(payload, ensure_ascii=False),
                        review_fields=f"possible_duplicate:{score:.2f}",
                        identity=ident,
                        possible_duplicate_of=matched_cand.get("original_record_ref") or matched_id,
                    )
                    store.pipeline_mark_pending_review(gid, detail=f"possible_duplicate:{score:.2f}")
                    pending_review_count += 1
                    continue

                # Step 5: Validate before save and check readiness (A1, M9, P9)
                payload, should_route_review, review_reason = validate_requirement_before_save(
                    payload,
                    block_text=body_for_ai,
                    client=client,
                )
                readiness = check_ui_readiness(payload)
                is_ready = readiness.get("is_ready_for_auto_sync", False) and not should_route_review
                is_uncertain = bool(payload.get("is_classifier_uncertain"))

                if not is_ready or is_uncertain:
                    rev_fields = list(readiness.get("review_fields", []))
                    if review_reason and review_reason not in rev_fields:
                        rev_fields.append(review_reason)
                    review_fields_str = ",".join(rev_fields)
                    store.register_requirement_identity(
                        identity=ident,
                        client=client,
                        client_jd_id=cjd,
                        city=city,
                        profile=prof,
                        state="pending_review",
                        original_record_ref=f"pending:{gid}",
                        graph_id=gid,
                        seen_at=recv_raw,
                    )
                    store.add_pending_review(
                        graph_id=gid,
                        job_id="",
                        client_jd_id=str(cjd or ""),
                        payload_json=json.dumps(payload, ensure_ascii=False),
                        review_fields=review_fields_str,
                        identity=ident,
                    )
                    store.pipeline_mark_pending_review(gid, detail=review_fields_str)
                    _LOG.info(
                        "Routed message %s (identity=%s) to pending_review (review_fields=%r)",
                        gid,
                        ident,
                        review_fields_str,
                    )
                    pending_review_count += 1
                    continue

                # Ready to store! REQ number assigned inside transaction at insert time (R1, R3)
                if sync_via_task:
                    payload.setdefault("_provenance", {})
                    if isinstance(payload["_provenance"], dict):
                        payload["_provenance"]["queued_sync_total"] = len(payloads)
                    from tasks import sync_metaforge_payload_task

                    sync_metaforge_payload_task.delay(payload)
                    job_id = payload.get("job_id", "")
                else:
                    # Allocate atomically inside _sqlite_upsert transaction (R1, R2)
                    job_id = send_to_metaforge(payload, settings)
                    if not job_id:
                        job_id = payload.get("job_id", "")
                    payload["job_id"] = job_id

                store.register_requirement_identity(
                    identity=ident,
                    client=client,
                    client_jd_id=cjd,
                    city=city,
                    profile=prof,
                    state="stored",
                    original_record_ref=job_id,
                    graph_id=gid,
                    seen_at=recv_raw,
                )

                if cjd:
                    store.evaluate_client_requirement_action(
                        client_jd_id=cjd,
                        requirement_from=payload.get("requirement_from") or client,
                        payload=payload,
                    )

                store.add_requirement_fingerprint(
                    graph_id=gid,
                    requirement_from=str(payload.get("requirement_from") or ""),
                    job_title=str(payload.get("job_title") or ""),
                    location=str(payload.get("location") or ""),
                    budget_period=("monthly" if payload.get("monthly_budget") else "yearly"),
                )
                try:
                    store.add_requirement_memory(
                        requirement_from=str(payload.get("requirement_from") or ""),
                        job_title=str(payload.get("job_title") or ""),
                        payload_json=json.dumps(payload, ensure_ascii=False),
                        source_graph_id=str(gid),
                    )
                except Exception as mem_exc:
                    _LOG.warning("Failed to persist requirement memory: %s", mem_exc)
                synced_for_message += 1

                # Post-save verification (V4)
                if is_strict_field_mapping():
                    from two_way_verifier import verify_stored_requirement
                    v_status, failed_fields = verify_stored_requirement(payload, body_text)
                    payload["verification_status"] = v_status
                    if v_status == "failed":
                        _LOG.warning("Post-save verification failed for %s on %s", payload.get("job_id"), failed_fields)

    except Exception as exc:
        _LOG.exception("MetaForge sync failed for message %s: %s", gid, exc)
        store.record_email_disposition(
            message_id=gid,
            graph_id=gid,
            internet_message_id=inet_id,
            subject=str(raw.get("subject") or ""),
            from_email=fe,
            received_date_time=recv_raw,
            disposition="failed",
            reason=str(exc),
        )
        clear_log_context()
        return 0

    # Record disposition ledger row (N1) before advancing watermark (S4)
    disp_final = "extracted" if synced_for_message > 0 else ("pending_review" if pending_review_count > 0 else "duplicate")
    store.record_email_disposition(
        message_id=gid,
        graph_id=gid,
        internet_message_id=inet_id,
        subject=str(raw.get("subject") or ""),
        from_email=fe,
        received_date_time=recv_raw,
        disposition=disp_final,
        requirements_count=synced_for_message,
    )

    # Mark message seen in seen_messages and update watermark (S4)
    store.mark_message_seen(gid, inet_id, str(raw.get("subject") or ""), source="pipeline")
    if recv_raw:
        cur_wm = store.get_watermark()
        if not cur_wm or recv_raw > cur_wm:
            store.set_watermark(recv_raw)

    if pending_review_count > 0 and synced_for_message == 0:
        _LOG.info("OK %s: %s requirement row(s) routed to pending_review", gid, pending_review_count)
        clear_log_context()
        return 0

    if sync_via_task:
        store.pipeline_mark_pending_sync(gid, f"queued_sync_rows={synced_for_message}")
        _LOG.info("OK %s: queued %s requirement row(s) for sync", gid, synced_for_message)
    else:
        store.pipeline_mark_synced(gid, f"requirements={synced_for_message}")
        _LOG.info("OK %s: synced %s requirement row(s)", gid, synced_for_message)
    clear_log_context()
    return synced_for_message


def run_pipeline(args: argparse.Namespace, settings: Settings) -> int:
    try:
        token = acquire_token_from_env()
    except RuntimeError as e:
        _LOG.error("%s", e)
        return 1

    id_db = (
        settings.metaforge_sqlite_path
        if settings.metaforge_mode == "sqlite"
        else settings.metaforge_id_db
    )
    allocator = IdAllocator(id_db)

    mailbox = args.mailbox or settings.mailbox_upn
    processed = 0
    synced = 0

    try:
        with ProcessedStore(settings.processed_db) as store:
            min_recv = get_effective_cutoff_iso(settings, store)
            today_filter = getattr(args, "today", False) or os.getenv("EXTRACT_TODAY_ONLY", "").lower() in ("true", "1", "yes")
            today_str = ""
            if today_filter:
                from datetime import date
                today_str = date.today().isoformat()
                min_recv = f"{today_str}T00:00:00Z"
                _LOG.info("Ingest cutoff set to today only: min_received_time=%s", min_recv)
            elif getattr(args, "since", None):
                min_recv = str(args.since)
                _LOG.info("Ingest cutoff overridden: min_received_time=%s", min_recv)
            else:
                _LOG.info("Ingest cutoff filter: min_received_time=%s", min_recv)
            for raw in iter_inbox_messages(
                token,
                mailbox,
                limit=args.limit,
                min_received_time=min_recv,
                orderby="receivedDateTime asc",
            ):
                if today_filter and today_str:
                    recv_val = str(raw.get("receivedDateTime") or "")
                    if recv_val and not recv_val.startswith(today_str):
                        continue
                processed += 1
                synced += process_single_message(
                    raw,
                    token=token,
                    mailbox=mailbox,
                    settings=settings,
                    allocator=allocator,
                    store=store,
                )
    finally:
        allocator.close()

    _LOG.info("Pipeline finished: examined=%s total rows synced=%s", processed, synced)
    
    # SQLite to CSV/JSON Sync: Always generate final consolidated CSV
    try:
        import csv
        import json
        from datetime import date
        
        today = date.today().strftime('%Y-%m-%d')
        csv_filename = f"metaforge_consolidated_{today}.csv"
        json_filename = f"metaforge_consolidated_{today}.json"
        
        # Generate CSV from SQLite
        if settings.metaforge_mode == "sqlite":
            import sqlite3
            conn = sqlite3.connect(settings.metaforge_sqlite_path)
            
            # Get all data from SQLite
            cursor = conn.execute("SELECT * FROM metaforge_requirements ORDER BY created_at DESC")
            rows = cursor.fetchall()
            columns = [description[0] for description in cursor.description]
            
            # Write to CSV
            with open(csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(columns)
                writer.writerows(rows)
            
            # Write to JSON
            data = []
            for row in rows:
                data.append(dict(zip(columns, row)))
            
            with open(json_filename, 'w', encoding='utf-8') as jsonfile:
                json.dump(data, jsonfile, indent=2, ensure_ascii=False)
            
            conn.close()
            
            _LOG.info("Generated consolidated files: %s, %s with %d rows", csv_filename, json_filename, len(rows))
        else:
            _LOG.info("MetaForge API mode detected - skipping local CSV/JSON generation")
            
    except Exception as e:
        _LOG.error("Failed to generate consolidated CSV/JSON: %s", e)
    
    return 0


def retry_pending_sync_batch(settings: Settings, store: ProcessedStore, *, limit: int = 3) -> int:
    """Re-post stored payloads stuck in pending_sync. API dedupes; skips if already ingested."""
    import json

    from metaforge_api import send_to_metaforge

    synced = 0
    for graph_id, payload_json in store.pipeline_pending_sync_with_memory(limit=limit):
        try:
            payload = json.loads(payload_json)
        except json.JSONDecodeError:
            _LOG.warning("pending_sync retry skipped invalid JSON for %s", graph_id[:40])
            continue
        try:
            send_to_metaforge(payload, settings)
            store.pipeline_mark_synced(graph_id, "scheduler_retry_pending_sync")
            synced += 1
        except Exception as exc:
            _LOG.warning("pending_sync retry failed for %s: %s", graph_id[:40], exc)
    if synced:
        _LOG.info("Retried pending_sync payloads: synced=%s", synced)
    return synced


def enqueue_pipeline(args: argparse.Namespace, settings: Settings) -> int:
    """
    Producer mode: queue message IDs into Celery for asynchronous worker processing.
    """
    try:
        from tasks import classify_email_task
    except Exception as exc:
        _LOG.error("Celery tasks import failed: %s", exc)
        return 1

    try:
        token = acquire_token_from_env()
    except RuntimeError as e:
        _LOG.error("%s", e)
        return 1

    mailbox = args.mailbox or settings.mailbox_upn
    queued = 0
    examined = 0
    with ProcessedStore(settings.processed_db) as store:
        stale = store.pipeline_clear_stale_inflight(max_age_seconds=1800)
        if stale:
            _LOG.info("Cleared stale inflight pipeline rows: %s", stale)
        for raw in iter_inbox_messages(token, mailbox, limit=args.limit):
            examined += 1
            gid = str(raw.get("id") or "").strip()
            if not gid:
                continue
            if store.pipeline_should_skip(gid):
                continue
            state = store.pipeline_get_state(gid)
            if state in {"queued", "processing"}:
                continue
            classify_email_task.delay(gid, mailbox)
            store.pipeline_mark_queued(gid, "queued_by_producer")
            queued += 1

    _LOG.info("Enqueue finished: examined=%s queued=%s", examined, queued)
    return 0


def _build_raw_from_file(path: Path) -> tuple[str, dict[str, Any]]:
    payload: dict[str, Any]
    text = path.read_text(encoding="utf-8", errors="ignore")
    if path.suffix.lower() == ".json":
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                payload = obj
            else:
                payload = {"body": text}
        except Exception:
            payload = {"body": text}
    else:
        payload = {"body": text}

    subject = str(payload.get("subject") or path.stem).strip() or "Requirement mail"
    from_email = str(payload.get("from_email") or payload.get("from_address") or payload.get("from") or "unknown@local").strip()
    from_name = str(payload.get("from_name") or "").strip()
    body_text = str(payload.get("body") or payload.get("content") or text)
    file_event_id = str(
        payload.get("message_id")
        or payload.get("graph_id")
        or f"file:{hashlib.sha256(text.encode('utf-8')).hexdigest()[:24]}"
    )

    raw = {
        "id": file_event_id,
        "subject": subject,
        "from": {
            "emailAddress": {
                "address": from_email,
                "name": from_name,
            }
        },
        "body": {"contentType": "text", "content": body_text},
        "hasAttachments": False,
        "receivedDateTime": payload.get("receivedDateTime") or datetime.now(timezone.utc).isoformat(),
    }
    return file_event_id, raw


def run_file_listener_cycle(settings: Settings, store: ProcessedStore | None = None) -> int:
    inbox = Path(settings.file_listener_inbox_dir)
    archive = Path(settings.file_listener_archive_dir)
    inbox.mkdir(parents=True, exist_ok=True)
    archive.mkdir(parents=True, exist_ok=True)

    files = sorted([p for p in inbox.glob("*") if p.is_file()])
    if not files:
        return 0

    id_db = settings.metaforge_sqlite_path if settings.metaforge_mode == "sqlite" else settings.metaforge_id_db
    allocator = IdAllocator(id_db)
    processed_count = 0
    close_store_on_exit = False
    if store is None:
        store = ProcessedStore(settings.processed_db)
        close_store_on_exit = True
    try:
        for f in files:
            fp = hashlib.sha256(f"{f.resolve()}|{f.stat().st_size}|{f.stat().st_mtime}".encode("utf-8")).hexdigest()
            if store.is_file_event_processed(fp):
                continue
            try:
                gid, raw = _build_raw_from_file(f)
                bind_log_context(message_id=gid, source="file_listener")
                synced_rows = process_single_message(
                    raw,
                    token="",
                    mailbox=settings.mailbox_upn,
                    settings=settings,
                    allocator=allocator,
                    store=store,
                    skip_classifier=False,
                    sync_via_task=(getattr(settings, "scheduler_mode", "inline").lower() == "celery"),
                )
                store.mark_file_event_processed(fingerprint=fp, file_path=str(f))
                processed_count += 1
                archived_name = f"{f.stem}.{int(time.time())}{f.suffix}"
                shutil.move(str(f), str(archive / archived_name))
                _LOG.info("File listener processed=%s synced_rows=%s", f.name, synced_rows)
            except Exception as exc:
                _LOG.exception("File listener failed for %s: %s", f, exc)
            finally:
                clear_log_context()
    finally:
        if close_store_on_exit:
            store.close()
        allocator.close()

    return processed_count


def _write_scheduler_heartbeat(
    path: str,
    *,
    status: str,
    details: dict[str, Any] | None = None,
) -> None:
    try:
        parent = os.path.dirname(os.path.abspath(path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        payload: dict[str, Any] = {
            "status": status,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }
        if details:
            payload.update(details)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        _LOG.warning("Failed to write scheduler heartbeat file: %s", exc)


def run_scheduler_preflight(settings: Settings) -> None:
    """Preflight check on scheduler start: env values, Graph token, mailbox readable, DB paths writable."""
    if not (settings.azure_tenant_id and settings.azure_client_id and settings.azure_client_secret):
        print("PREFLIGHT FAILED: Azure credentials missing in environment", file=sys.stderr)
        sys.exit(1)
    if not settings.mailbox_upn:
        print("PREFLIGHT FAILED: Mailbox UPN missing in environment", file=sys.stderr)
        sys.exit(1)
    if not (settings.openai_api_key or os.getenv("GEMINI_API_KEY")):
        print("PREFLIGHT FAILED: OpenAI / Gemini API key missing in environment", file=sys.stderr)
        sys.exit(1)

    try:
        token = acquire_token_from_env()
        if not token:
            raise ValueError("Token is empty")
    except Exception as exc:
        print(f"PREFLIGHT FAILED: Failed to acquire Graph token: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        _ = next(iter_inbox_messages(token, settings.mailbox_upn, limit=1), None)
    except Exception as exc:
        print(f"PREFLIGHT FAILED: Mailbox {settings.mailbox_upn} not readable: {exc}", file=sys.stderr)
        sys.exit(1)

    for db_path in (settings.processed_db, settings.metaforge_sqlite_path):
        p = Path(db_path)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            test_f = p.parent / ".write_test"
            test_f.write_text("ok")
            test_f.unlink()
        except Exception as exc:
            print(f"PREFLIGHT FAILED: Database path {db_path} not writable: {exc}", file=sys.stderr)
            sys.exit(1)


def run_scheduler(args: argparse.Namespace, settings: Settings) -> int:
    """
    Fixed-rate 120s scheduler loop (S1-S6):
      - S1: SCHEDULER_POLL_SECONDS = 120. Next tick is tick_start + 120s.
      - S2: Single run at a time (lock). Skip tick and log if lock is active.
      - S3: Fetch with receivedDateTime ge (watermark - 5 minutes), ascending, follow @odata.nextLink.
      - S4: Advance watermark only after message has ledger row committed.
      - S5: Heartbeat row every tick (started_at, finished_at, fetched, extracted, failed).
      - S6: Handle token expiry and Graph throttling.
    """
    run_scheduler_preflight(settings)
    mode = getattr(settings, "scheduler_mode", "inline").lower()
    if mode == "celery":
        try:
            import redis
            r = redis.from_url(settings.celery_broker_url or "redis://localhost:6379/0", socket_timeout=1)
            r.ping()
        except Exception as exc:
            _LOG.warning("Redis unreachable, falling back from celery to inline mode: %s", exc)
            mode = "inline"

    poll_seconds = getattr(settings, "scheduler_poll_seconds", 120)
    max_cycles = args.max_cycles if args.max_cycles and args.max_cycles > 0 else None
    cycle = 0
    mailbox = args.mailbox or settings.mailbox_upn
    lock_file = Path("data/scheduler.lock")

    _LOG.info(
        "Scheduler started (fixed-rate): poll=%ss mailbox=%s heartbeat=%s mode=%s",
        poll_seconds,
        mailbox,
        settings.scheduler_heartbeat_path,
        mode,
    )

    while True:
        tick_start = time.time()
        started_at = datetime.now(timezone.utc).isoformat()
        cycle += 1

        # S2: Process Lock check — dead PID or lock older than 3 minutes is stale
        if lock_file.exists():
            try:
                lock_age = time.time() - lock_file.stat().st_mtime
                lock_content = lock_file.read_text()
                lock_pid: int | None = None
                pid_match = re.search(r"pid=(\d+)", lock_content)
                if pid_match:
                    lock_pid = int(pid_match.group(1))
                # Check if the PID is alive (Windows: tasklist)
                pid_alive = False
                if lock_pid is not None and lock_pid != os.getpid():
                    try:
                        import subprocess as _sp
                        result = _sp.run(
                            ["tasklist", "/FI", f"PID eq {lock_pid}", "/NH", "/FO", "CSV"],
                            capture_output=True, text=True, timeout=3
                        )
                        pid_alive = str(lock_pid) in result.stdout
                    except Exception:
                        # If we can't check, assume alive if lock is fresh
                        pid_alive = lock_age < 180
                is_stale = (not pid_alive) or (lock_age > 180)
                if not is_stale:
                    _LOG.warning(
                        "Scheduler run already in progress (pid=%s lock age %.1fs); skipping tick per S2.",
                        lock_pid, lock_age
                    )
                    elapsed = time.time() - tick_start
                    sleep_time = max(0.0, poll_seconds - elapsed)
                    time.sleep(sleep_time)
                    continue
                else:
                    _LOG.warning(
                        "Stale lock detected (pid=%s age=%.1fs alive=%s); removing and proceeding.",
                        lock_pid, lock_age, pid_alive
                    )
                    lock_file.unlink(missing_ok=True)
            except Exception:
                lock_file.unlink(missing_ok=True)

        try:
            lock_file.parent.mkdir(parents=True, exist_ok=True)
            lock_file.write_text(f"pid={os.getpid()}; started={started_at}")
        except Exception:
            pass

        fetched_count = 0
        extracted_count = 0
        failed_count = 0
        status_str = "ok"
        err_msg = None

        try:
            with ProcessedStore(settings.processed_db) as store:
                # S3: Watermark minus 5 minutes, ascending order
                wm = store.get_watermark()
                min_recv_time = None
                if wm:
                    try:
                        wm_dt = _parse_to_utc_dt(wm) - timedelta(minutes=5)
                        min_recv_time = wm_dt.isoformat()
                    except Exception:
                        min_recv_time = None

                id_db = settings.metaforge_sqlite_path if settings.metaforge_mode == "sqlite" else settings.metaforge_id_db
                allocator = IdAllocator(id_db)
                try:
                    token = acquire_token_from_env()
                except Exception as e:
                    token = ""
                    _LOG.warning("Graph token acquisition failed: %s", e)

                fetched_ids = []
                if token:
                    for raw in iter_inbox_messages(
                        token,
                        mailbox,
                        limit=args.limit,
                        min_received_time=min_recv_time,
                        orderby="receivedDateTime asc",
                    ):
                        gid = raw.get("id")
                        if not gid:
                            continue
                        fetched_ids.append(gid)
                        fetched_count += 1
                        try:
                            synced = process_single_message(
                                raw,
                                token=token,
                                mailbox=mailbox,
                                settings=settings,
                                allocator=allocator,
                                store=store,
                                skip_classifier=False,
                                sync_via_task=False,
                            )
                            extracted_count += synced
                        except Exception as p_exc:
                            failed_count += 1
                            _LOG.exception("Message processing error: %s", p_exc)

                # N1: Reconcile disposition ledger
                reconciled, missing_cnt, missing_ids = store.reconcile_disposition_ledger(fetched_ids)
                if not reconciled:
                    _LOG.error("Disposition ledger gap: %d messages missing ledger rows: %s", missing_cnt, missing_ids)

                if cycle % 5 == 0:
                    retry_pending_sync_batch(settings, store, limit=3)
                if settings.file_listener_enabled:
                    run_file_listener_cycle(settings, store=store)
                if getattr(settings, "accuracy_monitor_enabled", True) and cycle % getattr(settings, "accuracy_monitor_cycle_interval", 30) == 0:
                    try:
                        from accuracy_monitor import run_accuracy_audit_cycle
                        run_accuracy_audit_cycle(settings, store, limit=getattr(settings, "accuracy_monitor_sample_limit", 30))
                    except Exception as a_exc:
                        _LOG.warning("Periodic accuracy audit cycle failed: %s", a_exc)

                finished_at = datetime.now(timezone.utc).isoformat()
                store.record_scheduler_heartbeat(
                    started_at=started_at,
                    finished_at=finished_at,
                    fetched=fetched_count,
                    extracted=extracted_count,
                    failed=failed_count,
                    status=status_str,
                    error_message=err_msg,
                )
                _write_scheduler_heartbeat(
                    settings.scheduler_heartbeat_path,
                    status="running",
                    details={
                        "cycle": cycle,
                        "started_at": started_at,
                        "finished_at": finished_at,
                        "fetched": fetched_count,
                        "extracted": extracted_count,
                        "failed": failed_count,
                    },
                )
                duration = time.time() - tick_start
                try:
                    log_file = Path("logs/scheduler.log")
                    log_file.parent.mkdir(parents=True, exist_ok=True)
                    with open(log_file, "a", encoding="utf-8") as f:
                        f.write(f"Tick {cycle:04d} | Start: {started_at} | Fetched: {fetched_count} | Processed: {extracted_count} | Failed: {failed_count} | Duration: {duration:.2f}s\n")
                except Exception as l_exc:
                    _LOG.warning("Failed to write to logs/scheduler.log: %s", l_exc)
        except Exception as exc:
            status_str = "degraded"
            err_msg = str(exc)
            _LOG.exception("Scheduler cycle failed: %s", exc)
            finished_at = datetime.now(timezone.utc).isoformat()
            try:
                with ProcessedStore(settings.processed_db) as store:
                    store.record_scheduler_heartbeat(
                        started_at=started_at,
                        finished_at=finished_at,
                        fetched=fetched_count,
                        extracted=extracted_count,
                        failed=failed_count,
                        status="degraded",
                        error_message=str(exc),
                    )
            except Exception:
                pass
        finally:
            if lock_file.exists():
                try:
                    lock_file.unlink()
                except Exception:
                    pass

        if max_cycles is not None and cycle >= max_cycles:
            break

        # S1: Fixed-rate: next tick is tick_start + 120s
        elapsed = time.time() - tick_start
        sleep_time = poll_seconds - elapsed
        if sleep_time < 0:
            skip_cnt = int(abs(sleep_time) // poll_seconds) + 1
            next_sleep = poll_seconds - (abs(sleep_time) % poll_seconds)
            _LOG.warning("Scheduler tick overrun by %.2fs; skipping %d tick(s)", abs(sleep_time), skip_cnt)
            time.sleep(next_sleep)
        else:
            _LOG.info("Scheduler tick cycle %s took %.2fs; sleeping %.2fs until next tick", cycle, elapsed, sleep_time)
            time.sleep(sleep_time)

    _LOG.info("Scheduler stopped after %s cycle(s)", cycle)
    return 0


def run_verify_times(args: argparse.Namespace, settings: Settings) -> int:
    """
    Verify arrival times across all stored requirements against Microsoft Graph.
    - Matches by graph id
    - For rows without Graph ID, searches by internetMessageId, then conversationId, then subject + sender within one day.
    - Rows still unmatched show 'imported, time not verified'.
    Prints checked, matched, mismatched, unverifiable.
    """
    import sqlite3
    db_path = settings.metaforge_sqlite_path
    if not os.path.exists(db_path):
        print(f"Database not found: {db_path}")
        return 1

    try:
        token = acquire_token_from_env()
    except Exception as e:
        print(f"Graph token error: {e}")
        return 1

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT job_id, payload_json FROM metaforge_requirements")
    rows = c.fetchall()

    checked = 0
    matched = 0
    mismatches = 0
    unverifiable = 0

    print("=" * 80)
    print("VERIFY TIMES REPORT")
    print("=" * 80)

    msg_cache: dict[str, Any] = {}

    for r in rows:
        job_id = r["job_id"]
        try:
            payload = json.loads(r["payload_json"])
        except Exception:
            continue
        checked += 1
        gid = payload.get("graphMessageId") or payload.get("id")
        stored_fa = payload.get("first_arrival_at") or payload.get("receivedDateTime")

        raw = None
        if gid and not str(gid).startswith("file:"):
            if gid in msg_cache:
                raw = msg_cache[gid]
            else:
                try:
                    raw = fetch_message_by_id(token, settings.mailbox_upn, gid)
                    msg_cache[gid] = raw
                except Exception:
                    raw = None

        if not raw:
            inet_id = payload.get("internetMessageId")
            if inet_id:
                try:
                    import requests
                    from outlook_graph import GRAPH, _encode_user
                    url = f"{GRAPH}/users/{_encode_user(settings.mailbox_upn)}/mailFolders/inbox/messages?$filter=internetMessageId eq '{inet_id}'&$top=1"
                    resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=10)
                    val = resp.json().get("value", [])
                    if val:
                        raw = val[0]
                except Exception:
                    pass

        if not raw:
            conv_id = payload.get("conversationId")
            if conv_id:
                try:
                    import requests
                    from outlook_graph import GRAPH, _encode_user
                    url = f"{GRAPH}/users/{_encode_user(settings.mailbox_upn)}/mailFolders/inbox/messages?$filter=conversationId eq '{conv_id}'&$top=1"
                    resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=10)
                    val = resp.json().get("value", [])
                    if val:
                        raw = val[0]
                except Exception:
                    pass

        if raw:
            graph_fa = raw.get("receivedDateTime")
            if stored_fa:
                s_dt = _parse_to_utc_dt(stored_fa)
                g_dt = _parse_to_utc_dt(graph_fa)
                if s_dt == g_dt:
                    matched += 1
                else:
                    mismatches += 1
                    print(f"MISMATCH for {job_id}: stored='{stored_fa}' vs graph='{graph_fa}'")
            else:
                payload["first_arrival_at"] = graph_fa
                c.execute("UPDATE metaforge_requirements SET payload_json = ? WHERE job_id = ?", (json.dumps(payload), job_id))
                matched += 1
        else:
            unverifiable += 1
            payload["time_verified"] = False
            payload["time_status"] = "imported, time not verified"
            c.execute("UPDATE metaforge_requirements SET payload_json = ? WHERE job_id = ?", (json.dumps(payload), job_id))

    conn.commit()
    conn.close()
    print(f"Checked: {checked}, Matched: {matched}, Mismatches: {mismatches}, Unverifiable: {unverifiable}")
    return 0


def _add_dump_args(p: argparse.ArgumentParser) -> None:
    import os

    p.add_argument("--format", choices=("json", "csv", "sqlite"), default="json")
    p.add_argument("--body-mode", choices=("normalized", "full"), default="normalized")
    p.add_argument("-o", "--output", default="extractions.json")
    p.add_argument(
        "--processed-db",
        default=os.getenv("PROCESSED_DB", "data/processed_messages.db"),
    )
    p.add_argument("--no-skip-processed", action="store_true")
    p.add_argument("--csv-body-full", action="store_true")


def run_baseline(args: argparse.Namespace, settings: Settings) -> int:
    """Mark every message currently in the inbox as seen without processing it."""
    try:
        token = acquire_token_from_env()
    except RuntimeError as e:
        _LOG.error("%s", e)
        return 1

    mailbox = args.mailbox or settings.mailbox_upn
    marked = 0
    with ProcessedStore(settings.processed_db) as store:
        for raw in iter_inbox_messages(token, mailbox, limit=args.limit, orderby="receivedDateTime asc"):
            gid = raw.get("id")
            if not gid:
                continue
            inet_id = str(raw.get("internetMessageId") or "").strip() or None
            subj = str(raw.get("subject") or "")
            recv_iso = str(raw.get("receivedDateTime") or "")
            store.mark_message_seen(gid, inet_id, subj, source="baseline")
            if recv_iso:
                cur_wm = store.get_watermark()
                if not cur_wm or recv_iso > cur_wm:
                    store.set_watermark(recv_iso)
            marked += 1
    _LOG.info("Baseline complete: marked %d messages as seen", marked)
    print(f"Baseline complete: marked {marked} messages as seen")
    return 0


def run_reprocess(args: argparse.Namespace, settings: Settings) -> int:
    import sqlite3
    from datetime import date, datetime, timezone
    from config import is_placeholder
    from requirement_parser import parse_requirements_from_email
    from boilerplate_learner import validate_skills
    from field_mapper import EmailContext, map_to_metaforge, _as_list
    from strict_validator import validate_requirement_before_save

    db_path = settings.metaforge_sqlite_path
    if not os.path.exists(db_path):
        print(f"Database not found: {db_path}")
        return 1

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    target_job_id = getattr(args, "job_id", None)
    if target_job_id:
        c.execute(
            "SELECT rowid, job_id, client_jd_id, payload_json FROM metaforge_requirements WHERE job_id = ? OR client_jd_id = ? LIMIT 1",
            (target_job_id, target_job_id),
        )
        rows = c.fetchall()
    else:
        limit = args.limit or 60
        c.execute(
            """SELECT rowid, job_id, client_jd_id, payload_json
               FROM metaforge_requirements
               ORDER BY coalesce(json_extract(payload_json, '$.first_arrival_at'),
                                 json_extract(payload_json, '$.receivedDateTime'),
                                 created_at, job_id) ASC
               LIMIT ?""",
            (limit,),
        )
        rows = c.fetchall()

    if not rows:
        print("No requirements found to reprocess.")
        conn.close()
        return 0

    print(f"Reprocessing {len(rows)} requirement(s)...")

    reprocessed_count = 0
    for r in rows:
        job_id = r["job_id"]
        cjd_orig = r["client_jd_id"]
        try:
            payload = json.loads(r["payload_json"])
            orig_payload = json.loads(r["payload_json"])
        except Exception:
            continue

        source_text = (
            payload.get("bodyText")
            or payload.get("body")
            or payload.get("raw_body")
            or payload.get("source_text")
            or payload.get("email_body")
            or ""
        )
        subj = payload.get("subject") or payload.get("email_subject") or ""
        client_name = payload.get("requirement_from") or payload.get("client_name") or payload.get("client") or ""
        arrival_time = payload.get("first_arrival_at") or payload.get("receivedDateTime")
        status = payload.get("status") or payload.get("job_status")
        cjd = payload.get("client_jd_id") or cjd_orig
        from_email = str(
            payload.get("from")
            or payload.get("client_lead_poc")
            or payload.get("sender_email")
            or ""
        ).strip()

        if source_text:
            parse_res = parse_requirements_from_email(
                subject=subj,
                body=source_text,
                settings=settings,
                from_email=from_email,
            )
            if parse_res.requirements:
                matching_req = None
                if cjd:
                    for item in parse_res.requirements:
                        if (item.req_id and item.req_id.strip() == str(cjd).strip()) or (item.client_jd_id and item.client_jd_id.strip() == str(cjd).strip()):
                            matching_req = item
                            break
                new_req = matching_req or parse_res.requirements[0]

                ctx = EmailContext(
                    graph_message_id=str(payload.get("graphMessageId") or ""),
                    internet_message_id=str(payload.get("internetMessageId") or ""),
                    to_emails=_as_list(payload.get("to")),
                    cc_emails=_as_list(payload.get("cc")),
                    from_email=from_email,
                    from_name=str(payload.get("from_name") or from_email),
                )

                recv_date = date.today()
                if arrival_time:
                    try:
                        recv_date = date.fromisoformat(str(arrival_time)[:10])
                    except ValueError:
                        pass

                mapped_payload = map_to_metaforge(
                    extracted=new_req.model_dump(mode="json", by_alias=True),
                    ctx=ctx,
                    client_display_name=client_name,
                    job_id=job_id,
                    client_jd_id=cjd or new_req.req_id,
                    body_text=source_text,
                    demand_received_date=recv_date,
                    email_subject=subj,
                    email_body_plain=source_text,
                    email_body_html=payload.get("bodyHtml", ""),
                    email_received_iso=str(arrival_time or ""),
                )

                val_payload, should_route, reason = validate_requirement_before_save(
                    mapped_payload,
                    block_text=source_text,
                    client=client_name,
                )

                # Production Safe Merge Rule:
                # 1. Only replace a field when the current pipeline successfully extracts and validates a real source value.
                # 2. Never replace a valid existing value with None because a new extraction failed.
                # 3. Keep genuinely absent fields as None.
                # 4. Preserve raw source data.
                MERGE_FIELDS = [
                    "job_title", "number_of_positions", "overall_experience", "experience",
                    "overall_experience_min", "overall_experience_max",
                    "experience_text", "experience_level", "mandatory_skills", "skills",
                    "monthly_budget", "monthly_budget_min", "monthly_budget_max",
                    "yearly_budget", "yearly_budget_min", "yearly_budget_max",
                    "budget", "budget_text", "budget_currency",
                    "work_mode", "work_mode_text", "notice_period", "location", "priority"
                ]

                for f in MERGE_FIELDS:
                    new_val = val_payload.get(f)
                    if new_val is not None and not is_placeholder(new_val):
                        if isinstance(new_val, list):
                            if len(new_val) > 0:
                                payload[f] = new_val
                        elif isinstance(new_val, str):
                            if new_val.strip():
                                payload[f] = new_val.strip()
                        else:
                            payload[f] = new_val

                # When budget is successfully parsed/reconciled, sync all budget fields together
                if val_payload.get("budget_text") or val_payload.get("budget"):
                    payload["budget"] = val_payload.get("budget")
                    payload["budget_text"] = val_payload.get("budget_text")
                    payload["monthly_budget"] = val_payload.get("monthly_budget")
                    payload["monthly_budget_min"] = val_payload.get("monthly_budget_min")
                    payload["monthly_budget_max"] = val_payload.get("monthly_budget_max")
                    payload["yearly_budget"] = val_payload.get("yearly_budget")
                    payload["yearly_budget_min"] = val_payload.get("yearly_budget_min")
                    payload["yearly_budget_max"] = val_payload.get("yearly_budget_max")
                    payload["budget_currency"] = val_payload.get("budget_currency")

                if val_payload.get("confidence") is not None:
                    payload["confidence"] = val_payload["confidence"]
                if val_payload.get("validation_warnings"):
                    payload["validation_warnings"] = val_payload["validation_warnings"]
        else:
            # Fallback if no source_text is stored: validate skills to clear any table noise
            new_mand_skills = validate_skills(payload.get("mandatory_skills"), client=client_name)
            new_soft_skills = validate_skills(payload.get("skills"), client=client_name)
            payload["mandatory_skills"] = new_mand_skills
            payload["skills"] = new_soft_skills

        # Preserve immutable metadata
        payload["job_id"] = job_id
        if cjd:
            payload["client_jd_id"] = cjd
        if arrival_time:
            payload["first_arrival_at"] = arrival_time
        if status:
            payload["status"] = status
            payload["job_status"] = status

        is_dry_run = getattr(args, "dry_run", False)

        diff_fields = [
            "job_title", "number_of_positions", "overall_experience", "experience",
            "experience_level", "mandatory_skills", "skills",
            "monthly_budget", "yearly_budget", "budget", "budget_currency",
            "work_mode", "notice_period", "location", "priority"
        ]

        src_search = f"{subj}\n{source_text}"
        for f in diff_fields:
            old_val = orig_payload.get(f)
            new_val = payload.get(f)
            if old_val != new_val:
                val_str = str(new_val) if new_val is not None else ""
                if isinstance(new_val, list):
                    val_str = ", ".join(str(x) for x in new_val)

                ev_snippet = ""
                has_source_evidence = False
                if val_str:
                    val_tokens = [tok.strip().lower() for tok in re.split(r"[,;|\-\s/]+", val_str) if len(tok.strip()) >= 2]
                    matched_tokens = [tok for tok in val_tokens if tok in src_search.lower()]
                    has_source_evidence = bool(matched_tokens) or (val_str.lower() in src_search.lower())
                    for line in src_search.splitlines():
                        line_clean = line.strip()
                        if any(t in line_clean.lower() for t in matched_tokens) and len(line_clean) > 3:
                            ev_snippet = line_clean[:140]
                            break
                    if not ev_snippet and has_source_evidence:
                        ev_snippet = val_str[:120]

                if new_val is None or new_val == "" or new_val == []:
                    res_cat = "MISSING"
                elif not has_source_evidence:
                    res_cat = "FABRICATED"
                elif has_source_evidence:
                    res_cat = "SAFE"
                else:
                    res_cat = "AMBIGUOUS"

                safe_old = str(old_val).encode("ascii", errors="replace").decode("ascii") if old_val is not None else "None"
                safe_new = str(new_val).encode("ascii", errors="replace").decode("ascii") if new_val is not None else "None"
                safe_ev = str(ev_snippet or "(None found)").encode("ascii", errors="replace").decode("ascii")
                print("-" * 60)
                print(f"Requirement ID:   {job_id}")
                print(f"Field:            {f}")
                print(f"Current value:    {safe_old}")
                print(f"Proposed value:   {safe_new}")
                print(f"Source evidence:  {safe_ev}")
                print(f"Result:           {res_cat}")

        if is_dry_run:
            reprocessed_count += 1
            continue

        now_iso = datetime.now(timezone.utc).isoformat()
        c.execute(
            "UPDATE metaforge_requirements SET payload_json = ?, updated_at = ? WHERE job_id = ?",
            (json.dumps(payload), now_iso, job_id),
        )
        reprocessed_count += 1

    if not is_dry_run:
        conn.commit()
    conn.close()
    if is_dry_run:
        print(f"\n[DRY-RUN COMPLETE] Evaluated {reprocessed_count} requirement(s). Production DB writes = 0.")
    else:
        print(f"Reprocessed {reprocessed_count} requirement(s) successfully.")
    return 0


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    load_dotenv()
    settings = Settings.from_env()
    setup_logging(settings.log_level)

    root = argparse.ArgumentParser(
        description="MetaForge email requirement pipeline (default) or legacy mailbox dump",
    )
    root.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Pipeline/dump: max inbox messages (newest first)",
    )
    root.add_argument(
        "--mailbox",
        default=None,
        help="Pipeline/dump: mailbox UPN (default MAILBOX_UPN)",
    )
    root.add_argument(
        "--today",
        action="store_true",
        default=False,
        help="Extract only today's requirement emails",
    )
    root.add_argument(
        "--since",
        type=str,
        default=None,
        help="Extract requirement emails received on or after this ISO datetime/date",
    )
    sub = root.add_subparsers(dest="cmd", required=False)

    p_pipe = sub.add_parser("pipeline", help="Run filter + AI + MetaForge (same as default)")
    p_pipe.add_argument(
        "--today",
        action="store_true",
        default=False,
        help="Extract only today's requirement emails",
    )
    p_pipe.add_argument(
        "--since",
        type=str,
        default=None,
        help="Extract requirement emails received on or after this ISO datetime/date",
    )
    sub.add_parser("baseline", help="Mark all current inbox messages as seen without processing")
    sub.add_parser("enqueue", help="Queue inbox messages for async Celery workers")
    sub.add_parser("verify-times", help="Compare stored arrival time with Graph API (T4)")
    p_scheduler = sub.add_parser(
        "scheduler",
        help="Always-on scheduler: periodically enqueue inbox messages for workers",
    )
    p_scheduler.add_argument(
        "--max-cycles",
        type=int,
        default=None,
        help="Run only N cycles (default: infinite loop)",
    )
    p_reprocess = sub.add_parser(
        "reprocess",
        help="Re-extract newest N stored rows from stored source text",
    )
    p_reprocess.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Number of stored rows to reprocess",
    )
    p_reprocess.add_argument(
        "--job-id",
        type=str,
        default=None,
        help="Specific job_id or client_jd_id to reprocess",
    )
    p_reprocess.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Simulate reprocessing without writing to database",
    )

    p_dump = sub.add_parser("dump", help="Legacy: export mailbox to JSON/CSV/SQLite")
    _add_dump_args(p_dump)
    p_monitor = sub.add_parser("monitor-accuracy", help="Run continuous accuracy monitoring and threshold check against baseline")
    p_monitor.add_argument("--limit", type=int, default=30, help="Number of recent production records to sample")
    p_monitor.add_argument("--json", action="store_true", default=False, help="Output metrics as JSON")

    args = root.parse_args()

    if args.cmd == "baseline":
        return run_baseline(args, settings)
    if args.cmd == "dump":
        return run_legacy_dump(args)
    if args.cmd == "enqueue":
        return enqueue_pipeline(args, settings)
    if args.cmd == "scheduler":
        return run_scheduler(args, settings)
    if args.cmd == "verify-times":
        return run_verify_times(args, settings)
    if args.cmd == "reprocess":
        return run_reprocess(args, settings)
    if args.cmd == "monitor-accuracy":
        from accuracy_monitor import ContinuousAccuracyMonitor
        monitor = ContinuousAccuracyMonitor(settings=settings)
        res = monitor.run_accuracy_check(limit=args.limit)
        if args.json:
            import json
            print(json.dumps(res, indent=2))
        else:
            print("\n=== ACCURACY MONITORING AUDIT COMPLETE ===")
            print(f"Sample size: {res['sample_size']}")
            print(f"Overall Accuracy: {res['metrics']['overall_accuracy']:.1%}")
            print(f"Source-Present Recovery: {res['metrics']['source_present_recovery']:.1%}")
            print(f"Degraded: {res['degraded']}")
            if res['degraded']:
                print("Breached thresholds:", res['breached_thresholds'])
        return 0 if not res["degraded"] else 1

    if not settings.openai_api_key:
        _LOG.warning("OPENAI_API_KEY is empty — classifier/parser will reject all")
    return run_pipeline(args, settings)


if __name__ == "__main__":
    raise SystemExit(main())
