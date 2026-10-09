"""
Unit and integration tests for Issue 1 and Issue 2:
1. Same requirement, changed or unchanged JD:
   - Match by client identity + Request ID
   - Changed JD: in-place update, job_id and dashboard position unchanged, new version saved, previous JD preserved
   - Identical JD: duplicate, no new requirement or version
   - Missing fields: do not overwrite or delete existing fields
2. Multiple requirements in one email:
   - Independent extraction and processing of every requirement
   - An existing Request ID never skips or condenses other requirements
   - Traceability and idempotency preserved across mixed (changed, unchanged, new) requirements
"""

import json
import sqlite3
import tempfile
from pathlib import Path
from typing import Any, Dict

import pytest

from metaforge_api import _ensure_schema, _sqlite_upsert, check_jd_diff
from processed_store import ProcessedStore


@pytest.fixture
def test_env(tmp_path: Path):
    """Set up isolated SQLite databases for testing without touching production data."""
    processed_db_path = tmp_path / "processed_messages.db"
    metaforge_db_path = tmp_path / "metaforge_requirements.db"

    # Initialize metaforge schema
    conn_mf = sqlite3.connect(metaforge_db_path)
    _ensure_schema(conn_mf)
    conn_mf.close()

    # Initialize store
    store = ProcessedStore(processed_db_path)

    return {
        "store": store,
        "processed_db_path": processed_db_path,
        "metaforge_db_path": metaforge_db_path,
        "tmp_path": tmp_path,
    }


def test_issue1_same_requirement_changed_jd_creates_version_and_updates_inplace(test_env):
    """
    Test Issue 1:
    - Initial insert: creates v1.
    - Changed JD with same client identity + Request ID: updates in place, preserves job_id, creates v2, preserves v1.
    """
    store = test_env["store"]
    mf_db = test_env["metaforge_db_path"]

    # 1. Initial requirement
    req_v1 = {
        "client_jd_id": "REQ-101",
        "requirement_from": "ltts",
        "job_title": "Senior Python Backend Engineer",
        "location": "Bangalore",
        "monthly_budget": "150000",
        "mandatory_skills": ["Python", "FastAPI", "PostgreSQL"],
        "job_description": "We need a Senior Python Developer with 5+ years experience in FastAPI and PostgreSQL.",
        "graphMessageId": "msg-v1-001",
    }

    job_id_1 = _sqlite_upsert(req_v1, str(mf_db))
    assert job_id_1, "Expected valid job_id allocated"
    assert "-" in job_id_1 or "_" in job_id_1

    # Verify v1 saved in metaforge_requirements and jd_versions
    conn = sqlite3.connect(mf_db)
    conn.row_factory = sqlite3.Row
    row1 = conn.execute("SELECT * FROM metaforge_requirements WHERE job_id = ?", (job_id_1,)).fetchone()
    assert row1 is not None
    p1 = json.loads(row1["payload_json"])
    assert p1.get("jd_version") == 1
    assert len(p1.get("version_history", [])) == 1

    cur_vers = conn.execute("SELECT * FROM jd_versions WHERE requirement_id = ? ORDER BY version_number ASC", (job_id_1,)).fetchall()
    assert len(cur_vers) == 1
    assert cur_vers[0]["version_number"] == 1
    assert "FastAPI" in cur_vers[0]["job_description"]
    conn.close()

    # 2. Updated requirement with changed JD (budget & JD text changed)
    req_v2 = {
        "client_jd_id": "REQ-101",
        "requirement_from": "ltts",
        "job_title": "Senior Python Backend Engineer",
        "location": "Bangalore",
        "monthly_budget": "180000",  # Changed budget
        "mandatory_skills": ["Python", "FastAPI", "PostgreSQL", "Docker"],  # Added skill
        "job_description": "REVISED: We need a Senior Python Developer with FastAPI, PostgreSQL, and Docker experience.",
        "graphMessageId": "msg-v2-002",
    }

    job_id_2 = _sqlite_upsert(req_v2, str(mf_db))
    # Must preserve exact same internal job_id (in-place update)
    assert job_id_2 == job_id_1, f"Expected in-place update keeping job_id {job_id_1}, got {job_id_2}"

    # Verify database state
    conn = sqlite3.connect(mf_db)
    conn.row_factory = sqlite3.Row
    # Check only 1 row exists in metaforge_requirements
    all_rows = conn.execute("SELECT * FROM metaforge_requirements").fetchall()
    assert len(all_rows) == 1, f"Expected 1 record in metaforge_requirements, found {len(all_rows)}"

    updated_row = all_rows[0]
    assert updated_row["job_id"] == job_id_1
    p2 = json.loads(updated_row["payload_json"])
    assert p2.get("monthly_budget") == "180000"
    assert p2.get("jd_version") == 2
    assert len(p2.get("version_history", [])) == 2

    # Verify version 1 is preserved and version 2 is recorded in jd_versions table
    vers_rows = conn.execute("SELECT * FROM jd_versions WHERE requirement_id = ? ORDER BY version_number ASC", (job_id_1,)).fetchall()
    assert len(vers_rows) == 2
    v1_rec, v2_rec = vers_rows[0], vers_rows[1]
    assert v1_rec["version_number"] == 1
    assert "FastAPI and PostgreSQL." in v1_rec["job_description"]
    assert v2_rec["version_number"] == 2
    assert "REVISED: We need a Senior Python Developer" in v2_rec["job_description"]
    assert v2_rec["source_email_id"] == "msg-v2-002"
    conn.close()


