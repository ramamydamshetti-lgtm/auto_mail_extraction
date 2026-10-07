import urllib.request
import re

print("Testing live dashboard: http://127.0.0.1:5000/")
with urllib.request.urlopen("http://127.0.0.1:5000/") as resp:
    html = resp.read().decode('utf-8')
    print("Dashboard HTTP status:", resp.status)

# Check prohibited strings
prohibited = ["Accenture Requirement", "Requirement Role", "Other company / source"]
for p in prohibited:
    if p in html:
        print(f"FAILED: Found prohibited string '{p}' in dashboard HTML!")
    else:
        print(f"PASSED: '{p}' NOT found in dashboard HTML.")

# Parse the first 5 table rows
rows = re.findall(r'<tr onclick="window\.location\.href=\'/requirement/([^\']+)\'">(.*?)</tr>', html, re.DOTALL)
print(f"\nRendered rows on page 1: {len(rows)}")
for i, (req_path, row_html) in enumerate(rows[:6]):
    cells = [re.sub(r'<[^>]+>', '', c).strip() for c in re.findall(r'<td[^>]*>(.*?)</td>', row_html, re.DOTALL)]
    print(f"\nRow {i+1} [URL: /requirement/{req_path}]:")
    if len(cells) >= 7:
        print(f"  Req ID: {cells[1]}")
        print(f"  Client: {cells[2]}")
        print(f"  Email: {cells[3]}")
        print(f"  Role: {cells[4]}")
        print(f"  Priority: {cells[5]}")
        print(f"  Owner: {cells[6]}")
        print(f"  Arrived: {cells[7] if len(cells) > 7 else 'N/A'}")
