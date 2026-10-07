import sys
import os
import json
import sqlite3
sys.path.insert(0, os.path.abspath("."))
from scratch.simulate_accenture_req_id_lifecycle import status_history, req_store

print("=== REQUIREMENTS WITH STATUS CHANGES ===")
for rid, history in status_history.items():
    update_events = [h for h in history if h["action"] == "UPDATE_STATUS"]
    if update_events:
        print(f"\nReq ID: {rid}")
        print(f"  Times Seen: {req_store[rid]['times_seen']}")
        print(f"  First Seen: {req_store[rid]['first_seen_at']} | Last Seen: {req_store[rid]['last_seen_at']}")
        print(f"  Current Status: {req_store[rid]['last_status']}")
        print("  Full Timeline:")
        for ev in history:
            if ev["action"] == "CREATED":
                print(f"    - [{ev['changed_at']}] CREATED with initial status '{ev['to_status']}'")
            else:
                print(f"    - [{ev['changed_at']}] UPDATE_STATUS: '{ev['from_status']}' --> '{ev['to_status']}'")
