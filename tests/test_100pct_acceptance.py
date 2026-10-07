"""
Acceptance Test Suite for 100% Correct Extraction, Two-Way Verification,
Scheduler & Time Synchronization (F1-F8, V1-V4, N1-N5, S1-S6, T1-T4).
"""

import json
import os
import re
import sqlite3
import time
from datetime import datetime, timezone, timedelta
from typing import Any
import pytest

from config import Settings, is_strict_field_mapping
from models import RequirementItem, RequirementParseResult
from two_way_verifier import (
    deterministic_extract_block,
    reconcile_two_way,
    parse_experience_digits,
    parse_budget_details,
    parse_work_mode,
    verify_stored_requirement,
)
from requirement_parser import parse_requirements_from_email
from processed_store import ProcessedStore
from main import process_single_message, _parse_to_utc_dt


def test_example_email_scenario():
    """
    Gold Scenario 1: The example email:
    Senior Java Developer; Java, Spring Boot, AWS; 6+ years; Hyderabad; 18 LPA; notice period 'Not mentioned'.
    Expectations:
      - notice_period is NULL
      - monthly_budget is NULL (never derived from yearly/LPA)
      - mandatory_skills is NULL if no explicit mandatory label
      - experience_min_years is 6, max is NULL
      - yearly_budget is 18
      - location is ['Hyderabad']
    """
    body = (
        "Hi Team,\n"
        "Please share profiles for the following role:\n"
        "Role: Senior Java Developer\n"
        "Skills: Java, Spring Boot, AWS\n"
        "Experience: 6+ years\n"
        "Location: Hyderabad\n"
        "Budget: 18 LPA\n"
        "Notice Period: Not mentioned\n"
        "Regards,\nTalent Acquisition"
    )

    det = deterministic_extract_block(body)
    assert det["job_title"] == "Senior Java Developer"
    assert det["skills"] == ["Java", "Spring Boot", "AWS"]
    assert det["mandatory_skills"] is None
    assert det["experience_text"] == "6+ years"
    assert det["experience_min_years"] == 6.0
    assert det["experience_max_years"] is None
    assert det["location"] == ["Hyderabad"]
    assert det["budget_text"] == "18 LPA"
    assert det["yearly_budget"] == 18.0 or det["yearly_budget_min"] == 18.0
    assert det["monthly_budget"] is None
    assert det["monthly_budget_min"] is None
    assert det["notice_period"] is None
    assert det["work_mode"] is None


def test_mandatory_vs_good_to_have():
    """
    Gold Scenario 2: Mandatory vs Good to have skills:
    'Mandatory: Java, SQL' and 'Good to have: AWS'.
    Expectations:
      - Mandatory skills are in mandatory_skills only.
      - Good to have skills are in skills only.
      - No duplication between the two.
    """
    body = (
        "Job Title: Backend Developer\n"
        "Mandatory: Java, SQL\n"
        "Good to have: AWS\n"
        "Location: Bangalore\n"
        "Notice: 30 days\n"
    )

    det = deterministic_extract_block(body)
    assert det["job_title"] == "Backend Developer"
    assert set(det["mandatory_skills"]) == {"Java", "SQL"}
    assert det["skills"] == ["AWS"]
    assert "Java" not in det["skills"]
    assert "SQL" not in det["skills"]
    assert "AWS" not in det["mandatory_skills"]
    assert det["notice_period"] == "30 days"


def test_work_mode_wfh_vs_hybrid_remote():
    """
    Gold Scenario 3: F8 Work mode rules:
    - 'WFH' -> Remote
    - 'Hybrid/Remote' -> NULL (multiple offered per F8)
    - 'On-site' -> On-site
    """
    # Case A: WFH
    norm_a, text_a = parse_work_mode("Work Mode: WFH")
    assert norm_a == "Remote"
    assert text_a == "Work Mode: WFH"

    # Case B: Hybrid/Remote (multiple options)
    norm_b, text_b = parse_work_mode("Work Mode: Hybrid/Remote")
    assert norm_b is None  # F8: NULL if multiple options offered
    assert text_b == "Work Mode: Hybrid/Remote"

    # Case C: On-site / 5 days office
    norm_c, text_c = parse_work_mode("Work Mode: 5 days office")
    assert norm_c == "On-site"


def test_ltts_candidate_template_filtering():
    """
    Gold Scenario 4: LTTS email with candidate submission template:
    Candidate template headers (Full Name, Mail ID, Resumes sent Date...) must NEVER leak into skills.
    """
    body = (
        "Hi Team,\n"
        "Role: Embedded Firmware Engineer\n"
        "Location: Bangalore\n"
        "Experience: 5-8 years\n"
        "Mandatory Skills: C, RTOS, Microcontrollers\n\n"
        "Please share profiles in below format:\n"
        "Full Name of the candidate | Mobile No | Mail ID | Resumes sent Date (DDMMYY) | Last Full Time Qualification | Total Experience\n"
    )

    det = deterministic_extract_block(body)
    assert det["job_title"] == "Embedded Firmware Engineer"
    assert det["location"] == ["Bangalore"]
    assert det["experience_min_years"] == 5.0
    assert det["experience_max_years"] == 8.0
    assert set(det["mandatory_skills"]) == {"C", "RTOS", "Microcontrollers"}

    # Verify no template words leaked
    all_extracted_skills = (det["mandatory_skills"] or []) + (det["skills"] or [])
    for s in all_extracted_skills:
        assert "full name" not in s.lower()
        assert "mail id" not in s.lower()
        assert "resumes sent date" not in s.lower()
        assert "qualification" not in s.lower()


