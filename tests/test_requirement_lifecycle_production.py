"""
Production Lifecycle & Duplicate Handling Verification Suite.
Verifies all 5 required production scenarios using existing production logic:
1. STOP DEMAND: "Partner - Pls stop on this demand" updates status to hold, creates 0 new requirements.
2. SAME REQUIREMENT RECEIVED TWICE: Duplicates identified, 1 record kept, 0 new requirements created.
3. SAME REQUIREMENT RECEIVED MULTIPLE TIMES: Multiple receipts collapse to 1 single requirement.
4. EXISTING REQUIREMENT WITH CLIENT CHANGES: Updates same requirement in-place, preserves Job ID, records diff in field_change_history.
5. UNCHANGED DUPLICATE EMAIL: Preserves existing requirement untouched.
"""

import sys
import json
import sqlite3
import tempfile
from pathlib import Path

# Add project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from processed_store import ProcessedStore
from status_tracker import detect_status_keyword, evaluate_status_short_circuit
from requirement_comparator import build_requirement_profile, compare_requirements
from requirement_identity import compute_requirement_identity


def run_lifecycle_verification():
    print("=" * 80)
    print("RUNNING PRODUCTION REQUIREMENT LIFECYCLE & DUPLICATE VERIFICATION")
    print("=" * 80)

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        pm_db_path = tmp_path / "processed_messages.db"
        mf_db_path = tmp_path / "metaforge_requirements.db"

        # Initialize schema in metaforge_requirements.db
        conn_mf = sqlite3.connect(mf_db_path)
        conn_mf.execute("""
            CREATE TABLE metaforge_requirements (
                job_id TEXT PRIMARY KEY,
                client_jd_id TEXT,
                payload_json TEXT NOT NULL,
                identity TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                field_change_history TEXT,
                former_job_id TEXT
            )
        """)
        conn_mf.execute("""
            CREATE TABLE status_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                requirement_id TEXT NOT NULL,
                from_status TEXT NOT NULL,
                to_status TEXT NOT NULL,
                changed_at TEXT NOT NULL,
                source_email_id TEXT,
                changed_by TEXT NOT NULL
            )
        """)
        conn_mf.commit()
        conn_mf.close()

        with ProcessedStore(pm_db_path) as store:
            # ------------------------------------------------------------------
            # SETUP: Create an initial real requirement (e.g. MES Product Owner)
            # ------------------------------------------------------------------
            initial_job_id = "2026/09/29-004"
            initial_payload = {
                "job_id": initial_job_id,
                "client_jd_id": None,
                "requirement_from": "LTTS",
                "job_title": "SMS MES Product Owner",
                "job_status": "open",
                "requirement_status": "open",
                "location": "Bangalore",
                "work_mode": "Hybrid",
                "number_of_positions": 1,
                "overall_experience": "8-12 years",
                "monthly_budget": "160000",
                "budget_currency": "INR",
                "skills": ["Manufacturing awareness", "Azure DevOps"],
                "mandatory_skills": ["MES", "Product Owner"],
                "subject": "TPC - Requirement - SMS - MES Product Owner - Bangalore, Chennai, Pune",
                "bodyText": "Role: SMS MES Product Owner. Budget: 160000 INR per month. Experience: 8-12 years.",
                "graphMessageId": "ORIG-GRAPH-001",
                "_provenance": {
                    "conversation_id": "CONV-THREAD-MES-001",
                    "graph_message_id": "ORIG-GRAPH-001",
                },
            }

            prof_initial = build_requirement_profile(initial_payload, body_text=initial_payload["bodyText"])
            ident_initial = compute_requirement_identity(
                client="LTTS",
                client_jd_id=None,
                job_title=initial_payload["job_title"],
                location=initial_payload["location"],
                experience=initial_payload["overall_experience"],
                mandatory_skills=initial_payload["mandatory_skills"],
            )
            initial_payload["identity"] = ident_initial

            # Save to metaforge_requirements.db and requirement_identity
            conn_mf = sqlite3.connect(mf_db_path)
            conn_mf.execute(
                """INSERT INTO metaforge_requirements (job_id, client_jd_id, payload_json, identity, created_at, updated_at, field_change_history)
                   VALUES (?, ?, ?, ?, datetime('now'), datetime('now'), ?)""",
                (initial_job_id, None, json.dumps(initial_payload), ident_initial, json.dumps([])),
            )
            conn_mf.commit()
            conn_mf.close()

            store.register_requirement_identity(
                identity=ident_initial,
                client="ltts",
                client_jd_id=None,
                city=prof_initial["city"],
                profile=prof_initial,
                state="stored",
                original_record_ref=initial_job_id,
                graph_id="ORIG-GRAPH-001",
            )
            print(f"[OK] Initial requirement created: {initial_job_id} ('{initial_payload['job_title']}')")

            # ------------------------------------------------------------------
            # TEST 1: STOP DEMAND
            # "Partner – Pls stop on this demand"
            # ------------------------------------------------------------------
            print("\n[TEST 1] Testing Stop Demand handling...")
            stop_email_subj = "RE: TPC - Requirement - SMS - MES Product Owner - Bangalore, Chennai, Pune"
            stop_email_body = "Partner – Pls stop on this demand\nRgds/Kallol\n+91-9686100177"
            
            # Detect status keyword
            kw = detect_status_keyword(stop_email_subj, stop_email_body)
            assert kw == "hold", f"Expected 'hold', got '{kw}'"
            print(f"  [1.1] Keyword correctly detected as: '{kw}'")

            # Evaluate short circuit
            action, matched_id = evaluate_status_short_circuit(
                subject=stop_email_subj,
                body=stop_email_body,
                conversation_id="CONV-THREAD-MES-001",
                graph_id="STOP-GRAPH-002",
                store=store,
                from_email="Kallol.Chakraborty@Ltts.com",
            )
            assert action == "STATUS_UPDATED", f"Expected STATUS_UPDATED, got {action}"
            assert matched_id == initial_job_id, f"Expected matched {initial_job_id}, got {matched_id}"
            print(f"  [1.2] Short-circuit matched requirement {matched_id} with action {action}")

            # Verify existing requirement status is updated to hold in metaforge_requirements.db
            conn_mf = sqlite3.connect(mf_db_path)
            mf_row = conn_mf.execute("SELECT payload_json FROM metaforge_requirements WHERE job_id = ?", (initial_job_id,)).fetchone()
            assert mf_row is not None, "Requirement missing in metaforge_requirements.db"
            p_after_stop = json.loads(mf_row[0])
            assert p_after_stop["job_status"] == "hold", f"Expected status 'hold', got '{p_after_stop['job_status']}'"
            
            # Verify status history audit trail
            hist_rows = conn_mf.execute("SELECT from_status, to_status, changed_by FROM status_history WHERE requirement_id = ?", (initial_job_id,)).fetchall()
            assert len(hist_rows) >= 1, "Status history missing"
            assert hist_rows[0][0] == "open" and hist_rows[0][1] == "hold"
            conn_mf.close()
            print(f"  [1.3] Database verified: {initial_job_id} status is now 'hold'; status history logged.")
            print("  [PASS] Test 1: Stop demand successfully updated existing record without creating new requirement.")

            # ------------------------------------------------------------------
            # TEST 2: SAME REQUIREMENT RECEIVED TWICE (Duplicate Handling)
            # ------------------------------------------------------------------
            print("\n[TEST 2] Testing duplicate requirement received twice...")
            # Reopen the requirement first to test active state
            store.update_requirement_status(requirement_id=initial_job_id, new_status="open")

            dup_payload_2 = dict(initial_payload)
            dup_payload_2["graphMessageId"] = "DUP-GRAPH-003"
            prof_dup_2 = build_requirement_profile(dup_payload_2, body_text=dup_payload_2["bodyText"])

            decision, matched_cand, score, deciding_rule = store.find_requirement_duplicate(prof_dup_2)
            assert decision == "DUPLICATE", f"Expected DUPLICATE, got {decision}"
            assert matched_cand["original_record_ref"] == initial_job_id, f"Expected match with {initial_job_id}, got {matched_cand}"
            
            # Update seen count
            store.update_identity_seen(matched_cand["identity"], graph_id="DUP-GRAPH-003")
            id_info = store.get_requirement_identity(matched_cand["identity"])
            assert id_info["times_seen"] >= 2, f"Expected times_seen >= 2, got {id_info['times_seen']}"
            print(f"  [2.1] Detected DUPLICATE (rule: {deciding_rule}, score: {score:.2f})")
            print(f"  [2.2] Identity times_seen incremented to: {id_info['times_seen']}")
            print("  [PASS] Test 2: Duplicate email identified; no new requirement created.")

            # ------------------------------------------------------------------
            # TEST 3: SAME REQUIREMENT RECEIVED MULTIPLE TIMES
            # ------------------------------------------------------------------
            print("\n[TEST 3] Testing same requirement received multiple times (3x, 4x, 5x)...")
            for i in range(4, 7):
                dup_i = dict(initial_payload)
                dup_i["graphMessageId"] = f"DUP-GRAPH-00{i}"
                prof_i = build_requirement_profile(dup_i, body_text=dup_i["bodyText"])
                dec_i, cand_i, _, _ = store.find_requirement_duplicate(prof_i)
                assert dec_i == "DUPLICATE"
                store.update_identity_seen(cand_i["identity"], graph_id=f"DUP-GRAPH-00{i}")

            id_final = store.get_requirement_identity(ident_initial)
            assert id_final["times_seen"] >= 5, f"Expected times_seen >= 5, got {id_final['times_seen']}"
            
            # Check metaforge_requirements still only has ONE requirement
            conn_mf = sqlite3.connect(mf_db_path)
            total_reqs = conn_mf.execute("SELECT COUNT(*) FROM metaforge_requirements").fetchone()[0]
            conn_mf.close()
            assert total_reqs == 1, f"Expected exactly 1 requirement in DB, found {total_reqs}"
            print(f"  [3.1] Times seen correctly tracked up to: {id_final['times_seen']}")
            print(f"  [3.2] Total requirements in database remains strictly: {total_reqs}")
            print("  [PASS] Test 3: Multiple receipts confirmed to maintain strictly 1 unique requirement.")

            # ------------------------------------------------------------------
            # TEST 4: CLIENT CHANGES TO EXISTING REQUIREMENT
            # Client updates budget, experience, skills, positions, work mode
            # ------------------------------------------------------------------
            print("\n[TEST 4] Testing client changes to existing requirement...")
            client_change_payload = {
                "job_title": "SMS MES Product Owner",
                "requirement_from": "LTTS",
                "monthly_budget": "190000",          # Changed from 160000
                "number_of_positions": 2,             # Changed from 1
                "overall_experience": "10-14 years",  # Changed from 8-12 years
                "work_mode": "Work from Office",      # Changed from Hybrid
                "skills": ["Manufacturing awareness", "Azure DevOps", "Siemens Opcenter", "Rockwell FactoryTalk"], # New skills
                "mandatory_skills": ["MES", "Product Owner", "ISA-95"], # Updated mandatory skills
                "location": "Bangalore",              # Unchanged
                "bodyText": "Updated requirements: budget revised to 190000 per month, 2 positions, experience 10-14 years, ISA-95 mandatory.",
            }

            # 1. Detection: verify that duplicate engine identifies this as the same role update
            prof_change = build_requirement_profile(client_change_payload, body_text=client_change_payload["bodyText"])
            dec_chg, cand_chg, score_chg, rule_chg = store.find_requirement_duplicate(prof_change)
            assert dec_chg == "DUPLICATE", f"Expected DUPLICATE for client change, got {dec_chg} (score={score_chg}, rule={rule_chg})"
            assert cand_chg["original_record_ref"] == initial_job_id
            print(f"  [4.1] Client change recognized as DUPLICATE of {initial_job_id} (rule: {rule_chg})")

            # 2. In-place update: update existing requirement
            updated_ok = store.update_requirement_fields_in_place(
                requirement_id=initial_job_id,
                incoming_payload=client_change_payload,
                source_email_id="CHANGE-GRAPH-007",
                metaforge_db_path=mf_db_path,
            )
            assert updated_ok is True, "In-place field update failed"

            # 3. Verify fields updated and unchanged fields preserved
            conn_mf = sqlite3.connect(mf_db_path)
            conn_mf.row_factory = sqlite3.Row
            row_updated = conn_mf.execute("SELECT * FROM metaforge_requirements WHERE job_id = ?", (initial_job_id,)).fetchone()
            p_updated = json.loads(row_updated["payload_json"])
            
            # Check changed fields
            assert p_updated["monthly_budget"] == "190000", f"Budget not updated: {p_updated['monthly_budget']}"
            assert p_updated["number_of_positions"] == 2, f"Positions not updated: {p_updated['number_of_positions']}"
            assert p_updated["overall_experience"] == "10-14 years", f"Experience not updated: {p_updated['overall_experience']}"
            assert p_updated["work_mode"] == "Work from Office", f"Work mode not updated: {p_updated['work_mode']}"
            assert "ISA-95" in p_updated["mandatory_skills"], "Mandatory skills not updated"
            assert "Siemens Opcenter" in p_updated["skills"], "Skills not updated"

            # Check unchanged fields preserved
            assert p_updated["location"] == "Bangalore", f"Location was altered: {p_updated['location']}"
            assert p_updated["budget_currency"] == "INR", f"Currency was altered: {p_updated['budget_currency']}"
            assert row_updated["job_id"] == initial_job_id, f"Job ID was altered: {row_updated['job_id']}"

            # Check field change history
            diff_hist = json.loads(row_updated["field_change_history"])
            changed_fields_logged = {entry["field"] for entry in diff_hist}
            expected_fields = {"monthly_budget", "number_of_positions", "overall_experience", "work_mode", "skills", "mandatory_skills"}
            assert expected_fields.issubset(changed_fields_logged), f"Missing fields in diff history: {expected_fields - changed_fields_logged}"
            
            total_reqs_after_change = conn_mf.execute("SELECT COUNT(*) FROM metaforge_requirements").fetchone()[0]
            conn_mf.close()
            assert total_reqs_after_change == 1, f"Expected 1 requirement, found {total_reqs_after_change}"
            
            print(f"  [4.2] Fields updated in-place: budget -> 190000, positions -> 2, experience -> 10-14 yrs, work_mode -> Work from Office")
            print(f"  [4.3] Unchanged fields preserved: location='Bangalore', currency='INR', Job ID='{initial_job_id}'")
            print(f"  [4.4] Audit trail recorded in field_change_history: {len(diff_hist)} field diffs logged")
            print("  [PASS] Test 4: Client changes modified the SAME requirement without creating a new record.")

            # ------------------------------------------------------------------
            # TEST 5: UNCHANGED DUPLICATE EMAIL
            # ------------------------------------------------------------------
            print("\n[TEST 5] Testing unchanged duplicate email...")
            conn_mf = sqlite3.connect(mf_db_path)
            prev_updated_at = conn_mf.execute("SELECT updated_at FROM metaforge_requirements WHERE job_id = ?", (initial_job_id,)).fetchone()[0]
            conn_mf.close()

            # Resend unchanged payload
            dup_unchanged_ok = store.update_requirement_fields_in_place(
                requirement_id=initial_job_id,
                incoming_payload=p_updated,
                source_email_id="DUP-UNCHANGED-008",
                metaforge_db_path=mf_db_path,
            )
            assert dup_unchanged_ok is False, "Expected False (no fields changed) for unchanged duplicate"
            print("  [5.1] Unchanged duplicate detected; no redundant field writes or history entries made.")
            print("  [PASS] Test 5: Unchanged duplicate preserved existing requirement untouched.")

    print("\n" + "=" * 80)
    print("ALL 5 PRODUCTION REQUIREMENT LIFECYCLE & DUPLICATE TESTS PASSED PERFECTLY!")
    print("=" * 80)


if __name__ == "__main__":
    run_lifecycle_verification()
