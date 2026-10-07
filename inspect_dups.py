import sqlite3
import json
from requirement_comparator import build_requirement_profile, compare_requirements

conn = sqlite3.connect("data/metaforge_requirements.db")
conn.row_factory = sqlite3.Row

rows = conn.execute("SELECT job_id, client_jd_id, identity, payload_json, former_job_id, created_at FROM metaforge_requirements ORDER BY rowid ASC").fetchall()

items = []
for r in rows:
    p = json.loads(r["payload_json"])
    prof = build_requirement_profile(p)
    items.append({
        "job_id": r["job_id"],
        "client_jd_id": r["client_jd_id"] or p.get("client_jd_id"),
        "former_job_id": r["former_job_id"] or p.get("former_job_id"),
        "identity": r["identity"],
        "client": prof["client"],
        "title": prof["title"],
        "city": prof["city"],
        "exp": prof["experience_range"],
        "skills": prof["mandatory_skills"] + prof["additional_skills"],
        "created_at": r["created_at"],
        "profile": prof,
        "payload": p,
    })

# Deduplicate
seen_canonical = set()
duplicates_to_merge = [] # (duplicate_item, canonical_item)

for i in range(len(items)):
    for j in range(i + 1, len(items)):
        it1 = items[i]
        it2 = items[j]

        if it1["job_id"] in seen_canonical or it2["job_id"] in seen_canonical:
            continue

        if it1["client"] != it2["client"]:
            continue

        cjd1 = it1["client_jd_id"]
        cjd2 = it2["client_jd_id"]

        is_dup = False
        rule_desc = ""

        if cjd1 and cjd2 and str(cjd1).strip().lower() == str(cjd2).strip().lower():
            is_dup = True
            rule_desc = f"SAME_CLIENT_JD_ID ({cjd1})"
        elif (not cjd1 or not cjd2) or (cjd1 == cjd2):
            dec, score, rule = compare_requirements(it1["profile"], it2["profile"])
            # Distinguish developer levels (L1, L2, L3)
            t1 = it1["title"]
            t2 = it2["title"]
            if t1 != t2 and ("l1" in t1 or "l2" in t1 or "l3" in t1 or "l1" in t2 or "l2" in t2 or "l3" in t2):
                dec = "NOT_DUPLICATE"
            if dec == "DUPLICATE":
                is_dup = True
                rule_desc = f"{rule} (score={score:.2f})"

        if is_dup:
            # Older/canonical record is usually it1 (earlier in DB or created_at)
            # If one has formatted ID YYYY/MM/DD-NNN and other has legacy (e.g. ACC-...), formatted is canonical
            if "ACC-" in it1["job_id"] and "2026/" in it2["job_id"]:
                canonical, dup = it2, it1
            elif "ACC-" in it2["job_id"] and "2026/" in it1["job_id"]:
                canonical, dup = it1, it2
            else:
                canonical, dup = it1, it2

            duplicates_to_merge.append((dup, canonical, rule_desc))
            seen_canonical.add(dup["job_id"])

print(f"Total duplicates to merge: {len(duplicates_to_merge)}")
for dup, canonical, rule_desc in duplicates_to_merge:
    print(f"Duplicate [{dup['job_id']}] -> Canonical [{canonical['job_id']}] | {rule_desc}")
    print(f"  Title: '{canonical['title']}' | Client: '{canonical['client']}' | Loc: '{canonical['city']}'")
