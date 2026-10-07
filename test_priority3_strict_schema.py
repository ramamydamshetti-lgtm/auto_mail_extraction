"""
Unit tests for Priority 3 — Strict Schema & Evidence Rules.
"""

import pytest
from pydantic import ValidationError

from models import (
    EmploymentType,
    ExperienceLevel,
    ExtractionMethodEnum,
    Priority,
    RequirementItem,
    RequirementParseResult,
    WorkMode,
    to_strict_json_schema,
)


def test_strict_json_schema_generation():
    """Verify that generated JSON Schema enforces strict mode and required properties."""
    schema = to_strict_json_schema(RequirementParseResult)
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert "required" in schema
    assert "requirements" in schema["required"]

    # Check nested RequirementItem schema in $defs
    defs = schema.get("$defs", {})
    assert "RequirementItem" in defs
    item_schema = defs["RequirementItem"]
    assert item_schema["additionalProperties"] is False
    assert "required" in item_schema
    # Ensure all properties are marked required in strict schema
    assert set(item_schema["properties"].keys()) == set(item_schema["required"])


def test_reject_extra_fields():
    """Verify that extra/unknown fields in payload raise ValidationError (extra='forbid')."""
    payload = {
        "job_title": "Senior Python Developer",
        "unknown_extra_attribute": "should_fail_validation",
    }
    with pytest.raises(ValidationError) as excinfo:
        RequirementItem.model_validate(payload)
    assert "Extra inputs are not permitted" in str(excinfo.value) or "unknown_extra_attribute" in str(excinfo.value)


def test_reject_invalid_field_extraction_method():
    """Verify that field_extraction_method rejects values outside ExtractionMethodEnum."""
    invalid_payload = {
        "job_title": "Java Architect",
        "field_extraction_method": {
            "job_title": "magic_ai_guessing",  # Invalid method
        },
    }
    with pytest.raises(ValidationError) as excinfo:
        RequirementItem.model_validate(invalid_payload)
    assert "Invalid extraction method" in str(excinfo.value) or "magic_ai_guessing" in str(excinfo.value)


def test_accept_valid_field_extraction_method():
    """Verify that valid ExtractionMethodEnum values are accepted."""
    valid_payload = {
        "job_title": "DevOps Engineer",
        "field_extraction_method": {
            "job_title": "regex_anchor",
            "skills": "ai_semantic",
            "location": "hybrid_regex_ai",
            "budget": "not_found",
        },
    }
    item = RequirementItem.model_validate(valid_payload)
    assert item.field_extraction_method["job_title"] == ExtractionMethodEnum.REGEX_ANCHOR
    assert item.field_extraction_method["skills"] == ExtractionMethodEnum.AI_SEMANTIC
    assert item.field_extraction_method["location"] == ExtractionMethodEnum.HYBRID_REGEX_AI
    assert item.field_extraction_method["budget"] == ExtractionMethodEnum.NOT_FOUND


def test_never_guess_missing_values():
    """Verify that missing fields evaluate to None (null) and are NOT guessed."""
    minimal_payload = {
        "job_title": "React Frontend Developer",
    }
    item = RequirementItem.model_validate(minimal_payload)
    assert item.job_title == "React Frontend Developer"
    assert item.work_mode is None
    assert item.employment_type is None
    assert item.experience_level is None
    assert item.number_of_positions is None
    assert item.yearly_budget_min is None
    assert item.yearly_budget_max is None
    assert item.priority is None
    assert item.location is None
    assert item.mandatory_skills is None


def test_evidence_metadata_for_unextracted_fields():
    """Verify that unextracted fields populate 'not_found' extraction method without fabricated evidence."""
    payload = {
        "job_title": "Fullstack Engineer",
        "field_sources": {"budget": "not_found"},
        "field_evidence_quotes": {"budget": ""},
        "field_extraction_method": {"budget": "not_found"},
    }
    item = RequirementItem.model_validate(payload)
    assert item.field_extraction_method["budget"] == ExtractionMethodEnum.NOT_FOUND
    assert item.field_sources["budget"] == "not_found"
    assert item.field_evidence_quotes["budget"] == ""


