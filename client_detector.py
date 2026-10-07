"""
Detect known recruitment clients from subject, body, and sender metadata.
Includes word-boundary regex marker resolution (D-Client -> Deloitte, P-Client -> PwC) for idexcel.com.
Unidentified idexcel.com emails resolve to "unresolved" (key: "idexcel_unresolved").
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

# Canonical keys and display names; search uses normalized lowercase text.
_CLIENT_SPECS: list[tuple[str, str, tuple[str, ...]]] = [
    ("itc", "ITC", ("itc", "itc limited", "itc ltd")),
    ("kpmg", "KPMG", ("kpmg",)),
    ("ust", "UST", ("ust global", "ust")),
    ("ltts", "LTTS", ("ltts", "l&t technology", "l and t technology")),
    ("accenture", "Accenture", ("accenture",)),
    ("pwc", "PwC", ("pwc", "pricewaterhouse", "pricewaterhousecoopers")),
    ("deloitte", "Deloitte", ("deloitte",)),
    ("qbrainx", "QBrainX", ("qbrainx", "q brainx", "qbrain x")),
    ("brillio", "Brillio", ("brillio",)),
    ("happiest_minds", "Happiest Minds", ("happiest minds", "happiestminds")),
    ("metaforge", "Metaforge (Internal)", ("metaforge", "meta forge", "metaforgeit")),
]


@dataclass(frozen=True)
class ClientMatch:
    """Result of client detection."""

    key: str
    display_name: str


def load_pipeline_rules() -> dict:
    rules_path = Path(__file__).resolve().parent / "config" / "pipeline_rules.json"
    if rules_path.exists():
        try:
            with open(rules_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def strip_reply_history(body: str) -> str:
    """
    Remove quoted email reply/forward history so markers in previous email threads are ignored.
    """
    if not body:
        return ""
    lines = body.splitlines()
    cut_idx = len(lines)
    patterns = [
        r"(?im)^\s*---+\s*$",
        r"(?im)^\s*From\s*:.*$",
        r"(?im)^\s*Subject\s*:.*$",
        r"(?im)^\s*Sent\s*:.*$",
        r"(?im)^\s*--------\s*Original Message\s*--------.*$",
        r"(?im)^\s*On\s+.*?\s+wrote\s*:.*$",
    ]
    for idx, line in enumerate(lines):
        for pat in patterns:
            if re.match(pat, line):
                cut_idx = min(cut_idx, idx)
                break
        if cut_idx < len(lines):
            break
    return "\n".join(lines[:cut_idx])


def find_idexcel_client_matches(text: str) -> list[tuple[str, str, int]]:
    """
    Find all D-Client and P-Client regex matches in search text.
    Returns list of tuples: (client_key, client_display_name, char_index)
    Loaded from config/pipeline_rules.json.
    """
    if not text:
        return []
    rules = load_pipeline_rules()
    idexcel_rules = rules.get("ambiguous_domain_markers", {}).get("idexcel.com", [])

    matches: list[tuple[str, str, int]] = []
    for item in idexcel_rules:
        client_name = item.get("client", "")
        client_key = item.get("key", client_name.lower().replace(" ", "_"))
        patterns = item.get("patterns", [])
        if not patterns and item.get("marker"):
            m_str = re.escape(str(item["marker"]))
            patterns = [rf"\b{m_str}\b"]
        for pat in patterns:
            try:
                for m in re.finditer(pat, text, flags=re.IGNORECASE):
                    matches.append((client_key, client_name, m.start()))
            except Exception:
                continue

    matches.sort(key=lambda x: x[2])
    return matches


def resolve_idexcel_client_for_requirement(
    subject: str,
    body: str,
    requirement_text: str = "",
    role_index: int = 0,
) -> tuple[ClientMatch, str | None]:
    """
    Per-requirement client resolution for idexcel.com emails (Rules 3, 4, 5).

    Returns (ClientMatch, processing_note_or_none)
    """
    clean_body = strip_reply_history(body)
    search_text = (subject or "") + "\n" + (clean_body or "")

    email_matches = find_idexcel_client_matches(search_text)
    distinct_email_keys = set(m[0] for m in email_matches)

    rules = load_pipeline_rules()
    unres_cfg = rules.get("unresolved_idexcel_client", {})
    unres_match = ClientMatch(
        key=unres_cfg.get("key", "idexcel_unresolved"),
        display_name=unres_cfg.get("display_name", "unresolved"),
    )

    # Case 1: No tags at all in email (Rule 5)
    if not email_matches:
        note = "Missing D-Client / P-Client tag for idexcel.com requirement. Flagged for review."
        return unres_match, note

    # Case 2: Exactly one distinct tag type in entire email (e.g. all Deloitte or all PwC)
    if len(distinct_email_keys) == 1:
        first = email_matches[0]
        return ClientMatch(key=first[0], display_name=first[1]), None

    # Case 3: Multiple distinct tags in email (both Deloitte and PwC)
    # 1. Check if requirement_text itself has a direct tag match
    req_matches = find_idexcel_client_matches(requirement_text) if requirement_text else []
    distinct_req_keys = set(m[0] for m in req_matches)
    if len(distinct_req_keys) == 1:
        first = req_matches[0]
        return ClientMatch(key=first[0], display_name=first[1]), None
    elif len(distinct_req_keys) > 1:
        note = "Ambiguous D-Client / P-Client tags found in email. Flagged for review."
        return unres_match, note

    # 2. Check nearest tag above role position in search_text
    if requirement_text:
        req_sub = requirement_text.strip()[:60].lower()
        pos = search_text.lower().find(req_sub)
        if pos != -1:
            tags_above = [m for m in email_matches if m[2] <= pos + len(req_sub)]
            if tags_above:
                nearest_tag = tags_above[-1]
                # Check line containing nearest_tag for inline conflicts
                line_start = search_text.rfind("\n", 0, nearest_tag[2])
                line_start = 0 if line_start == -1 else line_start + 1
                line_end = search_text.find("\n", nearest_tag[2])
                line_end = len(search_text) if line_end == -1 else line_end
                tag_line = search_text[line_start:line_end]

                line_matches = find_idexcel_client_matches(tag_line)
                if len(set(m[0] for m in line_matches)) > 1:
                    note = "Ambiguous D-Client / P-Client tags found in email. Flagged for review."
                    return unres_match, note

                return ClientMatch(key=nearest_tag[0], display_name=nearest_tag[1]), None

    # Cannot resolve unambiguously (Conflict - Rule 4)
    note = "Ambiguous D-Client / P-Client tags found in email. Flagged for review."
    return unres_match, note


def detect_client(subject: str, body: str, from_email: str) -> ClientMatch | None:
    """
    Identify a supported client from email content using generic rules from config/pipeline_rules.json.
    Handles domain mapping and regex marker resolution (D-Client -> Deloitte, P-Client -> PwC for idexcel.com).
    """
    sender = (from_email or "").strip().lower()
    domain = sender.split("@", 1)[1] if "@" in sender else ""

    clean_body = strip_reply_history(body)
    search_text = (subject or "") + "\n" + (clean_body or "")

    rules = load_pipeline_rules()
    allowed_domains = set(rules.get("allowed_domains", []))
    domain_map = rules.get("domain_client_mapping", {})
    ambiguous_markers = rules.get("ambiguous_domain_markers", {})

    if domain in allowed_domains or domain in ambiguous_markers or domain in domain_map:
        if domain == "idexcel.com" or domain in ambiguous_markers:
            matches = find_idexcel_client_matches(search_text)
            distinct_keys = set(m[0] for m in matches)
            if len(distinct_keys) == 1:
                single_match = matches[0]
                return ClientMatch(key=single_match[0], display_name=single_match[1])
            else:
                unres = rules.get("unresolved_idexcel_client", {})
                return ClientMatch(
                    key=unres.get("key", "idexcel_unresolved"),
                    display_name=unres.get("display_name", "unresolved"),
                )

        # If text explicitly names a supported client, prioritize that over generic domain defaults
        blob = search_text.lower()
        for key, display, needles in _CLIENT_SPECS:
            for n in needles:
                n = n.strip()
                if len(n) > 4 and n in blob:
                    return ClientMatch(key=key, display_name=display)
                elif len(n) <= 4 and re.search(rf"\b{re.escape(n)}\b", blob):
                    return ClientMatch(key=key, display_name=display)

        if domain in domain_map:
            c_name = domain_map[domain]
            return ClientMatch(
                key=c_name.lower().replace(" ", "_"),
                display_name=c_name,
            )

        def_name = domain.split(".", 1)[0].capitalize()
        return ClientMatch(key=def_name.lower(), display_name=def_name)

    # Secondary: match specs over search_text + sender
    blob = search_text.lower() + "\n" + sender
    ranked: list[tuple[str, str, str]] = []
    for key, display, needles in _CLIENT_SPECS:
        for n in needles:
            ranked.append((key, display, n))
    ranked.sort(key=lambda x: len(x[2]), reverse=True)

    seen_keys: set[str] = set()
    for key, display, needle in ranked:
        if key in seen_keys:
            continue
        n = needle.strip()
        if n and len(n) > 4 and n in blob:
            return ClientMatch(key=key, display_name=display)

    for key, display, needles in _CLIENT_SPECS:
        for n in needles:
            n = n.strip()
            if len(n) <= 4 and re.search(rf"\b{re.escape(n)}\b", blob):
                return ClientMatch(key=key, display_name=display)

    if domain and "metaforgeit.com" not in domain:
        return ClientMatch(key="other", display_name="Other")

    return None

