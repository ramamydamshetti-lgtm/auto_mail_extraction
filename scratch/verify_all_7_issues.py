import sys
import json
import sqlite3
import re
from datetime import datetime, timezone, timedelta

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')

from requirement_parser import extract_client_jd_id_from_text, parse_requirements_from_email, _is_noise_skill_candidate
from field_mapper import map_to_ui_payload, _norm_work_mode, _align_experience_level_with_overall
from metaforge_api import IdAllocator
from glossary import TermGlossary
from ui.db import _format_internal_id, fetch_all_records, _extract_real_client_jd_id
from ui.app import format_received_time, format_open_since

print("================================================================================")
print("VERIFICATION SUITE: 7 EXTRACTION ACCURACY ISSUES ON REPRODUCTION & HISTORICAL MAILS")
print("================================================================================\n")

# ------------------------------------------------------------------------------
# ISSUE 1: Client-provided ID Extraction & Label Recognition & Priority
# ------------------------------------------------------------------------------
print("--- ISSUE 1: CLIENT-PROVIDED ID EXTRACTION ---")
repro_subj = "New Requirement - Control & Monitoring RQ056293 (Prasad's Team)"
repro_body = """Work Location: Delhi
Office Model: 3 days work from Office
Monthly Bill Rate:
150000 - 200000
D.client
- Job Posting ID -
DLTJP00062540
Regards, Vaishnavi"""

repro_cid = extract_client_jd_id_from_text(repro_subj, repro_body)
print(f"Reproduction Email Client ID (Expected: DLTJP00062540): Extracted -> {repro_cid}")
assert repro_cid == "DLTJP00062540", f"Issue 1 failed on repro email, got {repro_cid}"

# Historical Test Cases for Issue 1:
hist_cid_cases = [
    ("Urgent Requirement - Req ID: 203421-1", "Accenture demand details...", "203421-1"),
    ("Fidelity Requisition RQ056293", "Requirement for Control Specialist...", "RQ056293"),
    ("LTTS Demand - REQ-98241", "LTTS automotive software engineer...", "REQ-98241"),
    ("Deloitte Job Posting ID - DLTJP00059663", "Deloitte SAP Lead...", "DLTJP00059663"),
]
for i, (s, b, expected) in enumerate(hist_cid_cases, 1):
    res = extract_client_jd_id_from_text(s, b)
    print(f"  Historical Test {i} ({expected}): Extracted -> {res}")
    assert res == expected, f"Historical Client ID test {i} failed: got {res}, expected {expected}"
print("[PASS] Issue 1 verified on reproduction email + 4 historical emails!\n")

# ------------------------------------------------------------------------------
# ISSUE 2: Requirement ID Format (YYYY/MM/DD-NNN)
# ------------------------------------------------------------------------------
print("--- ISSUE 2: REQUIREMENT ID FORMAT (YYYY/MM/DD-NNN) ---")
import tempfile
from pathlib import Path
with tempfile.TemporaryDirectory() as tmpdir:
    db_p = str(Path(tmpdir) / "test_id.db")
    allocator = IdAllocator(db_p)
    job_id = allocator.next_job_id()
    allocator.close()
    print(f"IdAllocator.next_job_id() output: {job_id}")
    assert "/" in job_id and "-" in job_id and len(job_id.split("-")) == 2, f"Invalid format: {job_id}"
    date_part, seq_part = job_id.split("-")
    assert len(date_part.split("/")) == 3, f"Date part should have 3 slash segments: {date_part}"
    assert len(seq_part) == 3, f"Seq part should be 3 digits: {seq_part}"

fmt_test1 = _format_internal_id("2026-09-30-044")
fmt_test2 = _format_internal_id("REQ-2026-09-30-012")
fmt_test3 = _format_internal_id("2026/09/30-005")
print(f"  Format Test 1 ('2026-09-30-044'): {fmt_test1}")
print(f"  Format Test 2 ('REQ-2026-09-30-012'): {fmt_test2}")
print(f"  Format Test 3 ('2026/09/30-005'): {fmt_test3}")
assert fmt_test1 == "2026/09/30-044"
assert fmt_test2 == "2026/09/30-012"
assert fmt_test3 == "2026/09/30-005"
print("[PASS] Issue 2 verified across all requirement ID generators & formatters!\n")

