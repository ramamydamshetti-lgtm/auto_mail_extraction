"""
Script: scripts/run_today_extraction.py
Runs a real-data test on today's emails from the recruitment inbox via MS Graph API,
applies the two-layer filter gate (is_sender_allowlisted + has_requirement_structure),
runs requirement_classifier for emails passing both gates, and outputs CSV & summary JSON.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import quote

from dotenv import load_dotenv

# Ensure workspace root is in sys.path
workspace_root = Path(__file__).resolve().parent.parent
if str(workspace_root) not in sys.path:
    sys.path.insert(0, str(workspace_root))

load_dotenv(workspace_root / ".env")

import requests
from config import Settings
import email_filter
import requirement_classifier
import outlook_graph
from body_normalizer import normalize_body

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
_LOG = logging.getLogger("today_extraction")


def fetch_today_messages(
    token: str,
    mailbox: str,
    start_datetime_iso: str,
) -> list[dict[str, Any]]:
    """
    Queries Graph API GET /users/{mailbox}/mailFolders/inbox/messages
    with $filter=receivedDateTime ge {start_datetime_iso} with paging (@odata.nextLink).
    """
    select = (
        "id,subject,from,toRecipients,ccRecipients,receivedDateTime,body,hasAttachments,"
        "isRead,internetMessageId"
    )
    mailbox_enc = quote(mailbox, safe="")
    filter_enc = quote(f"receivedDateTime ge {start_datetime_iso}", safe="()= ':")
    url = (
        f"https://graph.microsoft.com/v1.0/users/{mailbox_enc}/mailFolders/inbox/messages"
        f"?$filter=receivedDateTime ge {start_datetime_iso}&$orderby=receivedDateTime desc&$select={select}&$top=50"
    )
    headers = {"Authorization": f"Bearer {token}"}
    messages: list[dict[str, Any]] = []

    _LOG.info("Fetching messages from MS Graph for %s with filter: receivedDateTime ge %s", mailbox, start_datetime_iso)

    while url:
        resp = requests.get(url, headers=headers, timeout=60)
        resp.raise_for_status()
        payload = resp.json()
        items = payload.get("value", [])
        messages.extend(items)
        _LOG.info("Fetched page with %d messages (Total so far: %d)", len(items), len(messages))
        url = payload.get("@odata.nextLink")

    return messages


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run real-data extraction on today's emails from recruitment inbox"
    )
    parser.add_argument(
        "--output-csv",
        default=str(workspace_root / "data" / "today_extraction_results.csv"),
        help="Output CSV file path (default: data/today_extraction_results.csv)",
    )
    parser.add_argument(
        "--output-summary",
        default=str(workspace_root / "data" / "today_extraction_summary.json"),
        help="Output summary JSON file path (default: data/today_extraction_summary.json)",
    )
    parser.add_argument(
        "--start-datetime",
        default=None,
        help="Optional ISO datetime string for filtering (default: start of today UTC e.g. YYYY-MM-DDT00:00:00Z)",
    )
    args = parser.parse_args()

    settings = Settings.from_env()
    mailbox = settings.mailbox_upn or os.environ.get("MAILBOX_UPN", "recruitment.application@metaforgeit.com")
    _LOG.info("Initializing extraction test for mailbox: %s", mailbox)

    # Calculate default start of today UTC
    now_utc = datetime.now(timezone.utc)
    if args.start_datetime:
        start_iso = args.start_datetime
    else:
        # Default start of today UTC
        start_iso = now_utc.strftime("%Y-%m-%dT00:00:00Z")

    _LOG.info("Querying Graph API for emails received since: %s", start_iso)

    # Step 1: Authenticate to MS Graph & fetch today's emails
    try:
        token = outlook_graph.acquire_token_from_env()
        _LOG.info("Successfully acquired MS Graph token via MSAL client credentials")
    except Exception as exc:
        _LOG.error("Failed to acquire MS Graph token: %s", exc)
        sys.exit(1)

    try:
        raw_messages = fetch_today_messages(token, mailbox, start_iso)
    except Exception as exc:
        _LOG.error("Error fetching messages from Graph API: %s", exc)
        sys.exit(1)

    total_emails = len(raw_messages)
    _LOG.info("Total emails fetched for today (%s): %d", start_iso, total_emails)

    summary_counts = {
        "total_emails_received_today": total_emails,
        "total_with_pdf_attachments": 0,
        "rejected_layer1_sender_not_allowlisted": 0,
        "rejected_layer2_no_requirement_structure": 0,
        "passed_both_gates": 0,
        "classified_REQUIREMENT": 0,
        "classified_NOT_A_REQUIREMENT": 0,
        "errors": 0,
    }

    csv_rows: list[dict[str, Any]] = []

    # Step 2: Process each email through two-layer gate & classifier
    for idx, msg in enumerate(raw_messages, 1):
        msg_id = msg.get("id") or ""
        subject = msg.get("subject") or ""
        fe, fn = outlook_graph._addr_from_from_field(msg.get("from"))
        from_email = fe
        received_dt = msg.get("receivedDateTime") or ""
        has_attachments = bool(msg.get("hasAttachments"))

        # Extract plain body
        body_obj = msg.get("body") or {}
        content_type = (body_obj.get("contentType") or "").lower()
        content_text = body_obj.get("content") or ""

        if content_type == "html":
            plain_body = normalize_body("", content_text)
        else:
            plain_body = normalize_body(content_text, "")

        # Check attachments for PDF
        has_pdf = False
        attachment_names: list[str] = []
        if has_attachments and msg_id:
            try:
                atts = outlook_graph.fetch_attachments(token, mailbox, msg_id)
                for a in atts:
                    attachment_names.append(a.name)
                    if a.name.lower().endswith(".pdf") or (a.content_type and a.content_type.lower() == "application/pdf"):
                        has_pdf = True
            except Exception as att_exc:
                _LOG.warning("Could not fetch attachments for msg %s: %s", msg_id[:10], att_exc)

        if has_pdf:
            summary_counts["total_with_pdf_attachments"] += 1

        row_data = {
            "subject": subject,
            "sender": from_email,
            "received_date_time": received_dt,
            "filter_allowed": False,
            "filter_reason": "",
            "classification_label": "",
            "has_pdf_attachment": has_pdf,
            "attachment_names": ", ".join(attachment_names),
        }

        try:
            # Layer 1: Check sender allowlist
            is_allowlisted = email_filter.is_sender_allowlisted(from_email)
            if not is_allowlisted:
                summary_counts["rejected_layer1_sender_not_allowlisted"] += 1
                row_data["filter_allowed"] = False
                row_data["filter_reason"] = "sender_not_allowlisted"
                csv_rows.append(row_data)
                _LOG.info("[%d/%d] REJECTED (Layer 1 - sender_not_allowlisted): %s | %s", idx, total_emails, from_email, subject[:40])
                continue

            # Layer 2: Check requirement structure in body
            has_req_struct = email_filter.has_requirement_structure(plain_body)
            if not has_req_struct:
                summary_counts["rejected_layer2_no_requirement_structure"] += 1
                row_data["filter_allowed"] = False
                row_data["filter_reason"] = "no_requirement_structure_in_body"
                csv_rows.append(row_data)
                _LOG.info("[%d/%d] REJECTED (Layer 2 - no_requirement_structure): %s | %s", idx, total_emails, from_email, subject[:40])
                continue

            # Passed BOTH gates!
            summary_counts["passed_both_gates"] += 1
            row_data["filter_allowed"] = True
            row_data["filter_reason"] = ""

            # Step 2b: Requirement Classifier
            _LOG.info("[%d/%d] PASSED GATES -> Classifying via LLM: %s | %s", idx, total_emails, from_email, subject[:40])
            time.sleep(1.0)  # Pacing pause for LLM API

            cls_res = requirement_classifier.classify_email(
                body=plain_body,
                subject=subject,
                from_email=from_email,
                settings=settings,
            )

            label = cls_res.label if hasattr(cls_res, "label") else str(cls_res)
            row_data["classification_label"] = label

            if label == "REQUIREMENT":
                summary_counts["classified_REQUIREMENT"] += 1
            elif label == "NOT_A_REQUIREMENT":
                summary_counts["classified_NOT_A_REQUIREMENT"] += 1
            else:
                _LOG.warning("Unexpected classification label: %s", label)

            csv_rows.append(row_data)

        except Exception as exc:
            _LOG.error("Error processing email [%d/%d] (%s): %s", idx, total_emails, subject[:40], exc)
            summary_counts["errors"] += 1
            row_data["filter_reason"] = f"error: {exc}"
            csv_rows.append(row_data)

    # Step 3: Write CSV results
    output_csv_path = Path(args.output_csv)
    output_csv_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "subject",
        "sender",
        "received_date_time",
        "filter_allowed",
        "filter_reason",
        "classification_label",
        "has_pdf_attachment",
        "attachment_names",
    ]

    with open(output_csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(csv_rows)

    _LOG.info("Wrote CSV results to %s", output_csv_path.resolve())

    # Write summary JSON
    output_summary_path = Path(args.output_summary)
    output_summary_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_summary_path, "w", encoding="utf-8") as f:
        json.dump(summary_counts, f, indent=2)

    _LOG.info("Wrote summary JSON to %s", output_summary_path.resolve())

    # Step 4: Console summary output & Markdown Table
    print("\n" + "=" * 60)
    print("TODAY'S EMAIL EXTRACTION TEST SUMMARY")
    print("=" * 60)
    print(json.dumps(summary_counts, indent=2))
    print("\n### Acceptance Criteria Summary Report\n")
    print("| Metric Name | Count |")
    print("|---|---|")
    print(f"| Total Emails Received Today | {summary_counts['total_emails_received_today']} |")
    print(f"| Total With PDF Attachments | {summary_counts['total_with_pdf_attachments']} |")
    print(f"| Rejected (Layer 1: Sender Not Allowlisted) | {summary_counts['rejected_layer1_sender_not_allowlisted']} |")
    print(f"| Rejected (Layer 2: No Requirement Structure) | {summary_counts['rejected_layer2_no_requirement_structure']} |")
    print(f"| Passed Both Gates | {summary_counts['passed_both_gates']} |")
    print(f"| Classified: REQUIREMENT | {summary_counts['classified_REQUIREMENT']} |")
    print(f"| Classified: NOT_A_REQUIREMENT | {summary_counts['classified_NOT_A_REQUIREMENT']} |")
    print(f"| Errors | {summary_counts['errors']} |")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
