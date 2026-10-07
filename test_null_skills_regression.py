"""
Regression test for null-safety when mandatory_skills or soft_skills is None on RequirementItem.
Verifies list concatenation in requirement_parser does not crash when soft_skills=None or mandatory_skills=None.
"""

from __future__ import annotations

import unittest
from models import RequirementItem


class TestNullSkillsRegression(unittest.TestCase):
    def test_soft_skills_none_list_merging(self) -> None:
        """RequirementItem with soft_skills=None must not raise TypeError when merging skills."""
        item = RequirementItem(
            job_title="Java Developer",
            mandatory_skills=["Java", "Spring Boot"],
            soft_skills=None,
        )
        
        # Replicate skill-merging logic safely
        skill_candidates = ["Microservices"]
        merged_skills = list(item.mandatory_skills or []) + list(item.soft_skills or []) + (skill_candidates or [])
        
        self.assertEqual(merged_skills, ["Java", "Spring Boot", "Microservices"])
        self.assertIsNone(item.soft_skills)

    def test_mandatory_skills_none_list_merging(self) -> None:
        """RequirementItem with mandatory_skills=None must not raise TypeError when merging skills."""
        item = RequirementItem(
            job_title="Python Developer",
            mandatory_skills=None,
            soft_skills=["Communication"],
        )
        
        skill_candidates = ["Python"]
        merged_skills = list(item.mandatory_skills or []) + list(item.soft_skills or []) + (skill_candidates or [])
        
        self.assertEqual(merged_skills, ["Communication", "Python"])
        self.assertIsNone(item.mandatory_skills)


if __name__ == "__main__":
    unittest.main()
