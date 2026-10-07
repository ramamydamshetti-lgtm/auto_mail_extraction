"""
Tests for whole-requirement comparison and duplicate rules W1-W9:
1. Same requirement re-sent with skills in a different order and "5-7 yrs" vs "5+ years": duplicate, one record.
2. Same requirement, same client ID, different wording: duplicate.
3. Same role in Pune and Mumbai: two records.
4. Same client, IDs 203421-1 and 203421-2: two records.
5. Reply quoting the original with no new content: no new record.
6. Two identical rows inside one email: one record.
7. Score 0.78: one review item linked to the original, no new requirement.
8. Duplicate containing "on hold": status updated, details untouched.
9. Two workers process the same email at the same time: one record.
10. Different clients with the same title and city: two records.
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import shutil
import sqlite3
import tempfile
from unittest.mock import patch

import pytest

from config import Settings
from main import process_single_message
from metaforge_api import IdAllocator
from models import RequirementItem, RequirementParseResult
from processed_store import ProcessedStore


@pytest.fixture
def temp_env():
    td = tempfile.mkdtemp(prefix="test_whole_req_")
    req_db = os.path.join(td, "test_metaforge.db")
    proc_db = os.path.join(td, "test_processed.db")
    id_db = os.path.join(td, "test_id.db")

    # Set up metaforge schema
    conn = sqlite3.connect(req_db)
    conn.execute(
        """CREATE TABLE metaforge_requirements (
            job_id TEXT PRIMARY KEY,
            payload_json TEXT,
            created_at TEXT,
            client_jd_id TEXT,
            updated_at TEXT,
            field_change_history TEXT,
            identity TEXT
        )"""
    )
    conn.commit()
    conn.close()

    store = ProcessedStore(proc_db)
    allocator = IdAllocator(id_db)

    settings = Settings(
        azure_tenant_id="",
        azure_client_id="",
        azure_client_secret="",
        mailbox_upn="recruitment.application@metaforgeit.com",
        openai_api_key="",
        openai_model="gpt-4o-mini",
        metaforge_api_url="",
        metaforge_requirements_endpoint="",
        metaforge_mode="sqlite",
        metaforge_sqlite_path=req_db,
        metaforge_id_db=id_db,
        processed_db=proc_db,
        log_level="DEBUG",
        similarity_weights={
            "title": 0.25,
            "skills": 0.25,
            "experience": 0.15,
            "whole_text": 0.25,
            "other_fields": 0.10,
        },
        similarity_thresholds={
            "duplicate": 0.85,
            "possible_duplicate": 0.70,
        },
    )

    yield {
        "td": td,
        "req_db": req_db,
        "proc_db": proc_db,
        "id_db": id_db,
        "store": store,
        "allocator": allocator,
        "settings": settings,
    }

    try:
        allocator.close()
    except Exception:
        pass
    try:
        store.close()
    except Exception:
        pass
    try:
        shutil.rmtree(td, ignore_errors=True)
    except Exception:
        pass


def _query(db_path: str, sql: str, params: tuple = ()) -> list:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()
    return rows


_DEFAULT_FROM = {"emailAddress": {"address": "recruiter@iexcel.co.in", "name": "Recruiter"}}


def test_1_skills_reordered_and_exp_variation(temp_env):
    """1. Same requirement re-sent with skills in a different order and '5-7 yrs' vs '5+ years': duplicate, one record."""
    store = temp_env["store"]
    settings = temp_env["settings"]
    allocator = temp_env["allocator"]

    item1 = RequirementItem(
        req_id=None,
        raw_status="Open",
        job_title="Java Backend Engineer",
        location=["Bangalore"],
        overall_experience="5-7 yrs",
        mandatory_skills=["Java", "Spring Boot", "Microservices", "SQL"],
        client_name="Accenture",
        confidence=1.0,
    )
    msg1 = {
        "id": "msg_001_a",
        "internetMessageId": "<001_a@accenture.com>",
        "receivedDateTime": "2026-09-10T10:00:00Z",
        "subject": "Accenture Java Backend Requirement",
        "from": _DEFAULT_FROM,
        "body": {"contentType": "text", "content": "Looking for Java Backend Engineer with 5-7 yrs experience in Java, Spring Boot, Microservices, SQL in Bangalore."},
    }

    item2 = RequirementItem(
        req_id=None,
        raw_status="Open",
        job_title="Java Backend Engineer",
        location=["Bangalore"],
        overall_experience="5+ years",
        mandatory_skills=["Microservices", "SQL", "Java", "Spring Boot"],
        client_name="Accenture",
        confidence=1.0,
    )
    msg2 = {
        "id": "msg_001_b",
        "internetMessageId": "<001_b@accenture.com>",
        "receivedDateTime": "2026-09-12T10:00:00Z",
        "subject": "Accenture Java Backend Requirement Re-sent",
        "from": _DEFAULT_FROM,
        "body": {"contentType": "text", "content": "Looking for Java Backend Engineer with 5+ years experience in Microservices, SQL, Java, Spring Boot in Bangalore."},
    }

    with patch("main.parse_requirements_from_email", return_value=RequirementParseResult(requirements=[item1], overall_confidence=1.0)):
        res1 = process_single_message(raw=msg1, token="", mailbox="test", settings=settings, allocator=allocator, store=store, skip_classifier=True)
        assert res1 == 1

    with patch("main.parse_requirements_from_email", return_value=RequirementParseResult(requirements=[item2], overall_confidence=1.0)):
        res2 = process_single_message(raw=msg2, token="", mailbox="test", settings=settings, allocator=allocator, store=store, skip_classifier=True)
        assert res2 == 0

    rows = _query(temp_env["req_db"], "SELECT job_id FROM metaforge_requirements")
    assert len(rows) == 1


def test_2_same_requirement_same_client_id_different_wording(temp_env):
    """2. Same requirement, same client ID, different wording: duplicate."""
    store = temp_env["store"]
    settings = temp_env["settings"]
    allocator = temp_env["allocator"]

    item1 = RequirementItem(
        req_id="203421-1",
        raw_status="Open",
        job_title="Senior Python Architect",
        location=["Bangalore"],
        overall_experience="8-10 years",
        mandatory_skills=["Python", "Architecture", "Distributed Systems"],
        client_name="Accenture",
        confidence=1.0,
    )
    msg1 = {
        "id": "msg_002_a",
        "internetMessageId": "<002_a@accenture.com>",
        "receivedDateTime": "2026-09-10T10:00:00Z",
        "subject": "Accenture Requirement 203421-1",
        "from": _DEFAULT_FROM,
        "body": {"contentType": "text", "content": "We need Senior Python Architect with distributed systems background."},
    }

    item2 = RequirementItem(
        req_id="203421-1",
        raw_status="Open",
        job_title="Python Developer Lead",
        location=["Bangalore"],
        overall_experience="7 years",
        mandatory_skills=["Python", "FastAPI"],
        client_name="Accenture",
        confidence=1.0,
    )
    msg2 = {
        "id": "msg_002_b",
        "internetMessageId": "<002_b@accenture.com>",
        "receivedDateTime": "2026-09-12T10:00:00Z",
        "subject": "Accenture Updated Req 203421-1",
        "from": _DEFAULT_FROM,
        "body": {"contentType": "text", "content": "Updated description for req 203421-1 Lead Python Developer in Bangalore."},
    }

    with patch("main.parse_requirements_from_email", return_value=RequirementParseResult(requirements=[item1], overall_confidence=1.0)):
        res1 = process_single_message(raw=msg1, token="", mailbox="test", settings=settings, allocator=allocator, store=store, skip_classifier=True)
        assert res1 == 1

    with patch("main.parse_requirements_from_email", return_value=RequirementParseResult(requirements=[item2], overall_confidence=1.0)):
        res2 = process_single_message(raw=msg2, token="", mailbox="test", settings=settings, allocator=allocator, store=store, skip_classifier=True)
        assert res2 == 0

    rows = _query(temp_env["req_db"], "SELECT job_id, client_jd_id FROM metaforge_requirements")
    assert len(rows) == 1
    assert rows[0][1] == "203421-1"


def test_3_same_role_in_pune_and_mumbai(temp_env):
    """3. Same role in Pune and Mumbai: two records."""
    store = temp_env["store"]
    settings = temp_env["settings"]
    allocator = temp_env["allocator"]

    item_pune = RequirementItem(
        req_id=None,
        raw_status="Open",
        job_title="DevOps Specialist",
        location=["Pune"],
        overall_experience="5 years",
        mandatory_skills=["AWS", "Kubernetes"],
        client_name="Accenture",
        confidence=1.0,
    )
    msg_pune = {
        "id": "msg_003_pune",
        "internetMessageId": "<003_pune@accenture.com>",
        "receivedDateTime": "2026-09-10T10:00:00Z",
        "subject": "Accenture DevOps Pune",
        "from": _DEFAULT_FROM,
        "body": {"contentType": "text", "content": "DevOps Specialist position in Pune office."},
    }

    item_mumbai = RequirementItem(
        req_id=None,
        raw_status="Open",
        job_title="DevOps Specialist",
        location=["Mumbai"],
        overall_experience="5 years",
        mandatory_skills=["AWS", "Kubernetes"],
        client_name="Accenture",
        confidence=1.0,
    )
    msg_mumbai = {
        "id": "msg_003_mumbai",
        "internetMessageId": "<003_mumbai@accenture.com>",
        "receivedDateTime": "2026-09-11T10:00:00Z",
        "subject": "Accenture DevOps Mumbai",
        "from": _DEFAULT_FROM,
        "body": {"contentType": "text", "content": "DevOps Specialist position in Mumbai office."},
    }

    with patch("main.parse_requirements_from_email", return_value=RequirementParseResult(requirements=[item_pune], overall_confidence=1.0)):
        res1 = process_single_message(raw=msg_pune, token="", mailbox="test", settings=settings, allocator=allocator, store=store, skip_classifier=True)
        assert res1 == 1

    with patch("main.parse_requirements_from_email", return_value=RequirementParseResult(requirements=[item_mumbai], overall_confidence=1.0)):
        res2 = process_single_message(raw=msg_mumbai, token="", mailbox="test", settings=settings, allocator=allocator, store=store, skip_classifier=True)
        assert res2 == 1

    rows = _query(temp_env["req_db"], "SELECT job_id FROM metaforge_requirements")
    assert len(rows) == 2


def test_4_same_client_ids_differ_suffix(temp_env):
    """4. Same client, IDs 203421-1 and 203421-2: two records."""
    store = temp_env["store"]
    settings = temp_env["settings"]
    allocator = temp_env["allocator"]

    item1 = RequirementItem(
        req_id="203421-1",
        raw_status="Open",
        job_title="React Developer",
        location=["Hyderabad"],
        overall_experience="4 years",
        mandatory_skills=["React", "TypeScript"],
        client_name="Accenture",
        confidence=1.0,
    )
    msg1 = {
        "id": "msg_004_1",
        "internetMessageId": "<004_1@accenture.com>",
        "receivedDateTime": "2026-09-10T10:00:00Z",
        "subject": "Accenture 203421-1",
        "from": _DEFAULT_FROM,
        "body": {"contentType": "text", "content": "React Developer 203421-1 in Hyderabad."},
    }

    item2 = RequirementItem(
        req_id="203421-2",
        raw_status="Open",
        job_title="React Developer",
        location=["Hyderabad"],
        overall_experience="4 years",
        mandatory_skills=["React", "TypeScript"],
        client_name="Accenture",
        confidence=1.0,
    )
    msg2 = {
        "id": "msg_004_2",
        "internetMessageId": "<004_2@accenture.com>",
        "receivedDateTime": "2026-09-11T10:00:00Z",
        "subject": "Accenture 203421-2",
        "from": _DEFAULT_FROM,
        "body": {"contentType": "text", "content": "React Developer 203421-2 in Hyderabad."},
    }

    with patch("main.parse_requirements_from_email", return_value=RequirementParseResult(requirements=[item1], overall_confidence=1.0)):
        res1 = process_single_message(raw=msg1, token="", mailbox="test", settings=settings, allocator=allocator, store=store, skip_classifier=True)
        assert res1 == 1

    with patch("main.parse_requirements_from_email", return_value=RequirementParseResult(requirements=[item2], overall_confidence=1.0)):
        res2 = process_single_message(raw=msg2, token="", mailbox="test", settings=settings, allocator=allocator, store=store, skip_classifier=True)
        assert res2 == 1

    rows = _query(temp_env["req_db"], "SELECT job_id, client_jd_id FROM metaforge_requirements")
    assert len(rows) == 2
    cjd_set = {r[1] for r in rows}
    assert "203421-1" in cjd_set
    assert "203421-2" in cjd_set


def test_5_reply_quoting_original_no_new_content(temp_env):
    """5. Reply quoting the original with no new content: no new record."""
    store = temp_env["store"]
    settings = temp_env["settings"]
    allocator = temp_env["allocator"]

    item1 = RequirementItem(
        req_id=None,
        raw_status="Open",
        job_title="Cloud Architect",
        location=["Bangalore"],
        overall_experience="10 years",
        mandatory_skills=["AWS", "GCP", "Kubernetes"],
        client_name="Accenture",
        confidence=1.0,
    )
    orig_body = "Looking for Cloud Architect with 10 years experience in AWS, GCP, Kubernetes in Bangalore."
    msg1 = {
        "id": "msg_005_orig",
        "internetMessageId": "<005_orig@accenture.com>",
        "receivedDateTime": "2026-09-10T10:00:00Z",
        "subject": "Requirement: Cloud Architect",
        "from": _DEFAULT_FROM,
        "body": {"contentType": "text", "content": orig_body},
    }

    reply_body = (
        "Hi Team,\n\n"
        "Please prioritize this.\n\n"
        "Thanks & Regards,\nRecruiter\n\n"
        "> On Sep 10, 2026, at 10:00 AM, lead@accenture.com wrote:\n"
        f"> {orig_body}"
    )
    msg2 = {
        "id": "msg_005_reply",
        "internetMessageId": "<005_reply@accenture.com>",
        "receivedDateTime": "2026-09-11T12:00:00Z",
        "subject": "Re: Requirement: Cloud Architect",
        "from": _DEFAULT_FROM,
        "body": {"contentType": "text", "content": reply_body},
    }

    with patch("main.parse_requirements_from_email", return_value=RequirementParseResult(requirements=[item1], overall_confidence=1.0)):
        res1 = process_single_message(raw=msg1, token="", mailbox="test", settings=settings, allocator=allocator, store=store, skip_classifier=True)
        assert res1 == 1

    with patch("main.parse_requirements_from_email", return_value=RequirementParseResult(requirements=[item1], overall_confidence=1.0)):
        res2 = process_single_message(raw=msg2, token="", mailbox="test", settings=settings, allocator=allocator, store=store, skip_classifier=True)
        assert res2 == 0

    rows = _query(temp_env["req_db"], "SELECT job_id FROM metaforge_requirements")
    assert len(rows) == 1


def test_6_two_identical_rows_inside_one_email(temp_env):
    """6. Two identical rows inside one email: one record."""
    store = temp_env["store"]
    settings = temp_env["settings"]
    allocator = temp_env["allocator"]

    item = RequirementItem(
        req_id=None,
        raw_status="Open",
        job_title="Data Engineer",
        location=["Pune"],
        overall_experience="4-6 years",
        mandatory_skills=["Python", "Spark"],
        client_name="Accenture",
        confidence=1.0,
    )
    msg = {
        "id": "msg_006_multi",
        "internetMessageId": "<006_multi@accenture.com>",
        "receivedDateTime": "2026-09-10T10:00:00Z",
        "subject": "Accenture Openings",
        "from": _DEFAULT_FROM,
        "body": {"contentType": "text", "content": "Data Engineer role in Pune 4-6 yrs with Python, Spark."},
    }

    with patch("main.parse_requirements_from_email", return_value=RequirementParseResult(requirements=[item, item], overall_confidence=1.0)):
        res = process_single_message(raw=msg, token="", mailbox="test", settings=settings, allocator=allocator, store=store, skip_classifier=True)
        assert res == 1

    rows = _query(temp_env["req_db"], "SELECT job_id FROM metaforge_requirements")
    assert len(rows) == 1


def test_7_score_0_78_possible_duplicate_review_item_linked(temp_env):
    """7. Score 0.78: one review item linked to the original, no new requirement."""
    store = temp_env["store"]
    settings = temp_env["settings"]
    allocator = temp_env["allocator"]

    item1 = RequirementItem(
        req_id=None,
        raw_status="Open",
        job_title="Senior Java Software Engineer",
        location=["Bangalore"],
        overall_experience="6-8 yrs",
        mandatory_skills=["Java", "Spring Boot", "Kafka", "SQL", "Docker"],
        client_name="Accenture",
        confidence=1.0,
    )
    msg1 = {
        "id": "msg_007_a",
        "internetMessageId": "<007_a@accenture.com>",
        "receivedDateTime": "2026-09-10T10:00:00Z",
        "subject": "Accenture Senior Java Software Engineer",
        "from": _DEFAULT_FROM,
        "body": {"contentType": "text", "content": "Senior Java Software Engineer with Java, Spring Boot, Kafka, SQL, Docker in Bangalore with 6-8 yrs exp."},
    }

    item2 = RequirementItem(
        req_id=None,
        raw_status="Open",
        job_title="Java Software Engineer",
        location=["Bangalore"],
        overall_experience="5-7 yrs",
        mandatory_skills=["Java", "Spring Boot", "Kafka"],
        client_name="Accenture",
        confidence=1.0,
    )
    msg2 = {
        "id": "msg_007_b",
        "internetMessageId": "<007_b@accenture.com>",
        "receivedDateTime": "2026-09-12T10:00:00Z",
        "subject": "Accenture Java Software Engineer",
        "from": _DEFAULT_FROM,
        "body": {"contentType": "text", "content": "Java Software Engineer with Java, Spring Boot, Kafka in Bangalore with 5-7 yrs exp."},
    }

    with patch("main.parse_requirements_from_email", return_value=RequirementParseResult(requirements=[item1], overall_confidence=1.0)):
        res1 = process_single_message(raw=msg1, token="", mailbox="test", settings=settings, allocator=allocator, store=store, skip_classifier=True)
        assert res1 == 1

    stored_rows = _query(temp_env["req_db"], "SELECT job_id FROM metaforge_requirements")
    original_job_id = stored_rows[0][0]

    with patch("main.parse_requirements_from_email", return_value=RequirementParseResult(requirements=[item2], overall_confidence=1.0)):
        res2 = process_single_message(raw=msg2, token="", mailbox="test", settings=settings, allocator=allocator, store=store, skip_classifier=True)
        assert res2 == 0

    # metaforge_requirements still has only 1 requirement
    stored_rows_after = _query(temp_env["req_db"], "SELECT job_id FROM metaforge_requirements")
    assert len(stored_rows_after) == 1

    # pending_reviews has 1 review item linked to original requirement
    pending_rows = _query(temp_env["proc_db"], "SELECT id, review_fields, possible_duplicate_of FROM pending_reviews")
    assert len(pending_rows) == 1
    assert "possible_duplicate" in pending_rows[0][1]
    assert pending_rows[0][2] == original_job_id


def test_8_duplicate_containing_on_hold(temp_env):
    """8. Duplicate containing 'on hold': status updated, details untouched."""
    store = temp_env["store"]
    settings = temp_env["settings"]
    allocator = temp_env["allocator"]

    item1 = RequirementItem(
        req_id="200964-1",
        raw_status="Open",
        job_title="SAP FICO Consultant",
        location=["Mumbai"],
        overall_experience="6 years",
        mandatory_skills=["SAP FICO", "S/4HANA"],
        client_name="Accenture",
        confidence=1.0,
    )
    msg1 = {
        "id": "msg_008_a",
        "internetMessageId": "<008_a@accenture.com>",
        "receivedDateTime": "2026-09-10T10:00:00Z",
        "subject": "Accenture Demand 200964-1",
        "from": _DEFAULT_FROM,
        "body": {"contentType": "text", "content": "Accenture Demand 200964-1 SAP FICO Consultant in Mumbai."},
    }

    item2 = RequirementItem(
        req_id="200964-1",
        raw_status="Open",
        job_title="SAP FICO Consultant",
        location=["Mumbai"],
        overall_experience="6 years",
        mandatory_skills=["SAP FICO", "S/4HANA"],
        client_name="Accenture",
        confidence=1.0,
    )
    msg2 = {
        "id": "msg_008_b",
        "internetMessageId": "<008_b@accenture.com>",
        "receivedDateTime": "2026-09-15T10:00:00Z",
        "subject": "Hold notice for 200964-1",
        "from": _DEFAULT_FROM,
        "body": {"contentType": "text", "content": "Please note requirement 200964-1 has been put on hold until further notice."},
    }

    with patch("main.parse_requirements_from_email", return_value=RequirementParseResult(requirements=[item1], overall_confidence=1.0)):
        res1 = process_single_message(raw=msg1, token="", mailbox="test", settings=settings, allocator=allocator, store=store, skip_classifier=True)
        assert res1 == 1

    stored_before = _query(temp_env["req_db"], "SELECT job_id, payload_json FROM metaforge_requirements")[0]
    p_before = json.loads(stored_before[1])

    with patch("main.parse_requirements_from_email", return_value=RequirementParseResult(requirements=[item2], overall_confidence=1.0)):
        res2 = process_single_message(raw=msg2, token="", mailbox="test", settings=settings, allocator=allocator, store=store, skip_classifier=True)
        assert res2 == 0

    # Ensure details untouched
    stored_after = _query(temp_env["req_db"], "SELECT job_id, payload_json FROM metaforge_requirements")[0]
    p_after = json.loads(stored_after[1])
    assert p_before["job_title"] == p_after["job_title"]
    assert p_before["location"] == p_after["location"]

    # Verify status changed to hold in client_requirements and status_history
    cr_rows = _query(temp_env["proc_db"], "SELECT status FROM client_requirements WHERE client_jd_id = '200964-1'")
    assert len(cr_rows) == 1
    assert cr_rows[0][0] == "hold"

    sh_rows = _query(temp_env["proc_db"], "SELECT to_status, changed_by FROM status_history WHERE requirement_id = '200964-1'")
    assert len(sh_rows) >= 1
    assert sh_rows[-1][0] == "hold"


def test_9_two_workers_concurrent_same_email_one_record(temp_env):
    """9. Two workers process the same email at the same time: one record."""
    settings = temp_env["settings"]
    proc_db = temp_env["proc_db"]
    id_db = temp_env["id_db"]

    item = RequirementItem(
        req_id="204999-1",
        raw_status="Open",
        job_title="MLOps Engineer",
        location=["Bangalore"],
        overall_experience="5 years",
        mandatory_skills=["MLflow", "Kubeflow", "Python"],
        client_name="Accenture",
        confidence=1.0,
    )
    msg = {
        "id": "msg_009_conc",
        "internetMessageId": "<009_conc@accenture.com>",
        "receivedDateTime": "2026-09-10T10:00:00Z",
        "subject": "Accenture MLOps 204999-1",
        "from": _DEFAULT_FROM,
        "body": {"contentType": "text", "content": "Accenture MLOps Engineer position 204999-1 in Bangalore."},
    }

    def worker_run():
        w_store = ProcessedStore(proc_db)
        w_alloc = IdAllocator(id_db)
        try:
            with patch("main.parse_requirements_from_email", return_value=RequirementParseResult(requirements=[item], overall_confidence=1.0)):
                return process_single_message(raw=msg, token="", mailbox="test", settings=settings, allocator=w_alloc, store=w_store, skip_classifier=True)
        finally:
            w_alloc.close()
            w_store.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(worker_run)
        f2 = executor.submit(worker_run)
        r1 = f1.result()
        r2 = f2.result()

    # Between both workers, exactly 1 created the record
    assert r1 + r2 == 1

    rows = _query(temp_env["req_db"], "SELECT job_id, client_jd_id FROM metaforge_requirements")
    assert len(rows) == 1
    assert rows[0][1] == "204999-1"


def test_10_different_clients_same_title_and_city(temp_env):
    """10. Different clients with the same title and city: two records."""
    store = temp_env["store"]
    settings = temp_env["settings"]
    allocator = temp_env["allocator"]

    item_acc = RequirementItem(
        req_id=None,
        raw_status="Open",
        job_title="Data Scientist",
        location=["Bangalore"],
        overall_experience="4-6 years",
        mandatory_skills=["Python", "Machine Learning"],
        client_name="Accenture",
        confidence=1.0,
    )
    msg_acc = {
        "id": "msg_010_acc",
        "internetMessageId": "<010_acc@accenture.com>",
        "receivedDateTime": "2026-09-10T10:00:00Z",
        "subject": "Accenture Data Scientist",
        "from": _DEFAULT_FROM,
        "body": {"contentType": "text", "content": "Data Scientist opening in Bangalore at Accenture."},
    }

    item_kpmg = RequirementItem(
        req_id=None,
        raw_status="Open",
        job_title="Data Scientist",
        location=["Bangalore"],
        overall_experience="4-6 years",
        mandatory_skills=["Python", "Machine Learning"],
        client_name="KPMG",
        confidence=1.0,
    )
    msg_kpmg = {
        "id": "msg_010_kpmg",
        "internetMessageId": "<010_kpmg@kpmg.com>",
        "receivedDateTime": "2026-09-11T10:00:00Z",
        "subject": "KPMG Data Scientist",
        "from": _DEFAULT_FROM,
        "body": {"contentType": "text", "content": "Data Scientist opening in Bangalore at KPMG."},
    }

    with patch("main.parse_requirements_from_email", return_value=RequirementParseResult(requirements=[item_acc], overall_confidence=1.0)):
        res1 = process_single_message(raw=msg_acc, token="", mailbox="test", settings=settings, allocator=allocator, store=store, skip_classifier=True)
        assert res1 == 1

    with patch("main.parse_requirements_from_email", return_value=RequirementParseResult(requirements=[item_kpmg], overall_confidence=1.0)):
        res2 = process_single_message(raw=msg_kpmg, token="", mailbox="test", settings=settings, allocator=allocator, store=store, skip_classifier=True)
        assert res2 == 1

    rows = _query(temp_env["req_db"], "SELECT job_id, payload_json FROM metaforge_requirements")
    assert len(rows) == 2
    clients = {json.loads(r[1]).get("requirement_from") for r in rows}
    assert "Accenture" in clients
    assert "KPMG" in clients
