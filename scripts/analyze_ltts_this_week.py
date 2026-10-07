"""
Analyze LTTS requirements received this week (September 21, 2026 to September 25, 2026)
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
_LOG = logging.getLogger(__name__)


def main() -> None:
    token = outlook_graph.acquire_token_from_env()
    settings = Settings.from_env()
    mailbox = settings.mailbox_upn

    start_iso = "2026-09-21T00:00:00Z"
    select = "id,subject,from,toRecipients,ccRecipients,receivedDateTime,body,hasAttachments,isRead,internetMessageId"
    filter_str = f"receivedDateTime ge {start_iso}"
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

    _LOG.info("Fetched %d total emails since %s", len(messages), start_iso)

    ltts_req_list = []
    ltts_total_emails = 0

    for idx, m in enumerate(sorted(messages, key=lambda x: x.get("receivedDateTime", "")), 1):
        fe, fn = outlook_graph._addr_from_from_field(m.get("from"))
        if "ltts.com" not in fe.lower():
            continue

        ltts_total_emails += 1
        subj = m.get("subject") or ""
        dt = m.get("receivedDateTime") or ""

        body_obj = m.get("body") or {}
        ct = (body_obj.get("contentType") or "").lower()
        content = body_obj.get("content") or ""
        plain = normalize_body("", content) if ct == "html" else normalize_body(content, "")

        cls_res = requirement_classifier.classify_email(
            body=plain, subject=subj, from_email=fe, settings=settings
        )

        if cls_res.label == "REQUIREMENT":
            p_res = requirement_parser.parse_requirements_from_email(
                subject=subj, body=plain, settings=settings
            )
            roles = p_res.requirements if p_res else []
            for r in roles:
                ltts_req_list.append({
                    "received_date_time": dt,
                    "subject": subj,
                    "sender": fe,
                    "job_title": r.job_title,
                    "location": r.location,
                    "number_of_positions": r.number_of_positions,
                    "experience_level": r.experience_level,
                })

    # Group by date
    by_date = {}
    for req in ltts_req_list:
        date_str = req["received_date_time"][:10]
        if date_str not in by_date:
            by_date[date_str] = []
        by_date[date_str].append(req)

    print("\n" + "=" * 60)
    print("LTTS REQUIREMENTS THIS WEEK (SEP 21 - SEP 25, 2026)")
    print("=" * 60)
    print(f"Total LTTS Emails Received This Week: {ltts_total_emails}")
    print(f"Total LTTS Requirements / Roles Extracted: {len(ltts_req_list)}")
    print("\nRequirements Breakdown by Date:")
    for d in sorted(by_date.keys()):
        print(f"\n--- Date: {d} ({len(by_date[d])} requirements) ---")
        for item in by_date[d]:
            loc = ", ".join(item["location"]) if isinstance(item["location"], list) else str(item["location"] or "N/A")
            print(f"  - [{item['job_title']}] | Location: {loc} | Subject: {item['subject'][:50]}")

    print("\nDetailed JSON Output:")
    print(json.dumps(ltts_req_list, indent=2))


if __name__ == "__main__":
    main()
