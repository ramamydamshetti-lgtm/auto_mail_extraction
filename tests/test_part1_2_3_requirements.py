"""
Regression test suite for Part 1 (Internal requirement ID format & ordering),
Part 2 (Real client-provided ID extraction & display), and
Part 3 (Duplicate detection via client-provided ID).
"""

import os
import sys
sys.path.insert(0, os.path.abspath("."))
import json
import sqlite3
import pytest
from datetime import datetime, date, timezone
from pathlib import Path

from metaforge_api import IdAllocator
from processed_store import ProcessedStore
from requirement_parser import extract_client_jd_id_from_text, parse_requirements_from_email
from ui.db import fetch_all_records, _format_internal_id, _extract_real_client_jd_id
from config import Settings


@pytest.fixture
def tmp_db_paths(tmp_path):
    pm_path = tmp_path / "processed_messages.db"
    mf_path = tmp_path / "metaforge_requirements.db"
    return str(pm_path), str(mf_path)


def test_part1_internal_id_format_and_arrival_sequence(tmp_db_paths):
    """
    Part 1 Test: Internal requirement IDs follow YYYY-MM-DD-NNN,
    NNN resets to 001 per day, sequence reflects arrival order regardless of processing time.
    """
    pm_path, mf_path = tmp_db_paths
    allocator = IdAllocator(mf_path)

    arrival_day = date(2026, 9, 30)
    id1 = allocator.next_job_id(arrival_day)
    id2 = allocator.next_job_id(arrival_day)
    id3 = allocator.next_job_id(arrival_day)

    assert id1 == "2026/09/30-001"
    assert id2 == "2026/09/30-002"
    assert id3 == "2026/09/30-003"

    next_day = date(2026, 10, 1)
    id_next_day = allocator.next_job_id(next_day)
    assert id_next_day == "2026/10/01-001"
    allocator.close()


def test_part1_ui_ordering_most_recent_arrival_top(tmp_path):
    """
    Part 1 Test: UI lists requirements in strict reverse-chronological order of arrival
    (most recent arrival at top).
    """
    mf_path = tmp_path / "metaforge_requirements.db"
    conn = sqlite3.connect(mf_path)
    conn.execute(
        "CREATE TABLE metaforge_requirements (job_id TEXT PRIMARY KEY, payload_json TEXT, created_at TEXT)"
    )

    reqs = [
        ("2026-09-30-001", "2026-09-30T09:00:00Z", "Role 1"),
        ("2026-09-30-002", "2026-09-30T10:00:00Z", "Role 2"),
        ("2026-09-30-003", "2026-09-30T11:00:00Z", "Role 3"),
    ]

    for job_id, arrival_iso, title in reqs:
        p = {
            "job_id": job_id,
            "job_title": title,
            "demand_received_date": arrival_iso[:10],
            "email_received_iso": arrival_iso
        }
        conn.execute(
            "INSERT INTO metaforge_requirements VALUES (?, ?, ?)",
            (job_id, json.dumps(p), arrival_iso)
        )
    conn.commit()
    conn.close()

    cfg = {"db_paths": [str(mf_path)]}
    records = fetch_all_records(cfg)

    assert len(records) == 3
    # Top record must be the most recent arrival (2026-09-30-003 at 11:00)
    assert records[0]["req_id"] == "2026/09/30-003"
    assert records[1]["req_id"] == "2026/09/30-002"
    assert records[2]["req_id"] == "2026/09/30-001"


def test_part2_extract_client_jd_id_multi_vendor_formats():
    """
    Part 2 Test: Real client-provided IDs extracted for multiple client formats (Accenture, Deloitte, Fidelity).
    Returns None if no client ID is present in source text.
    """
    # Accenture format (numeric-dash)
    acc_text = "Accenture Open Demands: Request-ID 203421-1 for Embedded C++ Developer"
    assert extract_client_jd_id_from_text("Open Demands", acc_text) == "203421-1"

    # Deloitte format (DLTJP)
    deloitte_text = "Urgent requirement DLTJP00059663 for SAP FICO Consultant"
    assert extract_client_jd_id_from_text("Urgent Req - DLTJP00059663", deloitte_text) == "DLTJP00059663"

    # Fidelity / Generic RQ format (RQ056293)
    fidelity_text = "Requisition RQ056293: Control & Monitoring Specialist"
    assert extract_client_jd_id_from_text("Fidelity Req RQ056293", fidelity_text) == "RQ056293"

    # Text WITHOUT client-provided ID -> must return None (never fabricate placeholder IDs)
    no_id_text = "Looking for Java Full Stack Developer with 5+ years experience in Bangalore"
    assert extract_client_jd_id_from_text("Java Developer Needed", no_id_text) is None


