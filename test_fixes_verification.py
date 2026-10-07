"""
Verification script for Task 1 and Task 3 fixes.
"""

from __future__ import annotations

import re
from requirement_parser import (
    _norm,
    _MULTI_JD_SIGNAL_RE,
    _SUBJECT_ROLE_RE,
)

def test_multi_jd_signals():
    # Test plural role keywords & table header patterns
    signal_re = re.compile(
        r"(?i)\b(req\s*\d+|role\s*\d+|multiple roles|roles|requirements|tables|job description\s*\d+)\b|^\s*sr\.?\s*no\.?\s*\|\s*role\b"
    )
    
    s1 = "Fw: Requirement - Banking Client - BA & PMO roles"
    b1 = "Sr. No | Role | Requirement | Comments\n1 | Finops MR | GCB 5"
    
    print(f"s1 match: {bool(signal_re.search(s1))}")
    print(f"b1 match: {bool(signal_re.search(b1))}")

def test_pivot_titles_subject_only():
    subject = "WORKDAY | FTE - Urgent Requirements"
    body = "2 | SAP ABAP Consultant | 5+ yrs exp in SAP S/4HANA | High Priority"
    
    # If _extract_requirement_titles_from_thread only checks subject (or subject lines):
    subject_titles = [re.sub(r"\s+", " ", m.group(1)).strip() for m in _SUBJECT_ROLE_RE.finditer(subject)]
    print(f"Subject-only pivot titles: {subject_titles}")

if __name__ == "__main__":
    test_multi_jd_signals()
    test_pivot_titles_subject_only()
