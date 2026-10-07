import sys
sys.path.insert(0, '.')
from datetime import date
from requirement_parser import extract_client_jd_id_from_text
from metaforge_api import IdAllocator
from processed_store import ProcessedStore
import sqlite3, json, tempfile, os

test_client_ids = ["200961-1", "203501-1", "203489-1", "203495-1"]

print("=== 1. VERIFYING CLIENT JD ID EXTRACTION ===")
for cid in test_client_ids:
    sample_text = f"Accenture Open Demand Details:\nRequest-ID : {cid}\nRole : Senior SAP Consultant\nLocation : Bangalore"
    extracted = extract_client_jd_id_from_text("New Requirement", sample_text)
    print(f"Source ID: {cid} -> Extracted: {extracted} {'[PASS]' if extracted == cid else '[FAIL]'}")
    assert extracted == cid

print("\n=== 2. VERIFYING INTERNAL ID ASSIGNMENT & DEDUPLICATION ===")
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
    db_path = os.path.join(tmp_dir, "processed_messages.db")
    mf_path = os.path.join(tmp_dir, "metaforge_requirements.db")
    
    allocator = IdAllocator(mf_path)
    store = ProcessedStore(db_path)
    
    today = date(2026, 9, 30)
    ingested_records = []
    
    for cid in test_client_ids:
        internal_id = allocator.next_job_id(today)
        payload = {
            "job_id": internal_id,
            "client_jd_id": cid,
            "requirement_from": "Accenture",
            "job_title": f"Accenture Role for {cid}",
            "job_status": "open"
        }
        
        action, res = store.evaluate_client_requirement_action(
            client_jd_id=cid,
            requirement_from="Accenture",
            payload=payload
        )
        
        print(f"Client ID: {cid} -> Action: {action} | Assigned Internal ID: {internal_id}")
        assert action == "CREATE"
        ingested_records.append((internal_id, cid))
    
    allocator.close()
    store.close()
    
    print("\n=== 3. VERIFYING REPEAT EMAIL DEDUPLICATION ===")
    store2 = ProcessedStore(db_path)
    for cid in test_client_ids:
        duplicate_payload = {
            "job_id": "2026/09/30-999",
            "client_jd_id": cid,
            "requirement_from": "Accenture",
            "job_title": f"Accenture Role for {cid}",
            "job_status": "open"
        }
        action, res = store2.evaluate_client_requirement_action(
            client_jd_id=cid,
            requirement_from="Accenture",
            payload=duplicate_payload
        )
        print(f"Repeat Client ID: {cid} -> Action: {action} {'[PASS - DUPLICATE SKIPPED]' if action == 'SKIP' else '[FAIL]'}")
        assert action == "SKIP"
    store2.close()

print("\nALL VERIFICATIONS PASSED CLEANLY FOR TODAY'S NEW ACCENTURE REQUIREMENT IDs!")
