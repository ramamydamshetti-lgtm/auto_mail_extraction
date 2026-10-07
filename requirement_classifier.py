"""AI-based gate: classify as REQUIREMENT vs NOT_A_REQUIREMENT for pipeline intake."""

from __future__ import annotations

import logging
import os
import re
from typing import TYPE_CHECKING

from intake_gates import (
    is_subject_reply,
    pre_classify_block_reason,
    should_block_internal_sender,
)

from config import Settings

_LOG = logging.getLogger(__name__)

_FTE_JD_MARKERS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\brole title\s*:", re.I),
    re.compile(r"\bposition\s*:", re.I),
    re.compile(r"\bjob title\s*:", re.I),
    re.compile(r"\bjob summary\b", re.I),
    re.compile(r"\bkey responsibilities\b", re.I),
    re.compile(r"\brole purpose\b", re.I),
    re.compile(r"\bmust have\b", re.I),
    re.compile(r"\bnice to have\b", re.I),
    re.compile(r"\bprimary skills\b", re.I),
    re.compile(r"\bsecondary skills\b", re.I),
    re.compile(r"\bkey skills\b", re.I),
    re.compile(r"\bskills and experience\b", re.I),
    re.compile(r"\brequired skills\b", re.I),
    re.compile(r"\bexperience required\b", re.I),
    re.compile(r"\bdesired profile\b", re.I),
    re.compile(r"\bjob description\b", re.I),
)

FTE_JD_MARKERS = _FTE_JD_MARKERS

def heuristic_structured_client_jd(subject: str, body: str) -> bool:
    """
    Direct client JD (FTE / project / C2H) without classic vendor broadcast phrasing.
    Requires multiple JD sections so trackers and one-liners do not bypass the LLM gate.
    """
    from intake_gates import is_status_or_tracker_report

    subj = (subject or "").strip()
    if is_status_or_tracker_report(subj, body):
        return False
    if re.match(r"^\s*(re|fw|fwd)\s*:", subj, re.I):
        return False

    blob = body or ""
    blob_l = blob.lower()

    jd_hits = sum(1 for rx in _FTE_JD_MARKERS if rx.search(blob))
    has_experience = bool(
        re.search(
            r"\b(?:yrs?|years?)\s*[:\-–—]|\b\d+\s*-\s*\d+\+?\s*(?:yrs?|years?)|\boverall\s+exp\b",
            blob_l,
        )
    )
    has_location = bool(re.search(r"\blocation\s*[:\-–—]\s*\S", blob_l))
    has_budget_line = bool(re.search(r"\bbudget\s*[:\-–—]", blob_l))
    staffing_subject = bool(
        re.search(r"\b(?:fte|c2h|sub[\-\s]?con|workday|requirement|urgent)\b|\|", (subject or "").lower())
    )

    if jd_hits >= 3:
        return True
    if jd_hits >= 2 and (has_experience or has_location) and (has_budget_line or staffing_subject):
        return True
    return False


from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class ClassificationResult:
    label: Literal["REQUIREMENT", "NOT_A_REQUIREMENT"]
    confidence: float  # 0.0 to 1.0


_CLASSIFIER_PROMPT = """You distinguish a CLIENT JOB REQUIREMENT from everything else.

Return a JSON object with exactly two keys:
- "label": "REQUIREMENT" or "NOT_A_REQUIREMENT"
- "confidence": float between 0.0 and 1.0

Classification Labels:
- REQUIREMENT — an external client/vendor/RPO is asking to fill one or more roles NOW.
  Valid signals: JD text, bill rate, open positions, mandatory skills, experience band,
  "share profiles", "kindly submit", SOW intake, new demand with hiring details in the latest message.
- NOT_A_REQUIREMENT — everything else, including:
  * Promotional emails, newsletters, marketing updates
  * Job-seeker self-applications, candidate resumes ("I am writing to apply", "attached is my resume")
  * Internal recruiter replies, status/submission reports ("following is weekly report", submission tables)
  * Popup / system notifications, automated calendar invites, password resets
  * Interview scheduling, thank-you notes, offer updates, "no update" replies

Labeled Examples:

Example 1 (Promotional Email):
Subject: Weekly Tech Trends Newsletter
Body: Here are top tech news. Click here to unsubscribe from our newsletter.
Output: {{"label": "NOT_A_REQUIREMENT", "confidence": 1.0}}

Example 2 (Job-Seeker Self-Application):
Subject: Application for Java Developer
Body: Dear Hiring Manager, I am writing to apply for the Java Developer position. Attached is my resume.
Output: {{"label": "NOT_A_REQUIREMENT", "confidence": 1.0}}

Example 3 (Internal Recruiter Reply):
Subject: Re: Python Developer requirement
Body: Thanks, I sent 3 profiles to the client today. Will share updates shortly.
Output: {{"label": "NOT_A_REQUIREMENT", "confidence": 0.95}}

Example 4 (Popup / System Notification):
Subject: System Security Alert
Body: Your account password was changed. This is an automated message.
Output: {{"label": "NOT_A_REQUIREMENT", "confidence": 1.0}}

{thread_hint}
Email subject:
{subject}

Email body (evaluate the LATEST message; ignore quoted reply history unless it contains a new demand):
{body}
"""


