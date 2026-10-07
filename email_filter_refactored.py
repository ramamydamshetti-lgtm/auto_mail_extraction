"""
ZERO-SKIP EMAIL FILTER - 100% Extraction Reliability
Rule 1: Zero-Skip Policy - Remove all pre-extraction filters
Every client email must be passed to AI parser. No guessing or skipping before AI evaluation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
try:
    import pytz
    def _get_ist_tz():
        return pytz.timezone('Asia/Kolkata')
except ImportError:
    from zoneinfo import ZoneInfo
    def _get_ist_tz():
        return ZoneInfo('Asia/Kolkata')
from typing import Optional


@dataclass(frozen=True)
class FilterResult:
    allowed: bool
    reason: str | None = None


def normalize_to_ist(received_date_time: str) -> str:
    """
    Rule 3: Timezone Normalization
    Convert all timestamps to Asia/Kolkata (IST) before processing
    """
    try:
        # Parse the incoming datetime (usually in UTC)
        if 'Z' in received_date_time:
            dt = datetime.fromisoformat(received_date_time.replace('Z', '+00:00'))
        else:
            dt = datetime.fromisoformat(received_date_time)
        
        # Convert to IST
        ist_tz = _get_ist_tz()
        dt_ist = dt.astimezone(ist_tz)
        
        # Return in ISO format with IST offset
        return dt_ist.isoformat()
    except Exception:
        # If parsing fails, return original
        return received_date_time


def apply_zero_skip_filter(
    *,
    subject: str,
    body: str,
    has_attachments: bool,
    from_email: str = "",
    received_date_time: str = "",
    is_client_domain: bool = True,
) -> FilterResult:
    """
    ZERO-SKIP POLICY: Allow ALL client domain emails to pass through to AI parser
    Only filter out obvious spam/system emails, never skip potential requirements
    """
    
    # Only filter out non-client domains and obvious system emails
    sender = (from_email or "").strip().lower()
    
    # Block only obvious automated system emails (not client notifications)
    blocked_senders = {
        "mailer-daemon@",
        "postmaster@",
        "security@",
        "abuse@",
    }
    
    if any(sender.startswith(blocked) for blocked in blocked_senders):
        return FilterResult(False, "system_email")
    
    # Allow ALL client domain emails (Zero-Skip Policy)
    if is_client_domain:
        return FilterResult(True, None)
    
    # For non-client domains, apply minimal filtering only
    subject_lower = (subject or "").lower()
    body_lower = (body or "").lower()
    
    # Block only obvious non-requirement content
    obvious_non_requirements = [
        "delivery status notification",
        "failure notice",
        "undeliverable",
        "auto-reply",
        "out of office",
        "vacation",
        "automatic reply",
    ]
    
    for phrase in obvious_non_requirements:
        if phrase in subject_lower or phrase in body_lower:
            return FilterResult(False, f"obvious_non_requirement: {phrase}")
    
    # Default to allow for everything else - let AI decide
    return FilterResult(True, None)


def sort_emails_chronologically(emails: list[dict]) -> list[dict]:
    """
    Rule 2: Chronological Integrity
    Sort emails by receivedDateTime (Oldest to Newest) before processing
    """
    def extract_datetime(email):
        received_time = email.get('received_date_time', '')
        if not received_time:
            return datetime.min
        
        try:
            # Normalize to IST first, then parse
            ist_time = normalize_to_ist(received_time)
            return datetime.fromisoformat(ist_time.replace('Z', '+00:00'))
        except:
            return datetime.min
    
    # Sort by datetime (oldest to newest)
    sorted_emails = sorted(emails, key=extract_datetime)
    
    # Update received_date_time to IST for all emails
    for email in sorted_emails:
        if 'received_date_time' in email:
            email['received_date_time'] = normalize_to_ist(email['received_date_time'])
    
    return sorted_emails


def is_client_domain(from_email: str, known_client_domains: set[str]) -> bool:
    """
    Check if email is from a known client domain
    """
    if not from_email:
        return False
    
    domain = from_email.split('@')[-1].lower() if '@' in from_email else ''
    return domain in known_client_domains


# Legacy function for backward compatibility - now implements zero-skip
def apply_email_filter(
    *,
    subject: str,
    body: str,
    has_attachments: bool,
    from_email: str = "",
    min_body_chars: int = 50,
    received_date_time: str = "",
) -> FilterResult:
    """
    Legacy wrapper - implements zero-skip policy
    All client emails pass through to AI parser
    """
    
    # Known client domains (should be moved to config)
    known_client_domains = {
        'ltts.com',
        'iexcel.co.in',
        'idexcel.com',
        'kpmg.com',
        'itcinfotech.com', 
        'metaforgeit.com',
        'otter.ai',
        'viazohocrm.in',
    }
    
    is_client = is_client_domain(from_email, known_client_domains)
    
    return apply_zero_skip_filter(
        subject=subject,
        body=body,
        has_attachments=has_attachments,
        from_email=from_email,
        received_date_time=received_date_time,
        is_client_domain=is_client
    )
