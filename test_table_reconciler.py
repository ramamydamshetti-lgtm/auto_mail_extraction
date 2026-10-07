"""
Unit tests for Client/Table Cross-check and Reconciliation (Priority 4 Accuracy Rules 4.2 - 4.4).
"""

from pathlib import Path
import pytest
from models import RequirementItem, RequirementParseResult
from table_reconciler import (
    has_expected_table_structure,
    reconcile_parser_results,
    run_client_table_reconciliation,
)


def test_table_structure_detection():
    """Verify special extractor is triggered ONLY when table structure is detected."""
    kpmg_body_with_table = """
    Sr. No | Role | Requirement | Comments
    1 | Java Developer | 5+ yrs exp | Urgent
    """
    assert has_expected_table_structure("KPMG", kpmg_body_with_table) is True

    plain_email_body = "Hi Team, We need a Java Developer for KPMG client in Bangalore."
    assert has_expected_table_structure("KPMG", plain_email_body) is False


def test_reconciliation_agreement():
    """Verify that matching general parser & special extractor results agree."""
    parse_result = RequirementParseResult(requirements=[RequirementItem(job_title="Java Developer")])
    spec_table_roles = [{"role": "Java Developer", "sr_no": "1"}]

    reconciled_env, meta = reconcile_parser_results(parse_result, spec_table_roles, client_name="KPMG")
    assert meta["reconciliation_status"] == "agreed"
    assert reconciled_env.requirements[0].job_title == "Java Developer"
    assert reconciled_env.processing_note is None


def test_reconciliation_conflict_flagged_for_review():
    """
    CRITICAL: Verify that when general parser and special extractor conflict,
    it flags for review and does NOT automatically replace general parser results.
    """
    parse_result = RequirementParseResult(requirements=[RequirementItem(job_title="Senior Python Architect")])
    spec_table_roles = [{"role": "Frontend React Engineer", "sr_no": "1"}]

    reconciled_env, meta = reconcile_parser_results(parse_result, spec_table_roles, client_name="KPMG")

    # Status must be conflict_review_flagged
    assert meta["reconciliation_status"] == "conflict_review_flagged"
    assert meta["conflict_count"] == 1

    # General parser result MUST NOT be replaced!
    assert reconciled_env.requirements[0].job_title == "Senior Python Architect"
    assert "Reconciliation conflict" in reconciled_env.processing_note


def test_special_extractor_not_triggered_for_non_table_email():
    """Rule 4.2 (1): Special extractor must NOT be triggered for non-table emails."""
    parse_result = RequirementParseResult(requirements=[RequirementItem(job_title="DevOps Engineer")])
    plain_body = "We are looking for a DevOps Engineer with Kubernetes experience for KPMG."

    reconciled_env, meta = run_client_table_reconciliation("KPMG", plain_body, parse_result)
    assert meta["ran_special_extractor"] is False
    assert meta["reconciliation_status"] == "not_applicable"
    assert reconciled_env.requirements[0].job_title == "DevOps Engineer"
    assert reconciled_env.processing_note is None


def test_run_reconciliation_agreement_case():
    """Rule 4.2 & 4.3 (2): Agreement case accepted unchanged."""
    table_body = """
    Sr. No
    Role
    Requirement
    Comments
    1
    Java Developer
    5+ years
    Urgent
    """
    parse_result = RequirementParseResult(requirements=[RequirementItem(job_title="Java Developer")])

    reconciled_env, meta = run_client_table_reconciliation("KPMG", table_body, parse_result)
    assert meta["ran_special_extractor"] is True
    assert meta["reconciliation_status"] == "agreed"
    assert reconciled_env.requirements[0].job_title == "Java Developer"
    assert reconciled_env.processing_note is None


def test_run_reconciliation_conflict_case_untouched():
    """Rule 4.4 (3): Conflict case flagged with general result untouched."""
    table_body = """
    Sr. No
    Role
    Requirement
    Comments
    1
    Frontend React Engineer
    3+ years
    Urgent
    """
    parse_result = RequirementParseResult(requirements=[RequirementItem(job_title="Senior Python Architect")])

    reconciled_env, meta = run_client_table_reconciliation("KPMG", table_body, parse_result)
    assert meta["ran_special_extractor"] is True
    assert meta["reconciliation_status"] == "conflict_review_flagged"
    assert meta["conflict_count"] == 1
    # General parser result is untouched!
    assert reconciled_env.requirements[0].job_title == "Senior Python Architect"
    assert "Reconciliation conflict" in reconciled_env.processing_note


def test_special_extractor_exception_resilience(monkeypatch):
    """Task 4 (4): Special extractor raising an exception must NOT break or crash the pipeline."""
    def mock_broken_extractor(text):
        raise ValueError("Simulated table extractor failure")

    monkeypatch.setattr("job_table_extractor.extract_kpmg_style_roles", mock_broken_extractor)

    table_body = """
    Sr. No | Role | Requirement | Comments
    1 | Java Developer | 5+ yrs exp | Urgent
    """
    parse_result = RequirementParseResult(requirements=[RequirementItem(job_title="Java Developer")])

    reconciled_env, meta = run_client_table_reconciliation("KPMG", table_body, parse_result)
    assert meta["ran_special_extractor"] is False
    assert reconciled_env.requirements[0].job_title == "Java Developer"


def test_end_to_end_raw_emails():
    """Use sample emails in raw_emails/ for end-to-end check."""
    raw_dir = Path(__file__).resolve().parent / "raw_emails"
    sample_file = raw_dir / "req_001.txt"
    assert sample_file.exists()
    text = sample_file.read_text(encoding="utf-8")

    parse_result = RequirementParseResult(requirements=[RequirementItem(job_title="Business Analyst")])
    reconciled_env, meta = run_client_table_reconciliation("ITC", text, parse_result)

    # ITC req_001 has no KPMG Sr. No table, so special extractor is skipped gracefully
    assert meta["ran_special_extractor"] is False
    assert reconciled_env.requirements[0].job_title == "Business Analyst"
