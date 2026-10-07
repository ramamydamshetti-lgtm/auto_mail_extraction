"""
Deterministic status tracking rule engine for requirement intake (Part A).
Detects Hold / Reopen / Closed status keywords and executes thread-matching short-circuit
prior to LLM requirement classification.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from processed_store import ProcessedStore

_LOG = logging.getLogger(__name__)


def load_status_rules() -> dict:
    rules_path = Path(__file__).resolve().parent / "config" / "pipeline_rules.json"
    if rules_path.exists():
        try:
            with open(rules_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as err:
            _LOG.warning("Failed to load pipeline rules for status tracker: %s", err)
    return {}


def detect_status_keyword(subject: str, body: str) -> str | None:
    """
    Detect Hold / Stop Demand / Reopen / Closed status keywords from email subject and body.
    Returns: 'hold', 'closed', 'reopen', or None.
    """
    text = f"{subject or ''}\n{body or ''}".lower()
    if not text.strip():
        return None

    # Check for Reopen patterns first
    reopen_patterns = [
        r"\b(?:reopen(?:ed|ing)?|re-open(?:ed|ing)?)\b",
        r"\b(?:active\s+again|requirement\s+active\s+again)\b",
        r"\b(?:resume\s+(?:work|sharing\s+profiles|profile\s+submissions?|hiring))\b",
    ]
    for pat in reopen_patterns:
        if re.search(pat, text):
            return "reopen"

    # Check for Hold / Stop Demand patterns
    hold_patterns = [
        r"\b(?:pls\s+|please\s+)?stop\s+(?:working\s+on\s+|sharing\s+profiles\s+for\s+|sharing\s+profiles\s+on\s+|on\s+)?(?:this|below|the)?\s*(?:demand|requirement|role|position)\b",
        r"\b(?:stop\s+(?:profile\s+submissions?|sharing\s+profiles|candidate\s+submissions?))\b",
        r"\b(?:put\s+(?:this\s+requirement\s+|this\s+demand\s+|this\s+role\s+)?on\s+hold|keep\s+on\s+hold|placed\s+on\s+hold)\b",
        r"\b(?:hold\s+(?:profile\s+submissions?|sharing\s+profiles|this\s+requirement|this\s+demand|the\s+demand|the\s+requirement))\b",
        r"\b(?:don'?t\s+work\s+on\s+(?:below|this|the)\s+(?:requirement|demand))\b",
        r"\b(?:do\s+not\s+work\s+on\s+(?:below|this|the)\s+(?:requirement|demand))\b",
    ]
    for pat in hold_patterns:
        if re.search(pat, text):
            return "hold"

    # Contextual Hold pattern: if email is a reply/forward and explicitly asks for hold
    is_reply = bool(re.match(r"^\s*(?:re|fwd|fw)\s*:\s*", subject or "", re.IGNORECASE))
    if is_reply:
        if re.search(r"\b(?:put\s+on\s+hold|requirement\s+on\s+hold|demand\s+on\s+hold|on\s+hold|please\s+hold|kindly\s+hold)\b", text):
            return "hold"

    # Check for Closed patterns
    closed_patterns = [
        r"\b(?:close\s+(?:this\s+)?(?:demand|requirement|role|position))\b",
        r"\b(?:requirement\s+closed|demand\s+closed|position\s+filled|opening\s+closed)\b",
        r"\b(?:demand\s+cancelled|requirement\s+cancelled)\b",
    ]
    for pat in closed_patterns:
        if re.search(pat, text):
            return "closed"

    if is_reply and re.search(r"\b(?:close|closed)\b", text):
        if re.search(r"\b(?:is\s+closed|has\s+been\s+closed|please\s+close|kindly\s+close)\b", text):
            return "closed"

    return None


def extract_req_ids_from_text(subject: str, body: str) -> list[str]:
    """Extract explicit requirement IDs (e.g. 203483-1, REQ-10293, DLTJP00062540, RQ056293) from text."""
    text = f"{subject or ''}\n{body or ''}"
    if not text.strip():
        return []
    ids: list[str] = []
    # Pattern 1: Explicit labels
    for m in re.finditer(
        r"(?i)\b(?:Request[\-\s]?ID|Req[\-\s]?ID|Demand[\-\s]?ID|Job[\-\s]?Posting[\-\s]?ID|Job[\-\s]?ID|Ref[\-\s]?ID|Requirement[\-\s]?ID|Requisition[\-\s]?ID)\s*[:=\-#]?\s*([A-Za-z0-9_\-]+)",
        text,
    ):
        v = m.group(1).strip()
        if len(v) >= 3 and v not in ids and not v.lower().startswith(("the", "for", "and", "http", "null", "none")):
            ids.append(v)
    # Pattern 2: Specific ID formats (DLTJP..., RQ..., REQ-..., 203483-1, etc.)
    for pat in (r"\b(DLTJP\d{5,10})\b", r"\b(RQ\d{5,8})\b", r"\b(REQ-\d{4,8})\b", r"\b(\d{5,7}-\d{1,2})\b"):
        for m in re.finditer(pat, text, re.I):
            v = m.group(1).strip()
            if v not in ids:
                ids.append(v)
    return ids


from email_filter import is_sender_allowlisted
from client_detector import detect_client


def is_multi_requirement_digest(subject: str, body: str) -> bool:
    """
    Generic structural detection for multi-requirement digest/table emails across all clients.
    Detects HTML <table> elements, pipe-delimited table rows, header patterns, and multi-row demand structures.
    """
    text = f"{subject or ''}\n{body or ''}".lower()
    
    # Structural Check 1: HTML table elements
    if "<table" in text and ("<tr" in text or "<td" in text):
        return True

    # Structural Check 2: Pipe-delimited multi-column table headers or rows (| col1 | col2 |)
    pipe_rows = [line for line in text.splitlines() if line.count("|") >= 2]
    if len(pipe_rows) >= 2:
        return True

    # Structural Check 3: Header rows containing key tabular column headers
    header_rx = re.compile(
        r"\b(?:sr\.?\s*no|req\s*id|job\s*id|so\s*#?|role|position|designation)\b.*?\b(?:skills?|location|status|experience)\b",
        re.I,
    )
    if header_rx.search(text):
        return True

    # Structural Check 4: Multiple explicit Req ID patterns (e.g. ACC-1234, REQ-5678, SO# 000123)
    req_id_matches = re.findall(r"\b(?:req|acc|so|jd)[\s\-_]?:?\s*#?\d{4,8}\b", text, re.I)
    if len(set(req_id_matches)) >= 2:
        return True

    # Structural Check 5: Phrase markers fallback
    digest_markers = [
        "daily open requirements",
        "open demands",
        "requirements snapshot",
        "demands snapshot",
        "open requirements snapshot",
        "daily demands",
        "tracker report",
    ]
    return any(m in text for m in digest_markers)


def evaluate_status_short_circuit(
    *,
    subject: str,
    body: str,
    conversation_id: str,
    graph_id: str,
    store: ProcessedStore,
    from_email: str = "",
) -> tuple[str, str | None]:
    """
    Deterministic status tracking rule engine.
    Detects Stop Demand / Hold / Reopen / Closed status keywords and updates existing requirement
    without creating a duplicate or new requirement record.
    """
    if from_email and not is_sender_allowlisted(from_email):
        return "SENDER_BLOCKED", None

    if is_multi_requirement_digest(subject, body):
        return "CONTINUE_PIPELINE", None

    status_kw = detect_status_keyword(subject, body)
    if not status_kw:
        return "CONTINUE_PIPELINE", None

    # Status keyword detected! Find existing matching requirement.
    target_id: str | None = None
    target_payload: dict | None = None

    # 1. Search explicit Requirement IDs from subject/body
    req_ids = extract_req_ids_from_text(subject, body)
    for rid in req_ids:
        found = store.find_requirement_by_req_id(rid)
        if found:
            target_id, target_payload = found
            break

    # 2. Search by conversation_id / thread
    if not target_id and conversation_id:
        found = store.find_requirement_by_conversation_id(conversation_id)
        if found:
            target_id, target_payload = found

    # 3. Search by normalized subject match (stripping RE:/FW:)
    if not target_id and subject:
        found = store.find_requirement_by_subject(subject)
        if found:
            target_id, target_payload = found

    # 4. Search by client + role title
    if not target_id:
        client_match = detect_client(subject, body, from_email) if from_email else None
        client_name = client_match.display_name if client_match else ""
        if client_name:
            found = store.find_requirement_by_client_and_title(client_name, subject)
            if found:
                target_id, target_payload = found

    norm_status = status_kw

    if target_id:
        store.update_requirement_status(
            requirement_id=target_id,
            new_status=norm_status,
            source_email_id=graph_id,
            changed_by="RULE_ENGINE",
        )
        return "STATUS_UPDATED", target_id

    # If status keyword was found but no thread / existing requirement could be matched
    if conversation_id:
        return "PENDING_REVIEW_NO_THREAD", None
    return "STOP_UNMATCHED", None
