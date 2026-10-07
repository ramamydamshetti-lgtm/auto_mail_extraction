"""
Map extracted AI fields + email metadata to MetaForge application payload shape.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from models import DashboardRequirement24
from config import is_placeholder, is_strict_field_mapping, lpa_implies_inr


@dataclass(frozen=True)
class EmailContext:
    """Graph-derived fields needed for MetaForge mapping."""

    graph_message_id: str
    internet_message_id: str
    to_emails: list[str]
    cc_emails: list[str]
    from_email: str
    from_name: str


_LPA_RE = re.compile(
    r"(?P<low>\d+(?:\.\d+)?)\s*(?:-|to|–|—)?\s*(?P<high>\d+(?:\.\d+)?)?\s*lpa",
    re.IGNORECASE,
)
_LPM_RE = re.compile(
    r"(?:inr|rs\.?)?\s*(?P<low>\d+(?:\.\d+)?)\s*(?:[Ll](?:akhs?)?)?(?:\s*/\s*[Mm](?:onth)?)?\s*(?:-|to|–|—)\s*(?:inr|rs\.?)?\s*(?P<high>\d+(?:\.\d+)?)\s*(?:[Ll](?:akhs?)?)(?:\s*/\s*[Mm](?:onth)?|lpm|\b)",
    re.IGNORECASE,
)
_USD_RE = re.compile(
    r"\$\s*(?P<n>\d+(?:\.\d+)?)\s*(?:/hr|per hour)?",
    re.IGNORECASE,
)
_EUR_RE = re.compile(r"(?i)\b(?:€|eur)\s*(?P<n>\d+(?:\.\d+)?)")
_INR_RE = re.compile(r"(?i)\b(?:₹|inr)\s*(?P<n>\d+(?:\.\d+)?)")
_SKILL_LINE_RE = re.compile(r"(?im)^\s*(?:skill|skills|mandatory\s*(?:technical\s*)?skills?|must\s*(?:to\s*)?have\s*(?:technical\s*)?skills?|primary\s*skills?)\s*[:\-]\s*(.+)$")
_EXP_RE = re.compile(r"(?i)\b(\d{1,2}\s*[-–]\s*\d{1,2}|\d{1,2}\+?)\s*(?:years?|yrs?)\b")
_JD_SECTION_RE = re.compile(
    r"(?is)(?:job description\s*[:\-]\s*)(?P<jd>.+?)(?:\n\s*qualifications?\s*[:\-]|\Z)"
)

_MANDATORY_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bbiw\b", "BIW (Body-in-White) design experience"),
    (r"\bnx\b|\bsiemens nx\b|\bnx cad\b", "CAD modeling using Siemens NX (NX CAD)"),
    (r"doors?\s*(?:&|and)?\s*closures?\b|\bdoor mechanisms?\b", "Automotive Doors & Closures domain knowledge"),
    (r"\bdaimler\b", "Daimler design methodology experience"),
    (r"assembly\b.*\b(joining|elements?)|\bjoining elements?\b", "Assembly design & joining elements creation"),
    (r"concept (?:proposal|design)|packaging study", "Concept design & packaging study"),
    (r"interference (?:check|checking)", "Interference checking"),
)

_CORE_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"master section", "Master section creation & validation"),
    (r"benchmark", "Benchmarking"),
    (r"styling validation", "Styling validation"),
    (r"door mechanisms?", "Door mechanisms"),
    (r"\bglass\b", "Glass systems"),
    (r"hinges?\b|handles?\b", "Hinges & handles"),
    (r"cost reduction", "Cost reduction techniques"),
    (r"weight reduction|weight optimization", "Weight optimization"),
    (r"cross functional|cft", "Cross-functional collaboration (CFT)"),
    (r"change management", "Change management"),
    (r"vehicle integration", "Vehicle integration understanding"),
    (r"corrosion", "Corrosion protection awareness"),
)


def _type_of_demand(jd_count: int | None = None, stated_type: str | None = None) -> str | None:
    """
    In strict mode: demand type is NULL unless explicitly stated.
    In legacy mode: 1 JD => Single, 2-9 JDs => Multiple, 10+ JDs => Bulk.
    """
    if is_strict_field_mapping():
        if stated_type and not is_placeholder(stated_type):
            s = str(stated_type).strip().capitalize()
            if s in ("Single", "Multiple", "Bulk"):
                return s
        return None
    if jd_count is None or jd_count < 1:
        return "Single"
    if jd_count == 1:
        return "Single"
    if 2 <= jd_count <= 9:
        return "Multiple"
    return "Bulk"


def _norm_priority(p: str | None) -> str | None:
    if not p or is_placeholder(p):
        return None
    u = str(p).strip().upper()
    if re.search(r"\bHIGH\b", u):
        return "HIGH"
    if re.search(r"\bMEDIUM\b", u):
        return "MEDIUM"
    if re.search(r"\bLOW\b", u):
        return "LOW"
    return None


def _norm_employment(t: str | None) -> str | None:
    if not t or is_placeholder(t):
        return None
    s = str(t).strip().lower()
    if any(k in s for k in ("full", "permanent", "fte")):
        return "Full-time"
    if any(k in s for k in ("contract", "c2h", "c2c", "subcon", "sub-con")):
        return "Contract"
    return None


def _norm_work_mode(w: str | None, body_text: str = "") -> str | None:
    if is_strict_field_mapping():
        text = str(w or "").strip().lower()
        if not text or is_placeholder(text):
            return None
        if re.search(r"\bhybrid\b", text) or re.search(r"\b[1-4]\s*days?\b", text):
            return "Hybrid"
        if re.search(r"\b(?:on-site|onsite|on site|in office|client location)\b", text):
            return "On-site"
        if re.search(r"\b(?:remote|wfh|work from home)\b", text):
            return "Remote"
        return None
    text = f"{w or ''} {body_text or ''}".lower().strip()
    if not text:
        return None
    if re.search(r"\b[1-4]\s*days?\b", text) or re.search(r"\b[1-4]\s*days?\s*(?:work\s*)?(?:from\s*|in\s*|at\s*)?office\b", text) or "hybrid" in text or "partially" in text:
        return "Hybrid"
    if any(k in text for k in ("on-site", "onsite", "on site", "in office", "client location", "100% office", "all 5 days")):
        return "On-site"
    if any(k in text for k in ("remote", "wfh", "work from home", "home based")):
        return "Remote"
    return None


def _norm_experience_level(level: str | None) -> str | None:
    if not level or is_placeholder(level):
        return None
    s = str(level).strip().lower()
    if s in ("entry level", "entry", "fresher", "junior level", "junior"):
        return "Junior Level"
    if s in ("mid level", "mid", "intermediate"):
        return "Mid Level"
    if s in ("mid senior", "mid-senior", "mid-senior level", "midsenior"):
        return "Mid-Senior Level"
    if s in ("senior level", "senior", "lead"):
        return "Senior Level"
    if s in ("expert level", "expert", "principal"):
        return "Expert Level"
    return None


def _align_experience_level_with_overall(exp_level: str | None, overall_exp: str | None) -> str | None:
    """Ensure experience_level is aligned with overall_experience without inserting fabricated defaults."""
    if is_strict_field_mapping():
        if exp_level and not is_placeholder(exp_level):
            return _norm_experience_level(exp_level)
        return None
    if not exp_level and not overall_exp:
        return None
    exp_str = str(exp_level or "").strip()
    if exp_str.lower() in ("none", "null", "unknown", "n/a", ""):
        exp_str = ""
    if not overall_exp:
        return exp_str or None
    m = re.search(r"(\d{1,2})\s*\+?", str(overall_exp))
    if m:
        try:
            years = int(m.group(1))
            if years >= 8 and (not exp_str or exp_str.lower() in ("mid senior", "mid-senior", "junior", "unknown")):
                return "Senior Level"
            elif years <= 3 and (not exp_str or exp_str.lower() in ("senior", "mid senior")):
                return "Junior Level"
            elif 4 <= years <= 7 and (not exp_str or exp_str.lower() in ("junior", "senior")):
                return "Mid-Senior Level"
        except ValueError:
            pass
    return exp_str or None


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    text = str(value).strip()
    if not text:
        return []
    if text.startswith("[") and text.endswith("]"):
        try:
            import ast
            parsed = ast.literal_eval(text)
            if isinstance(parsed, list):
                return [str(v).strip() for v in parsed if str(v).strip()]
        except Exception:
            pass
    parts = re.split(r"[,\n;/|]+", text)
    return [p.strip() for p in parts if p.strip()]


def _norm_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def _infer_experience_level_from_text(text: str) -> str:
    m = _EXP_RE.search(text or "")
    if not m:
        return "unknown"
    raw = m.group(1).replace(" ", "")
    try:
        if "-" in raw:
            lo = float(raw.split("-", 1)[0])
        elif "+" in raw:
            lo = float(raw.replace("+", ""))
        else:
            lo = float(raw)
    except ValueError:
        return "unknown"
    if lo < 3:
        return "junior"
    if lo < 7:
        return "mid"
    return "senior"


def _infer_overall_experience(text: str, level: str) -> str:
    m = _EXP_RE.search(text or "")
    if m:
        return f"{m.group(1)} years".replace("  ", " ").strip()
    if level == "junior":
        return "2-4 years"
    if level == "mid senior":
        return "4-7 years"
    if level == "senior":
        return "7+ years"
    return "3-6 years"


def _extract_skills_from_text(text: str) -> tuple[str | None, str | None]:
    if not text:
        return None, None
    mandatory: list[str] = []
    skills: list[str] = []
    low_text = text.lower()

    # JD-focused parsing for richer extraction quality.
    jd_match = _JD_SECTION_RE.search(text)
    jd_block = jd_match.group("jd") if jd_match else text
    jd_low = jd_block.lower()

    # Explicit "Skill:" line
    for m in _SKILL_LINE_RE.finditer(text):
        raw_val = m.group(1).strip().rstrip(".")
        chunks = re.split(r"(?:[,\n;/|•*]|\s+&\s+|\s+and\s+)+", raw_val)
        for c in chunks:
            c = c.strip(" .:-–—\t")
            if not c:
                continue
            sub_tokens = re.split(r"\s+(?=(?:C\+\+|Rust|C#|Python|Java|React|Go|Golang)\b)|\s+[-–—]\s+", c, flags=re.I)
            for st in sub_tokens:
                st = st.strip(" :-–—\t").rstrip(".")
                if not st.lower().startswith(".net"):
                    st = st.lstrip(".")
                if st and len(st) > 1:
                    mandatory.append(st)
                    skills.append(st)

    # Pattern-based extraction for automotive JD-style emails.
    for pat, label in _MANDATORY_PATTERNS:
        if re.search(pat, jd_low, re.IGNORECASE):
            mandatory.append(label)

    for pat, label in _CORE_PATTERNS:
        if re.search(pat, jd_low, re.IGNORECASE):
            skills.append(label)

    # Job description bullet-ish lines and strong requirements
    for ln in jd_block.splitlines():
        s = ln.strip().strip("-*•· ")
        if not s:
            continue
        low = s.lower()
        if len(s) > 120:
            continue
        if re.search(r"(?i)^(?:position|title|job title|role|work location|location|bill rate|budget|overall exp|over all exp|total exp|open positions?|qualification|mandatory\s*(?:technical\s*)?skills?|technical\s*skills?)\b", s):
            continue
        if any(k in low for k in ("must", "mandatory", "should have", "hands on", "strong in")):
            mandatory.append(s)

    # Technology chip tags from JD
    tech_tags = (
        "Python", "Docker", "GitLab", "Jira", "Linux", "LAN", "Cyber Security",
        "Rust", "C++", "C#", "React", "Angular", "Node.js", "Java", "Spring Boot",
        "AWS", "Azure", "GCP", "SQL", "Kafka", "Microservices", "SAP", "ABAP",
        "Snowflake", "Databricks", "PLC", "DCS", "Emerson DeltaV", "DeltaV", "Automation",
    )
    for tag in tech_tags:
        if re.search(r"\b" + re.escape(tag) + r"\b", jd_block, re.I):
            skills.append(tag)

    def _dedup(xs: list[str]) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for x in xs:
            k = x.lower()
            if k not in seen:
                seen.add(k)
                out.append(x)
        return out

    # Remove overlap so "skills" acts as core/nice-to-have list.
    dedup_m = _dedup(mandatory)
    dedup_s = [x for x in _dedup(skills) if x.lower() not in {m.lower() for m in dedup_m}]

    # If still empty, run pattern checks against full body as fallback.
    if not dedup_m:
        for pat, label in _MANDATORY_PATTERNS:
            if re.search(pat, low_text, re.IGNORECASE):
                dedup_m.append(label)
    if not dedup_s:
        for pat, label in _CORE_PATTERNS:
            if re.search(pat, low_text, re.IGNORECASE):
                dedup_s.append(label)

    m_out = "; ".join(dedup_m[:12]) if dedup_m else None
    s_out = "; ".join(dedup_s[:20]) if dedup_s else None
    return m_out, s_out


def parse_budget_fields(budget_text: str | None) -> dict[str, Any]:
    """
    Derive display budget and optional INR LPA numeric range from free text.
    """
    raw = (budget_text or "").strip()
    # Sanitize initial display: only use raw if it's a short, plausible budget note, NOT an email body
    is_body_like = (
        len(raw) > 80
        or "\n" in raw
        or any(w in raw.lower() for w in ("dear", "kindly", "hello", "hi ", "regards", "candidate", "partner", "submission", "resume", "pls ensure", "subject line"))
    )
    out: dict[str, Any] = {
        "budget_display": None if is_body_like else (raw or None),
        "budget_currency": None,
        "budget_inr_lpa_min": None,
        "budget_inr_lpa_max": None,
        "budget_inr_lpm_min": None,
        "budget_inr_lpm_max": None,
        "budget_period": None,
    }
    if not raw:
        return out

    m = _LPA_RE.search(raw)
    if m:
        low = float(m.group("low"))
        high_s = m.group("high")
        high = float(high_s) if high_s else low
        out["budget_currency"] = "INR"
        out["budget_inr_lpa_min"] = int(min(low, high) * 100000)
        out["budget_inr_lpa_max"] = int(max(low, high) * 100000)
        out["budget_period"] = "yearly"
        out["budget_display"] = f"{int(max(low, high)) if max(low, high).is_integer() else max(low, high)} LPA"
        return out

    m_lpm = _LPM_RE.search(raw)
    if m_lpm:
        low = float(m_lpm.group("low"))
        high_s = m_lpm.group("high")
        high = float(high_s) if high_s else low
        out["budget_currency"] = "INR"
        out["budget_inr_lpm_min"] = int(min(low, high) * 100000)
        out["budget_inr_lpm_max"] = int(max(low, high) * 100000)
        out["budget_period"] = "monthly"
        if abs(low - high) < 1e-6:
            out["budget_display"] = f"INR {int(low * 100000):,}/month"
        else:
            out["budget_display"] = f"INR {int(min(low, high) * 100000):,} - {int(max(low, high) * 100000):,}/month"
        return out

    # Tiered budget rates (e.g. Bill Rate per month for TPC... or Tiered Budget Rates...)
    m_tiered = re.search(
        r"(?i)\b(?:bill\s+rate(?:\s+per\s+month)?(?:\s+for\s+tpc)?(?:\s*\([^)]*\))?|tiered\s+(?:budget|rates?)|rate\s+slabs?|tiered\s+budget\s+rates?)\s*[:\-–]?\s*\n"
        r"((?:[ \t]*\d+.*?yrs[^\n]*\n?)+)",
        raw
    )
    if m_tiered:
        tier_block = m_tiered.group(1).strip()
        lines = [re.sub(r"\s+", " ", l.strip(" -:*•\t")) for l in tier_block.splitlines() if l.strip(" -:*•\t")]
        cleaned_tiers: list[str] = []
        for l in lines:
            if re.search(r"\d+\s*[-–+]\s*(?:\d+\s*)?(?:yrs?|years?)", l, re.I):
                m_rate = re.search(r"^(.+?\b(?:\d+(?:\.\d+)?\s*(?:[Ll]|[Kk]|Lakhs?|INR|Rs\.?)|Open\s*Budget))\b", l, re.I)
                cleaned_line = m_rate.group(1).strip() if m_rate else l
                cleaned_tiers.append(cleaned_line)
        vals = []
        for l in lines:
            for kv, lv in re.findall(r"(?:(\d+(?:\.\d+)?)\s*k\b|(\d+(?:\.\d+)?)\s*(?:l\b|lakhs?))", l, re.I):
                if kv:
                    vals.append(int(float(kv) * 1000))
                elif lv:
                    vals.append(int(float(lv) * 100000))
        if vals:
            out["budget_inr_lpm_min"] = min(vals)
            out["budget_inr_lpm_max"] = max(vals)
        if cleaned_tiers:
            summary = " / ".join(cleaned_tiers)
            out["budget_display"] = summary
            out["budget_currency"] = "INR" if re.search(r"(?i)\b(?:l|lakhs?|inr|rs\.?|₹|k)\b", summary) else None
            out["budget_period"] = "monthly"
            return out

    clean_raw = re.sub(r"(?<=\d),(?=\d)", "", raw)
    low_raw = clean_raw.lower()
    is_monthly = bool(re.search(r"(?i)\b(?:per\s+month|/month|p\.?m\.?|monthly|bill\s+rate|rate\s*/\s*pm|rate\s*card|tpc\s+rates?)\b", clean_raw))

    # Explicit Monthly Rate Card pattern (e.g. Monthly rate card- 120000, Monthly rate card- 175000)
    m_rate_card = re.search(
        r"(?i)\b(?:monthly\s+rate\s+card|rate\s*card|monthly\s*rate)\s*[:\-–]?\s*(\d{4,7})\b",
        clean_raw
    )
    if m_rate_card:
        val = int(m_rate_card.group(1))
        out["budget_currency"] = "INR"
        out["budget_inr_lpm_min"] = val
        out["budget_inr_lpm_max"] = val
        out["budget_period"] = "monthly"
        out["budget_display"] = f"INR {val:,}/month"
        return out

    # Range pattern (e.g. 75000-80000 max, 200000-250000 max)
    m_range = re.search(r"(\d{5,7})\s*(?:-|to|–|—)\s*(\d{5,7})", clean_raw)
    if m_range:
        v_min = int(m_range.group(1))
        v_max = int(m_range.group(2))
        out["budget_currency"] = "INR"
        out["budget_inr_lpm_min"] = min(v_min, v_max)
        out["budget_inr_lpm_max"] = max(v_min, v_max)
        out["budget_period"] = "monthly"
        out["budget_display"] = f"INR {min(v_min, v_max):,} - {max(v_min, v_max):,}/month"
        return out

    # Monthly Lakhs pattern (e.g. 1.25L, 1.3 L)
    m_lakh = re.search(r"(\d+(?:\.\d+)?)\s*(?:l\b|lakhs?|lpm\b)", clean_raw, re.I)
    if m_lakh:
        n_lakh = float(m_lakh.group(1))
        out["budget_currency"] = "INR"
        val = int(n_lakh * 100000)
        if is_monthly or "lpm" in low_raw or "month" in low_raw or "rate" in low_raw:
            out["budget_inr_lpm_min"] = val
            out["budget_inr_lpm_max"] = val
            out["budget_period"] = "monthly"
            out["budget_display"] = f"INR {val:,}/month"
        else:
            out["budget_inr_lpa_min"] = val
            out["budget_inr_lpa_max"] = val
            out["budget_period"] = "yearly"
            out["budget_display"] = f"{n_lakh} LPA"
        return out

    # Monthly Thousands pattern (e.g. 90 K, 95 K)
    m_k = re.search(r"(\d+(?:\.\d+)?)\s*k\b", clean_raw, re.I)
    if m_k:
        val = int(float(m_k.group(1)) * 1000)
        out["budget_currency"] = "INR"
        out["budget_inr_lpm_min"] = val
        out["budget_inr_lpm_max"] = val
        out["budget_period"] = "monthly"
        out["budget_display"] = f"INR {val:,}/month"
        return out

    # Require either a keyword prefix (rate/budget) OR an explicit monthly suffix (/month, pm), or a standalone number
    m_monthly = re.search(
        r"(?i)(?:"
        r"(?:tpc\s+rates?|rate\s*/\s*pm|monthly\s+budget|monthly\s+rate\s+card|rate\s*card|monthly\s*rate|bill\s+rate(?:\s+per\s+month)?(?:\s+for\s+tpc)?(?:\s*\([^)]*\))?|rate)\s*[:\-–]?\s*(\d{5,7})(?:\s*(?:/\s*m(?:onth)?|per\s+month|pm))?"
        r"|(\d{5,7})\s*(?:/\s*m(?:onth)?|per\s+month|pm)"
        r"|^\s*(\d{5,7})\s*$"
        r")",
        clean_raw
    )
    if m_monthly:
        val_str = next((g for g in m_monthly.groups() if g), None)
        if val_str and int(val_str) >= 10000:
            val = int(val_str)
            out["budget_currency"] = "INR"
            out["budget_inr_lpm_min"] = val
            out["budget_inr_lpm_max"] = val
            out["budget_period"] = "monthly"
            out["budget_display"] = f"INR {val:,}/month"
            return out

    m2 = _USD_RE.search(raw)
    if m2:
        out["budget_currency"] = "USD"
        out["budget_display"] = f"USD {m2.group('n')}"
        return out

    m3 = _EUR_RE.search(raw)
    if m3:
        out["budget_currency"] = "EUR"
        out["budget_display"] = f"EUR {m3.group('n')}"
        return out

    m4 = _INR_RE.search(raw)
    if m4:
        out["budget_currency"] = "INR"
        out["budget_display"] = f"INR {m4.group('n')}"
        return out

    return out


def map_to_ui_payload(validated_item: dict[str, Any], email_metadata: dict[str, Any]) -> dict[str, Any]:
    """
    Translate validated requirement into UI-facing JSON shape.
    """
    def _is_generic_loc(s: Any) -> bool:
        low = str(s).strip("[]'\" ").lower()
        return any(g in low for g in ("client location", "client site", "client office", "any ltts", "any office", "any location", "pan india"))

    loc_list = [l for l in _as_list(validated_item.get("location")) if not _is_generic_loc(l)]
    mand = _as_list(validated_item.get("mandatory_skills"))
    additional = _as_list(validated_item.get("soft_skills") or validated_item.get("skills"))
    budget_min = validated_item.get("yearly_budget_min")
    budget_max = validated_item.get("yearly_budget_max")
    monthly_budget_min = validated_item.get("monthly_budget_min")
    monthly_budget_max = validated_item.get("monthly_budget_max")
    budget_raw = str(validated_item.get("budget") or "")
    budget_bits = parse_budget_fields(budget_raw)
    if not is_strict_field_mapping() or lpa_implies_inr():
        if budget_min is not None or budget_max is not None:
            budget_bits["budget_currency"] = budget_bits.get("budget_currency") or "INR"
        if monthly_budget_min is not None or monthly_budget_max is not None:
            budget_bits["budget_currency"] = budget_bits.get("budget_currency") or "INR"

    raw_pos = validated_item.get("number_of_positions")
    if raw_pos is not None and not is_placeholder(raw_pos):
        try:
            n_positions = int(raw_pos)
        except (TypeError, ValueError):
            n_positions = None
    else:
        n_positions = None

    from_email = str(email_metadata.get("from_email") or "").strip()
    to_emails = _as_list(email_metadata.get("to_emails"))
    cc_emails = _as_list(email_metadata.get("cc_emails"))
    
    # Internal POC is derived from To recipients (internal company staff)
    internal_poc_str = "; ".join(to_emails) if to_emails else None

    # Client POC (CC) must ONLY include external client domain addresses, excluding internal company staff (@metaforgeit.com)
    internal_domains = {"metaforgeit.com", "metaforge.com", "metaforge.co"}
    client_poc_parts: list[str] = []
    poc_seen: set[str] = set()
    for em in cc_emails:
        norm = _norm_text(em)
        domain = norm.split("@")[-1] if "@" in norm else ""
        if norm and norm not in poc_seen and domain not in internal_domains:
            poc_seen.add(norm)
            client_poc_parts.append(em)

    NOISE_SKILLS = {
        "mobile no", "mobile number", "phone", "email id", "email address",
        "applicant location", "applicant name", "candidate name", "preferred location",
        "current org", "vendor", "sl. no", "sl no", "s.no", "total exp", "relevant exp",
        "notice period", "monthly billing rates", "billing rates"
    }
    mand = [s for s in mand if str(s).strip().lower() not in NOISE_SKILLS and not is_placeholder(s)]
    additional = [s for s in additional if str(s).strip().lower() not in NOISE_SKILLS and not is_placeholder(s)]

    if monthly_budget_min is None and budget_bits.get("budget_inr_lpm_min") is not None:
        monthly_budget_min = budget_bits.get("budget_inr_lpm_min")
        monthly_budget_max = budget_bits.get("budget_inr_lpm_max")

    if monthly_budget_min is not None or monthly_budget_max is not None:
        if monthly_budget_min is not None and monthly_budget_max is not None and monthly_budget_min != monthly_budget_max:
            monthly_budget_val = f"₹{monthly_budget_min:,} - ₹{monthly_budget_max:,}"
        else:
            mval = monthly_budget_max if monthly_budget_max is not None else monthly_budget_min
            monthly_budget_val = f"₹{mval:,}"
    elif budget_bits.get("budget_period") == "monthly" and budget_bits.get("budget_display"):
        monthly_budget_val = budget_bits["budget_display"]
    else:
        monthly_budget_val = None

    if is_strict_field_mapping():
        raw_exp_level = _norm_experience_level(validated_item.get("experience_level"))
        final_exp_level = raw_exp_level
        overall_exp = str(validated_item.get("overall_experience") or validated_item.get("experience") or validated_item.get("experience_text") or "").strip() or None
        if is_placeholder(overall_exp):
            overall_exp = None
    else:
        raw_exp_level = _norm_experience_level(str(validated_item.get("experience_level") or "")).replace("-", " ").title()
        overall_exp = str(validated_item.get("overall_experience") or validated_item.get("experience") or validated_item.get("experience_text") or "").strip() or None
        final_exp_level = _align_experience_level_with_overall(raw_exp_level, overall_exp)

    p_val = _norm_priority(validated_item.get("priority"))

    if is_strict_field_mapping():
        tod_raw = validated_item.get("type_of_demand")
        final_tod = str(tod_raw).lower() if tod_raw and str(tod_raw).lower() in ("single", "multiple", "bulk") else "single"
    else:
        final_tod = "single" if (n_positions == 1 or n_positions is None) else ("multiple" if n_positions < 10 else "bulk")

    cjd_raw = validated_item.get("client_jd_id") or email_metadata.get("client_jd_id")
    final_cjd = None if is_placeholder(cjd_raw) else str(cjd_raw).strip()

    np_raw = validated_item.get("notice_period")
    final_np = None if is_placeholder(np_raw) else str(np_raw).strip()

    job_title_val = str(validated_item.get("job_title") or "").strip() or None
    if is_placeholder(job_title_val):
        job_title_val = None

    payload = {
        "job_id": str(email_metadata.get("job_id") or f"REQ-{email_metadata.get('date')}-{email_metadata.get('count')}"),
        "demand_received_date": email_metadata.get("date"),
        "internal_poc_email": internal_poc_str,
        "internal_poc": internal_poc_str,
        "requirement_from": email_metadata.get("requirement_from") or validated_item.get("client_name") or "",
        "client_jd_id": final_cjd or "",
        "client_lead_poc_email": from_email or None,
        "client_poc_emails": "; ".join(client_poc_parts) if client_poc_parts else None,
        "job_title": job_title_val,
        "job_status": validated_item.get("job_status") or "open",
        "closed_date": None,
        "type_of_demand": final_tod,
        "priority": p_val.lower() if p_val else None,
        "number_of_positions": n_positions,
        "experience_level": final_exp_level,
        "employment_type": _norm_employment(validated_item.get("employment_type")),
        "budget_currency": budget_bits.get("budget_currency"),
        "yearly_budget": None if budget_bits.get("budget_period") == "monthly" else (budget_max if budget_max is not None else (budget_min if budget_min is not None else (budget_raw if budget_raw and not is_placeholder(budget_raw) else None))),
        "monthly_budget": monthly_budget_val,
        "work_mode": _norm_work_mode(validated_item.get("work_mode")),
        "location": ", ".join(loc_list) if loc_list else None,
        "overall_experience": overall_exp,
        "notice_period": final_np,
        "mandatory_skills": mand,
        "skills": additional,
    }
    return DashboardRequirement24.model_validate(payload).model_dump(mode="json")


def check_ui_readiness(validated_item: dict[str, Any]) -> dict[str, Any]:
    """
    Flag fields for manual review when critical requirements fail.
    A1: Only a missing job title (or title and ID both missing) or a failed ID/evidence check
    on a critical field sends an item to pending review. Missing budget, notice period, skills,
    experience, location, work mode or positions are valid NULLs and never block saving or cause review.
    Remove budget_not_provided and overall_confidence from the review triggers that block saving.
    """
    review_required: list[str] = []

    if validated_item.get("is_classifier_uncertain") or validated_item.get("classifier_uncertain"):
        review_required.append("classifier_uncertain")

    if validated_item.get("reconciliation_status") == "conflict_review_flagged" or (
        validated_item.get("processing_note") and "Reconciliation conflict" in str(validated_item.get("processing_note"))
    ):
        review_required.append("table_reconciliation_conflict")

    if (
        validated_item.get("client_key") == "idexcel_unresolved"
        or validated_item.get("requirement_from") in ("unresolved", "Idexcel (client not identified)", "Idexcel")
        or validated_item.get("idexcel_unresolved")
        or (validated_item.get("processing_note") and "idexcel.com" in str(validated_item.get("processing_note")))
    ):
        review_required.append("idexcel_client_unresolved")

    # Title check (or title and ID both missing)
    jt = str(validated_item.get("job_title") or "").strip()
    if not jt or is_placeholder(jt):
        review_required.append("job_title")

    critical_blocks = [
        f for f in review_required
        if f in {
            "job_title",
            "classifier_uncertain",
            "table_reconciliation_conflict",
            "idexcel_client_unresolved",
        }
    ]

    return {
        "is_ready_for_auto_sync": len(critical_blocks) == 0,
        "review_fields": sorted(set(review_required)),
    }


def is_internal_domain(email: str | None) -> bool:
    """Check if an email address belongs to the internal company domain."""
    if not email:
        return False
    e = email.strip().lower()
    if "@" not in e:
        return False
    domain = e.rsplit("@", 1)[-1]
    internal_domains = ("metaforgeit.com",)
    return any(domain == d or domain.endswith("." + d) for d in internal_domains)


def derive_experience_level_from_text_or_years(exp_text: str | None, exp_level_raw: str | None) -> str | None:
    """
    Rule 4: Shared, client-agnostic experience-level classifier.
    Under strict mapping: experience_level is NULL unless explicitly stated.
    """
    if is_strict_field_mapping():
        if exp_level_raw and not is_placeholder(exp_level_raw):
            return _norm_experience_level(exp_level_raw)
        return None

    text = f"{exp_text or ''} {exp_level_raw or ''}".strip().lower()
    if not text:
        return None

    m = re.search(r"(\d{1,2})\s*(?:-|to|–|—|\+)?\s*(\d{1,2})?", text)
    if m:
        try:
            val1 = int(m.group(1))
            val2 = int(m.group(2)) if m.group(2) else val1
            avg_yrs = (val1 + val2) / 2.0
            if avg_yrs >= 12:
                return "Expert Level"
            elif avg_yrs >= 8:
                return "Senior Level"
            elif avg_yrs >= 5:
                return "Mid-Senior Level"
            elif avg_yrs >= 2:
                return "Mid Level"
            else:
                return "Junior Level"
        except ValueError:
            pass

    if "expert" in text:
        return "Expert Level"
    elif "senior" in text or "lead" in text:
        return "Senior Level"
    elif "mid-senior" in text or "mid senior" in text:
        return "Mid-Senior Level"
    elif "mid" in text:
        return "Mid Level"
    elif "junior" in text or "entry" in text:
        return "Junior Level"

    return None


def _norm_work_mode(w: str | None, body_text: str = "") -> str | None:
    """
    Rule 5: Work mode classification based on actual wording.
    Phrasings like 'X days from office', 'X days RTO', 'hybrid' -> Hybrid
    'remote', 'work from home', 'wfh' -> Remote
    'on-site', 'onsite', 'in office', '100% office' -> On-site
    Returns None if not stated in text (no fabricated defaults!).
    """
    text = f"{w or ''} {body_text or ''}".lower()
    if not text.strip():
        return None

    if (
        re.search(r"\b[1-4]\s*days?\b", text)
        or re.search(r"\b[1-4]\s*days?\s*(?:work\s*)?(?:from\s*|in\s*|at\s*)?(?:office|site|rto)\b", text)
        or "hybrid" in text
        or "partially" in text
    ):
        return "Hybrid"

    if any(k in text for k in ("remote", "wfh", "work from home", "home based")):
        return "Remote"

    if any(
        k in text
        for k in (
            "on-site",
            "onsite",
            "on site",
            "in office",
            "client location",
            "100% office",
            "5 days office",
            "5 days from office",
            "all 5 days",
        )
    ):
        return "On-site"

    return None


def extract_min_max_experience(exp_text: str | None) -> tuple[int | None, int | None]:
    """Rule 3: Preserve experience ranges as min/max numbers."""
    if not exp_text:
        return None, None
    m = re.search(r"(\d{1,2})\s*(?:-|to|–|—)\s*(\d{1,2})", exp_text)
    if m:
        try:
            return int(m.group(1)), int(m.group(2))
        except ValueError:
            pass
    m_plus = re.search(r"(\d{1,2})\s*\+", exp_text)
    if m_plus:
        try:
            val = int(m_plus.group(1))
            return val, None
        except ValueError:
            pass
    m_single = re.search(r"\b(\d{1,2})\b", exp_text)
    if m_single:
        try:
            val = int(m_single.group(1))
            return val, val
        except ValueError:
            pass
    return None, None


def map_to_metaforge(
    extracted: dict[str, Any],
    *,
    ctx: EmailContext,
    client_display_name: str,
    job_id: str,
    client_jd_id: str,
    body_text: str = "",
    internal_poc_default: str = "offshore demands",
    jd_count: int = 1,
    demand_received_date: date | None = None,
    email_subject: str = "",
    email_body_plain: str = "",
    email_body_html: str = "",
    email_received_iso: str = "",
) -> dict[str, Any]:
    """
    Build the MetaForge-ready dict from one extracted requirement row, strictly adhering to Rules 1-10.
    """
    d = demand_received_date or date.today()
    demand_date_str = d.isoformat()

    # Rule 1: Headcount / Number of positions (None if not specified)
    n_pos = extracted.get("number_of_positions") or extracted.get("positions") or extracted.get("open_positions") or extracted.get("headcount")
    if (n_pos is None or is_placeholder(n_pos)) and body_text:
        m_pos = re.search(r"(?i)\b(?:open\s*positions?|positions?|openings?|headcount|no\.?\s*(?:of\s*)?positions?)\b\s*[:\-–—|]\s*(\d{1,3})\b", body_text)
        if m_pos:
            n_pos = m_pos.group(1)

    n_int = None
    if n_pos is not None and not is_placeholder(n_pos):
        try:
            n_int = int(n_pos)
        except (TypeError, ValueError):
            m = re.search(r"\d+", str(n_pos))
            if m:
                n_int = int(m.group(0))

    extracted_mand = (
        extracted.get("mandatory_skills")
        or extracted.get("must_have_skills")
        or extracted.get("primary_skills")
        or extracted.get("key_skills")
        or extracted.get("technical_skills")
    )
    extracted_mand_list = _as_list(extracted_mand)

    extracted_soft = (
        extracted.get("soft_skills")
        or extracted.get("skills")
        or extracted.get("secondary_skills")
        or extracted.get("nice_to_have_skills")
    )
    extracted_soft_list = _as_list(extracted_soft)

    if not extracted_mand_list and not extracted_soft_list:
        fallback_mand, fallback_skills = _extract_skills_from_text(body_text)
        if fallback_mand:
            extracted_mand_list = _as_list(fallback_mand)
        if fallback_skills:
            extracted_soft_list = _as_list(fallback_skills)

    job_title = str(extracted.get("job_title") or extracted.get("role") or extracted.get("title") or "").strip() or None
    if not job_title and body_text:
        m_jt = re.search(r"(?im)^\s*(?:position\s*/\s*title|position|job\s*title|role)\s*[:\-]\s*(.+)$", body_text)
        if m_jt:
            jt_cand = m_jt.group(1).strip()
            if jt_cand and not is_placeholder(jt_cand):
                job_title = jt_cand

    experience_raw = str(
        extracted.get("overall_experience")
        or extracted.get("experience")
        or extracted.get("experience_text")
        or extracted.get("total_experience")
        or extracted.get("exp")
        or ""
    ).strip() or None
    if not experience_raw and body_text:
        m_exp = re.search(r"(?i)\b(?:overall\s*exp(?:erience)?|over\s*all\s*exp(?:erience)?|total\s*exp(?:erience)?|years\s*of\s*exp(?:erience)?)\b\s*[:\-]\s*([^\n\r]+)", body_text)
        if m_exp:
            exp_val = m_exp.group(1).strip()
            if exp_val and not is_placeholder(exp_val):
                experience_raw = exp_val

    exp_level = derive_experience_level_from_text_or_years(
        experience_raw, str(extracted.get("experience_level") or "")
    )

    requirement_from = (client_display_name or "").strip() or None

    # Location: preserve all locations if multiple
    raw_loc = extracted.get("location") or extracted.get("job_location") or extracted.get("work_location") or extracted.get("base_location") or extracted.get("city")
    if not raw_loc and body_text:
        m_loc = re.search(r"(?im)^\s*(?:work\s*location|location|job\s*location|base\s*location)\s*[:\-]\s*(.+)$", body_text)
        if m_loc:
            loc_cand = m_loc.group(1).strip()
            if loc_cand and not is_placeholder(loc_cand):
                raw_loc = loc_cand
    def _is_generic_raw_loc(s: Any) -> bool:
        low = str(s).strip("[]'\" ").lower()
        return any(g in low for g in ("client location", "client site", "client office", "any ltts", "any office", "any location", "pan india"))

    loc_items = [str(l).strip() for l in _as_list(raw_loc) if not _is_generic_raw_loc(str(l))]
    loc_str = ", ".join(loc_items) if loc_items else (
        str(raw_loc).strip() if raw_loc and not is_placeholder(raw_loc) and not _is_generic_raw_loc(str(raw_loc)) else ""
    )

    raw_np = extracted.get("notice_period") or extracted.get("notice") or extracted.get("np")
    notice_period_str = str(raw_np).strip() if raw_np and not is_placeholder(raw_np) else ""

    final_cjd = client_jd_id or str(extracted.get("client_jd_id") or extracted.get("client_req_id") or extracted.get("req_id") or "").strip() or ""

    # Rule 6 & Rule 7: To/Cc vs POC and Domain-based check
    # client_poc must NEVER be assigned an internal company domain address
    client_poc = None
    client_lead_poc = None

    if ctx.from_email and not is_internal_domain(ctx.from_email):
        client_poc = ctx.from_email
        client_lead_poc = ctx.from_email

    if not client_poc and ctx.cc_emails:
        for cc in ctx.cc_emails:
            if cc and not is_internal_domain(cc):
                client_poc = cc
                client_lead_poc = cc
                break

    if not client_poc and ctx.to_emails:
        for to_addr in ctx.to_emails:
            if to_addr and not is_internal_domain(to_addr):
                client_poc = to_addr
                client_lead_poc = to_addr
                break

    to_join = ", ".join(ctx.to_emails) if ctx.to_emails else ""
    cc_join = ", ".join(ctx.cc_emails) if ctx.cc_emails else ""

    return format_metaforge_requirement(
        job_id=job_id,
        demand_received_date=demand_date_str,
        internal_poc=internal_poc_default,
        requirement_from=requirement_from,
        client_jd_id=final_cjd,
        client_lead_poc=client_lead_poc or "",
        client_poc=client_poc or "",
        job_title=job_title or "",
        experience=experience_raw or "",
        location=loc_str,
        notice_period=notice_period_str,
        number_of_positions=n_int,
        mandatory_skills=extracted_mand_list,
        skills=extracted_soft_list,
        body_text=body_text,
        extracted=extracted,
        email_subject=email_subject,
        email_body_plain=email_body_plain,
        email_body_html=email_body_html,
        email_received_iso=email_received_iso,
        email_to=to_join,
        email_cc=cc_join,
    )


def format_metaforge_requirement(
    *,
    job_id: str,
    demand_received_date: str,
    internal_poc: str,
    requirement_from: str,
    client_jd_id: str,
    client_lead_poc: str,
    client_poc: str,
    job_title: str,
    experience: str,
    location: str,
    notice_period: str,
    number_of_positions: int | None,
    mandatory_skills: list[str],
    skills: list[str],
    body_text: str,
    extracted: dict[str, Any],
    email_subject: str = "",
    email_body_plain: str = "",
    email_body_html: str = "",
    email_received_iso: str = "",
    email_to: str = "",
    email_cc: str = "",
) -> dict[str, Any]:
    """
    Format requirement into MetaForge dictionary payload with zero fabricated defaults.
    """
    # Rule 1 & Rule 3: Budget min/max and currency (None if not stated)
    budget_currency = None
    yearly_budget: int | None = None
    yearly_budget_min: int | None = None
    yearly_budget_max: int | None = None
    monthly_budget: int | None = None
    monthly_budget_min: int | None = None
    monthly_budget_max: int | None = None

    budget_raw = str(
        extracted.get("budget_text")
        or extracted.get("budget")
        or extracted.get("monthly_budget_text")
        or extracted.get("rate")
        or extracted.get("ctc")
        or extracted.get("billing_rate")
        or ""
    ).strip() or None

    if budget_raw and (
        len(budget_raw) > 80
        or "\n" in budget_raw
        or any(w in budget_raw.lower() for w in ("dear", "kindly", "hello", "hi ", "regards", "candidate", "partner", "submission", "resume", "pls ensure", "subject line"))
    ):
        budget_raw = None

    parsed_b = parse_budget_fields(budget_raw or body_text or "")
    if not budget_raw and parsed_b.get("budget_display"):
        budget_raw = parsed_b.get("budget_display")
    if not is_strict_field_mapping() or lpa_implies_inr():
        if extracted.get("yearly_budget_max") is not None or extracted.get("yearly_budget_min") is not None or parsed_b.get("budget_inr_lpa_max") is not None:
            budget_currency = str(parsed_b.get("budget_currency") or "INR")
    else:
        budget_currency = parsed_b.get("budget_currency") or extracted.get("budget_currency") or None

    def _parse_int_safe(val: Any) -> int | None:
        if val is None or is_placeholder(val):
            return None
        try:
            return int(str(val).replace(",", "").strip())
        except (ValueError, TypeError):
            m = re.search(r"\d+", str(val).replace(",", ""))
            return int(m.group(0)) if m else None

    # Yearly budget
    yearly_budget_min = _parse_int_safe(extracted.get("yearly_budget_min")) or _parse_int_safe(parsed_b.get("budget_inr_lpa_min"))
    yearly_budget_max = _parse_int_safe(extracted.get("yearly_budget_max")) or _parse_int_safe(parsed_b.get("budget_inr_lpa_max"))
    if yearly_budget_min is None and yearly_budget_max is None and extracted.get("yearly_budget") is not None:
        yb_val = _parse_int_safe(extracted.get("yearly_budget"))
        if yb_val is not None:
            yearly_budget_min = yb_val
            yearly_budget_max = yb_val

    yearly_budget = yearly_budget_max if yearly_budget_max is not None else yearly_budget_min

    # Monthly budget
    monthly_budget_min = _parse_int_safe(extracted.get("monthly_budget_min")) or _parse_int_safe(parsed_b.get("budget_inr_lpm_min"))
    monthly_budget_max = _parse_int_safe(extracted.get("monthly_budget_max")) or _parse_int_safe(parsed_b.get("budget_inr_lpm_max"))
    if monthly_budget_min is None and monthly_budget_max is None and extracted.get("monthly_budget") is not None:
        mb_val = _parse_int_safe(extracted.get("monthly_budget"))
        if mb_val is not None:
            monthly_budget_min = mb_val
            monthly_budget_max = mb_val

    monthly_budget = monthly_budget_max if monthly_budget_max is not None else monthly_budget_min

    # Ensure budget_raw is clean and never an email dump
    if not budget_raw or len(str(budget_raw)) > 80 or "\n" in str(budget_raw) or any(w in str(budget_raw).lower() for w in ("dear", "kindly", "hello", "hi ", "regards", "candidate", "partner")):
        if monthly_budget is not None:
            budget_raw = f"{monthly_budget:,} / month" if isinstance(monthly_budget, int) else f"{monthly_budget} / month"
        elif yearly_budget is not None:
            budget_raw = f"{yearly_budget} LPA"
        else:
            budget_raw = None

    # Rule 4: Experience level alignment
    exp_level = derive_experience_level_from_text_or_years(
        experience, str(extracted.get("experience_level") or "")
    )
    exp_min, exp_max = extract_min_max_experience(experience)

    # Rule 1: Employment type (None if not stated)
    emp_type_raw = extracted.get("employment_type")
    employment_type = None
    if emp_type_raw:
        s_emp = str(emp_type_raw).strip().lower()
        if "full" in s_emp or "permanent" in s_emp:
            employment_type = "Full Time"
        elif "contract" in s_emp or "c2h" in s_emp:
            employment_type = "Contract"

    # Rule 5: Work mode classification
    raw_wm = extracted.get("work_mode") or extracted.get("work_mode_text")
    work_mode = _norm_work_mode(raw_wm, body_text)
    work_mode_text = str(raw_wm).strip() if raw_wm and not is_placeholder(raw_wm) else None

    # Rule 1: Priority (None if not stated)
    raw_p = extracted.get("priority")
    priority = None
    if raw_p and not is_placeholder(raw_p):
        p_u = str(raw_p).strip().upper()
        if re.search(r"\bHIGH\b", p_u):
            priority = "HIGH"
        elif re.search(r"\bMEDIUM\b", p_u):
            priority = "MEDIUM"
        elif re.search(r"\bLOW\b", p_u):
            priority = "LOW"
    elif not is_strict_field_mapping():
        if "high priority" in body_text.lower() or "urgent" in body_text.lower() or "p1" in body_text.lower():
            priority = "HIGH"
        elif "medium priority" in body_text.lower() or "p2" in body_text.lower():
            priority = "MEDIUM"
        elif "low priority" in body_text.lower() or "p3" in body_text.lower():
            priority = "LOW"
    else:
        m_p = re.search(r"\b(high|medium|low)\s+priority\b|\bpriority\s*[:\-]\s*(high|medium|low)\b", body_text, re.IGNORECASE)
        if m_p:
            priority = (m_p.group(1) or m_p.group(2)).upper()

    # Demand type
    if is_strict_field_mapping():
        tod_raw = extracted.get("type_of_demand")
        demand_type = str(tod_raw).lower() if tod_raw and not is_placeholder(tod_raw) else None
    else:
        demand_type = "single"
        if number_of_positions is not None:
            if number_of_positions >= 10:
                demand_type = "bulk"
            elif number_of_positions >= 2:
                demand_type = "multiple"

    raw_st = (extracted.get("job_status") or extracted.get("raw_status") or "").strip().lower()
    if raw_st in ("hold", "on hold", "kindly hold", "paused", "pause"):
        job_status = "hold"
    elif raw_st in ("closed", "close", "cancel", "cancelled", "filled"):
        job_status = "closed"
    elif raw_st in ("reopen", "re-open", "resumed", "resume", "active"):
        job_status = "open"
    elif not raw_st or raw_st in ("none", "null"):
        from status_tracker import detect_status_keyword
        status_kw = detect_status_keyword(email_subject, body_text)
        job_status = status_kw if status_kw else "open"
    else:
        job_status = raw_st

    conf_val = extracted.get("confidence")
    final_conf = float(conf_val) if conf_val is not None else (1.0 if not is_strict_field_mapping() else None)

    result: dict[str, Any] = {
        "pipeline_extracted": True,
        "job_id": job_id,
        "demand_received_date": demand_received_date,
        "internal_poc": internal_poc,
        "requirement_from": requirement_from,
        "client_jd_id": client_jd_id or None,
        "client_lead_poc": client_lead_poc,
        "client_poc": client_poc,
        "job_title": job_title or None,
        "job_status": job_status,
        "confidence": final_conf,
        "closed_date": None,
        "type_of_demand": demand_type,
        "priority": priority,
        "number_of_positions": number_of_positions,
        "experience_level": exp_level,
        "employment_type": employment_type,
        "budget": budget_raw,
        "budget_text": budget_raw,
        "budget_currency": budget_currency,
        "yearly_budget": yearly_budget,
        "yearly_budget_min": yearly_budget_min,
        "yearly_budget_max": yearly_budget_max,
        "monthly_budget": monthly_budget,
        "monthly_budget_min": monthly_budget_min,
        "monthly_budget_max": monthly_budget_max,
        "work_mode": work_mode or work_mode_text,
        "work_mode_text": work_mode_text,
        "location": location or None,
        "overall_experience": experience or None,
        "experience": experience or None,
        "experience_text": extracted.get("experience_text") or experience or None,
        "overall_experience_min": exp_min,
        "overall_experience_max": exp_max,
        "notice_period": notice_period or None,
        "mandatory_skills": mandatory_skills,
        "skills": skills,
    }

    subj = str(email_subject or "").strip()
    if subj:
        result["subject"] = subj
    plain_arc = str(email_body_plain or "").strip()
    html_arc = str(email_body_html or "").strip()
    if plain_arc:
        result["bodyText"] = plain_arc
    elif str(body_text or "").strip():
        result["bodyText"] = str(body_text).strip()
    if html_arc:
        result["bodyHtml"] = html_arc
    rdt = str(email_received_iso or "").strip()
    if rdt:
        result["receivedDateTime"] = rdt
    fe = str(client_lead_poc or "").strip()
    if fe:
        result["from"] = fe
    tos = str(email_to or "").strip()
    if tos:
        result["to"] = tos
    ccs = str(email_cc or "").strip()
    if ccs:
        result["cc"] = ccs
    if extracted.get("processing_note"):
        result["processing_note"] = extracted["processing_note"]
    if extracted.get("reconciliation_status"):
        result["reconciliation_status"] = extracted["reconciliation_status"]

    return result

