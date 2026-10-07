"""
Verification test for email reply loop deduplication and in-place updates.
Tests the exact scenario:
Client -> Recruiter -> Client -> Recruiter

Expected:
1 unique requirement -> 1 database record -> 1 UI record -> same requirement ID.
Client changes requirement -> same database record is updated -> same UI requirement is updated -> no new requirement created.
"""

import json
import os
import sys
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from config import Settings
from main import process_single_message
from metaforge_api import IdAllocator
from models import RequirementParseResult, RequirementItem
from processed_store import ProcessedStore


def test_reply_loop_deduplication_lifecycle():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        tmp_path = Path(tmp_dir)
        proc_db_path = tmp_path / "processed_messages.db"
        mf_db_path = tmp_path / "metaforge_requirements.db"

        # Mock settings to point to our test databases
        settings = Settings(
            azure_tenant_id="test-tenant",
            azure_client_id="test-client",
            azure_client_secret="test-secret",
            mailbox_upn="test@domain.com",
            openai_api_key="test-key",
            openai_model="gpt-4o",
            metaforge_api_url="",
            metaforge_requirements_endpoint="",
            metaforge_mode="sqlite",
            metaforge_sqlite_path=str(mf_db_path),
            metaforge_id_db=str(mf_db_path),
            processed_db=str(proc_db_path),
        )

        store = ProcessedStore(proc_db_path)
        allocator = IdAllocator(db_path=str(mf_db_path))

        conv_id = "AAQk-CONV-REPLY-LOOP-TEST-999"

        def mock_parse_reqs(subject="", body="", **kwargs):
            if "ITC-PY-8899" in (subject or "") or "ITC-PY-8899" in (body or ""):
                b_low = (body or "").lower()
                if "revisions" in b_low or "increased to 220000" in b_low:
                    return RequirementParseResult(
                        requirements=[
                            RequirementItem(
                                job_title="Senior Python Engineer",
                                mandatory_skills=["Python", "FastAPI", "AWS", "Docker", "Kafka"],
                                location=["Bangalore", "Pune"],
                                number_of_positions=2,
                                monthly_budget="220000",
                                overall_experience="5 - 8 Years",
                                req_id="ITC-PY-8899",
                                confidence=1.0,
                            )
                        ],
                        overall_confidence=1.0,
                    )
                elif "sourcing profiles" in b_low or "noted" in b_low:
                    return RequirementParseResult(requirements=[], overall_confidence=0.0)
                else:
                    return RequirementParseResult(
                        requirements=[
                            RequirementItem(
                                job_title="Senior Python Engineer",
                                mandatory_skills=["Python", "FastAPI", "AWS", "Docker"],
                                location=["Bangalore"],
                                number_of_positions=1,
                                monthly_budget="180000",
                                overall_experience="5 - 8 Years",
                                req_id="ITC-PY-8899",
                                confidence=1.0,
                            )
                        ],
                        overall_confidence=1.0,
                    )
            return RequirementParseResult(requirements=[], overall_confidence=0.0)

        with patch("main.parse_requirements_from_email", side_effect=mock_parse_reqs):
            # -------------------------------------------------------------
            # Message 1: Client sends initial requirement
            # Client -> Recruiter
            # -------------------------------------------------------------
            msg1 = {
                "id": "MSG-001-CLIENT-INITIAL",
                "internetMessageId": "<client-msg-001@itcinfotech.com>",
                "conversationId": conv_id,
                "receivedDateTime": "2026-10-07T10:00:00Z",
                "from": {"emailAddress": {"address": "client@itcinfotech.com", "name": "ITC Manager"}},
                "subject": "Requirement for Senior Python Engineer (Req: ITC-PY-8899)",
                "body": {
                    "contentType": "text",
                    "content": (
                        "Hi Team,\n\n"
                        "We have an immediate opening for Senior Python Engineer in Bangalore.\n"
                        "Client Req ID: ITC-PY-8899\n"
                        "Role: Senior Python Engineer\n"
                        "Skills: Python, FastAPI, AWS, Docker\n"
                        "Experience: 5 - 8 Years\n"
                        "Positions: 1\n"
                        "Budget: 180000 per month\n"
                        "Location: Bangalore\n\n"
                        "Please submit suitable candidates."
                    ),
                },
            }

            res1 = process_single_message(
                raw=msg1,
                token="dummy",
                mailbox="test@domain.com",
                settings=settings,
                allocator=allocator,
                store=store,
                skip_classifier=True,
            )

            assert res1 == 1, "Initial email should create 1 requirement row"

            # Verify DB has exactly 1 requirement
            conn_mf = sqlite3.connect(mf_db_path)
            rows1 = conn_mf.execute("SELECT job_id, client_jd_id, payload_json FROM metaforge_requirements").fetchall()
            assert len(rows1) == 1, f"Expected 1 record after Msg 1, found {len(rows1)}"
            initial_job_id = rows1[0][0]
            initial_payload = json.loads(rows1[0][2])
            assert initial_payload.get("job_title") == "Senior Python Engineer"
            assert int(initial_payload.get("number_of_positions")) == 1
            assert str(initial_payload.get("monthly_budget")) == "180000"
            conn_mf.close()

            # -------------------------------------------------------------
            # Message 2: Recruiter replies to Client (acknowledgment)
            # Client -> Recruiter
            # -------------------------------------------------------------
            msg2 = {
                "id": "MSG-002-RECRUITER-ACK",
                "internetMessageId": "<recruiter-reply-002@metaforgeit.com>",
                "inReplyTo": "<client-msg-001@itcinfotech.com>",
                "conversationId": conv_id,
                "receivedDateTime": "2026-10-07T10:15:00Z",
                "from": {"emailAddress": {"address": "rkarnam@metaforgeit.com", "name": "Recruiter Team"}},
                "subject": "RE: Requirement for Senior Python Engineer (Req: ITC-PY-8899)",
                "body": {
                    "contentType": "text",
                    "content": (
                        "Hi ITC Team,\n\n"
                        "Received the requirement ITC-PY-8899. Our technical recruitment team is actively sourcing profiles on priority.\n"
                        "We will share candidate profiles by EOD.\n\n"
                        "Best regards,\nRecruiter Team\n"
                    ),
                },
            }

            res2 = process_single_message(
                raw=msg2,
                token="dummy",
                mailbox="test@domain.com",
                settings=settings,
                allocator=allocator,
                store=store,
                skip_classifier=True,
            )

            assert res2 == 0, "Recruiter acknowledgment must create 0 new requirements"

            # Verify DB still has exactly 1 requirement, same job_id
            conn_mf = sqlite3.connect(mf_db_path)
            rows2 = conn_mf.execute("SELECT job_id, client_jd_id, payload_json FROM metaforge_requirements").fetchall()
            assert len(rows2) == 1, f"Expected 1 record after Msg 2, found {len(rows2)}"
            assert rows2[0][0] == initial_job_id, "Job ID must not change"
            conn_mf.close()

            # -------------------------------------------------------------
            # Message 3: Client replies with GENUINE requirement changes
            # Recruiter -> Client
            # -------------------------------------------------------------
            msg3 = {
                "id": "MSG-003-CLIENT-UPDATE",
                "internetMessageId": "<client-update-003@itcinfotech.com>",
                "inReplyTo": "<recruiter-reply-002@metaforgeit.com>",
                "conversationId": conv_id,
                "receivedDateTime": "2026-10-07T11:00:00Z",
                "from": {"emailAddress": {"address": "client@itcinfotech.com", "name": "ITC Manager"}},
                "subject": "RE: Requirement for Senior Python Engineer (Req: ITC-PY-8899)",
                "body": {
                    "contentType": "text",
                    "content": (
                        "Hi Team,\n\n"
                        "Please note revisions for Req: ITC-PY-8899:\n"
                        "Role: Senior Python Engineer\n"
                        "Skills: Python, FastAPI, AWS, Docker, Kafka\n"
                        "Positions: 2\n"
                        "Budget: 220000 per month\n"
                        "Location: Bangalore, Pune\n\n"
                        "Budget is increased to 220000 per month and open positions increased to 2. Please accelerate sourcing."
                    ),
                },
            }

            res3 = process_single_message(
                raw=msg3,
                token="dummy",
                mailbox="test@domain.com",
                settings=settings,
                allocator=allocator,
                store=store,
                skip_classifier=True,
            )

            assert res3 == 0, "Client update must update existing record and NOT create a new requirement"

            # Verify DB still has exactly 1 requirement, same job_id, but with UPDATED fields
            conn_mf = sqlite3.connect(mf_db_path)
            rows3 = conn_mf.execute("SELECT job_id, client_jd_id, payload_json, field_change_history FROM metaforge_requirements").fetchall()
            assert len(rows3) == 1, f"Expected 1 record after Msg 3, found {len(rows3)}"
            assert rows3[0][0] == initial_job_id, "Job ID must strictly be preserved"
            updated_payload = json.loads(rows3[0][2])
            assert int(updated_payload.get("number_of_positions")) == 2, f"Expected positions=2, got {updated_payload.get('number_of_positions')}"
            assert str(updated_payload.get("monthly_budget")) == "220000", f"Expected budget=220000, got {updated_payload.get('monthly_budget')}"
            
            # Verify field change history recorded the update
            history = json.loads(rows3[0][3] or "[]")
            assert len(history) > 0, "field_change_history must record genuine client changes"
            history_fields = [h["field"] for h in history]
            assert "number_of_positions" in history_fields or "monthly_budget" in history_fields
            conn_mf.close()

            # -------------------------------------------------------------
            # Message 4: Recruiter acknowledges the client update
            # Client -> Recruiter
            # -------------------------------------------------------------
            msg4 = {
                "id": "MSG-004-RECRUITER-UPDATE-ACK",
                "internetMessageId": "<recruiter-ack-004@metaforgeit.com>",
                "inReplyTo": "<client-update-003@itcinfotech.com>",
                "conversationId": conv_id,
                "receivedDateTime": "2026-10-07T11:15:00Z",
                "from": {"emailAddress": {"address": "rkarnam@metaforgeit.com", "name": "Recruiter Team"}},
                "subject": "RE: Requirement for Senior Python Engineer (Req: ITC-PY-8899)",
                "body": {
                    "contentType": "text",
                    "content": (
                        "Hi ITC Team,\n\n"
                        "Noted the updated budget of 220000 and 2 positions. Search criteria updated accordingly.\n"
                        "Profiles are being aligned.\n\n"
                        "Regards,\nRecruiter Team"
                    ),
                },
            }

            res4 = process_single_message(
                raw=msg4,
                token="dummy",
                mailbox="test@domain.com",
                settings=settings,
                allocator=allocator,
                store=store,
                skip_classifier=True,
            )

            assert res4 == 0, "Second recruiter acknowledgment must create 0 new requirements"

            # Final verification:
            conn_mf = sqlite3.connect(mf_db_path)
            rows_final = conn_mf.execute("SELECT job_id, client_jd_id, payload_json FROM metaforge_requirements").fetchall()
            assert len(rows_final) == 1, f"Expected exactly 1 record after full loop, found {len(rows_final)}"
            assert rows_final[0][0] == initial_job_id, "Requirement ID must remain identical across entire conversation loop"
            conn_mf.close()

            # Check duplicate decisions log
            conn_proc = sqlite3.connect(proc_db_path)
            dec_rows = conn_proc.execute("SELECT source_email_id, matched_requirement_id, deciding_rule, decision FROM duplicate_decisions").fetchall()
            assert len(dec_rows) >= 3, "All 3 reply messages should have duplicate decisions logged"
            conn_proc.close()

            print("\nALL REPLY LOOP ASSERTIONS PASSED:")
            print(f"Total messages processed: 4 (Client -> Recruiter -> Client -> Recruiter)")
            print(f"Unique requirements: 1")
            print(f"Database records: 1")
            print(f"Duplicate records created: 0")
            print(f"Preserved requirement ID: {initial_job_id}")
            print(f"Updated positions: {updated_payload.get('number_of_positions')}")
            print(f"Updated budget: {updated_payload.get('monthly_budget')}")

        store.close()


if __name__ == "__main__":
    test_reply_loop_deduplication_lifecycle()
