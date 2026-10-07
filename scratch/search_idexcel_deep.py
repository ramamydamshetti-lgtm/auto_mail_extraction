import csv
import json
import os

print("=== Checking latest_500_all.csv columns ===")
if os.path.exists("latest_500_all.csv"):
    with open("latest_500_all.csv", "r", encoding="utf-8", errors="ignore") as f:
        reader = csv.reader(f)
        headers = next(reader)
        print("CSV Headers:", headers)

print("\n=== Checking latest_500_all.json ===")
if os.path.exists("latest_500_all.json"):
    with open("latest_500_all.json", "r", encoding="utf-8", errors="ignore") as f:
        data = json.load(f)
        print(f"Total JSON records: {len(data)}")
        
        domains = {}
        d_p_items = []
        
        for item in data:
            meta = item.get("metadata") or {}
            sender = meta.get("from") or meta.get("from_address") or item.get("from") or ""
            if isinstance(sender, dict):
                sender = sender.get("address") or sender.get("email") or str(sender)
            
            sender_str = str(sender).lower()
            if "@" in sender_str:
                dom = sender_str.split("@", 1)[1]
                if any(x in dom for x in ["excel", "idexcel", "ideexcel", "iexcel"]):
                    domains[dom] = domains.get(dom, 0) + 1
            
            subj = str(item.get("subject") or meta.get("subject") or "")
            body = str(item.get("content") or item.get("body") or "")
            blob = (subj + " " + body).lower()
            
            if "d-client" in blob or "p-client" in blob or "dclient" in blob or "pclient" in blob or "d client" in blob or "p client" in blob:
                d_p_items.append({
                    "from": sender_str,
                    "subject": subj,
                    "snippet": (subj + " " + body)[:250].replace("\n", " ")
                })
        
        print("Domains found matching excel/idexcel/iexcel:")
        for d, count in domains.items():
            print(f"  Domain: '{d}' -> Count: {count}")
            
        print(f"\nD-Client / P-Client items found in JSON: {len(d_p_items)}")
        for i, s in enumerate(d_p_items[:10]):
            print(f"\nSample {i+1}:")
            print(f"  From: {s['from']}")
            print(f"  Subject: {s['subject']}")
            print(f"  Snippet: {s['snippet']}")
