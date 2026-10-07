"""
Test suite covering the 9 specific requirements for single-store requirement identity,
cutoff filtering, deduplication, pending review idempotency, and status updates.
All tests use temporary SQLite databases and never touch data/*.db.
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from unittest.mock import patch

import pytest

from config import Settings
from metaforge_api import IdAllocator
from processed_store import ProcessedStore
from models import RequirementItem, RequirementParseResult
from requirement_identity import compute_requirement_identity
from main import process_single_message, get_effective_cutoff_iso
from scripts.cleanup_duplicates import run_cleanup


def query_db(path: str, sql: str, params: tuple = ()) -> list[tuple]:
    """Execute SQL query and guarantee connection is immediately closed."""
    conn = sqlite3.connect(path)
    try:
        cur = conn.execute(sql, params)
        rows = cur.fetchall()
        return rows
    finally:
        conn.close()


def make_test_settings(
    tmpdir: str,
    proc_db_path: str,
    req_db_path: str,
    seq_db_path: str,
    ingest_start: str = "2026-09-01T00:00:00+05:30",
) -> Settings:
    return Settings(
        azure_tenant_id="",
        azure_client_id="",
        azure_client_secret="",
        mailbox_upn="recruitment.application@metaforgeit.com",
        openai_api_key="",
        openai_model="gpt-4o-mini",
        metaforge_api_url="",
        metaforge_requirements_endpoint="",
        metaforge_mode="sqlite",
        metaforge_sqlite_path=req_db_path,
        metaforge_id_db=seq_db_path,
        processed_db=proc_db_path,
        log_level="DEBUG",
        openai_min_confidence=0.0,
        internal_poc_default="offshore demands",
        scheduler_poll_seconds=120,
        scheduler_error_backoff_seconds=30,
        scheduler_heartbeat_path=os.path.join(tmpdir, "scheduler_heartbeat.json"),
        file_listener_enabled=False,
        file_listener_inbox_dir=os.path.join(tmpdir, "inbox"),
        file_listener_archive_dir=os.path.join(tmpdir, "archive"),
        ingest_start_datetime=ingest_start,
        fingerprint_window_days=None,
    )


@pytest.fixture
def temp_env():
    with tempfile.TemporaryDirectory() as tmpdir:
        proc_db_path = os.path.join(tmpdir, "processed_messages.db")
        req_db_path = os.path.join(tmpdir, "metaforge_requirements.db")
        seq_db_path = os.path.join(tmpdir, "metaforge_sequences.db")

        store = ProcessedStore(proc_db_path)
        allocator = IdAllocator(seq_db_path)
        settings = make_test_settings(tmpdir, proc_db_path, req_db_path, seq_db_path)

        yield {
            "tmpdir": tmpdir,
            "proc_db_path": proc_db_path,
            "req_db_path": req_db_path,
            "seq_db_path": seq_db_path,
            "store": store,
            "allocator": allocator,
            "settings": settings,
        }
        allocator.close()
        store.close()


def test_1_email_older_than_cutoff(temp_env):
    """1. Email older than the cutoff: not fetched or processed."""
    store = temp_env["store"]
    settings = temp_env["settings"]
    allocator = temp_env["allocator"]

    # Effective cutoff calculation verifies ISO format >= cutoff
    eff_cutoff = get_effective_cutoff_iso(settings, store)
    assert eff_cutoff is not None
    assert "2026-08-31" in eff_cutoff or "2026-09-01" in eff_cutoff

    # Message dated August 15, 2026 (older than 2026-09-01)
    msg = {
        "id": "old_msg_001",
        "internetMessageId": "<old_001@example.com>",
        "receivedDateTime": "2026-08-15T10:00:00Z",
        "subject": "Accenture Open Demands: Request-ID 200901-1",
        "from": {"emailAddress": {"address": "recruiter@iexcel.co.in", "name": "Recruiter"}},
        "body": {
            "contentType": "html",
            "content": "<table><tr><th>Request-ID</th><th>Status</th></tr><tr><td>200901-1</td><td>Open</td></tr></table>",
        },
    }

    synced = process_single_message(
        raw=msg,
        token="",
        mailbox="recruitment.application@metaforgeit.com",
        settings=settings,
        allocator=allocator,
        store=store,
        skip_classifier=True,
    )

    assert synced == 0

    if os.path.exists(temp_env["req_db_path"]):
        rows = query_db(temp_env["req_db_path"], "SELECT COUNT(*) FROM metaforge_requirements")
        assert rows[0][0] == 0

    rows_pending = query_db(temp_env["proc_db_path"], "SELECT COUNT(*) FROM pending_reviews")
    assert rows_pending[0][0] == 0


def test_2_same_email_fetched_twice(temp_env):
    """2. Same email fetched twice: one record."""
    store = temp_env["store"]
    settings = temp_env["settings"]
    allocator = temp_env["allocator"]

    mock_items = [
        RequirementItem(
            req_id="200902-1",
            raw_status="Open",
            job_title="Senior Java Developer",
            location=["Bangalore"],
            overall_experience="7 years",
            mandatory_skills=["Java", "Spring Boot"],
            client_name="Accenture",
            confidence=1.0,
        )
    ]

    msg = {
        "id": "msg_dup_002",
        "internetMessageId": "<dup_002@example.com>",
        "receivedDateTime": "2026-09-10T10:00:00Z",
        "subject": "Accenture Requirement: Senior Java Developer",
        "from": {"emailAddress": {"address": "recruiter@iexcel.co.in", "name": "Recruiter"}},
        "body": {
            "contentType": "text",
            "content": "Accenture requirement for Senior Java Developer in Bangalore with 7 years experience.",
        },
    }

    with patch("main.parse_requirements_from_email", return_value=RequirementParseResult(requirements=mock_items, overall_confidence=1.0)):
        # Run 1: processes successfully
        synced1 = process_single_message(
            raw=msg,
            token="",
            mailbox="recruitment.application@metaforgeit.com",
            settings=settings,
            allocator=allocator,
            store=store,
            skip_classifier=True,
        )
        assert synced1 == 1

        # Run 2: same email fetched again -> skipped by seen_messages check
        synced2 = process_single_message(
            raw=msg,
            token="",
            mailbox="recruitment.application@metaforgeit.com",
            settings=settings,
            allocator=allocator,
            store=store,
            skip_classifier=True,
        )
        assert synced2 == 0

    rows = query_db(temp_env["req_db_path"], "SELECT job_id, client_jd_id FROM metaforge_requirements")
    assert len(rows) == 1
    assert rows[0][1] == "200902-1"


def test_3_same_requirement_new_email_with_client_id(temp_env):
    """3. Same requirement in a new email (reply/forward, new graph_id), with the same client ID:
    duplicate, no new row, no REQ number used."""
    store = temp_env["store"]
    settings = temp_env["settings"]
    allocator = temp_env["allocator"]

    mock_items = [
        RequirementItem(
            req_id="200903-1",
            raw_status="Open",
            job_title="React Developer",
            location=["Pune"],
            overall_experience="4 years",
            mandatory_skills=["React", "TypeScript"],
            client_name="Accenture",
            confidence=1.0,
        )
    ]

    msg1 = {
        "id": "graph_msg_003_a",
        "internetMessageId": "<orig_003@example.com>",
        "receivedDateTime": "2026-09-10T10:00:00Z",
        "subject": "Accenture Requirement: React Developer",
        "from": {"emailAddress": {"address": "recruiter@iexcel.co.in", "name": "Recruiter"}},
        "body": {"contentType": "text", "content": "Accenture React Developer in Pune, skills: React, TypeScript."},
    }

    msg2 = {
        "id": "graph_msg_003_b",  # New Graph ID (forward or reply)
        "internetMessageId": "<reply_003@example.com>",
        "receivedDateTime": "2026-09-12T14:00:00Z",
        "subject": "Re: Accenture Requirement: React Developer",
        "from": {"emailAddress": {"address": "recruiter@iexcel.co.in", "name": "Recruiter"}},
        "body": {"contentType": "text", "content": "Follow up on Accenture React Developer in Pune, skills: React, TypeScript."},
    }

    with patch("main.parse_requirements_from_email", return_value=RequirementParseResult(requirements=mock_items, overall_confidence=1.0)):
        synced1 = process_single_message(
            raw=msg1,
            token="",
            mailbox="recruitment.application@metaforgeit.com",
            settings=settings,
            allocator=allocator,
            store=store,
            skip_classifier=True,
        )
        assert synced1 == 1

        row = query_db(temp_env["req_db_path"], "SELECT job_id FROM metaforge_requirements")[0]
        first_job_id = row[0]

        # Second email with new graph_id, same requirement
        synced2 = process_single_message(
            raw=msg2,
            token="",
            mailbox="recruitment.application@metaforgeit.com",
            settings=settings,
            allocator=allocator,
            store=store,
            skip_classifier=True,
        )
        assert synced2 == 0  # Duplicate skipped

    # Verify no new row added and REQ allocator was not incremented
    rows = query_db(temp_env["req_db_path"], "SELECT job_id FROM metaforge_requirements")
    assert len(rows) == 1
    assert rows[0][0] == first_job_id

    # Verify times_seen updated in requirement_identity
    ident = compute_requirement_identity(
        client="Accenture",
        client_jd_id="200903-1",
        job_title="React Developer",
        location="Pune",
        experience="4 years",
        mandatory_skills="React, TypeScript",
    )
    rec = store.get_requirement_identity(ident)
    assert rec is not None
    assert rec["times_seen"] == 2
    assert "2026-09-12" in rec["last_seen"]


def test_4_same_content_no_client_id_40_days_later(temp_env):
    """4. Same content, no client ID, 40 days later: duplicate."""
    store = temp_env["store"]
    settings = temp_env["settings"]
    allocator = temp_env["allocator"]

    mock_items = [
        RequirementItem(
            req_id=None,  # No client JD ID!
            raw_status="Open",
            job_title="Embedded Systems Engineer",
            location=["Mysore"],
            experience="5-8 years",
            overall_experience="5-8 years",
            mandatory_skills=["C", "C++", "RTOS"],
            client_name="LTTS",
            confidence=1.0,
        )
    ]

    msg1 = {
        "id": "graph_msg_004_a",
        "internetMessageId": "<orig_004@example.com>",
        "receivedDateTime": "2026-09-02T10:00:00Z",
        "subject": "Opening at LTTS: Embedded Systems Engineer",
        "from": {"emailAddress": {"address": "lead@ltts.com", "name": "LTTS Lead"}},
        "body": {"contentType": "text", "content": "LTTS opening for Embedded Systems Engineer in Mysore, experience: 5-8 years."},
    }

    # 40 days later
    msg2 = {
        "id": "graph_msg_004_b",
        "internetMessageId": "<later_004@example.com>",
        "receivedDateTime": "2026-10-12T10:00:00Z",
        "subject": "Urgent Opening at LTTS: Embedded Systems Engineer",
        "from": {"emailAddress": {"address": "lead@ltts.com", "name": "LTTS Lead"}},
        "body": {"contentType": "text", "content": "Urgent LTTS opening for Embedded Systems Engineer in Mysore, experience: 5-8 years."},
    }

    with patch("main.parse_requirements_from_email", return_value=RequirementParseResult(requirements=mock_items, overall_confidence=1.0)):
        synced1 = process_single_message(
            raw=msg1,
            token="",
            mailbox="recruitment.application@metaforgeit.com",
            settings=settings,
            allocator=allocator,
            store=store,
            skip_classifier=True,
        )
        assert synced1 == 1

        synced2 = process_single_message(
            raw=msg2,
            token="",
            mailbox="recruitment.application@metaforgeit.com",
            settings=settings,
            allocator=allocator,
            store=store,
            skip_classifier=True,
        )
        assert synced2 == 0  # Permanent content hash deduplication!

    rows = query_db(temp_env["req_db_path"], "SELECT job_id FROM metaforge_requirements")
    assert len(rows) == 1

    ident = compute_requirement_identity(
        client="LTTS",
        client_jd_id=None,
        job_title="Embedded Systems Engineer",
        location="Mysore",
        experience="5-8 years",
        mandatory_skills=["C", "C++", "RTOS"],
    )
    rec = store.get_requirement_identity(ident)
    assert rec is not None
    assert rec["times_seen"] == 2


def test_5_two_clients_with_same_id_number(temp_env):
    """5. Two clients with the same ID number: two records."""
    store = temp_env["store"]
    settings = temp_env["settings"]
    allocator = temp_env["allocator"]

    # Accenture with client_jd_id 200964-1
    acc_items = [
        RequirementItem(
            req_id="200964-1",
            raw_status="Open",
            job_title="SAP Consultant",
            location=["Mumbai"],
            overall_experience="6 years",
            mandatory_skills=["SAP FICO"],
            client_name="Accenture",
            confidence=1.0,
        )
    ]
    msg_acc = {
        "id": "graph_msg_005_a",
        "internetMessageId": "<acc_005@example.com>",
        "receivedDateTime": "2026-09-05T10:00:00Z",
        "subject": "Accenture Demand 200964-1",
        "from": {"emailAddress": {"address": "recruiter@iexcel.co.in", "name": "Recruiter"}},
        "body": {"contentType": "text", "content": "Accenture Demand 200964-1 for SAP Consultant in Mumbai."},
    }

    # PWC with identical ID 200964-1 (unpatterned client with explicit label)
    pwc_items = [
        RequirementItem(
            req_id="200964-1",
            raw_status="Open",
            job_title="Audit Specialist",
            location=["Hyderabad"],
            overall_experience="3 years",
            mandatory_skills=["Auditing"],
            client_name="PWC",
            confidence=1.0,
        )
    ]
    msg_pwc = {
        "id": "graph_msg_005_b",
        "internetMessageId": "<pwc_005@example.com>",
        "receivedDateTime": "2026-09-06T10:00:00Z",
        "subject": "PWC Requirement Req ID: 200964-1",
        "from": {"emailAddress": {"address": "recruiter2@iexcel.co.in", "name": "PWC Lead"}},
        "body": {"contentType": "text", "content": "PWC Requirement Req ID: 200964-1 for Audit Specialist in Hyderabad."},
    }

    with patch("main.parse_requirements_from_email", return_value=RequirementParseResult(requirements=acc_items, overall_confidence=1.0)):
        synced_acc = process_single_message(
            raw=msg_acc,
            token="",
            mailbox="recruitment.application@metaforgeit.com",
            settings=settings,
            allocator=allocator,
            store=store,
            skip_classifier=True,
        )
        assert synced_acc == 1

    with patch("main.parse_requirements_from_email", return_value=RequirementParseResult(requirements=pwc_items, overall_confidence=1.0)):
        synced_pwc = process_single_message(
            raw=msg_pwc,
            token="",
            mailbox="recruitment.application@metaforgeit.com",
            settings=settings,
            allocator=allocator,
            store=store,
            skip_classifier=True,
        )
        assert synced_pwc == 1

    rows = query_db(temp_env["req_db_path"], "SELECT client_jd_id, identity FROM metaforge_requirements")
    assert len(rows) == 2
    identities = [r[1] for r in rows]
    assert "accenture:cjd:200964-1" in identities
    assert "pwc:cjd:200964-1" in identities


def test_6_requirement_to_pending_review_rerun_idempotent(temp_env):
    """6. Requirement that went to pending review, then the email is rerun: still one pending row."""
    store = temp_env["store"]
    settings = temp_env["settings"]
    allocator = temp_env["allocator"]

    # Low-confidence item without job title to trigger pending review
    mock_items = [
        RequirementItem(
            req_id="200906-1",
            raw_status="Open",
            job_title="",  # Empty job title -> check_ui_readiness flags critical review!
            location=["Bangalore"],
            overall_experience="5 years",
            mandatory_skills=["Python"],
            client_name="Accenture",
            confidence=0.40,
        )
    ]

    msg = {
        "id": "graph_msg_006",
        "internetMessageId": "<pending_006@example.com>",
        "receivedDateTime": "2026-09-15T10:00:00Z",
        "subject": "Accenture Open Demand Request-ID 200906-1",
        "from": {"emailAddress": {"address": "recruiter@iexcel.co.in", "name": "Recruiter"}},
        "body": {
            "contentType": "text",
            "content": "Accenture opening Request-ID 200906-1, experience 5 years in Bangalore, skills: Python.",
        },
    }

    with patch("main.parse_requirements_from_email", return_value=RequirementParseResult(requirements=mock_items, overall_confidence=0.40)):
        # Run 1
        synced1 = process_single_message(
            raw=msg,
            token="",
            mailbox="recruitment.application@metaforgeit.com",
            settings=settings,
            allocator=allocator,
            store=store,
            skip_classifier=True,
        )
        assert synced1 == 0
        rows1 = query_db(temp_env["proc_db_path"], "SELECT COUNT(*) FROM pending_reviews")
        assert rows1[0][0] == 1

        # Reset seen_messages only for this message ID to simulate a rerun/retry
        conn = sqlite3.connect(temp_env["proc_db_path"])
        conn.execute("DELETE FROM seen_messages WHERE graph_id = 'graph_msg_006'")
        conn.commit()
        conn.close()

        # Run 2: rerun email
        synced2 = process_single_message(
            raw=msg,
            token="",
            mailbox="recruitment.application@metaforgeit.com",
            settings=settings,
            allocator=allocator,
            store=store,
            skip_classifier=True,
        )
        assert synced2 == 0

        # Still exactly one pending review!
        rows2 = query_db(temp_env["proc_db_path"], "SELECT COUNT(*) FROM pending_reviews")
        assert rows2[0][0] == 1


def test_7_duplicate_email_containing_on_hold(temp_env):
    """7. Duplicate email containing 'on hold': status updated, no new row."""
    store = temp_env["store"]
    settings = temp_env["settings"]
    allocator = temp_env["allocator"]

    mock_open = [
        RequirementItem(
            req_id="200907-1",
            raw_status="Open",
            job_title="Solution Architect",
            location=["Chennai"],
            overall_experience="10 years",
            mandatory_skills=["AWS", "Architecture"],
            client_name="Accenture",
            confidence=1.0,
        )
    ]
    msg1 = {
        "id": "graph_msg_007_a",
        "internetMessageId": "<arch_007@example.com>",
        "receivedDateTime": "2026-09-18T10:00:00Z",
        "subject": "Accenture Demand: Solution Architect",
        "from": {"emailAddress": {"address": "recruiter@iexcel.co.in", "name": "Recruiter"}},
        "body": {"contentType": "text", "content": "Accenture Solution Architect in Chennai, 10 years experience."},
    }

    mock_hold = [
        RequirementItem(
            req_id="200907-1",
            raw_status="Hold",
            job_title="Solution Architect",
            location=["Chennai"],
            overall_experience="10 years",
            mandatory_skills=["AWS", "Architecture"],
            client_name="Accenture",
            confidence=1.0,
        )
    ]
    msg2 = {
        "id": "graph_msg_007_b",
        "internetMessageId": "<hold_007@example.com>",
        "receivedDateTime": "2026-09-20T11:00:00Z",
        "subject": "HOLD: Accenture Solution Architect 200907-1",
        "from": {"emailAddress": {"address": "recruiter@iexcel.co.in", "name": "Recruiter"}},
        "body": {"contentType": "text", "content": "Please put requirement 200907-1 on hold immediately, role Solution Architect."},
    }

    with patch("main.parse_requirements_from_email", return_value=RequirementParseResult(requirements=mock_open, overall_confidence=1.0)):
        synced1 = process_single_message(
            raw=msg1,
            token="",
            mailbox="recruitment.application@metaforgeit.com",
            settings=settings,
            allocator=allocator,
            store=store,
            skip_classifier=True,
        )
        assert synced1 == 1

    row = query_db(temp_env["req_db_path"], "SELECT job_id, payload_json FROM metaforge_requirements")[0]
    orig_job_id = row[0]

    with patch("main.parse_requirements_from_email", return_value=RequirementParseResult(requirements=mock_hold, overall_confidence=1.0)):
        synced2 = process_single_message(
            raw=msg2,
            token="",
            mailbox="recruitment.application@metaforgeit.com",
            settings=settings,
            allocator=allocator,
            store=store,
            skip_classifier=True,
        )
        assert synced2 == 0

    rows = query_db(temp_env["req_db_path"], "SELECT job_id, payload_json FROM metaforge_requirements")
    assert len(rows) == 1
    assert rows[0][0] == orig_job_id
    payload = json.loads(rows[0][1])
    assert payload.get("job_status") == "hold"


def test_8_two_identical_roles_in_one_email(temp_env):
    """8. Two identical roles in one email: stored once."""
    store = temp_env["store"]
    settings = temp_env["settings"]
    allocator = temp_env["allocator"]

    # Email contains two duplicate items for the same role/client ID
    mock_items = [
        RequirementItem(
            req_id="200908-1",
            raw_status="Open",
            job_title="Python Developer",
            location=["Bangalore"],
            overall_experience="5 years",
            mandatory_skills=["Python", "Django"],
            client_name="Accenture",
            confidence=1.0,
        ),
        RequirementItem(
            req_id="200908-1",
            raw_status="Open",
            job_title="Python Developer",
            location=["Bangalore"],
            overall_experience="5 years",
            mandatory_skills=["Python", "Django"],
            client_name="Accenture",
            confidence=1.0,
        ),
    ]

    msg = {
        "id": "graph_msg_008",
        "internetMessageId": "<multi_008@example.com>",
        "receivedDateTime": "2026-09-22T10:00:00Z",
        "subject": "Accenture Multiple Positions",
        "from": {"emailAddress": {"address": "recruiter@iexcel.co.in", "name": "Recruiter"}},
        "body": {"contentType": "text", "content": "Accenture positions for Python Developer in Bangalore."},
    }

    with patch("main.parse_requirements_from_email", return_value=RequirementParseResult(requirements=mock_items, overall_confidence=1.0)):
        synced = process_single_message(
            raw=msg,
            token="",
            mailbox="recruitment.application@metaforgeit.com",
            settings=settings,
            allocator=allocator,
            store=store,
            skip_classifier=True,
        )
        assert synced == 1

    rows = query_db(temp_env["req_db_path"], "SELECT job_id, client_jd_id FROM metaforge_requirements")
    assert len(rows) == 1
    assert rows[0][1] == "200908-1"


def test_9_cleanup_dry_run_lists_known_pairs(temp_env):
    """9. Cleanup dry run lists the known pairs (LTTS PLM Mysore, Accenture SAP CO Management Accounting Mumbai) as duplicates."""
    tmpdir = temp_env["tmpdir"]
    req_db_path = temp_env["req_db_path"]
    proc_db_path = temp_env["proc_db_path"]

    # Set up tables in req_db_path
    conn_mf = sqlite3.connect(req_db_path)
    conn_mf.execute("""
        CREATE TABLE IF NOT EXISTS metaforge_requirements (
            job_id TEXT PRIMARY KEY,
            payload_json TEXT,
            created_at TEXT,
            client_jd_id TEXT,
            updated_at TEXT,
            field_change_history TEXT,
            identity TEXT
        )
    """)
    # Pair 1: LTTS PLM Mysore (same content, no client ID)
    p1 = {
        "job_id": "2026-09-29-004",
        "requirement_from": "LTTS",
        "job_title": "PLM Consultant",
        "location": "Mysore",
        "overall_experience": "4-7 yrs",
        "mandatory_skills": "Windchill, PLM",
        "email_received_iso": "2026-09-29T10:00:00Z",
    }
    p2 = {
        "job_id": "2026/09/11-018",
        "requirement_from": "LTTS",
        "job_title": "PLM Consultant",
        "location": "Mysore",
        "overall_experience": "4-7 yrs",
        "mandatory_skills": "Windchill, PLM",
        "email_received_iso": "2026-09-11T08:00:00Z",
    }
    # Pair 2: Accenture SAP CO Management Accounting Mumbai (first in metaforge_requirements)
    p3 = {
        "job_id": "2026/09/22-109",
        "client_jd_id": "200968-1",
        "requirement_from": "Accenture",
        "job_title": "SAP CO Management Accounting Specialist",
        "location": "Mumbai",
        "overall_experience": "5-8 yrs",
        "mandatory_skills": "SAP CO, Controlling",
        "email_received_iso": "2026-09-22T09:00:00Z",
    }

    conn_mf.execute("""
        INSERT INTO metaforge_requirements (job_id, payload_json, created_at, client_jd_id, updated_at, identity)
        VALUES (?, ?, ?, ?, ?, ?)
    """, ("2026-09-29-004", json.dumps(p1), "2026-09-29T10:00:00Z", None, "2026-09-29T10:00:00Z", None))
    conn_mf.execute("""
        INSERT INTO metaforge_requirements (job_id, payload_json, created_at, client_jd_id, updated_at, identity)
        VALUES (?, ?, ?, ?, ?, ?)
    """, ("2026/09/11-018", json.dumps(p2), "2026-09-11T08:00:00Z", None, "2026-09-11T08:00:00Z", None))
    conn_mf.execute("""
        INSERT INTO metaforge_requirements (job_id, payload_json, created_at, client_jd_id, updated_at, identity)
        VALUES (?, ?, ?, ?, ?, ?)
    """, ("2026/09/22-109", json.dumps(p3), "2026-09-22T09:00:00Z", "200968-1", "2026-09-22T09:00:00Z", None))
    conn_mf.commit()
    conn_mf.close()

    # Insert the Accenture pair duplicate in client_requirements in proc_db_path
    conn_pm = sqlite3.connect(proc_db_path)
    p_client_req = {
        "job_id": "200968-1",
        "client_jd_id": "200968-1",
        "requirement_from": "Accenture",
        "job_title": "SAP CO Management Accounting Specialist",
        "location": "Mumbai",
        "overall_experience": "5-8 yrs",
        "mandatory_skills": "SAP CO, Controlling",
        "email_received_iso": "2026-09-23T11:00:00Z",
    }
    conn_pm.execute("""
        INSERT INTO client_requirements
        (client_jd_id, requirement_from, status, details_hash, payload_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        "200968-1",
        "Accenture",
        "open",
        "hash123",
        json.dumps(p_client_req),
        "2026-09-23T11:00:00Z",
        "2026-09-23T11:00:00Z",
    ))
    conn_pm.commit()
    conn_pm.close()

    # Run cleanup in DRY-RUN mode (apply=False)
    summary = run_cleanup(
        data_dir=tmpdir,
        cutoff_iso="2026-09-01T00:00:00+05:30",
        apply=False,
    )

    assert summary["scanned"] == 4
    assert summary["duplicates"] == 2
    assert summary["unique_identities"] == 2
    assert summary["active_kept"] == 2

    # Verify both known pairs detected
    known_names = [k["name"] for k in summary["known_pairs"]]
    assert "LTTS PLM Mysore" in known_names
    assert "Accenture SAP CO Management Accounting Mumbai" in known_names

    # Verify nothing was deleted in dry-run mode
    rows = query_db(req_db_path, "SELECT COUNT(*) FROM metaforge_requirements")
    assert rows[0][0] == 3
