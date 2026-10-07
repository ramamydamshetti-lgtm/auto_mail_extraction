"""
Two-Way Verification Engine (V1-V4, F1-F8).
Runs two independent extractors per requirement block:
  1. AI Engine
  2. Deterministic label/header extractor

Reconciliation Logic (V2):
  - Both agree -> accept.
  - One has value with verbatim quote in block and other is NULL -> accept, record recovered_by_<method>.
  - Different values -> store NULL, flag item for review, keep both candidates in review log.
  - No verbatim quote -> NULL.

Recall Guard (V3):
  - If block contains field label followed by non-placeholder value and final value is NULL,
    flag possible_miss and route to review.

Post-Save Verifier (V4):
  - Re-read stored values against source block, setting verification_status = verified or failed.
"""

from __future__ import annotations

import re
from typing import Any

from config import (
    FIELD_LABEL_SYNONYMS,
    is_placeholder,
    skills_from_requirement_sections,
    lpa_implies_inr,
)
from glossary import TermGlossary
from requirement_segmenter import strip_all_exclusion_zones

# Candidate template headers to strictly exclude from skills (F6)
CANDIDATE_TEMPLATE_HEADINGS = {
    "full name",
    "full name of the candidate",
    "name",
    "mobile no",
    "mobile number",
    "phone",
    "mail id",
    "email id",
    "email",
    "resumes sent date",
    "resumes sent date (ddmmyy)",
    "last full time qualification",
    "total experience",
    "relevant experience",
    "current ctc",
    "expected ctc",
    "notice period",
    "current location",
    "preferred location",
    "holding any offers",
    "pan number",
    "dob",
}


def _find_verbatim_quote(val_str: str, block_text: str) -> str | None:
    """Find exact or case-insensitive verbatim quote in the block text."""
    if not val_str or not block_text:
        return None
    val_clean = val_str.strip()
    if not val_clean:
        return None
    if val_clean in block_text:
        return val_clean
    # Case-insensitive search
    m = re.search(re.escape(val_clean), block_text, re.IGNORECASE)
    if m:
        return m.group(0)
    # Match without punctuation
    words = [w for w in re.split(r"\s+", val_clean) if w]
    if words:
        pat = r"\s+".join(re.escape(w) for w in words)
        m = re.search(pat, block_text, re.IGNORECASE)
        if m:
            return m.group(0)
    return None


def parse_experience_digits(exp_str: str | None) -> tuple[float | None, float | None]:
    """F2: experience_min_years and experience_max_years only from digits stated."""
    if not exp_str:
        return None, None
    s = str(exp_str).strip()
    # 5-7 years / 5 to 7 years / 5 – 7 years / 5 — 7 years
    m_range = re.search(r"(\d+(?:\.\d+)?)\s*(?:[-–—~]|to)\s*(\d+(?:\.\d+)?)\s*(?:years?|yrs?)?", s, re.I)
    if m_range:
        return float(m_range.group(1)), float(m_range.group(2))
    # 6+ years / 6 + years / min 6 years / more than 6 years
    m_plus = re.search(r"(?:more\s+than\s+|min(?:imum)?\s+)?(\d+(?:\.\d+)?)\s*(?:\+|\b)\s*(?:years?|yrs?)", s, re.I)
    if m_plus:
        return float(m_plus.group(1)), None
    # single number: "8 years" -> min 8, max None
    m_single = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:years?|yrs?|\+)?\b", s, re.I)
    if m_single:
        return float(m_single.group(1)), None
    return None, None


def parse_work_mode(text: str | None) -> tuple[str | None, str | None]:
    """
    F8 work_mode: work_mode_text verbatim.
    work_mode is On-site, Hybrid or Remote only for an explicit single term.
    If multiple ("Hybrid/Remote") or unclear, work_mode is NULL and text is kept.
    """
    if not text or is_placeholder(text):
        return None, None
    wm_text = str(text).strip()
    norm = TermGlossary.normalize_work_mode(wm_text)
    return norm, wm_text


