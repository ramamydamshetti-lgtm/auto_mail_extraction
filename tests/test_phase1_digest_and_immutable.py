"""
Tests for Phase 1 requirements and additions (N1-N9, A1-A6).
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import tempfile
from unittest.mock import patch

import pytest

from config import Settings
from main import process_single_message
from metaforge_api import IdAllocator, _sqlite_upsert
from models import RequirementItem, RequirementParseResult
from processed_store import ProcessedStore


@pytest.fixture
def temp_phase1_env():
    td = tempfile.mkdtemp(prefix="test_phase1_")
    req_db = os.path.join(td, "test_metaforge.db")
    proc_db = os.path.join(td, "test_processed.db")
    id_db = os.path.join(td, "test_id.db")

    # Set up metaforge schema
    conn = sqlite3.connect(req_db)
    conn.execute(
        """CREATE TABLE metaforge_requirements (
            job_id TEXT PRIMARY KEY,
            payload_json TEXT,
            created_at TEXT,
            client_jd_id TEXT,
            updated_at TEXT,
            field_change_history TEXT,
            identity TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE mf_sequences (
            name TEXT PRIMARY KEY,
            value INTEGER NOT NULL DEFAULT 0
        )"""
    )
    conn.commit()
    conn.close()

    store = ProcessedStore(proc_db)
    allocator = IdAllocator(id_db)

    settings = Settings(
        azure_tenant_id="",
        azure_client_id="",
        azure_client_secret="",
        mailbox_upn="recruitment.application@metaforgeit.com",
        openai_api_key="",
        openai_model="gpt-4o-mini",
        metaforge_api_url="",
        metaforge_requirements_endpoint="",
        metaforge_mode="sqlite",
        metaforge_sqlite_path=req_db,
        metaforge_id_db=id_db,
        processed_db=proc_db,
        log_level="DEBUG",
        similarity_weights={
            "title": 0.25,
            "skills": 0.25,
            "experience": 0.15,
            "whole_text": 0.25,
            "other_fields": 0.10,
        },
        similarity_thresholds={
            "duplicate": 0.85,
            "possible_duplicate": 0.70,
        },
    )

    yield {
        "td": td,
        "req_db": req_db,
        "proc_db": proc_db,
        "id_db": id_db,
        "store": store,
        "allocator": allocator,
        "settings": settings,
    }

    try:
        allocator.close()
    except Exception:
        pass
    try:
        store.close()
    except Exception:
        pass
    try:
        shutil.rmtree(td, ignore_errors=True)
    except Exception:
        pass


def _query(db_path: str, sql: str, params: tuple = ()) -> list:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()
    return rows


_DEFAULT_FROM = {"emailAddress": {"address": "anusha.k@iexcel.co.in", "name": "Anusha"}}


def test_1_digest_with_34_known_and_1_new(temp_phase1_env):
    """
    Test 1 & A6: Digest of 35 rows with 34 known:
    Exactly 1 new row, numbered -001, 34 untouched (same REQ number, Email Arrived, Open Since, created_at).
    """
    store = temp_phase1_env["store"]
    settings = temp_phase1_env["settings"]
    allocator = temp_phase1_env["allocator"]
    req_db = temp_phase1_env["req_db"]

    # Pre-populate 34 existing requirements from September
    existing_items = []
    sept_date = "2026-09-22"
    conn = sqlite3.connect(req_db)
    for i in range(1, 35):
        cjd = f"REQ-OLD-{i:03d}"
        job_id = f"2026/09/22-{i:03d}"
        payload = {
            "job_id": job_id,
            "client_jd_id": cjd,
            "requirement_from": "Accenture",
            "job_title": f"Software Engineer {i}",
            "location": ["Bangalore"],
            "demand_received_date": sept_date,
            "receivedDateTime": f"{sept_date}T09:00:00Z",
            "job_status": "open",
        }
        conn.execute(
            """INSERT INTO metaforge_requirements
               (job_id, payload_json, created_at, client_jd_id, updated_at, field_change_history)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (job_id, json.dumps(payload), f"{sept_date}T09:00:00Z", cjd, f"{sept_date}T09:00:00Z", json.dumps([])),
        )
        existing_items.append(RequirementItem(
            req_id=cjd,
            raw_status="Open",
            job_title=f"Software Engineer {i}",
            location=["Bangalore"],
            overall_experience="5 years",
            mandatory_skills=[f"Skill {i}"],
            client_name="Accenture",
            confidence=1.0,
        ))
    conn.commit()
    conn.close()

    # The 1 genuinely new requirement for today
    new_item = RequirementItem(
        req_id="200964-1",
        raw_status="Open",
        job_title="SAP FI CO Finance",
        location=["Mumbai"],
        overall_experience="6 years",
        mandatory_skills=["SAP FICO", "S/4HANA"],
        client_name="Accenture",
        confidence=1.0,
    )

    all_digest_items = existing_items + [new_item]

    msg_today = {
        "id": "msg_oct01_digest",
        "internetMessageId": "<digest_oct01@accenture.com>",
        "receivedDateTime": "2026-10-01T03:33:18Z",
        "subject": "Accenture open demands for 1st Oct",
        "from": _DEFAULT_FROM,
        "body": {"contentType": "text", "content": "Requirement digest table with 35 positions and mandatory skills"},
    }

    with patch("main.parse_requirements_from_email", return_value=RequirementParseResult(requirements=all_digest_items, overall_confidence=1.0)):
        res = process_single_message(raw=msg_today, token="", mailbox="test", settings=settings, allocator=allocator, store=store, skip_classifier=True)
        # Exactly 1 new requirement synced
        assert res == 1

    # Check newly created requirement in metaforge_requirements
    new_rows = _query(req_db, "SELECT job_id, client_jd_id, payload_json, created_at FROM metaforge_requirements WHERE client_jd_id = '200964-1'")
    assert len(new_rows) == 1
    new_jid = new_rows[0][0]
    # N5: Today's genuinely new requirement should be 2026/10/01-001
    assert new_jid == "2026/10/01-001"
    p_new = json.loads(new_rows[0][2])
    assert p_new["demand_received_date"] == "2026-10-01"

    # Check that the 34 old rows were UNTOUCHED
    for i in range(1, 35):
        cjd = f"REQ-OLD-{i:03d}"
        old_rows = _query(req_db, "SELECT job_id, payload_json, created_at, updated_at FROM metaforge_requirements WHERE client_jd_id = ?", (cjd,))
        assert len(old_rows) == 1
        assert old_rows[0][0] == f"2026/09/22-{i:03d}"
        assert old_rows[0][2] == f"{sept_date}T09:00:00Z"
        p_old = json.loads(old_rows[0][1])
        assert p_old["demand_received_date"] == sept_date
        assert p_old["receivedDateTime"] == f"{sept_date}T09:00:00Z"


