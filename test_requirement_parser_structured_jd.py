"""Parser heuristics for structured FTE/project JD emails (no LLM)."""

from __future__ import annotations

import unittest

from models import RequirementItem
from requirement_parser import (
    _apply_structured_jd_single_role,
    _extract_multi_role_rows,
    _extract_role_title_field,
    _is_reporting_manager_role,
)
from test_requirement_classifier_fte import KPMG_WORKDAY_BODY


class TestStructuredJdParserHeuristics(unittest.TestCase):
    def test_role_title_field_extracted(self) -> None:
        self.assertEqual(_extract_role_title_field(KPMG_WORKDAY_BODY), "Workday Integration SME")

    def test_reporting_manager_not_a_hiring_role(self) -> None:
        self.assertTrue(_is_reporting_manager_role("Programme / Tech Lead", KPMG_WORKDAY_BODY))

    def test_multi_role_rows_ignore_reporting_line(self) -> None:
        self.assertEqual(_extract_multi_role_rows(KPMG_WORKDAY_BODY), [])

    def test_structured_jd_collapses_to_single_role(self) -> None:
        items = [
            RequirementItem(
                job_title="The Workday Integration SME will lead",
                mandatory_skills=["Workday"],
                confidence=0.9,
            ),
            RequirementItem(
                job_title="Programme / Tech Lead",
                mandatory_skills=["Programme"],
                confidence=0.8,
            ),
        ]
        out = _apply_structured_jd_single_role(items, subject="WORKDAY | FTE", body=KPMG_WORKDAY_BODY)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].job_title, "Workday Integration SME")


if __name__ == "__main__":
    unittest.main()
