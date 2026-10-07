import sqlite3, json, sys, os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath('.'))

from boilerplate_learner import clean_structure_and_extract_boilerplate, validate_skills

conn = sqlite3.connect('data/metaforge_requirements.db')
c = conn.cursor()

print("======================================================================")
print("TESTING ROOT CAUSE 1 (SKILLS) FIX ON REAL HISTORICAL EMAILS")
print("======================================================================")

# Record 1: 2026/09/11-001 (Deloitte Fullstack Developer)
c.execute("SELECT payload_json FROM metaforge_requirements WHERE job_id = '2026/09/11-001'")
p1 = json.loads(c.fetchone()[0])
body1 = p1.get('bodyText')
cleaned1, removed1 = clean_structure_and_extract_boilerplate(body1, client='Deloitte')
print(f"\n1. RECORD 2026/09/11-001:")
print(f"   Original body: {len(body1)} chars | Cleaned body: {len(cleaned1)} chars | Removed lines: {len(removed1)}")
skills_in_cleaned = [sk for sk in ["Python", "Django", "FastAPI", "React.js", "TypeScript", "JavaScript", "HTML5", "PostgreSQL", "Docker", "AWS"] if sk.lower() in cleaned1.lower()]
print(f"   Skills preserved in cleaned text for LLM: {skills_in_cleaned} (Total: {len(skills_in_cleaned)}/10)")
test_skills_1 = ["Python", "Django", "FastAPI", "React.js", "TypeScript", "JavaScript", "HTML5", "PostgreSQL", "Docker", "AWS"]
val_skills_1 = validate_skills(test_skills_1, client='Deloitte', removed_lines=removed1)
print(f"   Validated skills output: {val_skills_1}")

# Record 2: 2026/09/29-024 (LTTS NVH)
c.execute("SELECT payload_json FROM metaforge_requirements WHERE job_id = '2026/09/29-024'")
p2 = json.loads(c.fetchone()[0])
body2 = p2.get('bodyText')
cleaned2, removed2 = clean_structure_and_extract_boilerplate(body2, client='LTTS')
print(f"\n2. RECORD 2026/09/29-024:")
skills_to_test_2 = ['ANSA', 'META', 'Resumes sent Date (DDMMYY)', 'Full Name of the candidate', 'Last Full Time Qualification', 'Mail ID']
val_skills_2 = validate_skills(skills_to_test_2, client='LTTS', removed_lines=removed2)
print(f"   Raw extracted items: {skills_to_test_2}")
print(f"   Validated skills (Candidate table noise removed, real skills kept): {val_skills_2}")

# Record 3: 2026/09/07-023 (Lead Power System Engineer)
c.execute("SELECT payload_json FROM metaforge_requirements WHERE job_id = '2026/09/07-023'")
p3 = json.loads(c.fetchone()[0])
body3 = p3.get('bodyText')
cleaned3, removed3 = clean_structure_and_extract_boilerplate(body3, client='LTTS')
print(f"\n3. RECORD 2026/09/07-023:")
skills_to_test_3 = ['PSS®E', 'Dig SILENT', 'Simulation awareness']
val_skills_3 = validate_skills(skills_to_test_3, client='LTTS', removed_lines=removed3)
print(f"   Raw candidate skills: {skills_to_test_3}")
print(f"   Validated skills (Real tools kept, fake keyword 'Simulation awareness' dropped): {val_skills_3}")