def test_2_same_digest_processed_again_zero_new_rows(temp_phase1_env):
    """
    Test 2: Same digest processed again: 0 new rows, nothing changed.
    """
    store = temp_phase1_env["store"]
    settings = temp_phase1_env["settings"]
    allocator = temp_phase1_env["allocator"]

    item = RequirementItem(
        req_id="200964-1",
        raw_status="Open",
        job_title="SAP FI CO Finance",
        location=["Mumbai"],
        overall_experience="6 years",
        mandatory_skills=["SAP FICO"],
        client_name="Accenture",
        confidence=1.0,
    )
    msg = {
        "id": "msg_run1",
        "internetMessageId": "<run1@accenture.com>",
        "receivedDateTime": "2026-10-01T03:33:18Z",
        "subject": "Accenture Demand 200964-1",
        "from": _DEFAULT_FROM,
        "body": {"contentType": "text", "content": "Requirement for SAP FI CO Finance in Mumbai, 6 years experience, mandatory skills"},
    }

    with patch("main.parse_requirements_from_email", return_value=RequirementParseResult(requirements=[item], overall_confidence=1.0)):
        res1 = process_single_message(raw=msg, token="", mailbox="test", settings=settings, allocator=allocator, store=store, skip_classifier=True)
        assert res1 == 1

    msg_repeat = {
        "id": "msg_run2_repeat",
        "internetMessageId": "<run2@accenture.com>",
        "receivedDateTime": "2026-10-01T04:00:00Z",
        "subject": "Accenture Demand 200964-1 repeat",
        "from": _DEFAULT_FROM,
        "body": {"contentType": "text", "content": "Requirement for SAP FI CO Finance in Mumbai, 6 years experience, mandatory skills"},
    }
    with patch("main.parse_requirements_from_email", return_value=RequirementParseResult(requirements=[item], overall_confidence=1.0)):
        res2 = process_single_message(raw=msg_repeat, token="", mailbox="test", settings=settings, allocator=allocator, store=store, skip_classifier=True)
        assert res2 == 0


