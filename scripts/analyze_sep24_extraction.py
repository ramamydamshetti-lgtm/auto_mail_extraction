"""
Analyze emails received on September 24, 2026 (2026-09-24)
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

    select = "id,subject,from,toRecipients,ccRecipients,receivedDateTime,body,hasAttachments,isRead,internetMessageId"
    filter_str = "receivedDateTime ge 2026-09-24T00:00:00Z and receivedDateTime lt 2026-09-25T00:00:00Z"
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

    print(f"Total emails received on 2026-09-24: {len(messages)}")

    results = []
    for idx, m in enumerate(messages, 1):
        fe, fn = outlook_graph._addr_from_from_field(m.get("from"))
        subj = m.get("subject") or ""
        dt = m.get("receivedDateTime") or ""
        has_att = bool(m.get("hasAttachments"))

        body_obj = m.get("body") or {}
        ct = (body_obj.get("contentType") or "").lower()
        content = body_obj.get("content") or ""
        plain = normalize_body("", content) if ct == "html" else normalize_body(content, "")

        # Check sender domain (including iexcel.co.in & idexcel.com)
        fe_lower = fe.lower()
        is_client_domain = (
            email_filter.is_sender_allowlisted(fe)
            or any(d in fe_lower for d in ["iexcel.co.in", "idexcel.com", "ltts.com", "kpmg.com", "deloitte.com", "itcinfotech.com"])
        )
        has_struct = email_filter.has_requirement_structure(plain)

        cls_label = "SKIPPED"
        parsed_roles = []

        if is_client_domain:
            cls_res = requirement_classifier.classify_email(
                body=plain, subject=subj, from_email=fe, settings=settings
            )
            cls_label = cls_res.label
            if cls_label == "REQUIREMENT":
                p_res = requirement_parser.parse_requirements_from_email(
                    subject=subj, body=plain, settings=settings
                )
                if p_res and p_res.requirements:
                    for r in p_res.requirements:
                        parsed_roles.append({
                            "job_title": r.job_title,
                            "location": r.location,
                            "number_of_positions": r.number_of_positions,
                            "experience_level": r.experience_level,
                        })

        results.append({
            "idx": idx,
            "subject": subj,
            "sender": fe,
            "receivedDateTime": dt,
            "is_client_domain": is_client_domain,
            "has_struct": has_struct,
            "classification": cls_label,
            "roles_count": len(parsed_roles),
            "roles": parsed_roles,
            "body_snippet": plain[:250],
        })

    summary_by_sender = {}
    total_req_emails = 0
    total_parsed_roles = 0

    for r in results:
        sender = r["sender"]
        domain = sender.split("@")[-1].lower() if "@" in sender else "other"
        if domain not in summary_by_sender:
            summary_by_sender[domain] = {"total_emails": 0, "requirement_emails": 0, "parsed_roles": 0}
        summary_by_sender[domain]["total_emails"] += 1
        if r["classification"] == "REQUIREMENT":
            summary_by_sender[domain]["requirement_emails"] += 1
            total_req_emails += 1
            roles_cnt = r["roles_count"]
            summary_by_sender[domain]["parsed_roles"] += roles_cnt
            total_parsed_roles += roles_cnt

    print("\n" + "=" * 60)
    print("SEPTEMBER 24, 2026 EXTRACTION ANALYSIS SUMMARY")
    print("=" * 60)
    print(f"Total Emails Received: {len(messages)}")
    print(f"Total Requirement Emails Classified: {total_req_emails}")
    print(f"Total Extracted Requirement Roles: {total_parsed_roles}")
    print("\nSummary by Domain:")
    print(json.dumps(summary_by_sender, indent=2))
    print("\nDetailed Email Results:")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
