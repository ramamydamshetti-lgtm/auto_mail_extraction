"""
Normalize email body: strip HTML, collapse whitespace, light signature trimming.
"""

from __future__ import annotations

import re
from html import unescape

from bs4 import BeautifulSoup


_SIG_SPLIT = re.compile(
    r"(?m)^(?:--\s*[-—]|_{3,}|Sent from my |Get Outlook for |Regards,\s*$)",
)

_FWD_FROM_LINE = re.compile(r"(?m)^\s*From:\s*$")
_CONFIDENTIAL_BLOCK = re.compile(
    r"(?is)IMPORTANT/CONFIDENTIAL:.*?$|This message.*?strictly prohibited\..*?$",
)
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
_PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?\d{1,3}[\s\-]?)?(?:\(?\d{3}\)?[\s\-]?)?\d{3}[\s\-]?\d{4}(?!\d)"
)


def html_to_plain(html: str) -> str:
    if not html or not html.strip():
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    text = unescape(text)
    lines = [ln.strip() for ln in text.splitlines()]
    out = "\n".join(ln for ln in lines if ln)
    return re.sub(r"\n{3,}", "\n\n", out).strip()


def strip_signature_heuristic(text: str) -> str:
    if not text:
        return ""
    t = text.strip()

    # If this is a forwarded/replied thread, keep the actual forwarded content
    # and drop the short intro/signature above it.
    fm = _FWD_FROM_LINE.search(t)
    if fm and fm.start() > 0:
        before = t[: fm.start()].strip()
        after = t[fm.start() :].strip()
        # Heuristic: if the part before "From:" is short (FYI/Thanks/Regards + signature),
        # prefer the forwarded content.
        if len(before) < 400 or before.lower().startswith(("fyi", "thanks", "please see")):
            t = after

    # Remove common long confidentiality/disclaimer blocks (keep the rest).
    t = _CONFIDENTIAL_BLOCK.sub("", t).strip()

    m = _SIG_SPLIT.search(t)
    if m:
        return t[: m.start()].strip()
    return t.strip()


def scrub_pii(text: str) -> str:
    """
    Redact personal emails and phone numbers before sending content to external AI APIs.
    """
    if not text:
        return ""
    redacted = _EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    redacted = _PHONE_RE.sub("[REDACTED_PHONE]", redacted)
    return redacted


def normalize_body(plain: str | None, html: str | None) -> str:
    """Prefer plain text; if missing, derive from HTML; then trim signature noise."""
    p = (plain or "").strip()
    if not p and html:
        p = html_to_plain(html)
    return strip_signature_heuristic(p)