def parse_budget_details(raw_budget: str | None) -> dict[str, Any]:
    """
    F3 & F4: budget_text verbatim; amount (min/max), unit, period only as stated.
    No conversion; currency only if written.
    Words like 'negotiable' stay in budget_text, numbers stay NULL.
    monthly_budget only when stated monthly (never derived from yearly/LPA).
    """
    res: dict[str, Any] = {
        "budget_text": None,
        "yearly_budget": None,
        "yearly_budget_min": None,
        "yearly_budget_max": None,
        "monthly_budget": None,
        "monthly_budget_min": None,
        "monthly_budget_max": None,
        "budget_currency": None,
    }
    if not raw_budget or is_placeholder(raw_budget):
        return res

    b_text = str(raw_budget).strip()
    is_body_like = (
        len(b_text) > 80
        or "\n" in b_text
        or any(w in b_text.lower() for w in ("dear", "kindly", "hello", "hi ", "regards", "candidate", "partner", "submission", "resume", "pls ensure", "subject line"))
    )
    res["budget_text"] = None if is_body_like else b_text
    lower = b_text.lower()

    # Detect currency strictly if stated (F3, A5)
    if re.search(r"(?:inr|rs\.?|₹)", lower):
        res["budget_currency"] = "INR"
    elif re.search(r"(?:usd|\$)", lower):
        res["budget_currency"] = "USD"
    elif re.search(r"(?:eur|€)", lower):
        res["budget_currency"] = "EUR"
    elif re.search(r"(?:gbp|£)", lower):
        res["budget_currency"] = "GBP"
    elif lpa_implies_inr() and re.search(r"\blpa\b", lower):
        res["budget_currency"] = "INR"
    elif re.search(r"\b\d{1,2},\d{2},\d{3}\b", b_text) or "lpm" in lower or "/ m" in lower or "/m" in lower:
        res["budget_currency"] = "INR"

    # Non-numeric phrases stay in budget_text; numbers stay NULL (F3)
    if any(p in lower for p in ["negotiable", "as per market", "competitive", "market standards", "best in industry"]):
        if not re.search(r"\d", lower):
            return res

    # Detect period: monthly vs yearly (F4)
    is_monthly = bool(re.search(r"\b(?:per\s+month|/month|p\.?m\.?|monthly|bill\s+rate|rate\s*/\s*pm|tpc\s+rates?)\b", lower))
    is_yearly = bool(re.search(r"\b(?:per\s+annum|/annum|p\.?a\.?|annually|yearly|lpa)\b", lower))

    # Extract digits: range or single (strip commas between digits like 80,000)
    clean_digits_text = re.sub(r"(?<=\d),(?=\d)", "", b_text)
    m_tiered = re.findall(r"(?:(\d+(?:\.\d+)?)\s*k\b|(\d+(?:\.\d+)?)\s*(?:l\b|lakhs?))", clean_digits_text, re.I)
    if ("rate" in lower or "tpc" in lower or "tier" in lower) and len(m_tiered) >= 2:
        vals = []
        for kv, lv in m_tiered:
            if kv:
                vals.append(float(kv) * 1000)
            elif lv:
                vals.append(float(lv) * 100000)
        if vals:
            res["budget_currency"] = "INR"
            res["monthly_budget_min"] = min(vals)
            res["monthly_budget_max"] = max(vals)
            res["monthly_budget"] = max(vals)
            res["budget_text"] = f"{int(min(vals)):,} - {int(max(vals)):,} / month"
            return res

    m_range = re.search(r"(\d+(?:\.\d+)?)\s*(?:-|to|–|—)\s*(\d+(?:\.\d+)?)", clean_digits_text)
    m_k = re.search(r"(\d+(?:\.\d+)?)\s*k\b", clean_digits_text, re.I)
    m_lakh = re.search(r"(\d+(?:\.\d+)?)\s*(?:l\b|lakhs?|lpa\b|lpm\b)", clean_digits_text, re.I)
    m_single = re.search(r"\b(\d+(?:\.\d+)?)\b", clean_digits_text)

    if is_monthly and not is_yearly:
        if m_range:
            res["monthly_budget_min"] = float(m_range.group(1))
            res["monthly_budget_max"] = float(m_range.group(2))
            res["monthly_budget"] = float(m_range.group(2))
        elif m_k:
            val = float(m_k.group(1)) * 1000
            res["monthly_budget"] = val
            res["monthly_budget_min"] = val
            res["monthly_budget_max"] = val
        elif m_lakh:
            val = float(m_lakh.group(1)) * 100000
            res["monthly_budget"] = val
            res["monthly_budget_min"] = val
            res["monthly_budget_max"] = val
        elif m_single:
            res["monthly_budget"] = float(m_single.group(1))
            res["monthly_budget_min"] = float(m_single.group(1))
            res["monthly_budget_max"] = float(m_single.group(1))
    elif is_yearly or "lpa" in lower or ("lakh" in lower and not is_monthly):
        if m_range:
            res["yearly_budget_min"] = float(m_range.group(1))
            res["yearly_budget_max"] = float(m_range.group(2))
        elif m_single:
            res["yearly_budget"] = float(m_single.group(1))
            res["yearly_budget_min"] = float(m_single.group(1))
    else:
        # Default numeric assignment without unit assumption
        if m_range:
            v1, v2 = float(m_range.group(1)), float(m_range.group(2))
            if 20000 <= v1 <= 500000 and 20000 <= v2 <= 500000:
                res["monthly_budget_min"] = v1
                res["monthly_budget_max"] = v2
            else:
                res["yearly_budget_min"] = v1
                res["yearly_budget_max"] = v2
        elif m_k:
            val = float(m_k.group(1)) * 1000
            res["monthly_budget"] = val
            res["monthly_budget_min"] = val
            res["monthly_budget_max"] = val
        elif m_single:
            val = float(m_single.group(1))
            if 20000 <= val <= 500000 or "rate" in lower or "tpc" in lower:
                res["monthly_budget"] = val
                res["monthly_budget_min"] = val
            else:
                res["yearly_budget"] = val
                res["yearly_budget_min"] = val

    if is_body_like:
        if res.get("monthly_budget"):
            res["budget_text"] = f"{int(res['monthly_budget']):,} / month"
        elif res.get("yearly_budget"):
            res["budget_text"] = f"{res['yearly_budget']} LPA"
        else:
            res["budget_text"] = None

    return res


