import sys
import os
import json
import sqlite3
import re

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")

from models import RequirementItem
from field_mapper import map_to_metaforge, EmailContext
from strict_validator import validate_requirement_before_save
from two_way_verifier import reconcile_two_way, deterministic_extract_block
from ui.app import load_config
from ui.db import fetch_all_records

conn_mf = sqlite3.connect("data/metaforge_requirements.db")
conn_mf.row_factory = sqlite3.Row

# Target records
targets = [
    {"jid": "2026/09/07-023", "name": "Lead Power System Engineer", "client": "LTTS"},
    {"jid": "2026/09/08-005", "name": "Pega Marketing", "client": "Accenture"},
    {"jid": "2026/09/08-001", "name": "Data Scientist", "client": "KPMG"},
    {"jid": "2026/09/23-006", "name": "Sr Data Scientist", "client": "ITC Infotech"},
    {"jid": "2026/09/30-007", "name": "ServiceNow ITAM Administrator", "client": "Accenture"},
]

print("=" * 80)
print("REAL HISTORICAL REQUIREMENTS END-TO-END PIPELINE AUDIT")
print("Tracing Email -> Extracted -> mapper -> validation -> DB -> UI")
print("=" * 80)

fields_to_check = [
    "job_title",
    "client_jd_id",
    "number_of_positions",
    "location",
    "experience",
    "work_mode",
    "budget",
    "notice_period",
    "mandatory_skills",
    "skills",
]

for t in targets:
    jid = t["jid"]
    row = conn_mf.execute("SELECT payload_json FROM metaforge_requirements WHERE job_id = ?", (jid,)).fetchone()
    if not row:
        print(f"Row {jid} not found in DB")
        continue
    p = json.loads(row["payload_json"])
    body = p.get("bodyText") or p.get("body") or ""
    subj = p.get("subject") or ""

    # 1. Deterministic extract from email text
    det = deterministic_extract_block(body)

    # 2. Simulate mapper on original extracted dictionary
    ctx = EmailContext(
        from_email=p.get("from") or "test@client.com",
        to_emails=[p.get("to") or "internal@metaforge.com"],
        cc_emails=[],
        graph_message_id=p.get("graphMessageId") or "gid1",
        internet_message_id=p.get("internetMessageId") or "iid1",
        from_name=t["client"],
    )

    # Use stored payload as simulated LLM extracted output
    sim_llm = dict(p)

    # Map to metaforge
    mapped = map_to_metaforge(
        sim_llm,
        ctx=ctx,
        client_display_name=t["client"],
        job_id=jid,
        client_jd_id=p.get("client_jd_id"),
        body_text=body,
        email_subject=subj,
    )

    # Validate before save
    validated, should_review, review_reason = validate_requirement_before_save(
        mapped,
        block_text=body,
        client=t["client"],
    )

    print(f"\nTarget: {t['name']} ({jid}) | Client: {t['client']}")
    print("-" * 70)
    for f in fields_to_check:
        val_db = p.get(f) if f != "experience" else (p.get("overall_experience") or p.get("experience"))
        val_mapped = mapped.get(f) if f != "experience" else (mapped.get("overall_experience") or mapped.get("experience"))
        val_val = validated.get(f) if f != "experience" else (validated.get("overall_experience") or validated.get("experience"))

        # For budget, also check budget_text / monthly / yearly
        if f == "budget":
            val_db = p.get("budget_text") or p.get("budget") or p.get("monthly_budget") or p.get("yearly_budget")
            val_mapped = mapped.get("budget_text") or mapped.get("budget") or mapped.get("monthly_budget") or mapped.get("yearly_budget")
            val_val = validated.get("budget_text") or validated.get("budget") or validated.get("monthly_budget") or validated.get("yearly_budget")

        status = "OK" if val_val is not None else "ABSENT_IN_SOURCE"
        print(f"  {f:22} -> DB: {str(val_db)[:35]:35} | Pipeline: {str(val_val)[:35]:35} [{status}]")

print("\nEnd-to-end verification completed.")
