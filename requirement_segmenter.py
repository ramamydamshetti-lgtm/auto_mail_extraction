"""
Requirement Segmentation and Exclusion Zone Stripper (M1, M2, M3, M4).

Principles:
- P1: Values come only from text of their OWN requirement block.
- P5: Candidate submission tables, headers, signatures, quoted history must never leak into requirement fields.
- M1: Discrete requirement blocks (one per table row / JD section).
- M2: Config-driven exclusion zone stripper.
- M3: Verbatim evidence quote check inside block.
- M4: Fixed header synonym table (read table cells by header name, never column index).
"""

from __future__ import annotations

import logging
import re
from typing import Any, List, Optional
from bs4 import BeautifulSoup

from config import is_placeholder, is_strict_field_mapping

_LOG = logging.getLogger(__name__)

# M2: Candidate submission table markers (headers indicating operational recruiter reports/trackers)
CANDIDATE_TABLE_HEADERS = (
    "candidate name",
    "candidate",
    "candidate_name",
    "applicant name",
    "resumes sent date",
    "resume sent date",
    "submitted date",
    "submission date",
    "mobile no",
    "mobile number",
    "contact no",
    "phone number",
    "contact number",
    "email id",
    "candidate email",
    "total experience",
    "relevant experience",
    "current ctc",
    "expected ctc",
    "current organization",
    "current company",
    "holding any offer",
    "offer in hand",
    "l1 interview",
    "l2 interview",
    "interview status",
    "status of candidate",
    "feedback",
    "screening status",
    "shortlisted",
    "rejected",
    "no of submissions",
    "number of submissions",
    "submission report",
    "details of list of candidate submitted",
    "tracker",
)

# M2: Signature & footer markers
SIGNATURE_STARTS = (
    r"(?im)^\s*--\s*[-—]?\s*$",
    r"(?im)^\s*_{3,}\s*$",
    r"(?im)^\s*thanks\s*(?:&|and)?\s*regards\b.*$",
    r"(?im)^\s*best\s*regards\b.*$",
    r"(?im)^\s*warm\s*regards\b.*$",
    r"(?im)^\s*with\s*regards\b.*$",
    r"(?im)^\s*sincerely\b.*$",
    r"(?im)^\s*cheers\b.*$",
    r"(?im)^\s*sent\s*from\s*my\s*(?:iphone|ipad|galaxy|android|outlook)\b.*$",
    r"(?im)^\s*get\s*outlook\s*for\s*(?:ios|android)\b.*$",
    r"(?im)^\s*disclaimer\s*:.*$",
    r"(?im)^\s*important\s*/\s*confidential\s*:.*$",
    r"(?im)^this\s+message(?:\s+and\s+any\s+attachments)?\s+is\s+intended\s+only\b.*$",
)

# M2: Quoted reply / history markers
QUOTED_HISTORY_MARKERS = (
    r"(?im)^\s*From:\s+.*$",
    r"(?im)^\s*Sent:\s+.*$",
    r"(?im)^\s*To:\s+.*$",
    r"(?im)^\s*Subject:\s+.*$",
    r"(?im)^\s*-----Original Message-----\s*$",
    r"(?im)^\s*_{10,}\s*$",
    r"(?im)^On\s+.+?wrote:\s*$",
)

# Candidate profile / CV markers for attachments (A4)
CANDIDATE_PROFILE_MARKERS = (
    r"(?i)\b(?:curriculum\s*vitae|resume|cv)\b",
    r"(?i)\b(?:candidate\s*profile|applicant\s*profile)\b",
    r"(?i)\b(?:work\s*experience|employment\s*history|professional\s*experience)\s*:",
    r"(?i)\b(?:educational\s*qualification|education)\s*:",
    r"(?i)\b(?:personal\s*details|passport\s*no|date\s*of\s*birth|dob)\s*:",
    r"(?i)\b(?:declaration|hobbies|languages\s*known)\s*:",
)


