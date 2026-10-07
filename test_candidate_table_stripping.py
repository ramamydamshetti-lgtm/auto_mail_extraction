"""
Test candidate table stripping on KPMG requirement tables.
"""

from __future__ import annotations

from requirement_parser import _strip_candidate_tables

def test_banking_table_stripping():
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
    cleaned = _strip_candidate_tables(body)
    print("--- Original Body ---")
    print(body)
    print("\n--- Cleaned Body by _strip_candidate_tables ---")
    print(cleaned)

if __name__ == "__main__":
    test_banking_table_stripping()
