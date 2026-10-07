import sys
sys.path.insert(0, ".")
from collections import defaultdict
import re
from ui.db import _open_ro_connection, _format_internal_id, _clean_client_jd_id, _extract_real_client_jd_id, _parse_to_utc_dt, _merge_field_change_history, normalize_id
from requirement_identity import normalize_client_key, compute_requirement_identity
from metaforge_api import get_ist_req_date
import json

db_paths = ['data/metaforge_requirements.db', 'data/processed_messages.db']
tables_to_query = ["metaforge_requirements", "client_requirements", "pending_reviews", "requirement_memory"]
TABLE_PRIORITY = {
    "metaforge_requirements": 10,
    "client_requirements": 5,
    "pending_reviews": 3,
    "archived_backlog": 2,
    "requirement_memory": 1,
}

unique_records = {}
identity_to_key = {}
client_jd_to_key = {}
raw_id_to_key = {}

for db_path in db_paths:
    conn = _open_ro_connection(db_path)
    if not conn:
        continue
    for tbl in tables_to_query:
        try:
            rows = conn.execute(f"SELECT * FROM {tbl} ORDER BY created_at ASC").fetchall()
            tbl_prio = TABLE_PRIORITY.get(tbl, 1)
            for row in rows:
                try:
                    row_keys = row.keys()
                    payload = json.loads(row["payload_json"])
                    job_id_db = (
                        row["job_id"] if "job_id" in row_keys else
                        (row["client_jd_id"] if "client_jd_id" in row_keys else "")
                    )
                    job_id_raw = payload.get("job_id") or job_id_db or ""
                    fmt_id = _format_internal_id(job_id_raw)
                    created_at_db = row["created_at"] if "created_at" in row_keys else ""
                    updated_at_db = str(row["updated_at"] or "") if "updated_at" in row_keys else ""
                    
                    prov = payload.get("_provenance") if isinstance(payload.get("_provenance"), dict) else {}
                    fa_raw = (
                        payload.get("first_arrival_at") or
                        prov.get("received_date_time") or
                        prov.get("receivedDateTime") or
                        payload.get("receivedDateTime") or
                        payload.get("received_date_time") or
                        payload.get("email_received_iso") or
                        payload.get("received_at") or
                        created_at_db or
                        payload.get("demand_received_date") or ""
                    )
                    arr_iso = fa_raw
                    sort_ts = arr_iso or created_at_db or updated_at_db or ""
                    
                    client_jd = None
                    if "client_jd_id" in row_keys and row["client_jd_id"]:
                        client_jd = _clean_client_jd_id(row["client_jd_id"])
                    if not client_jd:
                        client_jd = _extract_real_client_jd_id(payload, job_id_raw)
                        
                    c_key = normalize_client_key(payload.get("requirement_from") or payload.get("client_key") or "")
                    ident = row["identity"] if ("identity" in row_keys and row["identity"]) else payload.get("identity")
                    if not ident:
                        ident = compute_requirement_identity(
                            client=payload.get("requirement_from") or payload.get("client_key"),
                            client_jd_id=client_jd,
                            job_title=payload.get("job_title"),
                            location=payload.get("location"),
                            experience=payload.get("overall_experience") or payload.get("experience_level"),
                            mandatory_skills=payload.get("mandatory_skills"),
                        )
                        
                    field_change_history = []
                    if "field_change_history" in row_keys and row["field_change_history"]:
                        try:
                            field_change_history = json.loads(row["field_change_history"]) or []
                        except:
                            pass
                            
                    record = {
                        "raw_req_id": job_id_raw,
                        "fmt_id": fmt_id,
                        "client_jd_id": client_jd,
                        "client_key": c_key,
                        "identity": ident,
                        "first_arrival_at": arr_iso,
                        "arr_iso": arr_iso,
                        "created_at": created_at_db,
                        "updated_at": updated_at_db,
                        "sort_ts": sort_ts,
                        "tbl_priority": tbl_prio,
                        "payload": payload,
                        "field_change_history": field_change_history,
                        "times_seen": 1,
                    }
                    
                    match_key = None
                    if ident and ident in identity_to_key:
                        match_key = identity_to_key[ident]
                    elif client_jd and (c_key, client_jd) in client_jd_to_key:
                        match_key = client_jd_to_key[(c_key, client_jd)]
                    elif fmt_id and fmt_id in raw_id_to_key:
                        match_key = raw_id_to_key[fmt_id]
                    elif job_id_raw and job_id_raw in raw_id_to_key:
                        match_key = raw_id_to_key[job_id_raw]
                        
                    if match_key is None:
                        assigned_key = ident or (f"{c_key}:{client_jd}" if client_jd else (fmt_id or job_id_raw))
                        unique_records[assigned_key] = record
                        if ident:
                            identity_to_key[ident] = assigned_key
                        if client_jd:
                            client_jd_to_key[(c_key, client_jd)] = assigned_key
                        if fmt_id:
                            raw_id_to_key[fmt_id] = assigned_key
                        if job_id_raw:
                            raw_id_to_key[job_id_raw] = assigned_key
                    else:
                        if ident:
                            identity_to_key[ident] = match_key
                        if client_jd:
                            client_jd_to_key[(c_key, client_jd)] = match_key
                        if fmt_id:
                            raw_id_to_key[fmt_id] = match_key
                        if job_id_raw:
                            raw_id_to_key[job_id_raw] = match_key
                            
                        existing = unique_records[match_key]
                        orig_fa = existing.get("first_arrival_at") or record.get("first_arrival_at")
                        merged_hist = _merge_field_change_history(existing["field_change_history"], field_change_history)
                        if tbl_prio > existing["tbl_priority"] or (tbl_prio == existing["tbl_priority"] and sort_ts > existing.get("sort_ts", "")):
                            record["field_change_history"] = merged_hist
                            record["times_seen"] = max(record.get("times_seen", 1), existing.get("times_seen", 1))
                            record["first_arrival_at"] = orig_fa
                            record["arr_iso"] = orig_fa
                            record["payload"]["first_arrival_at"] = orig_fa
                            if not record.get("client_jd_id") and existing.get("client_jd_id"):
                                record["client_jd_id"] = existing["client_jd_id"]
                            if not record.get("fmt_id") and existing.get("fmt_id"):
                                record["fmt_id"] = existing["fmt_id"]
                            unique_records[match_key] = record
                        else:
                            existing["field_change_history"] = merged_hist
                            existing["times_seen"] = max(record.get("times_seen", 1), existing.get("times_seen", 1))
                            existing["first_arrival_at"] = orig_fa
                            existing["arr_iso"] = orig_fa
                            existing["payload"]["first_arrival_at"] = orig_fa
                            if not existing.get("client_jd_id") and record.get("client_jd_id"):
                                existing["client_jd_id"] = record["client_jd_id"]
                except Exception:
                    pass
        except Exception:
            pass
    conn.close()

