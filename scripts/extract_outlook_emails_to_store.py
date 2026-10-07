"""Extract client requirements directly from Outlook emails in CSV dumps into SQLite UI databases."""

import csv
import json
import logging
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

# Enable logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
_LOG = logging.getLogger("extract_outlook")

# Path definitions
DB_METAFORGE = Path("data/metaforge_requirements.db")
DB_PROCESSED = Path("data/processed_messages.db")
CSV_PATH = Path("latest_500_all.csv")

# Ensure data dir exists
DB_METAFORGE.parent.mkdir(parents=True, exist_ok=True)

# Allowed client domain check
CLIENT_DOMAINS = {
    "accenture.com": "Accenture",
    "iexcel.co.in": "Accenture",
    "idexcel.com": "Accenture",
    "ltts.com": "LTTS",
    "kpmg.com": "KPMG",
    "itcinfotech.com": "ITC Infotech"
}

ALLOWED_SENDERS = {
    "rkarnam@metaforgeit.com": "MetaForge CEO"
}


def detect_client_from_email(from_email: str, subject: str, body: str) -> str:
    """Detect client name from email metadata."""
    email_clean = (from_email or "").strip().lower()
    if "@" in email_clean:
        domain = email_clean.rsplit("@", 1)[-1]
        for d_key, c_name in CLIENT_DOMAINS.items():
            if domain == d_key or domain.endswith("." + d_key):
                return c_name

    # Body or subject check
    blob = f"{subject} {body}".lower()
    if "accenture" in blob or "iexcel" in blob:
        return "Accenture"
    if "ltts" in blob or "l&t" in blob:
        return "LTTS"
    if "kpmg" in blob:
        return "KPMG"
    if "itc infotech" in blob or "itcinfotech" in blob:
        return "ITC Infotech"

    return "Unknown"


def extract_table_requirements(body_html_or_plain: str, client_name: str, email_date: str) -> list:
    """Regex table/pattern extraction for demand tables in Outlook email body."""
    reqs = []
    # Pattern for Req ID (e.g. 123456-1 or ACCENTURE-2026-09-01-001 or LTTS-20260901-01)
    req_id_rx = re.compile(r"\b([0-9]{6}-[0-9]|[A-Z0-9]{3,10}-\d{6,8}-\d{1,4})\b", re.I)
    
    # Try finding lines with Req IDs or Job Roles
    lines = body_html_or_plain.split("\n")
    for line in lines:
        line_s = line.strip()
        if not line_s:
            continue
        m = req_id_rx.search(line_s)
        if m:
            req_id = m.group(1).upper()
            reqs.append({
                "client_jd_id": req_id,
                "job_title": line_s[:80],
                "requirement_from": client_name,
                "job_status": "Hold" if "hold" in line_s.lower() else "Open",
                "demand_received_date": email_date[:10] if email_date else "2026-09-01"
            })
    return reqs


def init_db_tables():
    """Ensure database tables are initialized."""
    conn1 = sqlite3.connect(DB_METAFORGE)
    conn1.execute("""
        CREATE TABLE IF NOT EXISTS metaforge_requirements (
            job_id TEXT PRIMARY KEY,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn1.commit()
    conn1.close()

    conn2 = sqlite3.connect(DB_PROCESSED)
    conn2.execute("""
        CREATE TABLE IF NOT EXISTS requirement_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            requirement_from TEXT NOT NULL,
            job_title_norm TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            source_graph_id TEXT,
            created_at TEXT NOT NULL
        )
    """)
    conn2.commit()
    conn2.close()


def process_outlook_csv():
    """Read Outlook emails from CSV and ingest into SQLite UI database."""
    init_db_tables()
    if not CSV_PATH.exists():
        _LOG.error("CSV file %s not found!", CSV_PATH)
        return

    _LOG.info("Reading Outlook emails directly from %s...", CSV_PATH)
    with open(CSV_PATH, "r", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    _LOG.info("Processing %d Outlook emails...", len(rows))

    conn_mf = sqlite3.connect(DB_METAFORGE)
    conn_mem = sqlite3.connect(DB_PROCESSED)

    ingested_count = 0
    seq = 1

    for row in rows:
        graph_id = row.get("graph_id") or f"GRAPH-{seq}"
        from_email = row.get("from_email") or row.get("from_address") or ""
        subject = row.get("subject") or ""
        body = row.get("body_normalized") or row.get("body") or ""
        received_at = row.get("received_date_time") or row.get("date") or datetime.now(timezone.utc).isoformat()

        fe_clean = (from_email or "").strip().lower()
        if (fe_clean.endswith("@metaforgeit.com") or fe_clean.endswith(".metaforgeit.com")) and fe_clean != "rkarnam@metaforgeit.com":
            continue

        client = detect_client_from_email(from_email, subject, body)
        if client == "Unknown" and not ("requirement" in subject.lower() or "demand" in subject.lower()):
            continue

        # Extract requirements from payload or body text
        req_json_str = row.get("requirement_json") or ""
        req_id = None
        job_title = subject or "Client Job Requirement"

        if req_json_str and req_json_str.strip().startswith("{"):
            try:
                rj = json.loads(req_json_str)
                req_id = rj.get("client_jd_id") or rj.get("req_id")
                job_title = rj.get("job_title") or job_title
            except Exception:
                pass

        if not req_id:
            # Look for Req ID in body / subject
            m = re.search(r"\b([0-9]{6}-[0-9]|[A-Z0-9]{3,10}-\d{6,8}-\d{1,4})\b", f"{subject} {body}")
            if m:
                req_id = m.group(1).upper()
            else:
                req_id = f"{client[:3].upper()}-REQ-{seq:04d}"

        sys_job_id = f"REQ-OUTLOOK-{seq:04d}"
        seq += 1

        payload = {
            "job_id": sys_job_id,
            "client_jd_id": req_id,
            "requirement_from": client,
            "job_title": job_title,
            "job_status": "Hold" if "hold" in subject.lower() or "hold" in body.lower() else "Open",
            "demand_received_date": received_at[:10],
            "client_poc": from_email,
            "client_lead_poc": from_email,
            "internal_poc": "offshore demands",
            "number_of_positions": 1,
            "experience_level": "Mid Senior",
            "employment_type": "Full-time",
            "work_mode": "Hybrid",
            "location": "India",
            "overall_experience": "3+ years",
            "mandatory_skills": subject[:100],
            "skills": body[:150],
            "yearly_budget": "Not provided",
            "monthly_budget": "Not provided"
        }

        # Store in metaforge_requirements table
        conn_mf.execute(
            "INSERT OR REPLACE INTO metaforge_requirements (job_id, payload_json, created_at) VALUES (?, ?, ?)",
            (sys_job_id, json.dumps(payload), received_at)
        )

        # Store in requirement_memory table
        conn_mem.execute(
            "INSERT INTO requirement_memory (requirement_from, job_title_norm, payload_json, source_graph_id, created_at) VALUES (?, ?, ?, ?, ?)",
            (client, job_title[:100].lower(), json.dumps(payload), graph_id, received_at)
        )

        ingested_count += 1

    conn_mf.commit()
    conn_mem.commit()
    conn_mf.close()
    conn_mem.close()

    _LOG.info("SUCCESS! Extracted and ingested %d requirements directly from Outlook emails into SQLite databases.", ingested_count)


if __name__ == "__main__":
    process_outlook_csv()
