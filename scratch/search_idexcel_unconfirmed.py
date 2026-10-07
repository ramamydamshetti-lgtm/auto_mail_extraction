import csv
import json
import re
import os

csv_path = "latest_500_all.csv"
if not os.path.exists(csv_path):
    print("latest_500_all.csv not found!")
    exit(1)

domains = {}
d_p_snippets = []

with open(csv_path, "r", encoding="utf-8", errors="ignore") as f:
    reader = csv.DictReader(f)
    for row in reader:
        # Check sender email/domain
        from_addr = row.get("from_address") or row.get("from") or row.get("sender") or ""
        sender_email = str(from_addr).strip().lower()
        if "@" in sender_email:
            domain = sender_email.split("@", 1)[1]
            if "idexcel" in domain or "ideexcel" in domain or "excel" in domain:
                domains[domain] = domains.get(domain, 0) + 1
        
        # Check subject and body for D-Client / P-Client
        subj = row.get("subject") or ""
        body = row.get("body") or row.get("content") or ""
        combined = f"{subj}\n{body}"
        
        if "d-client" in combined.lower() or "p-client" in combined.lower() or "dclient" in combined.lower() or "pclient" in combined.lower():
            d_p_snippets.append({
                "from": sender_email,
                "subject": subj,
                "snippet": combined[:200].replace("\n", " ")
            })

print("=== SENDER DOMAINS RESEMBLING idexcel/ideexcel ===")
for d, count in domains.items():
    print(f"Domain: '{d}' | Count: {count}")

print(f"\n=== TOTAL D-Client / P-Client MESSAGES FOUND: {len(d_p_snippets)} ===")
print("=== SAMPLE SNIPPETS (up to 5) ===")
for i, s in enumerate(d_p_snippets[:5]):
    print(f"\nSample {i+1}:")
    print(f"  From: {s['from']}")
    print(f"  Subject: {s['subject']}")
    print(f"  Snippet: {s['snippet']}")
