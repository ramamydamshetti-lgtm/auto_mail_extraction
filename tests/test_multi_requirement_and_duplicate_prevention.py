"""
Focused unit and integration tests for Multi-Requirement Extraction and Duplicate Prevention:

Issue 1: Extract all distinct requirements:
- Numbered lists
- Bullet points (both with explicit role prefixes and plain titles with attributes)
- HTML tables
- Unnumbered lists (repeated Role: / Job Title:)
- Separate JD sections (markdown / dividers)
- Mixed formats (e.g., numbered roles with bullet-point skills inside)
- Preservation of correct field associations without cross-contamination or hallucination

Issue 2: Prevent duplicate requirements:
- Intra-email duplicate roles (same requirement twice in 1 email -> collapsed)
- Cross-email duplicate roles (same requirement in separate emails -> duplicate, no new record or version)
- Cross-email update with genuinely new information (changed JD -> in-place update, new version recorded, old preserved)
- Genuinely different roles (different titles, different cities, different client IDs) -> stay strictly separate
"""

import json
import sqlite3
from pathlib import Path
from typing import Any
import pytest
from dotenv import load_dotenv

load_dotenv()

from requirement_segmenter import segment_email_into_blocks
from requirement_parser import parse_requirements_from_email, RequirementItem
from requirement_comparator import build_requirement_profile, compare_requirements
from metaforge_api import _ensure_schema, _sqlite_upsert, check_jd_diff
from processed_store import ProcessedStore
from config import Settings


@pytest.fixture
def test_dbs(tmp_path: Path):
    """Isolated SQLite databases for testing without modifying production data."""
    mf_db = tmp_path / "metaforge_test.db"
    conn = sqlite3.connect(mf_db)
    _ensure_schema(conn)
    conn.close()

    pm_db = tmp_path / "processed_test.db"
    store = ProcessedStore(pm_db)

    return {
        "mf_db": mf_db,
        "pm_db": pm_db,
        "store": store,
        "tmp_path": tmp_path,
    }


# ==============================================================================
# ISSUE 1: MULTI-REQUIREMENT EXTRACTION TESTS
# ==============================================================================

def test_numbered_list_extraction_and_field_isolation():
    """Verify distinct roles in numbered list are extracted with correct, isolated fields."""
    email_text = """
    Hi Team,
    Please share profiles for the following requirements:

    1. Data Scientist
    Location: Bangalore
    Exp: 8-15 years
    Budget: 25 LPA
    Skills: Python, Machine Learning, Statistics

    2. AI Engineer
    Location: Hyderabad
    Exp: 5-8 years
    Budget: 18 LPA
    Skills: PyTorch, LLMs, LangChain

    3. Cloud Architect
    Location: Pune
    Exp: 10+ years
    Budget: 35 LPA
    Skills: AWS, Kubernetes, Terraform
    """
    settings = Settings.from_env()
    res = parse_requirements_from_email(subject="Demands for Sep", body=email_text, settings=settings)

    assert len(res.requirements) == 3, f"Expected 3 roles, got {len(res.requirements)}"
    
    titles = [r.job_title for r in res.requirements]
    assert any("Data Scientist" in t for t in titles)
    assert any("AI Engineer" in t for t in titles)
    assert any("Cloud Architect" in t for t in titles)

    # Check field isolation: Role 1 must have 8-15 years, Role 2 must have 5-8 years
    ds = next(r for r in res.requirements if "Data Scientist" in r.job_title)
    ai = next(r for r in res.requirements if "AI Engineer" in r.job_title)
    ca = next(r for r in res.requirements if "Cloud Architect" in r.job_title)

    assert "8" in str(ds.experience) and "15" in str(ds.experience)
    assert "5" in str(ai.experience) and "8" in str(ai.experience)
    assert "10" in str(ca.experience)

    assert "bangalore" in [loc.lower() for loc in (ds.location or [])]
    assert "hyderabad" in [loc.lower() for loc in (ai.location or [])]
    assert "pune" in [loc.lower() for loc in (ca.location or [])]


