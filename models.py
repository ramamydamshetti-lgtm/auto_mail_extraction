"""
Typed contracts for AI parser output.
Priority 3 — Strict Schema & Evidence Rules.
"""

from __future__ import annotations

from enum import Enum
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from glossary import TermGlossary
from config import is_placeholder


class ExtractionMethodEnum(str, Enum):
    REGEX = "regex"
    AI_SEMANTIC = "ai_semantic"
    HYBRID_REGEX_AI = "hybrid_regex_ai"
    REGEX_ANCHOR = "regex_anchor"
    NOT_FOUND = "not_found"


class EmploymentType(str, Enum):
    FULL_TIME = "Full-time"
    CONTRACT = "Contract"


class ExperienceLevel(str, Enum):
    ENTRY = "Entry Level"
    JUNIOR = "Junior Level"
    MID = "Mid Level"
    MID_SENIOR = "Mid-Senior Level"
    SENIOR = "Senior Level"
    EXPERT = "Expert Level"


class WorkMode(str, Enum):
    ON_SITE = "On-site"
    REMOTE = "Remote"
    HYBRID = "Hybrid"


class Priority(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class RequirementItem(BaseModel):
    """Single extracted requirement from one email with strict schema enforcement."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    job_title: str | None = None
    number_of_positions: int | None = Field(default=None, ge=1)
    experience_level: ExperienceLevel | None = None
    employment_type: EmploymentType | None = None
    work_mode: WorkMode | None = None
    work_mode_text: str | None = None
    location: list[str] | None = None
    yearly_budget: int | float | str | None = None
    yearly_budget_min: int | None = Field(default=None, ge=0)
    yearly_budget_max: int | None = Field(default=None, ge=0)
    monthly_budget: int | float | str | None = None
    monthly_budget_min: int | None = Field(default=None, ge=0)
    monthly_budget_max: int | None = Field(default=None, ge=0)
    budget_currency: str | None = None
    budget_text: str | None = None
    mandatory_skills: list[str] | None = None
    soft_skills: list[str] | None = Field(default=None, alias="skills")

    # Experience details (F2)
    experience_text: str | None = None
    experience_min_years: float | int | None = None
    experience_max_years: float | int | None = None

    # Legacy & metadata fields
    req_id: str | None = Field(
        default=None,
        description="The requisition/request ID that the CLIENT assigned, only if the email labels it as an ID. Never a budget, salary range, experience, date, phone number, or count. If not clearly present, null.",
    )
    raw_status: str | None = None
    budget: str | None = None
    experience: str | None = None
    overall_experience: str | None = None
    notice_period: str | None = None
    engagement_type: str | None = None
    contract_duration: str | None = None
    priority: Priority | None = None
    client_name: str | None = None
    confidence: float = Field(default=1.0, ge=0, le=1)

    field_confidence: dict[str, float] = Field(default_factory=dict)
    field_sources: dict[str, str] = Field(default_factory=dict)
    field_evidence_quotes: dict[str, str] = Field(default_factory=dict)
    field_extraction_method: dict[str, ExtractionMethodEnum] = Field(default_factory=dict)

    # Two-way verification & recall guard fields (V1-V4)
    verification_status: str | None = None
    recovered_by: dict[str, str] = Field(default_factory=dict)
    review_candidates: dict[str, Any] = Field(default_factory=dict)
    possible_miss: bool = False
    client_jd_id: str | None = None

    @model_validator(mode="before")
    @classmethod
    def preserve_and_map_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        d = dict(data)

        # 1. client_jd_id / req_id
        cid = d.get("client_jd_id") or d.get("client_req_id") or d.get("req_id")
        if cid and not is_placeholder(cid):
            cid_str = str(cid).strip()
            if not d.get("req_id"):
                d["req_id"] = cid_str
            if not d.get("client_jd_id"):
                d["client_jd_id"] = cid_str

        # 2. positions / number_of_positions
        n_pos = d.get("number_of_positions") if d.get("number_of_positions") is not None else (d.get("positions") if d.get("positions") is not None else d.get("open_positions"))
        if n_pos is not None and not is_placeholder(n_pos):
            try:
                d["number_of_positions"] = int(n_pos)
            except (ValueError, TypeError):
                m = re.search(r"\d+", str(n_pos))
                if m:
                    d["number_of_positions"] = int(m.group(0))

        # 3. experience / experience_text / overall_experience
        exp = d.get("experience_text") or d.get("overall_experience") or d.get("experience") or d.get("total_experience") or d.get("exp")
        if exp and not is_placeholder(exp):
            exp_str = str(exp).strip()
            if not d.get("experience_text"):
                d["experience_text"] = exp_str
            if not d.get("overall_experience"):
                d["overall_experience"] = exp_str
            if not d.get("experience"):
                d["experience"] = exp_str
            if d.get("experience_min_years") is None and d.get("experience_max_years") is None:
                from two_way_verifier import parse_experience_digits
                mn, mx = parse_experience_digits(exp_str)
                if mn is not None:
                    d["experience_min_years"] = mn
                if mx is not None:
                    d["experience_max_years"] = mx

        # 4. budget / budget_text
        bgt = d.get("budget_text") or d.get("budget") or d.get("monthly_budget_text") or d.get("rate") or d.get("ctc") or d.get("billing_rate")
        if bgt and not is_placeholder(bgt):
            bgt_str = str(bgt).strip()
            if not d.get("budget_text"):
                d["budget_text"] = bgt_str
            if not d.get("budget"):
                d["budget"] = bgt_str

        # 5. work_mode_text / work_mode
        wm = d.get("work_mode_text") or d.get("work_mode")
        if wm and not is_placeholder(wm):
            wm_str = str(wm).strip()
            if not d.get("work_mode_text"):
                d["work_mode_text"] = wm_str
            if not d.get("work_mode"):
                d["work_mode"] = wm_str

        # 6. location
        loc = d.get("location") or d.get("job_location") or d.get("work_location") or d.get("base_location") or d.get("city")
        if loc and not is_placeholder(loc) and not d.get("location"):
            d["location"] = loc

        # 7. skills
        m_skills = d.get("mandatory_skills") or d.get("must_have_skills") or d.get("primary_skills") or d.get("key_skills")
        if m_skills and not d.get("mandatory_skills"):
            d["mandatory_skills"] = m_skills

        s_skills = d.get("soft_skills") or d.get("skills") or d.get("secondary_skills") or d.get("nice_to_have_skills")
        if s_skills and not d.get("soft_skills") and not d.get("skills"):
            d["soft_skills"] = s_skills

        return d

    @field_validator("job_title", mode="before")
    @classmethod
    def clean_title(cls, value: object) -> str | None:
        if value is None:
            return None
        from config import is_placeholder
        text = str(value).strip()
        if is_placeholder(text):
            return None
        return text if text else None

    @field_validator(
        "experience",
        "experience_text",
        "notice_period",
        "client_name",
        "engagement_type",
        "contract_duration",
        "budget",
        "budget_text",
        "budget_currency",
        "work_mode_text",
        "overall_experience",
        mode="before",
    )
    @classmethod
    def coerce_optional_strings(cls, value: object) -> str | None:
        if value is None:
            return None
        from config import is_placeholder
        text = str(value).strip()
        if is_placeholder(text):
            return None
        return text

    @field_validator("location", "mandatory_skills", "soft_skills", mode="before")
    @classmethod
    def normalize_list_fields(cls, value: object) -> list[str] | None:
        if value is None:
            return None
        from config import is_placeholder
        if isinstance(value, list):
            res = [str(v).strip() for v in value if not is_placeholder(v)]
            return res if res else None
        text = str(value).strip()
        if is_placeholder(text):
            return None
        parts = re.split(r"[,\n;/|]+", text)
        res = [p.strip() for p in parts if not is_placeholder(p.strip())]
        return res if res else None

    @field_validator("employment_type", mode="before")
    @classmethod
    def normalize_employment_type(cls, value: object) -> str | None:
        if value is None:
            return None
        from config import is_placeholder
        text = str(value).strip()
        if is_placeholder(text):
            return None
        s = text.lower()
        res = TermGlossary.normalize_employment_type(s)
        if res == "Full-time":
            return EmploymentType.FULL_TIME.value
        if res == "Contract":
            return EmploymentType.CONTRACT.value
        return None

    @field_validator("work_mode", mode="before")
    @classmethod
    def normalize_work_mode(cls, value: object) -> str | None:
        if value is None:
            return None
        from config import is_placeholder
        text = str(value).strip()
        if is_placeholder(text):
            return None
        s = text.lower()
        res = TermGlossary.normalize_work_mode(s)
        if res == "On-site":
            return WorkMode.ON_SITE.value
        if res == "Remote":
            return WorkMode.REMOTE.value
        if res == "Hybrid":
            return WorkMode.HYBRID.value
        return None

    @field_validator("experience_level", mode="before")
    @classmethod
    def normalize_experience_level(cls, value: object) -> str | None:
        if value is None:
            return None
        from config import is_placeholder
        text = str(value).strip()
        if is_placeholder(text):
            return None
        s = text.lower()
        if s in {"entry", "entry level", "junior", "fresher", "junior level"}:
            return ExperienceLevel.ENTRY.value
        if s in {"mid", "mid level", "intermediate"}:
            return ExperienceLevel.MID.value
        if s in {"mid-senior", "mid senior", "mid-senior level"}:
            return ExperienceLevel.MID_SENIOR.value
        if s in {"senior", "senior level"}:
            return ExperienceLevel.SENIOR.value
        if s in {"expert", "expert level", "lead", "principal"}:
            return ExperienceLevel.EXPERT.value
        return None

    @field_validator("priority", mode="before")
    @classmethod
    def normalize_priority(cls, value: object) -> str | None:
        if value is None:
            return None
        from config import is_placeholder
        text = str(value).strip()
        if is_placeholder(text):
            return None
        s = text.upper()
        # Whole-word matches only (so 'below' does not match 'low')
        if re.search(r"\bHIGH\b", s):
            return Priority.HIGH.value
        if re.search(r"\bMEDIUM\b", s):
            return Priority.MEDIUM.value
        if re.search(r"\bLOW\b", s):
            return Priority.LOW.value
        return None

    @field_validator(
        "yearly_budget_min",
        "yearly_budget_max",
        "monthly_budget_min",
        "monthly_budget_max",
        mode="before",
    )
    @classmethod
    def parse_budget_lakh_to_int(cls, value: object) -> int | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return int(value)
        from config import is_placeholder, is_strict_field_mapping
        text = str(value).strip()
        if is_placeholder(text):
            return None
        m = re.search(r"(\d+(?:\.\d+)?)", text)
        if not m:
            return None
        n = float(m.group(1))
        low = text.lower()
        if "k" in low and "lakh" not in low and "lpa" not in low:
            return int(n * 1000)
        # Under strict mapping, unit conversions are prohibited for whole numbers, but decimal lakhs (e.g. 1.25L) must not truncate to 1
        if ("lakh" in low or "lpa" in low or "l" in low) and n < 100:
            if not is_strict_field_mapping() or n != int(n):
                return int(n * 100000)
        return int(n)

    @field_validator("field_confidence", mode="before")
    @classmethod
    def normalize_field_confidence(cls, value: object) -> dict[str, float]:
        if not isinstance(value, dict):
            return {}
        out: dict[str, float] = {}
        for k, v in value.items():
            try:
                out[str(k)] = max(0.0, min(1.0, float(v)))
            except (TypeError, ValueError):
                continue
        return out

    @field_validator("field_sources", mode="before")
    @classmethod
    def normalize_field_sources(cls, value: object) -> dict[str, str]:
        if not isinstance(value, dict):
            return {}
        out: dict[str, str] = {}
        for k, v in value.items():
            key = str(k or "").strip()
            val = str(v or "").strip()
            if key and val:
                out[key] = val
        return out

    @field_validator("field_evidence_quotes", mode="before")
    @classmethod
    def normalize_field_evidence_quotes(cls, value: object) -> dict[str, str]:
        if not isinstance(value, dict):
            return {}
        out: dict[str, str] = {}
        for k, v in value.items():
            key = str(k or "").strip()
            val = str(v or "").strip()
            if key:
                out[key] = val
        return out

    @field_validator("field_extraction_method", mode="before")
    @classmethod
    def validate_field_extraction_method(cls, value: object) -> dict[str, ExtractionMethodEnum]:
        if not isinstance(value, dict):
            return {}
        out: dict[str, ExtractionMethodEnum] = {}
        allowed = {e.value for e in ExtractionMethodEnum}
        for k, v in value.items():
            key = str(k or "").strip()
            val = str(v or "").strip().lower()
            if not val:
                continue
            if val not in allowed:
                raise ValueError(
                    f"Invalid extraction method '{v}' for field '{k}'. "
                    f"Allowed values are: {sorted(list(allowed))}"
                )
            out[key] = ExtractionMethodEnum(val)
        return out


class RequirementParseResult(BaseModel):
    """Validated parser response envelope with extra='forbid'."""

    model_config = ConfigDict(extra="forbid")

    requirements: list[RequirementItem] = Field(default_factory=list)
    overall_confidence: float = Field(default=0.0, ge=0, le=1)
    multi_requirement_note: str | None = None
    is_multi_role: bool = False
    processing_note: str | None = None


class DashboardRequirement24(BaseModel):
    """Strict 24-field schema for dashboard payload."""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    demand_received_date: str | None = None
    internal_poc_email: str | None = None
    internal_poc: str | None = None
    sla: str | None = None
    requirement_from: str
    client_jd_id: str
    client_lead_poc_email: str | None = None
    client_poc_emails: str | None = None
    job_title: str | None = None
    job_status: str = "open"
    closed_date: str | None = None
    type_of_demand: Literal["single", "multiple", "bulk"] = "single"
    priority: str | None = None
    number_of_positions: int | None = Field(default=None, ge=1)
    experience_level: str | None = None
    employment_type: str | None = None
    budget_currency: Literal["INR", "USD", "EUR"] | None = None
    yearly_budget: int | str | None = Field(default=None)
    monthly_budget: int | str | None = Field(default=None)
    work_mode: str | None = None
    location: str | None = None
    overall_experience: str | None = None
    notice_period: str | None = None
    mandatory_skills: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)


def to_strict_json_schema(model_cls: type[BaseModel]) -> dict[str, Any]:
    """
    Generate an OpenAI Strict Structured Outputs JSON schema from a Pydantic model.
    - Sets additionalProperties: False on all objects.
    - Ensures required includes all properties for every object.
    - Recursively processes $defs/definitions.
    """
    schema = model_cls.model_json_schema()
    return _make_schema_strict(schema)


def _make_schema_strict(schema: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(schema, dict):
        return schema

    s = dict(schema)

    if "$defs" in s and isinstance(s["$defs"], dict):
        s["$defs"] = {k: _make_schema_strict(v) for k, v in s["$defs"].items()}
    if "definitions" in s and isinstance(s["definitions"], dict):
        s["definitions"] = {k: _make_schema_strict(v) for k, v in s["definitions"].items()}

    if s.get("type") == "object" or "properties" in s:
        s["type"] = "object"
        s["additionalProperties"] = False
        props = s.get("properties", {})
        s["properties"] = {k: _make_schema_strict(v) for k, v in props.items()}
        s["required"] = list(props.keys())

    if s.get("type") == "array" and "items" in s:
        if isinstance(s["items"], dict):
            s["items"] = _make_schema_strict(s["items"])

    for key in ("anyOf", "oneOf", "allOf"):
        if key in s and isinstance(s[key], list):
            s[key] = [_make_schema_strict(v) for v in s[key]]

    return s


def _is_quote_relevant_to_field(field_name: str, quote: str, field_value: Any) -> bool:
    if not quote or not str(quote).strip():
        return True
    q = str(quote).lower().strip()
    fn = field_name.lower().strip()

    if field_value is not None:
        if isinstance(field_value, list):
            if any(str(v).lower() in q for v in field_value if v):
                return True
        elif isinstance(field_value, (str, int, float)):
            v_str = str(field_value).lower().strip()
            if v_str and v_str in q:
                return True

    if "location" in fn:
        loc_kw = ("location", "loc", "remote", "onsite", "on-site", "hybrid", "wfh", "city", "site", "office")
        return any(k in q for k in loc_kw)

    if any(k in fn for k in ("experience", "exp_level", "overall_experience")):
        exp_kw = ("exp", "yrs", "years", "senior", "junior", "lead", "mid", "fresher", "entry", "level", "year")
        return any(k in q for k in exp_kw)

    if "budget" in fn:
        bgt_kw = ("lpa", "lpm", "ctc", "budget", "inr", "usd", "$", "₹", "salary", "pay", "rate", "k", "lakh", "lakhs", "per annum", "per month", "per hour")
        return any(k in q for k in bgt_kw)

    if "skills" in fn or "skill" in fn:
        skl_kw = ("skill", "skills", "mandatory", "required", "knowledge", "experience in", "hands-on", "technologies", "stack")
        return any(k in q for k in skl_kw)

    if "employment" in fn or "engagement" in fn:
        emp_kw = ("full-time", "full time", "permanent", "contract", "c2h", "subcon", "sub-con", "fte", "duration")
        return any(k in q for k in emp_kw)

    if "work_mode" in fn:
        wm_kw = ("remote", "wfh", "hybrid", "onsite", "on-site", "office", "rto")
        return any(k in q for k in wm_kw)

    if "job_title" in fn or "title" in fn or "role" in fn:
        title_kw = ("role", "title", "position", "developer", "engineer", "lead", "manager", "architect", "analyst", "consultant", "specialist", "designer", "tester", "admin")
        return any(k in q for k in title_kw)

    return True


def verify_evidence_quotes(
    item: RequirementItem,
    raw_text: str,
) -> RequirementItem:
    """
    Post-extraction evidence verification (Rule 1.5).
    - Enforces metadata field presence (field_confidence, field_sources, field_evidence_quotes, field_extraction_method).
    - Verifies that quotes in `field_evidence_quotes` actually exist in `raw_text`.
    - Confirms quotes are relevant to and support the specific field value they are attached to.
    """
    norm_raw = re.sub(r"\s+", " ", (raw_text or "").lower()).strip()

    evidence_quotes = dict(item.field_evidence_quotes or {})
    confidence_map = dict(item.field_confidence or {})
    sources_map = dict(item.field_sources or {})
    method_map = dict(item.field_extraction_method or {})

    primary_fields = [
        "job_title", "number_of_positions", "experience_level", "employment_type",
        "work_mode", "location", "yearly_budget_min", "yearly_budget_max",
        "monthly_budget_min", "monthly_budget_max", "mandatory_skills", "soft_skills",
        "experience", "overall_experience", "notice_period", "budget", "priority"
    ]

    for field in primary_fields:
        val = getattr(item, field, None)
        if val is not None:
            if field not in confidence_map:
                confidence_map[field] = float(item.confidence or 1.0)
            if field not in sources_map:
                sources_map[field] = "email_body"
            if field not in evidence_quotes:
                evidence_quotes[field] = ""
            if field not in method_map:
                method_map[field] = ExtractionMethodEnum.AI_SEMANTIC
        else:
            if field not in confidence_map:
                confidence_map[field] = 0.0
            if field not in sources_map:
                sources_map[field] = "not_found"
            if field not in evidence_quotes:
                evidence_quotes[field] = ""
            if field not in method_map:
                method_map[field] = ExtractionMethodEnum.NOT_FOUND

    for field, quote in list(evidence_quotes.items()):
        if not quote or str(quote).strip() == "":
            continue

        norm_quote = re.sub(r"\s+", " ", str(quote).lower()).strip()
        field_val = getattr(item, field, None)

        # 1. Textual presence check
        present = False
        if norm_raw and norm_quote in norm_raw:
            present = True
        elif norm_raw:
            words = norm_quote.split()
            if len(words) >= 3 and " ".join(words[:min(10, len(words))]) in norm_raw:
                present = True

        # 2. Field relevance check
        relevant = _is_quote_relevant_to_field(field, quote, field_val)

        if not present or not relevant:
            evidence_quotes[field] = ""
            if field in confidence_map:
                confidence_map[field] = round(max(0.0, float(confidence_map[field]) * 0.5), 2)
            sources_map[field] = "unverified_ai"

    item.field_evidence_quotes = evidence_quotes
    item.field_confidence = confidence_map
    item.field_sources = sources_map
    item.field_extraction_method = method_map
    return item

