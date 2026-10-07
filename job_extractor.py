from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple


KEY_VALUE_RE = re.compile(r"^\s*([A-Za-z ]+)\s*:\s*(.+?)\s*$")
YEARS_RANGE_RE = re.compile(r"(\d+)\s*[-–]\s*(\d+)\s*Years", re.IGNORECASE)
YEARS_PLUS_RE = re.compile(r"(\d+)\s*\+\s*years", re.IGNORECASE)


def _parse_experience(text: str) -> Tuple[Optional[int], Optional[int]]:
    text = text.strip()
    m = YEARS_RANGE_RE.search(text)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = YEARS_PLUS_RE.search(text)
    if m:
        years = int(m.group(1))
        return years, None
    return None, None


def _clean_bullet(line: str) -> str:
    line = line.strip().lstrip("•·-o*").strip()
    return re.sub(r"\s+", " ", line).strip().strip('"')


def extract_job_fields_from_body(body: str) -> Dict[str, Any]:
    """Extract structured job fields from a job-requirement email body."""
    lines = [ln.rstrip() for ln in body.splitlines() if ln.strip()]

    data: Dict[str, Any] = {
        "job_title": None,
        "client": None,
        "location": None,
        "experience_raw": None,
        "experience_min_years": None,
        "experience_max_years": None,
        "salary_or_pay": None,
        "employment_type": None,
        "skills_required": [],
        "soft_skills": [],
    }

    current_section: Optional[str] = None

    for raw in lines:
        line = raw.strip()

        # Top-level labeled lines like "Role: QA Automation Engineer"
        m = KEY_VALUE_RE.match(line)
        if m and current_section is None:
            key = m.group(1).strip().lower()
            val = m.group(2).strip().strip('"')

            if key.startswith("role"):
                # Both "Role: QA Automation Engineer" and "Role : C2H" appear in samples.
                # If we already have a title, treat later "Role" as employment_type.
                if data["job_title"] is None:
                    data["job_title"] = val
                else:
                    data["employment_type"] = val
            elif key.startswith("client"):
                data["client"] = val
            elif key.startswith("location"):
                data["location"] = val
            elif key.startswith("over experience") or "experience" in key:
                data["experience_raw"] = val
                mn, mx = _parse_experience(val)
                data["experience_min_years"] = mn
                data["experience_max_years"] = mx
            elif "market" in key or "ctc" in key or "salary" in key:
                data["salary_or_pay"] = val
            else:
                # Ignore other labels for now; they can be added later if needed.
                pass
            continue

        low = line.lower()
        if "required skills" in low and "qualification" in low:
            current_section = "skills"
            continue
        if low.startswith("soft skills"):
            current_section = "soft_skills"
            continue

        if current_section in {"skills", "soft_skills"}:
            cleaned = _clean_bullet(line)
            if cleaned:
                if current_section == "skills":
                    data["skills_required"].append(cleaned)
                else:
                    data["soft_skills"].append(cleaned)
            continue

    return data