def test_issue1_same_requirement_unchanged_jd_treated_as_duplicate(test_env):
    """
    Test Issue 1:
    - If JD is identical, treat as duplicate.
    - Do not create a new requirement record or a new version.
    """
    mf_db = test_env["metaforge_db_path"]

    req_initial = {
        "client_jd_id": "REQ-202",
        "requirement_from": "accenture",
        "job_title": "Java Cloud Developer",
        "location": "Hyderabad",
        "monthly_budget": "120000",
        "mandatory_skills": ["Java", "Spring Boot", "AWS"],
        "job_description": "Looking for Java Spring Boot developer with AWS expertise.",
        "graphMessageId": "msg-dup-001",
    }

    job_id = _sqlite_upsert(req_initial, str(mf_db))
    assert job_id

    # Send identical requirement (duplicate email)
    req_duplicate = {
        "client_jd_id": "REQ-202",
        "requirement_from": "accenture",
        "job_title": "Java Cloud Developer",
        "location": "Hyderabad",
        "monthly_budget": "120000",
        "mandatory_skills": ["Java", "Spring Boot", "AWS"],
        "job_description": "Looking for Java Spring Boot developer with AWS expertise.",  # Identical JD
        "graphMessageId": "msg-dup-002",
    }

    job_id_dup = _sqlite_upsert(req_duplicate, str(mf_db))
    assert job_id_dup == job_id

    # Verify no new row or version was created
    conn = sqlite3.connect(mf_db)
    conn.row_factory = sqlite3.Row
    count_reqs = conn.execute("SELECT COUNT(*) FROM metaforge_requirements").fetchone()[0]
    count_vers = conn.execute("SELECT COUNT(*) FROM jd_versions WHERE requirement_id = ?", (job_id,)).fetchone()[0]
    row = conn.execute("SELECT payload_json FROM metaforge_requirements WHERE job_id = ?", (job_id,)).fetchone()
    p = json.loads(row["payload_json"])

    assert count_reqs == 1, "Duplicate email must not create new requirement record"
    assert count_vers == 1, "Duplicate identical email must not create new version"
    assert p.get("jd_version") == 1
    assert len(p.get("version_history", [])) == 1
    conn.close()


