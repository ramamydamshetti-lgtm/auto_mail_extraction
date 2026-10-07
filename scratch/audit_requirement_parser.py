import re

with open("requirement_parser.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

print(f"Total lines in requirement_parser.py: {len(lines)}")
for i, line in enumerate(lines, 1):
    l_lower = line.lower()
    if any(k in l_lower for k in [
        "0.62", "first_cells", "confidence = 1.0", "confidence=1.0", "mandatory_skills =",
        "extractionmethodenum", "job_title", "priority"
    ]):
        print(f"{i:4d}: {line.strip()[:100]}")
