import re

pat = re.compile(
    r"(?i)(?:"
    r"(?:tpc\s+rates?|rate\s*/\s*pm|monthly\s+budget|bill\s+rate(?:\s+per\s+month)?(?:\s+for\s+tpc)?(?:\s*\([^)]*\))?|rate)\s*[:\-–]?\s*(\d{5,7})(?:\s*(?:/\s*m(?:onth)?|per\s+month|pm))?"
    r"|(\d{5,7})\s*(?:/\s*m(?:onth)?|per\s+month|pm)"
    r"|^\s*(\d{5,7})\s*$"
    r")"
)

tests = [
    "Bengaluru, Karnataka 560092 India",
    "Bill Rate per month for TPC (in terms of INR) – 100000",
    "rate: 80000",
    "100000 per month",
    "100000",
    "80000 / month",
    "Phone: +91 96 8610 0177",
]

for t in tests:
    m = pat.search(t)
    val = next((g for g in m.groups() if g), None) if m else None
    print(f"{t[:40]:40} -> {val}")