def is_candidate_profile_text(text: str) -> bool:
    """
    Check if text represents a candidate profile/resume rather than job descriptions (A4).
    """
    if not text:
        return False
    matches = sum(1 for m in CANDIDATE_PROFILE_MARKERS if re.search(m, text))
    return matches >= 2


def strip_candidate_tables(text: str) -> str:
    """
    M2: Strip candidate submission/status tables from text.
    """
    if not text:
        return ""

    # 1. HTML table stripping
    if "<table" in text.lower():
        try:
            soup = BeautifulSoup(text, "html.parser")
            for table in soup.find_all("table"):
                header_text = " ".join(th.get_text(" ", strip=True).lower() for th in table.find_all(["th", "td"]))
                # If table contains candidate markers, strip it
                cand_matches = sum(1 for m in CANDIDATE_TABLE_HEADERS if m in header_text)
                if cand_matches >= 2:
                    table.decompose()
            text = str(soup)
        except Exception:
            pass

    # 2. Text line-based stripping
    lines = text.splitlines()
    clean_lines: list[str] = []
    in_candidate_block = False
    cand_line_count = 0

    # Candidate template intro and strong triggers
    CANDIDATE_TEMPLATE_START_RE = re.compile(
        r"(?i)\b(?:profile\s*submission\s*template|submission\s*template|candidate\s*submission|"
        r"candidate\s*tracker|s/?r\s*num\.?|vendor\s*name)\b"
    )

    STRONG_CANDIDATE_TRIGGERS = frozenset({
        "current ctc", "expected ctc", "current salary", "expected salary",
        "candidate name", "mobile no", "mobile number", "email id", "candidate email",
        "holding any offer", "offer in hand", "resumes sent date", "resume sent date",
        "full name of the candidate", "last full time qualification",
    })

    REQ_BOUNDARY_START_RE = re.compile(
        r"(?i)^\s*(?:[-*•·]\s*)?(?:"
        r"job\s*(?:title|description|details|profile|role)|"
        r"role(?:\s*title)?|position(?:\s*/\s*title)?\b|title\b|jd\b|req(?:uirement)?s?\b|"
        r"(?:mandatory|preferred|technical|key|core|required|must[\s-]have)?\s*skills?\b|"
        r"(?:overall|total|relevant|years\s+of)?\s*exp(?:erience)?\b|"
        r"(?:work\s+|job\s+)?location\b|"
        r"(?:open\s+|no(?:\.|\s*of)?\s*)?(?:positions?|openings?|headcount)\b|"
        r"qualifications?\b|education\b|eligibility\b|"
        r"(?:bill\s+|pay\s+)?rate\b|budget\b|salary\b|ctc\b|"
        r"notice(?:\s*period)?\b|"
        r"work\s*mode\b|shift\b|domain\b"
        r")(?:\s*[:\-–—]|\s+[A-Za-z0-9])"
    )

    # For sliding-window detection: accumulate consecutive candidate header hits
    consecutive_cand_hits = 0

    for i, line in enumerate(lines):
        low = line.strip().lower()

        if not in_candidate_block:
            # Trigger on explicit template intro line or single-line strong candidate label
            if CANDIDATE_TEMPLATE_START_RE.search(low) or any(trigger in low for trigger in STRONG_CANDIDATE_TRIGGERS):
                in_candidate_block = True
                cand_line_count = 0
                consecutive_cand_hits = 0
                continue

            # Multi-header on single line (original check)
            matches = sum(1 for m in CANDIDATE_TABLE_HEADERS if m in low)
            if matches >= 2:
                in_candidate_block = True
                cand_line_count = 0
                consecutive_cand_hits = 0
                continue

            # Sliding window: count consecutive lines each with at least 1 candidate header
            if matches >= 1:
                consecutive_cand_hits += 1
                if consecutive_cand_hits >= 3:
                    # Retroactively remove the last 2 lines added (the ones that triggered)
                    clean_lines = clean_lines[: len(clean_lines) - min(2, len(clean_lines))]
                    in_candidate_block = True
                    cand_line_count = 0
                    consecutive_cand_hits = 0
                    continue
            else:
                consecutive_cand_hits = 0

        else:
            cand_line_count += 1
            # Stop candidate block when hitting a genuine requirement header with separator/value,
            # ensuring candidate field tokens (like '(inr)', '(days)', 'of the candidate') are excluded.
            if REQ_BOUNDARY_START_RE.match(low) and not any(m in low for m in ("(inr)", "(days)", "(ddmmyy)", "of the candidate")):
                in_candidate_block = False
            elif cand_line_count > 60:
                in_candidate_block = False
            else:
                continue

        clean_lines.append(line)

    return "\n".join(clean_lines)



