"""
Unit tests for Junk Detector: Promotional & Job-Seeker Email Filtering Rules.
"""

import pytest
from intake_gates import is_job_seeker_email, is_promotional_email, pre_classify_block_reason


def test_promotional_email_detection():
    """Verify hard-blocking of strong promotional emails."""
    # Strong sender + marker
    assert is_promotional_email(
        from_email="newsletter@marketing.com",
        subject="Monthly Industry Insights",
        body="Check out our latest tools and services. Click here to unsubscribe.",
    ) is True

    # Generic sender with 2 promotional markers (unsubscribe + view in browser)
    assert is_promotional_email(
        from_email="sales@vendor.com",
        subject="Special Discounts Available",
        body="View in browser. Unsubscribe from this mailing list.",
    ) is True


def test_promotional_email_false_positives_avoided():
    """Verify client recruitment emails with generic words are NOT blocked as promotional."""
    # Recruiter email mentioning privacy policy or view
    assert is_promotional_email(
        from_email="client@ltts.com",
        subject="Requirement for Senior Java Developer",
        body="Please view the attached job description for the open position.",
    ) is False


def test_job_seeker_candidate_email_detection():
    """Verify hard-blocking of strong candidate / job-seeker emails."""
    # Candidate applying for a role
    assert is_job_seeker_email(
        from_email="john.doe@gmail.com",
        subject="Application for Senior React Developer position",
        body="Dear Hiring Team, I am writing to apply for the React Developer role. Please find my resume attached.",
        has_attachments=True,
    ) is True

    # Candidate sending CV with first-person phrasing
    assert is_job_seeker_email(
        from_email="candidate@gmail.com",
        subject="My Profile for Python Developer",
        body="Hello, I have total 6 years of experience in Python. My profile for your review is attached.",
        has_attachments=True,
    ) is True


def test_job_seeker_false_positives_avoided():
    """
    CRITICAL: Verify emails are NOT rejected solely because generic words 
    (resume, candidate, developer, experience, position) appear or are missing.
    """
    # Client email asking for candidate resumes for a position
    client_email_subject = "Urgent: Need Candidate Resumes for Senior Developer Position"
    client_email_body = (
        "Hi Team, We have an immediate opening for a Java Developer with 5+ years experience. "
        "Please share candidate profiles and resumes at the earliest."
    )

    assert is_job_seeker_email(
        from_email="recruiter@client.com",
        subject=client_email_subject,
        body=client_email_body,
        has_attachments=False,
    ) is False

    # Check pre_classify_block_reason does NOT block genuine client requirement
    reason = pre_classify_block_reason(
        from_email="recruiter@client.com",
        subject=client_email_subject,
        body=client_email_body,
    )
    assert reason is None


def test_narrative_requirement_passes_intake_gate():
    """Rule 2.3: Verify narrative requirements (without position count, experience figure, or skills label) pass intake filter."""
    from email_filter import apply_email_filter

    from_email = "manager@kpmg.com"
    subject = "Cloud Architecture Role"
    body = "Hi Team, We urgently need a Cloud Infrastructure Architect to lead our platform migration. Please share suitable candidates."

    result = apply_email_filter(from_email=from_email, body=body, subject=subject)
    assert result.allowed is True
    assert result.reason == "Passed sender allowlist and structure gate"

