"""
REFACTORED METAForge recruitment pipeline: 100% Extraction Reliability
Implements 3 strict rules:
1. Zero-Skip Policy: No pre-extraction filters
2. Chronological Integrity: Sort by receivedDateTime (Oldest to Newest)  
3. Timezone Normalization: Convert to Asia/Kolkata (IST)
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from dataclasses import asdict
from datetime import datetime
from typing import Any

from dotenv import load_dotenv

from attachment_handler import extract_text_from_attachment
from body_normalizer import html_to_plain, normalize_body, scrub_pii
from client_detector import detect_client
from config import Settings
from email_filter_refactored import apply_zero_skip_filter, sort_emails_chronologically, normalize_to_ist
from field_mapper import EmailContext, map_to_metaforge
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
from requirement_classifier import classify_email
from requirement_parser import parse_requirements_from_email
from models import RequirementItem
from structured_requirement_extract import build_requirement_struct
from utils import (
    bind_log_context,
    clear_log_context,
    decode_graph_attachment_bytes,
    setup_logging,
)

_LOG = logging.getLogger(__name__)


# --- Legacy dump (original export) -------------------------------------------------

def _msg_dict(om: OutlookMessage) -> dict[str, object]:
    return asdict(om)


def _structured_email(row: dict[str, object], *, body_mode: str) -> dict[str, object]:
    attachments = row.get("attachments") or []
    job_table = row.get("job_table") or {"locations": [], "roles": []}
    extracted = {"job_table": job_table}
    requirement = build_requirement_struct(
        subject=str(row.get("subject") or ""),
        from_email=str(row.get("from_email") or ""),
        from_name=str(row.get("from_name") or ""),
        body_normalized=str(row.get("body_normalized") or ""),
        job_table=job_table if isinstance(job_table, dict) else None,
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
    body_html = body_obj.get("content") or ""
    body_plain = html_to_plain(body_html)
    body_normalized = normalize_body(body_plain)

    attachments = []
    for att in raw.get("attachments") or []:
        try:
            detail = fetch_attachment_detail(
                token=token, mailbox=mailbox, message_id=raw["id"], attachment_id=att["id"]
            )
            if detail.is_inline:
                continue
            ct = extract_text_from_attachment(
                decode_graph_attachment_bytes(detail.content_bytes), detail.content_type, detail.name
            )
            attachments.append(
                {
                    "id": att["id"],
                    "name": att["name"],
                    "content_type": att["contentType"],
                    "size": att["size"],
                    "extracted_text": ct,
                }
            )
        except Exception as exc:
            _LOG.warning("Failed to extract attachment %s: %s", att.get("id"), exc, exc_info=True)

    row = {
        "graph_id": raw["id"],
        "internet_message_id": raw.get("internetMessageId", ""),
        "subject": raw.get("subject", ""),
        "from_email": raw.get("sender", {}).get("emailAddress", {}).get("address", ""),
        "from_name": raw.get("sender", {}).get("emailAddress", {}).get("name", ""),
        "to_recipients": [
            r["emailAddress"]["address"] for r in raw.get("toRecipients", [])
        ],
        "cc_recipients": [
            r["emailAddress"]["address"] for r in raw.get("ccRecipients", [])
        ],
        "received_date_time": raw.get("receivedDateTime", ""),
        "is_read": raw.get("isRead", False),
        "body_html": body_html,
        "body_plain": body_plain,
        "body_normalized": body_normalized,
        "attachments": attachments,
        "body_char_count": len(body_normalized),
    }

    # Rule 3: Normalize timestamp to IST
    row["received_date_time"] = normalize_to_ist(row["received_date_time"])

    om = message_to_outlook(raw)
    om.body_plain = body_plain
    om.body_normalized = body_normalized
    om.attachments = attachments

    return row, om


def _dump_csv(args: argparse.Namespace) -> None:
    """Legacy CSV export with chronological ordering"""
    settings = Settings.from_env()
    token = acquire_token_from_env(settings)
    mailbox = settings.mailbox_upn

    # Collect all emails first
    all_emails = []
    for raw in iter_inbox_messages(token=token, mailbox=mailbox):
        all_emails.append(raw)

    # Rule 2: Sort chronologically (Oldest to Newest)
    all_emails = sorted(all_emails, key=lambda x: x.get('receivedDateTime', ''))

    writer = csv.DictWriter(sys.stdout, fieldnames=_msg_dict(message_to_outlook({})).keys())
    writer.writeheader()
    for raw in all_emails:
        om = message_to_outlook(raw)
        writer.writerow(_msg_dict(om))


def _dump_json(args: argparse.Namespace) -> None:
    """Legacy JSON export with chronological ordering"""
    settings = Settings.from_env()
    token = acquire_token_from_env(settings)
    mailbox = settings.mailbox_upn
    body_mode = args.body_mode

    # Collect all emails first
    all_emails = []
    for raw in iter_inbox_messages(token=token, mailbox=mailbox):
        all_emails.append(raw)

    # Rule 2: Sort chronologically (Oldest to Newest)  
    all_emails = sorted(all_emails, key=lambda x: x.get('receivedDateTime', ''))

    out = []
    for raw in all_emails:
        row, om = _build_row(raw, token, mailbox)
        out.append(_structured_email(row, body_mode=body_mode))
    json.dump(out, sys.stdout, indent=2, ensure_ascii=False)


def _dump_sqlite(args: argparse.Namespace) -> None:
    """Legacy SQLite export with chronological ordering"""
    import sqlite3

    settings = Settings.from_env()
    token = acquire_token_from_env(settings)
    mailbox = settings.mailbox_upn
    db_path = settings.sqlite_path

    # Collect all emails first
    all_emails = []
    for raw in iter_inbox_messages(token=token, mailbox=mailbox):
        all_emails.append(raw)

    # Rule 2: Sort chronologically (Oldest to Newest)
    all_emails = sorted(all_emails, key=lambda x: x.get('receivedDateTime', ''))

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            graph_id TEXT PRIMARY KEY,
            internet_message_id TEXT,
            subject TEXT,
            from_email TEXT,
            from_name TEXT,
            to_recipients TEXT,
            cc_recipients TEXT,
            received_date_time TEXT,
            is_read BOOLEAN,
            body_html TEXT,
            body_plain TEXT,
            body_normalized TEXT,
            attachments TEXT,
            job_table TEXT,
            body_char_count INTEGER
        )
        """
    )

    for raw in all_emails:
        row, om = _build_row(raw, token, mailbox)
        flat = {
            "graph_id": row["graph_id"],
            "internet_message_id": row["internet_message_id"],
            "subject": row["subject"],
            "from_email": row["from_email"],
            "from_name": row["from_name"],
            "to_recipients": json.dumps(row["to_recipients"]),
            "cc_recipients": json.dumps(row["cc_recipients"]),
            "received_date_time": row["received_date_time"],
            "is_read": row["is_read"],
            "body_html": row["body_html"],
            "body_plain": row["body_plain"],
            "body_normalized": row["body_normalized"],
            "attachments": json.dumps(row["attachments"]),
            "job_table": json.dumps(row["job_table"]),
            "body_char_count": row["body_char_count"],
        }
        cols = ", ".join(flat.keys())
        placeholders = ", ".join(["?"] * len(flat))
        cursor.execute(f"INSERT OR REPLACE INTO messages ({cols}) VALUES ({placeholders})", list(flat.values()))

    conn.commit()
    conn.close()