# ------------------------------------------------------------------------------
# ISSUE 3: Work Mode Misclassification ("3 days work from Office" -> "Hybrid")
# ------------------------------------------------------------------------------
print("--- ISSUE 3: WORK MODE CLASSIFICATION ---")
wm_repro1 = _norm_work_mode("3 days work from Office")
wm_repro2 = TermGlossary.normalize_work_mode("3 days work from Office")
print(f"Reproduction Email Work Mode ('3 days work from Office'): field_mapper -> {wm_repro1} | TermGlossary -> {wm_repro2}")
assert wm_repro1.lower() == "hybrid" and wm_repro2 == "Hybrid", f"Issue 3 failed on repro text: {wm_repro1}, {wm_repro2}"

hist_wm_cases = [
    ("2 days work from home, 3 days office", "Hybrid"),
    ("Office Model: 4 days from Office", "Hybrid"),
    ("1 day work from office", "Hybrid"),
    ("Fully on-site 5 days week", "On-site"),
    ("100% remote WFH", "Remote"),
]
for i, (text, expected) in enumerate(hist_wm_cases, 1):
    res = TermGlossary.normalize_work_mode(text)
    print(f"  Historical Test {i} ('{text}'): Normalized -> {res}")
    assert res == expected, f"Historical Work Mode test {i} failed: got {res}, expected {expected}"
print("[PASS] Issue 3 verified on reproduction phrase + 5 historical phrases!\n")

# ------------------------------------------------------------------------------
# ISSUE 4: Budget Range Min/Max Separation & UI Display
# ------------------------------------------------------------------------------
print("--- ISSUE 4: BUDGET RANGE SEPARATION & DISPLAY ---")
v_item_range = {
    "job_title": "Control & Monitoring Specialist",
    "monthly_budget_min": 150000,
    "monthly_budget_max": 200000,
    "number_of_positions": 1,
}
meta = {"date": "2026/09/30", "count": "044"}
mapped_range = map_to_ui_payload(v_item_range, meta)
monthly_bud_disp = mapped_range.get("monthly_budget")
print(f"Reproduction Email Monthly Budget (150000 - 200000): Mapped -> '{monthly_bud_disp}'")
assert monthly_bud_disp == "₹150,000 - ₹200,000", f"Issue 4 failed, got '{monthly_bud_disp}'"

hist_bud_cases = [
    ({"monthly_budget_min": 80000, "monthly_budget_max": 120000}, "₹80,000 - ₹120,000"),
    ({"monthly_budget_min": 250000, "monthly_budget_max": 250000}, "₹250,000"),
    ({"yearly_budget_min": 1500000, "yearly_budget_max": 2000000}, None),
]
for i, (b_dict, expected) in enumerate(hist_bud_cases, 1):
    res_payload = map_to_ui_payload(b_dict, meta)
    res_mb = res_payload.get("monthly_budget")
    print(f"  Historical Test {i} ({b_dict}): Mapped -> '{res_mb}'")
    assert res_mb == expected, f"Historical Budget test {i} failed: got {res_mb}, expected {expected}"
print("[PASS] Issue 4 verified on reproduction budget range + 3 historical cases!\n")

# ------------------------------------------------------------------------------
# ISSUE 5: Experience Level vs. Overall Experience Consistency
# ------------------------------------------------------------------------------
print("--- ISSUE 5: EXPERIENCE LEVEL VS OVERALL EXPERIENCE CONSISTENCY ---")
aligned_repro = _align_experience_level_with_overall("Mid Senior", "9+ years")
print(f"Reproduction Alignment ('Mid Senior' vs '9+ years'): Aligned -> '{aligned_repro}'")
assert aligned_repro == "Senior", f"Issue 5 failed on repro, got {aligned_repro}"

hist_exp_cases = [
    ("Mid Senior", "12+ years", "Senior"),
    ("Junior", "10 years", "Senior"),
    ("Senior", "2 years", "Junior"),
    ("Mid Senior", "5 years", "Mid Senior"),
]
for i, (lvl, ovr, expected) in enumerate(hist_exp_cases, 1):
    res = _align_experience_level_with_overall(lvl, ovr)
    print(f"  Historical Test {i} ('{lvl}' vs '{ovr}'): Aligned -> '{res}'")
    assert res == expected, f"Historical Experience Alignment test {i} failed: got {res}, expected {expected}"
