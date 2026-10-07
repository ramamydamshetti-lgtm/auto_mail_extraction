import json
import sqlite3
import urllib.request
import re
from bs4 import BeautifulSoup
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ui.app import UI_CONFIG
from ui.db import fetch_all_records

def main():
    records = fetch_all_records(UI_CONFIG)
    print(f"Total records in identity engine: {len(records)}")
    
    # Pick 4 diverse records with rich payloads (e.g., from different clients)
    chosen = []
    seen_clients = set()
    for r in records:
        c = r.get("payload", {}).get("requirement_from") or "Unknown"
        if c not in seen_clients and len(r.get("payload", {})) > 5:
            seen_clients.add(c)
            chosen.append(r)
        if len(chosen) >= 4:
            break
            
    print(f"Selected {len(chosen)} requirements for deep audit:")
    for c in chosen:
        print(f" - {c.get('req_id')} (Client: {c.get('payload', {}).get('requirement_from')}, Raw ID: {c.get('raw_req_id')})")
        
    for r in chosen:
        req_id = r.get("req_id")
        p = r.get("payload", {})
        print(f"\n=======================================================")
        print(f"AUDITING REQUIREMENT: {req_id}")
        print(f"=======================================================")
        
        # 1. Fetch rendered HTML
        url = f"http://127.0.0.1:5000/requirement/{urllib.parse.quote(req_id)}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "AuditScript/1.0"})
            with urllib.request.urlopen(req) as resp:
                html = resp.read().decode("utf-8")
        except Exception as e:
            print(f"Failed to fetch {url}: {e}")
            continue
            
        soup = BeautifulSoup(html, "html.parser")
        
        # Extract title & header items
        main_title = soup.find("h1", class_="detail-main-title")
        main_title_txt = main_title.get_text(strip=True) if main_title else "MISSING"
        
        sub_meta = soup.find("div", class_="detail-sub-meta")
        sub_meta_txt = sub_meta.get_text(" | ", strip=True) if sub_meta else "MISSING"
        
        # Extract fields in overview grid
        fields = {}
        for f in soup.find_all("div", class_="overview-field"):
            lbl_el = f.find("div", class_="field-label")
            val_el = f.find("div", class_="field-value")
            if lbl_el and val_el:
                fields[lbl_el.get_text(strip=True)] = val_el.get_text(strip=True)
                
        print(f"RENDERED MAIN TITLE: {main_title_txt}")
        print(f"RENDERED SUB META: {sub_meta_txt}")
        print(f"RENDERED FIELDS:")
        for k, v in fields.items():
            print(f"  {k}: {v}")
            
        print("\nRAW STORED PAYLOAD:")
        print(json.dumps(p, indent=2))

if __name__ == "__main__":
    main()
