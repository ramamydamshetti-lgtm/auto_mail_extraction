import sqlite3, json, sys, os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath('.'))

conn = sqlite3.connect('data/metaforge_requirements.db')
c = conn.cursor()
c.execute("SELECT payload_json FROM metaforge_requirements WHERE job_id = '2026/09/11-001'")
row = c.fetchone()
p = json.loads(row[0])
body = p.get('bodyText')
subject = p.get('subject')

print(f"Subject: {subject}")
print(f"Body length: {len(body)}")

# Step 1: Thread segment & candidate tables
from requirement_parser import _latest_thread_segment, _strip_candidate_tables
latest = _latest_thread_segment(body)
cleaned_latest = _strip_candidate_tables(latest)
print(f"Latest segment length: {len(latest)}")
print(f"Cleaned latest length: {len(cleaned_latest)}")

# Step 2: Segmentation into blocks
from requirement_segmenter import segment_email_into_blocks
blocks = segment_email_into_blocks(cleaned_latest or body, subject=subject)
print(f"Blocks count: {len(blocks)}")
for i, b in enumerate(blocks):
    print(f"  Block {i}: length={len(b.get('block_text') or '')} table_row_fields={b.get('table_row_fields')}")

# Step 3: Boilerplate removal
from boilerplate_learner import clean_structure_and_extract_boilerplate, validate_skills
b_text = blocks[0].get('block_text') or ''
cleaned_b, removed = clean_structure_and_extract_boilerplate(b_text, client='Deloitte')
print(f"Cleaned block length: {len(cleaned_b)} | Removed lines: {len(removed)}")
print("Sample removed lines:", removed[:10])

# Step 4: Let's check what 2500 truncation would do to cleaned_b
truncated_b = cleaned_b[:2500]
print(f"Truncated block length: {len(truncated_b)}")
print("Is 'Python' in truncated_b?", 'Python' in truncated_b)
print("Is 'Bangalore' in truncated_b?", 'Bangalore' in truncated_b)
print("Is 'Fullstack' in truncated_b?", 'Fullstack' in truncated_b)
print("Is '75000' in truncated_b?", '75000' in truncated_b)
print("Is 'office' in truncated_b?", 'office' in truncated_b)

# Step 5: Deterministic extract block
from two_way_verifier import deterministic_extract_block
det = deterministic_extract_block(b_text, client_name='Deloitte')
print("Deterministic extraction:")
for k, v in det.items():
    if k != 'quotes':
        print(f"  {k:20}: {v}")
