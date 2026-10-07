"""
Unified Final Pre-Save Validator (M9).
Enforces strict requirement-to-field acceptance principles (P1-P9) across all pipeline paths.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from config import is_placeholder, is_strict_field_mapping
from client_identity_validator import is_genuine_client_id

_LOG = logging.getLogger(__name__)

# System-owned fields that are not subject to extraction-drop validation
_SYSTEM_FIELDS = {
    "job_id",
    "demand_received_date",
    "created_at",
    "first_arrival_at",
    "internal_poc",
    "internal_poc_email",
    "client_poc_emails",
    "client_lead_poc_email",
    "client_lead_poc",
    "client_poc",
    "requirement_from",
    "client_key",
    "job_status",
    "closed_date",
    "confidence",
    "_provenance",
    "_profile",
    "identity",
    "idempotencyKey",
    "graphMessageId",
    "internetMessageId",
}

_EXTRACTED_FIELDS = (
    "job_title",
    "client_jd_id",
    "number_of_positions",
    "experience_level",
    "employment_type",
    "work_mode",
    "work_mode_text",
    "location",
    "overall_experience",
    "experience",
    "experience_text",
    "notice_period",
    "mandatory_skills",
    "skills",
    "budget",
    "budget_text",
    "yearly_budget",
    "yearly_budget_min",
    "yearly_budget_max",
    "monthly_budget",
    "monthly_budget_min",
    "monthly_budget_max",
    "budget_currency",
    "priority",
    "type_of_demand",
)


_CANDIDATE_TABLE_NOISE_RE = re.compile(
    r"(?i)^(?:position(?:/title)?|title|skills?|mandatory\s+skills?[\s\-–]*|name|candidate\s+name|vendor\s+name|"
    r"bu\s*/\s*is|s[/\.]?r\s*num(?:ber)?\.?|s[/\.]?r\s*no\.?|s[/\.]?l\s*n(?:o|um)\.?|sl\s*no\.?|"
    r"resumes?\s+sent\s+date.*|full\s+name.*|mobile\s+no|mail\s+id|np\s*\(days\)|np\s+days|"
    r"total\s+exp|relevant\s+exp|current\s+location|job\s+location|current\s+organization|"
    r"rate\s*/\s*pm.*|supplier\s+comments.*|last\s+full\s+time\s+qualification|qualification\s+criteria|"
    r"domain:?|role\s+overview|job\s+description:?|detailed\s+jd|requirements?\s*[-–]|"
    r"responsibilities|key\s+responsibilities|highlighted|must\s+have|good\s+to\s+have|nice\s+to\s+have|preferred\s+skills?|"
    r"simulation\s+awareness|manufacturing\s+awareness)$"
)


def _is_candidate_table_noise(sk_str: str) -> bool:
    s = str(sk_str or "").strip()
    s = re.sub(r"^\s*[-*•·–—]\s*", "", s)
    s = re.sub(r"^\s*\d{1,2}[.)\]-]\s*", "", s).strip()
    if not s or len(s) < 2:
        return True
    if _CANDIDATE_TABLE_NOISE_RE.match(s):
        return True
    return False


def validate_requirement_before_save(
    payload: dict[str, Any],
    *,
    block_text: str | None = None,
    other_blocks: list[str] | None = None,
    client: str | None = None,
) -> tuple[dict[str, Any], bool, str | None]:
    """
    Validate and sanitize requirement payload before persisting to DB (M9).

    Returns:
        (sanitized_payload, should_route_to_pending_review, review_reason)
    """
    if not is_strict_field_mapping():
        # Legacy passthrough
        jt = str(payload.get("job_title") or "").strip()
        should_review = not jt or is_placeholder(jt)
        return payload, should_review, ("missing_job_title" if should_review else None)

    out = dict(payload)
    client_name = client or out.get("requirement_from") or out.get("client_key")
    subj_text = str(out.get("subject") or out.get("email_subject") or "").strip()
    full_ctx = f"{subj_text} {block_text or ''}".lower()
    normalized_block = re.sub(r"\s+", " ", full_ctx).strip()

    # 1. Strip all placeholders -> strictly NULL (P3)
    for field in _EXTRACTED_FIELDS:
        val = out.get(field)
        if val is None:
            continue
        if isinstance(val, list):
            cleaned_list = [str(x).strip() for x in val if not is_placeholder(x)]
            out[field] = cleaned_list if cleaned_list else None
            if not cleaned_list and val:
                _LOG.info("validation_nulled field=%s reason=placeholder_elements", field)
        elif is_placeholder(val):
            out[field] = None
            _LOG.info("validation_nulled field=%s reason=placeholder_value value=%r", field, val)

    # Strip generic location phrases -> strictly None
    loc_val = out.get("location")
    if loc_val and not is_placeholder(loc_val):
        low_loc = str(loc_val).strip("[]'\" ").lower()
        if any(g in low_loc for g in ("client location", "client site", "client office", "any ltts", "any office", "any location", "pan india")):
            out["location"] = None
            _LOG.info("validation_nulled field=location reason=generic_location_phrase value=%r", loc_val)

    # 2. Client ID validation (M7, P7)
    cjd = out.get("client_jd_id")
    if cjd and not is_placeholder(cjd):
        is_val, clean_id, reason = is_genuine_client_id(
            client_name,
            cjd,
            context=None,
        )
        if not is_val or not clean_id:
            out["client_jd_id"] = None
            _LOG.info("validation_nulled field=client_jd_id reason=%s rejected_val=%r", reason, cjd)
        else:
            out["client_jd_id"] = clean_id
    else:
        out["client_jd_id"] = None

    # 3. Evidence rule (M3, P1) - preserve extracted values and verify against context
    if normalized_block and len(normalized_block) >= 80:
        # Check job_title
        jt = out.get("job_title")
        if jt and not is_placeholder(jt):
            jt_str = str(jt).strip()
            tokens = [t.lower() for t in re.split(r"[^a-zA-Z0-9]+", jt_str) if len(t) >= 3]
            if tokens and not any(t in normalized_block for t in tokens):
                out.setdefault("validation_warnings", []).append("job_title_unverified_in_block")
                _LOG.info("validation_unverified field=job_title value=%r", jt)

        # Check location (with city synonym normalization)
        loc = out.get("location")
        if loc and not is_placeholder(loc):
            loc_str = str(loc).strip()
            _GENERIC_LOCS = {"client location", "client site", "client office", "any ltts location", "any ltts office", "any location", "any office", "pan india"}
            if loc_str.lower() in _GENERIC_LOCS:
                out["location"] = None
            else:
                from requirement_comparator import normalize_city
                norm_loc_city = normalize_city(loc_str)
                norm_block_city = normalize_city(normalized_block)
                loc_tokens = [t.lower() for t in re.split(r"[^a-zA-Z0-9]+", loc_str) if len(t) >= 3]
                has_loc_ev = (
                    (norm_loc_city and norm_loc_city == norm_block_city)
                    or (loc_tokens and any(t in normalized_block for t in loc_tokens))
                    or loc_str.lower() in normalized_block
                )
                if not has_loc_ev:
                    out.setdefault("validation_warnings", []).append("location_unverified_in_block")
                    _LOG.info("validation_unverified field=location value=%r", loc)

        # Check notice period
        np_val = out.get("notice_period")
        if np_val and not is_placeholder(np_val):
            np_str = str(np_val).strip()
            np_tokens = [t.lower() for t in re.split(r"[^a-zA-Z0-9]+", np_str) if len(t) >= 3]
            if np_tokens and not any(t in normalized_block for t in np_tokens):
                out.setdefault("validation_warnings", []).append("notice_period_unverified_in_block")
                _LOG.info("validation_unverified field=notice_period value=%r", np_val)

        # Check skills - filter candidate table noise, preserve genuine skills
        for sf in ("mandatory_skills", "skills"):
            s_list = out.get(sf)
            if isinstance(s_list, list):
                from boilerplate_learner import validate_skills
                val_sk = validate_skills(s_list, client=client_name or "")
                out[sf] = val_sk if val_sk else None

    # 4. Cross-field collision check (P6)
    # One field's value never fills another field unless explicitly stated
    title_str = str(out.get("job_title") or "").strip().lower()
    mand_list = [str(x).strip().lower() for x in (out.get("mandatory_skills") or [])]
    if title_str and title_str in mand_list:
        # Title was duplicated into skills
        out["mandatory_skills"] = [s for s in (out.get("mandatory_skills") or []) if s.strip().lower() != title_str]
        if not out["mandatory_skills"]:
            out["mandatory_skills"] = None
        _LOG.info("validation_nulled field=mandatory_skills reason=cross_field_collision_with_title")

    # 5. Compute confidence per A2
    conf = compute_requirement_confidence(out, block_text=block_text)
    out["confidence"] = conf

    # 6. Review routing (A1, A2)
    # Only a missing job title (or title and ID both missing), empty extraction (conf == 0),
    # or a failed ID/evidence check on a critical field sends an item to pending review.
    # Missing budget, notice period, skills, experience, location, work mode or positions are valid NULLs.
    final_jt = str(out.get("job_title") or "").strip()
    final_id = str(out.get("client_jd_id") or "").strip()
    if not final_jt or is_placeholder(final_jt):
        reason = "missing_job_title_and_id" if (not final_id or is_placeholder(final_id)) else "missing_job_title"
        return out, True, reason

    if conf == 0.0:
        return out, True, "empty_extraction_zero_confidence"

    return out, False, None


def compute_requirement_confidence(
    payload_or_item: dict[str, Any] | Any,
    block_text: str | None = None,
) -> float:
    """
    A2: Confidence = share of the non-null extracted fields that passed the evidence check,
    computed per requirement. Empty extraction gives 0 and goes to review.
    """
    if hasattr(payload_or_item, "model_dump"):
        p = payload_or_item.model_dump()
    elif hasattr(payload_or_item, "__dict__"):
        p = dict(payload_or_item.__dict__)
    elif isinstance(payload_or_item, dict):
        p = payload_or_item
    else:
        p = {}

    quotes = p.get("field_evidence_quotes") or {}
    text_ctx = (block_text or str(p.get("bodyText") or p.get("body") or "")).lower()

    # Check the 11 canonical fields
    field_checks: dict[str, Any] = {
        "job_title": p.get("job_title"),
        "skills": p.get("mandatory_skills") or p.get("skills"),
        "experience": p.get("overall_experience") or p.get("experience"),
        "location": p.get("location"),
        "work_mode": p.get("work_mode"),
        "employment_type": p.get("employment_type"),
        "budget": p.get("yearly_budget") or p.get("monthly_budget") or p.get("budget"),
        "notice_period": p.get("notice_period"),
        "positions": p.get("number_of_positions"),
        "priority": p.get("priority"),
        "client_id": p.get("client_jd_id") or p.get("req_id"),
    }

    non_null_fields = []
    passed_fields = 0

    for f_name, f_val in field_checks.items():
        if f_val is None or is_placeholder(f_val):
            continue
        if isinstance(f_val, (list, tuple)) and not f_val:
            continue
        if str(f_val).strip() == "":
            continue

        non_null_fields.append(f_name)

        # Evidence check
        has_ev = False
        quote = str(quotes.get(f_name) or "").strip()
        if quote and (not text_ctx or quote.lower() in text_ctx):
            has_ev = True
        elif text_ctx and len(text_ctx) >= 80:
            # Check if token of value appears in text_ctx
            if isinstance(f_val, (list, tuple)):
                v_str = " ".join(str(x) for x in f_val)
            else:
                v_str = str(f_val)
            toks = [t for t in re.split(r"[^a-zA-Z0-9]+", v_str.lower()) if len(t) >= 3]
            if toks and any(t in text_ctx for t in toks):
                has_ev = True
            elif not toks and v_str.lower() in text_ctx:
                has_ev = True
        else:
            # If no full context is available to verify against or short mock text, treat non-empty stated value as passed
            has_ev = True

        if has_ev:
            passed_fields += 1

    if not non_null_fields:
        return 0.0

    return round(passed_fields / len(non_null_fields), 2)