def test_issue1_missing_fields_do_not_erase_existing_data(test_env):
    """
    Test Issue 1:
    - Missing/blank fields in update email must NOT overwrite or erase existing values.
    """
    mf_db = test_env["metaforge_db_path"]

    req_full = {
        "client_jd_id": "REQ-303",
        "requirement_from": "ltts",
        "job_title": "DevOps Engineer",
        "location": "Pune",
        "monthly_budget": "140000",
        "work_mode": "Hybrid",
        "mandatory_skills": ["Kubernetes", "Terraform", "CI/CD"],
        "job_description": "DevOps engineer with Kubernetes and Terraform experience.",
        "graphMessageId": "msg-full-001",
    }
    job_id = _sqlite_upsert(req_full, str(mf_db))

    # Follow-up email mentions only changed budget and revised JD, omits location and work_mode
    req_partial = {
        "client_jd_id": "REQ-303",
        "requirement_from": "ltts",
        "monthly_budget": "160000",
        "job_description": "DevOps engineer with Kubernetes, Terraform, and Helm experience.",
        "graphMessageId": "msg-partial-002",
    }
    _sqlite_upsert(req_partial, str(mf_db))

    conn = sqlite3.connect(mf_db)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT payload_json FROM metaforge_requirements WHERE job_id = ?", (job_id,)).fetchone()
    p = json.loads(row["payload_json"])

    # Verify existing fields were not deleted
    assert p.get("job_title") == "DevOps Engineer"
    assert p.get("location") == "Pune"
    assert p.get("work_mode") == "Hybrid"
    assert p.get("mandatory_skills") == ["Kubernetes", "Terraform", "CI/CD"]
    # Verify updated fields took effect
    assert p.get("monthly_budget") == "160000"
    assert "Helm" in p.get("job_description")
    assert p.get("jd_version") == 2
    conn.close()


