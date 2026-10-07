"""
Central Client ID Validator.
Implements C1, C2, and C3 requirements.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from config import DEFAULT_CLIENT_ID_PATTERNS, EXPLICIT_ID_LABELS
from requirement_identity import normalize_client_key

_LOG = logging.getLogger(__name__)

BUDGET_WORDS = (
    "lpa",
    "ctc",
    "cctc",
    "ectc",
    "budget",
    "inr",
    "rs.",
    "rs",
    "salary",
    "lakh",
    "lakhs",
    "per month",
    "per annum",
    "pm",
    "pa",
)

BUDGET_WORD_PATTERN = re.compile(
    r"(?i)\b(lpa|ctc|cctc|ectc|budget|inr|rs|salary|lakhs?|per\s+month|per\s+annum)\b|\b\d+\s*k\b"
)


def _is_numeric_range(val: str) -> bool:
    """
    Check if value is a numeric range:
    two numbers joined by '-' where both have 4 or more digits, or the second is larger than the first.
    """
    m = re.match(r"^(\d+)\s*[-–—]\s*(\d+)$", val.strip())
    if not m:
        return False
    n1_str, n2_str = m.group(1), m.group(2)
    # Check length
    if len(n1_str) >= 4 and len(n2_str) >= 4:
        return True
    try:
        n1 = int(n1_str)
        n2 = int(n2_str)
        if n2 > n1:
            return True
    except ValueError:
        pass
    return False


def _is_experience_date_phone_or_count(val: str) -> str | None:
    """Check if value is experience, date, phone number, pin code, or count."""
    s = val.strip()
    # Date formats (YYYY/MM/DD, YYYY-MM-DD, DD/MM/YYYY, etc.)
    if re.match(r"^\d{4}[/-]\d{1,2}[/-]\d{1,2}$", s) or re.match(r"^\d{1,2}[/-]\d{1,2}[/-]\d{4}$", s):
        return "is_date"
    # Internal sequence formats
    if re.match(r"^\d{4}[/-]\d{2}[/-]\d{2}[/-]\d{3,}$", s):
        return "is_internal_sequence_id"
    # Phone number (10-13 digits, optional +)
    if re.match(r"^\+?\d{10,13}$", s):
        return "is_phone_number"
    # Pin codes (6 digits exact)
    if re.match(r"^\d{6}$", s):
        return "is_pin_code"
    # Experience (e.g. 5+ yrs, 5-8 years, 10yrs)
    if re.search(r"(?i)^\d{1,2}(\+|\s*-\s*\d{1,2})?\s*(?:yrs?|years?|yoe)$", s):
        return "is_experience"
    # Simple count (1-3 digits standalone, e.g. '1', '2', '10')
    if re.match(r"^\d{1,3}$", s):
        return "is_count_or_position"
    return None


def _check_budget_proximity_in_text(val: str, text: str) -> bool:
    """
    Check if any occurrence of val in text is directly associated with budget words
    (e.g., 'Budget: <val>', '<val> LPA', 'CTC: <val>', '<val> per month').
    Does not cross newlines into preceding/subsequent table rows.
    """
    if not val or not text:
        return False
    val_lower = val.lower()
    text_lower = text.lower()
    start_pos = 0
    while True:
        idx = text_lower.find(val_lower, start_pos)
        if idx == -1:
            break
        # Bound to current line to avoid picking up previous/next table cells
        line_start = max(0, text_lower.rfind("\n", 0, idx) + 1)
        line_end = text_lower.find("\n", idx + len(val))
        if line_end == -1:
            line_end = len(text_lower)

        window_start = max(line_start, idx - 40)
        window_end = min(line_end, idx + len(val) + 40)
        window_text = text_lower[window_start:window_end]

        if BUDGET_WORD_PATTERN.search(window_text):
            # If the occurrence is directly preceded by an explicit ID label, it's a genuine ID
            if not _check_explicit_label_in_text(val, text):
                return True

        start_pos = idx + len(val)
    return False


def _check_explicit_label_in_text(val: str, text: str) -> bool:
    """Check if val follows an explicit ID label in text."""
    if not val or not text:
        return False
    val_escaped = re.escape(val)
    labels_pattern = "|".join(re.escape(lbl) for lbl in EXPLICIT_ID_LABELS)
    # Match: label followed by [:=-#]? and then val
    rx = re.compile(rf"(?i)(?:{labels_pattern})\s*[:=\-#]?\s*{val_escaped}\b")
    return bool(rx.search(text))


def is_genuine_client_id(
    client: str | None,
    value: Any,
    context: Any = None,
) -> tuple[bool, str | None, str | None]:
    """
    Validate whether value is a genuine client ID.
    Replaces every ID check across the codebase.

    Returns:
        (is_valid, cleaned_client_id, rejection_reason)
        If valid: (True, cleaned_client_id, None)
        If rejected: (False, None, rejection_reason)
    """
    if value is None:
        return False, None, "is_null"

    raw = str(value).strip().strip("[]()")
    if not raw or raw.lower() in ("none", "null", "not_found", "n/a", "unknown", "unassigned", "undefined", ""):
        return False, None, "placeholder_or_empty"

    # Reject placeholder formats (ACC-2026-..., LTTS-2026-..., REQ-2026-...)
    if re.match(r"^(LTTS|ACC|REQ)[-_](?:19\d\d|20\d\d)[-_/]", raw, re.IGNORECASE):
        _LOG.info("client_id_rejected value=%r reason=%s", raw, "fabricated_placeholder")
        return False, None, "fabricated_placeholder"

    # Reject noise label artifacts
    if raw.endswith(":") or any(term in raw.lower() for term in ["job description", "comments for supplier"]):
        _LOG.info("client_id_rejected value=%r reason=%s", raw, "label_artifact")
        return False, None, "label_artifact"

    # C2 Check 1: Numeric range check (e.g. 200000-250000)
    if _is_numeric_range(raw):
        _LOG.info("client_id_rejected value=%r reason=%s", raw, "numeric_range")
        return False, None, "numeric_range"

    # C2 Check 2: Experience, dates, phone numbers, counts, pin codes, positions
    exp_or_date = _is_experience_date_phone_or_count(raw)
    if exp_or_date:
        _LOG.info("client_id_rejected value=%r reason=%s", raw, exp_or_date)
        return False, None, exp_or_date

    # Extract context text and other rows if provided
    context_text = ""
    other_rows: list[dict[str, Any]] = []
    if isinstance(context, str):
        context_text = context
    elif isinstance(context, dict):
        body_part = str(context.get("text") or context.get("body") or context.get("email_body") or "")
        subj_part = str(context.get("subject") or context.get("email_subject") or "")
        context_text = f"{subj_part}\n{body_part}".strip()
        other_rows = context.get("other_rows") or []
        if "subject" in context and context.get("subject") not in context_text:
            context_text = f"{context.get('subject')}\n{context_text}"
        other_rows = context.get("other_rows") or []

    # C2 Check 3: Near budget words
    if context_text and _check_budget_proximity_in_text(raw, context_text):
        _LOG.info("client_id_rejected value=%r reason=%s", raw, "near_budget_words")
        return False, None, "near_budget_words"

    # C2 Check 4: Verbatim evidence quote in email (if context provided)
    if context_text and raw.lower() not in context_text.lower():
        _LOG.info("client_id_rejected value=%r reason=%s", raw, "no_verbatim_evidence")
        return False, None, "no_verbatim_evidence"

    # C2 Check 5: Multi-row collision in same email with different title/city
    if other_rows:
        for r in other_rows:
            other_id = str(r.get("client_jd_id") or r.get("req_id") or "").strip()
            if other_id.lower() == raw.lower():
                # Compare title and location
                curr_title = str(context.get("job_title") or "").strip().lower()
                other_title = str(r.get("job_title") or "").strip().lower()
                curr_loc = str(context.get("location") or "").strip().lower()
                other_loc = str(r.get("location") or "").strip().lower()
                if (curr_title and other_title and curr_title != other_title) or (
                    curr_loc and other_loc and curr_loc != other_loc
                ):
                    _LOG.info("client_id_rejected value=%r reason=%s", raw, "duplicate_value_different_roles")
                    return False, None, "duplicate_value_different_roles"

    # C1 Pattern Check per client
    norm_client = normalize_client_key(client)
    pattern = DEFAULT_CLIENT_ID_PATTERNS.get(norm_client) if norm_client and norm_client != "unknown" else None

    if pattern:
        # Client has a configured pattern
        if not re.match(pattern, raw, re.IGNORECASE):
            _LOG.info("client_id_rejected value=%r client=%s reason=%s", raw, norm_client, "pattern_mismatch")
            return False, None, f"pattern_mismatch_for_{norm_client}"
    else:
        # If no specific client is provided or client has no fixed pattern:
        # Check if raw matches ANY configured pattern in technical settings
        matched_any = False
        if not norm_client or norm_client == "unknown":
            for p in DEFAULT_CLIENT_ID_PATTERNS.values():
                if p and re.match(p, raw, re.IGNORECASE):
                    matched_any = True
                    break
        if not matched_any:
            # Clients without a fixed pattern (pwc, ltts, itc, etc.):
            # Accept an ID only when it follows an explicit ID label in the email and is 4-20 chars
            if len(raw) < 4 or len(raw) > 20:
                _LOG.info("client_id_rejected value=%r client=%s reason=%s", raw, norm_client, "length_out_of_range")
                return False, None, "length_out_of_range"
            if context_text and not _check_explicit_label_in_text(raw, context_text):
                _LOG.info("client_id_rejected value=%r client=%s reason=%s", raw, norm_client, "missing_explicit_id_label")
                return False, None, "missing_explicit_id_label"

    # Normalized clean ID
    cleaned = re.sub(r"\s+", "", raw).upper() if not re.match(r"^\d+-\d+$", raw) else raw.strip()
    return True, cleaned, None