def test_bullet_list_extraction_with_prefixes():
    """Verify distinct roles introduced with bullet points and role prefixes are extracted independently."""
    email_text = """
    Urgent client hiring drive:

    * Role: Senior React Developer
      Location: Bangalore
      Experience: 5+ years
      Skills: React, Redux, TypeScript
      Notice Period: Immediate

    * Role: Node.js Backend Engineer
      Location: Chennai
      Experience: 6+ years
      Skills: Node.js, Express, PostgreSQL
      Notice Period: 15 days
    """
    settings = Settings.from_env()
    res = parse_requirements_from_email(subject="Hiring Drive", body=email_text, settings=settings)

    assert len(res.requirements) == 2, f"Expected 2 roles, got {len(res.requirements)}"
    
    r1 = next(r for r in res.requirements if "React" in r.job_title)
    r2 = next(r for r in res.requirements if "Node" in r.job_title)

    assert "bangalore" in [loc.lower() for loc in (r1.location or [])]
    assert "chennai" in [loc.lower() for loc in (r2.location or [])]
    assert "5" in str(r1.experience)
    assert "6" in str(r2.experience)


def test_bullet_list_plain_titles_with_attribute_lines():
    """Verify bullet points with plain job titles followed by attributes are split and isolated."""
    email_text = """
    Open positions:

    • Python Developer
      Location: Gurgaon
      Exp: 4-6 years
      Skills: Python, Django, Docker

    • DevOps Engineer
      Location: Mumbai
      Exp: 7+ years
      Skills: Kubernetes, CI/CD, Terraform
    """
    settings = Settings.from_env()
    res = parse_requirements_from_email(subject="Open positions", body=email_text, settings=settings)

    assert len(res.requirements) == 2, f"Expected 2 roles, got {len(res.requirements)}"
    
    titles = [r.job_title for r in res.requirements]
    assert any("Python" in t for t in titles)
    assert any("DevOps" in t for t in titles)


def test_html_table_multi_requirement_extraction():
    """Verify multiple requirements formatted in HTML tables are extracted independently."""
    html_body = """
    <html>
    <body>
    <p>Please find the open demands below:</p>
    <table>
      <tr>
        <th>Job Title</th>
        <th>Req ID</th>
        <th>Location</th>
        <th>Experience</th>
        <th>Mandatory Skills</th>
      </tr>
      <tr>
        <td>Full Stack Developer</td>
        <td>REQ-FSD-01</td>
        <td>Bangalore</td>
        <td>4-6 years</td>
        <td>Java, Angular</td>
      </tr>
      <tr>
        <td>Data Architect</td>
        <td>REQ-DATA-02</td>
        <td>Hyderabad</td>
        <td>12+ years</td>
        <td>Snowflake, Databricks</td>
      </tr>
    </table>
    </body>
    </html>
    """
    settings = Settings.from_env()
    res = parse_requirements_from_email(subject="Table Demands", body=html_body, settings=settings)

    assert len(res.requirements) == 2, f"Expected 2 roles from table, got {len(res.requirements)}"
    
    r1 = next(r for r in res.requirements if "Full Stack" in r.job_title)
    r2 = next(r for r in res.requirements if "Data Architect" in r.job_title)

    assert r1.req_id == "REQ-FSD-01"
    assert r2.req_id == "REQ-DATA-02"
    assert "bangalore" in [loc.lower() for loc in (r1.location or [])]
    assert "hyderabad" in [loc.lower() for loc in (r2.location or [])]


def test_unnumbered_list_repeated_role_headers():
    """Verify unnumbered lists with repeated 'Role:' headers are split and extracted independently."""
    email_text = """
    Demands for this week:

    Role: Golang Developer
    Location: Pune
    Experience: 5-8 years
    Skills: Go, gRPC, Microservices

    Role: QA Automation Engineer
    Location: Bangalore
    Experience: 3-5 years
    Skills: Selenium, Python, PyTest
    """
    settings = Settings.from_env()
    res = parse_requirements_from_email(subject="Weekly Demands", body=email_text, settings=settings)

    assert len(res.requirements) == 2, f"Expected 2 roles, got {len(res.requirements)}"
    
    titles = [r.job_title for r in res.requirements]
    assert any("Golang" in t for t in titles)
    assert any("QA Automation" in t for t in titles)


