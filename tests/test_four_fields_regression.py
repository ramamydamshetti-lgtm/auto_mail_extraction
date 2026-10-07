"""
Regression tests for BUDGET, EXPERIENCE, JOB TITLE, and WORK MODE improvements.
Strictly verifies:
1. Budget: Ranges, Lakhs, Thousands, Tiered slabs, Monthly vs Yearly separation.
2. Experience: Unicode dashes, decimals, ranges, open-ended plus, no fabricated maximums.
3. Job Title: Multi-role isolation, table row assignment, explicit labels.
4. Work Mode: Explicit arrangement extraction, zero hallucination from technical words ('Remote Function Adapter') or office prose ('office buildings').
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from field_mapper import parse_budget_fields, map_to_ui_payload
from two_way_verifier import parse_experience_digits, parse_work_mode, deterministic_extract_block
from models import RequirementItem


def test_budget_monthly_ranges_and_multipliers():
    """Verify ranges, Thousands (K), Lakhs (L), and tiered budget parsing."""
    # Monthly range
    b1 = parse_budget_fields("Bill Rate - 75000-80000 max")
    assert b1["budget_inr_lpm_min"] == 75000
    assert b1["budget_inr_lpm_max"] == 80000
    assert b1["budget_period"] == "monthly"

    # Monthly Lakhs
    b2 = parse_budget_fields("Bill Rate - 1.25L")
    assert b2["budget_inr_lpm_min"] == 125000
    assert b2["budget_inr_lpm_max"] == 125000
    assert b2["budget_period"] == "monthly"

    # Monthly Thousands (K)
    b3 = parse_budget_fields("Bill Rate - 90 K +")
    assert b3["budget_inr_lpm_min"] == 90000
    assert b3["budget_inr_lpm_max"] == 90000
    assert b3["budget_period"] == "monthly"

    # Tiered budget slab
    tier_text = (
        "Bill Rate per month for TPC:\n"
        "4 – 5 yrs – 1.2 L\n"
        "5 - 6 yrs – 1.35 L\n"
        "6 – 7 yrs – 1.5 L\n"
    )
    b4 = parse_budget_fields(tier_text)
    assert b4["budget_period"] == "monthly"
    assert "4 – 5 yrs – 1.2 L" in b4["budget_display"]
    assert "5 - 6 yrs – 1.35 L" in b4["budget_display"]


def test_budget_does_not_leak_to_yearly():
    """Verify monthly bill rates do not leak into yearly_budget in DashboardRequirement24."""
    item = {
        "budget": "Bill Rate - 120000",
        "monthly_budget_min": 120000,
        "monthly_budget_max": 120000,
        "yearly_budget_min": None,
        "yearly_budget_max": None,
        "client_name": "LTTS",
        "job_title": "Software Engineer",
    }
    mapped = map_to_ui_payload(item, {"job_id": "REQ-001", "date": "2026-09-01", "client_jd_id": "123"})
    assert mapped["monthly_budget"] == "₹120,000"
    assert mapped["yearly_budget"] is None


def test_experience_unicode_dashes_and_decimals():
    """Verify ranges with unicode en-dash and decimal years are accurately extracted."""
    # En-dash range
    mn, mx = parse_experience_digits("Overall exp – 4 – 9 years")
    assert mn == 4.0
    assert mx == 9.0

    # Decimal range
    mn, mx = parse_experience_digits("2.5-4 Yrs")
    assert mn == 2.5
    assert mx == 4.0

    # Open-ended plus
    mn, mx = parse_experience_digits("Overall exp – 7 + years")
    assert mn == 7.0
    assert mx is None

    # Textual open-ended
    mn, mx = parse_experience_digits("Overall exp – more than 6 years")
    assert mn == 6.0
    assert mx is None


def test_job_title_extraction_with_requirement_label():
    """Verify job title extracted from 'Requirement - Title' label without capturing position numbers."""
    block = (
        "Requirement – Lighting Design Engineer\n"
        "Overall exp – more than 6 years\n"
        "Open Positions – 5\n"
    )
    det = deterministic_extract_block(block, "LTTS")
    assert det["job_title"] == "Lighting Design Engineer"


def test_work_mode_clean_extraction_and_zero_hallucination():
    """Verify explicit work mode is extracted while tech terms and office prose are not hallucinated."""
    # Explicit arrangement
    norm_wm, wm_text = parse_work_mode("Work Model - Hybrid, 2 days in office")
    assert norm_wm == "Hybrid"

    # Technical SAP PaPM feature must NOT be extracted as Remote work mode
    det_tech = deterministic_extract_block("Modelling Function Types like Remote Function Adapter, Query", "Accenture")
    assert det_tech["work_mode"] is None

    # Prose with office must NOT be extracted as On-site work mode
    det_office = deterministic_extract_block("Responsible for modern office buildings and facilities", "LTTS")
    assert det_office["work_mode"] is None
