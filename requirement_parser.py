"""
AI-based structured extraction of recruitment fields from email (+ optional PDF text).
Supports multiple requirements in one email with per-item confidence.
"""

from __future__ import annotations

import os
import re
import time
from typing import Any, TYPE_CHECKING

import structlog
from pydantic import ValidationError

from intake_gates import is_status_or_tracker_report
from models import ExtractionMethodEnum, RequirementItem, RequirementParseResult, to_strict_json_schema, verify_evidence_quotes
from glossary import TermGlossary
from utils import bind_log_context, clear_log_context
from utils import parse_json_loose
from config import is_strict_field_mapping
from strict_validator import compute_requirement_confidence
from requirement_comparator import normalize_city

if TYPE_CHECKING:
    from config import Settings

_LOG = structlog.get_logger(__name__)

from pathlib import Path

_PROMPT_FILE = Path(__file__).resolve().parent / "extraction_prompt.txt"
if _PROMPT_FILE.exists():
    _PARSER_SYSTEM = _PROMPT_FILE.read_text(encoding="utf-8").strip()
else:
    _PARSER_SYSTEM = "Extract ONE hiring requirement from the text below. Return JSON only."


def build_parser_system_prompt() -> str:
    """Constructs the full system prompt sent to the LLM from extraction_prompt.txt."""
    return _PARSER_SYSTEM


SCHEMA_EVIDENCE_PROPS = {
    "job_title": {"type": ["string", "null"]},
    "location": {"type": ["string", "null"]},
    "experience_text": {"type": ["string", "null"]},
    "exp_min": {"type": ["string", "null"]},
    "exp_max": {"type": ["string", "null"]},
    "budget_text": {"type": ["string", "null"]},
    "budget_min": {"type": ["string", "null"]},
    "budget_max": {"type": ["string", "null"]},
    "budget_unit": {"type": ["string", "null"]},
    "budget_period": {"type": ["string", "null"]},
    "monthly_budget_text": {"type": ["string", "null"]},
    "mandatory_skills": {"type": ["string", "null"]},
    "skills": {"type": ["string", "null"]},
    "notice_period": {"type": ["string", "null"]},
    "work_mode_text": {"type": ["string", "null"]},
    "work_mode": {"type": ["string", "null"]},
    "positions": {"type": ["string", "null"]},
    "client_req_id": {"type": ["string", "null"]},
    "priority_text": {"type": ["string", "null"]},
}

STRICT_EXTRACTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "job_title": {"type": ["string", "null"]},
        "location": {"type": ["array", "null"], "items": {"type": "string"}},
        "experience_text": {"type": ["string", "null"]},
        "exp_min": {"type": ["number", "null"]},
        "exp_max": {"type": ["number", "null"]},
        "budget_text": {"type": ["string", "null"]},
        "budget_min": {"type": ["number", "null"]},
        "budget_max": {"type": ["number", "null"]},
        "budget_unit": {"type": ["string", "null"]},
        "budget_period": {"type": ["string", "null"]},
        "monthly_budget_text": {"type": ["string", "null"]},
        "mandatory_skills": {"type": ["array", "null"], "items": {"type": "string"}},
        "skills": {"type": ["array", "null"], "items": {"type": "string"}},
        "notice_period": {"type": ["string", "null"]},
        "work_mode_text": {"type": ["string", "null"]},
        "work_mode": {"type": ["string", "null"]},
        "positions": {"type": ["number", "null"]},
        "client_req_id": {"type": ["string", "null"]},
        "priority_text": {"type": ["string", "null"]},
        "evidence": {
            "type": ["object", "null"],
            "additionalProperties": False,
            "properties": SCHEMA_EVIDENCE_PROPS,
            "required": list(SCHEMA_EVIDENCE_PROPS.keys()),
        },
    },
    "required": [
        "job_title",
        "location",
        "experience_text",
        "exp_min",
        "exp_max",
        "budget_text",
        "budget_min",
        "budget_max",
        "budget_unit",
        "budget_period",
        "monthly_budget_text",
        "mandatory_skills",
        "skills",
        "notice_period",
        "work_mode_text",
        "work_mode",
        "positions",
        "client_req_id",
        "priority_text",
        "evidence",
    ],
}

_PARSER_USER = """Subject:
{subject}

Body and attachment excerpts:
{body}
"""

from glossary import TermGlossary

_FIELD_SYNONYMS: dict[str, tuple[str, ...]] = {
    "notice_period": TermGlossary.get_field_synonyms("notice_period"),
    "experience": TermGlossary.get_field_synonyms("experience"),
    "budget": TermGlossary.get_field_synonyms("budget"),
    "location": TermGlossary.get_field_synonyms("location"),
    "job_title": TermGlossary.get_field_synonyms("job_title"),
    "skills": TermGlossary.get_field_synonyms("mandatory_skills") + TermGlossary.get_field_synonyms("soft_skills"),
}


def _label_variant_pattern(values: tuple[str, ...]) -> str:
    return "|".join(re.escape(v).replace(r"\ ", r"\s+") for v in values)


_EXP_RE = re.compile(r"(?i)\b(\d{1,2}(?:\.\d+)?\s*(?:[-–—~\u2011\ufffd]|to)\s*\d{1,2}(?:\.\d+)?|\d{1,2}(?:\.\d+)?\+?)\s*(?:years?|yrs?|yoe)\b")
_EXP_LABEL_RE = re.compile(
    rf"(?i)\b(?:{_label_variant_pattern(_FIELD_SYNONYMS['experience'])})\b\s*(?:[:\-]|is)?\s*(\d{{1,2}}(?:\.\d+)?(?:\s*(?:[-–—~\u2011\ufffd]|to)\s*\d{{1,2}}(?:\.\d+)?|\+?)?(?:\s*(?:years?|yrs?|yoe))?)"
)
_NOTICE_RE = re.compile(
    rf"(?i)\b(?:{_label_variant_pattern(_FIELD_SYNONYMS['notice_period'])})\b\s*(?:[:\-]|is)\s*([a-z0-9 +/\-]{{2,40}})"
)
_NOTICE_CONTEXT_RE = re.compile(
    r"(?i)\b(immediate(?:\s+joiner)?|joiners?\s+only|serving\s+notice|lwd|last\s+working\s+day|availability(?:\s+to\s+join)?)\b"
)
_LPA_RE = re.compile(
    r"(?i)\b(\d+(?:\.\d+)?)\s*(?:-|to|–|—)?\s*(\d+(?:\.\d+)?)?\s*(?:lpa|lakh)\b"
)
_LPM_RE = re.compile(
    r"(?i)\b(\d+(?:\.\d+)?)\s*(?:-|to|–|—)?\s*(\d+(?:\.\d+)?)?\s*(?:lpm|lakhs?\s*per\s*month)\b"
)
_BUDGET_LABELLED_RE = re.compile(
    rf"(?i)\b(?:{_label_variant_pattern(_FIELD_SYNONYMS['budget'])})\b\s*(?:[:\-]|is)?\s*(?P<low>\d+(?:\.\d+)?)\s*(?:-|to|–|—)?\s*(?P<high>\d+(?:\.\d+)?)?\s*(?P<unit>lpa|lakhs?|pa|per\s*annum)?\b"
)
_LOCATION_LABEL_RE = re.compile(
    rf"(?i)\b(?:{_label_variant_pattern(_FIELD_SYNONYMS['location'])})\b\s*[:\-]\s*([a-z0-9 ,/&()\-]{{2,120}})"
)
_JOB_TITLE_LABEL_RE = re.compile(
    rf"(?im)\b(?:{_label_variant_pattern(_FIELD_SYNONYMS['job_title'])})\b\s*[:\-]\s*([a-z0-9/&+().,\- ]{{3,100}})$"
)
_MIN_POSITIONS_RE = re.compile(
    r"(?i)\b(?:need|require|looking for|openings?|positions?|headcount)\s*(?:min(?:imum)?\s*)?(\d{1,3})\s*(?:immediate\s+joiner\s+)?(?:profiles?|resources?|candidates?)?\b"
)
_IMMEDIATE_RE = re.compile(r"(?i)\b(immediate(?:\s+joiner)?|join\s+immediately)\b")
_ENGAGEMENT_RE = re.compile(r"(?i)\b(3pt|c2h|c2c|contract|full[- ]?time|fte)\b")
_DURATION_RE = re.compile(r"(?i)\b(\d{1,2}\s*(?:month|months|mon|week|weeks|day|days))\b")
_CONTRACT_DURATION_RE = re.compile(
    r"(?i)\b(?:contract\s*(?:duration|period|tenure)?|duration|tenure)\b[^\n]{0,30}?\b(\d{1,2}\s*(?:month|months|mon|week|weeks|day|days))\b"
)
_REMOTE_RE = re.compile(r"(?i)\bremote\b")
_THREAD_FROM_RE = re.compile(r"(?im)^\s*from\s*:")
_THREAD_SENT_RE = re.compile(
    r"(?im)^\s*sent\s*:\s*(?P<dt>.+)$"
)
_SKILL_LINE_RE = re.compile(
    rf"(?im)\b(?:{_label_variant_pattern(_FIELD_SYNONYMS['skills'])})\b\s*[:\-]\s*(.+)$"
)
_SKILL_SECTION_HEADER_RE = re.compile(
    rf"(?i)^\s*(?:required\s+skills?|{_label_variant_pattern(_FIELD_SYNONYMS['skills'])})\s*[:\-]?\s*(.*)$"
)
_SKILL_SECTION_STOP_RE = re.compile(
    r"(?i)^\s*(experience|required|location|work loc|pref loc|base location|budget|ctc|ectc|compensation|notice|np|lwd|role overview|job title|role|ta poc|spoc|from|sent|subject)\b"
)
_EXP_PLUS_RE = re.compile(r"(?i)\b(\d{1,2}(?:\.\d+)?)\s*\+\s*(?:years?|yrs?)\b")
_EXP_RANGE_RE = re.compile(
    r"(?i)\b(\d{1,2}(?:\.\d+)?)\s*[-–—~\u2011\ufffd]\s*(\d{1,2}(?:\.\d+)?)\s*(?:years?|yrs?)\b"
)
_BUDGET_RANGE_RE = re.compile(
    r"(?i)\b(?:range\s*[-:]?\s*)?(\d+(?:\.\d+)?)\s*(?:to|-|–|—)\s*(\d+(?:\.\d+)?)\s*lpa\b"
)
_HIKE_RE = re.compile(r"(?i)\b(40\s*/\s*50%|50%|40%)\s*hike\b")
_LOCATION_INLINE_RE = re.compile(r"(?i)\b([a-z]{3,30}\s*/\s*[a-z]{3,30})\b")
_ROLE_HINT_RE = re.compile(
    r"(?i)\b([a-z][a-z0-9&/+\- ]{1,60}\b(?:developer|lead|engineer|analyst|administrator|architect|consultant))\b"
)
_CANDIDATE_TABLE_MARKERS = (
    "candidate name",
    "contact number",
    "email id",
    "emailid",
    "submission date",
    "preferred location",
    "current company",
    "current ctc",
    "expected ctc",
    "ectc",
    "cctc",
    "lwd",
    "so id",
    "s.no",
    "sl no",
    "skillset",
    "skillset",
    "total exp",
    "relevant exp",
    "interview availability",
)
_REQUIREMENT_MARKERS = (
    "role",
    "skill",
    "skills",
    "exp",
    "experience",
    "location",
    "budget",
    "np",
    "notice",
    "jd",
    "urgent",
    "requirement",
)
_EXCEPT_LOC_RE = re.compile(
    r"(?i)\b(?:all\s+location[s]?|any\s+location[s]?)\s+except\s*[-:]?\s*([a-z ]{3,40})"
)
_SUBJECT_ROLE_RE = re.compile(r"(?i)\b(?:requirement\s*[-:]\s*)?(sap\s+[a-z0-9/+ ]{2,25})\b")
_SUBJECT_HIRING_ROLE_RE = re.compile(
    r"(?i)\b(?:hiring\s+for|requirement\s+for|looking\s+for|role\s+for)\s+([a-z0-9/&+().,\- ]{3,90})"
)
_SUBJECT_PREFIX_RE = re.compile(r"(?i)^\s*(?:re|fw|fwd|recall)\s*:\s*")
_SUBJECT_ROLE_FALLBACK_RE = re.compile(
    r"(?i)\b(?:requirement|drive|request(?:\s+to\s+upload)?\s+relevant\s+profiles?|open\s+positions?)\b\s*[:_\-|]*\s*([a-z0-9/&+().,\- ]{3,100})"
)
_SUBJECT_REQUIREMENT_TITLE_RE = re.compile(
    r"(?i)\brequirement\b\s*[-:|–—\ufffd]\s*([a-z0-9/&+().,\- ]{3,100})"
)
_SUBJECT_TECH_SKILL_RE = re.compile(
    r"(?i)\b(sap(?:\s+[a-z0-9]+)?|abap|java|python|databricks|azure|salesforce|piping|kinaxis|apriso|snowflake|power\s*bi|oauth|saml|oidc|api|tester|testing|developer|engineer|analyst|consultant|checker)\b"
)
_EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_PHONE_RE = re.compile(r"(?i)\b\+?\d[\d\s-]{8,}\b")
_MULTI_JD_SIGNAL_RE = re.compile(
    r"(?im)\b(req\s*\d+|role\s*\d+|multiple roles|roles|requirements|tables|job description\s*\d+)\b|^\s*sr\.?\s*no\.?\s*\|\s*role\b"
)
_DEMAND_SIGNAL_RE = re.compile(
    r"(?i)\b(requirement|urgent drive|need profiles|request to upload|open positions?|hiring|looking for|position open)\b"
)
_TITLE_LOCATION_SPLIT_RE = re.compile(r"\s*(?:,|-|\||/)\s*")
_TITLE_LOCATION_TOKEN_RE = re.compile(
    r"(?i)\b("
    r"airoli|mumbai|bangalore|bengaluru|mysore|hyderabad|pune|vadodara|kolkata|chennai|"
    r"delhi|gurgaon|noida|remote|onsite|on-site|any\s+\w+\s+location|location"
    r")\b"
)
_EXPLICIT_SKILL_TOKEN_RE = re.compile(
    r"(?i)\b("
    r"python|java|c\+\+|c#|\.net|node\.?js|react|angular|vue|django|flask|spring boot|"
    r"kubernetes|docker|terraform|ansible|jenkins|gitlab|github actions|linux|sql|mysql|postgresql|"
    r"mongodb|redis|snowflake|databricks|pyspark|spark|hadoop|tableau|power bi|"
    r"sap(?:\s+[a-z0-9]+)?|abap|odata|idoc|cds|s4hana|teamcenter|tekla|autocad|labview|"
    r"aws|azure|gcp|ec2|s3|lambda|rds|eks|ecs|cloudwatch|iam|aks|adf|synapse|devops|"
    r"machine learning|signal processing|plc|emi/emc"
    r")\b"
)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _strip_subject_prefixes(subject: str) -> str:
    s = (subject or "").strip()
    while True:
        m = _SUBJECT_PREFIX_RE.match(s)
        if not m:
            break
        s = s[m.end() :].strip()
    return s