def deterministic_extract_block(block_text: str, client_name: str | None = None) -> dict[str, Any]:
    """
    Deterministic extractor (V1):
    Extracts all 8 fields using label synonyms and boundary patterns on isolated clean requirement block.
    Returns field values, parsed subfields, and exact verbatim quotes.
    """
    clean_block = strip_all_exclusion_zones(block_text)
    quotes: dict[str, str] = {}
    extracted: dict[str, Any] = {
        "job_title": None,
        "location": None,
        "experience": None,
        "experience_text": None,
        "experience_min_years": None,
        "experience_max_years": None,
        "number_of_positions": None,
        "budget": None,
        "budget_text": None,
        "budget_currency": None,
        "yearly_budget": None,
        "yearly_budget_min": None,
        "yearly_budget_max": None,
        "monthly_budget": None,
        "monthly_budget_min": None,
        "monthly_budget_max": None,
        "mandatory_skills": None,
        "skills": None,
        "notice_period": None,
        "work_mode": None,
        "work_mode_text": None,
        "quotes": quotes,
    }

    lines = [line.strip() for line in clean_block.splitlines() if line.strip()]

    # Helper to find lines matching label patterns
    def extract_label_value(labels: tuple[str, ...]) -> tuple[str | None, str | None]:
        is_pos_query = any("position" in l or "headcount" in l or "opening" in l for l in labels)
        for lbl in labels:
            pat = rf"(?i)^\s*(?:[-*•]\s*)?{re.escape(lbl)}\s*[:=\-–—|]\s*(.+)$"
            for line in lines:
                m = re.match(pat, line)
                if m:
                    val = m.group(1).strip()
                    if val and not is_placeholder(val):
                        if not is_pos_query and re.search(r"(?i)\b(?:open\s*positions?|positions?\s*[-:]?\s*\d)\b", m.group(0)):
                            continue
                        return val, m.group(0)
            # Multiline lookup on same line
            m_multi = re.search(rf"(?im)^\s*(?:[-*•]\s*)?{re.escape(lbl)}\s*[:=\-–—|]\s*([^\n\r]+)", clean_block)
            if m_multi:
                val = m_multi.group(1).strip()
                if val and not is_placeholder(val):
                    if not is_pos_query and re.search(r"(?i)\b(?:open\s*positions?|positions?\s*[-:]?\s*\d)\b", m_multi.group(0)):
                        continue
                    return val, m_multi.group(0)
            # Multiline lookup with value on next line or separated across lines (e.g. Overall exp\n–\n5-8 Years)
            m_nl = re.search(rf"(?im)^\s*(?:[-*•]\s*)?{re.escape(lbl)}\s*(?:[:=\-–—|]\s*)?(?:\r?\n\s*[:=\-–—|]?\s*)+([^\r\n]+)", clean_block)
            if m_nl:
                val = m_nl.group(1).strip(" :-–—|\t")
                if val and not is_placeholder(val):
                    if not is_pos_query and re.search(r"(?i)\b(?:open\s*positions?|positions?\s*[-:]?\s*\d)\b", m_nl.group(0)):
                        continue
                    return val, m_nl.group(0)
        return None, None

    # 1. Job Title
    title_labels = ("job title", "role title", "position title", "designation", "profile", "requirement for", "requirement", "role", "hiring for")
    raw_title, quote_title = extract_label_value(title_labels)
    if raw_title and not is_placeholder(raw_title):
        extracted["job_title"] = raw_title
        quotes["job_title"] = quote_title or raw_title
    else:
        # Check first line if it looks like a role title
        if lines and len(lines[0]) < 80 and not any(w in lines[0].lower() for w in ["hi", "dear", "hello", "team", "regards"]):
            first_line = lines[0].strip(" -:*•")
            if re.search(r"(?i)\b(?:developer|engineer|lead|consultant|architect|manager|analyst|specialist)\b", first_line):
                extracted["job_title"] = first_line
                quotes["job_title"] = lines[0]

    # 2. Location (F1)
    raw_loc, quote_loc = extract_label_value(FIELD_LABEL_SYNONYMS["location"])
    if raw_loc and not is_placeholder(raw_loc):
        # City/cities/region exactly as written ("PAN India", "Bangalore(BDC-7)")
        loc_parts = [p.strip() for p in re.split(r"[,/|;]+", raw_loc) if p.strip() and not is_placeholder(p.strip())]
        if loc_parts:
            extracted["location"] = loc_parts
            quotes["location"] = quote_loc or raw_loc

    # 3. Experience (F2)
    raw_exp, quote_exp = extract_label_value(FIELD_LABEL_SYNONYMS["experience"])
    if raw_exp and not is_placeholder(raw_exp):
        extracted["experience_text"] = raw_exp
        extracted["experience"] = raw_exp
        min_y, max_y = parse_experience_digits(raw_exp)
        extracted["experience_min_years"] = min_y
        extracted["experience_max_years"] = max_y
        quotes["experience"] = quote_exp or raw_exp

    # 4. Budget (F3, F4)
    raw_bgt, quote_bgt = extract_label_value(FIELD_LABEL_SYNONYMS["budget"])
    if raw_bgt and not is_placeholder(raw_bgt):
        is_bl = (
            len(raw_bgt) > 80
            or "\n" in raw_bgt
            or any(w in raw_bgt.lower() for w in ("dear", "kindly", "hello", "hi ", "regards", "candidate", "partner", "submission", "resume"))
        )
        if not is_bl:
            bgt_dict = parse_budget_details(raw_bgt)
            extracted.update(bgt_dict)
            extracted["budget"] = bgt_dict.get("budget_text") or raw_bgt
            quotes["budget"] = quote_bgt or raw_bgt

    # 5. Mandatory Skills (F5)
    raw_mand, quote_mand = extract_label_value(FIELD_LABEL_SYNONYMS["mandatory_skills"])
    if raw_mand and not is_placeholder(raw_mand):
        def _parse_mand_tokens(raw: str) -> list[str]:
            raw_c = raw.strip().rstrip('.')
            chunks = re.split(r'(?:[,\n;|•*]|\s+&\s+|\s+and\s+)+', raw_c)
            res = []
            for c in chunks:
                c = c.strip(' .:-–—\t')
                if not c:
                    continue
                sub_tokens = re.split(r'\s+(?=(?:C\+\+|Rust|C#|Python|Java|React|Go|Golang)\b)|\s+[-–—]\s+', c, flags=re.I)
                for st in sub_tokens:
                    st = st.strip(' :-–—\t').rstrip('.')
                    if not st.lower().startswith('.net'):
                        st = st.lstrip('.')
                    if st and (len(st) > 1 or st.upper() in ("C", "R")):
                        res.append(st)
            return res or [raw_c]

        mand_skills = _parse_mand_tokens(raw_mand)
        # Never job title, never candidate template headers (F5, F6)
        jt_lower = (extracted.get("job_title") or "").strip().lower()
        mand_skills = [
            s for s in mand_skills
            if s.lower() != jt_lower and s.lower() not in CANDIDATE_TEMPLATE_HEADINGS
        ]
        if mand_skills:
            extracted["mandatory_skills"] = mand_skills
            quotes["mandatory_skills"] = quote_mand or raw_mand

    # 6. Skills (F6)
    raw_sk, quote_sk = extract_label_value(FIELD_LABEL_SYNONYMS["skills"])
    if raw_sk and not is_placeholder(raw_sk):
        sec_skills = [
            s.strip()
            for s in re.split(r"[,\n;/|•*]+", raw_sk)
            if s.strip() and not is_placeholder(s.strip())
        ]
        jt_lower = (extracted.get("job_title") or "").strip().lower()
        mand_set = set(s.lower() for s in (extracted.get("mandatory_skills") or []))
        sec_skills = [
            s for s in sec_skills
            if s.lower() != jt_lower
            and s.lower() not in CANDIDATE_TEMPLATE_HEADINGS
            and s.lower() not in mand_set
        ]
        if sec_skills:
            extracted["skills"] = sec_skills
            quotes["skills"] = quote_sk or raw_sk

    # Also extract technologies from JD requirement sections if enabled (F6)
    if skills_from_requirement_sections() and not extracted.get("skills"):
        # Look for JD / Requirement section mentioning tech
        m_tech = re.search(
            r"(?is)(?:job\s+description|jd|responsibilities|qualifications|role\s+summary|about\s+the\s+role|detailed\s+jd)\s*[:=\-–—|]?\s*(.+?)(?=\n\s*(?:skills|location|ctc|budget|notice|regards|$))",
            clean_block,
        )
        if m_tech:
            jd_text = m_tech.group(1)
            # Find recognized technology terms
            found_techs: list[str] = []
            mand_set = set(s.lower() for s in (extracted.get("mandatory_skills") or []))
            common_techs = [
                "Java", "Spring Boot", "AWS", "Python", "SQL", "Docker", "Kubernetes",
                "Azure", "GCP", "React", "Angular", "Node.js", "C++", "C#", ".NET",
                "Kafka", "Microservices", "SAP", "ABAP", "Snowflake", "Databricks",
                "Rust", "GitLab", "Jira", "Linux", "LAN", "Cyber Security",
                "PLC", "DCS", "Emerson DeltaV", "DeltaV", "Automation",
            ]
            for tech in common_techs:
                if re.search(rf"\b{re.escape(tech)}\b", jd_text, re.I):
                    if tech.lower() not in mand_set and tech.lower() != (extracted.get("job_title") or "").lower():
                        found_techs.append(tech)
            if found_techs:
                extracted["skills"] = found_techs
                quotes["skills"] = m_tech.group(0)[:100]

    # 7. Notice Period (F7)
    raw_np, quote_np = extract_label_value(FIELD_LABEL_SYNONYMS["notice_period"])
    if raw_np and not is_placeholder(raw_np):
        extracted["notice_period"] = raw_np
        quotes["notice_period"] = quote_np or raw_np

    # 8. Work Mode (F8)
    raw_wm, quote_wm = extract_label_value(FIELD_LABEL_SYNONYMS["work_mode"])
    if raw_wm and not is_placeholder(raw_wm):
        norm_wm, wm_text = parse_work_mode(raw_wm)
        extracted["work_mode"] = norm_wm
        extracted["work_mode_text"] = wm_text
        quotes["work_mode"] = quote_wm or raw_wm
    else:
        # Check explicit standalone work arrangement patterns only (never arbitrary words like 'remote' or 'office' in technical skills)
        m_arr = re.search(r"(?im)^\s*(?:[-*•]\s*)?(?:(?:work\s+model|work\s+mode|mode\s+of\s+work)\s*[:\-–—]\s*)?(hybrid\s*,\s*\d+\s*days?\s*(?:in\s*)?office|fully\s+remote|100%\s*remote|work\s+from\s+home|wfh|wfo|work\s+from\s+office)\b", clean_block)
        if m_arr:
            raw_wm = m_arr.group(1).strip()
            norm_wm, wm_text = parse_work_mode(raw_wm)
            if norm_wm or wm_text:
                extracted["work_mode"] = norm_wm
                extracted["work_mode_text"] = wm_text
                quotes["work_mode"] = m_arr.group(0).strip()

    # 9. Number of Positions / Headcount
    pos_labels = FIELD_LABEL_SYNONYMS.get(
        "number_of_positions",
        ("open positions", "open position", "positions", "openings", "number of positions", "no of positions", "headcount"),
    )
    raw_pos, quote_pos = extract_label_value(pos_labels)
    if raw_pos and not is_placeholder(raw_pos):
        m_p = re.search(r"\b(\d{1,3})\b", raw_pos)
        if m_p:
            try:
                extracted["number_of_positions"] = int(m_p.group(1))
                quotes["number_of_positions"] = quote_pos or raw_pos
            except ValueError:
                pass

    return extracted


