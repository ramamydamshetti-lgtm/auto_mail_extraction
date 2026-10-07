"""
Analyze ALL client requirements received across September 23, 24, and 25, 2026
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


def main() -> None:
    token = outlook_graph.acquire_token_from_env()
    settings = Settings.from_env()
    mailbox = settings.mailbox_upn

    start_iso = "2026-09-23T00:00:00Z"
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

    print(f"Total emails received since {start_iso}: {len(messages)}")

    client_domains = ["ltts.com", "iexcel.com", "iexcel.co.in", "idexcel.com", "kpmg.com", "deloitte.com", "itcinfotech.com"]

    all_requirements = []

    for idx, m in enumerate(sorted(messages, key=lambda x: x.get("receivedDateTime", "")), 1):
        fe, fn = outlook_graph._addr_from_from_field(m.get("from"))
        fe_lower = fe.lower()

        # Check if client domain
        if not any(d in fe_lower for d in client_domains):
            continue

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
                all_requirements.append({
                    "received_date_time": dt,
                    "subject": subj,
                    "sender": fe,
                    "job_title": r.job_title,
                    "location": r.location,
                    "number_of_positions": r.number_of_positions,
                })

    print("\n" + "=" * 60)
    print("ALL CLIENT REQUIREMENTS (SEP 23 - SEP 25, 2026)")
    print("=" * 60)
    print(f"Total Client Requirements Extracted: {len(all_requirements)}")

    # Summary by Domain
    by_domain = {}
    for req in all_requirements:
        domain = req["sender"].split("@")[-1].lower()
        by_domain[domain] = by_domain.get(domain, 0) + 1

    print("\nBreakdown by Domain:")
    print(json.dumps(by_domain, indent=2))


if __name__ == "__main__":
    main()