def _clean_job_title(title: str) -> str:
    """
    Keep only functional role in title; strip location fragments (e.g., Mumbai/Airoli).
    """
    t = re.sub(r"\s+", " ", (title or "")).strip(" .:-_|")
    if not t:
        return ""
    parts = [p.strip(" .:-_|") for p in _TITLE_LOCATION_SPLIT_RE.split(t) if p.strip(" .:-_|")]
    if len(parts) <= 1:
        t2 = re.sub(r"\(\s*(?:airoli|mumbai|bangalore|mysore|hyderabad|pune|vadodara)\s*\)", "", t, flags=re.I)
        return re.sub(r"\s{2,}", " ", t2).strip(" .:-_|")
    kept: list[str] = []
    for p in parts:
        if _TITLE_LOCATION_TOKEN_RE.search(p):
            continue
        kept.append(p)
    cleaned = " ".join(kept).strip(" .:-_|")
    if not cleaned:
        cleaned = parts[0]
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" .:-_|")
    return cleaned[:120]


def _extract_subject_role_fallback(subject: str) -> str:
    s = _strip_subject_prefixes(subject)
    if not s:
        return ""
    req_m = _SUBJECT_REQUIREMENT_TITLE_RE.search(s)
    if req_m:
        req_title = re.sub(r"\s+", " ", req_m.group(1)).strip(" .:-_|")
        req_title = re.sub(r"(?i)\b(?:mysore|bangalore|vadodara|hyderabad|pune|kolkata|mumbai)\b$", "", req_title).strip(
            " ,-"
        )
        if req_title:
            return _clean_job_title(req_title)[:100]
    primary_m = re.search(
        r"(?i)\b((?:sap|azure|salesforce|databricks|java|python|piping|kinaxis|apriso|snowflake)[a-z0-9/&+().,\- ]{0,80}?)(?:\bdrive\b|\brequirement\b|$)",
        s,
    )
    if primary_m:
        primary = re.sub(r"\s+", " ", primary_m.group(1)).strip(" .:-_|")
        primary = re.sub(r"\s+\d{4,}\b$", "", primary).strip(" .:-_|")
        if primary and not re.search(r"\d{2,}", primary):
            return _clean_job_title(primary)[:100]
    chunks = [c.strip(" .:-_|") for c in re.split(r"[|]", s) if c.strip(" .:-_|")]
    candidates = chunks or [s]
    best = ""
    for cand in candidates:
        low = _norm(cand)
        if "we need profiles" in low or "face to face" in low:
            continue
        if _SUBJECT_TECH_SKILL_RE.search(cand) and len(cand) >= len(best):
            best = cand
    if not best:
        m = _SUBJECT_ROLE_FALLBACK_RE.search(s)
        if m:
            best = m.group(1).strip()
    best = re.sub(r"(?i)\b(?:today|urgent|immediate|priority)\b.*$", "", best).strip(" .:-_|")
    best = re.sub(r"\s+\d{4,}\b$", "", best).strip(" .:-_|")
    best = re.sub(r"\s{2,}", " ", best)
    return _clean_job_title(best)[:100]


def _has_clear_demand_signal(subject: str, body: str) -> bool:
    return bool(_DEMAND_SIGNAL_RE.search(f"{subject}\n{body}".strip()))


def _extract_rule_fields(subject: str, body: str, block: str | None = None) -> dict[str, Any]:
    from requirement_segmenter import strip_all_exclusion_zones
    from config import lpa_implies_inr

    target_block = block if block is not None else body
    clean_target = strip_all_exclusion_zones(target_block or "")
    text = clean_target if is_strict_field_mapping() else f"{subject}\n{clean_target}"
    out: dict[str, Any] = {}

    exp_m = _EXP_RE.search(text)
    if exp_m:
        out["experience"] = f"{exp_m.group(1)} years".replace("  ", " ").strip()
        out["experience_quote"] = exp_m.group(0).strip()
    else:
        exp_label_m = _EXP_LABEL_RE.search(text)
        if exp_label_m:
            out["experience"] = f"{exp_label_m.group(1)} years".replace("  ", " ").strip()
            out["experience_quote"] = exp_label_m.group(0).strip()

    notice_m = _NOTICE_RE.search(text)
    if notice_m:
        out["notice_period"] = notice_m.group(1).strip()
        out["notice_period_quote"] = notice_m.group(0).strip()
    else:
        immediate_m = _IMMEDIATE_RE.search(text)
        context_m = _NOTICE_CONTEXT_RE.search(text)
        if immediate_m:
            out["notice_period"] = "Immediate"
            out["notice_period_quote"] = immediate_m.group(0).strip()
        elif context_m:
            tok = context_m.group(1).strip()
            low_tok = tok.lower()
            if "serving notice" in low_tok:
                out["notice_period"] = "Serving Notice"
            elif "lwd" in low_tok:
                out["notice_period"] = "LWD Mentioned"
            else:
                out["notice_period"] = "Immediate"
            out["notice_period_quote"] = context_m.group(0).strip()

    title_m = _JOB_TITLE_LABEL_RE.search(text)
    if title_m:
        out["job_title"] = _clean_job_title(re.sub(r"\s+", " ", title_m.group(1)).strip(" .:-"))
        out["job_title_quote"] = title_m.group(0).strip()
    elif not block or block == body:
        sub_m = _SUBJECT_HIRING_ROLE_RE.search(subject or "")
        if sub_m:
            candidate = re.sub(r"\s+", " ", sub_m.group(1)).strip(" .:-")
            candidate = re.sub(
                r"(?i)\b(?:urgent|immediate|joiner|priority)\b.*$",
                "",
                candidate,
            ).strip(" .:-")
            if candidate:
                out["job_title"] = _clean_job_title(candidate)
                out["job_title_quote"] = sub_m.group(0).strip()
                out["job_title_source"] = "email_subject"
        else:
            fallback_title = _extract_subject_role_fallback(subject or "")
            if fallback_title:
                out["job_title"] = _clean_job_title(fallback_title)
                out["job_title_quote"] = _strip_subject_prefixes(subject or "")
                out["job_title_source"] = "email_subject"

    pos_m = _MIN_POSITIONS_RE.search(text)
    if pos_m:
        try:
            val = int(pos_m.group(1))
            out["number_of_positions"] = val
            out["number_of_positions_quote"] = pos_m.group(0).strip()
        except ValueError:
            pass
    if "number_of_positions" not in out:
        pos_label_m = re.search(r"(?i)\b(?:open\s*positions?|positions?|openings?|headcount|no\.?\s*(?:of\s*)?positions?)\b\s*[:\-]\s*(\d{1,3})\b", text)
        if pos_label_m:
            try:
                out["number_of_positions"] = int(pos_label_m.group(1))
                out["number_of_positions_quote"] = pos_label_m.group(0).strip()
            except ValueError:
                pass

    # Budget parsing
    from field_mapper import parse_budget_fields
    bgt_info = parse_budget_fields(text)
    if bgt_info.get("budget_inr_lpm_min") is not None or bgt_info.get("budget_inr_lpm_max") is not None:
        out["monthly_budget_min"] = bgt_info.get("budget_inr_lpm_min")
        out["monthly_budget_max"] = bgt_info.get("budget_inr_lpm_max") or bgt_info.get("budget_inr_lpm_min")
        out["budget_quote"] = bgt_info.get("budget_display") or ""
        out["budget_currency"] = bgt_info.get("budget_currency") or "INR"
    elif bgt_info.get("budget_inr_lpa_min") is not None or bgt_info.get("budget_inr_lpa_max") is not None:
        out["yearly_budget_min"] = bgt_info.get("budget_inr_lpa_min")
        out["yearly_budget_max"] = bgt_info.get("budget_inr_lpa_max") or bgt_info.get("budget_inr_lpa_min")
        out["budget_quote"] = bgt_info.get("budget_display") or ""
        out["budget_currency"] = bgt_info.get("budget_currency") or "INR"
    else:
        multiplier = 1 if is_strict_field_mapping() else 100000
        budget_m = _LPA_RE.search(text)
        if budget_m:
            lo = float(budget_m.group(1))
            hi = float(budget_m.group(2)) if budget_m.group(2) else lo
            out["yearly_budget_min"] = int(min(lo, hi) * multiplier)
            out["yearly_budget_max"] = int(max(lo, hi) * multiplier)
            out["budget_quote"] = budget_m.group(0).strip()
        else:
            budget_monthly_m = _LPM_RE.search(text)
            if budget_monthly_m:
                lo = float(budget_monthly_m.group(1))
                hi = float(budget_monthly_m.group(2)) if budget_monthly_m.group(2) else lo
                out["monthly_budget_min"] = int(min(lo, hi) * multiplier)
                out["monthly_budget_max"] = int(max(lo, hi) * multiplier)
                out["budget_quote"] = budget_monthly_m.group(0).strip()
            else:
                labelled_budget_m = _BUDGET_LABELLED_RE.search(text)
                if labelled_budget_m:
                    lo = float(labelled_budget_m.group("low"))
                    hi = float(labelled_budget_m.group("high")) if labelled_budget_m.group("high") else lo
                    unit = (labelled_budget_m.group("unit") or "").strip().lower()
                    abs_hi = max(lo, hi)
                    if unit or abs_hi <= 100:
                        out["yearly_budget_min"] = int(min(lo, hi) * multiplier)
                        out["yearly_budget_max"] = int(max(lo, hi) * multiplier)
                        out["budget_quote"] = labelled_budget_m.group(0).strip()
                    elif abs_hi >= 100000:
                        out["yearly_budget_min"] = int(min(lo, hi))
                        out["yearly_budget_max"] = int(max(lo, hi))
                        out["budget_quote"] = labelled_budget_m.group(0).strip()

    # A5 Currency: NULL unless currency symbol/code explicitly appears in requirement block
    if re.search(r"(?i)(?:₹|inr|rs\.?|rupees)", text):
        out["budget_currency"] = "INR"
    elif re.search(r"(?i)(?:\$|usd|dollars?)", text):
        out["budget_currency"] = "USD"
    elif re.search(r"(?i)(?:€|eur|euros?)", text):
        out["budget_currency"] = "EUR"
    elif re.search(r"(?i)(?:£|gbp|pounds?)", text):
        out["budget_currency"] = "GBP"
    elif lpa_implies_inr() and re.search(r"(?i)\b(?:lpa|lakhs?|lpm)\b", text):
        out["budget_currency"] = "INR"
    else:
        out["budget_currency"] = None

    # A5 Priority: accepted only from whole-word match of High, Medium, Low, or glossary terms
    prio_m = re.search(r"\b(HIGH|MEDIUM|LOW|URGENT|CRITICAL|P1|P2|P3)\b", text, re.IGNORECASE)
    if prio_m:
        raw_prio = prio_m.group(1).upper()
        if raw_prio in ("HIGH", "URGENT", "CRITICAL", "P1"):
            out["priority"] = "HIGH"
        elif raw_prio in ("MEDIUM", "P2"):
            out["priority"] = "MEDIUM"
        elif raw_prio in ("LOW", "P3"):
            out["priority"] = "LOW"
        out["priority_quote"] = prio_m.group(0)
    else:
        out["priority"] = None

    loc_m = _LOCATION_LABEL_RE.search(text)
    if loc_m:
        parts = re.split(r",|/|\||;", loc_m.group(1))
        locations = [
            p.strip() for p in parts
            if p.strip() and not re.search(r"\b(?:any\s+(?:\w+\s+)?(?:location|office)|client\s+(?:location|site|office)|pan\s+india)\b", p, re.I)
        ]
        if locations:
            out["location"] = locations
            out["location_quote"] = loc_m.group(0).strip()
    elif _REMOTE_RE.search(text):
        out["location"] = ["Remote"]
        out["location_quote"] = "Remote"
        out["work_mode"] = "Remote"

    exc = _EXCEPT_LOC_RE.search(text)
    if exc:
        out["location"] = [f"All locations (excluding {exc.group(1).strip().title()})"]
        out["location_quote"] = exc.group(0).strip()

    eng = _ENGAGEMENT_RE.search(text)
    if eng:
        out["engagement_type"] = eng.group(1).upper()
        out["engagement_quote"] = eng.group(0).strip()
    contract_dur = _CONTRACT_DURATION_RE.search(text)
    if contract_dur:
        out["contract_duration"] = contract_dur.group(1).strip()
        out["duration_quote"] = contract_dur.group(0).strip()
    elif eng and "contract" in eng.group(1).lower():
        dur = _DURATION_RE.search(text)
        if dur:
            out["contract_duration"] = dur.group(1).strip()
            out["duration_quote"] = dur.group(0).strip()

    return out


