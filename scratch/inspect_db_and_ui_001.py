import sqlite3
import json

db_path = "data/metaforge_requirements.db"
conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("SELECT rowid, job_id, client_jd_id, payload_json FROM metaforge_requirements WHERE job_id = '2026/09/01-001'")
row = cur.fetchone()

print("--- DB ROW ---")
print("rowid:", row["rowid"])
print("job_id:", row["job_id"])
print("client_jd_id:", row["client_jd_id"])

payload = json.loads(row["payload_json"])
print("\n--- STORED PAYLOAD IN DB ---")
for k, v in payload.items():
    if k not in ("bodyText", "bodyHtml"):
        print(f"  {k}: {v}")

from ui.app import UI_CONFIG
from ui.db import get_requirement

ui_rec = get_requirement(UI_CONFIG, "2026/09/01-001")
print("\n--- UI get_requirement RESULT ---")
for k, v in ui_rec.items():
    if k not in ("payload", "raw_payload"):
        print(f"  top-level {k}: {v}")

print("\n--- UI payload DICT ---")
for k, v in ui_rec.get("payload", {}).items():
    if k not in ("bodyText", "bodyHtml"):
        print(f"  payload.{k}: {v}")
