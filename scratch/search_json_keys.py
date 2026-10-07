import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('latest_500_all.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print(f"Total items in latest_500_all.json: {len(data)}")
if data:
    print("Keys of first item:", list(data[0].keys()))

accenture_items = []
for idx, item in enumerate(data):
    full_str = json.dumps(item).lower()
    if 'accenture' in full_str or 'req id' in full_str or 'open demands' in full_str:
        accenture_items.append((idx, item))

print(f"Items matching accenture/req id/open demands: {len(accenture_items)}")
for idx, item in accenture_items:
    print(f"--- Item {idx} ---")
    for k, v in item.items():
        if v and len(str(v)) > 0:
            if isinstance(v, str) and len(v) > 200:
                print(f"  {k}: {v[:200]}...")
            else:
                print(f"  {k}: {v}")
