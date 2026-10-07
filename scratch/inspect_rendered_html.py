import urllib.request
import re

html = urllib.request.urlopen('http://127.0.0.1:5000/').read().decode('utf-8')
matches = re.findall(r'<td style="white-space: nowrap;">\s*(.*?)\s*</td>', html, re.DOTALL)
print(f"Total rows rendered on page: {len(matches)}")
print("\n--- FIRST 25 RENDERED ROWS ---")
for i, m in enumerate(matches[:25], start=1):
    cleaned = re.sub(r'<[^>]+>', ' ', m)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    print(f"#{i:02d} | {cleaned}")
