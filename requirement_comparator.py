"""
Requirement Comparator & Whole-Requirement Duplicate Detection Engine.

Implements rules W1-W7:
- W1: Whole-requirement comparison (title, skills, experience range, whole text, other fields).
- W2: Requirement Profile construction with normalized structured fields + cleaned text block & fingerprint.
- W3: Hard rules:
      * Same client + same client ID -> DUPLICATE.
      * Both have client ID and IDs differ -> NOT a duplicate.
      * Cities differ -> NOT a duplicate.
      * Different clients -> NOT a duplicate.
- W4: Similarity score 0-1 (title 0.25, skills 0.25, exp range 0.15, text 0.25, other fields 0.10).
      Weights re-scaled when fields are missing.
      score >= 0.85 -> DUPLICATE.
      0.70 <= score < 0.85 -> POSSIBLE duplicate (routed to review).
      below 0.70 -> new requirement.
- W5: Candidate set: same client and city.
- W6: Intra-email deduplication: collapse identical groups.
- W7: Duplicate decisions update times_seen and last_seen without editing stored details;
      status phrases update status; all decisions are logged.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import logging
import re
from typing import Any

from requirement_identity import clean_client_jd_id, normalize_client_key, normalize_identity_text

_LOG = logging.getLogger(__name__)

# Default weights and thresholds (overridden by config/pipeline_rules.json if present)
DEFAULT_WEIGHTS = {
    "title": 0.25,
    "skills": 0.25,
    "experience": 0.15,
    "whole_text": 0.25,
    "other_fields": 0.10,
}

DEFAULT_THRESHOLDS = {
    "duplicate": 0.85,
    "possible_duplicate": 0.70,
}

# Canonical city mapping
_CITY_PATTERNS = [
    (r"\b(?:bengaluru|bangalore|electronic\s*city|whitefield|manyata|bdc\d*\w*)\b", "bangalore"),
    (r"\b(?:mumbai|bombay|navi\s*mumbai|thane|airoli|mdc(?:-\d+|\d*\w*))\b", "mumbai"),
    (r"\b(?:pune|hinjewadi|magarpatta|pdc\d*\w*)\b", "pune"),
    (r"\b(?:hyderabad|secunderabad|gachibowli|madhapur|hitec\s*city|hdc\d*\w*)\b", "hyderabad"),
    (r"\b(?:chennai|madras|sholinganallur|omr|t\s*nagar|cdc\d*\w*)\b", "chennai"),
    (r"\b(?:gurgaon|gurugram|cyber\s*city|ddc\d*\w*)\b", "gurgaon"),
    (r"\b(?:noida|greater\s*noida)\b", "noida"),
    (r"\b(?:mysore|mysuru)\b", "mysore"),
    (r"\b(?:kolkata|calcutta|kdc\d*\w*)\b", "kolkata"),
    (r"\b(?:delhi|new\s*delhi|ncr)\b", "delhi"),
    (r"\b(?:coimbatore)\b", "coimbatore"),
    (r"\b(?:kochi|cochin)\b", "kochi"),
    (r"\b(?:chandigarh|mohali)\b", "chandigarh"),
    (r"\b(?:ahmedabad)\b", "ahmedabad"),
    (r"\b(?:trivandrum|thiruvananthapuram)\b", "trivandrum"),
    (r"\b(?:bhubaneswar)\b", "bhubaneswar"),
    (r"\b(?:indore)\b", "indore"),
    (r"\b(?:jaipur)\b", "jaipur"),
]


def normalize_city(location: Any) -> str | None:
    """Canonicalize city string or return None if unspecified/missing."""
    if not location:
        return None
    if isinstance(location, (list, tuple, set)):
        items = [normalize_city(x) for x in location if x]
        valid_items = [x for x in items if x]
        return valid_items[0] if valid_items else None

    raw = str(location).strip().lower()
    if (
        not raw
        or raw.isdigit()
        or raw in ("none", "null", "n/a", "not provided", "unknown", "pan india", "remote", "client location", "client site", "client office")
        or re.search(r"\b(?:any\s+(?:\w+\s+)?(?:location|office)|client\s+(?:location|site|office)|pan\s+india)\b", raw)
    ):
        return None

    for pattern, canonical in _CITY_PATTERNS:
        if re.search(pattern, raw, re.IGNORECASE):
            return canonical

    return None


def clean_requirement_text(text: str) -> str:
    """
    Clean the requirement's text block from email (W2):
    lowercase, quoted replies, signatures, greetings, dates, phone numbers and emails removed,
    whitespace collapsed.
    """
    if not text:
        return ""

    s = str(text)

    # 1. Remove quoted reply blocks (lines starting with > or header lines)
    lines = []
    in_quote_block = False
    for line in s.splitlines():
        trimmed = line.strip()
        if trimmed.startswith(">"):
            continue
        if re.match(
            r"^(?:on\s+.+wrote:|from:\s*.+|sent:\s*.+|-----original message-----|subject:\s*.+)",
            trimmed,
            re.IGNORECASE,
        ):
            in_quote_block = True
            continue
        if not in_quote_block:
            lines.append(line)
    s = "\n".join(lines)

    # 2. Remove greetings at the beginning
    s = re.sub(
        r"^(?:\s*(?:hi|hello|dear|good\s+morning|good\s+afternoon|good\s+evening|team)[\s\w,.-]*\n+)+",
        "",
        s,
        flags=re.IGNORECASE,
    )

    # 3. Remove signatures at the end
    s = re.sub(
        r"\n+\s*(?:thanks\s*&?\s*regards|thanks\s+and\s+regards|best\s+regards|warm\s+regards|regards|sincerely|cheers|thanks)[\s\S]*$",
        "",
        s,
        flags=re.IGNORECASE,
    )

    # 4. Remove dates
    s = re.sub(
        r"\b(?:\d{1,4}[-/]\d{1,2}[-/]\d{2,4}|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})\b",
        " ",
        s,
        flags=re.IGNORECASE,
    )

    # 5. Remove phone numbers
    s = re.sub(
        r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}\b",
        " ",
        s,
    )

    # 6. Remove emails
    s = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", " ", s)

    # 7. Remove web URLs
    s = re.sub(r"https?://\S+", " ", s)

    # 8. Collapse whitespace and lowercase
    cleaned = re.sub(r"\s+", " ", s).strip().lower()
    return cleaned


def compute_text_fingerprint(cleaned_text: str) -> str:
    """Compute 16-char SHA256 hex digest of cleaned requirement text."""
    if not cleaned_text:
        return ""
    return hashlib.sha256(cleaned_text.encode("utf-8")).hexdigest()[:16]


def parse_experience_range(exp_val: Any) -> tuple[float | None, float | None]:
    """Parse experience text into (min_years, max_years)."""
    if exp_val is None:
        return (None, None)
    if isinstance(exp_val, (tuple, list)) and len(exp_val) >= 2:
        try:
            mn = float(exp_val[0]) if exp_val[0] is not None else None
            mx = float(exp_val[1]) if exp_val[1] is not None else None
            return (mn, mx)
        except (ValueError, TypeError):
            return (None, None)

    s = str(exp_val).strip()
    if not s or s.lower() in ("none", "null", "n/a", "unknown"):
        return (None, None)

    # Range pattern: e.g. "5-7 yrs", "5 to 8 years", "5 - 7.5", "5 – 8 years"
    m_range = re.search(r"(\d+(?:\.\d+)?)\s*(?:[-–—~]|to)\s*(\d+(?:\.\d+)?)", s, re.IGNORECASE)
    if m_range:
        try:
            return (float(m_range.group(1)), float(m_range.group(2)))
        except ValueError:
            pass

    # Open-ended plus pattern: e.g. "5+ years", "5+ yrs", "5 + years"
    m_plus = re.search(r"(\d+(?:\.\d+)?)\s*\+", s)
    if m_plus:
        try:
            return (float(m_plus.group(1)), None)
        except ValueError:
            pass

    # Single number: e.g. "5 years", "5 yrs"
    m_single = re.search(r"(\d+(?:\.\d+)?)\s*(?:yrs?|years?|\b)", s, re.IGNORECASE)
    if m_single:
        try:
            v = float(m_single.group(1))
            return (v, v)
        except ValueError:
            pass

    return (None, None)


def parse_skills_set(skills_val: Any) -> set[str]:
    """Normalize skills into a set of clean lowercase skill tokens."""
    if not skills_val:
        return set()

    raw_items: list[str] = []
    if isinstance(skills_val, (list, tuple, set)):
        for item in skills_val:
            if item:
                raw_items.extend(re.split(r"[,;/|•\n]+", str(item)))
    else:
        raw_items = re.split(r"[,;/|•\n]+", str(skills_val))

    normalized: set[str] = set()
    for token in raw_items:
        t = token.strip().lower()
        t = re.sub(r"^[^\w+]+|[^\w+]+$", "", t)
        if t and len(t) >= 2 and t not in ("skills", "mandatory", "required", "good to have", "n/a"):
            normalized.add(t)
    return normalized


def build_requirement_profile(payload: dict[str, Any], body_text: str = "") -> dict[str, Any]:
    """
    Build requirement profile (W2) for comparison and permanent storage:
    - client: normalized string
    - client_jd_id: clean genuine client ID (or None)
    - title: normalized title
    - city: normalized canonical city (or None)
    - experience_range: (min_years, max_years)
    - mandatory_skills: sorted list of normalized skills
    - additional_skills: sorted list of normalized skills
    - number_of_positions: int or None
    - work_mode: normalized work mode
    - employment_type: normalized employment type
    - budget: normalized budget string or None
    - cleaned_text: cleaned text block from email
    - text_fingerprint: SHA-256 fingerprint
    """
    client = normalize_client_key(
        payload.get("requirement_from")
        or payload.get("client_key")
        or payload.get("client")
    )
    cjd = clean_client_jd_id(payload.get("client_jd_id"))
    title = normalize_identity_text(payload.get("job_title"))
    city = normalize_city(payload.get("location"))

    exp_val = payload.get("overall_experience") or payload.get("experience")
    exp_range = parse_experience_range(exp_val)

    mand_skills = sorted(list(parse_skills_set(payload.get("mandatory_skills"))))
    add_skills = sorted(list(parse_skills_set(payload.get("skills"))))

    n_pos = payload.get("number_of_positions")
    try:
        n_pos = int(n_pos) if n_pos is not None else None
    except (ValueError, TypeError):
        n_pos = None

    wm = payload.get("work_mode")
    wm_str = str(wm).strip().lower() if wm else None

    emp = payload.get("employment_type")
    emp_str = str(emp).strip().lower() if emp else None

    budget = payload.get("yearly_budget") or payload.get("monthly_budget") or payload.get("budget")
    budget_str = str(budget).strip() if budget else None

    # Derive requirement text block
    raw_body = body_text or str(payload.get("bodyText") or payload.get("body") or "")
    if not raw_body:
        # Fallback to synthesizing a block from available text fields
        parts = [
            payload.get("job_title") or "",
            payload.get("location") or "",
            str(exp_val or ""),
            " ".join(mand_skills),
            " ".join(add_skills),
        ]
        raw_body = " ".join([p for p in parts if p])

    cleaned_text = clean_requirement_text(raw_body)
    fp = compute_text_fingerprint(cleaned_text)

    return {
        "client": client,
        "client_jd_id": cjd,
        "title": title,
        "city": city,
        "experience_range": exp_range,
        "mandatory_skills": mand_skills,
        "additional_skills": add_skills,
        "number_of_positions": n_pos,
        "work_mode": wm_str,
        "employment_type": emp_str,
        "budget": budget_str,
        "cleaned_text": cleaned_text,
        "text_fingerprint": fp,
    }


def _token_jaccard(s1: str, s2: str) -> float:
    t1 = set(s1.lower().split())
    t2 = set(s2.lower().split())
    if not t1 or not t2:
        return 0.0
    return len(t1 & t2) / len(t1 | t2)


def _compute_experience_overlap(
    r1: tuple[float | None, float | None],
    r2: tuple[float | None, float | None],
) -> float | None:
    min1, max1 = r1
    min2, max2 = r2
    if min1 is None and min2 is None:
        return None
    if min1 is None or min2 is None:
        return None

    # Treat open-ended range [min, None] as [min, max(min + 5.0, 15.0)]
    hi1 = max1 if max1 is not None else max(min1 + 5.0, 15.0)
    hi2 = max2 if max2 is not None else max(min2 + 5.0, 15.0)

    # Identical lower bound
    if abs(min1 - min2) < 0.01:
        return 1.0

    # Overlap interval [max(min1, min2), min(hi1, hi2)]
    overlap_start = max(min1, min2)
    overlap_end = min(hi1, hi2)

    if overlap_start <= overlap_end:
        overlap_len = overlap_end - overlap_start
        len1 = hi1 - min1
        len2 = hi2 - min2
        denom = min(len1, len2)
        if denom <= 0:
            return 1.0
        return min(1.0, (overlap_len + 1.0) / (denom + 1.0))

    # No overlap
    gap = overlap_start - overlap_end
    if gap <= 1.0:
        return 0.5
    return 0.0


def compare_requirements(
    profile1: dict[str, Any],
    profile2: dict[str, Any],
    rules_config: dict[str, Any] | None = None,
) -> tuple[str, float, str]:
    """
    Compare two requirement profiles (W3 & W4).

    Returns:
        (decision, score, deciding_rule)
        where decision in ("DUPLICATE", "POSSIBLE_DUPLICATE", "NOT_DUPLICATE")
    """
    cfg = rules_config or {}
    weights = cfg.get("similarity_weights") or DEFAULT_WEIGHTS
    thresholds = cfg.get("similarity_thresholds") or DEFAULT_THRESHOLDS
    dup_thresh = float(thresholds.get("duplicate", 0.85))
    poss_thresh = float(thresholds.get("possible_duplicate", 0.70))

    c1 = profile1.get("client")
    c2 = profile2.get("client")
    id1 = profile1.get("client_jd_id")
    id2 = profile2.get("client_jd_id")
    city1 = profile1.get("city")
    city2 = profile2.get("city")

    # --- W3: HARD RULES (Checked First) ---

    # Hard Rule 1: Different clients -> NOT a duplicate
    if c1 and c2 and c1 != c2:
        return ("NOT_DUPLICATE", 0.0, "HARD_RULE_DIFFERENT_CLIENTS")

    # Hard Rule 2: Same client and same client ID -> DUPLICATE (ID decides, content not needed)
    if c1 == c2 and id1 and id2 and id1 == id2:
        return ("DUPLICATE", 1.0, "HARD_RULE_SAME_CLIENT_AND_ID")

    # Hard Rule 3: Both have a client ID and IDs differ (including suffix 203421-1 vs 203421-2) -> NOT duplicate
    if c1 == c2 and id1 and id2 and id1 != id2:
        return ("NOT_DUPLICATE", 0.0, "HARD_RULE_CLIENT_IDS_DIFFER")

    # Hard Rule 4: Cities differ -> NOT a duplicate (same role in two cities = two requirements)
    # A missing value on either side never counts as a difference
    if city1 and city2 and city1 != city2:
        return ("NOT_DUPLICATE", 0.0, "HARD_RULE_CITIES_DIFFER")

    # --- W4: SIMILARITY SCORE COMPUTATION ---
    scores: dict[str, float] = {}

    # 1. Title Similarity (0.25)
    t1 = profile1.get("title") or ""
    t2 = profile2.get("title") or ""
    if t1 and t2:
        seq_ratio = difflib.SequenceMatcher(None, t1, t2).ratio()
        jacc = _token_jaccard(t1, t2)
        scores["title"] = max(seq_ratio, jacc)

    # 2. Skills Set Overlap (0.25)
    s1 = set(profile1.get("mandatory_skills") or []) | set(profile1.get("additional_skills") or [])
    s2 = set(profile2.get("mandatory_skills") or []) | set(profile2.get("additional_skills") or [])
    if s1 and s2:
        inter = len(s1 & s2)
        union = len(s1 | s2)
        skill_jacc = inter / union if union > 0 else 0.0
        # Word-level token fallback
        words1 = set(" ".join(s1).split())
        words2 = set(" ".join(s2).split())
        word_jacc = len(words1 & words2) / len(words1 | words2) if (words1 and words2) else 0.0
        scores["skills"] = max(skill_jacc, word_jacc)

    # 3. Experience Range Overlap (0.15)
    exp1 = profile1.get("experience_range") or (None, None)
    exp2 = profile2.get("experience_range") or (None, None)
    exp_ov = _compute_experience_overlap(exp1, exp2)
    if exp_ov is not None:
        scores["experience"] = exp_ov

    # 4. Whole-Text Similarity (0.25)
    txt1 = profile1.get("cleaned_text") or ""
    txt2 = profile2.get("cleaned_text") or ""
    if len(txt1) >= 15 and len(txt2) >= 15:
        # Check direct text fingerprint match
        fp1 = profile1.get("text_fingerprint")
        fp2 = profile2.get("text_fingerprint")
        if fp1 and fp2 and fp1 == fp2:
            scores["whole_text"] = 1.0
        else:
            txt_seq = difflib.SequenceMatcher(None, txt1, txt2).ratio()
            txt_jacc = _token_jaccard(txt1, txt2)
            scores["whole_text"] = max(txt_seq, txt_jacc)

    # 5. Other Fields Overlap (0.10) (positions, work_mode, employment_type, budget)
    other_sub_scores: list[float] = []
    p1, p2 = profile1.get("number_of_positions"), profile2.get("number_of_positions")
    if p1 is not None and p2 is not None:
        other_sub_scores.append(1.0 if p1 == p2 else min(p1, p2) / max(p1, p2))

    wm1, wm2 = profile1.get("work_mode"), profile2.get("work_mode")
    if wm1 and wm2:
        other_sub_scores.append(1.0 if wm1 == wm2 else 0.0)

    emp1, emp2 = profile1.get("employment_type"), profile2.get("employment_type")
    if emp1 and emp2:
        other_sub_scores.append(1.0 if emp1 == emp2 else 0.0)

    b1, b2 = profile1.get("budget"), profile2.get("budget")
    if b1 and b2:
        other_sub_scores.append(1.0 if b1 == b2 else 0.0)

    if other_sub_scores:
        scores["other_fields"] = sum(other_sub_scores) / len(other_sub_scores)

    # Re-scale weights for present fields
    active_weights: dict[str, float] = {}
    for k, s_val in scores.items():
        w = float(weights.get(k, DEFAULT_WEIGHTS.get(k, 0.10)))
        active_weights[k] = w

    sum_weights = sum(active_weights.values())
    if sum_weights <= 0.0:
        return ("NOT_DUPLICATE", 0.0, "NO_COMPARABLE_FIELDS")

    total_score = sum(active_weights[k] * scores[k] for k in active_weights) / sum_weights

    # Classify against thresholds
    if total_score >= dup_thresh:
        return ("DUPLICATE", round(total_score, 4), f"SIMILARITY_SCORE_{total_score:.2f}")
    if total_score >= poss_thresh:
        return ("POSSIBLE_DUPLICATE", round(total_score, 4), f"POSSIBLE_DUPLICATE_{total_score:.2f}")
    return ("NOT_DUPLICATE", round(total_score, 4), f"SIMILARITY_SCORE_{total_score:.2f}")
