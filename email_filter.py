"""
Email Access-Control Validator and Filter Rules.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional

try:
    import pytz
    def _get_ist_tz():
        return pytz.timezone('Asia/Kolkata')
except ImportError:
    from zoneinfo import ZoneInfo
    def _get_ist_tz():
        return ZoneInfo('Asia/Kolkata')

_LOG = logging.getLogger(__name__)

import json
from pathlib import Path

def _load_allowed_domains() -> set[str]:
    rules_path = Path(__file__).resolve().parent / "config" / "pipeline_rules.json"
    if rules_path.exists():
        try:
            with open(rules_path, "r", encoding="utf-8") as f:
                rules = json.load(f)
                doms = rules.get("allowed_domains", [])
                if doms:
                    return set(doms)
        except Exception:
            pass
    return {
        "idexcel.com",
        "iexcel.co.in",
        "kpmg.com",
        "itcinfotech.com",
        "ltts.com",
        "eximietas.com",
    }

ALLOWED_CLIENT_DOMAINS = _load_allowed_domains()

ALLOWED_SENDER_EMAILS = {
    "rkarnam@metaforgeit.com",   # CEO exception
}


def validate_email_access(email_input: str) -> Dict[str, str]:
    """
    Decide whether an email address is ALLOWED or BLOCKED using strict allowlist rules.
    Returns dict with keys: 'email', 'decision', 'reason'.
    """
    if not email_input or not isinstance(email_input, str):
        return {
            "email": "",
            "decision": "BLOCKED",
            "reason": "invalid format"
        }

    # Rule 1: Normalize
    email = email_input.strip().lower()

    # Rule 2: Valid email format check (exactly one "@", non-empty local part and domain)
    if email.count("@") != 1:
        return {
            "email": email,
            "decision": "BLOCKED",
            "reason": "invalid format"
        }

    local_part, domain = email.split("@", 1)
    if not local_part or not domain or "." not in domain:
        return {
            "email": email,
            "decision": "BLOCKED",
            "reason": "invalid format"
        }

    # Rule 3: CEO Exception (only rkarnam@metaforgeit.com is allowed from metaforgeit.com)
    if email == "rkarnam@metaforgeit.com" or email in ALLOWED_SENDER_EMAILS:
        return {
            "email": email,
            "decision": "ALLOWED",
            "reason": "CEO exception"
        }

    # Rule 4: Internal domain block (completely block all other @metaforgeit.com senders)
    if domain == "metaforgeit.com" or domain.endswith(".metaforgeit.com") or email.endswith("@metaforgeit.com"):
        return {
            "email": email,
            "decision": "BLOCKED",
            "reason": "internal domain blocked: metaforgeit.com (only rkarnam@metaforgeit.com permitted)"
        }

    # Rule 5: Strict exact domain match
    if domain in ALLOWED_CLIENT_DOMAINS:
        return {
            "email": email,
            "decision": "ALLOWED",
            "reason": f"allowed domain: {domain}"
        }

    # Rule 6: Default BLOCKED
    return {
        "email": email,
        "decision": "BLOCKED",
        "reason": "domain not in allowlist"
    }


def is_sender_allowlisted(from_email: str) -> bool:
    """Boolean helper wrapping validate_email_access."""
    result = validate_email_access(from_email)
    allowed = result["decision"] == "ALLOWED"
    if not allowed:
        _LOG.info("Sender blocked by allowlist: %r (%s)", from_email, result["reason"])
    return allowed


_POSITION_COUNT_RX = re.compile(r"\b\d+\+?\s*(?:position|positions|opening|openings)\b", re.I)
_EXP_SKILL_RX = re.compile(
    r"\b(?:exp|experience)\s*[:\-]?\s*\d+|\d+\+?\s*(?:yrs?|years?)\b|\bmandatory\s+skills?\b|\brequired\s+skills?\b",
    re.I,
)
_NARRATIVE_HIRING_RX = re.compile(
    r"\b(?:need|looking for|hiring|hiring for|require|requirement|opening|vacancy|position|role|job|engineer|developer|architect|consultant|lead|specialist|analyst|manager|contractor|technologies|tech stack|skills?)\b",
    re.I,
)


def has_requirement_structure(body: str, subject: str = "", has_attachments: bool = False) -> bool:
    """
    True if the email contains concrete requirement details, narrative hiring signals,
    attachment presence, or structural JD markers.
    """
    if has_attachments:
        return True

    blob = f"{(subject or '')}\n{(body or '')}".strip()
    if not blob:
        return False

    if _POSITION_COUNT_RX.search(blob):
        return True
    if _EXP_SKILL_RX.search(blob):
        return True
    if re.search(r"\b(?:req\s*id|job\s*posting\s*id|so\s*#?|acc|req|dltjp|rq)[\s\-_:]*#?\d+\b", blob, re.I):
        return True
    if _NARRATIVE_HIRING_RX.search(blob):
        return True
    try:
        from requirement_classifier import FTE_JD_MARKERS
        if any(rx.search(blob) for rx in FTE_JD_MARKERS):
            return True
    except ImportError:
        pass
    return False


@dataclass(frozen=True)
class FilterResult:
    allowed: bool
    reason: str | None = None


def normalize_to_ist(received_date_time: str) -> str:
    """Convert all timestamps to Asia/Kolkata (IST) before processing."""
    try:
        if 'Z' in received_date_time:
            dt = datetime.fromisoformat(received_date_time.replace('Z', '+00:00'))
        else:
            dt = datetime.fromisoformat(received_date_time)
        
        ist_tz = _get_ist_tz()
        dt_ist = dt.astimezone(ist_tz)
        return dt_ist.isoformat()
    except Exception:
        return received_date_time


def apply_email_filter(
    from_email: str,
    body: str,
    subject: str = "",
    has_attachments: bool = False,
    **kwargs: Any,
) -> FilterResult:
    """Main intake gate logic for pipeline."""
    validation = validate_email_access(from_email)
    if validation["decision"] != "ALLOWED":
        return FilterResult(allowed=False, reason=f"Sender blocked: {validation['reason']}")
    
    if not has_requirement_structure(body, subject=subject, has_attachments=has_attachments):
        return FilterResult(allowed=False, reason="Body lacks requirement structure")
        
    return FilterResult(allowed=True, reason="Passed sender allowlist and structure gate")
