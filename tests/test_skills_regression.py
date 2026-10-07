"""
Regression tests for generalized SKILLS fix.
Covers:
1. Multi-demand table downstream JD / Professional & Technical Skills association.
2. Cross-role contamination prevention (zero leak between Req IDs).
3. Generalized skill validation:
   - Word count preservation (up to 20 words for descriptive technical skills).
   - Preposition generalization ('hands-on expertise on', 'proficiency in', etc.).
   - Protection of short technical skills (C++, NX, CAD, FEA, CFD).
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from boilerplate_learner import validate_skills
from requirement_parser import associate_downstream_skills_for_req, extract_req_id_table_requirements


def test_short_technical_skills_preservation():
    """Verify short technical skills (C++, NX, CAD, FEA, CFD) are preserved by validate_skills."""
    skills = ["C++", "NX", "CAD", "FEA", "CFD", "BTP", "PM", "ABAP", "SQL"]
    validated = validate_skills(skills, client="LTTS")
    assert validated is not None
    for s in skills:
        assert s in validated


def test_preposition_and_framing_generalization():
    """Verify varied preposition and expertise framing are accepted without hardcoding."""
    skills = [
        "Hands-on expertise on Inmation or PI systems",
        "Proficiency in SAP ABAP Cloud",
        "Competency with cloud-native architectures",
        "Hands on coding experience on FICA objects",
        "Deep technical knowledge of distributed caching systems",
    ]
    validated = validate_skills(skills, client="Accenture")
    assert validated is not None
    assert len(validated) == len(skills)


def test_descriptive_technical_skills_word_count():
    """Verify descriptive technical skills (>6 words, up to 20 words) are preserved."""
    skills = [
        "Design, build, and deploy SAP datasphere solutions according to business requirements",
        "Experience in designing and implementing custom enhancements within SAP Extended Warehouse Management environments",
        "Modelling Function Types like Allocations, Transfer Structure, Views, Joins, Calculate, Writer, Models",
    ]
    validated = validate_skills(skills, client="Accenture")
    assert validated is not None
    assert len(validated) == 3


def test_generic_nontechnical_duty_prose_rejected():
    """Verify generic administrative / workplace prose without technical substance is rejected."""
    prose = [
        "Responsible for attending daily meetings and team discussions",
        "Collaborate and manage team deliverables on time",
        "Engage with multiple teams and stakeholders across the company",
    ]
    validated = validate_skills(prose, client="Generic")
    assert validated is None or len(validated) == 0


def test_multi_demand_downstream_association_isolation():
    """
    Verify that in a multi-demand email with multiple Req IDs and downstream JDs:
    1. Each Req ID receives its own explicit skills.
    2. Zero cross-role contamination occurs.
    """
    body = """
Client: Accenture
Demand Summary:
Req ID: 173640-1 | Role: SAP ABAP Developer | Location: Bangalore
Req ID: 173640-2 | Role: ServiceNow Lead | Location: Hyderabad

--------------------------------------------------
Req ID: 173640-1
Job Description:
Professional & Technical Skills:
Must To Have Skills: Proficiency in SAP ABAP Cloud
- Strong experience with RAP and CAP models.
- Hands-on with CDS views and OData services.

--------------------------------------------------
Req ID: 173640-2
Job Description:
Must Have Skills:
- ServiceNow SAM Pro
- Software Asset Management lifecycle
- Scripting in ServiceNow
Good To Have Skills:
- ITIL certified
- CMDB integration
"""

    # Test Req 1
    mand1, soft1 = associate_downstream_skills_for_req(body, "173640-1", "Accenture")
    assert mand1 == ["Proficiency in SAP ABAP Cloud"]
    assert any("RAP" in s for s in soft1)
    # Check NO ServiceNow leakage in Req 1
    assert not any("servicenow" in s.lower() for s in mand1 + soft1)
    assert not any("sam pro" in s.lower() for s in mand1 + soft1)

    # Test Req 2
    mand2, soft2 = associate_downstream_skills_for_req(body, "173640-2", "Accenture")
    assert any("ServiceNow SAM Pro" in s for s in mand2)
    assert any("ITIL certified" in s for s in soft2)
    # Check NO SAP ABAP leakage in Req 2
    assert not any("abap" in s.lower() for s in mand2 + soft2)
    assert not any("cds" in s.lower() for s in mand2 + soft2)


def test_extract_req_id_table_requirements_end_to_end_association():
    """Verify extract_req_id_table_requirements correctly associates downstream skills."""
    body = """
<table border="1">
  <tr><th>Req ID</th><th>Job Title</th><th>Location</th><th>Status</th></tr>
  <tr><td>199343-1</td><td>SAP EWM Consultant</td><td>Bangalore</td><td>Open</td></tr>
  <tr><td>199343-2</td><td>SAP PaPM Specialist</td><td>Gurugram</td><td>Open</td></tr>
</table>

Req ID: 199343-1
Job Description:
Professional & Technical Skills:
Must To Have Skills: Proficiency in SAP EWM
- Strong knowledge of warehouse management processes.
- Custom RF development.

Req ID: 199343-2
Job Description:
Professional & Technical Skills:
Must To Have Skills: SAP Profitability & Performance Management PaPM On-Premise
- PaPM integration with S/4 HANA.
- Function modelling in PaPM.
"""

    items = extract_req_id_table_requirements(body, subject="Demand Email", from_email="hiring@accenture.com")
    assert len(items) == 2

    # Item 1
    assert items[0].req_id == "199343-1"
    assert items[0].mandatory_skills == ["Proficiency in SAP EWM"]
    assert any("warehouse management" in s for s in items[0].soft_skills)
    assert not any("papm" in s.lower() for s in (items[0].mandatory_skills or []) + (items[0].soft_skills or []))

    # Item 2
    assert items[1].req_id == "199343-2"
    assert items[1].mandatory_skills == ["SAP Profitability & Performance Management PaPM On-Premise"]
    assert any("PaPM integration" in s for s in items[1].soft_skills)
    assert not any("ewm" in s.lower() for s in (items[1].mandatory_skills or []) + (items[1].soft_skills or []))
