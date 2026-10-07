"""
AI Few-Shot Prompt Supplement Generator (Part B3).
Provides per-client few-shot examples (e.g. LTTS, Accenture) and generic status rules
for AI parsing and classification.
Designed so adding new per-client examples requires zero restructuring.
"""

from __future__ import annotations

_CLIENT_FEW_SHOT_EXAMPLES: dict[str, str] = {
    "LTTS": """
--- CLIENT FEW-SHOT EXAMPLES: LTTS ---
Example 1 (Hold Request):
Email Subject: RE: Requirement for Java Lead (REQ-10293) - HOLD
Email Body: Hi team, please put requirement REQ-10293 on hold until further notice. Stop profile submissions immediately.
Extracted Status:
- raw_status: "Hold"
- job_status: "hold"
- req_id: "REQ-10293"

Example 2 (Reopen Request):
Email Subject: RE: Requirement for Java Lead (REQ-10293) - REOPEN
Email Body: Hi team, we are reopening requirement REQ-10293. Please resume sharing candidate profiles.
Extracted Status:
- raw_status: "Reopen"
- job_status: "open"
- req_id: "REQ-10293"
""",
    "Accenture": """
--- CLIENT FEW-SHOT EXAMPLES: ACCENTURE ---
Example 1 (Daily Snapshot Table with Hold Status):
Email Subject: Accenture Daily Open Requirements Snapshot - 29 Sep 2026
Email Body:
Req ID | Role Title | Location | Status
ACC-88391 | Python Developer | Remote | Active
ACC-77210 | DevOps Engineer | Bangalore | Hold
Extracted Requirements:
- Req ID ACC-88391 -> job_status: "open", raw_status: "Active"
- Req ID ACC-77210 -> job_status: "hold", raw_status: "Hold"

Example 2 (Daily Snapshot Table Reappearance after Multi-day Gap):
Email Subject: Accenture Daily Open Requirements Snapshot - 05 Oct 2026
Email Body:
Req ID | Role Title | Location | Status
ACC-77210 | DevOps Engineer | Bangalore | Active
Extracted Requirements:
- Req ID ACC-77210 (reappeared after gap) -> job_status: "open", raw_status: "Active" (reopened/active update)
""",
}


def get_prompt_supplement(client_name: str | None = None) -> str:
    """
    Generate prompt supplement for AI parser/classifier.
    """
    return ""
