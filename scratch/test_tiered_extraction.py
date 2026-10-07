import re

text = open('scratch/bodytext_011.txt', encoding='utf-8').read()

m_tiered = re.search(
    r"(?i)\b(?:bill\s+rate(?:\s+per\s+month)?(?:\s+for\s+tpc)?(?:\s*\([^)]*\))?|tiered\s+(?:budget|rates?)|rate\s+slabs?|tiered\s+budget\s+rates?)\s*[:\-–]?\s*\n"
    r"((?:[ \t]*(?:\d+.*?yrs|.*?l(?:\b|\n))[^\n]*\n?)+)",
    text
)

if m_tiered:
    tier_block = m_tiered.group(1).strip()
    lines = [re.sub(r"\s+", " ", l.strip(" -:*•\t")) for l in tier_block.splitlines() if l.strip(" -:*•\t")]
    cleaned_tiers = []
    for l in lines:
        if cleaned_tiers and re.match(r"^[-–—]?\s*\d+(?:\.\d+)?\s*l\b", l, re.I):
            cleaned_tiers[-1] = f"{cleaned_tiers[-1]} - {l.lstrip('-–— ')}"
        else:
            cleaned_tiers.append(l)
    summary = " / ".join(cleaned_tiers)
    print("Tiered summary:", repr(summary))
else:
    print("No tiered match")
