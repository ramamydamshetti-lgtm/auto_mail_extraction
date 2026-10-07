"""
Regression tests for Location Extraction, Normalization, and Generic Phrase Rejection.

Covers:
1. Gurugram(DDC5F)
2. Gurgaon
3. Bengaluru/Bangalore
4. Mumbai(MDC-5)
5. Bengaluru (Manyata)/Delhi NCR
6. Multiple locations across separate requirement rows
7. Client location must not become geographic location
8. Generic location phrases must not become geographic locations
"""

from __future__ import annotations

import pytest

from requirement_comparator import normalize_city
from requirement_parser import extract_req_id_table_requirements
from field_mapper import map_to_metaforge, map_to_ui_payload, EmailContext
from strict_validator import validate_requirement_before_save


def test_1_gurugram_ddc5f():
    # 1. Normalization
    assert normalize_city("Gurugram(DDC5F)") == "gurgaon"
    assert normalize_city("DDC5F") == "gurgaon"

    # 2. Table extraction
    body = (
        "173640-1\n"
        "8\n"
        "SAP ABAP Cloud\n"
        "Gurugram(DDC5F)\n"
        "RTO\n"
        "3 Lakhs\n"
        "7.5 Yrs\n"
        "P1\n"
    )
    reqs = extract_req_id_table_requirements(body, subject="Demand Email", from_email="hiring@accenture.com")
    assert len(reqs) == 1
    assert reqs[0].req_id == "173640-1"
    assert reqs[0].job_title == "SAP ABAP Cloud"
    assert reqs[0].location == ["Gurugram(DDC5F)"]

    # 3. Field mapping
    ctx = EmailContext(
        graph_message_id="msg-1",
        internet_message_id="<msg-1@client.com>",
        to_emails=["recruiter@metaforgeit.com"],
        cc_emails=["lead@client.com"],
        from_email="manager@client.com",
        from_name="Manager",
    )
    mapped = map_to_metaforge(
        {"job_title": "SAP ABAP Cloud", "location": "Gurugram(DDC5F)", "client_jd_id": "173640-1"},
        ctx=ctx,
        client_display_name="Accenture",
        job_id="job-1",
        client_jd_id="173640-1",
        body_text=body,
    )
    assert mapped["location"] == "Gurugram(DDC5F)"


def test_2_gurgaon():
    # 1. Normalization
    assert normalize_city("Gurgaon") == "gurgaon"
    assert normalize_city("Gurugram") == "gurgaon"

    # 2. Table extraction
    body = (
        "180001-1\n"
        "Java Developer\n"
        "Gurgaon\n"
        "5-8 Yrs\n"
        "Open\n"
    )
    reqs = extract_req_id_table_requirements(body, subject="Demand Email", from_email="hiring@accenture.com")
    assert len(reqs) == 1
    assert reqs[0].location == ["Gurgaon"]

    # 3. Mapping
    ctx = EmailContext("m", "<m>", ["r@metaforgeit.com"], [], "c@client.com", "Client")
    mapped = map_to_metaforge(
        {"job_title": "Java Developer", "location": "Gurgaon", "client_jd_id": "180001-1"},
        ctx=ctx,
        client_display_name="Accenture",
        job_id="job-2",
        client_jd_id="180001-1",
    )
    assert mapped["location"] == "Gurgaon"


def test_3_bengaluru_bangalore():
    # 1. Normalization
    assert normalize_city("Bengaluru") == "bangalore"
    assert normalize_city("Bangalore") == "bangalore"
    assert normalize_city("Bengaluru/Bangalore") == "bangalore"

    # 2. Mapping preserves multi-location
    ctx = EmailContext("m", "<m>", ["r@metaforgeit.com"], [], "c@client.com", "Client")
    mapped = map_to_metaforge(
        {"job_title": "DevOps Engineer", "location": "Bengaluru/Bangalore", "client_jd_id": "180002-1"},
        ctx=ctx,
        client_display_name="Accenture",
        job_id="job-3",
        client_jd_id="180002-1",
    )
    assert "Bengaluru" in mapped["location"] and "Bangalore" in mapped["location"]


def test_4_mumbai_mdc5():
    # 1. Normalization
    assert normalize_city("Mumbai(MDC-5)") == "mumbai"
    assert normalize_city("MDC-5") == "mumbai"

    # 2. Table extraction
    body = (
        "201120-1\n"
        "SAP Integrated Business Planning (IBP)\n"
        "Mumbai(MDC-5)\n"
        "5 Yrs\n"
        "2.40 Lakhs\n"
    )
    reqs = extract_req_id_table_requirements(body, subject="Demand Email", from_email="hiring@accenture.com")
    assert len(reqs) == 1
    assert reqs[0].location == ["Mumbai(MDC-5)"]