def test_issue2_multiple_requirements_in_one_email_processed_independently(test_env):
    """
    Test Issue 2:
    Single email containing 3 distinct requirements:
    - Req 1: REQ-A (existing, JD unchanged) -> skipped as duplicate, no new version.
    - Req 2: REQ-B (existing, JD changed) -> updated in place, version 2 created, version 1 preserved.
    - Req 3: REQ-C (genuinely new) -> created as new requirement, version 1 created.
    - Verify an existing Request ID never skips or stops the other requirements.
    - Verify source-email traceability and idempotency.
    """
    store = test_env["store"]
    mf_db = test_env["metaforge_db_path"]

    # Step 1: Pre-populate existing REQ-A and REQ-B
    req_a_orig = {
        "client_jd_id": "REQ-A",
        "requirement_from": "ltts",
        "job_title": "Frontend React Engineer",
        "location": "Bangalore",
        "job_description": "Frontend React Engineer with TypeScript.",
        "graphMessageId": "msg-seed-A",
    }
    job_id_a = _sqlite_upsert(req_a_orig, str(mf_db))
    store.register_requirement_identity(
        identity="ltts:req-a",
        client="ltts",
        client_jd_id="REQ-A",
        city="bangalore",
        profile={"client": "ltts", "client_jd_id": "REQ-A", "title": "Frontend React Engineer", "city": "bangalore"},
        state="stored",
        original_record_ref=job_id_a,
    )

    req_b_orig = {
        "client_jd_id": "REQ-B",
        "requirement_from": "ltts",
        "job_title": "Backend Go Developer",
        "location": "Chennai",
        "monthly_budget": "110000",
        "job_description": "Backend Go Developer with gRPC.",
        "graphMessageId": "msg-seed-B",
    }
    job_id_b = _sqlite_upsert(req_b_orig, str(mf_db))
    store.register_requirement_identity(
        identity="ltts:req-b",
        client="ltts",
        client_jd_id="REQ-B",
        city="chennai",
        profile={"client": "ltts", "client_jd_id": "REQ-B", "title": "Backend Go Developer", "city": "chennai"},
        state="stored",
        original_record_ref=job_id_b,
    )

    # Step 2: Now simulate an incoming email containing all 3 requirements:
    email_gid = "msg-batch-999"
    email_inet_id = "inet-batch-999@company.com"

    # Multi-requirement payloads extracted from the email
    incoming_payloads = [
        # Req 1: REQ-A (unchanged JD)
        {
            "client_jd_id": "REQ-A",
            "requirement_from": "ltts",
            "job_title": "Frontend React Engineer",
            "location": "Bangalore",
            "job_description": "Frontend React Engineer with TypeScript.",
            "graphMessageId": email_gid,
            "internetMessageId": email_inet_id,
        },
        # Req 2: REQ-B (changed JD: budget increased and new skill)
        {
            "client_jd_id": "REQ-B",
            "requirement_from": "ltts",
            "job_title": "Backend Go Developer",
            "location": "Chennai",
            "monthly_budget": "140000",
            "job_description": "Backend Go Developer with gRPC and Kubernetes.",
            "graphMessageId": email_gid,
            "internetMessageId": email_inet_id,
        },
        # Req 3: REQ-C (brand new requirement)
        {
            "client_jd_id": "REQ-C",
            "requirement_from": "ltts",
            "job_title": "Data Scientist",
            "location": "Hyderabad",
            "monthly_budget": "200000",
            "job_description": "Data Scientist with PyTorch and NLP experience.",
            "graphMessageId": email_gid,
            "internetMessageId": email_inet_id,
        },
    ]

    synced_count = 0
    updated_count = 0

    # Execute independent per-requirement processing loop (as done in Step 4)
    for p in incoming_payloads:
        cjd = p["client_jd_id"]
        prof = {
            "client": p["requirement_from"],
            "client_jd_id": cjd,
            "title": p["job_title"],
            "city": p["location"].lower(),
        }

        # Step 4 check
        decision, matched_cand, score, deciding_rule = store.find_requirement_duplicate(prof)

        if decision == "DUPLICATE" and matched_cand:
            target_ref = matched_cand.get("original_record_ref") or cjd
            updated_ok = store.update_requirement_fields_in_place(
                requirement_id=target_ref,
                incoming_payload=p,
                source_email_id=email_gid,
                metaforge_db_path=mf_db,
            )
            if updated_ok:
                updated_count += 1
        else:
            # New requirement!
            new_job_id = _sqlite_upsert(p, str(mf_db))
            store.register_requirement_identity(
                identity=f"ltts:{cjd.lower()}",
                client=p["requirement_from"],
                client_jd_id=cjd,
                city=p["location"].lower(),
                profile=prof,
                state="stored",
                original_record_ref=new_job_id,
                graph_id=email_gid,
            )
            synced_count += 1

    # Verify counts:
    # REQ-A was duplicate & unchanged -> 0 update, 0 new
    # REQ-B was changed -> 1 updated
    # REQ-C was new -> 1 synced
    assert updated_count == 1, f"Expected exactly 1 updated requirement (REQ-B), got {updated_count}"
    assert synced_count == 1, f"Expected exactly 1 new synced requirement (REQ-C), got {synced_count}"

    # Verify database contents
    conn = sqlite3.connect(mf_db)
    conn.row_factory = sqlite3.Row

    # 1. Check REQ-A: still version 1, unchanged
    row_a = conn.execute("SELECT * FROM metaforge_requirements WHERE client_jd_id = 'REQ-A'").fetchone()
    assert row_a is not None
    pa = json.loads(row_a["payload_json"])
    assert pa.get("jd_version") == 1
    assert len(pa.get("version_history", [])) == 1

    # 2. Check REQ-B: updated in-place to version 2, job_id preserved, version 1 preserved
    row_b = conn.execute("SELECT * FROM metaforge_requirements WHERE client_jd_id = 'REQ-B'").fetchone()
    assert row_b is not None
    assert row_b["job_id"] == job_id_b
    pb = json.loads(row_b["payload_json"])
    assert pb.get("monthly_budget") == "140000"
    assert pb.get("jd_version") == 2
    assert len(pb.get("version_history", [])) == 2
    vers_b = conn.execute("SELECT * FROM jd_versions WHERE client_jd_id = 'REQ-B' ORDER BY version_number ASC").fetchall()
    assert len(vers_b) == 2
    assert "gRPC." in vers_b[0]["job_description"]
    assert "Kubernetes." in vers_b[1]["job_description"]

    # 3. Check REQ-C: created as new requirement with version 1
    row_c = conn.execute("SELECT * FROM metaforge_requirements WHERE client_jd_id = 'REQ-C'").fetchone()
    assert row_c is not None
    assert row_c["job_id"] != job_id_a
    assert row_c["job_id"] != job_id_b
    pc = json.loads(row_c["payload_json"])
    assert pc.get("job_title") == "Data Scientist"
    assert pc.get("jd_version") == 1
    assert pc.get("graphMessageId") == email_gid
    assert pc.get("internetMessageId") == email_inet_id
    vers_c = conn.execute("SELECT * FROM jd_versions WHERE client_jd_id = 'REQ-C'").fetchall()
    assert len(vers_c) == 1

    # Total requirements in DB should now be exactly 3
    total_reqs = conn.execute("SELECT COUNT(*) FROM metaforge_requirements").fetchone()[0]
    assert total_reqs == 3, f"Expected 3 requirements in metaforge_requirements, found {total_reqs}"
    conn.close()


