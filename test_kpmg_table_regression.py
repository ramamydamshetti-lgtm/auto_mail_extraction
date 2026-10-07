"""
Regression test for KPMG table extraction and multi-role parsing.
Asserts:
1. "WORKDAY | FTE - Urgent Requirements" extracts exactly 3 roles.
2. Job titles are Workday Financials Consultant, Workday Integration Consultant, and SAP ABAP Consultant.
3. "SAP S/4HANA" appears only as a skill under SAP ABAP Consultant, never as a standalone job_title.
"""

from __future__ import annotations

import unittest
from dotenv import load_dotenv

load_dotenv()

from config import Settings
from requirement_parser import parse_requirements_from_email


class TestKpmgTableRegression(unittest.TestCase):
    def test_workday_fte_urgent_requirements_roles(self) -> None:
        subject = "WORKDAY | FTE - Urgent Requirements"
        body = """Dear Partner,

Please share profiles for below urgent requirements:

1. Workday Financials Consultant
Location: Hyderabad / Bangalore / Pune
Exp: 5+ Years
Skills: Workday Financials, Core Financials, Business Process

2. Workday Integration Consultant
Location: Any
Exp: 4+ Years
Skills: Workday Studio, EIB, Core Connectors

3. SAP ABAP Consultant
Location: Bangalore
Exp: 6+ Years
Skills: SAP ABAP, S/4HANA, OData, CDS Views

Thanks"""

        settings = Settings.from_env()
        result = parse_requirements_from_email(subject=subject, body=body, settings=settings)

        # Assert exactly 3 roles extracted
        self.assertEqual(len(result.requirements), 3, f"Expected 3 roles, got {len(result.requirements)}")

        extracted_titles = [req.job_title for req in result.requirements]
        
        # Assert no fake role "SAP S/4HANA" in extracted titles
        self.assertNotIn("SAP S/4HANA", extracted_titles, "SAP S/4HANA should not be extracted as a job title")

        # Assert correct 3 job titles exist
        expected_titles = {
            "Workday Financials Consultant",
            "Workday Integration Consultant",
            "SAP ABAP Consultant",
        }
        self.assertEqual(set(extracted_titles), expected_titles)

        # Confirm SAP S/4HANA / S/4HANA appears as a skill under SAP ABAP Consultant
        abap_req = next((r for r in result.requirements if "SAP ABAP" in r.job_title), None)
        self.assertIsNotNone(abap_req, "SAP ABAP Consultant role must exist")
        all_skills = [s.upper() for s in (abap_req.mandatory_skills or []) + (abap_req.soft_skills or [])]
        self.assertTrue(
            any("S/4HANA" in s or "SAP S/4HANA" in s for s in all_skills),
            f"Expected S/4HANA in SAP ABAP Consultant skills, got {all_skills}",
        )


if __name__ == "__main__":
    unittest.main()
