import re
with open("scratch/pdf_text.txt", "r", encoding="utf-8") as f:
    text = f.read()

acc_count = len(re.findall(r"\bAccenture\b", text))
ltts_count = len(re.findall(r"\bLTTS\b", text))

print(f"Total 'Accenture' occurrences in PDF report: {acc_count}")
print(f"Total 'LTTS' occurrences in PDF report: {ltts_count}")

# Parse individual requirement entries in PDF if formatted with IDs
acc_ids = set(re.findall(r"\bACC[A-Z0-9_\-]*\b|\bAccenture\b", text))
ltts_ids = set(re.findall(r"LTTS-\d+-\d+", text))

print(f"Unique LTTS requirement IDs in PDF report: {len(ltts_ids)}")

# Let's count by daily sections in the PDF
days = re.split(r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+September\s+\d+,\s+2026", text)
print(f"Total days found in PDF report: {len(days)-1}")

acc_daily = 0
ltts_daily = 0

for i, day_chunk in enumerate(days[1:], 1):
    acc_in_day = len(re.findall(r"\bAccenture\b", day_chunk))
    ltts_in_day = len(re.findall(r"\bLTTS-\d+-\d+\b|\bLTTS\b", day_chunk))
    # Count distinct requirement blocks
    acc_reqs = day_chunk.count("Requirement ID:") if "Requirement ID:" in day_chunk else 0
    print(f"Day {i:02d}: Accenture mentions = {acc_in_day}, LTTS mentions = {ltts_in_day}")
