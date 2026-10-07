import json
import urllib.request
import re
from datetime import datetime

# 1. Fetch live page HTML
req_html = urllib.request.Request("http://127.0.0.1:5000/", headers={"User-Agent": "Verifier"})
with urllib.request.urlopen(req_html) as resp:
    html = resp.read().decode("utf-8")

# Extract table rows for Requirement ID column
# Regex to match <td> with req-id-link
# Look for: <a href="/requirement/..." class="req-id-link">...</a>
row_matches = re.findall(r'<td>\s*(<a href="/requirement/([^"]+)" class="req-id-link">([^<]+)</a>(?:\s*\(\[<a href="/requirement/[^"]+" class="req-id-link">([^<]+)</a>\]\))?)\s*</td>', html)

print(f"Total rows matched in live HTML: {len(row_matches)}")

with_client_id = []
without_client_id = []

for full_block, req_id, int_id_txt, client_id in row_matches:
    if client_id:
        with_client_id.append({
            "internal_id": int_id_txt,
            "client_id": client_id,
            "rendered_html": full_block.strip(),
            "rendered_markdown": f"{int_id_txt} ([{client_id}](http://127.0.0.1:5000/requirement/{req_id}))"
        })
    else:
        without_client_id.append({
            "internal_id": int_id_txt,
            "rendered_html": full_block.strip(),
            "rendered_markdown": f"[{int_id_txt}](http://127.0.0.1:5000/requirement/{req_id})"
        })

print("\n=== STEP 4.1: Real requirements WITH client-provided ID (linked format) ===")
for item in with_client_id[:5]:
    print(f"Internal ID: {item['internal_id']} | Client ID: {item['client_id']}")
    print(f"  Markdown: {item['rendered_markdown']}")
    print(f"  HTML:     {item['rendered_html']}\n")

print("\n=== STEP 4.2: Real requirements WITHOUT client-provided ID (bare internal ID) ===")
for item in without_client_id[:5]:
    print(f"Internal ID: {item['internal_id']}")
    print(f"  Markdown: {item['rendered_markdown']}")
    print(f"  HTML:     {item['rendered_html']}\n")

# 2. Fetch live API data to inspect top rows with full timestamps and seconds
req_api = urllib.request.Request("http://127.0.0.1:5000/api/requirements?page=1&page_size=10", headers={"User-Agent": "Verifier"})
with urllib.request.urlopen(req_api) as resp:
    api_data = json.loads(resp.read().decode("utf-8"))

items = api_data.get("data", [])
print("\n=== STEP 4.3: Top rows with full timestamp (strict descending order) ===")
dts = []
for i, item in enumerate(items[:8]):
    arr = item.get("arr_iso") or item.get("created_at") or ""
    s = arr.strip()
    if s.endswith("Z"):
        dt = datetime.fromisoformat(s[:-1] + "+00:00")
    else:
        dt = datetime.fromisoformat(s)
    dts.append(dt)
    client_str = f" ([{item.get('client_jd_id')}])" if item.get('client_jd_id') else ""
    print(f"Row {i+1} | {item.get('req_id')}{client_str:<15} | Full ISO: {arr:<25} | Display: {dt.strftime('%m/%d/%Y %I:%M:%S %p')}")

is_desc = all(dts[i] >= dts[i+1] for i in range(len(dts)-1))
print(f"\nStrict full-precision descending order verified: {is_desc}")