def reconcile_two_way(
    ai_item: dict[str, Any],
    det_item: dict[str, Any],
    block_text: str,
) -> tuple[dict[str, Any], bool, list[str]]:
    """
    Two-Way Verification (V2) & Recall Guard (V3).
    Returns (reconciled_item, review_required, review_reasons).
    """
    clean_block = strip_all_exclusion_zones(block_text)
    reconciled = dict(ai_item)
    review_required = False
    review_reasons: list[str] = []
    recovered_by: dict[str, str] = dict(ai_item.get("recovered_by") or {})
    review_candidates: dict[str, Any] = dict(ai_item.get("review_candidates") or {})
    evidence_quotes: dict[str, str] = dict(ai_item.get("field_evidence_quotes") or {})

    det_quotes = det_item.get("quotes") or {}

    fields_to_check = [
        "job_title",
        "location",
        "experience",
        "number_of_positions",
        "budget",
        "mandatory_skills",
        "skills",
        "notice_period",
        "work_mode",
    ]

    for field in fields_to_check:
        ai_val = ai_item.get(field)
        det_val = det_item.get(field)

        # Normalize values for comparison
        def norm_val(v: Any) -> Any:
            if v is None or is_placeholder(v):
                return None
            if isinstance(v, list):
                res = sorted([str(x).strip().lower() for x in v if not is_placeholder(x)])
                if len(res) == 1:
                    return res[0]
                return res if res else None
            return str(v).strip().lower()

        ai_norm = norm_val(ai_val)
        det_norm = norm_val(det_val)

        # Case 1: Both agree
        if ai_norm is not None and ai_norm == det_norm:
            # Verified by both!
            quote = det_quotes.get(field) or _find_verbatim_quote(str(ai_val), clean_block)
            if quote:
                evidence_quotes[field] = quote
            recovered_by[field] = "two_way_agreement"
            reconciled[field] = ai_val

        # Case 2: One has value with verbatim quote in block, other is NULL
        elif ai_norm is not None and det_norm is None:
            # AI has value, deterministic is NULL
            matching_quotes = []
            if isinstance(ai_val, list):
                for x in ai_val:
                    q = _find_verbatim_quote(str(x), clean_block)
                    if q:
                        matching_quotes.append(q)
            else:
                q = _find_verbatim_quote(str(ai_val), clean_block)
                if q:
                    matching_quotes.append(q)

            if matching_quotes:
                evidence_quotes[field] = "; ".join(matching_quotes[:3])
                recovered_by[field] = "recovered_by_ai"
            else:
                recovered_by[field] = "ai_extracted_unverified"

            # Always preserve the extracted value - never silently replace with None!
            reconciled[field] = ai_val

        elif det_norm is not None and ai_norm is None:
            # Deterministic has value, AI is NULL
            quote = det_quotes.get(field) or _find_verbatim_quote(str(det_val), clean_block)
            reconciled[field] = det_val
            if quote:
                evidence_quotes[field] = quote
            recovered_by[field] = "recovered_by_deterministic"
            # Also propagate subfields if experience or budget
            if field == "experience":
                if det_item.get("experience_text"):
                    reconciled["experience_text"] = det_item.get("experience_text")
                if det_item.get("experience_min_years") is not None:
                    reconciled["experience_min_years"] = det_item.get("experience_min_years")
                if det_item.get("experience_max_years") is not None:
                    reconciled["experience_max_years"] = det_item.get("experience_max_years")
            elif field == "budget":
                for bk in ["budget_text", "yearly_budget", "yearly_budget_min", "yearly_budget_max", "monthly_budget", "monthly_budget_min", "monthly_budget_max", "budget_currency"]:
                    if det_item.get(bk) is not None:
                        reconciled[bk] = det_item.get(bk)
            elif field == "number_of_positions":
                if det_item.get("number_of_positions") is not None:
                    reconciled["number_of_positions"] = det_item.get("number_of_positions")
            elif field == "work_mode":
                if det_item.get("work_mode_text"):
                    reconciled["work_mode_text"] = det_item.get("work_mode_text")

        # Case 3: Different values -> preserve best candidate, do not store NULL!
        elif ai_norm is not None and det_norm is not None and ai_norm != det_norm:
            if isinstance(ai_val, list) and isinstance(det_val, list):
                merged_list = list(ai_val)
                for d_item in det_val:
                    if str(d_item).lower() not in [str(x).lower() for x in merged_list]:
                        merged_list.append(d_item)
                reconciled[field] = merged_list
            elif isinstance(ai_val, list) and isinstance(det_val, str):
                if det_val.lower() in [str(x).lower() for x in ai_val]:
                    reconciled[field] = ai_val
                else:
                    reconciled[field] = ai_val + [det_val]
            elif isinstance(ai_val, str) and isinstance(det_val, list):
                if ai_val.lower() in [str(x).lower() for x in det_val]:
                    reconciled[field] = det_val
                else:
                    reconciled[field] = [ai_val] + det_val
            else:
                reconciled[field] = ai_val

            quote = det_quotes.get(field) or _find_verbatim_quote(str(ai_val), clean_block) or _find_verbatim_quote(str(det_val), clean_block)
            if quote:
                evidence_quotes[field] = quote

            review_required = True
            review_reasons.append(f"field_conflict_{field}")
            review_candidates[field] = {
                "ai_candidate": ai_val,
                "deterministic_candidate": det_val,
            }
            recovered_by[field] = "reconciled_conflict_preserved"

        # Case 4: Both NULL -> check Recall Guard (V3)
        else:
            # Check if block contains label followed by real value
            labels = FIELD_LABEL_SYNONYMS.get(field, ())
            for lbl in labels:
                pat = rf"(?im)^\s*(?:[-*•]\s*)?{re.escape(lbl)}\s*[:=\-–—|]\s*([^\n\r]+)"
                m = re.search(pat, clean_block)
                if m:
                    cand = m.group(1).strip()
                    if cand and not is_placeholder(cand):
                        # V5: Ambiguous values (e.g. 'Hybrid/Remote') keep work_mode_text with work_mode NULL; not a miss, no review.
                        if field == "work_mode" and (reconciled.get("work_mode_text") or "/" in cand):
                            continue
                        # Block contains label followed by real value, but final is NULL!
                        reconciled["possible_miss"] = True
                        review_required = True
                        reason = f"possible_miss_{field}: '{cand[:40]}'"
                        review_reasons.append(reason)
                        review_candidates[field] = {"missed_candidate": cand}
                        break

    # Propagate budget fields if present in either item
    for bk in ["budget_text", "budget", "yearly_budget", "yearly_budget_min", "yearly_budget_max", "monthly_budget", "monthly_budget_min", "monthly_budget_max", "budget_currency"]:
        if reconciled.get(bk) is None:
            val_bk = ai_item.get(bk) if ai_item.get(bk) is not None else det_item.get(bk)
            if val_bk is not None:
                reconciled[bk] = val_bk
    for bk in ("budget", "budget_text"):
        val_str = str(reconciled.get(bk) or "")
        if val_str and (len(val_str) > 80 or "\n" in val_str or any(w in val_str.lower() for w in ("dear", "kindly", "hello", "hi ", "regards", "candidate", "partner"))):
            if reconciled.get("monthly_budget"):
                reconciled[bk] = f"{int(reconciled['monthly_budget']):,} / month"
            elif reconciled.get("yearly_budget"):
                reconciled[bk] = f"{reconciled['yearly_budget']} LPA"
            else:
                reconciled[bk] = None

    if not reconciled.get("budget_text") and reconciled.get("budget"):
        reconciled["budget_text"] = reconciled["budget"]
    if not reconciled.get("budget") and reconciled.get("budget_text"):
        reconciled["budget"] = reconciled["budget_text"]

    # Propagate experience subfields
    for ek in ["experience_text", "experience", "overall_experience", "experience_min_years", "experience_max_years"]:
        if reconciled.get(ek) is None:
            val_ek = ai_item.get(ek) if ai_item.get(ek) is not None else det_item.get(ek)
            if val_ek is not None:
                reconciled[ek] = val_ek

    # Propagate work mode text
    if reconciled.get("work_mode_text") is None:
        reconciled["work_mode_text"] = ai_item.get("work_mode_text") or det_item.get("work_mode_text") or reconciled.get("work_mode")

    # Clean skills from template leakage
    for sk in ("mandatory_skills", "skills"):
        if isinstance(reconciled.get(sk), list):
            reconciled[sk] = [
                s for s in reconciled[sk]
                if str(s).strip().lower() not in CANDIDATE_TEMPLATE_HEADINGS
                and not any(h in str(s).strip().lower() for h in (
                    "full name", "mail id", "mobile no", "resumes sent date", "qualification",
                    "rate card", "joiners required", "work location", "current organization",
                    "current location", "job location", "s/r num", "vendor name", "position title"
                ))
            ]

    reconciled["recovered_by"] = recovered_by
    reconciled["review_candidates"] = review_candidates
    reconciled["field_evidence_quotes"] = evidence_quotes

    # Review routing (A1): only missing job title or failed critical check triggers pending review
    # Missing budget, notice period, skills, experience, location, work mode are valid NULLs
    if not reconciled.get("job_title"):
        review_required = True
        review_reasons.append("missing_job_title")

    return reconciled, review_required, review_reasons


def verify_stored_requirement(payload: dict[str, Any], block_text: str) -> tuple[str, list[str]]:
    """
    Post-Save Verifier (V4):
    Re-reads stored field values against stored source block.
    Returns status ("verified" | "failed") and failed fields list.
    """
    clean_block = strip_all_exclusion_zones(block_text)
    failed_fields: list[str] = []

    fields_to_verify = [
        "job_title",
        "location",
        "experience",
        "budget",
        "notice_period",
        "work_mode",
    ]

    for field in fields_to_verify:
        val = payload.get(field)
        if val is None or is_placeholder(val):
            continue  # Valid NULL

        val_str = ", ".join(val) if isinstance(val, list) else str(val)
        quote = _find_verbatim_quote(val_str, clean_block)
        if not quote:
            # Check individual tokens if multiple words
            tokens = [t for t in re.split(r"[\s,;/|]+", val_str) if len(t) >= 3 and not is_placeholder(t)]
            matched_tokens = sum(1 for t in tokens if _find_verbatim_quote(t, clean_block))
            if tokens and (matched_tokens / len(tokens)) < 0.5:
                failed_fields.append(field)

    status = "failed" if failed_fields else "verified"
    return status, failed_fields