def test_markdown_and_separated_sections():
    """Verify separate JD sections with markdown headings are extracted independently."""
    email_text = """
    ### Mobile Lead (iOS)
    Location: Hyderabad
    Exp: 8+ years
    Skills: Swift, SwiftUI, iOS Architecture

    ### Mobile Lead (Android)
    Location: Bangalore
    Exp: 8+ years
    Skills: Kotlin, Jetpack Compose, Android Architecture
    """
    settings = Settings.from_env()
    res = parse_requirements_from_email(subject="Mobile Leads", body=email_text, settings=settings)

    assert len(res.requirements) == 2, f"Expected 2 roles, got {len(res.requirements)}"
    titles = [r.job_title for r in res.requirements]
    assert any("iOS" in t for t in titles)
    assert any("Android" in t for t in titles)


def test_mixed_format_single_role_with_bulleted_skills_not_split():
    """Verify that a single role containing bullet points under skills is NOT falsely split."""
    email_text = """
    1. Senior Data Scientist
    Location: Bangalore
    Experience: 8-15 years
    Mandatory Skills:
    • Python
    • PyTorch
    • Scikit-learn
    Responsibilities:
    - Train machine learning models
    - Deploy to production
    """
    settings = Settings.from_env()
    res = parse_requirements_from_email(subject="Single Demand with Bullets", body=email_text, settings=settings)

    assert len(res.requirements) == 1, f"Expected exactly 1 role, got {len(res.requirements)}"
    r = res.requirements[0]
    assert "Data Scientist" in r.job_title
    assert "bangalore" in [loc.lower() for loc in (r.location or [])]


# ==============================================================================
# ISSUE 2: PREVENT DUPLICATE REQUIREMENTS TESTS
# ==============================================================================

def test_intra_email_duplicate_roles_collapsed(test_dbs):
    """Verify duplicate roles within the same email are collapsed, while distinct roles remain separate."""
    # Profile 1: Java Developer in Bangalore
    p1 = {
        "requirement_from": "ltts",
        "job_title": "Java Developer",
        "location": "Bangalore",
        "client_jd_id": "REQ-100",
        "mandatory_skills": ["Java", "Spring Boot"],
    }
    # Profile 2: Duplicate of Profile 1 in same email
    p2 = {
        "requirement_from": "ltts",
        "job_title": "Java Developer",
        "location": "Bangalore",
        "client_jd_id": "REQ-100",
        "mandatory_skills": ["Java", "Spring Boot"],
    }
    # Profile 3: Genuinely different role in same email
    p3 = {
        "requirement_from": "ltts",
        "job_title": "Python Developer",
        "location": "Bangalore",
        "client_jd_id": "REQ-200",
        "mandatory_skills": ["Python", "FastAPI"],
    }

    prof1 = build_requirement_profile(p1)
    prof2 = build_requirement_profile(p2)
    prof3 = build_requirement_profile(p3)

    # p1 vs p2 must be DUPLICATE
    dec_dup, score_dup, rule_dup = compare_requirements(prof1, prof2)
    assert dec_dup == "DUPLICATE", f"Expected DUPLICATE for identical roles, got {dec_dup}"

    # p1 vs p3 must be NOT_DUPLICATE
    dec_diff, score_diff, rule_diff = compare_requirements(prof1, prof3)
    assert dec_diff == "NOT_DUPLICATE", f"Expected NOT_DUPLICATE for different roles, got {dec_diff}"


