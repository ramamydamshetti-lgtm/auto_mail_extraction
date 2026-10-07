"""
Verification Test Suite: Status Tracking across ALL 6 allowed domains using Part A Rule Engine & Part B AI.
Domains tested: ltts.com, itcinfotech.com, kpmg.com, iexcel.co.in, eximietas.com, idexcel.com (D-Client/P-Client).
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from client_detector import detect_client
from email_filter import is_sender_allowlisted
from processed_store import ProcessedStore
from prompt_supplement import get_prompt_supplement
from status_tracker import detect_status_keyword, evaluate_status_short_circuit, is_multi_requirement_digest


def run_tests():
    print("=" * 70)
    print("STARTING FULL 6-DOMAIN STATUS TRACKING VERIFICATION SUITE")
    print("=" * 70)

    # -------------------------------------------------------------------------
    # TEST 1: Domain Mapping & Ambiguous Body Marker Resolution (Zero Hardcoding)
    # -------------------------------------------------------------------------
    print("\n[TEST 1] Domain Mapping & Marker Resolution across 6 domains...")
    domain_tests = [
        ("rkarnam@ltts.com", "Requirement for Java Developer", "LTTS"),
        ("divya@itcinfotech.com", "ITC Requirement: SAP ABAP", "ITC Infotech"),
        ("hiring@kpmg.com", "KPMG Audit Lead Role", "KPMG"),
        ("anusha.k@iexcel.co.in", "Accenture Requirement Snapshot", "Accenture"),
        ("partner@eximietas.com", "PwC Requirement for Senior Manager", "PwC"),
        ("vendor@idexcel.com", "Role: Java Lead (d-client)", "Deloitte"),
        ("vendor@idexcel.com", "Role: React Developer (p-client)", "PwC"),
    ]

    for email, body, expected_client in domain_tests:
        match = detect_client(subject="Job Intake", body=body, from_email=email)
        assert match is not None, f"Failed to detect client for {email}"
        assert match.display_name == expected_client, (
            f"Expected {expected_client}, got {match.display_name} for {email}"
        )
        print(f"  [OK] {email} (body marker: '{body}') -> {match.display_name}")

    # -------------------------------------------------------------------------
    # TEST 2: Part A Keyword Detection (Generic Status Rules)
    # -------------------------------------------------------------------------
    print("\n[TEST 2] Part A Status Keyword Detection across 6 domains...")
    kw_tests = [
        ("RE: KPMG Requirement", "Please put this requirement on hold.", "hold"),
        ("RE: ITC Requirement", "Stop profile submissions for now.", "hold"),
        ("RE: PwC Requirement", "Reopen this requirement immediately.", "reopen"),
        ("RE: Deloitte Requirement", "Requirement active again, proceed with profiles.", "reopen"),
        ("New Requirement Deloitte", "We need 3 Senior Java Developers in Bangalore.", None),
    ]

    for subj, body, expected in kw_tests:
        res = detect_status_keyword(subj, body)
        assert res == expected, f"Expected keyword '{expected}', got '{res}' for subj='{subj}'"
        print(f"  [OK] Subj: '{subj}' -> Status keyword: {res}")

    # -------------------------------------------------------------------------
    # TEST 3: Generic Structural Digest Table Detection (KPMG, ITC, PwC, Deloitte, LTTS, Accenture)
    # -------------------------------------------------------------------------
    print("\n[TEST 3] Generic Structural Digest Table Detection Across Unseen Header Phrasings...")
    struct_digest_tests = [
        ("KPMG Client Update", "| Sr No | Role | Skill | Location | Status |\n| 1 | Tax Lead | Audit | Mumbai | Hold |"),
        ("ITC Infotech Open Positions", "<table border='1'><tr><th>Job ID</th><th>Role</th><th>Status</th></tr><tr><td>ITC-99</td><td>SAP ABAP</td><td>Active</td></tr></table>"),
        ("PwC Weekly Pipeline", "Req ID: PWC-101 (Role: Audit Manager, Status: Hold)\nReq ID: PWC-102 (Role: Tax Associate, Status: Active)"),
        ("Deloitte Demands", "| SO # | Designation | Status |\n| 88201 | Java Architect | Active |\n| 88202 | React Lead | Hold |"),
    ]

    for subj, body in struct_digest_tests:
        is_digest = is_multi_requirement_digest(subj, body)
        assert is_digest is True, f"Failed structural digest detection for subj='{subj}'"
        print(f"  [OK] Structural Digest Detected for '{subj}' (Bypasses email-level short-circuit)")

    # -------------------------------------------------------------------------
    # TEST 4: Full 6-Scenario Thread Matching & Lifecycle Execution
    # -------------------------------------------------------------------------
    print("\n[TEST 4] Running 6-Scenario Lifecycle Execution Tests...")
    temp_dir = tempfile.mkdtemp()
    db_path = Path(temp_dir) / "test_store.db"

    with ProcessedStore(db_path) as store:
        # Scenario 1: Initial creation of requirement (Default status "open")
        conv_id = "THREAD-KPMG-1001"
        graph_id = "GRAPH-MSG-001"
        req_id = "KPMG-REQ-8820"
        init_payload = {
            "job_id": req_id,
            "client_jd_id": req_id,
            "requirement_from": "KPMG",
            "job_title": "Senior Tax Consultant",
            "job_status": "open",
            "graphMessageId": graph_id,
            "_provenance": {"conversation_id": conv_id, "graph_message_id": graph_id},
        }
        store.evaluate_client_requirement_action(
            client_jd_id=req_id,
            requirement_from="KPMG",
            payload=init_payload,
        )
        store.add_requirement_memory(
            requirement_from="KPMG",
            job_title="Senior Tax Consultant",
            payload_json=json.dumps(init_payload),
            source_graph_id=graph_id,
        )
        print(f"  [OK] Scenario 1: Created initial requirement {req_id} with default status 'open'")

        # Scenario 2: Threaded Hold Request (Part A Short-circuit)
        hold_subj = "RE: KPMG Senior Tax Consultant requirement"
        hold_body = "Hi team, please put this requirement on hold until further notice. Stop sharing profiles."
        status_act, target_id = evaluate_status_short_circuit(
            subject=hold_subj,
            body=hold_body,
            conversation_id=conv_id,
            graph_id="GRAPH-MSG-002",
            store=store,
            from_email="hiring@kpmg.com",
        )
        assert status_act == "STATUS_UPDATED", f"Expected STATUS_UPDATED, got {status_act}"
        assert target_id == req_id, f"Expected {req_id}, got {target_id}"

        req_info = store.find_requirement_by_req_id(req_id)
        assert req_info[1]["job_status"] == "hold", "Database status not updated to 'hold'"
        hist = store.get_status_history(req_id)
        assert len(hist) == 1, "Status history missing entry"
        assert hist[0]["from_status"] == "open" and hist[0]["to_status"] == "hold"
        print(f"  [OK] Scenario 2: Threaded hold request short-circuited & updated status to 'hold'")

        # Scenario 3: Threaded Reopen Request (Part A Short-circuit)
        reopen_subj = "RE: KPMG Senior Tax Consultant requirement"
        reopen_body = "Hi team, we are reopening this requirement. Active again, please proceed."
        status_act2, target_id2 = evaluate_status_short_circuit(
            subject=reopen_subj,
            body=reopen_body,
            conversation_id=conv_id,
            graph_id="GRAPH-MSG-003",
            store=store,
            from_email="hiring@kpmg.com",
        )
        assert status_act2 == "STATUS_UPDATED", f"Expected STATUS_UPDATED, got {status_act2}"

        req_info2 = store.find_requirement_by_req_id(req_id)
        assert req_info2[1]["job_status"] == "reopen", "Database status not updated to 'reopen'"
        hist2 = store.get_status_history(req_id)
        assert len(hist2) == 2, "Status history missing second entry"
        print(f"  [OK] Scenario 3: Threaded reopen request short-circuited & updated status to 'reopen'")

        # Scenario 4: Unmatched Thread Hold Request -> Pending Review
        unmatched_subj = "RE: ITC Infotech Requirement"
        unmatched_body = "Kindly hold profile submissions for this role."
        status_act3, _ = evaluate_status_short_circuit(
            subject=unmatched_subj,
            body=unmatched_body,
            conversation_id="UNKNOWN-THREAD-9999",
            graph_id="GRAPH-MSG-004",
            store=store,
            from_email="divya@itcinfotech.com",
        )
        assert status_act3 == "PENDING_REVIEW_NO_THREAD", f"Expected PENDING_REVIEW_NO_THREAD, got {status_act3}"
        print("  [OK] Scenario 4: Unmatched status email correctly routed to pending_reviews")

        # Scenario 5: Absence of Status Keywords
        normal_subj = "New Deloitte Opening: React Developer"
        normal_body = "We need 2 Senior React Developers in Pune. Bill rate: $60/hr."
        status_act4, _ = evaluate_status_short_circuit(
            subject=normal_subj,
            body=normal_body,
            conversation_id="NEW-THREAD-5555",
            graph_id="GRAPH-MSG-005",
            store=store,
            from_email="vendor@idexcel.com",
        )
        assert status_act4 == "CONTINUE_PIPELINE", f"Expected CONTINUE_PIPELINE, got {status_act4}"
        print("  [OK] Scenario 5: Absence of status keywords allows normal pipeline execution")

        # Scenario 6: Multi-Day Gap Reappearance (Accenture Snapshot Pattern)
        acc_req_id = "ACC-99100"
        acc_payload1 = {
            "job_id": acc_req_id,
            "client_jd_id": acc_req_id,
            "requirement_from": "Accenture",
            "job_title": "Java Microservices Lead",
            "job_status": "hold",
        }
        store.evaluate_client_requirement_action(
            client_jd_id=acc_req_id,
            requirement_from="Accenture",
            payload=acc_payload1,
        )

        acc_payload2 = {
            "job_id": acc_req_id,
            "client_jd_id": acc_req_id,
            "requirement_from": "Accenture",
            "job_title": "Java Microservices Lead",
            "job_status": "open",
        }
        action, updated_payload = store.evaluate_client_requirement_action(
            client_jd_id=acc_req_id,
            requirement_from="Accenture",
            payload=acc_payload2,
        )
        assert action == "UPDATE", f"Expected UPDATE for multi-day gap status change, got {action}"
        assert updated_payload["job_status"] == "open"
        print("  [OK] Scenario 6: Multi-day gap reappearance updated existing Req ID from hold to open")

    # -------------------------------------------------------------------------
    # TEST 5: Unauthorized Sender Gate Verification (Domain not in allowed_domains)
    # -------------------------------------------------------------------------
    print("\n[TEST 5] Unauthorized Sender Gate Verification...")
    unauth_email = "spammer@randomdomain.com"
    unauth_subj = "RE: Urgent requirement on hold"
    unauth_body = "Please put this requirement on hold immediately."

    assert is_sender_allowlisted(unauth_email) is False, "Unauthorized domain was not blocked by allowlist"

    with ProcessedStore(db_path) as store:
        status_act5, _ = evaluate_status_short_circuit(
            subject=unauth_subj,
            body=unauth_body,
            conversation_id="UNAUTH-THREAD-123",
            graph_id="GRAPH-MSG-UNAUTH",
            store=store,
            from_email=unauth_email,
        )
        assert status_act5 == "SENDER_BLOCKED", f"Expected SENDER_BLOCKED, got {status_act5}"
    print(f"  [OK] Unauthorized sender '{unauth_email}' with hold language BLOCKED at sender gate")

    # -------------------------------------------------------------------------
    # TEST 6: Part B3 AI Prompt Supplement Verification
    # -------------------------------------------------------------------------
    print("\n[TEST 6] AI Prompt Supplement (Part B3) Few-shot Coverage Check...")
    ltts_supp = get_prompt_supplement("LTTS")
    assert "LTTS" in ltts_supp and "REQ-10293" in ltts_supp
    print("  [OK] LTTS has explicit AI few-shot prompt supplement")

    acc_supp = get_prompt_supplement("Accenture")
    assert "ACCENTURE" in acc_supp and "ACC-88391" in acc_supp
    print("  [OK] Accenture has explicit AI few-shot prompt supplement")

    kpmg_supp = get_prompt_supplement("KPMG")
    assert "General AI rules apply for KPMG" in kpmg_supp
    print("  [OK] KPMG falls back cleanly to general AI rules + Part A rule engine")

    print("\n" + "=" * 70)
    print("ALL VERIFICATION TESTS (INCLUDING UNAUTHORIZED SENDER & STRUCTURAL DIGESTS) PASSED!")
    print("=" * 70)


if __name__ == "__main__":
    run_tests()
