"""Ingest Today's (28/09/2026) Requirements Batch into SQLite UI store:
- ITC Infotech: 1 requirement
- Accenture: 3 NEW requirements + 2 REOPENED (updated to Open status) = 5 total
"""

import sqlite3
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

DB_METAFORGE = Path("data/metaforge_requirements.db")
DB_PROCESSED = Path("data/processed_messages.db")
TODAY_DATE = "2026-09-28"

# 1. Define Today's Requirements
today_requirements = [
    # ITC Infotech (1 requirement)
    {
        "job_id": "REQ-2026-09-28-ITC-01",
        "client_jd_id": "ITC-2026-09-28-001",
        "requirement_from": "ITC Infotech",
        "job_title": "Java Microservices Senior Developer",
        "job_status": "Open",
        "action": "CREATE (New Requirement)",
        "demand_received_date": TODAY_DATE,
        "client_poc": "Divya.Grover@itcinfotech.com",
        "number_of_positions": 2,
        "location": "Bangalore",
        "overall_experience": "5-8 years",
        "mandatory_skills": "Java 17; Spring Boot; Microservices; Kafka; PostgreSQL",
        "work_mode": "Hybrid",
        "employment_type": "Full-time"
    },
    # Accenture - 3 NEW Requirements
    {
        "job_id": "REQ-2026-09-28-ACC-01",
        "client_jd_id": "ACC-2026-09-28-001",
        "requirement_from": "Accenture",
        "job_title": "SAP S/4HANA Finance Functional Lead",
        "job_status": "Open",
        "action": "CREATE (New Requirement)",
        "demand_received_date": TODAY_DATE,
        "client_poc": "anusha.k@iexcel.co.in",
        "number_of_positions": 4,
        "location": "Bangalore",
        "overall_experience": "7-10 years",
        "mandatory_skills": "SAP FI/CO; S/4HANA Finance; General Ledger; Asset Accounting",
        "work_mode": "On-site",
        "employment_type": "Contract"
    },
    {
        "job_id": "REQ-2026-09-28-ACC-02",
        "client_jd_id": "ACC-2026-09-28-002",
        "requirement_from": "Accenture",
        "job_title": "SAP BTP Datasphere & Analytics Specialist",
        "job_status": "Open",
        "action": "CREATE (New Requirement)",
        "demand_received_date": TODAY_DATE,
        "client_poc": "anusha.k@iexcel.co.in",
        "number_of_positions": 2,
        "location": "Hyderabad",
        "overall_experience": "5-8 years",
        "mandatory_skills": "SAP BTP; Datasphere; SAC Analytics Cloud; HANA Cloud",
        "work_mode": "Hybrid",
        "employment_type": "Contract"
    },
    {
        "job_id": "REQ-2026-09-28-ACC-03",
        "client_jd_id": "ACC-2026-09-28-003",
        "requirement_from": "Accenture",
        "job_title": "SAP FSCM Treasury & Risk Management Consultant",
        "job_status": "Open",
        "action": "CREATE (New Requirement)",
        "demand_received_date": TODAY_DATE,
        "client_poc": "anusha.k@iexcel.co.in",
        "number_of_positions": 3,
        "location": "Pune",
        "overall_experience": "6-9 years",
        "mandatory_skills": "SAP FSCM; TRM; Treasury Management; Cash & Liquidity",
        "work_mode": "On-site",
        "employment_type": "Contract"
    },
    # Accenture - 2 REOPENED Requirements (Hold -> Open)
    {
        "job_id": "REQ-2026-09-08-ACC-010",
        "client_jd_id": "ACCENTURE-2026-09-08-010",
        "requirement_from": "Accenture",
        "job_title": "SAP FSCM Treasury and Risk",
        "job_status": "Open",
        "action": "UPDATE (Reopened from Hold to Open)",
        "demand_received_date": TODAY_DATE,
        "client_poc": "anusha.k@iexcel.co.in",
        "number_of_positions": 2,
        "location": "BDC6F - SEZ",
        "overall_experience": "5-8 years",
        "mandatory_skills": "SAP FSCM Treasury and Risk Management",
        "work_mode": "On-site",
        "employment_type": "Contract"
    },
    {
        "job_id": "REQ-2026-09-09-ACC-004",
        "client_jd_id": "ACCENTURE-2026-09-09-004",
        "requirement_from": "Accenture",
        "job_title": "SAP HCM Time Management",
        "job_status": "Open",
        "action": "UPDATE (Reopened from Hold to Open)",
        "demand_received_date": TODAY_DATE,
        "client_poc": "anusha.k@iexcel.co.in",
        "number_of_positions": 1,
        "location": "Pune",
        "overall_experience": "4-7 years",
        "mandatory_skills": "SAP HCM; Time Management; Payroll Integration",
        "work_mode": "Hybrid",
        "employment_type": "Contract"
    }
]


def ingest_today_data():
    conn_mf = sqlite3.connect(DB_METAFORGE)
    conn_mem = sqlite3.connect(DB_PROCESSED)

    now_iso = f"{TODAY_DATE}T18:26:00+05:30"

    print(f"================ INGESTING TODAY'S (28/09/2026) BATCH ================")

    for item in today_requirements:
        sys_job_id = item["job_id"]
        client = item["requirement_from"]

        # Store in metaforge_requirements table
        conn_mf.execute(
            "INSERT OR REPLACE INTO metaforge_requirements (job_id, payload_json, created_at) VALUES (?, ?, ?)",
            (sys_job_id, json.dumps(item), now_iso)
        )

        # Store in requirement_memory table
        conn_mem.execute(
            "INSERT INTO requirement_memory (requirement_from, job_title_norm, payload_json, source_graph_id, created_at) VALUES (?, ?, ?, ?, ?)",
            (client, item["job_title"].lower(), json.dumps(item), f"TODAY-{sys_job_id}", now_iso)
        )

        print(f"[{client}] {item['action']} -> Req ID: {item['client_jd_id']} | Title: {item['job_title']} | Status: {item['job_status']}")

    conn_mf.commit()
    conn_mem.commit()
    conn_mf.close()
    conn_mem.close()

    print("\nSUCCESS: Today's (28/09/2026) batch successfully registered into database and live UI!")

if __name__ == "__main__":
    ingest_today_data()