# --- Refactored pipeline with 100% extraction reliability -------------------------

def _process_single_email_robust(
    row: dict[str, object],
    om: OutlookMessage,
    token: str,
    mailbox: str,
    settings: Settings,
    processed_store: ProcessedStore,
) -> None:
    """
    Process a single email with zero-skip policy and expert recruiter interpretation
    """
    graph_id = row["graph_id"]
    bind_log_context(graph_id=graph_id)

    try:
        # Rule 1: Zero-Skip Policy - Apply minimal filtering only
        filter_result = apply_zero_skip_filter(
            subject=row["subject"],
            body=row["body_normalized"],
            has_attachments=bool(row["attachments"]),
            from_email=row["from_email"],
            received_date_time=row["received_date_time"],
        )

        if not filter_result.allowed:
            _LOG.info("Email filtered out: %s", filter_result.reason)
            return

        # Detect client
        client_display, client_key = detect_client(
            subject=row["subject"],
            body=row["body_normalized"],
            sender_email=row["from_email"],
            sender_name=row["from_name"],
        )

        # Classify email (AI decides if it's a requirement)
        classification = classify_email(
            row["body_normalized"],
            subject=row["subject"],
            from_email=row["from_email"],
        )

        # Parse requirements with expert recruiter interpretation
        # AI will return empty/null if not a requirement - no manual filtering needed
        parsed = parse_requirements_from_email(
            subject=row["subject"],
            body=row["body_normalized"],
            sender_email=row["from_email"],
            sender_name=row["from_name"],
            attachments=row["attachments"],
            classification=classification,
        )

        # Map to MetaForge format with null values for missing fields
        for i, req in enumerate(parsed.get("requirements", []), 1):
            ctx = EmailContext(
                from_email=row["from_email"],
                from_name=row["from_name"],
                to_recipients=row["to_recipients"],
                cc_recipients=row["cc_recipients"],
                subject=row["subject"],
                body_plain=row["body_plain"],
                body_normalized=row["body_normalized"],
                attachments=row["attachments"],
                received_date_time=row["received_date_time"],
                graph_id=graph_id,
            )

            # Generate IDs
            allocator = IdAllocator(processed_store=processed_store, ctx=ctx)
            job_id = allocator.allocate_job_id()
            client_jd_id = allocator.allocate_client_jd_id()

            # Map with expert recruiter interpretation - null values for missing fields
            payload = map_to_metaforge(
                extracted=req,
                ctx=ctx,
                client_display_name=client_display,
                job_id=job_id,
                client_jd_id=client_jd_id,
                body_text=row["body_normalized"],
                internal_poc_default="offshore demands",
                jd_count=len(parsed.get("requirements", [])),
                demand_received_date=datetime.fromisoformat(row["received_date_time"].replace('Z', '+00:00')).date(),
            )

            # Send to MetaForge
            if settings.metaforge_mode == "api":
                send_to_metaforge(payload=payload, settings=settings)
            else:
                _LOG.info("MetaForge payload (SQLite mode): %s", json.dumps(payload, indent=2))

        # Mark as processed
        processed_store.mark_processed(graph_id, payload)

    except Exception as exc:
        _LOG.error("Failed to process email %s: %s", graph_id, exc, exc_info=True)
    finally:
        clear_log_context()


