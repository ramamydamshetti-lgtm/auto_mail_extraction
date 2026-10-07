import sqlite3
import json
import os
from pathlib import Path

# Add project root to sys.path
import sys
sys.path.insert(0, "g:/Auto_email_extraction (3)-new/Auto_email_extraction")

from requirement_identity import clean_client_jd_id, compute_requirement_identity, normalize_client_key
from requirement_comparator import build_requirement_profile, compare_requirements
from config import Settings

DATA_DIR = Path("g:/Auto_email_extraction (3)-new/Auto_email_extraction/data")
mf_db = DATA_DIR / "metaforge_requirements.db"

conn_mf = sqlite3.connect(f"file:{mf_db}?mode=ro", uri=True)

# Fetch all 237 rows ordered by created_at ASC
rows = conn_mf.execute(
    "SELECT job_id, client_jd_id, created_at, updated_at, payload_json FROM metaforge_requirements ORDER BY created_at ASC, job_id ASC"
).fetchall()

print(f"Total rows in metaforge_requirements: {len(rows)}")

stored_profiles = [] # list of (job_id, client, client_jd_id, identity, profile, created_at)
duplicates = [] # list of (dup_job_id, orig_job_id, rule, score, client_jd_id)

for job_id, cjd_raw, created_at, updated_at, p_str in rows:
    p = json.loads(p_str)
    cjd = clean_client_jd_id(cjd_raw or p.get("client_jd_id"))
    client = normalize_client_key(p.get("requirement_from") or p.get("client_key") or "unknown")
    
    prof = build_requirement_profile(p, body_text=str(p.get("bodyText") or p.get("body") or ""))
    ident = compute_requirement_identity(
        client=client,
        client_jd_id=cjd,
        job_title=p.get("job_title"),
        location=p.get("location"),
        experience=p.get("overall_experience") or p.get("experience_level"),
        mandatory_skills=p.get("mandatory_skills"),
    )
    
    # Check against stored
    is_dup = False
    matched_job_id = None
    deciding_rule = None
    match_score = 0.0
    
    # 1. Hard check: same client + same client_jd_id
    if cjd:
        for sp in stored_profiles:
            if sp["client"] == client and sp["client_jd_id"] == cjd:
                is_dup = True
                matched_job_id = sp["job_id"]
                deciding_rule = f"SAME_CLIENT_JD_ID ({cjd})"
                match_score = 1.0
                break
                
    # 2. Whole requirement comparison (same client and city)
    if not is_dup:
        for sp in stored_profiles:
            dec, score, rule = compare_requirements(prof, sp["profile"])
            if dec == "DUPLICATE":
                is_dup = True
                matched_job_id = sp["job_id"]
                deciding_rule = rule
                match_score = score
                break
                
    if is_dup:
        duplicates.append({
            "duplicate_job_id": job_id,
            "original_job_id": matched_job_id,
            "client_jd_id": cjd,
            "title": p.get("job_title"),
            "city": prof.get("city"),
            "rule": deciding_rule,
            "score": match_score,
            "created_at": created_at,
        })
    else:
        stored_profiles.append({
            "job_id": job_id,
            "client": client,
            "client_jd_id": cjd,
            "identity": ident,
            "profile": prof,
            "created_at": created_at,
        })

print(f"\nUnique records to keep in requirement_identity: {len(stored_profiles)}")
print(f"Duplicates to move to duplicates_archive: {len(duplicates)}")

print("\nDuplicate list:")
for d in duplicates:
    print(f"  Job {d['duplicate_job_id']} (client_jd_id={d['client_jd_id']}) is DUPLICATE of {d['original_job_id']} via {d['rule']} (score={d['score']:.2f})")

conn_mf.close()
