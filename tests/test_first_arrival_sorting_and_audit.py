"""
Tests for first_arrival_at sorting, pagination, date invariant audit and repairs (S1-S9).
All tests use temporary SQLite databases or mock objects and never mutate live databases.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from ui.app import filter_and_sort_records, format_received_time
from ui.db import _parse_to_utc_dt, fetch_all_records
from scripts.audit_dates import audit_and_repair, extract_req_date, IST


def test_1_mixed_dates_strictly_newest_first():
    """S9-1: 12 rows with mixed dates across two months and two years: order is strictly newest first."""
    dates = [
        ("2025-11-15T10:00:00Z", "2025/11/15-001"),
        ("2025-12-01T08:00:00Z", "2025/12/01-001"),
        ("2025-12-25T12:00:00Z", "2025/12/25-001"),
        ("2026-08-10T09:00:00Z", "2026/08/10-001"),
        ("2026-08-20T14:30:00Z", "2026/08/20-001"),
        ("2026-09-01T04:00:00Z", "2026/09/01-001"),
        ("2026-09-15T11:20:00Z", "2026/09/15-001"),
        ("2026-09-22T06:00:00Z", "2026/09/22-001"),
        ("2026-09-30T10:00:00Z", "2026/09/30-001"),
        ("2026-10-01T03:33:18Z", "2026/10/01-001"),
        ("2026-10-01T05:00:00Z", "2026/10/01-002"),
        ("2026-10-01T09:15:00Z", "2026/10/01-003"),
    ]
    # Scramble the input order
    import random
    rng = random.Random(42)
    scrambled = list(dates)
    rng.shuffle(scrambled)

    records = [
        {
            "req_id": req_id,
            "first_arrival_at": fa,
            "arr_iso": fa,
            "payload": {"first_arrival_at": fa, "job_id": req_id, "requirement_from": "TestClient"},
        }
        for fa, req_id in scrambled
    ]

    sorted_res = filter_and_sort_records(records, q="", client="", status="", sort="first_arrival_at", order="desc")

    # Verify descending: newest first
    expected_order = [d[1] for d in reversed(dates)]
    actual_order = [r["req_id"] for r in sorted_res]
    assert actual_order == expected_order


def test_2_same_timestamp_higher_sequence_first():
    """S9-2: Two rows with the same timestamp: higher sequence first, 100 before 99."""
    shared_ts = "2026-10-01T03:33:18Z"
    records = [
        {
            "req_id": "2026/10/01-099",
            "first_arrival_at": shared_ts,
            "arr_iso": shared_ts,
            "payload": {"first_arrival_at": shared_ts, "job_id": "2026/10/01-099"},
        },
        {
            "req_id": "2026/10/01-100",
            "first_arrival_at": shared_ts,
            "arr_iso": shared_ts,
            "payload": {"first_arrival_at": shared_ts, "job_id": "2026/10/01-100"},
        },
    ]

    sorted_res = filter_and_sort_records(records, q="", client="", status="", sort="first_arrival_at", order="desc")
    assert sorted_res[0]["req_id"] == "2026/10/01-100"
    assert sorted_res[1]["req_id"] == "2026/10/01-099"


def test_3_pagination_across_3_pages():
    """S9-3: 45 rows across 3 pages: no row out of order across pages."""
    records = []
    base_dt = datetime(2026, 9, 1, 0, 0, 0, tzinfo=timezone.utc)
    for i in range(1, 46):
        dt = base_dt + timedelta(hours=i)
        iso = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        req_id = f"2026/09/01-{i:03d}"
        records.append({
            "req_id": req_id,
            "first_arrival_at": iso,
            "arr_iso": iso,
            "payload": {"first_arrival_at": iso, "job_id": req_id},
        })

    # Shuffle before sorting
    import random
    random.Random(123).shuffle(records)

    sorted_res = filter_and_sort_records(records, q="", client="", status="", sort="first_arrival_at", order="desc")
    assert len(sorted_res) == 45

    page_size = 20
    page1 = sorted_res[0:20]
    page2 = sorted_res[20:40]
    page3 = sorted_res[40:45]

    # Verify no row out of order across pages
    last_page1_dt = _parse_to_utc_dt(page1[-1]["first_arrival_at"])
    first_page2_dt = _parse_to_utc_dt(page2[0]["first_arrival_at"])
    assert last_page1_dt >= first_page2_dt

    last_page2_dt = _parse_to_utc_dt(page2[-1]["first_arrival_at"])
    first_page3_dt = _parse_to_utc_dt(page3[0]["first_arrival_at"])
    assert last_page2_dt >= first_page3_dt

    # Complete list is strictly monotonic non-increasing
    for i in range(len(sorted_res) - 1):
        dt_curr = _parse_to_utc_dt(sorted_res[i]["first_arrival_at"])
        dt_next = _parse_to_utc_dt(sorted_res[i + 1]["first_arrival_at"])
        assert dt_curr >= dt_next


def test_4_utc_to_ist_conversion_and_sorting():
    """S9-4: An arrival at 23:30 UTC on 09/30 shows as 10/01 05:00 IST and sorts correctly."""
    utc_iso = "2026-09-30T23:30:00Z"
    ist_text = format_received_time(utc_iso)
    assert "10/01/2026 05:00 AM" == ist_text

    earlier_utc = "2026-09-30T22:00:00Z"
    later_utc = "2026-10-01T01:00:00Z"

    records = [
        {"req_id": "R1", "first_arrival_at": earlier_utc, "payload": {"first_arrival_at": earlier_utc}},
        {"req_id": "R2", "first_arrival_at": utc_iso, "payload": {"first_arrival_at": utc_iso}},
        {"req_id": "R3", "first_arrival_at": later_utc, "payload": {"first_arrival_at": later_utc}},
    ]

    sorted_res = filter_and_sort_records(records, q="", client="", status="", sort="first_arrival_at", order="desc")
    assert [r["req_id"] for r in sorted_res] == ["R3", "R2", "R1"]


def test_5_duplicate_or_status_change_leaves_order_unchanged():
    """S9-5: A duplicate email or status change leaves the order unchanged."""
    rec1 = {
        "req_id": "2026/09/20-001",
        "first_arrival_at": "2026-09-20T10:00:00Z",
        "created_at": "2026-09-20T10:00:00Z",
        "updated_at": "2026-09-20T10:00:00Z",
        "payload": {
            "first_arrival_at": "2026-09-20T10:00:00Z",
            "job_id": "2026/09/20-001",
            "job_status": "open",
        },
    }
    rec2 = {
        "req_id": "2026/09/25-001",
        "first_arrival_at": "2026-09-25T10:00:00Z",
        "created_at": "2026-09-25T10:00:00Z",
        "updated_at": "2026-09-25T10:00:00Z",
        "payload": {
            "first_arrival_at": "2026-09-25T10:00:00Z",
            "job_id": "2026/09/25-001",
            "job_status": "open",
        },
    }

    initial_sort = filter_and_sort_records([rec1, rec2], q="", client="", status="", sort="first_arrival_at", order="desc")
    assert [r["req_id"] for r in initial_sort] == ["2026/09/25-001", "2026/09/20-001"]

    # Status update happens on 2026-10-01 for rec1 (updated_at and status changes, first_arrival_at untouched)
    rec1_updated = dict(rec1)
    rec1_updated["updated_at"] = "2026-10-01T09:00:00Z"
    rec1_updated["payload"] = dict(rec1["payload"])
    rec1_updated["payload"]["job_status"] = "hold"

    after_update = filter_and_sort_records([rec1_updated, rec2], q="", client="", status="", sort="first_arrival_at", order="desc")
    # rec1 must NOT jump ahead of rec2
    assert [r["req_id"] for r in after_update] == ["2026/09/25-001", "2026/09/20-001"]


def test_6_top_row_is_200964_and_34_in_original_positions():
    """S9-6: After the repair, the top row is 200964-1 and the 34 old rows are back in their original positions."""
    today_rec = {
        "req_id": "2026/10/01-001",
        "client_jd_id": "200964-1",
        "first_arrival_at": "2026-10-01T03:33:18Z",
        "payload": {"first_arrival_at": "2026-10-01T03:33:18Z", "client_jd_id": "200964-1"},
    }

    sept_records = []
    base_dt = datetime(2026, 9, 11, 11, 18, 15, tzinfo=timezone.utc)
    for i in range(1, 35):
        dt = base_dt + timedelta(hours=i)
        iso = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        cjd = f"SEPT-{i:03d}"
        sept_records.append({
            "req_id": f"2026/09/11-{i:03d}",
            "client_jd_id": cjd,
            "first_arrival_at": iso,
            "payload": {"first_arrival_at": iso, "client_jd_id": cjd},
        })

    all_recs = [today_rec] + sept_records
    sorted_res = filter_and_sort_records(all_recs, q="", client="", status="", sort="first_arrival_at", order="desc")

    assert sorted_res[0]["client_jd_id"] == "200964-1"
    assert sorted_res[0]["req_id"] == "2026/10/01-001"

    # The 34 old rows follow in reverse chronological order
    for idx, r in enumerate(sorted_res[1:], start=1):
        assert r["client_jd_id"].startswith("SEPT-")
        # Ensure descending arrival timestamps
        assert _parse_to_utc_dt(r["first_arrival_at"]) <= _parse_to_utc_dt(sorted_res[idx - 1]["first_arrival_at"])


def test_7_audit_dates_finds_known_examples_and_zero_after_repair():
    """S9-7: audit_dates finds both known examples before the repair and reports zero after it."""
    td = tempfile.mkdtemp(prefix="test_audit_")
    mf_db = Path(td) / "metaforge_requirements.db"
    proc_db = Path(td) / "processed_messages.db"
    backup_json = Path(td) / "backup.json"

    try:
        conn = sqlite3.connect(str(mf_db))
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

        # Example 1: 2026/09/23-010 (203483-1) showing arrival 09/30 12:22 PM (2026-09-30T06:52:09Z)
        p1 = {
            "job_id": "2026/09/23-010",
            "client_jd_id": "203483-1",
            "receivedDateTime": "2026-09-30T06:52:09Z",
            "demand_received_date": "2026-09-30",
        }
        fch1 = [{
            "changed_at": "2026-09-30T20:12:21Z",
            "changes": {"demand_received_date": {"old": "2026-09-23", "new": "2026-09-30"}},
        }]
        conn.execute(
            "INSERT INTO metaforge_requirements VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("2026/09/23-010", json.dumps(p1), "2026-09-23T12:06:30Z", "203483-1", "2026-09-30T20:12:21Z", json.dumps(fch1), "ident1"),
        )

        # Example 2: 34 rows from 10/01 digest showing 10/01 09:03 AM (2026-10-01T03:33:18Z)
        backup_items = []
        for i in range(1, 35):
            cjd = f"OVERWRITE-{i:03d}"
            job_id = f"2026/09/22-{i:03d}"
            p_bad = {
                "job_id": job_id,
                "client_jd_id": cjd,
                "receivedDateTime": "2026-10-01T03:33:18Z",  # Overwritten with today's time
                "demand_received_date": "2026-10-01",
            }
            conn.execute(
                "INSERT INTO metaforge_requirements VALUES (?, ?, ?, ?, ?, ?, ?)",
                (job_id, json.dumps(p_bad), "2026-09-22T06:00:00Z", cjd, "2026-10-01T03:33:18Z", json.dumps([]), f"ident_{i}"),
            )
            # Pristine backup has the September date
            backup_items.append({
                "client_jd_id": cjd,
                "payload_json": json.dumps({
                    "job_id": job_id,
                    "client_jd_id": cjd,
                    "receivedDateTime": f"2026-09-22T06:{i:02d}:00Z",
                    "demand_received_date": "2026-09-22",
                }),
            })

        # Add backup entry for Example 1
        backup_items.append({
            "client_jd_id": "203483-1",
            "payload_json": json.dumps({
                "job_id": "2026/09/23-010",
                "client_jd_id": "203483-1",
                "receivedDateTime": "2026-09-23T12:06:30Z",
                "demand_received_date": "2026-09-23",
            }),
        })

        with open(backup_json, "w", encoding="utf-8") as f:
            json.dump(backup_items, f)

        conn.commit()
        conn.close()

        # Step 1: Run audit before repair: must find ALL 35 broken rows (Example 1 + 34 rows of Example 2)
        res_before = audit_and_repair(mf_db, proc_db, backup_json, apply_changes=False)
        assert res_before["broken"] == 35

        broken_cjds = {b["client_jd_id"] for b in res_before["broken_rows"]}
        assert "203483-1" in broken_cjds
        for i in range(1, 35):
            assert f"OVERWRITE-{i:03d}" in broken_cjds

        # Step 2: Apply the repairs
        res_apply = audit_and_repair(mf_db, proc_db, backup_json, apply_changes=True)
        assert res_apply["broken"] == 35

        # Step 3: Run audit after repair: must report exactly 0 broken rows!
        res_after = audit_and_repair(mf_db, proc_db, backup_json, apply_changes=False)
        assert res_after["broken"] == 0
        assert res_after["matched"] == 35

    finally:
        shutil.rmtree(td, ignore_errors=True)