def test_5_bengaluru_manyata_delhi_ncr():
    # 1. Normalization
    assert normalize_city("Bengaluru (Manyata)") == "bangalore"
    assert normalize_city("Delhi NCR") == "delhi"
    assert normalize_city("Bengaluru (Manyata)/Delhi NCR") == "bangalore"

    # 2. Mapping preserves both locations
    ctx = EmailContext("m", "<m>", ["r@metaforgeit.com"], [], "c@client.com", "Client")
    mapped = map_to_metaforge(
        {"job_title": "Cloud Architect", "location": "Bengaluru (Manyata)/Delhi NCR", "client_jd_id": "180005-1"},
        ctx=ctx,
        client_display_name="Accenture",
        job_id="job-5",
        client_jd_id="180005-1",
    )
    assert "Bengaluru (Manyata)" in mapped["location"]
    assert "Delhi NCR" in mapped["location"]


def test_6_multiple_locations_across_separate_requirement_rows():
    body = (
        "173640-1\nSAP ABAP Cloud\nGurugram(DDC5F)\n7.5 Yrs\n3 Lakhs\n"
        "195414-1\nMemory Design\nBangalore(BDC6F)\n6 Yrs\nOpen\n"
        "198381-1\nSAP FICA\nPune(PDC-3)\n4 Yrs\n1.90 Lakhs\n"
        "201120-1\nSAP IBP\nMumbai(MDC-5)\n5 Yrs\n2.40 Lakhs\n"
    )
    reqs = extract_req_id_table_requirements(body, subject="Batch Demand", from_email="hiring@accenture.com")
    assert len(reqs) == 4

    req_map = {r.req_id: r for r in reqs}
    assert req_map["173640-1"].location == ["Gurugram(DDC5F)"]
    assert req_map["195414-1"].location == ["Bangalore(BDC6F)"]
    assert req_map["198381-1"].location == ["Pune(PDC-3)"]
    assert req_map["201120-1"].location == ["Mumbai(MDC-5)"]


def test_7_client_location_must_not_become_geographic_location():
    # 1. Normalization returns None
    assert normalize_city("Client location") is None
    assert normalize_city("client site") is None
    assert normalize_city("Client office") is None

    # 2. Table extractor must NOT treat it as a location
    body = (
        "180010-1\n"
        "Data Engineer\n"
        "Client location\n"
        "5 Yrs\n"
        "Open\n"
    )
    reqs = extract_req_id_table_requirements(body, subject="Demand Email", from_email="hiring@accenture.com")
    assert len(reqs) == 1
    # Location should not be set to "Client location"
    assert reqs[0].location == [] or reqs[0].location is None

    # 3. Field mapper maps work mode to On-site, but location to empty
    ctx = EmailContext("m", "<m>", ["r@metaforgeit.com"], [], "c@client.com", "Client")
    mapped = map_to_metaforge(
        {"job_title": "Data Engineer", "location": "Client location", "client_jd_id": "180010-1"},
        ctx=ctx,
        client_display_name="Accenture",
        job_id="job-7",
        client_jd_id="180010-1",
        body_text="Work is at client location",
    )
    assert mapped["location"] is None, f"Mapped location should be None, got: {mapped['location']}"

    # 4. Strict validator sets location to None
    val, _, _ = validate_requirement_before_save(
        {"job_title": "Data Engineer", "location": "Client location"},
        block_text="Data Engineer 5 Yrs Client location",
    )
    assert val.get("location") is None


def test_8_generic_location_phrases_must_not_become_geographic_locations():
    generic_phrases = [
        "Any LTTS Location",
        "Any LTTS office",
        "Any office",
        "Any location",
        "Pan India",
        "Client location",
        "Client site",
    ]
    ctx = EmailContext("m", "<m>", ["r@metaforgeit.com"], [], "c@client.com", "Client")

    for phrase in generic_phrases:
        # Normalization returns None
        assert normalize_city(phrase) is None, f"Failed for {phrase}"

        # Field mapper strips it
        mapped = map_to_metaforge(
            {"job_title": "Software Engineer", "location": phrase, "client_jd_id": "180020-1"},
            ctx=ctx,
            client_display_name="Accenture",
            job_id="job-8",
            client_jd_id="180020-1",
        )
        assert mapped["location"] is None, f"Mapped location should be None for {phrase}, got: {mapped['location']}"

        # Strict validator nullifies it
        val, _, _ = validate_requirement_before_save(
            {"job_title": "Software Engineer", "location": phrase},
            block_text=f"Software Engineer {phrase}",
        )
        assert val.get("location") is None, f"Validator should nullify {phrase}, got: {val.get('location')}"
