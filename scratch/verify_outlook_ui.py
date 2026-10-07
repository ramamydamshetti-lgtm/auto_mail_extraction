import json
from ui.app import app, UI_CONFIG
from ui.db import fetch_all_records, get_requirement

records = fetch_all_records(UI_CONFIG)
print(f"Total Requirements ready in UI: {len(records)}")

if records:
    sample_id = records[0]["req_id"]
    print(f"\nTesting Autofill API for sample Req ID '{sample_id}'...")
    with app.test_client() as client:
        res = client.get(f"/api/requirement/{sample_id}")
        print(f"HTTP Status: {res.status_code}")
        print("Autofill Payload Output:")
        print(json.dumps(res.get_json(), indent=2))