def test_issue2_idempotency_on_repeated_email(test_env):
    """
    Test Issue 2 Idempotency:
    Re-processing the exact same email produces 0 new records and 0 new versions.
    """
    store = test_env["store"]
    mf_db = test_env["metaforge_db_path"]

    # Initial run with 2 requirements
    email_gid = "msg-batch-idemp"
    reqs = [
        {
            "client_jd_id": "REQ-X",
            "requirement_from": "ltts",
            "job_title": "QA Engineer",
            "location": "Pune",
            "job_description": "Manual and automation QA.",
            "graphMessageId": email_gid,
        },
        {
            "client_jd_id": "REQ-Y",
            "requirement_from": "ltts",
            "job_title": "Security Analyst",
            "location": "Mumbai",
            "job_description": "Cybersecurity and penetration testing.",
            "graphMessageId": email_gid,
        },
    ]

    for p in reqs:
        jid = _sqlite_upsert(p, str(mf_db))
        store.register_requirement_identity(
            identity=f"ltts:{p['client_jd_id'].lower()}",
            client="ltts",
            client_jd_id=p["client_jd_id"],
            city=p["location"].lower(),
            profile={"client": "ltts", "client_jd_id": p["client_jd_id"], "title": p["job_title"], "city": p["location"].lower()},
            state="stored",
            original_record_ref=jid,
            graph_id=email_gid,
        )

    # Re-run identical email
    second_synced = 0
    second_updated = 0
    for p in reqs:
        cjd = p["client_jd_id"]
        prof = {"client": "ltts", "client_jd_id": cjd, "title": p["job_title"], "city": p["location"].lower()}
        decision, matched_cand, _, _ = store.find_requirement_duplicate(prof)
        if decision == "DUPLICATE" and matched_cand:
            target_ref = matched_cand.get("original_record_ref") or cjd
            updated_ok = store.update_requirement_fields_in_place(
                requirement_id=target_ref,
                incoming_payload=p,
                source_email_id=email_gid,
                metaforge_db_path=mf_db,
            )
            if updated_ok:
                second_updated += 1
        else:
            second_synced += 1

    assert second_synced == 0, "Idempotent re-run must not create new requirements"
    assert second_updated == 0, "Idempotent re-run must not create new versions for identical JDs"

    conn = sqlite3.connect(mf_db)
    count_reqs = conn.execute("SELECT COUNT(*) FROM metaforge_requirements").fetchone()[0]
    count_vers = conn.execute("SELECT COUNT(*) FROM jd_versions").fetchone()[0]
    assert count_reqs == 2
    assert count_vers == 2
    conn.close()


