import csv
import json

domains_count = {}
d_client_matches = []
p_client_matches = []

with open("latest_500_all.csv", "r", encoding="utf-8", errors="ignore") as f:
    reader = csv.DictReader(f)
    for i, row in enumerate(reader):
        from_email = (row.get("from_email") or "").strip().lower()
        sender_domain = (row.get("sender_domain") or "").strip().lower()
        
        # Track domain
        domain = sender_domain or (from_email.split("@")[1] if "@" in from_email else "")
        if "excel" in domain or "idexcel" in domain or "ideexcel" in domain:
            domains_count[domain] = domains_count.get(domain, 0) + 1
            
        subj = row.get("subject") or ""
        body = row.get("body_normalized") or ""
        combined = f"Subject: {subj}\nBody: {body}"
        
        if "d-client" in combined.lower() or "dclient" in combined.lower() or "d client" in combined.lower():
            d_client_matches.append((from_email, subj, combined[:300].replace("\n", " ")))
            
        if "p-client" in combined.lower() or "pclient" in combined.lower() or "p client" in combined.lower():
            p_client_matches.append((from_email, subj, combined[:300].replace("\n", " ")))

print("=== ALL DOMAINS IN CSV RESEMBLING idexcel / ideexcel / excel ===")
for d, count in domains_count.items():
    print(f"  Domain: '{d}' -> Count: {count}")

print(f"\n=== D-Client matches count: {len(d_client_matches)} ===")
for idx, (f, s, snip) in enumerate(d_client_matches[:5]):
    print(f"\nD-Client Sample {idx+1}:")
    print(f"  From: {f}")
    print(f"  Subject: {s}")
    print(f"  Snippet: {snip}")

print(f"\n=== P-Client matches count: {len(p_client_matches)} ===")
for idx, (f, s, snip) in enumerate(p_client_matches[:5]):
    print(f"\nP-Client Sample {idx+1}:")
    print(f"  From: {f}")
    print(f"  Subject: {s}")
    print(f"  Snippet: {snip}")
