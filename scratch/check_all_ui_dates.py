import sys
sys.path.insert(0, ".")
from collections import defaultdict
import re
from ui.db import fetch_all_records

config = {'db_paths': ['data/metaforge_requirements.db', 'data/processed_messages.db']}
recs = fetch_all_records(config)

by_date = defaultdict(list)
for r in recs:
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
