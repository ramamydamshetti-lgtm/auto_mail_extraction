import re

with open("requirement_parser.py", "r", encoding="utf-8") as f:
    text = f.read()

print("Stripping functions:")
for m in re.finditer(r"def\s+(_strip[a-zA-Z0-9_]*|_clean[a-zA-Z0-9_]*|_filter[a-zA-Z0-9_]*|is_noise[a-zA-Z0-9_]*)\s*\(", text):
    print(m.group(1))

# Check where candidate tables are stripped
lines = text.splitlines()
for i, l in enumerate(lines, 1):
    if "candidate" in l.lower() or "resumes sent" in l.lower() or "exclusion" in l.lower():
        print(f"{i:4d}: {l.strip()[:100]}")