def strip_signatures_and_headers(text: str) -> str:
    """
    M2: Strip signatures, recruiter footers, confidentiality notices, and quoted history.
    """
    if not text:
        return ""

    t = text

    # Strip quoted email history
    REQ_MARKERS = re.compile(
        r"(?i)\b(?:requirement|job\s*description|mandatory\s*skills?|bill\s*rate|years\s+of\s+exp)\b"
    )
    for qm in QUOTED_HISTORY_MARKERS:
        m = re.search(qm, t)
        if m:
            prefix = t[: m.start()]
            suffix = t[m.start():]
            if not REQ_MARKERS.search(prefix) and REQ_MARKERS.search(suffix):
                # The requirement is in the forwarded/quoted content; do not strip it
                pass
            else:
                t = prefix
                break

    # Strip signatures & footers
    for sm in SIGNATURE_STARTS:
        m = re.search(sm, t)
        if m:
            t = t[: m.start()]
            break

    return t.strip()


def strip_all_exclusion_zones(text: str) -> str:
    """
    M2: Apply full exclusion zone stripping (candidate tables + signatures + quoted history).
    """
    if not text:
        return ""
    cleaned = strip_candidate_tables(text)
    cleaned = strip_signatures_and_headers(cleaned)
    return cleaned.strip()


# M4: Fixed header synonym table (read table cells by header name, never column index)
HEADER_SYNONYMS: dict[str, list[str]] = {
    "job_title": [
        "role",
        "job title",
        "job_title",
        "position",
        "designation",
        "profile",
        "skill / role",
        "skill/role",
        "role / skill",
        "requirement",
        "role name",
    ],
    "req_id": [
        "req id",
        "req_id",
        "request id",
        "request-id",
        "requisition id",
        "requisition no",
        "requisition number",
        "jd id",
        "demand id",
        "so#",
        "so id",
        "so number",
        "job id",
    ],
    "experience": [
        "experience",
        "exp",
        "total exp",
        "relevant exp",
        "yoe",
        "years of experience",
        "yrs",
        "exp range",
    ],
    "location": [
        "location",
        "work location",
        "base location",
        "city",
        "job location",
        "pref location",
        "preferred location",
        "wl",
    ],
    "budget": [
        "budget",
        "ctc",
        "package",
        "rate",
        "compensation",
        "salary",
        "billing rate",
        "max ctc",
    ],
    "notice_period": [
        "notice period",
        "notice",
        "np",
        "joining time",
        "availability",
    ],
    "skills": [
        "mandatory skills",
        "primary skills",
        "must have skills",
        "must have",
        "skills",
        "technical skills",
        "tech stack",
        "skill set",
    ],
    "positions": [
        "number of positions",
        "no of positions",
        "positions",
        "openings",
        "headcount",
        "vacancies",
        "count",
    ],
    "priority": [
        "priority",
        "urgency",
    ],
    "work_mode": [
        "work mode",
        "work model",
        "working model",
        "working mode",
        "mode of work",
        "rto/hybrid/wfh",
        "rto/hybrid",
        "rto",
    ],
    "employment_type": [
        "employment type",
        "engagement type",
        "hiring type",
    ],
    "status": [
        "status",
        "job status",
        "demand status",
        "req status",
    ],
}