def _looks_like_candidate_table(text: str) -> bool:
    low = _norm(text)
    return any(m in low for m in _CANDIDATE_TABLE_MARKERS)


def _requirement_score(text: str) -> int:
    low = _norm(text)
    score = sum(2 for m in _REQUIREMENT_MARKERS if m in low)
    if _looks_like_candidate_table(text):
        score -= 8
    return score


def _split_thread_chunks(body: str) -> list[str]:
    text = body or ""
    starts = [m.start() for m in _THREAD_FROM_RE.finditer(text)]
    if not starts:
        return [text]
    chunks: list[str] = []
    for i, s in enumerate(starts):
        e = starts[i + 1] if i + 1 < len(starts) else len(text)
        chunk = text[s:e].strip()
        if chunk:
            chunks.append(chunk)
    return chunks or [text]


def _strip_candidate_tables(body: str) -> str:
    """
    Remove candidate submission blocks so candidate PII/tables do not pollute requirement extraction.
    """
    lines = (body or "").splitlines()
    out: list[str] = []
    in_candidate_block = False
    table_lines = 0
    for ln in lines:
        low = _norm(ln)
        if any(m in low for m in _CANDIDATE_TABLE_MARKERS):
            in_candidate_block = True
            table_lines = 0
            continue
        if in_candidate_block:
            table_lines += 1
            if (
                low.startswith(("regards", "thanks", "important/confidential", "disclaimer"))
                or any(k in low for k in ("requirement", "job description", "mandatory skill", "open position", "role overview", "overall exp", "qualification criteria", "tpc rate", "bill rate", "work location"))
            ):
                in_candidate_block = False
            else:
                if table_lines > 120:
                    in_candidate_block = False
                continue

        # Drop pure PII footer noise, but keep requirement anchors like POC lines.
        if _EMAIL_RE.search(ln) and not any(k in low for k in ("ta poc", "poc", "spoc")):
            continue
        if _PHONE_RE.search(ln):
            continue
        out.append(ln)
    return "\n".join(out).strip()


def _latest_thread_segment(body: str) -> str:
    chunks = _split_thread_chunks(body)
    best_chunk = chunks[-1]
    best_dt = ""
    best_score = _requirement_score(best_chunk)
    for ch in chunks:
        sent = _THREAD_SENT_RE.search(ch)
        if not sent:
            continue
        dt = _norm(sent.group("dt"))
        sc = _requirement_score(ch)
        if sc > best_score or (sc == best_score and dt > best_dt):
            best_dt = dt
            best_chunk = ch
            best_score = sc
    return best_chunk


def _resolve_experience_conflict(text: str) -> tuple[str | None, str]:
    plus_vals = [int(m.group(1)) for m in _EXP_PLUS_RE.finditer(text or "")]
    ranges = [(int(m.group(1)), int(m.group(2))) for m in _EXP_RANGE_RE.finditer(text or "")]
    if plus_vals and ranges:
        floor = max(plus_vals)
        ceil = max(hi for _, hi in ranges)
        low = max(floor, min(lo for lo, _ in ranges))
        return f"{low}-{ceil} years", "hybrid_regex_ai"
    if ranges:
        lo, hi = ranges[-1]
        return f"{lo}-{hi} years", "regex_anchor"
    if plus_vals:
        v = plus_vals[-1]
        return f"{v}+ years", "regex_anchor"
    return None, "not_found"


def _extract_skill_candidates(text: str) -> list[str]:
    def _canon_skill(token: str) -> str:
        t = token.strip()
        t = re.sub(r"(?i)\bcontroling\b", "controlling", t)
        return re.sub(r"\s+", " ", t).strip()

    def _expand_skill_token(token: str) -> list[str]:
        t = _canon_skill(token.strip(" .:-\t\r\n"))
        if len(t) < 2:
            return []
        out = [t]
        # Keep original form and add slash components for searchable matching.
        if "/" in t and not any(ch.isdigit() for ch in t):
            parts = [p.strip() for p in t.split("/") if p.strip()]
            if len(parts) == 2 and all(len(p) >= 2 for p in parts):
                out.extend(parts)
        return out

    def _extract_section_skills(blob: str) -> list[str]:
        out_sec: list[str] = []
        in_section = False
        for raw in (blob or "").splitlines():
            ln = raw.strip()
            if not ln:
                in_section = False
                continue
            sec_m = _SKILL_SECTION_HEADER_RE.match(ln)
            if sec_m:
                in_section = True
                suffix = (sec_m.group(1) or "").strip()
                if suffix:
                    for tok in re.split(r",|;|\||\band\b", suffix):
                        out_sec.extend(_expand_skill_token(tok))
                continue
            if not in_section:
                continue
            if _SKILL_SECTION_STOP_RE.match(ln):
                in_section = False
                continue
            if len(ln) > 120 or _EMAIL_RE.search(ln) or _PHONE_RE.search(ln):
                continue
            for tok in re.split(r",|;|\||\band\b", ln):
                out_sec.extend(_expand_skill_token(tok))
        return out_sec

    out: list[str] = []
    for m in _SKILL_LINE_RE.finditer(text or ""):
        for token in re.split(r",|\||;|\+|\band\b", m.group(1)):
            out.extend(_expand_skill_token(token))
    out.extend(_extract_section_skills(text or ""))
    # Exhaustive skill mining: capture explicit tools/frameworks/languages/services from entire text.
    for m in _EXPLICIT_SKILL_TOKEN_RE.finditer(text or ""):
        tok = re.sub(r"\s+", " ", m.group(1)).strip(" .:-_|")
        if tok:
            out.extend(_expand_skill_token(tok))
    for ln in (text or "").splitlines():
        l = ln.strip()
        if len(l) < 4 or len(l) > 120:
            continue
    dedup: list[str] = []
    seen: set[str] = set()
    for x in out:
        x = _canon_skill(x)
        k = _norm(x)
        if k and k not in seen:
            seen.add(k)
            dedup.append(x)
    return dedup[:30]


def _extract_subject_skill_hints(subject: str, body: str, job_title: str) -> list[str]:
    source = f"{_strip_subject_prefixes(subject)}\n{(body or '')[:300]}"
    found: list[str] = []
    seen: set[str] = set()

    for m in _SUBJECT_TECH_SKILL_RE.finditer(source):
        token = re.sub(r"\s+", " ", m.group(1)).strip(" .:-_|").title()
        if not token:
            continue
        k = _norm(token)
        if k in seen:
            continue
        seen.add(k)
        found.append(token)

    # Add core title tokens if they are explicit role words in subject/body.
    for tok in re.split(r"[^a-z0-9+.#/&]+", _norm(job_title)):
        if len(tok) < 3 or tok in {"role", "requirement", "drive", "profiles", "open"}:
            continue
        if tok not in _norm(source):
            continue
        title_tok = tok.upper() if tok in {"sap", "abap"} else tok.title()
        if _norm(title_tok) not in seen:
            seen.add(_norm(title_tok))
            found.append(title_tok)
    return found[:12]


def _is_noise_skill_candidate(skill: str) -> bool:
    low = _norm(skill)
    if not low:
        return True
    if low.startswith("&"):
        return True
    if len(low.split()) > 8:
        return True
    noise_terms = (
        "bachelor",
        "degree",
        "qualifications",
        "or related field",
        "years of",
        "hands-on",
        "strong expertise",
        "good understanding",
        "please",
        "share",
        "mobile no",
        "mobile number",
        "email id",
        "email address",
        "applicant location",
        "applicant name",
        "candidate name",
        "preferred location",
        "current org",
        "vendor",
        "sl. no",
        "sl no",
        "total exp",
        "relevant exp",
        "notice period",
        "monthly billing rates",
        "billing rates",
        "l&t technology services",
        "technology services",
        "karnataka",
        "india",
        "mobile:",
        "phone:",
        "regards",
        "rgds",
        "engineering the change",
    )
    if any(t in low for t in noise_terms):
        return True
    if low in {
        "information systems",
        "computer science",
        "and qualifications",
        "qualifications",
        "mobile no",
        "email id",
        "applicant location",
        "vendor",
        "applicant name",
        "current org",
        "notice period",
    }:
        return True
    return False
    # Avoid generic summaries when specific technical skills are expected.
    if low in {"cloud", "devops", "sre", "developer", "engineer", "testing"}:
        return True
    return False


def _extract_requirement_titles_from_thread(subject: str, body: str) -> list[str]:
    """
    Detect requirement pivots (e.g., SAP SD -> SAP ABAP) using subject cues only.
    Avoid scanning body text to prevent mis-extracting skills (e.g., SAP S/4HANA) as job titles.
    """
    titles: list[str] = []
    for m in _SUBJECT_ROLE_RE.finditer(subject or ""):
        t = re.sub(r"\s+", " ", m.group(1)).strip()
        if not t:
            continue
        if t.lower() not in {x.lower() for x in titles}:
            titles.append(t)
    return titles[:6]


def _has_explicit_multi_jd_signal(text: str, extra_text: str = "") -> bool:
    """
    Multi-role extraction should be opt-in only when the message clearly indicates
    multiple distinct requirements/JDs.
    """
    t = f"{text or ''}\n{extra_text or ''}".strip()
    if not t:
        return False
    t = _strip_candidate_tables(t)
    if not t.strip():
        return False
    if _MULTI_JD_SIGNAL_RE.search(t):
        return True
    # Distinct role titles in thread subjects indicate separate JDs.
    subj_titles = {_norm(m.group(1)) for m in _SUBJECT_ROLE_RE.finditer(t) if _norm(m.group(1))}
    if len(subj_titles) >= 2:
        return True
    # Explicit tabular multi-role rows (role + budget/location cues).
    table_rows = _extract_multi_role_rows(t)
    table_titles = {_norm(str(r.get("job_title") or "")) for r in table_rows if _norm(str(r.get("job_title") or ""))}
    return len(table_titles) >= 2


def _pick_primary_requirement(items: list[RequirementItem]) -> list[RequirementItem]:
    if len(items) <= 1:
        return items
    # Prefer highest confidence with strongest evidence footprint.
    ranked = sorted(
        items,
        key=lambda x: (
            float(getattr(x, "confidence", 0.0)),
            len(getattr(x, "mandatory_skills", []) or []) + len(getattr(x, "soft_skills", []) or []),
            len(getattr(x, "job_title", "") or ""),
        ),
        reverse=True,
    )
    return [ranked[0]]


_ROLE_NOISE_TOKENS = {
    "consultant",
    "technical",
    "implementation",
    "developer",
    "engineer",
    "specialist",
    "lead",
    "senior",
    "junior",
    "principal",
}


def _role_title_tokens(title: str) -> set[str]:
    parts = re.split(r"[^a-z0-9+.#]+", _norm(title))
    return {p for p in parts if len(p) >= 2 and p not in _ROLE_NOISE_TOKENS}


def _same_role_title(a: str, b: str) -> bool:
    ta = _role_title_tokens(a)
    tb = _role_title_tokens(b)
    if not ta or not tb:
        return _norm(a) == _norm(b)
    inter = ta & tb
    if not inter:
        return False
    # Treat subset roles as same family (e.g., "SAP ABAP" vs "SAP ABAP Consultant").
    if ta <= tb or tb <= ta:
        return True
    jacc = len(inter) / max(len(ta | tb), 1)
    return jacc >= 0.5