def test_verify_evidence_quotes_valid_and_hallucinated():
    """Verify post-extraction evidence quote verification against raw source text."""
    from models import verify_evidence_quotes

    raw_email = "We are looking for a Senior Java Developer in Bangalore with 8+ years experience. Budget: 25 LPA."
    
    # Valid item with genuine quotes
    valid_payload = {
        "job_title": "Senior Java Developer",
        "field_confidence": {"job_title": 0.9, "location": 0.9, "budget": 0.8},
        "field_sources": {"job_title": "email_body", "location": "email_body", "budget": "email_body"},
        "field_evidence_quotes": {
            "job_title": "Senior Java Developer",
            "location": "Bangalore",
            "budget": "Budget: 25 LPA",
            "fake_field": "This text does not exist in email at all!",
        },
    }
    item = RequirementItem.model_validate(valid_payload)
    verified_item = verify_evidence_quotes(item, raw_email)

    # Valid quotes should remain
    assert verified_item.field_evidence_quotes["job_title"] == "Senior Java Developer"
    assert verified_item.field_evidence_quotes["location"] == "Bangalore"
    assert verified_item.field_evidence_quotes["budget"] == "Budget: 25 LPA"

    # Fake/hallucinated quote should be cleared, penalized confidence, and source updated to unverified_ai
    assert verified_item.field_evidence_quotes["fake_field"] == ""
    assert verified_item.field_sources["fake_field"] == "unverified_ai"


def test_openai_wire_format_response_format():
    """Verify that to_strict_json_schema formats properly for OpenAI response_format structured outputs."""
    schema = to_strict_json_schema(RequirementParseResult)
    response_format = {
        "type": "json_schema",
        "json_schema": {
            "name": "requirement_extraction",
            "schema": schema,
            "strict": True,
        },
    }
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True
    assert response_format["json_schema"]["schema"]["additionalProperties"] is False
    assert "requirements" in response_format["json_schema"]["schema"]["required"]


def test_rule_1_2_no_fabricated_defaults_in_payload():
    """Rule 1.2: Verify no fabricated defaults (Contract, On-site, Mid Senior, High priority, 1 position) survive to payload when source evidence is absent."""
    from field_mapper import EmailContext, map_to_metaforge

    extracted_item = {
        "job_title": "Python Specialist",
        # All optional fields left empty/null
    }
    ctx = EmailContext(
        graph_message_id="msg123",
        internet_message_id="<msg123@client.com>",
        to_emails=["recruiter@metaforgeit.com"],
        cc_emails=[],
        from_email="client@kpmg.com",
        from_name="KPMG Client",
    )
    metaforge_payload = map_to_metaforge(
        extracted=extracted_item,
        ctx=ctx,
        client_display_name="KPMG",
        job_id="REQ-001",
        client_jd_id="KPMG-001",
        email_subject="Requirement for Python Specialist",
        email_body_plain="Looking for Python Specialist",
    )

    assert metaforge_payload["job_title"] == "Python Specialist"
    assert metaforge_payload["employment_type"] is None
    assert metaforge_payload["work_mode"] is None
    assert metaforge_payload["experience_level"] is None
    assert metaforge_payload["priority"] is None
    assert metaforge_payload["number_of_positions"] is None


def test_rule_1_4_enum_strict_5_values_and_ai_normalization():
    """Rule 1.4: Verify ExtractionMethodEnum has strictly 5 values and normalizes raw 'ai' -> 'ai_semantic'."""
    approved_values = {e.value for e in ExtractionMethodEnum}
    expected_approved = {"regex", "ai_semantic", "hybrid_regex_ai", "regex_anchor", "not_found"}
    assert approved_values == expected_approved
    assert "ai" not in approved_values

    # Test raw 'ai' normalization in RequirementItem
    payload = {
        "job_title": "Data Engineer",
        "field_extraction_method": {
            "job_title": "ai",  # Should normalize to ai_semantic
            "skills": "regex",
        },
    }
    item = RequirementItem.model_validate(payload)
    assert item.field_extraction_method["job_title"] == ExtractionMethodEnum.AI_SEMANTIC
    assert item.field_extraction_method["skills"] == ExtractionMethodEnum.REGEX


def test_rule_1_5_relevance_verification_for_evidence_quotes():
    """Rule 1.5: Verify evidence quotes are validated for actual field relevance (e.g. 5 yrs exp attached to location gets flagged)."""
    from models import verify_evidence_quotes

    raw_email = "Need Java Developer. Experience required: 5 years. Location: Bangalore."

    payload = {
        "job_title": "Java Developer",
        "location": ["Bangalore"],
        "field_confidence": {"job_title": 0.9, "location": 0.9},
        "field_sources": {"job_title": "email", "location": "email"},
        "field_evidence_quotes": {
            "job_title": "Java Developer",
            "location": "Experience required: 5 years",  # Irrelevant quote for location!
        },
    }
    item = RequirementItem.model_validate(payload)
    verified_item = verify_evidence_quotes(item, raw_email)

    # Relevant quote for job_title remains
    assert verified_item.field_evidence_quotes["job_title"] == "Java Developer"

    # Irrelevant quote for location is cleared and flagged as unverified
    assert verified_item.field_evidence_quotes["location"] == ""
    assert verified_item.field_sources["location"] == "unverified_ai"


