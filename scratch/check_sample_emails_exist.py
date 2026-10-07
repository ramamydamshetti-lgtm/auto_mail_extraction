import os
import glob

print("=== CHECKING FOR REAL LTTS & ACCENTURE HOLD / REOPEN SAMPLE EMAILS ===")
sample_files = glob.glob("**/*hold*", recursive=True) + glob.glob("**/*reopen*", recursive=True)
for f in sample_files:
    if not any(x in f for x in [".venv", "__pycache__", ".git"]):
        print("Found:", f)

if not sample_files:
    print("No explicit hold/reopen sample email files found.")