def match_table_header(header_cell: str) -> str | None:
    """
    M4: Match table header string to canonical field name using synonym table.
    Never uses column indices.
    """
    clean_h = re.sub(r"[:#\-_]+", " ", header_cell.lower()).strip()
    clean_h = re.sub(r"\s+", " ", clean_h)
    if not clean_h:
        return None

    for canon, syns in HEADER_SYNONYMS.items():
        for syn in syns:
            if clean_h == syn or clean_h.startswith(syn + " ") or clean_h.endswith(" " + syn):
                return canon

    return None


def segment_email_into_blocks(
    text: str,
    *,
    subject: str = "",
    html: str | None = None,
) -> list[dict[str, Any]]:
    """
    M1: Segment email into discrete requirement blocks.
    - One per table row if HTML/matrix table present.
    - One per numbered JD / section if multiple JDs present.
    - Single requirement block if single job.
    Shared top text applies ONLY if it explicitly states "for all positions" or "common to all".

    Returns a list of dicts:
        [{"block_text": str, "table_row_fields": dict[str, str] | None, "block_index": int}]
    """
    clean_text = strip_all_exclusion_zones(text)
    if not clean_text and not html:
        return []

    # Check for shared top text
    shared_context = ""
    for line in clean_text.splitlines()[:15]:
        low = line.lower()
        if "for all positions" in low or "common to all" in low or "for all roles" in low:
            shared_context += line + "\n"

    # 1. Try HTML Table Segmentation (M1, M4)
    if html and "<table" in html.lower():
        try:
            soup = BeautifulSoup(html, "html.parser")
            tables = soup.find_all("table")
            for table in tables:
                trs = table.find_all("tr")
                if len(trs) < 2:
                    continue

                # Read header row
                header_row = trs[0]
                headers = [th.get_text(" ", strip=True) for th in header_row.find_all(["th", "td"])]
                col_map: dict[int, str] = {}
                for idx, h in enumerate(headers):
                    canon = match_table_header(h)
                    if canon:
                        col_map[idx] = canon

                # If table has at least role/title or req_id header:
                if any(f in col_map.values() for f in ("job_title", "req_id", "skills")):
                    blocks = []
                    for r_idx, tr in enumerate(trs[1:]):
                        cells = [td.get_text(" ", strip=True) for td in tr.find_all(["th", "td"])]
                        if not any(cells):
                            continue
                        row_fields: dict[str, str] = {}
                        row_text_parts = []
                        for c_idx, cell_val in enumerate(cells):
                            if c_idx in col_map and cell_val:
                                row_fields[col_map[c_idx]] = cell_val
                            if cell_val:
                                row_text_parts.append(cell_val)

                        row_block_text = " | ".join(row_text_parts)
                        if shared_context:
                            row_block_text = f"{shared_context.strip()}\n{row_block_text}"

                        blocks.append({
                            "block_text": row_block_text,
                            "table_row_fields": row_fields,
                            "block_index": r_idx,
                        })

                    if blocks:
                        return blocks
        except Exception as ex:
            _LOG.warning("HTML table segmentation error: %s", ex)

    # 2. Text-based JD Section Segmentation (M1)
    section_split_rx = re.compile(
        r"(?im)^\s*(?:req(?:uirement)?\s*(?:#|no\.?|id)?\s*\d+|job\s*(?:description)?\s*\d+|role\s*\d+|position\s*\d+|\d+[\.\)]\s+[A-Z][^\n\r]{3,})\b",
    )
    matches = list(section_split_rx.finditer(clean_text))
    if len(matches) >= 2:
        blocks = []
        for i, m in enumerate(matches):
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(clean_text)
            sec_text = clean_text[start:end].strip()
            if shared_context and shared_context not in sec_text:
                sec_text = f"{shared_context.strip()}\n{sec_text}"
            blocks.append({
                "block_text": sec_text,
                "table_row_fields": None,
                "block_index": i,
            })
        return blocks

    # 3. Single requirement block fallback
    return [{
        "block_text": clean_text,
        "table_row_fields": None,
        "block_index": 0,
    }]
