"""
Heuristic structured extraction from heterogeneous client requirement emails.
Works without LLM: vendor from domain, locations, bullets, experience hints, KPMG-style table.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Set

# Known client / internal domains → display label (extend as needed)
VENDOR_BY_DOMAIN: dict[str, str] = {
    "kpmg.com": "KPMG",
    "accenture.com": "Accenture",
    "happiestminds.com": "Happiest Minds",
    "ltts.com": "LTTS",
    "lnttechservices.com": "LTTS",
    "itc.in": "ITC",
    "itcportal.com": "ITC",
    "itcinfotech.com": "ITC",
    "brillio.com": "Brillio",
    "metaforgeit.com": "Metaforge",
    "qbrainx.com": "QBrainX",
    "qbruenax.com": "Qbruenax",
    "e.read.ai": "Read AI",
}

_LOC_PATTERNS = [
    re.compile(r"(?i)\bLocation(?:s)?\s*(?:for\s+(?:the\s+)?(?:all\s+)?roles\s*)?[:\-]\s*(.+)$"),
    re.compile(r"(?i)\bPreferred\s+location(?:s)?\s*[:\-]\s*(.+)$"),
    re.compile(r"(?i)\bJob\s+location(?:s)?\s*[:\-]\s*(.+)$"),
    re.compile(r"(?i)\bWork\s+location(?:s)?\s*[:\-]\s*(.+)$"),
]

_BULLET_LINE = re.compile(r"^\s*(?:[-*•●◦]|\d{1,3}[\.)])\s+(.+)$")

_EXP = re.compile(
    r"(?i)\b(\d{1,2}\s*[-–]\s*\d{1,2}\s*years?|\d{1,2}\s*\+\s*years?|"
    r"\d{1,2}\s*to\s*\d{1,2}\s*years?|GCB\s*\d|\d+\.?\d*\s*years?)\b"
)

_DISCLAIMER_START = re.compile(
    r"(?i)^(IMPORTANT/CONFIDENTIAL|DISCLAIMER|The information in this e-mail|KPMG \(in India\)|"
    r"This message from METAFORGE|strictly prohibited\.)"
)

_INVISIBLE_CHARS = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff\u00ad]")


def strip_invisible_chars(s: str) -> str:
    return _INVISIBLE_CHARS.sub("", s or "")


def merge_orphan_bullet_lines(lines: List[str]) -> List[str]:
    """Join lines where a bullet glyph sits alone on the previous line (common in HTML emails)."""
    out: List[str] = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        stripped = ln.strip()
        if re.match(r"^[\s•●◦]+\s*$", stripped) and i + 1 < len(lines):
            nxt = lines[i + 1].strip()
            if nxt:
                out.append("• " + nxt)
            i += 2
            continue
        out.append(ln)
        i += 1
    return out


def preprocess_for_structured(text: str) -> str:
    t = strip_invisible_chars(text or "")
    lines = t.splitlines()
    return "\n".join(merge_orphan_bullet_lines(lines))


def _domain_from_email(addr: str) -> str:
    a = (addr or "").strip().lower()
    if "@" not in a:
        return ""
    return a.split("@", 1)[1].strip()


def infer_vendor(from_email: str) -> dict[str, str]:
    dom = _domain_from_email(from_email)
    if not dom:
        return {"vendor_key": "unknown", "vendor_display": "Unknown", "sender_domain": ""}
    # Longest match / known map
    display = VENDOR_BY_DOMAIN.get(dom)
    if display:
        key = display.lower().replace(" ", "_")
        return {"vendor_key": key, "vendor_display": display, "sender_domain": dom}
    # Subdomain: mail.company.com
    parts = dom.split(".")
    if len(parts) >= 2:
        base = ".".join(parts[-2:])
        display = VENDOR_BY_DOMAIN.get(base)
        if display:
            key = display.lower().replace(" ", "_")
            return {"vendor_key": key, "vendor_display": display, "sender_domain": dom}
    key = re.sub(r"[^a-z0-9]+", "_", dom.split(".")[0] or "unknown").strip("_") or "unknown"
    return {
        "vendor_key": key,
        "vendor_display": dom,
        "sender_domain": dom,
    }


def _split_location_blob(blob: str) -> List[str]:
    blob = re.sub(r"\s+", " ", blob).strip(" .;")
    if not blob:
        return []
    parts = re.split(r"\s*/\s*|\s*,\s*|\s*\|\s*", blob)
    out: List[str] = []
    seen: Set[str] = set()
    for p in parts:
        s = p.strip(" .;")
        if len(s) < 2:
            continue
        if s.lower() not in seen:
            seen.add(s.lower())
            out.append(s)
    return out


def extract_locations(text: str) -> List[str]:
    seen: Set[str] = set()
    out: List[str] = []
    for ln in (text or "").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        for pat in _LOC_PATTERNS:
            m = pat.search(ln)
            if m:
                for loc in _split_location_blob(m.group(1)):
                    if loc.lower() not in seen:
                        seen.add(loc.lower())
                        out.append(loc)
    return out


def extract_bullet_points(text: str, *, max_items: int = 40) -> List[str]:
    out: List[str] = []
    for ln in (text or "").splitlines():
        ln = ln.strip()
        m = _BULLET_LINE.match(ln)
        if m:
            s = m.group(1).strip()
            if len(s) > 2 and s not in out:
                out.append(s)
        if len(out) >= max_items:
            break
    return out


def extract_experience_hints(text: str) -> List[str]:
    seen: Set[str] = set()
    out: List[str] = []
    for m in _EXP.finditer(text or ""):
        s = m.group(0).strip()
        if s.lower() not in seen:
            seen.add(s.lower())
            out.append(s)
    return out[:30]


def _trim_disclaimer_tail(text: str) -> str:
    lines = (text or "").splitlines()
    cut = len(lines)
    for i, ln in enumerate(lines):
        if _DISCLAIMER_START.search(ln.strip()):
            cut = min(cut, i)
            break
    return "\n".join(lines[:cut]).strip()


def first_summary(text: str, *, max_chars: int = 600) -> str:
    t = preprocess_for_structured(text)
    t = _trim_disclaimer_tail(t)
    t0 = t
    pf = re.search(r"(?is)Please find\b", t0)
    hi = re.search(r"(?im)^(?:Hi|Hello|Dear)\s+\S+", t0)
    if pf and pf.start() < 1800:
        t = t0[pf.start() :]
    elif hi and hi.start() < 4500:
        t = t0[hi.start() :]
    paras = [p.strip() for p in re.split(r"\n{2,}", t) if p.strip()]
    buf: List[str] = []
    n = 0
    for p in paras:
        pl = p.lower()
        if pl.startswith(("from:", "sent:", "to:", "cc:", "subject:", "importance:")):
            continue
        if pl.startswith("-----original message-----") or pl.startswith("begin forwarded message"):
            continue
        buf.append(p)
        n += len(p) + 2
        if n >= max_chars:
            break
    s = "\n\n".join(buf).strip()
    if not s:
        for ln in t.splitlines():
            low = ln.lower().strip()
            if not low or low.startswith(("from:", "sent:", "to:", "cc:", "subject:")):
                continue
            s = ln.strip()
            break
    if len(s) > max_chars:
        s = s[: max_chars - 1].rstrip() + "…"
    return s


def build_requirement_struct(
    *,
    subject: str,
    from_email: str,
    from_name: str,
    body_normalized: str,
    job_table: dict[str, Any] | None,
) -> dict[str, Any]:
    jt = job_table or {}
    locs_jt = jt.get("locations") if isinstance(jt, dict) else []
    roles = jt.get("roles") if isinstance(jt, dict) else []
    cand = jt.get("candidate_submissions") if isinstance(jt, dict) else []
    if not isinstance(cand, list):
        cand = []

    body = preprocess_for_structured(body_normalized)
    locs_body = extract_locations(body)
    merged_locs: List[str] = []
    seen: Set[str] = set()
    for src in (locs_jt if isinstance(locs_jt, list) else []), locs_body:
        for x in src:
            if not isinstance(x, str):
                continue
            k = x.strip()
            if not k:
                continue
            if k.lower() not in seen:
                seen.add(k.lower())
                merged_locs.append(k)

    vendor = infer_vendor(from_email)
    bullets = extract_bullet_points(body)
    exp = extract_experience_hints(body)

    for row in cand:
        if isinstance(row, dict):
            pl = row.get("preferred_location") or row.get("current_location")
            if isinstance(pl, str) and pl.strip() and pl.strip().lower() not in {x.lower() for x in merged_locs}:
                merged_locs.append(pl.strip())

    return {
        "source": {
            "vendor_key": vendor["vendor_key"],
            "vendor_display": vendor["vendor_display"],
            "sender_domain": vendor["sender_domain"],
            "sender_email": (from_email or "").strip(),
            "sender_name": (from_name or "").strip(),
        },
        "subject": (subject or "").strip(),
        "summary": first_summary(body_normalized),
        "locations": merged_locs,
        "key_points": bullets,
        "experience_mentions": exp,
        "roles_table": roles if isinstance(roles, list) else [],
        "candidate_submissions": cand,
        "parse": {
            "roles_table_rows": len(roles) if isinstance(roles, list) else 0,
            "candidate_submission_rows": len(cand),
            "key_points_count": len(bullets),
        },
    }
