import sys, os
import json
import sqlite3
from bs4 import BeautifulSoup
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.abspath("."))
from outlook_graph import acquire_token_from_env, iter_inbox_messages

token = acquire_token_from_env()
mailbox = os.environ.get("OUTLOOK_MAILBOX", "recruitment.application@metaforgeit.com")

# 1. Fetch live Outlook email for Accenture today
raw_messages = list(iter_inbox_messages(token, mailbox, limit=50))
accenture_today_msgs = [
    m for m in raw_messages 
    if "2026-09-30" in (m.get("receivedDateTime") or "")
    and ("accenture" in (m.get("subject") or "").lower() or "iexcel.co.in" in str(m.get("from") or "").lower())
]

print("=== VERIFICATION OF TODAY'S ACCENTURE REQUIREMENTS ===")
print(f"Total Accenture Emails Received Today (2026-09-30): {len(accenture_today_msgs)}")

accenture_req_list = []

for m in accenture_today_msgs:
    subj = m.get("subject") or ""
    recv_dt = m.get("receivedDateTime") or ""
    body_dict = m.get("body") or {}
    content = body_dict.get("content") or ""
    if content and "Accenture open demands" in subj:
        soup = BeautifulSoup(content, "html.parser")
        tables = soup.find_all("table")
        if tables:
            first_tbl = tables[0]
            rows = first_tbl.find_all("tr")
            for r in rows[1:]:
                cols = [c.get_text(strip=True) for c in r.find_all(["td", "th"])]
                if len(cols) >= 3 and cols[0].replace("-","").replace("1","").isdigit():
                    accenture_req_list.append({
                        "req_id": cols[0],
                        "grade": cols[1] if len(cols)>1 else "",
                        "skill": cols[2] if len(cols)>2 else "",
                        "location": cols[3] if len(cols)>3 else "",
                        "mode": cols[4] if len(cols)>4 else "",
                        "budget": cols[5] if len(cols)>5 else "",
                        "exp": cols[6] if len(cols)>6 else "",
                        "education": cols[7] if len(cols)>7 else ""
                    })

print(f"\nTotal Verified Accenture Requirements from Live Outlook Broadcast Email: {len(accenture_req_list)}")
print("\nFirst 5 Accenture Requirements:")
for idx, r in enumerate(accenture_req_list[:5], 1):
    print(f"  {idx}. [{r['req_id']}] {r['skill']} | Location: {r['location']} | Exp: {r['exp']} | Budget: {r['budget']}")

print(f"\nLast 5 Accenture Requirements:")
for idx, r in enumerate(accenture_req_list[-5:], len(accenture_req_list)-4):
    print(f"  {idx}. [{r['req_id']}] {r['skill']} | Location: {r['location']} | Exp: {r['exp']} | Budget: {r['budget']}")
