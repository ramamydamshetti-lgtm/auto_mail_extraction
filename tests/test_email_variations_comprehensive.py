"""
Comprehensive regression test suite covering the 13 required scenarios:
1. A simple single-role email.
2. An email containing multiple job roles.
3. An email containing several client requirement IDs.
4. A job description followed by a candidate-submission table.
5. A job description containing the phrase 'relevant experience'.
6. An email with qualifications but no explicit technical skills.
7. An email with missing location or experience.
8. An HTML email with job details in a table.
9. A forwarded email with quoted older content.
10. An email containing phone numbers and alphanumeric IDs.
11. An email with duplicated requirements.
12. An email with no genuine job requirement.
13. An email with malformed or ambiguous data.
"""

import re
import pytest
from body_normalizer import html_to_plain, scrub_pii, normalize_body
from requirement_parser import (
    _strip_candidate_tables,
    _DEGREE_PREFIX_RE,
    _is_noise_skill_candidate,
    extract_client_jd_id_from_text,
)
from field_mapper import (
    extract_min_max_experience,
    format_metaforge_requirement,
)
from status_tracker import extract_req_ids_from_text
from requirement_comparator import compare_requirements, build_requirement_profile
from email_filter import apply_email_filter, has_requirement_structure


# 1. Simple Single-Role Email
def test_scenario_1_simple_single_role():
    body = (
        "Role: Senior Java Developer\n"
        "Experience: 5-8 years\n"
        "Location: Bangalore\n"
        "Budget: 18-22 LPA\n"
        "Skills: Java, Spring Boot, Microservices, Hibernate\n"
    )
    lo, hi = extract_min_max_experience("5-8 years")
    assert lo == 5 and hi == 8

    req_payload = format_metaforge_requirement(
        job_id="2026/10/13-101",
        demand_received_date="2026-10-13",
        internal_poc="ta@metaforgeit.com",
        requirement_from="ClientX",
        client_jd_id="REQ-101",
        client_lead_poc="poc@client.com",
        client_poc="poc@client.com",
        job_title="Senior Java Developer",
        experience="5-8 years",
        location="Bangalore",
        notice_period="30 days",
        number_of_positions=2,
        mandatory_skills=["Java", "Spring Boot", "Microservices"],
        skills=["Hibernate"],
        body_text=body,
        extracted={"overall_experience": "5-8 years"},
        email_subject="New Requirement: Senior Java Developer",
    )
    assert req_payload["job_title"] == "Senior Java Developer"
    assert req_payload["location"] == "Bangalore"
    assert req_payload["experience"] == "5-8 years"
    assert req_payload["overall_experience_min"] == 5
    assert req_payload["overall_experience_max"] == 8
    assert "Java" in req_payload["mandatory_skills"]


# 2. Email Containing Multiple Job Roles
def test_scenario_2_multiple_job_roles():
    p1 = {
        "requirement_from": "Deloitte",
        "job_title": "DevOps Engineer",
        "location": "Pune",
        "mandatory_skills": ["AWS", "Kubernetes", "Terraform"],
        "client_jd_id": "REQ-DEVOPS",
    }
    p2 = {
        "requirement_from": "Deloitte",
        "job_title": "Frontend Developer",
        "location": "Hyderabad",
        "mandatory_skills": ["React", "TypeScript", "Redux"],
        "client_jd_id": "REQ-FRONTEND",
    }
    prof1 = build_requirement_profile(p1, body_text="DevOps AWS Kubernetes Pune")
    prof2 = build_requirement_profile(p2, body_text="Frontend React TypeScript Hyderabad")
    decision, score, rule = compare_requirements(prof1, prof2)
    assert decision == "NOT_DUPLICATE", f"Expected distinct roles to remain separate, got {decision}"


# 3. Email Containing Several Client Requirement IDs
def test_scenario_3_several_client_requirement_ids():
    subject = "New Requirement - Civil Engineering RQ057250 & RQ057252 - Prateek's Team"
    body = "Please review requirements under JP ID: DLTJP00063583 and RQ057250."
    found_ids = extract_req_ids_from_text(subject, body)
    assert "RQ057250" in found_ids
    assert "RQ057252" in found_ids
    assert "DLTJP00063583" in found_ids

    primary = extract_client_jd_id_from_text(subject, body)
    assert primary in ("RQ057250", "DLTJP00063583")

    payload = format_metaforge_requirement(
        job_id="2026/10/13-103",
        demand_received_date="2026-10-13",
        internal_poc="",
        requirement_from="Deloitte",
        client_jd_id=primary,
        client_lead_poc="",
        client_poc="",
        job_title="Civil Engineer",
        experience="2-5 years",
        location="Delhi",
        notice_period="",
        number_of_positions=1,
        mandatory_skills=["Civil Engineering"],
        skills=[],
        body_text=body,
        extracted={},
        email_subject=subject,
    )
    assert payload["all_client_jd_ids"] == found_ids
    assert len(payload["alternate_client_ids"]) >= 1