def test_issue2_process_single_message_pipeline_mixed_requirements(test_env, monkeypatch):
    """
    End-to-end pipeline test for process_single_message:
    Ensure that an email with existing unchanged, existing changed, and new requirements
    processes all of them independently without skipping or short-circuiting.
    """
    from unittest.mock import MagicMock
    from config import Settings
    from metaforge_api import IdAllocator
    from main import process_single_message

    store = test_env["store"]
    mf_db = test_env["metaforge_db_path"]

    # 1. Seed existing requirement REQ-OLD-1 and REQ-OLD-2
    req_seed1 = {
        "client_jd_id": "REQ-OLD-1",
        "requirement_from": "ltts",
        "job_title": "React Frontend Developer",
        "location": "Bangalore",
        "monthly_budget": "100000",
        "job_description": "React Developer with Redux.",
        "graphMessageId": "seed-001",
    }
    job_id_1 = _sqlite_upsert(req_seed1, str(mf_db))
    store.register_requirement_identity(
        identity="ltts:req-old-1",
        client="ltts",
        client_jd_id="REQ-OLD-1",
        city="bangalore",
        profile={"client": "ltts", "client_jd_id": "REQ-OLD-1", "title": "React Frontend Developer", "city": "bangalore"},
        state="stored",
        original_record_ref=job_id_1,
    )

    req_seed2 = {
        "client_jd_id": "REQ-OLD-2",
        "requirement_from": "ltts",
        "job_title": "Node Backend Developer",
        "location": "Pune",
        "monthly_budget": "110000",
        "job_description": "Node Developer with Express.",
        "graphMessageId": "seed-002",
    }
    job_id_2 = _sqlite_upsert(req_seed2, str(mf_db))
    store.register_requirement_identity(
        identity="ltts:req-old-2",
        client="ltts",
        client_jd_id="REQ-OLD-2",
        city="pune",
        profile={"client": "ltts", "client_jd_id": "REQ-OLD-2", "title": "Node Backend Developer", "city": "pune"},
        state="stored",
        original_record_ref=job_id_2,
    )

    # 2. Prepare incoming email containing 3 requirements:
    # - REQ-OLD-1: unchanged JD -> duplicate, skipped
    # - REQ-OLD-2: changed JD (budget 140k + NestJS) -> updated in place, v2
    # - REQ-NEW-3: brand new requirement -> created, v1
    incoming_extracted_payloads = [
        {
            "client_jd_id": "REQ-OLD-1",
            "requirement_from": "ltts",
            "job_title": "React Frontend Developer",
            "location": "Bangalore",
            "monthly_budget": "100000",
            "job_description": "React Developer with Redux.",
        },
        {
            "client_jd_id": "REQ-OLD-2",
            "requirement_from": "ltts",
            "job_title": "Node Backend Developer",
            "location": "Pune",
            "monthly_budget": "140000",
            "job_description": "Node Developer with Express and NestJS.",
        },
        {
            "client_jd_id": "REQ-NEW-3",
            "requirement_from": "ltts",
            "job_title": "Flutter Mobile Developer",
            "location": "Chennai",
            "monthly_budget": "130000",
            "job_description": "Flutter developer for mobile apps.",
        },
    ]

    # Mock extract_and_map to return our 3 payloads
    monkeypatch.setattr(
        "main.extract_and_map",
        lambda *args, **kwargs: ("ok", incoming_extracted_payloads, "Email text with 3 demands"),
    )
    # Allow test sender
    monkeypatch.setattr("main.is_sender_allowlisted", lambda addr: True)

    settings = MagicMock(spec=Settings)
    settings.metaforge_mode = "sqlite"
    settings.metaforge_sqlite_path = str(mf_db)
    settings.ingest_start_datetime = None
    settings.similarity_weights = None
    settings.similarity_thresholds = None

    # Ensure send_to_metaforge in main writes to mf_db
    monkeypatch.setattr("main.send_to_metaforge", lambda p, s: _sqlite_upsert(p, str(mf_db)))

    raw_message = {
        "id": "batch-msg-e2e-001",
        "internetMessageId": "<e2e-001@ltts.com>",
        "conversationId": "CONV-E2E-001",
        "subject": "Multiple demands: REQ-OLD-1, REQ-OLD-2, REQ-NEW-3",
        "from": {"emailAddress": {"address": "demands@ltts.com"}},
        "receivedDateTime": "2026-10-09T10:00:00Z",
        "body": {"content": "Demand table with 3 roles."},
    }

    allocator = IdAllocator(str(mf_db))
    total_processed = process_single_message(
        raw=raw_message,
        token="test-token",
        mailbox="demands@ltts.com",
        settings=settings,
        allocator=allocator,
        store=store,
        skip_classifier=True,
    )

    # Exactly 1 new requirement synced (REQ-NEW-3); REQ-OLD-2 was updated in-place (no new row)
    assert total_processed == 1

    # Verify database state
    conn = sqlite3.connect(mf_db)
    conn.row_factory = sqlite3.Row

    # REQ-OLD-1: still version 1
    p1 = json.loads(conn.execute("SELECT payload_json FROM metaforge_requirements WHERE client_jd_id = 'REQ-OLD-1'").fetchone()[0])
    assert p1.get("jd_version") == 1

    # REQ-OLD-2: in-place updated to version 2, job_id preserved
    r2 = conn.execute("SELECT job_id, payload_json FROM metaforge_requirements WHERE client_jd_id = 'REQ-OLD-2'").fetchone()
    assert r2["job_id"] == job_id_2
    p2 = json.loads(r2["payload_json"])
    assert p2.get("monthly_budget") == "140000"
    assert p2.get("jd_version") == 2
    assert len(p2.get("version_history", [])) == 2

    # REQ-NEW-3: created as new record, version 1
    r3 = conn.execute("SELECT job_id, payload_json FROM metaforge_requirements WHERE client_jd_id = 'REQ-NEW-3'").fetchone()
    assert r3 is not None
    assert r3["job_id"] not in (job_id_1, job_id_2)
    p3 = json.loads(r3["payload_json"])
    assert p3.get("job_title") == "Flutter Mobile Developer"
    assert p3.get("jd_version") == 1
    assert p3.get("graphMessageId") == "batch-msg-e2e-001"
    assert p3.get("internetMessageId") == "<e2e-001@ltts.com>"

    # Total in metaforge_requirements is exactly 3
    total = conn.execute("SELECT COUNT(*) FROM metaforge_requirements").fetchone()[0]
    assert total == 3
    conn.close()


