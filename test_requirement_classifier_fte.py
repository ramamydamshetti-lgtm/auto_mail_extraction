"""Tests for FTE / structured JD heuristic (no LLM calls)."""

from __future__ import annotations

import unittest

from requirement_classifier import heuristic_obvious_client_requirement, heuristic_structured_client_jd


KPMG_WORKDAY_BODY = """
Hi Raghu,

Need urgent and critical

Yrs – 7-8+
Budget – Will let u know
Location – Remote

Start time June/ July

Workday Integration SME

Role title: Workday Integration SME
Assignment: Support Global Mobility Upgrade and FWMT replacement
Reporting to: Programme / Tech Lead
Type:  project resource
Indicative focus: Workday interfaces, data flows, integration build/support

Role purpose

The Workday Integration SME will lead and support design, build, repointing, testing,
and stabilization of Workday integrations required for the Global Mobility Upgrade.

Key responsibilities

Design, build, enhance, or repoint Workday integrations required to support programme delivery
Define and maintain data mappings between Workday and connected systems

Skills and experience

Must have

Strong Workday integration experience across the full lifecycle
Workday Studio (mandatory)
Workday SOAP and REST APIs (HCM and Recruiting preferred)

Regards,
Vinuta
""".strip()


class TestStructuredClientJdHeuristic(unittest.TestCase):
    def test_kpmg_workday_fte_passes(self) -> None:
        self.assertTrue(
            heuristic_structured_client_jd("WORKDAY | FTE", KPMG_WORKDAY_BODY),
        )
        self.assertTrue(
            heuristic_obvious_client_requirement("WORKDAY | FTE", KPMG_WORKDAY_BODY),
        )

    def test_weekly_report_still_blocked(self) -> None:
        body = (
            "Following is the weekly report\n"
            "No of submissions: 12\n"
            "L1 interviews: 4\n"
            "No of rejections: 2\n"
            "Details of list of candidate submitted below"
        )
        self.assertFalse(heuristic_structured_client_jd("Weekly report", body))
        self.assertFalse(heuristic_obvious_client_requirement("Weekly report", body))

    def test_profile_hold_without_jd_still_blocked(self) -> None:
        body = (
            "Dear Vendor,\n"
            "Request you to HOLD in sharing more profiles, as we are seeking feedback.\n"
            "We shall let you know once we need more profiles."
        )
        self.assertFalse(heuristic_structured_client_jd("RE: Requirement - BA roles", body))

    def test_short_ack_not_bypassed(self) -> None:
        self.assertFalse(heuristic_structured_client_jd("RE: Some thread", "Done\n\nThanks"))

    def test_new_fte_jd_markers_threshold(self) -> None:
        # Body with 3 new markers: "Job Title:", "Job Summary", "Primary Skills"
        body_3_markers = (
            "Job Title: Senior Java Developer\n"
            "Job Summary: Responsible for backend development and API integration.\n"
            "Primary Skills: Java, Spring Boot, Microservices\n"
            "Secondary Skills: Docker, Kubernetes"
        )
        self.assertTrue(heuristic_structured_client_jd("New Opening", body_3_markers))

        # Single marker alone ("Job Title:") should NOT trigger requirement
        single_marker_body = "Job Title: Developer"
        self.assertFalse(heuristic_structured_client_jd("Quick update", single_marker_body))


if __name__ == "__main__":
    unittest.main()