def _consolidate_multi_role_requirements(items: list[RequirementItem]) -> list[RequirementItem]:
    if len(items) <= 1:
        return items
    ranked = sorted(
        items,
        key=lambda x: (
            float(getattr(x, "confidence", 0.0)),
            len(_role_title_tokens(getattr(x, "job_title", "") or "")),
            len(getattr(x, "job_title", "") or ""),
            len(getattr(x, "mandatory_skills", []) or []),
        ),
        reverse=True,
    )
    out: list[RequirementItem] = []
    for req in ranked:
        title = getattr(req, "job_title", "") or ""
        if any(_same_role_title(title, (getattr(x, "job_title", "") or "")) for x in out):
            continue
        out.append(req)
    return out


def _extract_role_title_field(text: str) -> str:
    m = re.search(r"(?im)^\s*role title\s*:\s*(.+?)\s*$", text or "")
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def _is_reporting_manager_role(title: str, body: str) -> bool:
    t = (title or "").strip()
    if not t:
        return False
    if re.search(r"(?i)\breporting\s+to\b", t):
        return True
    return bool(
        re.search(
            rf"(?im)^\s*reporting\s+to\s*:\s*{re.escape(t)}\s*$",
            body or "",
        )
    )


def _apply_structured_jd_single_role(
    items: list[RequirementItem],
    *,
    subject: str,
    body: str,
) -> list[RequirementItem]:
    """
    Structured FTE/project JDs with a single ``Role title:`` line are one requirement.
    Drop mis-parsed reporting-manager lines (``Reporting to: …``).
    """
    if not items:
        return items
    role_title = _extract_role_title_field(body)
    role_title_count = len(re.findall(r"(?im)^\s*role title\s*:", body or ""))
    filtered = [req for req in items if not _is_reporting_manager_role(req.job_title, body)]
    if not filtered:
        filtered = items[:1]

    if role_title and role_title_count == 1:
        primary = filtered[0]
        primary.job_title = _clean_job_title(role_title)
        return [primary]

    if len(filtered) < len(items):
        return filtered if filtered else items[:1]
    return items


def _extract_multi_role_rows(text: str) -> list[dict[str, Any]]:
    """
    Parse repeated table-like role blocks into distinct role entries.
    This is intentionally client-agnostic and relies on role/budget/location cues.
    """
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    rows: list[dict[str, Any]] = []
    for idx, line in enumerate(lines):
        if re.search(r"(?i)\breporting\s+to\b", line):
            continue
        role_m = _ROLE_HINT_RE.search(line)
        if not role_m:
            continue
        role = role_m.group(1).strip()
        window = "\n".join(lines[idx : min(idx + 8, len(lines))])
        budget_m = _BUDGET_RANGE_RE.search(window)
        loc_m = _LOCATION_INLINE_RE.search(window)
        hike_m = _HIKE_RE.search(window)
        if not budget_m and not loc_m:
            # Likely a plain mention, not a tabular requirement row.
            continue

        item: dict[str, Any] = {
            "job_title": role,
            "mandatory_skills": [role.split()[0]],
            "skills": [role.split()[0]],
            "experience": "",
            "notice_period": "",
            "field_confidence": {},
            "field_sources": {},
            "field_evidence_quotes": {},
            "field_extraction_method": {},
        }
        item["field_confidence"]["job_title"] = 1.0
        item["field_sources"]["job_title"] = "email_body"
        item["field_evidence_quotes"]["job_title"] = role
        item["field_extraction_method"]["job_title"] = "ai_semantic"

        if loc_m:
            loc_blob = loc_m.group(1)
            locs = [p.strip().title() for p in re.split(r"/", loc_blob) if p.strip()]
            item["location"] = locs
            item["field_confidence"]["location"] = 1.0
            item["field_sources"]["location"] = "email_body"
            item["field_evidence_quotes"]["location"] = loc_blob
            item["field_extraction_method"]["location"] = "regex_anchor"
        else:
            item["location"] = []
            item["field_confidence"]["location"] = 0.0
            item["field_sources"]["location"] = "not_found"
            item["field_evidence_quotes"]["location"] = ""
            item["field_extraction_method"]["location"] = "not_found"

        if budget_m:
            lo = float(budget_m.group(1))
            hi = float(budget_m.group(2))
            item["yearly_budget_min"] = int(min(lo, hi) * 100000)
            item["yearly_budget_max"] = int(max(lo, hi) * 100000)
            budget_quote = budget_m.group(0).strip()
            if hike_m:
                budget_quote = f"{budget_quote}; {hike_m.group(0).strip()}"
            item["field_confidence"]["budget"] = 0.98
            item["field_sources"]["budget"] = "email_body"
            item["field_evidence_quotes"]["budget"] = budget_quote
            item["field_extraction_method"]["budget"] = "hybrid_regex_ai"
        else:
            item["yearly_budget_min"] = None
            item["yearly_budget_max"] = None
            item["field_confidence"]["budget"] = 0.0
            item["field_sources"]["budget"] = "not_found"
            item["field_evidence_quotes"]["budget"] = ""
            item["field_extraction_method"]["budget"] = "not_found"

        # Explicit zero-guess for missing experience in table rows.
        item["field_confidence"]["experience"] = 0.0
        item["field_sources"]["experience"] = "not_found"
        item["field_evidence_quotes"]["experience"] = ""
        item["field_extraction_method"]["experience"] = "not_found"
        item["field_confidence"]["skills"] = 0.95
        item["field_sources"]["skills"] = "email_body"
        item["field_evidence_quotes"]["skills"] = role
        item["field_extraction_method"]["skills"] = "ai_semantic"
        item["confidence"] = round(
            (
                item["field_confidence"]["job_title"]
                + item["field_confidence"]["skills"]
                + item["field_confidence"]["location"]
                + item["field_confidence"]["budget"]
                + item["field_confidence"]["experience"]
            )
            / 5.0,
            4,
        )
        rows.append(item)

    # Deduplicate by role + budget + location.
    uniq: list[dict[str, Any]] = []
    seen: set[str] = set()
    for r in rows:
        key = "|".join(
            [
                _norm(str(r.get("job_title") or "")),
                _norm(str(r.get("yearly_budget_min") or "")),
                _norm(str(r.get("yearly_budget_max") or "")),
                _norm(",".join(r.get("location") or [])),
            ]
        )
        if key in seen:
            continue
        seen.add(key)
        uniq.append(r)
    return uniq


def _title_has_evidence(title: str, subject: str, body: str) -> bool:
    if not title:
        return False
    ctx = _norm(f"{subject} {body}")
    words = [w for w in re.split(r"[^a-z0-9]+", _norm(title)) if len(w) >= 3]
    if not words:
        return False
    matched = sum(1 for w in words if w in ctx)
    return matched >= max(1, min(2, len(words)))


def _skill_has_evidence(skill: str, subject: str, body: str) -> bool:
    s = _norm(skill)
    if not s:
        return False
    ctx = _norm(f"{subject} {body}")
    tokens = [t for t in re.split(r"[^a-z0-9+.#]+", s) if len(t) >= 3]
    if not tokens:
        return False
    return any(tok in ctx for tok in tokens)


def _best_skill_evidence(skills: list[str], body: str) -> str:
    if not skills:
        return ""
    lines = [ln.strip() for ln in (body or "").splitlines() if ln.strip()]
    for ln in lines:
        low = _norm(ln)
        if any(_norm(s) and _norm(s) in low for s in skills):
            return ln[:240]
    return "; ".join(skills[:4])


def _recover_from_schema_validation(subject: str, body: str) -> RequirementParseResult | None:
    """
    Build one conservative fallback requirement when model output fails schema validation.
    This is used to avoid dropping clearly extractable requirement emails due to empty job_title.
    """
    text_for_fields = _strip_candidate_tables(_latest_thread_segment(body) or body or "")
    rule_fields = _extract_rule_fields(subject or "", text_for_fields or "")
    job_title = _clean_job_title(
        str(rule_fields.get("job_title") or "").strip() or _extract_subject_role_fallback(subject or "")
    )
    if not job_title:
        return None

    skill_candidates = _extract_skill_candidates(text_for_fields or "")
    filtered_skills: list[str] = []
    for sk in skill_candidates:
        if _is_noise_skill_candidate(sk):
            continue
        if _skill_has_evidence(sk, subject or "", text_for_fields or ""):
            filtered_skills.append(sk)
    mandatory = filtered_skills[:8]
    soft = filtered_skills[8:20]

    has_location = bool(rule_fields.get("location"))
    pos_val = int(rule_fields.get("number_of_positions")) if rule_fields.get("number_of_positions") else None
    row: dict[str, Any] = {
        "job_title": job_title,
        "number_of_positions": pos_val,
        "experience": str(rule_fields.get("experience") or ""),
        "notice_period": str(rule_fields.get("notice_period") or ""),
        "location": list(rule_fields.get("location") or []),
        "mandatory_skills": mandatory,
        "skills": soft,
        "yearly_budget_min": rule_fields.get("yearly_budget_min"),
        "yearly_budget_max": rule_fields.get("yearly_budget_max"),
        "monthly_budget_min": rule_fields.get("monthly_budget_min"),
        "monthly_budget_max": rule_fields.get("monthly_budget_max"),
        "confidence": 0.62,
        "field_confidence": {
            "job_title": 1.0 if is_strict_field_mapping() else 0.92,
            "skills": (1.0 if (mandatory or soft) else 0.0) if is_strict_field_mapping() else (0.7 if (mandatory or soft) else 0.0),
            "location": (1.0 if has_location else 0.0) if is_strict_field_mapping() else (0.85 if has_location else 0.0),
            "budget": (
                1.0
                if (
                    rule_fields.get("yearly_budget_min") is not None
                    or rule_fields.get("monthly_budget_min") is not None
                )
                else 0.0
            ),
            "experience": (1.0 if rule_fields.get("experience") else 0.0) if is_strict_field_mapping() else (0.9 if rule_fields.get("experience") else 0.0),
        },
        "field_sources": {
            "job_title": "email_subject",
            "skills": "email_body" if (mandatory or soft) else "not_found",
            "location": "email_body" if rule_fields.get("location") else "not_found",
            "budget": "email_body"
            if (
                rule_fields.get("yearly_budget_min") is not None
                or rule_fields.get("monthly_budget_min") is not None
            )
            else "not_found",
            "experience": "email_body" if rule_fields.get("experience") else "not_found",
        },
        "field_evidence_quotes": {
            "job_title": str(rule_fields.get("job_title_quote") or _strip_subject_prefixes(subject or "")),
            "skills": _best_skill_evidence(mandatory + soft, text_for_fields or ""),
            "location": str(rule_fields.get("location_quote") or ""),
            "budget": str(rule_fields.get("budget_quote") or ""),
            "experience": str(rule_fields.get("experience_quote") or ""),
        },
        "field_extraction_method": {
            "job_title": "regex_anchor",
            "skills": "hybrid_regex_ai" if (mandatory or soft) else "not_found",
            "location": "regex_anchor" if rule_fields.get("location") else "not_found",
            "budget": "regex_anchor"
            if (
                rule_fields.get("yearly_budget_min") is not None
                or rule_fields.get("monthly_budget_min") is not None
            )
            else "not_found",
            "experience": "regex_anchor" if rule_fields.get("experience") else "not_found",
        },
    }
    if is_strict_field_mapping():
        row["confidence"] = compute_requirement_confidence(row, block_text=text_for_fields)
    try:
        item = RequirementItem.model_validate(row)
    except Exception:
        return None
    return RequirementParseResult(
        requirements=[item],
        overall_confidence=float(item.confidence),
        processing_note="schema_validation_error_recovered_with_rules",
    )


def extract_client_jd_id_from_text(subject: str = "", body: str = "", client: str | None = None) -> str | None:
    """
    Extract genuine client-provided requirement ID from email subject or body.
    Supports multiple client ID formats (e.g. Accenture '203421-1', Deloitte 'DLTJP00059663',
    Fidelity 'RQ056293', LTTS 'REQ-XXXX', etc.).
    Returns None if no client-provided ID exists in source text (never fabricates placeholder IDs).
    Validated with is_genuine_client_id (C1, C2).
    """
    from client_identity_validator import is_genuine_client_id

    text = f"{subject or ''}\n{body or ''}"
    if not text.strip():
        return None

    if not client:
        from client_detector import detect_client
        cm = detect_client(subject, body, "")
        if cm and cm.key and cm.key != "unresolved":
            client = cm.key

    # Pattern 1: Explicit key-value pairs (Request-ID: 203421-1, Job Posting ID - DLTJP00062540, Req ID: REQ-1234, etc.)
    p1 = re.search(
        r"(?i)\b(?:Request[\-\s]?ID|Req[\-\s]?ID|Demand[\-\s]?ID|Job[\-\s]?Posting[\-\s]?ID|Job[\-\s]?ID|Ref[\-\s]?ID|Requirement[\-\s]?ID|Requisition[\-\s]?ID)\s*[:=\-#]?\s*([A-Za-z0-9_\-]+)",
        text,
    )
    if p1:
        val = p1.group(1).strip()
        is_val, clean_val, _ = is_genuine_client_id(client, val, context=text)
        if is_val and clean_val:
            return clean_val

    # Pattern 2: DLTJP format (e.g. DLTJP00059663)
    p2 = re.search(r"\b(DLTJP\d{5,10})\b", text, re.IGNORECASE)
    if p2:
        val = p2.group(1).upper()
        is_val, clean_val, _ = is_genuine_client_id(client, val, context=text)
        if is_val and clean_val:
            return clean_val

    # Pattern 3: Generic RQ format (e.g. RQ056293)
    p3 = re.search(r"\b(RQ\d{5,8})\b", text, re.IGNORECASE)
    if p3:
        val = p3.group(1).upper()
        is_val, clean_val, _ = is_genuine_client_id(client, val, context=text)
        if is_val and clean_val:
            return clean_val

    # Pattern 4: Numeric-dash format (e.g. 203421-1, 195414-1)
    p4 = re.search(r"\b(\d{5,7}\-\d{1,2})\b", text)
    if p4:
        val = p4.group(1)
        is_val, clean_val, _ = is_genuine_client_id(client, val, context=text)
        if is_val and clean_val:
            return clean_val

    # Pattern 5: Standard REQ format (e.g. REQ-98241 or REQ_12345)
    p5 = re.search(r"\b(REQ[\-_][A-Za-z0-9]{4,12})\b", text, re.IGNORECASE)
    if p5:
        val = p5.group(1).upper()
        is_val, clean_val, _ = is_genuine_client_id(client, val, context=text)
        if is_val and clean_val:
            return clean_val

    return None