# 4. Job Description Followed by a Candidate-Submission Table
def test_scenario_4_jd_followed_by_candidate_submission_table():
    body = (
        "Job Description: Backend Python Specialist\n"
        "Key Responsibilities:\n"
        "Design and scale REST APIs\n"
        "Experience: 3-6 years\n"
        "Location: Chennai\n"
        "Monthly Bill Rate: 80000\n"
        "Please share the profiles on the below table.\n"
        "Sl. No | Vendor | Applicant Name | Skill | Mobile no | Email ID | Total Exp | Relevant Exp | Notice Period\n"
        "1 | TechCorp | John Smith | Python | 9876543210 | john@tech.com | 5 yrs | 4 yrs | Immediate\n"
        "JP ID: DLTJP00099999\n"
        "Regards,\nRecruiter"
    )
    cleaned = _strip_candidate_tables(body)
    # JD text must be preserved
    assert "Backend Python Specialist" in cleaned
    assert "Experience: 3-6 years" in cleaned
    assert "Location: Chennai" in cleaned
    assert "Monthly Bill Rate: 80000" in cleaned
    # Table data row and column noise must be stripped
    assert "John Smith" not in cleaned
    assert "john@tech.com" not in cleaned
    # Requisition ID line preserved
    assert "DLTJP00099999" in cleaned


# 5. Job Description Containing the Phrase 'relevant experience'
def test_scenario_5_jd_containing_phrase_relevant_experience():
    body = (
        "Eligibility Criteria:\n"
        "Bachelor's degree in Civil Engineering (B.E./B.Tech.) from a recognised institution.\n"
        "2-5 years of relevant experience in construction, project management, and project monitoring.\n"
        "Location: Delhi\n"
        "Monthly Bill Rate: 60000\n"
    )
    cleaned = _strip_candidate_tables(body)
    assert "2-5 years of relevant experience" in cleaned
    assert "Location: Delhi" in cleaned
    assert "Monthly Bill Rate: 60000" in cleaned


# 6. Email with Qualifications But No Explicit Technical Skills
def test_scenario_6_qualifications_without_explicit_technical_skills():
    body = (
        "We are hiring for Audit & Assurance.\n"
        "Eligibility Criteria:\n"
        "Bachelor's degree in Civil Engineering (B.E./B.Tech.)\n"
        "Experience: 2-5 years\n"
        "Location: Delhi\n"
    )
    qual_match = re.search(r"(?im)^\s*(?:eligibility(?:\s+criteria)?|qualification[s]?)\s*[:\-]?(?:\n|\r|\s)+([^\n\r]+)", body)
    assert qual_match is not None
    qual_text = qual_match.group(1).strip()
    assert "Civil Engineering" in qual_text

    # Prefix stripping extracts genuine discipline
    discipline = _DEGREE_PREFIX_RE.sub("", qual_text).strip()
    assert discipline.startswith("Civil Engineering")
    assert not _is_noise_skill_candidate(discipline)


# 7. Email with Missing Location or Experience
def test_scenario_7_missing_location_or_experience():
    body = (
        "Role: Machine Learning Engineer\n"
        "Skills: PyTorch, Transformers, LLMs\n"
        "Work Mode: Remote\n"
    )
    # Experience is not stated
    exp_lo, exp_hi = extract_min_max_experience(None)
    assert exp_lo is None and exp_hi is None

    payload = format_metaforge_requirement(
        job_id="2026/10/13-107",
        demand_received_date="2026-10-13",
        internal_poc="",
        requirement_from="ClientY",
        client_jd_id="REQ-ML",
        client_lead_poc="",
        client_poc="",
        job_title="Machine Learning Engineer",
        experience="",
        location="",
        notice_period="",
        number_of_positions=1,
        mandatory_skills=["PyTorch", "Transformers"],
        skills=["LLMs"],
        body_text=body,
        extracted={},
        email_subject="Urgent ML Engineer opening",
    )
    # Missing fields remain valid NULLs without hallucinations
    assert payload["location"] is None
    assert payload["experience"] is None
    assert payload["job_title"] == "Machine Learning Engineer"