def classify_email(
    email_body: str = "",
    *,
    subject: str = "",
    settings: Settings | None = None,
    from_email: str = "",
    body: str | None = None,
    **kwargs: Any,
) -> ClassificationResult:
    """
    Classify email as REQUIREMENT or NOT_A_REQUIREMENT.

    Returns ClassificationResult(label, confidence).
    """
    if settings is None:
        settings = Settings.from_env()
    target_body = body if body is not None else email_body

    block = pre_classify_block_reason(from_email, subject, target_body)
    if block:
        _LOG.info("Classifier blocked message tag=%s from=%s subject=%r", block, from_email, subject)
        return ClassificationResult("NOT_A_REQUIREMENT", 1.0)

    if heuristic_obvious_client_requirement(subject, target_body):
        _LOG.info("Heuristic client-requirement gate passed (vendor JD pattern)")
        return ClassificationResult("REQUIREMENT", 0.95)

    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    gemini_base = os.getenv("GEMINI_BASE_URL", "").strip()
    llm_model = os.getenv("LLM_MODEL", "").strip() or settings.openai_model
    api_key = gemini_key or settings.openai_api_key

    if not api_key:
        raise RuntimeError("Classifier misconfigured: missing API key")

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("Classifier misconfigured: openai package not installed") from exc

    client = OpenAI(
        api_key=api_key,
        base_url=gemini_base or None,
    )

    thread_hint = ""
    if is_subject_reply(subject):
        thread_hint = (
            "THREAD: This email is a REPLY. Classify NOT_A_REQUIREMENT unless the newest "
            "top-of-thread text is a fresh client demand (new JD/opening/skills/bill rate). "
            "Ignore quoted blocks, submission tables, and weekly report content below."
        )
    elif should_block_internal_sender(from_email, subject):
        thread_hint = "THREAD: Internal forward — only REQUIREMENT if forwarding a client JD."

    user_content = _CLASSIFIER_PROMPT.format(
        thread_hint=thread_hint,
        subject=subject or "(empty)",
        body=(email_body or "")[:24_000],
    )

    import json
    import time

    max_attempts = 3
    backoff_delays = [2.0, 5.0]

    label: Literal["REQUIREMENT", "NOT_A_REQUIREMENT"] = "REQUIREMENT"
    confidence = 0.0
    call_succeeded = False

    for attempt in range(1, max_attempts + 1):
        try:
            resp = client.chat.completions.create(
                model=llm_model,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You classify recruitment emails into JSON object with 'label' "
                            "('REQUIREMENT', 'NOT_A_REQUIREMENT') and 'confidence' (0.0-1.0)."
                        ),
                    },
                    {"role": "user", "content": user_content},
                ],
                temperature=0,
                max_tokens=100,
            )
            raw = resp.choices[0].message.content or ""
            data = json.loads(raw)
            parsed_label = str(data.get("label") or "").strip().upper()
            if parsed_label not in {"REQUIREMENT", "NOT_A_REQUIREMENT"}:
                parsed_label = "REQUIREMENT"

            label = parsed_label  # type: ignore[assignment]
            conf_val = data.get("confidence")
            confidence = float(conf_val) if conf_val is not None else 0.8
            call_succeeded = True
            break
        except Exception as exc:
            _LOG.warning(
                "LLM classifier attempt %d/%d failed with %s: %s",
                attempt,
                max_attempts,
                type(exc).__name__,
                exc,
            )
            if attempt < max_attempts:
                time.sleep(backoff_delays[attempt - 1])

    if not call_succeeded:
        _LOG.error(
            "Classifier failed after retries, defaulting to REQUIREMENT for manual/downstream visibility"
        )
        label = "REQUIREMENT"
        confidence = 0.0

    _LOG.debug("Classifier output: label=%s, confidence=%.2f", label, confidence)
    return ClassificationResult(label=label, confidence=confidence)


def heuristic_obvious_client_requirement(subject: str, body: str) -> bool:
    """
    Deterministic bypass before the LLM gate for unmistakable vendor JD patterns only.
    Never bypasses status reports, replies, or internal outbound mail.
    """
    from intake_gates import is_status_or_tracker_report

    subj = (subject or "").strip()
    subj_l = subj.lower()
    blob = (body or "").lower()

    if is_status_or_tracker_report(subj, body):
        return False

    if re.match(r"^\s*(re|fw|fwd)\s*:", subj, re.I):
        return False

    has_req_in_subject = "requirement" in subj_l
    has_bill_rate = bool(re.search(r"\bbill rate\b", blob))
    has_tpc_rates = bool(re.search(r"\btpc\s+rates?\b", blob))
    has_overall_exp = bool(re.search(r"\boverall\s+exp\b", blob))
    has_open_pos = bool(re.search(r"\bopen positions?\b", blob))
    has_openings = bool(re.search(r"\bopenings?\b", blob))
    has_lpa_budget = bool(re.search(r"\b\d+(?:\.\d+)?\s*lpa\b", blob))
    has_so_id = bool(re.search(r"\bso\s*id\s*[:\-]?\s*[a-z0-9_\/-]+", blob))
    has_location_inline = bool(re.search(r"\blocation\s*[:\-–—]\s*[a-z]", blob))
    has_mandatory = bool(re.search(r"\bmandatory\s+skills?\b", blob))
    has_share_profiles = bool(re.search(r"\b(?:kindly|please)\s+share\s+profiles?\b", blob))

    if has_req_in_subject and (has_bill_rate or has_open_pos or has_openings or has_share_profiles):
        return True

    if has_bill_rate and (has_open_pos or has_openings):
        return True

    if (has_open_pos or has_openings) and (has_tpc_rates or has_bill_rate):
        return True
    if (has_open_pos or has_openings) and has_mandatory and (
        has_overall_exp or has_share_profiles or has_tpc_rates
    ):
        return True
    if has_openings and has_so_id and (has_mandatory or has_location_inline or has_lpa_budget):
        return True

    if heuristic_structured_client_jd(subject, body):
        return True

    return False
