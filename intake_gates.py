"""
Deterministic intake gates: block internal outbound mail, weekly reports, and tracker noise
before LLM classification or parsing.
"""

from __future__ import annotations

import re

_SUBJ_FORWARD = re.compile(r"^\s*(fw|fwd)\s*:", re.IGNORECASE)
_SUBJ_REPLY = re.compile(r"^\s*re\s*:", re.IGNORECASE)

INTERNAL_SENDER_DOMAINS: tuple[str, ...] = ("metaforgeit.com",)

_STATUS_REPORT_SUBJECT_RE = re.compile(
    r"(?i)\b("
    r"weekly\s+report|"
    r"submission\s+report|"
    r"status\s+report|"
    r"tracker\s+report|"
    r"pipeline\s+report|"
    r"recruiter\s+report"
    r")\b",
)

_STATUS_REPORT_BODY_RES: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)\bfollowing\s+is\s+(?:the\s+)?weekly\s+report\b"),
    re.compile(r"(?i)\bno\.?\s*of\s+submissions\b"),
    re.compile(r"(?i)\bl1\s+interviews?\b"),
    re.compile(r"(?i)\bno\.?\s*of\s+rejections\b"),
    re.compile(r"(?i)\bdetails\s+of\s+list\s+of\s+candidate\s+submitted\b"),
    re.compile(r"(?i)\bcandidates?\s+submitted\b"),
    re.compile(r"(?i)\bsubmission\s+tracker\b"),
    re.compile(r"(?i)\breceived\s+date\b.*\bsubmissions?\b"),
)


def _sender_domain(from_email: str) -> str:
    email = (from_email or "").strip().lower()
    if "@" not in email:
        return ""
    return email.split("@", 1)[1]


def is_internal_sender(from_email: str) -> bool:
    email = (from_email or "").strip().lower()
    if not email:
        return False
    domain = _sender_domain(email)
    return (
        domain == "metaforgeit.com"
        or domain.endswith(".metaforgeit.com")
        or email.endswith("@metaforgeit.com")
        or any(domain == d or domain.endswith(f".{d}") for d in INTERNAL_SENDER_DOMAINS)
    )


def is_subject_forward(subject: str) -> bool:
    return bool(_SUBJ_FORWARD.match((subject or "").strip()))


def is_subject_reply(subject: str) -> bool:
    return bool(_SUBJ_REPLY.match((subject or "").strip()))


def should_block_internal_sender(from_email: str, subject: str = "") -> bool:
    """
    Completely block all internal mail from @metaforgeit.com, EXCEPT rkarnam@metaforgeit.com.
    """
    email = (from_email or "").strip().lower()
    if not is_internal_sender(email):
        return False
    # CEO Exception: only rkarnam@metaforgeit.com is allowed to forward client requirements
    if email == "rkarnam@metaforgeit.com":
        return not is_subject_forward(subject)
    # ALL other @metaforgeit.com senders are completely blocked
    return True


def is_status_or_tracker_report(subject: str, body: str) -> bool:
    """Weekly reports, submission trackers, and interview outcome tables."""
    subj = (subject or "").strip()
    subj_l = subj.lower()

    # Explicit override: Client requirement, demand, or job emails are NEVER status reports
    if any(k in subj_l for k in ("requirement", "demand", "opening", "urgent", "job", "req")):
        return False

    blob = f"{subj}\n{body or ''}".lower()

    if _STATUS_REPORT_SUBJECT_RE.search(subj):
        return True

    body_hits = sum(1 for rx in _STATUS_REPORT_BODY_RES if rx.search(blob))
    if body_hits >= 2:
        return True

    if "weekly report" in blob and body_hits >= 1:
        return True

    if (
        "no of submissions" in blob
        and ("l1 interview" in blob or "no of rejection" in blob)
    ):
        return True

    if "details of list of candidate submitted" in blob:
        return True

    return False


