import os
import json
import csv
import glob
import re

print("================ DEEP SCAN ACROSS ALL REPOSITORY DATA FILES ================")

def check_file_counts(filepath):
    acc_count = 0
    ltts_count = 0
    
    if filepath.endswith(".json"):
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                data = json.load(f)
                if isinstance(data, list):
                    for item in data:
                        blob = json.dumps(item).lower()
                        if "accenture" in blob or "iexcel" in blob:
                            acc_count += 1
                        elif "ltts" in blob or "l&t" in blob:
                            ltts_count += 1
        except Exception as e:
            pass
            
    elif filepath.endswith(".csv"):
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                reader = csv.reader(f)
                for row in reader:
                    blob = " ".join(row).lower()
                    if "accenture" in blob or "iexcel" in blob:
                        acc_count += 1
                    elif "ltts" in blob or "l&t" in blob:
                        ltts_count += 1
        except Exception as e:
            pass

    return acc_count, ltts_count

# Search all CSV and JSON files
for root, dirs, files in os.walk("."):
    if ".venv" in root or ".pytest_cache" in root or ".git" in root:
        continue
    for file in files:
        if file.endswith(".json") or file.endswith(".csv"):
            full_path = os.path.join(root, file)
            acc, ltts = check_file_counts(full_path)
            if acc > 0 or ltts > 0:
                print(f"File: {full_path:<60} | Accenture: {acc:<5} | LTTS: {ltts:<5}")

print("\n--- Checking PDF text if pypdf or pdfplumber available ---")
try:
    import pypdf
    reader = pypdf.PdfReader("September_2026_Recruitment_Requirements_Report.pdf")
    text = ""
    for page in reader.pages:
        text += page.extract_text()
    print("PDF Text Preview (first 1000 chars):")
    print(text[:1000])
except Exception as e:
    print("PyPDF not available or error:", e)
