import urllib.request
import re

html = urllib.request.urlopen('http://127.0.0.1:5000/?page=2').read().decode('utf-8')
matches = re.findall(r'<td style="white-space: nowrap;">\s*(.*?)\s*</td>', html, re.DOTALL)
print(f"Total rows on page 2: {len(matches)}")
print("\n--- PAGE 2 ROWS ---")
for i, m in enumerate(matches, start=21):
    cleaned = re.sub(r'<[^>]+>', ' ', m)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    print(f"#{i:02d} | {cleaned}")
