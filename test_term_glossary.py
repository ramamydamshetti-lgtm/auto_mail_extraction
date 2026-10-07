"""
Unit tests for TermGlossary & Canonical Term Mappings.
"""

import pytest
from glossary import TermGlossary


def test_canonical_field_aliases():
    """Verify alias to canonical field mappings."""
    assert TermGlossary.get_canonical_field("NP") == "notice_period"
    assert TermGlossary.get_canonical_field("notice period") == "notice_period"
    assert TermGlossary.get_canonical_field("YOE") == "experience"
    assert TermGlossary.get_canonical_field("overall exp") == "experience"
    assert TermGlossary.get_canonical_field("WFH") == "work_mode"
    assert TermGlossary.get_canonical_field("C2H") == "employment_type"
    assert TermGlossary.get_canonical_field("LPA") == "budget"
    assert TermGlossary.get_canonical_field("primary skills") == "mandatory_skills"
    assert TermGlossary.get_canonical_field("secondary skills") == "soft_skills"
    assert TermGlossary.get_canonical_field("preferred skills") == "soft_skills"


def test_value_normalizations():
    """Verify value mapping for work mode, employment type, and budget unit."""
    assert TermGlossary.normalize_work_mode("WFH") == "Remote"
    assert TermGlossary.normalize_work_mode("onsite") == "On-site"
    assert TermGlossary.normalize_employment_type("C2H") == "Contract"
    assert TermGlossary.normalize_employment_type("FTE") == "Full-time"
    assert TermGlossary.normalize_budget_unit("25 LPA") == "LPA"
    assert TermGlossary.normalize_budget_unit("50k/pm") == "Monthly"


def test_strict_grounded_absence_rule():
    """
    CRITICAL: Verify that when terms/values are absent, None is returned.
    Glossary is ONLY used when values are actually present in source text.
    """
    assert TermGlossary.get_canonical_field("") is None
    assert TermGlossary.get_canonical_field(None) is None
    assert TermGlossary.normalize_work_mode(None) is None
    assert TermGlossary.normalize_work_mode("") is None
    assert TermGlossary.normalize_employment_type(None) is None
    assert TermGlossary.normalize_budget_unit(None) is None


def test_constructed_prompt_contains_glossary_and_hardcoded_terms():
    """
    Constructs the actual prompt requirement_parser.py sends to LLM.
    Confirms:
    1. Glossary-only terms (e.g. 'buyout', 'subcon', 'pay rate') appear in constructed prompt text.
    2. All original hardcoded terms ('LWD', 'immediate joiner', 'base location') remain unchanged.
    3. The new additive section header is present.
    """
    from requirement_parser import build_parser_system_prompt

    prompt_text = build_parser_system_prompt()

    # 1. Section Header present
    assert "Additional recognized terminology (may overlap with terms above):" in prompt_text

    # 2. Glossary-only terms appear in constructed prompt
    assert "buyout" in prompt_text
    assert "subcon" in prompt_text
    assert "pay rate" in prompt_text

    # 3. Original hardcoded terms remain unchanged in prompt text
    assert "LWD" in prompt_text or "lwd" in prompt_text
    assert "immediate joiner" in prompt_text
    assert "serving NP" in prompt_text or "serving np" in prompt_text
    assert "base location" in prompt_text
    assert "ECTC" in prompt_text or "ectc" in prompt_text


def test_single_source_of_truth_propagation():
    """Rule 3.1: Confirm that terms in TermGlossary dynamically propagate to LLM prompt, regex _FIELD_SYNONYMS, and field_mapper."""
    from requirement_parser import _FIELD_SYNONYMS, build_parser_system_prompt
    from field_mapper import _norm_employment

    # 1. Term 'lwd' (last working day) exists in TermGlossary
    assert TermGlossary.get_canonical_field("lwd") == "notice_period"

    # 2. Automatically present in regex _FIELD_SYNONYMS in requirement_parser.py
    assert "lwd" in _FIELD_SYNONYMS["notice_period"]

    # 3. Automatically present in prompt supplement
    prompt_text = build_parser_system_prompt()
    assert "lwd" in prompt_text

    # 4. Field mapper normalization uses TermGlossary
    assert _norm_employment("sub-con") == "Contract"



