"""
Inspect Task 1 and Task 3 root causes in requirement_parser.py functions.
"""

from __future__ import annotations

from requirement_parser import (
    _has_explicit_multi_jd_signal,
    _extract_requirement_titles_from_thread,
)

def test_banking_multi_signal():
    subject = "Fw: Requirement - Banking Client - BA & PMO roles"
    body = """Dear Vendor,
New requirements have been added to Tables.
Please share relevant profiles.

Sr. No | Role | Requirement | Comments
1 | Finops MR (Chennai - 6 or Hyderabad - 1) | GCB 5 | JD Shared
2 | CCR /treasury/Basel 3.1 BA (Gurgaon/Bangalore) | GCB 5 | JD Shared
3 | WDS Design | GCB 4 | JD will be Shared soon
4 | Python programming - finance system operation | GCB 5 | JD Shared
5 | ESG Delivery PM | GCB 4 | JD Shared
"""
    print(f"Subject multi signal: {_has_explicit_multi_jd_signal(subject)}")
    print(f"Body multi signal: {_has_explicit_multi_jd_signal(body)}")

if __name__ == "__main__":
    test_banking_multi_signal()