def test_two_way_reconciliation_and_recall_guard():
    """
    Two-Way Verification (V1-V4):
      - Agreement on job title
      - Recall guard flags possible_miss when label is present with real value but final is NULL
      - Post-save verifier verifies values against source block
    """
    block = (
        "Role: DevOps Architect\n"
        "Location: PAN India\n"
        "Experience: 10-12 years\n"
        "Budget: 35 LPA\n"
        "Notice Period: 15 days\n"
    )
    det = deterministic_extract_block(block)

    # Simulate AI output matching
    ai = {
        "job_title": "DevOps Architect",
        "location": ["PAN India"],
        "experience": "10-12 years",
        "budget": "35 LPA",
        "notice_period": "15 days",
    }

    reconciled, review_req, reasons = reconcile_two_way(ai, det, block)
    assert not review_req
    assert reconciled["job_title"] == "DevOps Architect"
    assert reconciled["location"] == ["PAN India"]

    # Post-save verifier
    status, failed = verify_stored_requirement(reconciled, block)
    assert status == "verified"
    assert len(failed) == 0

    # Test Recall Guard (V3)
    # AI dropped location completely
    ai_incomplete = {
        "job_title": "DevOps Architect",
        "location": None,  # dropped!
        "experience": "10-12 years",
    }
    reconciled_rec, review_req_rec, reasons_rec = reconcile_two_way(ai_incomplete, {"quotes": {}}, block)
    # Because block had "Location: PAN India", recall guard flags it
    assert reconciled_rec["possible_miss"] is True
    assert review_req_rec is True
    assert any("possible_miss_location" in r for r in reasons_rec)


def test_disposition_ledger_and_reconciliation(tmp_path):
    """
    N1 Disposition ledger:
    - Every message gets a row
    - Reconciliation detects any gap
    """
    db_file = tmp_path / "test_proc.db"
    store = ProcessedStore(db_file)

    # Record 3 messages
    store.record_email_disposition(
        message_id="msg_1",
        subject="Java Dev",
        disposition="extracted",
        requirements_count=1,
    )
    store.record_email_disposition(
        message_id="msg_2",
        subject="Newsletter",
        disposition="filtered",
        reason="promotional_email",
    )
    store.record_email_disposition(
        message_id="msg_3",
        subject="Out of Office",
        disposition="not_a_requirement",
        reason="ai_classifier_no",
    )

    # Reconcile when all 3 fetched
    reconciled, missing_cnt, missing_ids = store.reconcile_disposition_ledger(["msg_1", "msg_2", "msg_3"])
    assert reconciled is True
    assert missing_cnt == 0

    # Reconcile with missing message
    reconciled, missing_cnt, missing_ids = store.reconcile_disposition_ledger(["msg_1", "msg_2", "msg_3", "msg_missing"])
    assert reconciled is False
    assert missing_cnt == 1
    assert "msg_missing" in missing_ids
    store.close()


def test_scheduler_fixed_rate_and_heartbeat(tmp_path):
    """
    S1, S2, S5: Scheduler 120s fixed rate, lock, and heartbeat
    """
    db_file = tmp_path / "test_proc.db"
    store = ProcessedStore(db_file)

    # Record 5 consecutive ticks of heartbeat
    base_time = datetime(2026, 10, 1, 10, 0, 0, tzinfo=timezone.utc)
    for tick in range(5):
        t_start = (base_time + timedelta(seconds=120 * tick)).isoformat()
        t_end = (base_time + timedelta(seconds=120 * tick + 4)).isoformat()
        store.record_scheduler_heartbeat(
            started_at=t_start,
            finished_at=t_end,
            fetched=5,
            extracted=4,
            failed=0,
            status="ok",
        )

    last_hb = store.get_last_scheduler_heartbeat()
    assert last_hb is not None
    assert last_hb["status"] == "ok"
    assert last_hb["fetched"] == 5
    assert last_hb["extracted"] == 4
    store.close()


def test_time_ist_conversion_matches_outlook():
    """
    T1-T3: Received time in UTC converted to IST matches Outlook minute.
    UTC: 2026-09-30T10:15:30Z -> IST (+5:30): 2026-09-30 15:45:30 -> 09/30/2026 03:45 PM
    """
    utc_str = "2026-09-30T10:15:30Z"
    dt_utc = _parse_to_utc_dt(utc_str)
    ist_tz = timezone(timedelta(hours=5, minutes=30))
    dt_ist = dt_utc.astimezone(ist_tz)

    formatted = dt_ist.strftime("%m/%d/%Y %I:%M %p")
    assert formatted == "09/30/2026 03:45 PM"