def associate_downstream_skills_for_req(body: str, req_id: str, client_name: str | None = None) -> tuple[list[str], list[str]]:
    """
    For multi-demand/table emails, associate each Req ID with its own downstream
    Job Description / Professional & Technical Skills section (Primary Fix).
    Flow: Req ID -> matching role/JD block -> explicit skill section -> extraction -> validation.
    """
    if not body or not req_id:
        return [], []

    # 1. Locate downstream section starting at Req ID
    pat = rf"(?:Req\s*ID\s*[:\-–]?\s*{re.escape(req_id)}|{re.escape(req_id)}\s*[\r\n]+\s*(?:Job\s+Description|\d{{1,2}}\s+[A-Z0-9]+))"
    matches = list(re.finditer(pat, body, re.IGNORECASE))
    if not matches:
        occs = [m.start() for m in re.finditer(re.escape(req_id), body)]
        if len(occs) > 1:
            start_pos = occs[-1]
            end_match = start_pos + len(req_id)
        else:
            return [], []
    else:
        m = matches[-1]
        start_pos = m.start()
        end_match = m.end()

    sub = body[end_match:]
    m_next = re.search(
        r"(?:Req\s*ID\s*[:\-–]?\s*\d{5,7}-\d{1,2}|\b\d{5,7}-\d{1,2}\b\s*[\r\n]+\s*(?:Job\s+Description|\d{1,2}\s+[A-Z0-9]+)|(?:From|Sent|To|Subject)\s*:|Thanks\s*&|Best\s*Regards)",
        sub,
        re.IGNORECASE,
    )
    if m_next:
        block = body[start_pos : end_match + m_next.start()]
    else:
        block = body[start_pos:]

    clean_block = block
    m_stop = re.search(r"(?i)(?:Additional\s*Information|Comments\s*for\s*Suppliers|Thanks\s*&|Best\s*Regards)", clean_block)
    if m_stop:
        clean_block = clean_block[:m_stop.start()]

    mand_list: list[str] = []
    sec_list: list[str] = []

    # Check 1: Multi-bullet Must Have Skills / Good To Have Skills (e.g. R02)
    m_must_sec = re.search(
        r"(?is)(?:^|\n)\s*(?:Must\s*Have\s*Skills?|Mandatory\s*Skills?)\s*[:\-]??\s*\n\s*(.+?)(?=(?:(?:^|\n)\s*(?:Good\s*To\s*Have|Preferred|Technical|Roles|Additional))|\Z)",
        clean_block,
    )
    m_good_sec = re.search(
        r"(?is)(?:^|\n)\s*(?:Good\s*To\s*Have\s*(?:Skills?)?|Preferred\s*Skills?)\s*[:\-]??\s*\n\s*(.+?)(?=(?:(?:^|\n)\s*(?:Must|Technical|Roles|Additional))|\Z)",
        clean_block,
    )

    if m_must_sec:
        b_text = m_must_sec.group(1).strip()
        bullets = [b.strip() for b in re.split(r"(?:^|\n)\s*[-*•·\d+\.]+\s*", b_text) if b.strip()]
        for b in bullets:
            b_clean = re.sub(r"^[-\s*•·\d+\.]+", "", b).strip().rstrip(".;,!?:\t -–—")
            if b_clean and len(b_clean) > 2:
                mand_list.append(b_clean)

    if m_good_sec:
        b_text = m_good_sec.group(1).strip()
        bullets = [b.strip() for b in re.split(r"(?:^|\n)\s*[-*•·\d+\.]+\s*", b_text) if b.strip()]
        for b in bullets:
            b_clean = re.sub(r"^[-\s*•·\d+\.]+", "", b).strip().rstrip(".;,!?:\t -–—")
            if b_clean and len(b_clean) > 2:
                sec_list.append(b_clean)

    # Check 2: Professional & Technical Skills section (e.g. R01, R03, R04, R06, R07, R08, R09, R10, R23, R24)
    m_pts = re.search(
        r"(?is)(?:Professional\s*&\s*Technical\s*Skills|Technical\s*Skills)\s*[:\-–]?\s*(.+?)(?=(?:Roles\s*&\s*Responsibilities|Key\s*Responsibilities|Additional|Comments|\Z))",
        clean_block,
    )
    if m_pts:
        pts_text = m_pts.group(1).strip()
        pts_norm = re.sub(r"\.\s*-\s*", ".\n- ", pts_text)
        pts_norm = re.sub(r"\)\s*-\s*", ")\n- ", pts_norm)
        pts_norm = re.sub(r";\s*-\s*", ";\n- ", pts_norm)
        pts_norm = re.sub(r"(?<=[a-zA-Z0-9\.\)])\s+-\s+(?=[A-Z])", "\n- ", pts_norm)
        bullets = [b.strip() for b in re.split(r"(?:^|\n)\s*[-*•·\d+\.]+\s*", pts_norm) if b.strip()]
        for b in bullets:
            b_clean = re.sub(r"^[-\s*•·\d+\.]+", "", b).strip().rstrip(".;,!?:\t -–—")
            if not b_clean or len(b_clean) < 2:
                continue
            m_mth = re.match(r"(?i)^Must\s*(?:To\s*)?Have\s*Skills?\s*[:\-–]?\s*(.+)$", b_clean)
            if m_mth:
                val = m_mth.group(1).strip().rstrip(".;,!?:\t -–—")
                if val and val not in mand_list:
                    mand_list.append(val)
            else:
                if b_clean not in mand_list and b_clean not in sec_list:
                    sec_list.append(b_clean)

    # Check 3: Technical Experience / Key Responsibilities fallback (e.g. R05, R11)
    if not mand_list and not sec_list:
        m_resp = re.search(
            r"(?is)(?:Technical\s*Experience|Key\s*Responsibilities|Roles\s*&\s*Responsibilities)\s*[:\-–]?\s*(.+?)(?=(?:Additional|Comments|\Z))",
            clean_block,
        )
        if m_resp:
            resp_text = m_resp.group(1).strip()
            if re.search(r"[-*•·]", resp_text):
                resp_norm = re.sub(r"\.\s*-\s*", ".\n- ", resp_text)
                resp_norm = re.sub(r"\)\s*-\s*", ")\n- ", resp_norm)
                resp_norm = re.sub(r"(?<=[a-zA-Z0-9\.\)])\s*-\s+(?=[A-Z])", "\n- ", resp_norm)
                resp_norm = re.sub(r"(?<=[a-zA-Z0-9\.\)])-(?=[A-Z])", "\n- ", resp_norm)
                bullets = [b.strip() for b in re.split(r"(?:^|\n)\s*[-*•·\d+\.]+\s*", resp_norm) if b.strip()]

                for b in bullets:
                    b_clean = re.sub(r"^[-\s*•·\d+\.]+", "", b).strip().rstrip(".;,!?:\t -–—")
                    if not b_clean or len(b_clean) < 3:
                        continue
                    low = b_clean.lower()
                    if any(
                        noise in low
                        for noise in (
                            "expected to be an sme",
                            "collaborate and manage",
                            "responsible for team decisions",
                            "engage with multiple teams",
                            "contribute on key decisions",
                            "expected to perform independently and become an sme",
                            "required active participation",
                            "contribute in providing solutions to work related problems",
                        )
                    ):
                        continue
                    sec_list.append(b_clean)
            elif re.search(r"\b[a-g]\s+(?=[A-Z]|should\b|experience\b)", resp_text):
                sub_parts = re.split(r"(Key\s*Responsibilities|Technical\s*Experience|Professional\s*Attributes)", resp_text)
                sections = {}
                if len(sub_parts) >= 3:
                    for i in range(1, len(sub_parts), 2):
                        sections[sub_parts[i].strip()] = sub_parts[i + 1].strip()
                else:
                    sections["general"] = resp_text

                for s_name, s_body in sections.items():
                    markers = ["a", "b", "c", "d", "e", "f", "g"]
                    pos = 0
                    m_indices = []
                    for m_ch in markers:
                        m_match = re.search(rf"(?:^|\s|(?<=[a-zA-Z0-9]))({m_ch})\s+(?=[A-Z]|should\b|experience\b)", s_body[pos:])
                        if m_match:
                            actual_pos = pos + m_match.start(1)
                            end_pos = pos + m_match.end()
                            m_indices.append((m_ch, actual_pos, end_pos))
                            pos = end_pos
                        else:
                            break
                    for idx_m, (m_char, start_i, end_i) in enumerate(m_indices):
                        next_start = m_indices[idx_m + 1][1] if idx_m + 1 < len(m_indices) else len(s_body)
                        val = s_body[end_i:next_start].strip().rstrip(".;,!?:\t -–—")
                        if val and len(val) > 2 and val not in sec_list:
                            sec_list.append(val)

    from boilerplate_learner import validate_skills

    val_mand = validate_skills(mand_list, client=client_name or "") if mand_list else []
    val_sec = validate_skills(sec_list, client=client_name or "") if sec_list else []
    return (val_mand or []), (val_sec or [])


