"""
Live pipeline runner on real Outlook mailbox.
Captures exact per-message details, extraction payloads, database records, and summary counts.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from pathlib import Path
from dotenv import load_dotenv

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from outlook_graph import acquire_token_from_env, iter_inbox_messages, fetch_attachments
from config import Settings
from client_detector import detect_client
from email_filter import apply_email_filter, is_sender_allowlisted
from requirement_classifier import classify_email, heuristic_obvious_client_requirement
from requirement_parser import parse_requirements_from_email
from table_reconciler import run_client_table_reconciliation
from field_mapper import EmailContext, map_to_metaforge
from metaforge_api import IdAllocator
from processed_store import ProcessedStore

load_dotenv()
settings = Settings.from_env()
token = acquire_token_from_env()
mailbox = os.getenv("MAILBOX_UPN", "recruitment.application@metaforgeit.com")
allocator = IdAllocator(db_path=settings.metaforge_sqlite_path)
store = ProcessedStore(settings.processed_db)

print(f"Token acquired. Polling live mailbox: {mailbox}")

raw_msgs = list(iter_inbox_messages(token, mailbox, limit=25))
print(f"Polled {len(raw_msgs)} live messages from Graph API.")

results = []
summary = {
    "total_polled": len(raw_msgs),
    "filtered_rejected": 0,
    "classified_requirement": 0,
    "classified_not_requirement": 0,
    "pending_review": 0,
    "newly_created_requirements": 0,
    "status_updates": 0,
    "filter_reasons": {},
}

for idx, raw in enumerate(raw_msgs, 1):
    gid = raw.get("id", "")
    subj = raw.get("subject", "")
    recv_time = raw.get("receivedDateTime", "")
    from_dict = raw.get("from", {}) or {}
    ea = from_dict.get("emailAddress", {}) or {}
    fe = ea.get("address", "").strip()
    fn = ea.get("name", "").strip()

    body_obj = raw.get("body", {}) or {}
    body_content = body_obj.get("content", "")

    # Clean body plain
    from body_normalizer import html_to_plain, scrub_pii
    plain = html_to_plain(body_content) if body_obj.get("contentType") == "html" else body_content
    body_for_ai = scrub_pii(plain)

    record = {
        "index": idx,
        "graph_id": gid,
        "sender": fe,
        "sender_name": fn,
        "subject": subj,
        "received_datetime": recv_time,
        "filter_decision": None,
        "classification": None,
        "extracted_payloads": [],
        "rejection_reason": None,
    }

    # 1. Client Detection
    client = detect_client(subj, body_for_ai, fe)
    if client is None:
        record["filter_decision"] = "BLOCKED"
        record["rejection_reason"] = "unknown_client"
        summary["filtered_rejected"] += 1
        summary["filter_reasons"]["unknown_client"] = summary["filter_reasons"].get("unknown_client", 0) + 1
        results.append(record)
        continue

    # 2. Allowlist Check
    if not is_sender_allowlisted(fe):
        record["filter_decision"] = "BLOCKED"
        record["rejection_reason"] = "sender_not_allowlisted"
        summary["filtered_rejected"] += 1
        summary["filter_reasons"]["sender_not_allowlisted"] = summary["filter_reasons"].get("sender_not_allowlisted", 0) + 1
        results.append(record)
        continue

    # 3. Structure & Junk Filter Gate
    filt = apply_email_filter(from_email=fe, body=body_for_ai, subject=subj, has_attachments=bool(raw.get("hasAttachments")))
    if not filt.allowed:
        record["filter_decision"] = "BLOCKED"
        record["rejection_reason"] = filt.reason
        summary["filtered_rejected"] += 1
        summary["filter_reasons"][filt.reason] = summary["filter_reasons"].get(filt.reason, 0) + 1
        results.append(record)
        continue

    record["filter_decision"] = "ALLOWED"

    # 4. AI Classification
    cls_res = classify_email(body_for_ai, subject=subj, settings=settings, from_email=fe)
    record["classification"] = cls_res.label
    if cls_res.label == "NOT_A_REQUIREMENT":
        summary["classified_not_requirement"] += 1
        record["rejection_reason"] = "ai_classified_not_requirement"
        results.append(record)
        continue

    summary["classified_requirement"] += 1

    # 5. Extraction
    parsed = parse_requirements_from_email(subject=subj, body=body_for_ai, settings=settings, message_id=gid, from_email=fe)
    parsed, recon_meta = run_client_table_reconciliation(client_name=client.display_name, body_text=body_for_ai, parse_result=parsed, graph_id=gid)

    if recon_meta.get("reconciliation_status") == "conflict_review_flagged":
        summary["pending_review"] += 1

    ctx = EmailContext(
        graph_message_id=gid,
        internet_message_id=raw.get("internetMessageId", ""),
        to_emails=[t.get("emailAddress", {}).get("address", "") for t in (raw.get("toRecipients") or [])],
        cc_emails=[c.get("emailAddress", {}).get("address", "") for c in (raw.get("ccRecipients") or [])],
        from_email=fe,
        from_name=fn,
    )

    from datetime import date
    try:
        recv_date = date.fromisoformat(recv_time[:10])
    except Exception:
        recv_date = date.today()

    for ext in parsed.requirements:
        job_id = allocator.next_job_id(recv_date)
        cjd = ext.req_id if ext.req_id else allocator.next_client_jd_id(client.key)
        payload = map_to_metaforge(
            ext.model_dump(mode="json", by_alias=True),
            ctx=ctx,
            client_display_name=client.display_name,
            job_id=job_id,
            client_jd_id=cjd,
            body_text=body_for_ai,
            jd_count=len(parsed.requirements),
            demand_received_date=recv_date,
            email_subject=subj,
            email_body_plain=plain,
            email_received_iso=recv_time,
        )
        record["extracted_payloads"].append(payload)
        summary["newly_created_requirements"] += 1

    results.append(record)

print("\n--- EXTRACTION RUN COMPLETE ---")
print(json.dumps(summary, indent=2))

with open("scratch/live_run_results.json", "w", encoding="utf-8") as f:
    json.dump({"summary": summary, "results": results}, f, indent=2, default=str)
print("Saved live run details to scratch/live_run_results.json")
