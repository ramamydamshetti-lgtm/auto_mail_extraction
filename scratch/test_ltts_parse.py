import sqlite3
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv()

from config import Settings
from boilerplate_learner import clean_structure_and_extract_boilerplate
from requirement_parser import _segment_email_into_blocks, parse_requirements_from_email

con = sqlite3.connect("data/metaforge_requirements.db")
r = con.execute("SELECT payload_json FROM metaforge_requirements WHERE job_id = ?", ("2026/09/07-023",)).fetchone()
p = json.loads(r[0])
body = p.get("bodyText") or p.get("body") or ""
subj = p.get("subject") or ""
sender = p.get("sender_email") or "Kallol.Chakraborty@Ltts.com"

print("--- RAW BLOCKS ---")
blocks = _segment_email_into_blocks(body, "LTTS")
print(f"Total blocks: {len(blocks)}")
for i, b in enumerate(blocks):
    print(f"\nBlock {i}:")
    b_text = b.get("block_text", "")
    print(f"Length: {len(b_text)}")
    cleaned_b_text, removed = clean_structure_and_extract_boilerplate(b_text, "LTTS")
    print(f"Cleaned lines ({len(cleaned_b_text.splitlines())}):")
    for ln in cleaned_b_text.splitlines()[:25]:
        print("  ", ln)

settings = Settings.from_env()
res = parse_requirements_from_email(
    subject=subj,
    body=body,
    settings=settings,
    from_email=sender,
)
print("\n--- PARSE RESULT ---")
for req in res.requirements:
    print("RequirementItem:", req.model_dump())
