import re

with open("field_mapper.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

print(f"Total lines in field_mapper.py: {len(lines)}")
for i, line in enumerate(lines, 1):
    l_lower = line.lower()
    if any(k in l_lower for k in [
        "number_of_positions", "positions", "experience_level", "employment_type", 
        "work_mode", "priority", "type_of_demand", "job_status", "jd_count", "mid senior", "contract", "on-site", "below"
    ]):
        print(f"{i:4d}: {line.strip()[:100]}")