def test_issue1_dashboard_position_and_id_remain_unchanged_on_jd_update(test_env):
    """
    Test Issue 1:
    - Requirement ID and dashboard position remain strictly unchanged when JD is updated.
    - An update to an earlier requirement does NOT move it to the top of the dashboard.
    """
    from ui.db import fetch_all_records

    mf_db = test_env["metaforge_db_path"]
    pm_db = test_env["processed_db_path"]

    ui_cfg = {
        "db_paths": [str(pm_db), str(mf_db)],
        "id_normalization_rule": {"strip_whitespace": True, "uppercase": True},
    }

    # Create 3 sequential requirements on same date
    jid_1 = _sqlite_upsert({
        "client_jd_id": "POS-001",
        "requirement_from": "ltts",
        "job_title": "Position 1 Role",
        "first_arrival_at": "2026-10-09T08:00:00Z",
        "job_description": "JD text 1",
    }, str(mf_db))

    jid_2 = _sqlite_upsert({
        "client_jd_id": "POS-002",
        "requirement_from": "ltts",
        "job_title": "Position 2 Role",
        "first_arrival_at": "2026-10-09T09:00:00Z",
        "job_description": "JD text 2",
    }, str(mf_db))

    jid_3 = _sqlite_upsert({
        "client_jd_id": "POS-003",
        "requirement_from": "ltts",
        "job_title": "Position 3 Role",
        "first_arrival_at": "2026-10-09T10:00:00Z",
        "job_description": "JD text 3",
    }, str(mf_db))

    # Initial dashboard records (descending order by date/seq/arrival)
    recs_before = fetch_all_records(ui_cfg)
    order_before = [r["req_id"] for r in recs_before]
    assert order_before == [jid_3, jid_2, jid_1], f"Expected descending order, got {order_before}"
    assert order_before.index(jid_1) == 2, "POS-001 should be at position index 2"

    # Now update POS-001 (the earliest requirement) with changed JD at a later time
    jid_1_updated = _sqlite_upsert({
        "client_jd_id": "POS-001",
        "requirement_from": "ltts",
        "job_title": "Position 1 Role",
        "monthly_budget": "200000",
        "job_description": "UPDATED JD text 1 with higher budget",
    }, str(mf_db))

    # Verify Requirement ID is unchanged
    assert jid_1_updated == jid_1, f"Internal Requirement ID must remain unchanged! Expected {jid_1}, got {jid_1_updated}"

    # Verify Dashboard order is strictly unchanged
    # (Clear cache to ensure fresh query)
    from ui.db import _CACHE_RECORDS
    _CACHE_RECORDS.clear()

    recs_after = fetch_all_records(ui_cfg)
    order_after = [r["req_id"] for r in recs_after]
    assert order_after == [jid_3, jid_2, jid_1], f"Dashboard position must remain unchanged! Got {order_after}"
    assert order_after.index(jid_1) == 2, "POS-001 must remain at position index 2, not jumped to top"

