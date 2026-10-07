with open("ui/db.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

print(f"Total lines in ui/db.py: {len(lines)}")
for i, line in enumerate(lines, 1):
    l_lower = line.lower()
    if any(k in l_lower for k in [
        "parse_email_budget", "1000", "lpa", "inr", "fallback", "default", "none", "not specified", "sort", "first_arrival"
    ]):
        print(f"{i:4d}: {line.strip()[:100]}")