def extract_req_id_table_requirements(
    body: str, subject: str = "", from_email: str = ""
) -> list[RequirementItem]:
    """
    Extract requirements directly from email tables when unique Req IDs are present (Rule 1).
    Ensures LLM never generates or alters a Req ID.
    Supports standard matrix tables, key-value HTML tables, and summary row formats.
    """
    from bs4 import BeautifulSoup
    from config import get_client_identity_config

    cfg = get_client_identity_config(from_email)
    if not cfg:
        from client_detector import detect_client
        cm = detect_client(subject, body, from_email)
        if cm and cm.key and cm.key != "unresolved":
            cfg = get_client_identity_config(cm.key)
    if not cfg:
        return []

    items: list[RequirementItem] = []
    seen_ids: set[str] = set()
    soup = BeautifulSoup(body or "", "html.parser")
    tables = soup.find_all("table")

    if tables:
        current_item: RequirementItem | None = None

        for tbl in tables:
            trs = tbl.find_all("tr")
            if not trs:
                continue

            headers = [td.get_text(strip=True) for td in trs[0].find_all(["th", "td"])]
            req_id_idx = None
            status_idx = None
            title_idx = None
            loc_idx = None
            exp_idx = None
            budget_idx = None
            work_mode_idx = None

            from requirement_segmenter import match_table_header

            for idx, h in enumerate(headers):
                hl = h.lower()
                canon = match_table_header(hl)
                if canon == "req_id" or any(req_h.lower() in hl for req_h in cfg.table_req_id_headers):
                    req_id_idx = idx
                elif canon == "status" or any(stat_h.lower() in hl for stat_h in cfg.table_status_headers):
                    status_idx = idx
                elif canon == "job_title" or any(k in hl for k in ("skill", "role", "title")):
                    title_idx = idx
                elif canon == "location":
                    loc_idx = idx
                elif canon == "experience":
                    exp_idx = idx
                elif canon == "budget":
                    budget_idx = idx
                elif canon == "work_mode" or any(k in hl for k in ("rto", "hybrid", "wfh", "work mode", "work model")):
                    work_mode_idx = idx

            # Standard matrix table with column headers
            if req_id_idx is not None:
                for tr in trs[1:]:
                    cells = [td.get_text(strip=True) for td in tr.find_all(["th", "td"])]
                    if len(cells) == len(headers) and cells[req_id_idx]:
                        cand_id = cells[req_id_idx].strip()
                        from client_identity_validator import is_genuine_client_id

                        is_val, clean_id, _ = is_genuine_client_id(
                            cfg.display_name if cfg else None,
                            cand_id,
                            context=body,
                        )
                        if (
                            is_val
                            and clean_id
                            and clean_id not in seen_ids
                            and not any(req_h.lower() == clean_id.lower() for req_h in cfg.table_req_id_headers)
                        ):
                            raw_stat = cells[status_idx] if status_idx is not None else cells[-1]
                            norm_stat = cfg.status_mapping.get(raw_stat.lower(), "open")
                            title_val = cells[title_idx] if title_idx is not None else ""
                            loc_val = cells[loc_idx] if loc_idx is not None else ""
                            exp_val = cells[exp_idx] if exp_idx is not None else ""
                            budget_val = cells[budget_idx] if budget_idx is not None else ""
                            wm_val = cells[work_mode_idx] if work_mode_idx is not None else ""

                            seen_ids.add(clean_id)
                            tbl_jt = title_val or (None if is_strict_field_mapping() else f"{cfg.display_name} Requirement")
                            tbl_prio = None if is_strict_field_mapping() else ("HIGH" if norm_stat == "open" else "LOW")
                            mand_sk, soft_sk = associate_downstream_skills_for_req(body, clean_id, cfg.display_name if cfg else None)
                            from two_way_verifier import parse_experience_digits, parse_work_mode
                            t_exp_min, t_exp_max = parse_experience_digits(exp_val) if exp_val else (None, None)
                            m_wm_down = re.search(r"(?im)^\s*(?:[-*•]\s*)?(?:work\s*mode|work\s*model|mode\s*of\s*work)\s*[:\-–—|]\s*([^\r\n]+)", body)
                            if not wm_val and m_wm_down:
                                wm_val = m_wm_down.group(1).strip()
                            t_norm_wm, t_raw_wm = parse_work_mode(wm_val) if wm_val else (None, None)
                            tbl_item = RequirementItem(
                                req_id=clean_id,
                                raw_status=raw_stat,
                                job_title=tbl_jt,
                                location=[loc_val] if loc_val else [],
                                experience=exp_val,
                                experience_text=exp_val,
                                experience_min_years=t_exp_min,
                                experience_max_years=t_exp_max,
                                overall_experience=exp_val,
                                budget=budget_val,
                                priority=tbl_prio,
                                work_mode=t_norm_wm,
                                work_mode_text=t_raw_wm or (wm_val or None),
                                client_name=cfg.display_name,
                                mandatory_skills=mand_sk if mand_sk else ([] if is_strict_field_mapping() else ([title_val] if title_val else [])),
                                soft_skills=soft_sk if soft_sk else [],
                                confidence=1.0,
                            )
                            if is_strict_field_mapping():
                                tbl_item.confidence = compute_requirement_confidence(tbl_item, block_text=body)
                            items.append(tbl_item)

            # Key-Value 2-column format within each table (C3: never use first cell as fallback)
            table_req_id = None
            for tr in trs:
                cells = [td.get_text(" ", strip=True) for td in tr.find_all(["th", "td"])]
                if len(cells) >= 2:
                    key = cells[0].strip().rstrip(":").lower()
                    val = cells[1].strip()

                    is_id_header = any(req_h.lower() == key for req_h in cfg.table_req_id_headers) or key in (
                        "request-id",
                        "request id",
                        "req id",
                        "req-id",
                        "reqid",
                        "so id",
                        "demand id",
                        "so#",
                    )
                    if is_id_header and val:
                        from client_identity_validator import is_genuine_client_id

                        is_val, clean_id, _ = is_genuine_client_id(
                            cfg.display_name if cfg else None,
                            val,
                            context=body,
                        )
                        if is_val and clean_id:
                            if clean_id not in seen_ids:
                                seen_ids.add(clean_id)
                                is_hold_body = "don't work" in body.lower() or "dont work" in body.lower()
                                raw_stat = "hold" if is_hold_body else "open"
                                kv_jt = None if is_strict_field_mapping() else f"{cfg.display_name} Requirement"
                                kv_prio = None if is_strict_field_mapping() else ("HIGH" if raw_stat == "open" else "LOW")
                                current_item = RequirementItem(
                                    req_id=clean_id,
                                    raw_status=raw_stat,
                                    job_title=kv_jt,
                                    priority=kv_prio,
                                    client_name=cfg.display_name,
                                    confidence=1.0,
                                )
                                if is_strict_field_mapping():
                                    current_item.confidence = compute_requirement_confidence(current_item, block_text=body)
                                items.append(current_item)
                                table_req_id = clean_id
                            elif current_item and current_item.req_id == clean_id:
                                table_req_id = clean_id
                            break

            # If this table didn't define a new Request-ID, attach Job Description/Comments ONLY to current_item if it matches
            if not table_req_id and current_item:
                for tr in trs:
                    cells = [td.get_text(" ", strip=True) for td in tr.find_all(["th", "td"])]
                    if len(cells) >= 2:
                        key = cells[0].strip().rstrip(":").lower()
                        val = cells[1].strip()

                        if key in ("job description", "jd", "job summary"):
                            if "Summary:" in val:
                                summary_part = val.split("Summary:", 1)[1]
                                m_title = re.search(
                                    r"As a ([^,]+?),(?:\s*a typical day|\s*you will|\s*the)",
                                    summary_part,
                                    re.IGNORECASE,
                                )
                                if m_title:
                                    extracted_title = m_title.group(1).strip()
                                    current_item.job_title = extracted_title
                                    if not is_strict_field_mapping() and not current_item.mandatory_skills:
                                        current_item.mandatory_skills = [extracted_title]

                            m_skill = re.search(r"Must To Have Skills:\s*([^.\n]+)", val, re.IGNORECASE)
                            if m_skill:
                                skill = m_skill.group(1).strip()
                                current_item.mandatory_skills = [skill]
                                if not current_item.job_title or current_item.job_title == f"{cfg.display_name} Requirement":
                                    current_item.job_title = skill

                        elif key in ("comments for suppliers", "comments", "supplier comments"):
                            if not current_item.job_title or current_item.job_title == f"{cfg.display_name} Requirement":
                                m_comp = re.search(
                                    r"^([A-Za-z0-9\s/&\-\(\)]+?)(?:Relevant|Work|Location|\d+\+|\d+ Yrs|$)",
                                    val,
                                    re.IGNORECASE,
                                )
                                if m_comp and len(m_comp.group(1).strip()) > 3:
                                    current_item.job_title = m_comp.group(1).strip()
                        if is_strict_field_mapping():
                            current_item.confidence = compute_requirement_confidence(current_item, block_text=body)

    # Text-line / multiline fallback if HTML table parser found no items
    if not items and body:
        lines = [l.strip() for l in (body or "").splitlines() if l.strip()]
        seen = set()
        for idx, line in enumerate(lines):
            m = re.match(r"^(\d{5,7}-\d{1,2}|20\d{5}-\d|19\d{5}-\d|17\d{5}-\d|RQ\d{5,8})$", line, re.IGNORECASE)
            if not m:
                m = re.search(r"\b(\d{5,7}-\d{1,2}|20\d{5}-\d|19\d{5}-\d|17\d{5}-\d|RQ\d{5,8})\b", line, re.IGNORECASE)
            if m:
                cand_id = m.group(1).strip()
                from client_identity_validator import is_genuine_client_id

                is_val, clean_id, _ = is_genuine_client_id(
                    cfg.display_name if cfg else None,
                    cand_id,
                    context=body,
                )
                if not is_val or not clean_id or clean_id in seen:
                    continue
                req_id = clean_id

                window = lines[idx + 1 : idx + 10]
                title_val = ""
                loc_val = ""
                exp_val = ""
                budget_val = ""
                is_body_hold = "don't work" in body.lower() or "dont work" in body.lower() or "on hold" in body.lower()
                raw_stat = "hold" if is_body_hold else "open"

                for w in window:
                    wl = w.lower()
                    if re.match(r"^(\d{5,7}-\d{1,2})$", w):
                        break
                    if (
                        not title_val
                        and len(w) >= 3
                        and not w.isdigit()
                        and "grade" not in wl
                        and "rto" not in wl
                        and "graduation" not in wl
                        and "lakhs" not in wl
                        and "yrs" not in wl
                        and "hold" not in wl
                        and "open" not in wl
                        and "p1" not in wl
                        and "p2" not in wl
                    ):
                        title_val = w
                    elif (
                        not loc_val
                        and not re.search(r"\b(?:any\s+(?:\w+\s+)?(?:location|office)|client\s+(?:location|site|office)|pan\s+india)\b", wl)
                        and (
                            normalize_city(w) is not None
                            or any(dc in wl for dc in ("bdc", "pdc", "mdc", "hdc", "ddc", "cdc", "kdc"))
                        )
                    ):
                        loc_val = w
                    elif ("yrs" in wl or "year" in wl or "exp" in wl) and not exp_val:
                        exp_val = w
                    elif ("lakh" in wl or "budget" in wl) and not budget_val:
                        budget_val = w
                    elif wl in ("hold", "open", "reopen", "p1", "p2", "closed"):
                        raw_stat = "hold" if "hold" in wl else ("open" if wl in ("open", "p1", "p2") else wl)

                parts = [p.strip() for p in re.split(r"\s*\|\s*|\t+|\s{2,}", line) if p.strip()]
                if len(parts) >= 3:
                    raw_stat = parts[-1]
                    if len(parts) > 2 and parts[1].lower().startswith("grade"):
                        title_val = parts[2]
                        loc_val = parts[3] if len(parts) > 3 else loc_val
                        budget_val = parts[5] if len(parts) > 5 else budget_val
                        exp_val = parts[6] if len(parts) > 6 else exp_val
                    else:
                        title_val = parts[1] if len(parts) > 1 else title_val
                        loc_val = parts[2] if len(parts) > 2 else loc_val
                        exp_val = parts[3] if len(parts) > 3 else exp_val

                if loc_val and re.search(r"\b(?:any\s+(?:\w+\s+)?(?:location|office)|client\s+(?:location|site|office)|pan\s+india)\b", loc_val, re.I):
                    loc_val = ""

                seen.add(req_id)
                norm_stat = (
                    cfg.status_mapping.get(raw_stat.lower(), "hold" if "hold" in raw_stat.lower() else "open")
                    if cfg
                    else "open"
                )

                tl_jt = title_val or (None if is_strict_field_mapping() else (f"{cfg.display_name} Requirement" if cfg and cfg.display_name else None))
                tl_prio = None if is_strict_field_mapping() else ("HIGH" if norm_stat == "open" else "LOW")
                mand_sk, soft_sk = associate_downstream_skills_for_req(body, req_id, cfg.display_name if cfg else None)
                from two_way_verifier import parse_experience_digits, parse_work_mode
                t_exp_min, t_exp_max = parse_experience_digits(exp_val) if exp_val else (None, None)
                m_wm_down = re.search(r"(?im)^\s*(?:[-*•]\s*)?(?:work\s*mode|work\s*model|mode\s*of\s*work)\s*[:\-–—|]\s*([^\r\n]+)", body)
                wm_val_clean = m_wm_down.group(1).strip() if m_wm_down else ""
                t_norm_wm, t_raw_wm = parse_work_mode(wm_val_clean) if wm_val_clean else (None, None)
                tl_item = RequirementItem(
                    req_id=req_id,
                    raw_status=raw_stat,
                    job_title=tl_jt,
                    location=[loc_val] if loc_val else [],
                    experience=exp_val,
                    experience_text=exp_val,
                    experience_min_years=t_exp_min,
                    experience_max_years=t_exp_max,
                    overall_experience=exp_val,
                    budget=budget_val,
                    priority=tl_prio,
                    work_mode=t_norm_wm,
                    work_mode_text=t_raw_wm or (wm_val_clean or None),
                    client_name=cfg.display_name if cfg else None,
                    mandatory_skills=mand_sk if mand_sk else ([] if is_strict_field_mapping() else ([title_val] if title_val else [])),
                    soft_skills=soft_sk if soft_sk else [],
                    confidence=1.0,
                )
                if is_strict_field_mapping():
                    tl_item.confidence = compute_requirement_confidence(tl_item, block_text=body)
                items.append(tl_item)

    # Final pass: Ensure any items missing skills attempt downstream association
    for itm in items:
        if not itm.mandatory_skills and not itm.soft_skills:
            m_sk, s_sk = associate_downstream_skills_for_req(body, itm.req_id, itm.client_name)
            if m_sk:
                itm.mandatory_skills = m_sk
            if s_sk:
                itm.soft_skills = s_sk

    return items


