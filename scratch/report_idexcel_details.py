import csv
import json
import re
import os
import glob

# Search across latest_500_all.csv as specified in prompt
csv_path = "latest_500_all.csv"

domain_counts = {}
d_client_samples = []
p_client_samples = []

pattern_idexcel = re.compile(r"id[e]?xcel", re.I)
pattern_d = re.compile(r"\bD-Client\b|\bDClient\b|\bD\s*-\s*Client\b", re.I)
pattern_p = re.compile(r"\bP-Client\b|\bPClient\b|\bP\s*-\s*Client\b", re.I)

if os.path.exists(csv_path):
    with open(csv_path, "r", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            from_email = str(row.get("from_email") or "").strip().lower()
            sender_domain = str(row.get("sender_domain") or "").strip().lower()
            
            domain = sender_domain or (from_email.split("@")[1] if "@" in from_email else "")
            
            if pattern_idexcel.search(domain) or "idexcel" in from_email or "ideexcel" in from_email or "iexcel" in domain:
                domain_counts[domain] = domain_counts.get(domain, 0) + 1
            
            subj = str(row.get("subject") or "")
            body = str(row.get("body_normalized") or "")
            combined = f"Subject: {subj}\nBody: {body}"
            
            if pattern_d.search(combined):
                d_client_samples.append({
                    "from": from_email,
                    "subject": subj,
                    "snippet": combined[:250].replace("\n", " ")
                })
            if pattern_p.search(combined):
                p_client_samples.append({
                    "from": from_email,
                    "subject": subj,
                    "snippet": combined[:250].replace("\n", " ")
                })

print("=== EXACT DOMAIN STRINGS FOUND & EMAIL COUNTS ===")
if domain_counts:
    for d, c in domain_counts.items():
        print(f"Exact Domain String: '{d}' | Email Count: {c}")
else:
    print("No domains matching idexcel/ideexcel found directly in latest_500_all.csv sender column (iexcel.co.in / idexcel.com found in codebase).")

print(f"\n=== D-CLIENT WORDING SAMPLES ({len(d_client_samples)} total found) ===")
for i, s in enumerate(d_client_samples[:5]):
    print(f"Sample {i+1}:")
    print(f"  From: {s['from']}")
    print(f"  Subject: {s['subject']}")
    print(f"  Snippet: {s['snippet']}")

print(f"\n=== P-CLIENT WORDING SAMPLES ({len(p_client_samples)} total found) ===")
for i, s in enumerate(p_client_samples[:5]):
    print(f"Sample {i+1}:")
    print(f"  From: {s['from']}")
    print(f"  Subject: {s['subject']}")
    print(f"  Snippet: {s['snippet']}")
