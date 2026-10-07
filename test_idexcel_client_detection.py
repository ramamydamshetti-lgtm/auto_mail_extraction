"""
Unit tests for idexcel.com Client Detection, Tag Matching, and Per-Requirement Resolution.
"""

from __future__ import annotations

import pytest
from client_detector import (
    detect_client,
    find_idexcel_client_matches,
    resolve_idexcel_client_for_requirement,
    strip_reply_history,
)
from field_mapper import check_ui_readiness


def test_d_client_in_subject():
    """Test 1: (D-Client) in subject -> Deloitte."""
    match = detect_client(
        subject="Urgent Intake (D-Client) Java Lead",
        body="We need a Java Lead in Bangalore.",
        from_email="recruiter@idexcel.com",
    )
    assert match is not None
    assert match.key == "deloitte"
    assert match.display_name == "Deloitte"


def test_p_client_in_body():
    """Test 2: P-Client: React Dev in body -> PwC."""
    match = detect_client(
        subject="New Requirement",
        body="P-Client: React Dev with 5+ years experience.",
        from_email="recruiter@idexcel.com",
    )
    assert match is not None
    assert match.key == "pwc"
    assert match.display_name == "PwC"


def test_spelling_variants():
    """Test 3: Spelling variants 'P Client', 'D - Client', 'DClient' -> correct client."""
    match_p_space = detect_client("Intake", "Client is P Client", "user@idexcel.com")
    assert match_p_space.key == "pwc"
    assert match_p_space.display_name == "PwC"

    match_d_dash_space = detect_client("Intake", "Client: D - Client", "user@idexcel.com")
    assert match_d_dash_space.key == "deloitte"
    assert match_d_dash_space.display_name == "Deloitte"

    match_dclient = detect_client("Intake", "DClient opportunity", "user@idexcel.com")
    assert match_dclient.key == "deloitte"
    assert match_dclient.display_name == "Deloitte"


def test_false_positive_words_not_matched():
    """Test 4: 'End-client: Bank' and 'SAP client' -> NOT Deloitte / PwC (unresolved)."""
    match_end = detect_client("Bank Req", "End-client: National Bank", "user@idexcel.com")
    assert match_end.key == "idexcel_unresolved"
    assert match_end.display_name == "unresolved"

    match_sap = detect_client("SAP Req", "We have a SAP client project", "user@idexcel.com")
    assert match_sap.key == "idexcel_unresolved"
    assert match_sap.display_name == "unresolved"


def test_multi_requirement_separate_clients():
    """Test 5: Email with a D-Client row and a P-Client row -> each requirement gets its own client."""
    body = """
    Requirement 1:
    D-Client Java Developer
    
    Requirement 2:
    P-Client React Developer
    """
    subject = "Multiple Roles"
    from_email = "user@idexcel.com"

    client1, note1 = resolve_idexcel_client_for_requirement(
        subject, body, requirement_text="Java Developer", role_index=0
    )
    assert client1.key == "deloitte"
    assert client1.display_name == "Deloitte"
    assert note1 is None

    client2, note2 = resolve_idexcel_client_for_requirement(
        subject, body, requirement_text="React Developer", role_index=1
    )
    assert client2.key == "pwc"
    assert client2.display_name == "PwC"
    assert note2 is None


def test_both_tags_cannot_tie_role_unresolved():
    """Test 6: Both tags, cannot tie a role -> unresolved + flagged for review."""
    body = "Role 1 D-Client and P-Client mentioned in header text.\nRequirement: Generic Software Engineer"
    subject = "Conflicting Tags"

    client, note = resolve_idexcel_client_for_requirement(
        subject, body, requirement_text="Software Engineer", role_index=0
    )
    assert client.key == "idexcel_unresolved"
    assert client.display_name == "unresolved"
    assert note is not None
    assert "Ambiguous D-Client / P-Client tags" in note


def test_no_tag_sent_to_pending_review():
    """Test 7: No tag -> 'Idexcel (client not identified)', sent to pending review."""
    subject = "Java Requirement"
    body = "We are looking for 5 Java Engineers in Hyderabad."
    from_email = "user@idexcel.com"

    match = detect_client(subject, body, from_email)
    assert match.key == "idexcel_unresolved"
    assert match.display_name == "unresolved"

    client, note = resolve_idexcel_client_for_requirement(subject, body, "Java Engineer", 0)
    assert client.key == "idexcel_unresolved"
    assert note is not None
    assert "Missing D-Client / P-Client tag" in note

    # Check UI readiness flags it for pending review
    readiness = check_ui_readiness({
        "client_key": client.key,
        "requirement_from": client.display_name,
        "job_title": "Java Engineer",
        "processing_note": note,
    })
    assert readiness["is_ready_for_auto_sync"] is False
    assert "idexcel_client_unresolved" in readiness["review_fields"]


def test_tag_in_quoted_reply_history_ignored():
    """Test 8: Tag only in quoted reply history -> ignored."""
    subject = "RE: Java Developer"
    body = """
    Please process this new requirement for Python Engineer.
    
    ---
    From: manager@idexcel.com
    Sent: Yesterday
    Subject: Old REQ (D-Client)
    """
    from_email = "user@idexcel.com"

    match = detect_client(subject, body, from_email)
    assert match.key == "idexcel_unresolved"
    assert match.display_name == "unresolved"


def test_tag_in_sender_address_ignored():
    """Test 9: Tag text inside sender address -> ignored."""
    # e.g., sender is d-client@idexcel.com or p-client@idexcel.com
    match = detect_client("Req Intake", "We need a C++ engineer.", "d-client@idexcel.com")
    assert match.key == "idexcel_unresolved"
    assert match.display_name == "unresolved"


def test_other_domains_regression():
    """Test 10: iexcel.co.in -> Accenture, eximietas.com -> PwC, ltts.com -> LTTS unchanged."""
    acc = detect_client("Intake", "Job Requirement", "anusha.k@iexcel.co.in")
    assert acc.key == "accenture"
    assert acc.display_name == "Accenture"

    pwc = detect_client("Intake", "Job Requirement", "partner@eximietas.com")
    assert pwc.key == "pwc"
    assert pwc.display_name == "PwC"

    ltts = detect_client("Intake", "Job Requirement", "user@ltts.com")
    assert ltts.key == "ltts"
    assert ltts.display_name == "LTTS"