PROMOTIONAL_SENDER_PATTERNS: tuple[str, ...] = (
    "newsletter@",
    "promotions@",
    "marketing@",
    "updates@",
    "news@",
    "offers@",
    "campaign@",
    "no-reply@marketing",
    "noreply@marketing",
    "info@marketing",
)

PROMOTIONAL_BODY_MARKERS: tuple[str, ...] = (
    "unsubscribe",
    "view in browser",
    "view this email in your browser",
    "manage email preferences",
    "marketing preferences",
    "click here to unsubscribe",
    "no longer wish to receive",
    "privacy policy",
    "terms of service",
    "all rights reserved",
)


def is_promotional_email(from_email: str, subject: str, body: str) -> bool:
    """
    Hard-blocks dedicated promotional/marketing emails.
    Requires multiple strong promotional markers or a known promotional sender + marker.
    Avoids rejecting client emails that happen to mention single words.
    """
    sender = (from_email or "").strip().lower()
    text = f"{(subject or '')}\n{(body or '')}".lower()

    sender_match = any(sender.startswith(p) or p in sender for p in PROMOTIONAL_SENDER_PATTERNS)
    marker_hits = sum(1 for m in PROMOTIONAL_BODY_MARKERS if m in text)

    # Strong sender + at least 1 marker
    if sender_match and marker_hits >= 1:
        return True

    # Generic sender, but at least 2 distinct strong promotional markers
    if marker_hits >= 2:
        return True

    return False


JOB_SEEKER_EXPLICIT_MARKERS: tuple[str, ...] = (
    "i am writing to apply",
    "application for the position",
    "application for the role",
    "application for post",
    "please find my resume attached",
    "please find attached my resume",
    "please find my cv attached",
    "please find attached my cv",
    "attached is my resume",
    "attached is my cv",
    "enclosed is my resume",
    "enclosed is my cv",
    "seeking a position",
    "seeking job opportunities",
    "looking for job opportunities",
    "looking for a job",
    "kindly consider my profile",
    "kindly consider my resume",
    "consider my candidature",
)

JOB_SEEKER_FIRST_PERSON_MARKERS: tuple[str, ...] = (
    "my profile for your review",
    "my resume for your review",
    "my cv for your review",
    "my total experience is",
    "my skills include",
    "my core skills",
    "i am currently working as",
    "i am an experienced",
    "i have total",
)


def is_job_seeker_email(from_email: str, subject: str, body: str, has_attachments: bool = False) -> bool:
    """
    Hard-blocks candidates applying for jobs or submitting their own resumes.
    Does NOT block emails solely because generic words like 'resume', 'candidate', 
    'developer', 'experience', or 'position' appear or are missing.
    """
    text = f"{(subject or '')}\n{(body or '')}".lower()

    # Explicit application phrasing (e.g., "I am writing to apply", "Please find my resume attached")
    if any(marker in text for marker in JOB_SEEKER_EXPLICIT_MARKERS):
        return True

    # Combination of candidate first-person phrasing AND resume attachment/indicator
    first_person_hits = sum(1 for marker in JOB_SEEKER_FIRST_PERSON_MARKERS if marker in text)
    if first_person_hits >= 1:
        if has_attachments or "attached" in text or "resume" in text or "cv" in text:
            return True

    return False


def pre_classify_block_reason(
    from_email: str, subject: str, body: str, has_attachments: bool = False
) -> str | None:
    """Return a decision tag when the message must not become a requirement intake."""
    email = (from_email or "").strip().lower()
    if is_internal_sender(email) and email != "rkarnam@metaforgeit.com":
        return "INTERNAL_SENDER_BLOCKED"
    if should_block_internal_sender(from_email, subject):
        return "INTERNAL_RECRUITER_BLOCK"
    if is_status_or_tracker_report(subject, body):
        return "STATUS_REPORT_BLOCK"
    if is_promotional_email(from_email, subject, body):
        return "PROMOTIONAL_EMAIL_BLOCK"
    if is_job_seeker_email(from_email, subject, body, has_attachments):
        return "JOB_SEEKER_BLOCK"
    return None

