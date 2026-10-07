import sqlite3, json, hashlib, re

def normalize_text(val):
    if not val:
        return ""
    if isinstance(val, list):
        val = " ".join(str(x) for x in val)
    s = str(val).lower().strip()
    s = re.sub(r'[\s\-_–—]+', ' ', s)
    return s

def compute_identity(client, client_jd_id, job_title, location, experience, mandatory_skills):
    c = normalize_text(client)
    cjd = str(client_jd_id or "").strip().upper()
    # clean client_jd_id if it's a fabricated placeholder like LTTS-2026-..., REQ-..., etc.
    if cjd and not re.match(r'^(LTTS|ACC|REQ)-\d{4}-', cjd, re.I) and not re.match(r'^\d{4}/\d{2}/\d{2}-\d{3,}$', cjd) and cjd not in ('NONE', 'NULL', 'NOT_FOUND', 'N/A', 'UNKNOWN'):
        return f"{c}:cjd:{cjd}"
    
    # Content hash
    t = normalize_text(job_title)
    l = normalize_text(location)
    e = normalize_text(experience)
    m = normalize_text(mandatory_skills)
    h = hashlib.sha256(f"{t}|{l}|{e}|{m}".encode("utf-8")).hexdigest()[:16]
    return f"{c}:hash:{h}"

conn = sqlite3.connect('data/metaforge_requirements.db')
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT * FROM metaforge_requirements").fetchall()

identities = {}
duplicates = []

for r in rows:
    p = json.loads(r['payload_json'])
    client = p.get('requirement_from') or ''
    cjd = p.get('client_jd_id') or r['client_jd_id'] or ''
    title = p.get('job_title') or ''
    loc = p.get('location') or ''
    exp = p.get('overall_experience') or p.get('experience') or ''
    mskills = p.get('mandatory_skills') or []
    
    ident = compute_identity(client, cjd, title, loc, exp, mskills)
    if ident in identities:
        duplicates.append((ident, identities[ident], (r['job_id'], cjd, title, loc, exp, r['created_at'])))
    else:
        identities[ident] = (r['job_id'], cjd, title, loc, exp, r['created_at'])

print(f"Total rows: {len(rows)}")
print(f"Unique identities: {len(identities)}")
print(f"Duplicate rows: {len(duplicates)}")
print("\n--- Duplicate pairs found ---")
for ident, orig, dup in duplicates:
    print(f"Identity: {ident}")
    print(f"  ORIG: {orig}")
    print(f"  DUP : {dup}")
conn.close()