def test_part2_ui_display_client_jd_id_linking():
    """
    Part 2 Test: UI displays {internal_id} ([{client_jd_id}]) when client_jd_id exists,
    and only {internal_id} when client_jd_id is None.
    """
    p_with_cid = {"job_id": "2026-09-30-001", "client_jd_id": "203421-1"}
    p_no_cid = {"job_id": "2026-09-30-002", "client_jd_id": None}

    cid_extracted = _extract_real_client_jd_id(p_with_cid, "2026-09-30-001")
    assert cid_extracted == "203421-1"

    cid_null = _extract_real_client_jd_id(p_no_cid, "2026-09-30-002")
    assert cid_null is None


def test_part3_duplicate_detection_same_client_jd_id(tmp_db_paths):
    """
    Part 3 Test 1: Two emails with the SAME real client_jd_id and no status change
    -> confirm only ONE requirement row exists, duplicate creation is skipped.
    """
    pm_path, _ = tmp_db_paths
    store = ProcessedStore(pm_path)

    payload1 = {
        "job_id": "2026-09-30-001",
        "client_jd_id": "203421-1",
        "requirement_from": "Accenture",
        "job_title": "Embedded C++",
        "job_status": "open",
        "graphMessageId": "MSG-001"
    }

    action1, res1 = store.evaluate_client_requirement_action(
        client_jd_id="203421-1",
        requirement_from="Accenture",
        payload=payload1
    )
    assert action1 == "CREATE"

    # Second email with identical client_jd_id and no status change
    payload2 = dict(payload1)
    payload2["job_id"] = "2026-09-30-002"
    payload2["graphMessageId"] = "MSG-002"

    action2, res2 = store.evaluate_client_requirement_action(
        client_jd_id="203421-1",
        requirement_from="Accenture",
        payload=payload2
    )
    assert action2 == "SKIP"

    # Confirm database only contains 1 record in client_requirements
    conn = sqlite3.connect(pm_path)
    count = conn.execute("SELECT COUNT(*) FROM client_requirements WHERE client_jd_id = '203421-1'").fetchone()[0]
    assert count == 1
    conn.close()


