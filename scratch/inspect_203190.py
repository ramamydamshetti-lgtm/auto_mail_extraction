import sqlite3
import json
from pathlib import Path

DATA_DIR = Path("g:/Auto_email_extraction (3)-new/Auto_email_extraction/data")
mf_db = DATA_DIR / "metaforge_requirements.db"

conn_mf = sqlite3.connect(f"file:{mf_db}?mode=ro", uri=True)
row = conn_mf.execute("SELECT job_id, client_jd_id, created_at, updated_at, field_change_history, payload_json FROM metaforge_requirements WHERE client_jd_id = '203190-1'").fetchone()

print("job_id:", row[0])
print("client_jd_id:", row[1])
print("created_at:", row[2])
print("updated_at:", row[3])
print("field_change_history:", row[4])
p = json.loads(row[5])
print("Payload keys:", list(p.keys()))
for k in ["job_id", "client_jd_id", "demand_received_date", "email_received_iso", "created_at", "updated_at", "open_since", "first_arrival", "job_title", "location", "email_subject"]:
    print(f"  {k}: {p.get(k)}")

conn_mf.close()
