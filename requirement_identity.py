"""
Requirement Identity Engine.
Universal requirement identity computation ensuring every requirement is stored ONCE.

Identity Rules:
- With a genuine client ID: identity = f"{normalized_client}:{normalized_client_id}"
- Without a client ID: identity = f"{normalized_client}:{content_hash}"
  where content_hash = sha256(normalized_title | normalized_location | normalized_experience | normalized_mandatory_skills)
  No time window is applied (permanent deduplication).
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Iterable


def normalize_identity_text(text: Any) -> str:
    """Normalize text by lowercasing, stripping punctuation, and collapsing whitespace."""
    if text is None:
        return ""
    if isinstance(text, (list, tuple, set)):
        items = [normalize_identity_text(x) for x in text if x is not None]
        items = [x for x in items if x]
        items.sort()
        return " ".join(items)
    
    s = str(text).strip().lower()
    # Normalize unicode hyphens/spaces
    s = re.sub(r"[\s\-_–—/]+", " ", s)
    # Remove non-alphanumeric except spaces
    s = re.sub(r"[^\w\s]", "", s)
    # Collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s


def normalize_client_key(client: str | None) -> str:
    """Normalize client name to a stable canonical key."""
    raw = normalize_identity_text(client or "unknown")
    if not raw or raw in ("none", "null", "unknown", "unresolved"):
        return "unknown"
    if "accenture" in raw:
        return "accenture"
    if "ltts" in raw or "l t technology" in raw:
        return "ltts"
    if "itc" in raw:
        return "itc"
    if "deloitte" in raw:
        return "deloitte"
    if "pwc" in raw or "pricewaterhouse" in raw:
        return "pwc"
    if "kpmg" in raw:
        return "kpmg"
    if "ust" in raw:
        return "ust"
    if "qbrainx" in raw:
        return "qbrainx"
    if "brillio" in raw:
        return "brillio"
    if "happiest" in raw:
        return "happiest_minds"
    if "metaforge" in raw:
        return "metaforge"
    return re.sub(r"\s+", "_", raw)


def clean_client_jd_id(client_jd_id: Any, client: str | None = None, context: Any = None) -> str | None:
    """
    Return clean genuine client-provided requirement ID, or None if missing, fabricated, or invalid.
    Uses central validator is_genuine_client_id (C1, C2).
    """
    from client_identity_validator import is_genuine_client_id

    is_val, clean_id, _ = is_genuine_client_id(client, client_jd_id, context=context)
    return clean_id if is_val else None


def compute_requirement_identity(
    client: str | None,
    client_jd_id: str | None = None,
    job_title: str | None = None,
    location: Any = None,
    experience: Any = None,
    mandatory_skills: Any = None,
    context: Any = None,
) -> str:
    """
    Compute stable, permanent requirement identity.
    
    1. With genuine client ID: (client, normalized client ID)
    2. Without client ID: (client, hash(normalized job title, location, experience, mandatory skills))
    """
    c_key = normalize_client_key(client)
    cjd = clean_client_jd_id(client_jd_id, client=c_key, context=context)
    
    if cjd:
        return f"{c_key}:cjd:{cjd}"
    
    # Content hash
    t = normalize_identity_text(job_title)
    l = normalize_identity_text(location)
    e = normalize_identity_text(experience)
    m = normalize_identity_text(mandatory_skills)
    
    content_raw = f"{t}|{l}|{e}|{m}"
    content_hash = hashlib.sha256(content_raw.encode("utf-8")).hexdigest()[:16]
    return f"{c_key}:hash:{content_hash}"
