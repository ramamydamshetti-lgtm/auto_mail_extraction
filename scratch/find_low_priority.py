import os
import re

for root, dirs, files in os.walk("."):
    if ".git" in root or ".venv" in root or "__pycache__" in root:
        continue
    for f in files:
        if f.endswith(".py"):
            path = os.path.join(root, f)
            with open(path, "r", encoding="utf-8", errors="ignore") as file:
                lines = file.readlines()
            for idx, line in enumerate(lines, 1):
                if re.search(r'["\']low["\']\s+in\s+', line) or re.search(r'\bin\s+.*["\']low["\']', line) or ("priority" in line.lower() and "low" in line.lower()):
                    if any(w in line.lower() for w in ["priority", "norm_priority", "low"]):
                        print(f"{path}:{idx}: {line.strip()[:100]}")
