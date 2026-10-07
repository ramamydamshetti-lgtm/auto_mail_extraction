"""
Full diagnostic of the existing state and demonstration of all 4 rules.
Shows requirements that appeared in multiple emails (status changes),
and proves field-level update tracking, deduplication, and recency sort.
"""
import sqlite3
import json

# Connect to both DBs
proc_conn = sqlite3.connect('data/processed_messages.db')
proc_conn.row_factory = sqlite3.Row
mf_conn = sqlite3.connect('data/metaforge_requirements.db')
mf_conn.row_factory = sqlite3.Row

print("=" * 70)
print("VERIFICATION SCRIPT — Rules 1-4")
print("=" * 70)

# === Find requirements that have status_history (appeared in 2+ emails) ===
sh_rows = proc_conn.execute("""
    SELECT requirement_id, COUNT(*) as change_count, 
           MIN(changed_at) as first_change, MAX(changed_at) as last_change
    FROM status_history
    GROUP BY requirement_id
    ORDER BY change_count DESC
    LIMIT 10
""").fetchall()

print("\n1. Requirements with status changes (appeared in 2+ emails):")
for r in sh_rows:
    print(f"   req_id={r['requirement_id']}, changes={r['change_count']}, first={r['first_change'][:19]}, last={r['last_change'][:19]}")

# Pick the top requirement with multiple status changes for demo
if sh_rows:
    demo_req_id = sh_rows[0]['requirement_id']
    print(f"\n2. Detailed status history for: {demo_req_id}")
    hist = proc_conn.execute("""
        SELECT from_status, to_status, changed_at, changed_by, source_email_id
        FROM status_history WHERE requirement_id = ?
        ORDER BY id ASC
    """, (demo_req_id,)).fetchall()
    for h in hist:
        print(f"   {h['from_status']} -> {h['to_status']} at {h['changed_at'][:19]} by {h['changed_by']}")

# === Show client_requirements before/after ===
print("\n3. client_requirements table (requirement identity store):")
cr_rows = proc_conn.execute("""
    SELECT client_jd_id, requirement_from, status, created_at, updated_at
    FROM client_requirements
    ORDER BY updated_at DESC
    LIMIT 15
""").fetchall()
for r in cr_rows:
    print(f"   {r['client_jd_id']:15s} | {r['requirement_from']:12s} | {r['status']:6s} | created={r['created_at'][:19]} | updated={r['updated_at'][:19]}")

# === Show requirements with different created_at vs updated_at (were updated) ===
print("\n4. Requirements that were updated (created_at != updated_at):")
updated_rows = proc_conn.execute("""
    SELECT client_jd_id, requirement_from, status, created_at, updated_at
    FROM client_requirements
    WHERE created_at != updated_at
    ORDER BY updated_at DESC
""").fetchall()
print(f"   Count: {len(updated_rows)}")
for r in updated_rows[:10]:
    delta_s = None
    try:
        from datetime import datetime, timezone
        c = datetime.fromisoformat(r['created_at'].replace('Z', '+00:00'))
        u = datetime.fromisoformat(r['updated_at'].replace('Z', '+00:00'))
        delta_s = int((u - c).total_seconds())
    except:
        pass
    print(f"   {r['client_jd_id']:15s} | {r['requirement_from']:12s} | {r['status']:6s} | Δ={delta_s}s")

# === Prove deduplication: same client_jd_id appears only once ===
print("\n5. Deduplication check — each client_jd_id appears exactly once:")
dup_check = proc_conn.execute("""
    SELECT client_jd_id, COUNT(*) as cnt
    FROM client_requirements
    GROUP BY client_jd_id
    HAVING cnt > 1
""").fetchall()
if dup_check:
    print(f"   FAIL: Found {len(dup_check)} duplicate client_jd_ids!")
else:
    print("   PASS: All client_jd_ids are unique (no duplicates).")

# === Show the Accenture requirements for cross-client verification ===
print("\n6. Accenture requirements sample (client 1):")
acc_rows = proc_conn.execute("""
    SELECT client_jd_id, status, created_at, updated_at
    FROM client_requirements
    WHERE requirement_from = 'Accenture'
    ORDER BY updated_at DESC
    LIMIT 5
""").fetchall()
for r in acc_rows:
    print(f"   {r['client_jd_id']:15s} | {r['status']:6s} | created={r['created_at'][:19]} | updated={r['updated_at'][:19]}")

print("\n7. Deloitte requirements sample (client 2):")
del_rows = proc_conn.execute("""
    SELECT client_jd_id, status, created_at, updated_at
    FROM client_requirements
    WHERE requirement_from = 'Deloitte'
    ORDER BY updated_at DESC
    LIMIT 5
""").fetchall()
for r in del_rows:
    print(f"   {r['client_jd_id']:15s} | {r['status']:6s} | created={r['created_at'][:19]} | updated={r['updated_at'][:19]}")

proc_conn.close()
mf_conn.close()
print("\nDone.")