def test_cross_email_identical_requirement_skipped(test_dbs):
    """Verify identical requirement arriving in a second email is skipped and no new record/version created."""
    mf_db = test_dbs["mf_db"]

    req_initial = {
        "client_jd_id": "ACC-5001",
        "requirement_from": "accenture",
        "job_title": "SAP ABAP Consultant",
        "location": "Bangalore",
        "monthly_budget": "150000",
        "job_description": "SAP ABAP Consultant with S/4HANA and CDS Views experience.",
        "graphMessageId": "msg-first",
    }
    job_id_1 = _sqlite_upsert(req_initial, str(mf_db))
    assert job_id_1

    # Second email arrives with identical requirement
    req_dup = {
        "client_jd_id": "ACC-5001",
        "requirement_from": "accenture",
        "job_title": "SAP ABAP Consultant",
        "location": "Bangalore",
        "monthly_budget": "150000",
        "job_description": "SAP ABAP Consultant with S/4HANA and CDS Views experience.",
        "graphMessageId": "msg-second",
    }
    job_id_2 = _sqlite_upsert(req_dup, str(mf_db))

    assert job_id_2 == job_id_1, f"Expected same job_id {job_id_1}, got {job_id_2}"

    conn = sqlite3.connect(mf_db)
    count_reqs = conn.execute("SELECT COUNT(*) FROM metaforge_requirements").fetchone()[0]
    count_vers = conn.execute("SELECT COUNT(*) FROM jd_versions WHERE requirement_id = ?", (job_id_1,)).fetchone()[0]
    conn.close()

    assert count_reqs == 1, "Duplicate email must not create a new requirement record"
    assert count_vers == 1, "Duplicate email with identical JD must not create a new version"


def test_cross_email_changed_requirement_updates_in_place_with_version(test_dbs):
    """Verify update with genuinely new information updates in-place, increments version, and preserves history."""
    mf_db = test_dbs["mf_db"]

    req_initial = {
        "client_jd_id": "LTTS-777",
        "requirement_from": "ltts",
        "job_title": "DevOps Engineer",
        "location": "Pune",
        "monthly_budget": "120000",
        "job_description": "Initial JD: DevOps Engineer with Terraform and Docker.",
        "graphMessageId": "msg-v1",
    }
    job_id = _sqlite_upsert(req_initial, str(mf_db))

    # Follow-up email updates budget and adds Kubernetes to JD
    req_update = {
        "client_jd_id": "LTTS-777",
        "requirement_from": "ltts",
        "job_title": "DevOps Engineer",
        "location": "Pune",
        "monthly_budget": "160000",  # Changed budget
        "job_description": "Revised JD: DevOps Engineer with Terraform, Docker, and Kubernetes.",  # Changed JD
        "graphMessageId": "msg-v2",
    }
    job_id_updated = _sqlite_upsert(req_update, str(mf_db))

    assert job_id_updated == job_id, f"In-place update must preserve job_id {job_id}"

    conn = sqlite3.connect(mf_db)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT payload_json FROM metaforge_requirements WHERE job_id = ?", (job_id,)).fetchone()
    p = json.loads(row["payload_json"])

    assert p.get("monthly_budget") == "160000"
    assert p.get("jd_version") == 2
    assert len(p.get("version_history", [])) == 2

    # Check jd_versions table preserves both v1 and v2
    v_rows = conn.execute("SELECT * FROM jd_versions WHERE requirement_id = ? ORDER BY version_number ASC", (job_id,)).fetchall()
    assert len(v_rows) == 2
    assert "Initial JD" in v_rows[0]["job_description"]
    assert "Revised JD" in v_rows[1]["job_description"]
    conn.close()


def test_genuinely_different_roles_not_treated_as_duplicates(test_dbs):
    """Verify that different roles with some shared fields (e.g. same client, same location) remain separate."""
    mf_db = test_dbs["mf_db"]

    # Role 1: Data Scientist in Bangalore
    req1 = {
        "client_jd_id": "ROLE-01",
        "requirement_from": "kpmg",
        "job_title": "Data Scientist",
        "location": "Bangalore",
        "overall_experience": "8-15 years",
        "job_description": "Data Scientist focusing on statistical modeling.",
    }
    # Role 2: AI Architect in Bangalore (same client, same location, different role)
    req2 = {
        "client_jd_id": "ROLE-02",
        "requirement_from": "kpmg",
        "job_title": "AI Architect",
        "location": "Bangalore",
        "overall_experience": "8+ years",
        "job_description": "AI Architect focusing on LLM system architecture.",
    }

    jid_1 = _sqlite_upsert(req1, str(mf_db))
    jid_2 = _sqlite_upsert(req2, str(mf_db))

    assert jid_1 != jid_2, "Distinct roles must receive distinct IDs"

    conn = sqlite3.connect(mf_db)
    total = conn.execute("SELECT COUNT(*) FROM metaforge_requirements").fetchone()[0]
    conn.close()

    assert total == 2, f"Expected 2 separate records for distinct roles, got {total}"