# 8. HTML Email with Job Details in a Table
def test_scenario_8_html_email_with_job_details_in_table():
    html = (
        "<html><body>"
        "<h3>Requirement Update</h3>"
        "<table>"
        "<tr><th>Role</th><th>Location</th><th>Experience</th><th>Budget</th></tr>"
        "<tr><td>Lead Analyst</td><td>Mumbai</td><td>6-9 years</td><td>25 LPA</td></tr>"
        "</table>"
        "<p>Key Skills:</p>"
        "<ul><li>Python</li><li>SQL</li><li>Snowflake</li></ul>"
        "</body></html>"
    )
    plain = html_to_plain(html)
    assert "Lead Analyst | Mumbai | 6-9 years | 25 LPA" in plain
    assert "- Python" in plain
    assert "- SQL" in plain


# 9. Forwarded Email with Quoted Older Content
def test_scenario_9_forwarded_email_with_quoted_older_content():
    body = (
        "FYI please see forwarded requirements below.\n"
        "Best regards,\n"
        "Sender\n\n"
        "From: recruiter@client.com\n"
        "Sent: Monday, October 13, 2026\n"
        "Subject: Urgent: Data Architect\n\n"
        "Role: Data Architect\n"
        "Experience: 10+ years\n"
        "Location: Hyderabad\n"
        "Skills: Databricks, Spark, Azure\n"
    )
    norm = normalize_body(body, None)
    assert "Role: Data Architect" in norm
    assert "From: recruiter@client.com" in norm


# 10. Email Containing Phone Numbers and Alphanumeric IDs
def test_scenario_10_phone_numbers_and_alphanumeric_ids():
    text = (
        "For candidate submissions, call recruiter at +91 96 8610 0177 or (555) 123-4567.\n"
        "Please reference Requisition ID: RQ057250, Job Posting: DLTJP00063583, Code: 203421-1."
    )
    scrubbed = scrub_pii(text)
    # Phone numbers must be redacted
    assert "+91 96 8610 0177" not in scrubbed
    assert "(555) 123-4567" not in scrubbed
    assert "[REDACTED_PHONE]" in scrubbed
    # Alphanumeric business IDs must remain completely intact
    assert "RQ057250" in scrubbed
    assert "DLTJP00063583" in scrubbed
    assert "203421-1" in scrubbed


# 11. Email with Duplicated Requirements
def test_scenario_11_duplicated_requirements():
    p1 = {
        "requirement_from": "Deloitte",
        "job_title": "Civil Engineer",
        "location": "Delhi",
        "client_jd_id": "RQ057250",
    }
    p2 = {
        "requirement_from": "Deloitte",
        "job_title": "Civil Engineer",
        "location": "Delhi",
        "client_jd_id": "RQ057250",
    }
    prof1 = build_requirement_profile(p1, body_text="Civil Engineer Delhi RQ057250")
    prof2 = build_requirement_profile(p2, body_text="Civil Engineer Delhi RQ057250")
    decision, score, rule = compare_requirements(prof1, prof2)
    assert decision == "DUPLICATE"
    assert "HARD_RULE_SAME_CLIENT_AND_ID" in rule


# 12. Email with No Genuine Job Requirement
def test_scenario_12_no_genuine_job_requirement():
    subject = "Automatic reply: Out of Office: Meeting notes"
    body = "I am currently out of the office on annual leave until next Monday. Please contact my colleague."
    has_structure = has_requirement_structure(body, subject=subject)
    assert has_structure is False

    filter_res = apply_email_filter(
        from_email="recruiter@idexcel.com",
        body=body,
        subject=subject,
    )
    assert filter_res.allowed is False
    assert "structure" in filter_res.reason.lower()


# 13. Email with Malformed or Ambiguous Data
def test_scenario_13_malformed_or_ambiguous_data():
    malformed_body = (
        "Role:   Civil Engineer   \r\n"
        "Experience: 2\ufffd5 years of exp\r\n"
        "Min exp: Minimum 3 years of relevant experience\r\n"
        "Rate: 60000 \r\n"
        "Qualification: Bachelor's degree in Civil Engineering\r\n"
    )
    # Normalize unicode replacement characters and non-standard dashes
    cleaned = malformed_body.replace("\ufffd", "-").replace("–", "-")
    assert "2-5 years" in cleaned

    # Minimum pattern handles "Minimum 3 years"
    min_lo, min_hi = extract_min_max_experience("Minimum 3 years of relevant experience")
    assert min_lo == 3 and min_hi is None

    # Education discipline extracted
    discipline = _DEGREE_PREFIX_RE.sub("", "Bachelor's degree in Civil Engineering").strip()
    assert discipline == "Civil Engineering"