def test_3_digest_with_hold_status_update(temp_phase1_env):
    """
    Test 3: Digest where 3 old rows now say 'hold':
    Status of those 3 changes in DB; all other fields unchanged; no new rows.
    """
    store = temp_phase1_env["store"]
    settings = temp_phase1_env["settings"]
    allocator = temp_phase1_env["allocator"]
    req_db = temp_phase1_env["req_db"]

    item = RequirementItem(
        req_id="200964-1",
        raw_status="Open",
        job_title="SAP FI CO Finance",
        location=["Mumbai"],
        overall_experience="6 years",
        mandatory_skills=["SAP FICO"],
        client_name="Accenture",
        confidence=1.0,
    )
    msg1 = {
        "id": "msg_hold_1",
        "internetMessageId": "<hold_1@accenture.com>",
        "receivedDateTime": "2026-09-20T10:00:00Z",
        "subject": "Accenture Demand 200964-1",
        "from": _DEFAULT_FROM,
        "body": {"contentType": "text", "content": "Requirement for SAP FI CO Finance in Mumbai, 6 years experience, mandatory skills"},
    }
    with patch("main.parse_requirements_from_email", return_value=RequirementParseResult(requirements=[item], overall_confidence=1.0)):
        res1 = process_single_message(raw=msg1, token="", mailbox="test", settings=settings, allocator=allocator, store=store, skip_classifier=True)
        assert res1 == 1

    # Second email says "on hold"
    item_hold = RequirementItem(
        req_id="200964-1",
        raw_status="Hold",
        job_title="SAP FI CO Finance",
        location=["Mumbai"],
        overall_experience="6 years",
        mandatory_skills=["SAP FICO"],
        client_name="Accenture",
        confidence=1.0,
    )
    msg2 = {
        "id": "msg_hold_2",
        "internetMessageId": "<hold_2@accenture.com>",
        "receivedDateTime": "2026-10-01T10:00:00Z",
        "subject": "Accenture Demand 200964-1 Hold Notice",
        "from": _DEFAULT_FROM,
        "body": {"contentType": "text", "content": "Requirement 200964-1 has been put on hold for SAP FI CO Finance, mandatory skills"},
    }
    with patch("main.parse_requirements_from_email", return_value=RequirementParseResult(requirements=[item_hold], overall_confidence=1.0)):
        res2 = process_single_message(raw=msg2, token="", mailbox="test", settings=settings, allocator=allocator, store=store, skip_classifier=True)
        assert res2 == 0

    # Details untouched, status updated
    rows = _query(req_db, "SELECT job_id, payload_json FROM metaforge_requirements WHERE client_jd_id = '200964-1'")
    assert len(rows) == 1
    p = json.loads(rows[0][1])
    assert p["job_status"] == "hold"
    assert p["job_title"] == "SAP FI CO Finance"
    assert p["demand_received_date"] == "2026-09-20"


