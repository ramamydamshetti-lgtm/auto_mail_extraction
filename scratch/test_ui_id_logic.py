import sqlite3, json, re, sys
sys.path.insert(0, '.')
from client_detector import detect_client

def _format_internal_id(val: str) -> str | None:
    if not val:
        return None
    val = str(val).strip()
    if val.startswith("REQ-"):
        val = val[4:]
    # Matches 2026-09-30-001 or 2026/09/30-001 or ACC-2026-09-29-001
    m = re.search(r"(\d{4})[\-\/](\d{2})[\-\/](\d{2})[\-\/]?(\d{3,})$", val)
    if m:
        return f"{m.group(1)}/{m.group(2)}/{m.group(3)}-{m.group(4)}"
    return None

def _extract_client_jd_id(p: dict) -> str | None:
    cjd = p.get("client_jd_id") or p.get("client_jd_id_override")
    if not cjd or str(cjd).lower() in ("none", "null", "not_found"):
        return None
    val = str(cjd).strip()
    if re.match(r"^(ACC|LTTS|REQ)\-\d{4}\-", val, re.IGNORECASE) or re.match(r"^(ACC|LTTS)\-\d{4}\-[A-Z]{3}\-", val, re.IGNORECASE):
        return None
    return val

db_paths = ["data/metaforge_requirements.db", "data/processed_messages.db"]
records = []

for db_path in db_paths:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    for tbl in ["metaforge_requirements", "pending_reviews", "client_requirements"]:
        try:
            rows = conn.execute(f"SELECT * FROM {tbl}").fetchall()
            for r in rows:
                p = json.loads(r["payload_json"])
                job_id_raw = p.get("job_id") or r.get("job_id") or r.get("client_jd_id") or ""
                fmt_id = _format_internal_id(job_id_raw)
                client_jd = _extract_client_jd_id(p)
                
                # Check arrival date
                prov = p.get("_provenance") if isinstance(p.get("_provenance"), dict) else {}
                arr_iso = prov.get("received_date_time") or p.get("email_received_iso") or p.get("receivedDateTime") or p.get("demand_received_date") or r.get("created_at") or ""
                
                # Fix idexcel client resolution if needed
                client_name = p.get("requirement_from", "")
                from_email = p.get("from") or p.get("client_poc") or ""
                if "idexcel" in client_name.lower() or "idexcel" in from_email.lower():
                    subj = p.get("subject", "")
                    body = p.get("bodyText") or p.get("body") or p.get("email_body") or ""
                    cm = detect_client(subj, body, from_email)
                    if cm:
                        client_name = cm.display_name
                    else:
                        client_name = "unresolved"
                
                records.append({
                    "raw_job_id": job_id_raw,
                    "fmt_id": fmt_id,
                    "client_jd_id": client_jd,
                    "arr_iso": arr_iso,
                    "client_name": client_name,
                    "job_title": p.get("job_title", "")
                })
        except Exception:
            pass
    conn.close()

# Sort records by arrival date ascending to assign internal IDs if fmt_id is missing
records.sort(key=lambda x: x["arr_iso"])

# Assign internal IDs for missing ones per day
day_counters = {}
for r in records:
    date_part = r["arr_iso"][:10].replace("-", "/") if len(r["arr_iso"]) >= 10 else "2026/09/30"
    if not r["fmt_id"]:
        day_counters[date_part] = day_counters.get(date_part, 0) + 1
        r["internal_id"] = f"{date_part}-{day_counters[date_part]:03d}"
    else:
        r["internal_id"] = r["fmt_id"]
        # Update counter if fmt_id ends in digits
        m = re.search(r"(\d{3,})$", r["fmt_id"])
        if m:
            num = int(m.group(1))
            day_counters[date_part] = max(day_counters.get(date_part, 0), num)

# Sort records reverse-chronologically for UI
records.sort(key=lambda x: x["arr_iso"], reverse=True)

print(f"Total processed records: {len(records)}")
for i, r in enumerate(records[:15]):
    cjd_str = f" ([{r['client_jd_id']}])" if r['client_jd_id'] and r['client_jd_id'] != r['internal_id'] else ""
    print(f"Row {i+1}: {r['internal_id']}{cjd_str} | Client: {r['client_name']} | Title: {r['job_title'][:30]}")
