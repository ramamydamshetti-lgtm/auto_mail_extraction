import sqlite3, json, sys, os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath('.'))

from two_way_verifier import reconcile_two_way, deterministic_extract_block

conn = sqlite3.connect('data/metaforge_requirements.db')
c = conn.cursor()
c.execute("SELECT payload_json FROM metaforge_requirements WHERE job_id = '2026/09/11-001'")
p = json.loads(c.fetchone()[0])
body = p.get('bodyText')

det = deterministic_extract_block(body, client_name='Deloitte')

# Simulate AI output before verification
ai_item = {
    "job_title": "Fullstack Developer",
    "location": ["Bangalore"],
    "experience": "3-6 years",
    "budget": "75000 – 1,00,000",
    "mandatory_skills": ["Python", "Django", "FastAPI", "React.js"],
    "skills": ["TypeScript", "JavaScript", "HTML5", "CSS3"],
    "work_mode": "5 days work from office",
    "notice_period": "Immediate",
    "client_req_id": "RQ055262",
}

reconciled, rev_req, rev_reasons = reconcile_two_way(ai_item, det, body)
print("=== RECONCILED OUTPUT ===")
for k, v in reconciled.items():
    if k in ai_item:
        print(f"  {k:20}: {v}")
print("Review required:", rev_req)
print("Review reasons:", rev_reasons)
