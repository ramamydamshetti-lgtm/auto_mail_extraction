"""Find requirements that were referenced in multiple emails using the status_history and processed_messages.db."""
import sqlite3
import json

# Check processed_messages.db for client_requirements
print("=== processed_messages.db ===")
conn2 = sqlite3.connect('data/processed_messages.db')
conn2.row_factory = sqlite3.Row

# Check what tables exist
tables = [r[0] for r in conn2.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print("Tables:", tables)

# Check client_requirements
if 'client_requirements' in tables:
    cr_count = conn2.execute("SELECT COUNT(*) FROM client_requirements").fetchone()[0]
    print("client_requirements rows:", cr_count)
    
    cr_cols = [r[1] for r in conn2.execute("PRAGMA table_info(client_requirements)").fetchall()]
    print("Columns:", cr_cols)
    
    # Sample
    rows = conn2.execute("SELECT client_jd_id, requirement_from, status, created_at, updated_at FROM client_requirements ORDER BY updated_at DESC LIMIT 10").fetchall()
    for r in rows:
        print(f"  cjd={r['client_jd_id']}, from={r['requirement_from']}, status={r['status']}, created={str(r['created_at'])[:19]}, updated={str(r['updated_at'])[:19]}")

# Check status_history
if 'status_history' in tables:
    sh_count = conn2.execute("SELECT COUNT(*) FROM status_history").fetchone()[0]
    print("\nstatus_history rows:", sh_count)
    rows = conn2.execute("SELECT * FROM status_history ORDER BY id DESC LIMIT 10").fetchall()
    for r in rows:
        print(f"  req_id={r['requirement_id']}, {r['from_status']} -> {r['to_status']} at {r['changed_at']}")

# Check requirement_fingerprints
if 'requirement_fingerprints' in tables:
    fp_count = conn2.execute("SELECT COUNT(*) FROM requirement_fingerprints").fetchone()[0]
    print("\nrequirement_fingerprints rows:", fp_count)

# Check requirement_memory
if 'requirement_memory' in tables:
    rm_count = conn2.execute("SELECT COUNT(*) FROM requirement_memory").fetchone()[0]
    print("requirement_memory rows:", rm_count)
    rows = conn2.execute("SELECT requirement_from, job_title_norm, created_at FROM requirement_memory ORDER BY created_at DESC LIMIT 10").fetchall()
    for r in rows:
        print(f"  from={r['requirement_from']}, title={r['job_title_norm']}, at={str(r['created_at'])[:19]}")

conn2.close()

# Now check metaforge_requirements.db - look at any rows with client_jd_id
print("\n=== metaforge_requirements.db ===")
conn = sqlite3.connect('data/metaforge_requirements.db')
conn.row_factory = sqlite3.Row

# Check how many rows have a real client_jd_id (non-null, non-empty)
with_cjd = conn.execute("SELECT COUNT(*) FROM metaforge_requirements WHERE client_jd_id IS NOT NULL AND client_jd_id != ''").fetchone()[0]
without_cjd = conn.execute("SELECT COUNT(*) FROM metaforge_requirements WHERE client_jd_id IS NULL OR client_jd_id = ''").fetchone()[0]
print(f"Rows with client_jd_id: {with_cjd}, without: {without_cjd}")

# Sample rows that have client_jd_id
sample = conn.execute("""
    SELECT job_id, client_jd_id, created_at, updated_at, payload_json
    FROM metaforge_requirements
    WHERE client_jd_id IS NOT NULL AND client_jd_id != ''
    LIMIT 5
""").fetchall()
for r in sample:
    jid = r['job_id']
    cjd = r['client_jd_id']
    p = json.loads(r['payload_json'])
    title = p.get('job_title', '')
    client = p.get('requirement_from', '')
    print(f"  job_id={jid}, cjd={cjd}, title={title[:50]}, client={client}")

# Sample rows without client_jd_id
sample2 = conn.execute("""
    SELECT job_id, created_at, updated_at, payload_json
    FROM metaforge_requirements
    WHERE client_jd_id IS NULL OR client_jd_id = ''
    ORDER BY created_at DESC
    LIMIT 5
""").fetchall()
print("\nRows without client_jd_id:")
for r in sample2:
    p = json.loads(r['payload_json'])
    title = p.get('job_title', '')
    client = p.get('requirement_from', '')
    print(f"  job_id={r['job_id']}, title={title[:50]}, client={client}")

conn.close()
