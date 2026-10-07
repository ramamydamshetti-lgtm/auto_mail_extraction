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
    Status lifecycle keyword tracking removed.
    """
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
    Short-circuit action removed:
    All status lifecycle emails continue to the full LLM extraction and field mapping pipeline.
    """
    return "CONTINUE_PIPELINE", None
