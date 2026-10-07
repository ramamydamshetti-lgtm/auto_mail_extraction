"""
Exhaustive re-verification of September 24, 2026 emails (both UTC & IST timezones)
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv

workspace_root = Path(__file__).resolve().parent.parent
if str(workspace_root) not in sys.path:
    sys.path.insert(0, str(workspace_root))

load_dotenv(workspace_root / ".env")

import requests
from config import Settings
import outlook_graph
import email_filter
import requirement_classifier
import requirement_parser
from body_normalizer import normalize_body

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def fetch_emails_in_range(start_iso: str, end_iso: str, token: str, mailbox: str) -> list[dict]:
    select = "id,subject,from,toRecipients,ccRecipients,receivedDateTime,body,hasAttachments,isRead,internetMessageId"
    filter_str = f"receivedDateTime ge {start_iso} and receivedDateTime lt {end_iso}"
    mailbox_enc = quote(mailbox, safe="")
    filter_enc = quote(filter_str, safe="()= ':")
    url = f"https://graph.microsoft.com/v1.0/users/{mailbox_enc}/mailFolders/inbox/messages?$filter={filter_enc}&$orderby=receivedDateTime desc&$select={select}&$top=50"
    headers = {"Authorization": f"Bearer {token}"}

    messages = []
    while url:
        r = requests.get(url, headers=headers, timeout=60).json()
        items = r.get("value", [])
        messages.extend(items)
        url = r.get("@odata.nextLink")
    return messages


def main() -> None:
    token = outlook_graph.acquire_token_from_env()
    settings = Settings.from_env()
    mailbox = settings.mailbox_upn

    print("=== QUERY 1: UTC Midnight to Midnight (2026-09-24T00:00:00Z to 2026-09-25T00:00:00Z) ===")
    msgs_utc = fetch_emails_in_range("2026-09-24T00:00:00Z", "2026-09-25T00:00:00Z", token, mailbox)
    print(f"Total UTC emails: {len(msgs_utc)}")

    print("\n=== QUERY 2: IST Full Day (2026-09-23T18:30:00Z to 2026-09-24T18:30:00Z) ===")
    msgs_ist = fetch_emails_in_range("2026-09-23T18:30:00Z", "2026-09-24T18:30:00Z", token, mailbox)
    print(f"Total IST emails: {len(msgs_ist)}")

    # Combine unique messages
    all_msgs = {m["id"]: m for m in msgs_utc + msgs_ist}.values()
    print(f"\nTotal Unique Messages in 24-Sep window: {len(all_msgs)}")

    requirement_emails = []

    for idx, m in enumerate(sorted(all_msgs, key=lambda x: x.get("receivedDateTime", "")), 1):
        fe, fn = outlook_graph._addr_from_from_field(m.get("from"))
        subj = m.get("subject") or ""
        dt = m.get("receivedDateTime") or ""

        body_obj = m.get("body") or {}
        ct = (body_obj.get("contentType") or "").lower()
        content = body_obj.get("content") or ""
        plain = normalize_body("", content) if ct == "html" else normalize_body(content, "")

        # Test classifier
        cls_res = requirement_classifier.classify_email(
            body=plain, subject=subj, from_email=fe, settings=settings
        )

        p_res = None
        if cls_res.label == "REQUIREMENT":
            p_res = requirement_parser.parse_requirements_from_email(
                subject=subj, body=plain, settings=settings
            )
            req_list = p_res.requirements if p_res else []
            requirement_emails.append({
                "index": idx,
                "subject": subj,
                "sender": fe,
                "receivedDateTime": dt,
                "classification_confidence": cls_res.confidence,
                "roles_count": len(req_list),
                "roles": [
                    {
                        "job_title": r.job_title,
                        "location": r.location,
                        "number_of_positions": r.number_of_positions,
                        "experience_level": r.experience_level,
                    }
                    for r in req_list
                ],
            })

    print("\n" + "=" * 60)
    print("VERIFIED REQUIREMENT EMAILS FOR SEPTEMBER 24, 2026")
    print("=" * 60)
    print(f"Total Requirement Emails Found: {len(requirement_emails)}")
    total_roles = sum(e["roles_count"] for e in requirement_emails)
    print(f"Total Roles / Demands Extracted Across All Emails: {total_roles}")
    print("\nRequirement Email Details:")
    print(json.dumps(requirement_emails, indent=2))


if __name__ == "__main__":
    main()
