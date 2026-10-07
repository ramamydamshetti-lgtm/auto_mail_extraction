"""
Centralized Term Glossary & Canonical Field Normalizer.
Only maps terms/acronyms present in source text; never infers missing values.
"""

from __future__ import annotations

from typing import Any

# Canonical Field Name Alias Mapping
FIELD_ALIASES: dict[str, str] = {
    # Notice Period
    "np": "notice_period",
    "n.p": "notice_period",
    "notice": "notice_period",
    "notice period": "notice_period",
    "joining time": "notice_period",
    "join time": "notice_period",
    "buyout": "notice_period",
    "buying out": "notice_period",
    "lwd": "notice_period",
    "last working day": "notice_period",
    "availability": "notice_period",
    "availability to join": "notice_period",
    "joining availability": "notice_period",
    "serving notice": "notice_period",
    "serving np": "notice_period",
    "immediate joiner": "notice_period",

    # Experience / YOE
    "yoe": "experience",
    "exp": "experience",
    "experience": "experience",
    "total exp": "experience",
    "relevant exp": "experience",
    "overall exp": "experience",
    "over all exp": "experience",
    "overall experience": "experience",
    "over all experience": "experience",
    "years": "experience",
    "years of experience": "experience",
    "years of exp": "experience",
    "level": "experience",

    # Work Mode
    "wfh": "work_mode",
    "work mode": "work_mode",
    "work from home": "work_mode",
    "onsite": "work_mode",
    "on site": "work_mode",
    "hybrid": "work_mode",
    "remote": "work_mode",

    # Employment Type
    "c2h": "employment_type",
    "c2c": "employment_type",
    "fte": "employment_type",
    "full time": "employment_type",
    "full-time": "employment_type",
    "contract": "employment_type",
    "subcon": "employment_type",
    "sub-con": "employment_type",

    # Budget
    "lpa": "budget",
    "budget": "budget",
    "package": "budget",
    "compensation": "budget",
    "comp": "budget",
    "pay rate": "budget",
    "hourly rate": "budget",
    "bill rate": "budget",
    "bill rate per month": "budget",
    "bill rate per month for tpc": "budget",
    "rate / pm": "budget",
    "rate / pm (inr)": "budget",

    # Location
    "location": "location",
    "locations": "location",
    "job location": "location",
    "work location": "location",
    "work loc": "location",
    "preferred location": "location",
    "pref loc": "location",
    "base location": "location",
    "base": "location",
    "wl": "location",
    "place of posting": "location",

    # Job Title
    "job title": "job_title",
    "role name": "job_title",
    "role": "job_title",
    "position title": "job_title",
    "profile": "job_title",

    # Skills
    "skill": "mandatory_skills",
    "skills": "mandatory_skills",
    "skillset": "mandatory_skills",
    "primary skills": "mandatory_skills",
    "must have": "mandatory_skills",
    "must have skills": "mandatory_skills",
    "mandatory skills": "mandatory_skills",
    "technology stack": "mandatory_skills",
    "tech stack": "mandatory_skills",
    "competencies": "mandatory_skills",
    "tools & platforms": "mandatory_skills",
    "secondary skills": "soft_skills",
    "nice to have": "soft_skills",
    "preferred skills": "soft_skills",
    "soft skills": "soft_skills",
}

# Canonical Value Mappings for Value Normalization
WORK_MODE_MAP: dict[str, str] = {
    "wfh": "Remote",
    "work from home": "Remote",
    "remote": "Remote",
    "onsite": "On-site",
    "on site": "On-site",
    "office": "On-site",
    "hybrid": "Hybrid",
}

EMPLOYMENT_TYPE_MAP: dict[str, str] = {
    "c2h": "Contract",
    "c2c": "Contract",
    "contract": "Contract",
    "contractor": "Contract",
    "subcon": "Contract",
    "sub-con": "Contract",
    "fte": "Full-time",
    "full time": "Full-time",
    "full-time": "Full-time",
    "permanent": "Full-time",
}

