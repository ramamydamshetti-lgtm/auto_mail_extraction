"""
Specialized table structure extractor for structured client emails (e.g. KPMG Sr. No / Role tables).
Invoked by table_reconciler.py as part of Priority 4 Client/Table Cross-check.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List


_LOC_LINE = re.compile(r"(?i)\bLocation\b.*?-\s*(.+)")
_ROLE_ROW = re.compile(r"^\s*(\d{1,2})\s*$")


def _slug_header(h: str) -> str:
    k = re.sub(r"\s+", "_", h.lower().strip())
    k = re.sub(r"[^a-z0-9_]+", "", k).strip("_")
    return k or "col"


def _align_candidate_values(headers: List[str], avail: List[str]) -> List[str]:
    """Pad or shift values when optional columns (e.g. HM / Source) are omitted in the body."""
    n = len(headers)
    if len(avail) >= n:
        return (list(avail[:n]) + [""] * n)[:n]
    missing = n - len(avail)
    if missing == 0:
        return avail
    lows = [h.lower().strip() for h in headers]
    try:
        i_hm = lows.index("hiring manager")
        i_src = lows.index("source")
    except ValueError:
        return (list(avail) + [""] * missing)[:n]

    if missing == 2 and i_src == i_hm + 1 and len(avail) >= 2:
        return (avail[:2] + ["", ""] + avail[2:])[:n]
    if missing == 1 and len(avail) >= 2:
        return (avail[: i_hm] + [""] + avail[i_hm :])[:n]
    return (list(avail) + [""] * missing)[:n]


def extract_vertical_candidate_rows(text: str) -> List[Dict[str, str]]:
    """
    Vertical candidate-submission tables: column titles stacked one line each, then one or more
    rows of values in the same order (same line count as headers per row).
    """
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    out: List[Dict[str, str]] = []

    i = 0
    while i < len(lines):
        ln = lines[i]
        if ln.lower() not in ("sl no", "sr no", "sr. no") and not re.match(r"^sr\.?\s*no\.?$", ln.lower()):
            i += 1
            continue

        headers: List[str] = []
        j = i
        while j < len(lines):
            cur = lines[j]
            if re.match(r"^\d{1,3}$", cur) and len(headers) >= 8:
                break
            if len(cur) > 120 and len(headers) >= 6:
                break
            if headers and cur.lower().startswith(
                ("hi ", "hello ", "dear ", "thanks", "regards", "please find", "from:")
            ):
                break
            headers.append(cur)
            j += 1
            if j - i > 40:
                break

        if len(headers) < 8 or j >= len(lines):
            i += 1
            continue
        if not re.match(r"^\d{1,3}$", lines[j]):
            i += 1
            continue

        n = len(headers)
        row_start = j
        while row_start < len(lines):
            avail = lines[row_start : row_start + n]
            if not avail:
                break
            chunk = _align_candidate_values(headers, list(avail))
            row: Dict[str, str] = {"_table": "candidate_submission"}
            for hi, h in enumerate(headers):
                row[_slug_header(h)] = chunk[hi]
            out.append(row)
            consumed = min(len(avail), n)
            row_start += consumed
            if row_start < len(lines) and re.match(r"^\d{1,3}$", lines[row_start]):
                continue
            break

        i = row_start

    return out


def _extract_kpmg_style_roles_core(text: str) -> Dict[str, Any]:
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    locations: List[str] = []
    roles: List[Dict[str, str]] = []

    for ln in lines:
        m = _LOC_LINE.search(ln)
        if m:
            locs = m.group(1)
            parts = re.split(r"\s*/\s*|\s*,\s*", locs)
            for p in parts:
                p2 = p.strip(" .;")
                if p2 and p2.lower() not in {x.lower() for x in locations}:
                    locations.append(p2)

    header_idx = None
    for idx, ln in enumerate(lines):
        if ln.lower().startswith("sr. no") or ("sr. no" in ln.lower() and "role" in ln.lower()):
            header_idx = idx
            break

    if header_idx is None:
        return {"locations": locations, "roles": roles}

    i = header_idx + 1
    while i < len(lines):
        if not _ROLE_ROW.match(lines[i]):
            i += 1
            continue
        sr_no = lines[i]
        role = lines[i + 1] if i + 1 < len(lines) else ""
        req = lines[i + 2] if i + 2 < len(lines) else ""
        comments = lines[i + 3] if i + 3 < len(lines) else ""

        if role.lower().startswith(("thanks", "regards")):
            break

        roles.append(
            {
                "sr_no": sr_no,
                "role": role,
                "requirement": req,
                "comments": comments,
            }
        )
        i += 4

    return {"locations": locations, "roles": roles}


def extract_kpmg_style_roles(text: str) -> Dict[str, Any]:
    """
    KPMG-style 'Sr. No / Role / Requirement / Comments' blocks plus vertical candidate trackers.
    """
    base = _extract_kpmg_style_roles_core(text)
    cand = extract_vertical_candidate_rows(text)
    base["candidate_submissions"] = cand
    return base
