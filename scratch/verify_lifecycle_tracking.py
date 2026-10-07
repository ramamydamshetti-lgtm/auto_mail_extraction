import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import json
import sqlite3
from config import Settings
from main import extract_and_map, process_single_message
from processed_store import ProcessedStore
from metaforge_api import IdAllocator

settings = Settings.from_env()
allocator = IdAllocator("data/metaforge_requirements.db")

# Clear test IDs from processed store if present
with ProcessedStore("data/processed_messages.db") as store:
    store._conn.execute("DELETE FROM processed WHERE graph_id LIKE 'MSG-TEST-%'")
    store._conn.execute("DELETE FROM pipeline_state WHERE graph_id LIKE 'MSG-TEST-%'")
    store._conn.execute("DELETE FROM client_requirements WHERE client_jd_id IN ('203483-1', 'REQ-998811')")
    store._conn.execute("DELETE FROM status_history WHERE requirement_id IN ('203483-1', 'REQ-998811')")
    store._conn.commit()

# Clear test IDs from metaforge_requirements.db
conn_mf = sqlite3.connect("data/metaforge_requirements.db")
conn_mf.execute("DELETE FROM metaforge_requirements WHERE payload_json LIKE '%203483-1%' OR payload_json LIKE '%REQ-998811%'")
conn_mf.commit()
conn_mf.close()

print("=== VERIFICATION SCRIPT FOR REQUIREMENT LIFECYCLE TRACKING ===")

# Test Email 1: Accenture email (reproduction case)
accenture_msg = {
    "id": "MSG-TEST-ACCENTURE-203483-1",
    "conversationId": "CONV-TEST-ACCENTURE-203483",
    "subject": "Don't work on below requirement",
    "from": {"emailAddress": {"address": "anusha.k@iexcel.co.in", "name": "Anusha K"}},
    "toRecipients": [{"emailAddress": {"address": "hiring@iexcel.co.in", "name": "Hiring"}}],
    "ccRecipients": [{"emailAddress": {"address": "rkarnam@metaforgeit.com", "name": "Raghu Karnam"}}],
    "receivedDateTime": "2026-09-30T10:00:00Z",
    "hasAttachments": False,
    "body": {
        "contentType": "html",
        "content": """<p>Hi Team,</p>
<p>Don't work on below requirement.</p>
<table>
<tr>
  <th>Req ID</th><th>Grade</th><th>Skill</th><th>Location</th><th>Work Mode</th><th>Budget</th><th>Exp</th><th>Education</th><th>Status</th>
</tr>
<tr>
  <td>203483-1</td><td>Grade 9</td><td>Salesforce Omnistudio Platform</td><td>Bangalore(BDC-7)</td><td>RTO</td><td>2.79 Lakhs</td><td>5 Yrs</td><td>Any Graduation</td><td>Hold</td>
</tr>
</table>"""
    }
}

# Test Email 2: KPMG email (Rule 4 - different client)
kpmg_msg = {
    "id": "MSG-TEST-KPMG-998811-1",
    "conversationId": "CONV-TEST-KPMG-998811",
    "subject": "Requirement Hold Notice - REQ-998811",
    "from": {"emailAddress": {"address": "hiring.manager@kpmg.com", "name": "KPMG Lead"}},
    "toRecipients": [{"emailAddress": {"address": "offshorejobs@metaforgeit.com", "name": "Offshore Jobs"}}],
    "ccRecipients": [],
    "receivedDateTime": "2026-09-30T10:30:00Z",
    "hasAttachments": False,
    "body": {
        "contentType": "html",
        "content": """<p>Dear Partner,</p>
<p>Please put requirement REQ-998811 on hold immediately. Stop profile submissions until further notice.</p>
<p>Role: Senior SAP S/4HANA Finance Lead<br>Req ID: REQ-998811<br>Location: Mumbai<br>Status: Hold</p>"""
    }
}

print("\n--- Running Test Email 1 (Accenture 203483-1) ---")
with ProcessedStore("data/processed_messages.db") as store:
    res1 = process_single_message(
        accenture_msg,
        token="MOCK_TOKEN",
        mailbox="recruitment.application@metaforgeit.com",
        settings=settings,
        store=store,
        allocator=allocator,
    )

print("\n--- Running Test Email 2 (KPMG REQ-998811) ---")
with ProcessedStore("data/processed_messages.db") as store:
    res2 = process_single_message(
        kpmg_msg,
        token="MOCK_TOKEN",
        mailbox="recruitment.application@metaforgeit.com",
        settings=settings,
        store=store,
        allocator=allocator,
    )

print("\n=== VERIFYING DATABASE & UI RECORDS ===")
with ProcessedStore("data/processed_messages.db") as store:
    rec1 = store.find_requirement_by_req_id("203483-1")
    rec2 = store.find_requirement_by_req_id("REQ-998811")
    
    print("\nAccenture 203483-1 stored record:")
    if rec1:
        print("  Req ID:", rec1[0])
        print("  Job Status:", rec1[1].get("job_status"))
        print("  Full Payload:", json.dumps(rec1[1], indent=2))
        print("  Status History:", store.get_status_history(rec1[0]))
    else:
        print("  NOT FOUND in processed_store client_requirements!")

    print("\nKPMG REQ-998811 stored record:")
    if rec2:
        print("  Req ID:", rec2[0])
        print("  Job Status:", rec2[1].get("job_status"))
        print("  Full Payload:", json.dumps(rec2[1], indent=2))
        print("  Status History:", store.get_status_history(rec2[0]))
    else:
        print("  NOT FOUND in processed_store client_requirements!")

# Now test Rule 3: Subsequent sighting (Reopen/Resume update for 203483-1)
print("\n--- Testing Rule 3: Subsequent sighting (Resume sourcing for 203483-1) ---")
accenture_msg_reopen = {
    "id": "MSG-TEST-ACCENTURE-203483-2",
    "conversationId": "CONV-TEST-ACCENTURE-203483",
    "subject": "Resume sourcing for requirement 203483-1",
    "from": {"emailAddress": {"address": "anusha.k@iexcel.co.in", "name": "Anusha K"}},
    "toRecipients": [{"emailAddress": {"address": "hiring@iexcel.co.in", "name": "Hiring"}}],
    "ccRecipients": [],
    "receivedDateTime": "2026-09-30T11:00:00Z",
    "hasAttachments": False,
    "body": {
        "contentType": "html",
        "content": "<p>Hi Team, Please resume sourcing profiles for 203483-1. Requirement is re-opened.</p>"
    }
}

with ProcessedStore("data/processed_messages.db") as store:
    res3 = process_single_message(
        accenture_msg_reopen,
        token="MOCK_TOKEN",
        mailbox="recruitment.application@metaforgeit.com",
        settings=settings,
        store=store,
        allocator=allocator,
    )
    rec1_updated = store.find_requirement_by_req_id("203483-1")
    print("\nUpdated Accenture 203483-1 status after reopen email:")
    if rec1_updated:
        print("  Job Status:", rec1_updated[1].get("job_status"))
        print("  Status History:", store.get_status_history(rec1_updated[0]))