def parse_requirements_from_email(
    *,
    subject: str,
    body: str,
    settings: Settings,
    message_id: str | None = None,
    from_email: str = "",
) -> RequirementParseResult:
    """
    Call the model and parse JSON. On failure, returns empty requirements list.
    """
    if is_status_or_tracker_report(subject, body):
        clear_log_context()
        return RequirementParseResult(
            requirements=[],
            overall_confidence=0.0,
            processing_note="status_report_block",
        )

    # Rule 1: Read Req ID & status from email table directly if present
    table_reqs = extract_req_id_table_requirements(body, subject=subject, from_email=from_email)
    if table_reqs:
        _LOG.info(
            "table_req_id_extraction_success",
            requirements_count=len(table_reqs),
            client=table_reqs[0].client_name,
        )
        clear_log_context()
        return RequirementParseResult(
            requirements=table_reqs,
            overall_confidence=1.0,
            processing_note="table_req_id_extraction_success",
            is_multi_role=len(table_reqs) > 1,
        )

    bind_log_context(message_id=message_id, stage="ai_parser")
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    gemini_base = os.getenv("GEMINI_BASE_URL", "").strip()
    llm_model = os.getenv("LLM_MODEL", "").strip() or settings.openai_model
    api_key = gemini_key or settings.openai_api_key

    if not api_key:
        _LOG.error("ai_extraction_failed", reason="llm_api_key_missing")
        clear_log_context()
        return RequirementParseResult(
            requirements=[],
            overall_confidence=0.0,
            processing_note="LLM api key missing (OPENAI_API_KEY or GEMINI_API_KEY)",
        )

    try:
        from openai import OpenAI
    except ImportError:
        _LOG.error("ai_extraction_failed", reason="openai_package_not_installed")
        clear_log_context()
        return RequirementParseResult(
            requirements=[],
            overall_confidence=0.0,
            processing_note="openai package not installed",
        )

    client = OpenAI(
        api_key=api_key,
        base_url=gemini_base or None,
    )
    from requirement_segmenter import segment_email_into_blocks
    from config import is_placeholder

    latest_segment_raw = _latest_thread_segment(body)
    cleaned_latest = _strip_candidate_tables(latest_segment_raw)
    cleaned_full = _strip_candidate_tables(body or "")
    text_to_segment = cleaned_latest or cleaned_full or body or ""

    blocks = segment_email_into_blocks(text_to_segment, subject=subject or "", html=body if "<table" in (body or "") else None)
    if not blocks:
        blocks = [{"block_text": text_to_segment, "table_row_fields": None, "block_index": 0}]

    from client_detector import detect_client
    cm = detect_client(subject or "", body or "", from_email or "")
    client_name = cm.display_name if cm else "generic"
    from boilerplate_learner import clean_structure_and_extract_boilerplate, validate_skills

    def _lookup_known_requirement(client: str, client_jd_id: str) -> RequirementItem | None:
        try:
            import sqlite3
            req_db = Path("data/metaforge_requirements.db")
            if not req_db.exists():
                return None
            conn = sqlite3.connect(req_db)
            c = conn.cursor()
            c.execute("SELECT payload_json FROM metaforge_requirements WHERE client_jd_id = ? LIMIT 1", (client_jd_id,))
            row = c.fetchone()
            conn.close()
            if row:
                p = json.loads(row[0])
                return RequirementItem.model_validate(p)
        except Exception:
            pass
        return None

    def _detect_status_change(text: str) -> str | None:
        t = text.lower()
        if re.search(r"\b(hold|on hold|paused)\b", t):
            return "hold"
        if re.search(r"\b(closed|fulfilled|cancelled|dropped)\b", t):
            return "closed"
        if re.search(r"\b(reopen|reopened|re-opened|active)\b", t):
            return "open"
        return None

    def _call_model_for_block(b_text: str) -> tuple[dict[str, Any] | None, str, Any]:
        user_content = _PARSER_USER.format(
            subject=subject or "(empty)",
            body=b_text[:16000],
        )
        last_err = None
        max_attempts = 6
        for attempt in range(1, max_attempts + 1):
            try:
                resp = client.chat.completions.create(
                    model=llm_model,
                    messages=[
                        {"role": "system", "content": build_parser_system_prompt()},
                        {"role": "user", "content": user_content},
                    ],
                    temperature=0.0,
                    max_tokens=2000,
                    response_format={
                        "type": "json_schema",
                        "json_schema": {
                            "name": "hiring_requirement_extraction",
                            "schema": STRICT_EXTRACTION_SCHEMA,
                            "strict": True,
                        },
                    },
                )
                if hasattr(resp, "usage") and resp.usage:
                    _LOG.info(
                        "llm_token_usage",
                        prompt_tokens=resp.usage.prompt_tokens,
                        completion_tokens=resp.usage.completion_tokens,
                        total_tokens=resp.usage.total_tokens,
                    )
                    print(f"Token usage: prompt={resp.usage.prompt_tokens}, completion={resp.usage.completion_tokens}")
                    try:
                        tokens_log = Path("logs/tokens.log")
                        tokens_log.parent.mkdir(parents=True, exist_ok=True)
                        with open(tokens_log, "a", encoding="utf-8") as f:
                            f.write(f"call: prompt_tokens={resp.usage.prompt_tokens} completion_tokens={resp.usage.completion_tokens}\n")
                    except Exception:
                        pass
                raw_c = (resp.choices[0].message.content or "").strip()
                p_data = parse_json_loose(raw_c)
                return (p_data if isinstance(p_data, dict) else None), raw_c, getattr(resp, "usage", None)
            except Exception as exc:
                last_err = exc
                msg = str(exc).lower()
                retry_s = min(2 ** (attempt - 1), 30)
                transient = any(t in msg for t in ("503", "rate limit", "429", "timeout", "timed out", "connection"))
                if transient and attempt < max_attempts:
                    time.sleep(max(1, retry_s))
                    continue
                break
        _LOG.warning("ai_block_extraction_failed", error=str(last_err))
        return None, "", None

    extracted_items: list[RequirementItem] = []

    for block in blocks:
        tr_fields = block.get("table_row_fields")
        if tr_fields and ("job_title" in tr_fields or "skills" in tr_fields):
            # Table row whose fields are all mapped by header name needs NO LLM call
            jt = tr_fields.get("job_title") or tr_fields.get("role")
            sk = [tr_fields["skills"]] if tr_fields.get("skills") else []
            loc = [tr_fields["location"]] if tr_fields.get("location") else None
            exp = tr_fields.get("experience")
            bgt = tr_fields.get("budget")
            req_id = tr_fields.get("req_id")
            pos = int(tr_fields["positions"]) if tr_fields.get("positions") and str(tr_fields["positions"]).isdigit() else None
            t_item = RequirementItem(
                job_title=jt,
                mandatory_skills=sk or None,
                location=loc,
                experience=exp,
                experience_text=exp,
                budget=bgt,
                budget_text=bgt,
                req_id=req_id,
                number_of_positions=pos,
                confidence=1.0,
            )
            extracted_items.append(t_item)
            continue

        raw_b_text = block.get("block_text") or ""
        if not raw_b_text.strip():
            continue

        cleaned_b_text, removed_lines = clean_structure_and_extract_boilerplate(raw_b_text, client=client_name)
        if not cleaned_b_text.strip():
            continue

        # Look up (client, client ID). A known requirement skips extraction and AI entirely (0 tokens)
        cjd = extract_client_jd_id_from_text(subject or "", cleaned_b_text, client=client_name)
        if cjd:
            known_req = _lookup_known_requirement(client_name, cjd)
            if known_req:
                st = _detect_status_change(cleaned_b_text)
                if st:
                    known_req.status = st
                extracted_items.append(known_req)
                continue

        d, raw_str, _ = _call_model_for_block(cleaned_b_text)
        if not d:
            continue

        jt = d.get("job_title")
        mand_sk = validate_skills(d.get("mandatory_skills"), client=client_name, removed_lines=removed_lines)
        sec_sk = validate_skills(d.get("skills"), client=client_name, removed_lines=removed_lines)
        np_raw = d.get("notice_period")
        if np_raw and is_placeholder(np_raw):
            np_raw = None

        if not jt and not mand_sk and not sec_sk and d.get("exp_min") is None and d.get("budget_min") is None:
            continue

        ev = d.get("evidence") or {}
        field_ev_clean = {str(k): str(v) for k, v in ev.items() if v is not None and not is_placeholder(v)} if isinstance(ev, dict) else {}

        loc_val = d.get("location")
        if isinstance(loc_val, str):
            loc_val = [loc_val]
        elif not isinstance(loc_val, list):
            loc_val = None

        item = RequirementItem(
            job_title=jt,
            location=loc_val,
            experience_text=d.get("experience_text"),
            experience=d.get("experience_text"),
            experience_min_years=d.get("exp_min"),
            experience_max_years=d.get("exp_max"),
            budget_text=d.get("budget_text"),
            budget=d.get("budget_text"),
            yearly_budget_min=int(d["budget_min"]) if d.get("budget_min") is not None and d.get("budget_period") != "monthly" else None,
            yearly_budget_max=int(d["budget_max"]) if d.get("budget_max") is not None and d.get("budget_period") != "monthly" else None,
            monthly_budget_min=int(d["budget_min"]) if d.get("budget_min") is not None and d.get("budget_period") == "monthly" else (int(d["monthly_budget_min"]) if d.get("monthly_budget_min") is not None else None),
            monthly_budget_max=int(d["budget_max"]) if d.get("budget_max") is not None and d.get("budget_period") == "monthly" else (int(d["monthly_budget_max"]) if d.get("monthly_budget_max") is not None else None),
            budget_currency=d.get("budget_unit"),
            monthly_budget=d.get("monthly_budget_text"),
            mandatory_skills=mand_sk or None,
            soft_skills=sec_sk or None,
            notice_period=np_raw,
            work_mode_text=d.get("work_mode_text"),
            work_mode=d.get("work_mode"),
            number_of_positions=int(d["positions"]) if d.get("positions") is not None else None,
            req_id=d.get("client_req_id"),
            priority=d.get("priority_text"),
            field_evidence_quotes=field_ev_clean,
            confidence=1.0,
        )

        field_sources = {}
        field_methods = {}
        for fn in ("job_title", "location", "experience", "budget", "notice_period", "work_mode", "number_of_positions", "req_id", "mandatory_skills", "soft_skills"):
            val = getattr(item, fn, None)
            if val is not None and not is_placeholder(val):
                field_sources[fn] = "email_body"
                field_methods[fn] = ExtractionMethodEnum.AI_SEMANTIC
        item.field_sources = field_sources
        item.field_extraction_method = field_methods

        extracted_items.append(item)

    validated = RequirementParseResult(
        requirements=extracted_items,
        overall_confidence=1.0 if extracted_items else 0.0,
        is_multi_role=len(extracted_items) > 1,
    )

    # Hybrid extraction hardening: deterministic regex for stable fields + anti-hallucination guards.
    text_for_fields = cleaned_latest or cleaned_full or body
    rule_fields = _extract_rule_fields(subject, text_for_fields)
    exp_resolved, exp_method = _resolve_experience_conflict((cleaned_latest or "") + "\n" + (cleaned_full or ""))
    skill_candidates = _extract_skill_candidates(text_for_fields)
    short_thread_mode = len((text_for_fields or "").strip()) <= 900
    clear_demand_mode = _has_clear_demand_signal(subject or "", text_for_fields or "")
    multi_role_allowed = bool(
        len(validated.requirements) > 1
        or len(blocks) > 1
        or _has_explicit_multi_jd_signal(subject or "", text_for_fields or "")
    )
    for item in validated.requirements:
        field_conf = dict(item.field_confidence or {})
        field_sources = dict(item.field_sources or {})
        field_evidence = dict(item.field_evidence_quotes or {})
        field_method = dict(item.field_extraction_method or {})

        if exp_resolved:
            item.experience = exp_resolved
            field_sources["experience"] = "email_body"
            field_conf["experience"] = max(float(field_conf.get("experience", 0.0)), 0.95)
            field_evidence["experience"] = str(rule_fields.get("experience_quote") or exp_resolved)
            field_method["experience"] = exp_method
        elif rule_fields.get("experience"):
            item.experience = str(rule_fields["experience"])
            field_sources["experience"] = "email_body"
            field_conf["experience"] = max(float(field_conf.get("experience", 0.0)), 0.9)
            field_evidence["experience"] = str(rule_fields.get("experience_quote") or item.experience)
            field_method["experience"] = "regex_anchor"
        elif not item.experience:
            field_sources["experience"] = "not_found"
            field_conf["experience"] = 0.0
            field_evidence["experience"] = ""
            field_method["experience"] = "not_found"

        if isinstance(rule_fields.get("number_of_positions"), int):
            item.number_of_positions = int(rule_fields["number_of_positions"])
            field_conf["number_of_positions"] = max(
                float(field_conf.get("number_of_positions", 0.0)), 0.95
            )
            field_sources["number_of_positions"] = "email_body"
            field_evidence["number_of_positions"] = str(
                rule_fields.get("number_of_positions_quote") or ""
            )
            field_method["number_of_positions"] = "regex_anchor"

        if item.notice_period and _norm(item.notice_period) not in {"period", "notice period", "notice"}:
            item.notice_period = str(item.notice_period)
            field_sources["notice_period"] = field_sources.get("notice_period") or "ai_semantic"
            field_conf["notice_period"] = max(float(field_conf.get("notice_period", 0.0)), 0.85)
            field_evidence["notice_period"] = item.notice_period
            field_method["notice_period"] = field_method.get("notice_period") or "ai_semantic"
        elif rule_fields.get("notice_period"):
            item.notice_period = str(rule_fields["notice_period"])
            field_sources["notice_period"] = "email_body"
            field_conf["notice_period"] = max(float(field_conf.get("notice_period", 0.0)), 0.9)
            field_evidence["notice_period"] = str(
                rule_fields.get("notice_period_quote") or item.notice_period
            )
            field_method["notice_period"] = "regex_anchor"
        elif _norm(item.notice_period) in {"period", "notice period", "notice"}:
            item.notice_period = ""
            field_sources["notice_period"] = "not_found"
            field_conf["notice_period"] = 0.0
            field_evidence["notice_period"] = ""
            field_method["notice_period"] = "not_found"
        elif not item.notice_period:
            field_sources["notice_period"] = "not_found"
            field_conf["notice_period"] = 0.0
            field_evidence["notice_period"] = ""
            field_method["notice_period"] = "not_found"

        if rule_fields.get("engagement_type"):
            item.engagement_type = str(rule_fields["engagement_type"])
            field_conf["engagement_type"] = max(float(field_conf.get("engagement_type", 0.0)), 0.9)
            field_sources["engagement_type"] = "email_body"
            field_evidence["engagement_type"] = str(rule_fields.get("engagement_quote") or "")
            field_method["engagement_type"] = "regex_anchor"
        elif not item.engagement_type:
            field_conf["engagement_type"] = 0.0
            field_sources["engagement_type"] = "not_found"
            field_evidence["engagement_type"] = ""
            field_method["engagement_type"] = "not_found"

        if rule_fields.get("contract_duration"):
            item.contract_duration = str(rule_fields["contract_duration"])
            field_conf["contract_duration"] = max(float(field_conf.get("contract_duration", 0.0)), 0.9)
            field_sources["contract_duration"] = "email_body"
            field_evidence["contract_duration"] = str(rule_fields.get("duration_quote") or "")
            field_method["contract_duration"] = "regex_anchor"
        elif not item.contract_duration:
            field_conf["contract_duration"] = 0.0
            field_sources["contract_duration"] = "not_found"
            field_evidence["contract_duration"] = ""
            field_method["contract_duration"] = "not_found"

        if isinstance(rule_fields.get("yearly_budget_min"), int):
            item.yearly_budget_min = int(rule_fields["yearly_budget_min"])
            item.yearly_budget_max = int(rule_fields.get("yearly_budget_max") or rule_fields["yearly_budget_min"])
            item.monthly_budget_min = None
            item.monthly_budget_max = None
            field_sources["budget"] = "email_body"
            field_conf["budget"] = max(float(field_conf.get("budget", 0.0)), 0.95)
            field_evidence["budget"] = str(rule_fields.get("budget_quote") or "")
            field_method["budget"] = "regex_anchor"
        elif isinstance(rule_fields.get("monthly_budget_min"), int):
            item.monthly_budget_min = int(rule_fields["monthly_budget_min"])
            item.monthly_budget_max = int(
                rule_fields.get("monthly_budget_max") or rule_fields["monthly_budget_min"]
            )
            item.yearly_budget_min = None
            item.yearly_budget_max = None
            field_sources["budget"] = "email_body"
            field_conf["budget"] = max(float(field_conf.get("budget", 0.0)), 0.95)
            field_evidence["budget"] = str(rule_fields.get("budget_quote") or "")
            field_method["budget"] = "regex_anchor"
        elif (
            item.yearly_budget_min is None
            and item.yearly_budget_max is None
            and item.monthly_budget_min is None
            and item.monthly_budget_max is None
        ):
            field_sources["budget"] = "not_found"
            field_conf["budget"] = 0.0
            field_evidence["budget"] = ""
            field_method["budget"] = "not_found"

        if isinstance(rule_fields.get("location"), list) and rule_fields["location"]:
            item.location = list(rule_fields["location"])
            field_sources["location"] = "email_body"
            field_conf["location"] = max(float(field_conf.get("location", 0.0)), 0.9)
            field_evidence["location"] = str(rule_fields.get("location_quote") or "")
            field_method["location"] = "regex_anchor"
            if rule_fields.get("work_mode"):
                item.work_mode = str(rule_fields["work_mode"])
        elif not item.location:
            field_sources["location"] = "not_found"
            field_conf["location"] = 0.0
            field_evidence["location"] = ""
            field_method["location"] = "not_found"

        if item.job_title:
            item.job_title = _clean_job_title(item.job_title)
            field_sources["job_title"] = field_sources.get("job_title") or "ai_semantic"
            field_conf["job_title"] = max(float(field_conf.get("job_title", 0.0)), 0.75)
            field_evidence["job_title"] = item.job_title
            field_method["job_title"] = field_method.get("job_title") or "ai_semantic"
        elif rule_fields.get("job_title"):
            item.job_title = _clean_job_title(str(rule_fields["job_title"]))
            field_sources["job_title"] = str(rule_fields.get("job_title_source") or "email_body")
            field_conf["job_title"] = max(float(field_conf.get("job_title", 0.0)), 0.98)
            field_evidence["job_title"] = str(rule_fields.get("job_title_quote") or item.job_title)
            field_method["job_title"] = "regex_anchor"
        elif short_thread_mode and clear_demand_mode:
            fallback_title = _extract_subject_role_fallback(subject or "")
            if fallback_title:
                item.job_title = _clean_job_title(fallback_title)
                field_sources["job_title"] = "email_subject"
                field_conf["job_title"] = max(float(field_conf.get("job_title", 0.0)), 0.82)
                field_evidence["job_title"] = _strip_subject_prefixes(subject or "")
                field_method["job_title"] = "hybrid_regex_ai"
            else:
                item.job_title = ""
                field_sources["job_title"] = "not_found"
                field_conf["job_title"] = 0.0
                field_evidence["job_title"] = ""
                field_method["job_title"] = "not_found"
        else:
            item.job_title = ""
            field_sources["job_title"] = "not_found"
            field_conf["job_title"] = 0.0
            field_evidence["job_title"] = ""
            field_method["job_title"] = "not_found"

        # Prioritize explicit skill-line candidates over model-proposed skills.
        merged_skills = list(item.mandatory_skills or []) + list(item.soft_skills or []) + (skill_candidates or [])
        filtered = [s for s in merged_skills if _skill_has_evidence(s, subject, cleaned_latest or cleaned_full or body)]
        # Keep first seen order and split into mandatory/soft buckets for compatibility.
        uniq: list[str] = []
        seen_sk: set[str] = set()
        for sk in filtered:
            if _is_noise_skill_candidate(sk):
                continue
            k = _norm(sk)
            if k and k not in seen_sk:
                seen_sk.add(k)
                uniq.append(sk)
        filtered_mandatory = uniq[: min(8, len(uniq))]
        filtered_soft = uniq[min(8, len(uniq)) : min(20, len(uniq))]
        item.mandatory_skills = filtered_mandatory
        item.soft_skills = filtered_soft
        if filtered_mandatory or filtered_soft:
            field_sources["skills"] = "email_body"
            field_conf["skills"] = max(float(field_conf.get("skills", 0.0)), 0.7)
            field_evidence["skills"] = _best_skill_evidence(filtered_mandatory + filtered_soft, body)
            field_method["skills"] = "ai_semantic"
        else:
            if not is_strict_field_mapping():
                hints = _extract_subject_skill_hints(subject or "", text_for_fields or "", item.job_title or "")
                if hints and (short_thread_mode or clear_demand_mode):
                    item.mandatory_skills = hints[:8]
                    item.soft_skills = hints[8:12]
                    field_sources["skills"] = "email_subject"
                    field_conf["skills"] = max(float(field_conf.get("skills", 0.0)), 0.58)
                    field_evidence["skills"] = _strip_subject_prefixes(subject or "")[:240]
                    field_method["skills"] = "hybrid_regex_ai"
                else:
                    field_sources["skills"] = "not_found"
                    field_conf["skills"] = 0.0
                    field_evidence["skills"] = ""
                    field_method["skills"] = "not_found"
            else:
                field_sources["skills"] = "not_found"
                field_conf["skills"] = 0.0
                field_evidence["skills"] = ""
                field_method["skills"] = "not_found"

        if is_strict_field_mapping():
            item.confidence = compute_requirement_confidence(item, block_text=text_for_fields or body)
        else:
            key_fields = (
                float(field_conf.get("job_title", 0.0)),
                float(field_conf.get("skills", 0.0)),
                float(field_conf.get("location", 0.0)),
                float(field_conf.get("budget", 0.0)),
                float(field_conf.get("experience", 0.0)),
            )
            item.confidence = round(sum(key_fields) / len(key_fields), 4)
        item.field_confidence = field_conf
        item.field_sources = field_sources
        item.field_evidence_quotes = field_evidence
        item.field_extraction_method = field_method

        # Verify evidence quotes against source text
        verify_evidence_quotes(item, text_for_fields)

        # Validate or extract client requirement ID (C1, C2)
        from client_identity_validator import is_genuine_client_id

        if item.req_id:
            is_val, clean_cid, reason = is_genuine_client_id(
                item.client_name,
                item.req_id,
                context={
                    "text": text_for_fields,
                    "subject": subject,
                    "job_title": item.job_title,
                    "location": str(item.location),
                    "other_rows": [r.model_dump() for r in validated.requirements if r is not item],
                },
            )
            item.req_id = clean_cid if is_val else None

        if not item.req_id:
            ext_cid = extract_client_jd_id_from_text(subject, text_for_fields, client=item.client_name)
            if ext_cid:
                item.req_id = ext_cid

    # Balanced strictness: retain title-only requirements for clear short demand threads.
    validated.requirements = [
        req
        for req in validated.requirements
        if req.job_title
        and (
            req.mandatory_skills
            or req.soft_skills
            or req.location
            or req.experience
            or (short_thread_mode and clear_demand_mode)
            or multi_role_allowed
        )
    ]
    # Default to single requirement unless explicit multi-JD signals are present or LLM returned multiple items.
    if not multi_role_allowed and len(validated.requirements) < 2:
        validated.requirements = _pick_primary_requirement(validated.requirements)

    # Multi-role table augmentation: create distinct role entries when table rows are present.
    # Keep existing extracted rows, then add missing role rows discovered symbolically.
    table_rows = _extract_multi_role_rows(cleaned_latest or cleaned_full or body)
    if multi_role_allowed and table_rows:
        existing_titles = {_norm(req.job_title) for req in validated.requirements}
        for row in table_rows:
            jt = _norm(str(row.get("job_title") or ""))
            if not jt or jt in existing_titles:
                continue
            try:
                validated.requirements.append(RequirementItem.model_validate(row))
                existing_titles.add(jt)
            except Exception:
                continue

    # Requirement pivot support: ensure thread-level SAP role mentions become separate requirement entries
    # without leaking candidate table PII.
    pivot_titles = _extract_requirement_titles_from_thread(subject, body or "")
    if multi_role_allowed and pivot_titles:
        existing_titles = {_norm(req.job_title) for req in validated.requirements}
        for t in pivot_titles:
            if _norm(t) in existing_titles:
                continue
            try:
                row = {
                    "job_title": t,
                    "mandatory_skills": [t] if t else [],
                    "skills": [t] if t else [],
                    "location": [],
                    "yearly_budget_min": None,
                    "yearly_budget_max": None,
                    "experience": "",
                    "notice_period": "",
                    "confidence": 0.6,
                    "field_confidence": {
                        "job_title": 0.9,
                        "skills": 0.6,
                        "location": 0.0,
                        "budget": 0.0,
                        "experience": 0.0,
                    },
                    "field_sources": {
                        "job_title": "email_subject",
                        "skills": "email_subject",
                        "location": "not_found",
                        "budget": "not_found",
                        "experience": "not_found",
                    },
                    "field_evidence_quotes": {
                        "job_title": t,
                        "skills": t,
                        "location": "",
                        "budget": "",
                        "experience": "",
                    },
                    "field_extraction_method": {
                        "job_title": "ai_semantic",
                        "skills": "ai_semantic",
                        "location": "not_found",
                        "budget": "not_found",
                        "experience": "not_found",
                    },
                }
                validated.requirements.append(RequirementItem.model_validate(row))
                existing_titles.add(_norm(t))
            except Exception:
                continue

    if multi_role_allowed:
        validated.requirements = _consolidate_multi_role_requirements(validated.requirements)
        validated.is_multi_role = len(validated.requirements) > 1
    else:
        validated.is_multi_role = False

    if not validated.is_multi_role:
        validated.requirements = _apply_structured_jd_single_role(
            validated.requirements,
            subject=subject or "",
            body=body or "",
        )
    validated.is_multi_role = len(validated.requirements) > 1
    if is_strict_field_mapping():
        from two_way_verifier import deterministic_extract_block, reconcile_two_way
        det_extracted = deterministic_extract_block(body)
        updated_reqs = []
        for req in validated.requirements:
            req_dict = req.model_dump(mode="json", by_alias=True)
            reconciled_dict, review_req, reasons = reconcile_two_way(req_dict, det_extracted, body)
            reconciled_item = RequirementItem.model_validate(reconciled_dict)
            reconciled_item.confidence = compute_requirement_confidence(reconciled_item, block_text=body)
            if review_req:
                reconciled_item.raw_status = "PENDING_REVIEW"
            updated_reqs.append(reconciled_item)
        validated.requirements = updated_reqs
    else:
        for req in validated.requirements:
            if req.req_id or req.job_title:
                req.confidence = max(float(req.confidence or 0.95), 0.95)

    _LOG.info(
        "ai_extraction_success",
        requirements_count=len(validated.requirements),
        overall_confidence=validated.overall_confidence,
        is_multi_role=validated.is_multi_role,
    )
    clear_log_context()
    return validated