BUDGET_UNIT_MAP: dict[str, str] = {
    "lpa": "LPA",
    "lakh": "LPA",
    "lakhs": "LPA",
    "inr": "INR",
    "usd": "USD",
    "eur": "EUR",
    "per month": "Monthly",
    "pm": "Monthly",
}

EXPERIENCE_LEVEL_MAP: dict[str, str] = {
    "entry": "Entry Level",
    "entry level": "Entry Level",
    "junior": "Junior Level",
    "junior level": "Junior Level",
    "fresher": "Junior Level",
    "mid": "Mid Level",
    "mid level": "Mid Level",
    "intermediate": "Mid Level",
    "mid-senior": "Mid-Senior Level",
    "mid senior": "Mid-Senior Level",
    "mid-senior level": "Mid-Senior Level",
    "senior": "Senior Level",
    "senior level": "Senior Level",
    "lead": "Senior Level",
    "expert": "Expert Level",
    "expert level": "Expert Level",
    "principal": "Expert Level",
}


class TermGlossary:
    """Centralized glossary manager for canonical term mapping."""

    @classmethod
    def get_field_synonyms(cls, field_name: str) -> tuple[str, ...]:
        """Return all recognized raw terms/aliases mapped to canonical field_name."""
        syns = [alias for alias, f in FIELD_ALIASES.items() if f == field_name]
        return tuple(syns)

    @staticmethod
    def get_canonical_field(term: str) -> str | None:
        """Map raw term/alias to canonical field name if present."""
        if not term:
            return None
        return FIELD_ALIASES.get(term.strip().lower())

    @staticmethod
    def normalize_work_mode(value: str | None) -> str | None:
        """Map raw work mode term to canonical value if present; otherwise return None."""
        if not value or not str(value).strip():
            return None
        val_str = str(value).strip().lower()
        import re
        # F8: If text offers several ("Hybrid/Remote") or is unclear, work_mode is NULL and the text is kept.
        has_hybrid = bool(re.search(r"\b(?:hybrid|partially|[1-4]\s*days?\s*(?:work\s*)?(?:from\s*|in\s*|at\s*)?office)\b", val_str))
        has_remote = bool(re.search(r"\b(?:remote|wfh|work\s+from\s+home)\b", val_str))
        has_onsite = bool(re.search(r"\b(?:onsite|on-site|on\s+site|work\s+from\s+office|wfo|5\s*days\s*office|fully\s+on-site)\b", val_str))

        if sum([has_hybrid, has_remote, has_onsite]) > 1:
            return None  # Multiple options offered (e.g. Hybrid/Remote) -> NULL per F8

        if has_hybrid:
            return "Hybrid"
        if has_remote:
            return "Remote"
        if has_onsite:
            return "On-site"
        return WORK_MODE_MAP.get(val_str)

    @staticmethod
    def normalize_employment_type(value: str | None) -> str | None:
        """Map raw employment type term to canonical value if present; otherwise return None."""
        if not value or not str(value).strip():
            return None
        return EMPLOYMENT_TYPE_MAP.get(str(value).strip().lower())

    @staticmethod
    def normalize_experience_level(value: str | None) -> str | None:
        """Map raw experience level term to canonical value if present; otherwise return None."""
        if not value or not str(value).strip():
            return None
        return EXPERIENCE_LEVEL_MAP.get(str(value).strip().lower())

    @staticmethod
    def normalize_budget_unit(value: str | None) -> str | None:
        """Map raw budget string to canonical currency/unit if present; otherwise return None."""
        if not value or not str(value).strip():
            return None
        val_lower = str(value).strip().lower()
        for k, unit in BUDGET_UNIT_MAP.items():
            if k in val_lower:
                return unit
        return None

    @classmethod
    def get_prompt_supplement(cls) -> str:
        """
        Generate additive glossary instructions for LLM extraction prompt.
        """
        field_to_aliases: dict[str, list[str]] = {}
        for alias, field in FIELD_ALIASES.items():
            field_to_aliases.setdefault(field, []).append(alias)

        lines = ["Additional recognized terminology (may overlap with terms above):"]
        for field, aliases in field_to_aliases.items():
            alias_str = ", ".join(aliases)
            lines.append(f"- {field}: {alias_str}")
        return "\n".join(lines)

