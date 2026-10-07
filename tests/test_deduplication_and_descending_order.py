import os
import json
import sqlite3
import tempfile
from pathlib import Path

from ui.db import fetch_all_records
from ui.app import filter_and_sort_records
from processed_store import ProcessedStore


def test_no_duplicate_requirements_and_in_place_modification():
    """
    User requirement:
    - Should not store duplicate requirements (store only once).
    - If changes occur, modify at same requirement, not create duplicate requirements.
    - Updated in UI and database.
    """
    tmpdir = tempfile.mkdtemp()
    try:
        tmp_path = Path(tmpdir)
        mf_db = tmp_path / "metaforge_requirements.db"
        proc_db = tmp_path / "processed_messages.db"

        # Create metaforge_requirements table with an initial requirement
        conn_mf = sqlite3.connect(mf_db)
        conn_mf.execute("""
            CREATE TABLE metaforge_requirements (
                job_id TEXT PRIMARY KEY,
                payload_json TEXT,
                created_at TEXT,
                client_jd_id TEXT,
                updated_at TEXT,
                field_change_history TEXT,
                identity TEXT,
                req_date TEXT,
                seq INTEGER,
                former_job_id TEXT,
                former_client_id TEXT
            )
        """)
        init_payload = {
            "job_id": "2026/10/01-007",
            "client_jd_id": "RQ056291",
            "requirement_from": "Deloitte",
            "job_title": "Azure Agentic AI Platform Engineer",
            "location": None,
            "overall_experience": None,
            "job_status": "open",
            "first_arrival_at": "2026-10-01T11:34:34Z",
        }
        conn_mf.execute(
            "INSERT INTO metaforge_requirements (job_id, client_jd_id, payload_json, created_at, req_date, seq) VALUES (?, ?, ?, ?, ?, ?)",
            ("2026/10/01-007", "RQ056291", json.dumps(init_payload), "2026-10-01T11:34:34Z", "2026/10/01", 7),
        )
        conn_mf.commit()
        conn_mf.close()

        # Init processed_store
        store = ProcessedStore(proc_db)

        # Incoming update (e.g. reply email with locations and experience)
        incoming_profile = {
            "client": "unresolved",
            "client_jd_id": "RQ056291",
            "city": "bangalore",
            "title": "Azure Agentic AI",
            "text_fingerprint": "12345",
        }

        # Check duplicate detection finds the existing metaforge requirement despite client="unresolved"
        decision, matched_cand, score, rule = store.find_requirement_duplicate(incoming_profile)
        assert decision == "DUPLICATE", f"Expected DUPLICATE, got {decision}"
        assert matched_cand["client_jd_id"] == "RQ056291"
        assert matched_cand["original_record_ref"] == "2026/10/01-007"

        # Apply in-place modification
        update_payload = {
            "client_jd_id": "RQ056291",
            "location": "Bengaluru, Mumbai",
            "overall_experience": "around 4-7 yrs",
            "job_status": "open",
        }
        updated = store.update_requirement_fields_in_place(
            requirement_id="2026/10/01-007",
            incoming_payload=update_payload,
            source_email_id="test_graph_123",
            metaforge_db_path=mf_db,
        )
        assert updated is True

        # Verify metaforge_requirements updated in place
        conn_mf = sqlite3.connect(mf_db)
        conn_mf.row_factory = sqlite3.Row
        updated_row = conn_mf.execute("SELECT * FROM metaforge_requirements WHERE job_id = ?", ("2026/10/01-007",)).fetchone()
        conn_mf.close()

        p_up = json.loads(updated_row["payload_json"])
        assert p_up["location"] == "Bengaluru, Mumbai"
        assert p_up["overall_experience"] == "around 4-7 yrs"
        assert p_up["requirement_from"] == "Deloitte"

        hist = json.loads(updated_row["field_change_history"])
        assert len(hist) == 2
        assert hist[0]["field"] == "location"
        assert hist[0]["new_value"] == "Bengaluru, Mumbai"
        assert hist[1]["field"] == "overall_experience"
        assert hist[1]["new_value"] == "around 4-7 yrs"

        # Verify UI fetch_all_records aggregates only ONCE
        cfg = {"db_paths": [str(mf_db), str(proc_db)]}
        records = fetch_all_records(cfg)
        rq_records = [r for r in records if r.get("client_jd_id") == "RQ056291"]
        assert len(rq_records) == 1, f"Expected 1 record, got {len(rq_records)}"
        rec = rq_records[0]
        assert rec["req_id"] == "2026/10/01-007"
        assert rec["payload"]["location"] == "Bengaluru, Mumbai"
        assert rec["payload"]["overall_experience"] == "around 4-7 yrs"
        assert rec["payload"]["requirement_from"] == "Deloitte"

        store.close()
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_requirement_order_strictly_descending():
    """
    User requirement:
    - Requirement order should be always in descending order (means new requirement should be on top).
    """
    records = [
        {"req_id": "2026/10/01-007", "payload": {"job_id": "2026/10/01-007"}},
        {"req_id": "2026/10/06-001", "payload": {"job_id": "2026/10/06-001"}},
        {"req_id": "2026/10/06-008", "payload": {"job_id": "2026/10/06-008"}},
        {"req_id": "2026/10/05-011", "payload": {"job_id": "2026/10/05-011"}},
        {"req_id": "2026/10/06-005", "payload": {"job_id": "2026/10/06-005"}},
    ]

    sorted_res = filter_and_sort_records(records, q="", client="", status="", sort="req_id", order="desc")
    order = [r["req_id"] for r in sorted_res]

    expected = [
        "2026/10/06-008",
        "2026/10/06-005",
        "2026/10/06-001",
        "2026/10/05-011",
        "2026/10/01-007",
    ]
    assert order == expected, f"Expected {expected}, got {order}"