print("[PASS] Issue 5 verified on reproduction mismatch + 4 historical cases!\n")

# ------------------------------------------------------------------------------
# ISSUE 6: "Open Since" Local Timezone (Asia/Kolkata IST) Calculation
# ------------------------------------------------------------------------------
print("--- ISSUE 6: OPEN SINCE LOCAL TIMEZONE (IST) CALCULATION ---")
repro_iso = "2026-09-30T05:57:39Z" # Received at 11:27 AM IST on 2026-09-30
repro_fmt_time = format_received_time(repro_iso)
repro_open_since = format_open_since(repro_iso)
print(f"Reproduction Email Timestamp ({repro_iso}):")
print(f"  Formatted Received Time: {repro_fmt_time}")
print(f"  Formatted Open Since   : {repro_open_since}")
assert "09/30/2026" in repro_fmt_time and "11:27" in repro_fmt_time, f"Format time failed: {repro_fmt_time}"
assert "Sep 30, 2026" in repro_open_since, f"Open Since failed: {repro_open_since}"

hist_dt_cases = [
    ("2026-09-30T18:30:00Z", "Oct 01, 2026"), # UTC 6:30 PM is 12:00 AM Oct 1 IST
    ("2026-09-29T20:00:00Z", "Sep 30, 2026"), # UTC 8:00 PM Sep 29 is 1:30 AM Sep 30 IST
]
for i, (iso_str, expected_date_substr) in enumerate(hist_dt_cases, 1):
    res_os = format_open_since(iso_str)
    print(f"  Historical Timezone Test {i} ('{iso_str}'): Open Since -> '{res_os}'")
    assert expected_date_substr in res_os, f"Historical Timezone test {i} failed: got '{res_os}'"
print("[PASS] Issue 6 verified on reproduction timestamp + 2 timezone edge cases!\n")

# ------------------------------------------------------------------------------
# ISSUE 7: Response-Template Table Headers Filtered from Job Skills
# ------------------------------------------------------------------------------
print("--- ISSUE 7: CANDIDATE SUBMISSION FORM HEADERS FILTERED FROM SKILLS ---")
headers_to_test = ["Mobile no", "Email ID", "Applicant Location", "Vendor", "Sl. No", "Applicant Name", "Notice Period"]
print("Testing noise skill candidate filter on response template headers:")
for h in headers_to_test:
    is_noise = _is_noise_skill_candidate(h)
    print(f"  Header '{h}': Is Noise -> {is_noise}")
    assert is_noise, f"Header '{h}' should be recognized as noise skill!"

# Test payload filtering in field_mapper:
raw_skills_item = {
    "job_title": "Control & Monitoring Specialist",
    "mandatory_skills": ["Mobile no", "Investment Compliance", "Email ID"],
    "skills": ["Applicant Location", "CFA", "Vendor"],
}
mapped_skills = map_to_ui_payload(raw_skills_item, meta)
cleaned_mand = mapped_skills.get("mandatory_skills")
cleaned_soft = mapped_skills.get("skills")
print(f"  Reproduction Skills Payload Input : Mandatory={raw_skills_item['mandatory_skills']} | Soft={raw_skills_item['skills']}")
print(f"  Filtered Skills Payload Output: Mandatory={cleaned_mand} | Soft={cleaned_soft}")
assert "Mobile no" not in cleaned_mand and "Email ID" not in cleaned_mand, "Mobile no or Email ID failed to be filtered!"
assert "Investment Compliance" in cleaned_mand, "Genuine skill Investment Compliance was lost!"
assert "CFA" in cleaned_soft, "Genuine skill CFA was lost!"
print("[PASS] Issue 7 verified on candidate submission table headers + skill payload filtering!\n")

print("================================================================================")
print("ALL 7 EXTRACTION ACCURACY ISSUES EMPIRICALLY VERIFIED & PASSED SUCCESSFULLY!")
print("================================================================================")