def test_part3_duplicate_detection_status_change_hold(tmp_db_paths):
    """
    Part 3 Test 2: Repeat email with same client_jd_id containing 'hold'
    -> confirm existing row updates status to 'hold', no new row created, status_history entry logged.
    """
    pm_path, _ = tmp_db_paths
    store = ProcessedStore(pm_path)

    payload1 = {
        "job_id": "2026-09-30-001",
        "client_jd_id": "203421-1",
        "requirement_from": "Accenture",
        "job_title": "Embedded C++",
        "job_status": "open",
        "graphMessageId": "MSG-001"
    }
    store.evaluate_client_requirement_action(
        client_jd_id="203421-1",
        requirement_from="Accenture",
        payload=payload1
    )

    # Second email for same client_jd_id with status change to 'hold'
    payload_hold = dict(payload1)
    payload_hold["job_status"] = "hold"
    payload_hold["graphMessageId"] = "MSG-002"

    action_hold, _ = store.evaluate_client_requirement_action(
        client_jd_id="203421-1",
        requirement_from="Accenture",
        payload=payload_hold
    )
    assert action_hold == "UPDATE"

    # Confirm only 1 requirement row exists, status is updated to 'hold'
    conn = sqlite3.connect(pm_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT status FROM client_requirements WHERE client_jd_id = '203421-1'").fetchone()
    assert row["status"] == "hold"

    # Confirm status_history log entry exists
    history = conn.execute("SELECT from_status, to_status FROM status_history").fetchall()
    assert len(history) >= 1
    assert history[0]["from_status"] == "open"
    assert history[0]["to_status"] == "hold"
    conn.close()


def test_task2_idexcel_client_resolution_dclient_pclient_unresolved():
    """
    Task 2 Regression Tests:
    1. idexcel.com email with D.client / D-Client -> Deloitte
    2. idexcel.com email with P.client / P-Client -> PwC
    3. idexcel.com email with NEITHER marker -> 'unresolved' (never 'Idexcel' or 'Idexcel (client not identified)')
    """
    from client_detector import detect_client

    # Test 1: D.client (dot separator format found in RQ056293 email text)
    d_match = detect_client("Requirement Intake", "Requirement for Audit & Assurance. D.client details attached.", "recruiter@idexcel.com")
    assert d_match is not None
    assert d_match.display_name == "Deloitte"
    assert d_match.key == "deloitte"

    # Test 1b: D-Client (hyphen format)
    d_dash_match = detect_client("Requirement Intake", "Target account is D-Client for SAP.", "recruiter@idexcel.com")
    assert d_dash_match is not None
    assert d_dash_match.display_name == "Deloitte"

    # Test 2: P-Client / P.client
    p_match = detect_client("Requirement Intake", "Client is P.client for Financial Advisory.", "recruiter@idexcel.com")
    assert p_match is not None
    assert p_match.display_name == "PwC"
    assert p_match.key == "pwc"

    # Test 3: NEITHER marker -> literal string 'unresolved', never 'Idexcel'
    unres_match = detect_client("Requirement Intake", "We need a Python developer for our internal project.", "recruiter@idexcel.com")
    assert unres_match is not None
    assert unres_match.display_name == "unresolved"
    assert unres_match.display_name != "Idexcel"
    assert unres_match.display_name != "Idexcel (client not identified)"


def test_task4_all_clients_internal_id_format_no_prefix(tmp_path):
    """
    Task 4 Test: Requirement IDs for every client (Accenture, LTTS, KPMG, ITC Infotech, PwC, Deloitte)
    follow the exact same YYYY-MM-DD-NNN pattern with NO client-specific prefix.
    """
    import re

    clients = ["Accenture", "LTTS", "KPMG", "ITC Infotech", "PwC", "Deloitte"]
    mf_path = tmp_path / "metaforge_requirements.db"
    allocator = IdAllocator(str(mf_path))

    arrival_date = date(2026, 9, 29)
    generated_ids = []

    for client in clients:
        job_id = allocator.next_job_id(arrival_date)
        generated_ids.append((client, job_id))

    allocator.close()

    # Pattern: strictly YYYY/MM/DD-NNN (e.g. 2026/09/29-001) with NO prefix
    pattern = re.compile(r"^\d{4}/\d{2}/\d{2}-\d{3,}$")

    for client, job_id in generated_ids:
        assert pattern.match(job_id) is not None, f"Client {client} generated invalid ID format: {job_id}"
        # Ensure no client name or prefix appears in the job_id
        for c in ["ACC", "LTTS", "KPMG", "ITC", "PWC", "DELOITTE", "REQ"]:
            assert not job_id.startswith(f"{c}-"), f"Client {client} job_id contains prefix: {job_id}"

    # Verify _format_internal_id normalizes historical client-prefixed IDs to YYYY/MM/DD-NNN
    legacy_examples = [
        ("ACC-2026-09-29-001", "2026/09/29-001"),
        ("LTTS-2026-09-29-024", "2026/09/29-024"),
        ("KPMG-2026-09-29-003", "2026/09/29-003"),
        ("ITC-2026-09-29-004", "2026/09/29-004"),
        ("PWC-2026-09-29-005", "2026/09/29-005"),
        ("DELOITTE-2026-09-29-006", "2026/09/29-006"),
    ]

    for raw, expected in legacy_examples:
        fmt = _format_internal_id(raw)
        assert fmt == expected, f"Failed to format legacy ID {raw}: got {fmt}, expected {expected}"