merged_records = list(unique_records.values())

# Sort chronologically by first_arrival_at ascending to assign stable internal IDs
merged_records.sort(
    key=lambda r: (
        _parse_to_utc_dt(r.get("first_arrival_at") or r.get("arr_iso") or r.get("created_at") or ""),
        str(r.get("fmt_id") or r.get("raw_req_id") or "")
    )
)

day_counters = {}
records = []

for r in merged_records:
    fa = r.get("first_arrival_at") or r.get("arr_iso") or r.get("created_at") or ""
    date_part = get_ist_req_date(fa)
    
    day_counters[date_part] = day_counters.get(date_part, 0) + 1
    seq_num = day_counters[date_part]
    internal_id = f"{date_part}-{seq_num:03d}"
    
    # Preserve former_job_id if internal_id changed
    if r.get("raw_req_id") and r.get("raw_req_id") != internal_id:
        r["former_job_id"] = r.get("raw_req_id")
        
    r["req_id"] = internal_id
    r["req_seq"] = seq_num
    records.append(r)

by_date = defaultdict(list)
for r in records:
    rid = r.get("req_id")
    m = re.match(r"^(\d{4}/\d{2}/\d{2})-(\d+)$", rid)
    if m:
        by_date[m.group(1)].append(int(m.group(2)))

print(f"{'Date':12} | {'Count':5} | {'Min':4} | {'Max':4} | {'Gaps'}")
print("-" * 50)
for d in sorted(by_date.keys()):
    seqs = sorted(by_date[d])
    expected = list(range(1, len(seqs) + 1))
    gaps = [x for x in range(min(seqs), max(seqs) + 1) if x not in seqs]
    is_exact = seqs == expected
    gap_str = "None (1..N exact)" if is_exact else f"Gaps: {gaps[:5]} (min={min(seqs)}, max={max(seqs)})"
    print(f"{d:12} | {len(seqs):5} | {min(seqs):4} | {max(seqs):4} | {gap_str}")