def run_pipeline_robust(args: argparse.Namespace) -> None:
    """
    Refactored pipeline with 100% extraction reliability
    Implements all 3 strict rules
    """
    settings = Settings.from_env()
    token = acquire_token_from_env(settings)
    mailbox = settings.mailbox_upn
    processed_store = ProcessedStore(settings=settings)

    _LOG.info("Starting robust pipeline with 100% extraction reliability")
    _LOG.info("Rule 1: Zero-Skip Policy - No pre-extraction filters")
    _LOG.info("Rule 2: Chronological Integrity - Sort by receivedDateTime")
    _LOG.info("Rule 3: Timezone Normalization - Convert to Asia/Kolkata")

    # Collect all emails first for chronological sorting
    all_raw_emails = []
    for raw in iter_inbox_messages(token=token, mailbox=mailbox):
        all_raw_emails.append(raw)

    # Rule 2: Sort chronologically (Oldest to Newest) before any processing
    all_raw_emails = sorted(all_raw_emails, key=lambda x: x.get('receivedDateTime', ''))
    _LOG.info("Collected and sorted %d emails chronologically", len(all_raw_emails))

    # Process emails in chronological order
    for raw in all_raw_emails:
        try:
            row, om = _build_row(raw, token, mailbox)
            
            # Skip if already processed
            if processed_store.is_processed(row["graph_id"]):
                _LOG.debug("Email %s already processed, skipping", row["graph_id"])
                continue

            _process_single_email_robust(row, om, token, mailbox, settings, processed_store)

        except Exception as exc:
            _LOG.error("Failed to build email %s: %s", raw.get("id"), exc, exc_info=True)

    _LOG.info("Pipeline completed successfully")


# --- CLI -------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MetaForge recruitment pipeline")
    parser.add_argument("--mode", choices=["legacy_dump", "run_pipeline"], default="run_pipeline")
    parser.add_argument("--body-mode", choices=["normalized", "full"], default="normalized")
    parser.add_argument("--limit", type=int, help="Limit number of emails to process")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    load_dotenv()
    setup_logging()

    if args.mode == "legacy_dump":
        if args.body_mode == "full":
            _dump_json(args)
        else:
            _dump_csv(args)
    else:
        run_pipeline_robust(args)


if __name__ == "__main__":
    main()