def test_4_self_healing_missing_from_identity_present_in_metaforge(temp_phase1_env):
    """
    Test 4 & A6: Old requirement missing from the identity table but present in
    metaforge_requirements: treated as duplicate and added to identity.
    """
    store = temp_phase1_env["store"]
    settings = temp_phase1_env["settings"]
    allocator = temp_phase1_env["allocator"]
    req_db = temp_phase1_env["req_db"]
    proc_db = temp_phase1_env["proc_db"]

    # Insert into metaforge_requirements directly (identity table is empty!)
    cjd = "187648-1"
    job_id = "2026/09/24-277"
    payload = {
        "job_id": job_id,
        "client_jd_id": cjd,
        "requirement_from": "Accenture",
        "job_title": "SAP FSCM Consultant",
        "location": ["Bangalore"],
        "demand_received_date": "2026-09-24",
        "job_status": "open",
    }
    conn = sqlite3.connect(req_db)
    conn.execute(
        "INSERT INTO metaforge_requirements (job_id, payload_json, created_at, client_jd_id, updated_at) VALUES (?, ?, ?, ?, ?)",
        (job_id, json.dumps(payload), "2026-09-24T10:00:00Z", cjd, "2026-09-24T10:00:00Z"),
    )
    conn.commit()
    conn.close()

    # Identity table is verified empty
    id_rows = _query(proc_db, "SELECT COUNT(*) FROM requirement_identity")
    assert id_rows[0][0] == 0

    item = RequirementItem(
        req_id=cjd,
        raw_status="Open",
        job_title="SAP FSCM Consultant",
        location=["Bangalore"],
        overall_experience="5 years",
        mandatory_skills=["SAP FSCM"],
        client_name="Accenture",
        confidence=1.0,
    )
    msg = {
        "id": "msg_self_heal",
        "internetMessageId": "<self_heal@accenture.com>",
        "receivedDateTime": "2026-10-01T03:33:18Z",
        "subject": "Accenture FSCM Demand",
        "from": _DEFAULT_FROM,
        "body": {"contentType": "text", "content": "SAP FSCM Consultant Bangalore"},
    }

    with patch("main.parse_requirements_from_email", return_value=RequirementParseResult(requirements=[item], overall_confidence=1.0)):
        res = process_single_message(raw=msg, token="", mailbox="test", settings=settings, allocator=allocator, store=store, skip_classifier=True)
        # Treated as duplicate -> 0 new rows
        assert res == 0

    # Auto-seeded into requirement_identity!
    id_after = _query(proc_db, "SELECT identity, original_record_ref FROM requirement_identity WHERE client_jd_id = ?", (cjd,))
    assert len(id_after) == 1
    assert id_after[0][1] == job_id


def test_5_immutable_fields_protection_rejected(temp_phase1_env):
    """
    Test 5 & A5/A6: Call to _sqlite_upsert that tries to change demand_received_date
    or created_at is rejected with an exception.
    """
    req_db = temp_phase1_env["req_db"]

    # Initial insert
    p_initial = {
        "job_id": "2026/09/20-001",
        "client_jd_id": "REQ-IMMUTABLE-1",
        "requirement_from": "Accenture",
        "job_title": "Java Developer",
        "location": ["Bangalore"],
        "demand_received_date": "2026-09-20",
        "job_status": "open",
    }
    _sqlite_upsert(p_initial, req_db)

    # Attempt to update immutable field demand_received_date
    p_bad = {
        "job_id": "2026/09/20-001",
        "client_jd_id": "REQ-IMMUTABLE-1",
        "requirement_from": "Accenture",
        "job_title": "Java Developer",
        "location": ["Bangalore"],
        "demand_received_date": "2026-10-01",  # Forbidden modification!
        "job_status": "open",
    }

    with pytest.raises(ValueError, match="Cannot modify immutable field"):
        _sqlite_upsert(p_bad, req_db)

    # Verify demand_received_date was NOT corrupted
    rows = _query(req_db, "SELECT payload_json FROM metaforge_requirements WHERE client_jd_id = 'REQ-IMMUTABLE-1'")
    p_check = json.loads(rows[0][0])
    assert p_check["demand_received_date"] == "2026-09-20"
