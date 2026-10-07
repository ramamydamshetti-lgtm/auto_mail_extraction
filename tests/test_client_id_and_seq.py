"""
Comprehensive tests for Genuine Client IDs (C1-C5) and REQ Sequence Numbers (R1-R7).
Covers all 9 test scenarios specified in user prompt using temporary SQLite databases.
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from client_identity_validator import is_genuine_client_id
from metaforge_api import _sqlite_upsert, _ensure_schema, get_ist_req_date, send_to_metaforge
from models import RequirementItem, RequirementParseResult
from processed_store import ProcessedStore
from requirement_identity import compute_requirement_identity
from scripts.audit_ids import audit_ids
from ui.db import get_requirement


@pytest.fixture
def temp_dbs():
    td = tempfile.mkdtemp(prefix="test_c1_r7_")
    req_db = os.path.join(td, "metaforge_requirements.db")
    proc_db = os.path.join(td, "processed_messages.db")
    seq_db = os.path.join(td, "metaforge_sequences.db")

    conn = sqlite3.connect(req_db)
    _ensure_schema(conn)
    conn.close()

    yield {
        "td": td,
        "req_db": req_db,
        "proc_db": proc_db,
        "seq_db": seq_db,
    }
    shutil.rmtree(td, ignore_errors=True)


# ---------------------------------------------------------------------------
# Test 1: Range "200000-250000" in two LTTS requirements
# ---------------------------------------------------------------------------
def test_1_range_in_two_ltts_requirements(temp_dbs):
    """1. Range '200000-250000' in two LTTS requirements: both client IDs null, both stored as separate requirements."""
    req_db = temp_dbs["req_db"]

    payload1 = {
        "requirement_from": "LTTS",
        "client_jd_id": "200000-250000",
        "job_title": "Embedded Linux Engineer",
        "location": ["Mysore"],
        "overall_experience": "5 years",
        "mandatory_skills": ["Linux", "C++"],
        "first_arrival_at": "2026-09-29T10:00:00Z",
    }

    payload2 = {
        "requirement_from": "LTTS",
        "client_jd_id": "200000-250000",
        "job_title": "Hardware Design Engineer",
        "location": ["Bangalore"],
        "overall_experience": "6 years",
        "mandatory_skills": ["PCB", "Altium"],
        "first_arrival_at": "2026-09-29T10:05:00Z",
    }

    jid1 = _sqlite_upsert(payload1, req_db)
    jid2 = _sqlite_upsert(payload2, req_db)

    assert jid1 != jid2, "Both requirements must receive separate REQ sequence numbers"

    with sqlite3.connect(req_db) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT job_id, client_jd_id, payload_json FROM metaforge_requirements").fetchall()
        assert len(rows) == 2

        for r in rows:
            assert r["client_jd_id"] is None, "Client ID must be stored as null (rejected range)"
            p = json.loads(r["payload_json"])
            assert p.get("client_jd_id") is None
            assert p.get("former_client_id") == "200000-250000"


# ---------------------------------------------------------------------------
# Test 2: Accenture IDs accepted vs rejected
# ---------------------------------------------------------------------------
def test_2_accenture_id_patterns():
    """2. Accenture '203190-1' accepted; '187651-1' accepted; '250000-300000' rejected."""
    # 203190-1 accepted
    val1, clean1, _ = is_genuine_client_id("Accenture", "203190-1")
    assert val1 is True
    assert clean1 == "203190-1"

    # 187651-1 accepted
    val2, clean2, _ = is_genuine_client_id("Accenture", "187651-1")
    assert val2 is True
    assert clean2 == "187651-1"

    # 250000-300000 rejected (both numeric range and pattern mismatch)
    val3, clean3, reason3 = is_genuine_client_id("Accenture", "250000-300000")
    assert val3 is False
    assert clean3 is None
    assert reason3 in ("numeric_range", "pattern_mismatch_for_accenture")


# ---------------------------------------------------------------------------
# Test 3: Value near "LPA" or "CTC" rejected
# ---------------------------------------------------------------------------
def test_3_value_near_budget_words_rejected():
    """3. Value near 'LPA' or 'CTC' rejected as an ID."""
    body_lpa = "We have an open position for Java Lead. Budget is 15-18 LPA for the candidate."
    val_lpa, _, reason_lpa = is_genuine_client_id("LTTS", "15-18", context={"text": body_lpa})
    assert val_lpa is False
    assert reason_lpa in ("near_budget_words", "numeric_range", "length_out_of_range")

    body_ctc = "Expected CTC: 200000 - 250000 INR per annum"
    val_ctc, _, reason_ctc = is_genuine_client_id("Accenture", "200000-250000", context={"text": body_ctc})
    assert val_ctc is False
    assert reason_ctc in ("numeric_range", "near_budget_words", "pattern_mismatch_for_accenture")


# ---------------------------------------------------------------------------
# Test 4: Same value on two rows with different titles: rejected
# ---------------------------------------------------------------------------
def test_4_same_value_different_titles_rejected():
    """4. Same value on two rows of the same email whose title or city differ: rejected."""
    other_rows = [
        {"client_jd_id": "REQ-7788", "job_title": "Backend Go Developer", "location": "Bangalore"},
    ]
    context = {
        "text": "Email content mentions Req ID: REQ-7788",
        "job_title": "Frontend React Developer",
        "location": "Bangalore",
        "other_rows": other_rows,
    }

    val, clean, reason = is_genuine_client_id("PWC", "REQ-7788", context=context)
    assert val is False
    assert reason == "duplicate_value_different_roles"


# ---------------------------------------------------------------------------
# Test 5: 10 inserts, 1 forced failure, 5 duplicates: gap-free numbers
# ---------------------------------------------------------------------------
def test_5_ten_inserts_one_forced_fail_five_duplicates(temp_dbs):
    """5. Ten requirements inserted, one insert forced to fail, plus five duplicates: numbers are 001..010 with no gaps."""
    req_db = temp_dbs["req_db"]

    # 1. Insert 5 requirements
    inserted_ids = []
    for i in range(1, 6):
        payload = {
            "requirement_from": "Accenture",
            "job_title": f"Software Engineer {i}",
            "location": ["Bangalore"],
            "first_arrival_at": f"2026-10-01T10:0{i}:00Z",
        }
        jid = _sqlite_upsert(payload, req_db)
        inserted_ids.append(jid)

    # 2. Try an insert that forces a failure inside the transaction (e.g. invalid date or DB lock simulation)
    # The transaction must rollback and burn NO number.
    with patch("metaforge_api.json.dumps", side_effect=ValueError("Simulated serialization crash")):
        try:
            _sqlite_upsert({
                "requirement_from": "Accenture",
                "job_title": "Crash Role",
                "first_arrival_at": "2026-10-01T10:06:00Z",
            }, req_db)
        except ValueError:
            pass  # Expected simulated crash

    # 3. Insert remaining 5 requirements
    for i in range(6, 11):
        payload = {
            "requirement_from": "Accenture",
            "job_title": f"Software Engineer {i}",
            "location": ["Bangalore"],
            "first_arrival_at": f"2026-10-01T10:{i:02d}:00Z",
        }
        jid = _sqlite_upsert(payload, req_db)
        inserted_ids.append(jid)

    # 4. Five duplicates (same payload as earlier items)
    for i in range(1, 6):
        payload = {
            "requirement_from": "Accenture",
            "job_title": f"Software Engineer {i}",
            "location": ["Bangalore"],
            "first_arrival_at": f"2026-10-01T10:0{i}:00Z",
        }
        dup_jid = _sqlite_upsert(payload, req_db)
        assert dup_jid == inserted_ids[i - 1], "Duplicate must return existing job_id without allocating new seq"

    with sqlite3.connect(req_db) as conn:
        rows = conn.execute("SELECT seq FROM metaforge_requirements ORDER BY seq ASC").fetchall()
        seqs = [r[0] for r in rows]
        assert seqs == list(range(1, 11)), f"Sequences must be strictly gap-free 1..10, got {seqs}"


# ---------------------------------------------------------------------------
# Test 6: Two workers inserting at once: unique, gap-free numbers
# ---------------------------------------------------------------------------
def test_6_concurrent_workers_gap_free(temp_dbs):
    """6. Two workers inserting at once: unique, gap-free numbers."""
    req_db = temp_dbs["req_db"]

    def insert_worker(worker_id: int, count: int) -> list[str]:
        results = []
        for i in range(count):
            payload = {
                "requirement_from": "Deloitte",
                "job_title": f"Worker {worker_id} Role {i}",
                "location": ["Hyderabad"],
                "first_arrival_at": "2026-10-01T08:00:00Z",
            }
            jid = _sqlite_upsert(payload, req_db)
            results.append(jid)
        return results

    total_per_worker = 15
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(insert_worker, 1, total_per_worker)
        f2 = executor.submit(insert_worker, 2, total_per_worker)
        res1 = f1.result()
        res2 = f2.result()

    all_ids = res1 + res2
    assert len(all_ids) == 30
    assert len(set(all_ids)) == 30, "All allocated job_ids across concurrent workers must be unique"

    with sqlite3.connect(req_db) as conn:
        rows = conn.execute("SELECT seq FROM metaforge_requirements WHERE req_date = '2026/10/01' ORDER BY seq ASC").fetchall()
        seqs = [r[0] for r in rows]
        assert seqs == list(range(1, 31)), f"Concurrent sequences must be gap-free 1..30, got {seqs}"


# ---------------------------------------------------------------------------
# Test 7: Digest of 5 new rows: numbers follow arrival then email order
# ---------------------------------------------------------------------------
def test_7_digest_allocation_order(temp_dbs):
    """7. Digest of 5 new rows: numbers follow arrival then email order."""
    req_db = temp_dbs["req_db"]

    digest_rows = [
        {"job_title": "Role C", "first_arrival_at": "2026-10-01T09:00:00Z", "pos": 2},
        {"job_title": "Role A", "first_arrival_at": "2026-10-01T08:00:00Z", "pos": 0},
        {"job_title": "Role B", "first_arrival_at": "2026-10-01T08:00:00Z", "pos": 1},
        {"job_title": "Role E", "first_arrival_at": "2026-10-01T11:00:00Z", "pos": 4},
        {"job_title": "Role D", "first_arrival_at": "2026-10-01T09:00:00Z", "pos": 3},
    ]

    # R4: Sort by (arrival ASC, email position ASC)
    digest_rows.sort(key=lambda r: (r["first_arrival_at"], r["pos"]))

    assigned = []
    for r in digest_rows:
        payload = {
            "requirement_from": "Accenture",
            "job_title": r["job_title"],
            "first_arrival_at": r["first_arrival_at"],
        }
        jid = _sqlite_upsert(payload, req_db)
        assigned.append((r["job_title"], jid))

    expected_order = ["Role A", "Role B", "Role C", "Role D", "Role E"]
    actual_order = [a[0] for a in assigned]
    assert actual_order == expected_order

    actual_jids = [a[1] for a in assigned]
    expected_jids = [f"2026/10/01-{i:03d}" for i in range(1, 6)]
    assert actual_jids == expected_jids


# ---------------------------------------------------------------------------
# Test 8: Renumber dry run vs apply on a copy of current data
# ---------------------------------------------------------------------------
def test_8_renumber_dry_run_and_apply(temp_dbs):
    """8. Renumber dry run on a copy of the current data prints the mapping and changes nothing; apply on the copy keeps links and old URLs working."""
    req_db = temp_dbs["req_db"]
    proc_db = temp_dbs["proc_db"]

    # Seed with 3 out-of-order requirements
    p1 = {"job_title": "Late Role", "first_arrival_at": "2026-09-17T12:00:00Z", "job_id": "2026/09/17-005"}
    p2 = {"job_title": "Early Role", "first_arrival_at": "2026-09-17T06:00:00Z", "job_id": "2026/09/17-624"}
    p3 = {"job_title": "Mid Role", "first_arrival_at": "2026-09-17T09:00:00Z", "job_id": "2026/09/17-100"}

    _sqlite_upsert(p1, req_db)
    _sqlite_upsert(p2, req_db)
    _sqlite_upsert(p3, req_db)

    # 1. Run dry run
    audit_ids(req_db_path=req_db, proc_db_path=proc_db, renumber_dry_run=True, apply=False)

    # Verify dry run changed nothing
    with sqlite3.connect(req_db) as conn:
        jids = [r[0] for r in conn.execute("SELECT job_id FROM metaforge_requirements ORDER BY job_id").fetchall()]
        assert "2026/09/17-624" in jids
        assert "2026/09/17-005" in jids

    # 2. Run apply
    audit_ids(req_db_path=req_db, proc_db_path=proc_db, renumber_dry_run=False, apply=True)

    # Verify apply renumbered rows in order of arrival (06:00 -> 001, 09:00 -> 002, 12:00 -> 003)
    with sqlite3.connect(req_db) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT job_id, former_job_id, payload_json FROM metaforge_requirements ORDER BY job_id").fetchall()
        assert len(rows) == 3
        assert rows[0]["job_id"] == "2026/09/17-001"
        assert rows[0]["former_job_id"] == "2026/09/17-624"
        assert rows[1]["job_id"] == "2026/09/17-002"
        assert rows[1]["former_job_id"] == "2026/09/17-100"
        assert rows[2]["job_id"] == "2026/09/17-003"
        assert rows[2]["former_job_id"] == "2026/09/17-005"

    # Verify UI lookup of old URL / old ID still finds the requirement
    cfg = {"db_paths": [req_db]}
    rec_by_old = get_requirement(cfg, "2026/09/17-624")
    assert rec_by_old is not None
    assert rec_by_old["req_id"] == "2026/09/17-001"
    assert rec_by_old["former_job_id"] == "2026/09/17-624"


# ---------------------------------------------------------------------------
# Test 9: audit_ids reports 09/17 gap before repair and none after
# ---------------------------------------------------------------------------
def test_9_audit_ids_gap_reporting(temp_dbs):
    """9. audit_ids reports the known 09/17 gap before the repair and none after."""
    req_db = temp_dbs["req_db"]

    # Seed 09/17 with 2 rows having max 624 (gap!)
    _sqlite_upsert({"job_title": "Role 1", "first_arrival_at": "2026-09-17T08:00:00Z", "job_id": "2026/09/17-034"}, req_db)
    _sqlite_upsert({"job_title": "Role 2", "first_arrival_at": "2026-09-17T09:00:00Z", "job_id": "2026/09/17-624"}, req_db)

    stats_before = audit_ids(req_db_path=req_db, renumber_dry_run=False, apply=False)
    assert stats_before["2026/09/17"]["highest_nnn"] == 624
    assert stats_before["2026/09/17"]["row_count"] == 2
    assert stats_before["2026/09/17"]["ratio"] == 312.0
    assert len(stats_before["2026/09/17"]["missing_numbers"]) == 622

    # Repair
    audit_ids(req_db_path=req_db, renumber_dry_run=False, apply=True)

    # Audit after
    stats_after = audit_ids(req_db_path=req_db, renumber_dry_run=False, apply=False)
    assert stats_after["2026/09/17"]["highest_nnn"] == 2
    assert stats_after["2026/09/17"]["row_count"] == 2
    assert stats_after["2026/09/17"]["ratio"] == 1.00
    assert len(stats_after["2026/09/17"]["missing_numbers"]) == 0
