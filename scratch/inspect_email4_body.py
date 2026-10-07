import sys, os
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.abspath("."))
from outlook_graph import acquire_token_from_env, iter_inbox_messages
from bs4 import BeautifulSoup

token = acquire_token_from_env()
mailbox = os.environ.get("OUTLOOK_MAILBOX", "recruitment.application@metaforgeit.com")

raw_messages = list(iter_inbox_messages(token, mailbox, limit=50))
today_raw = [m for m in raw_messages if "2026-09-30" in (m.get("receivedDateTime") or "")]

print(f"=== Today's Emails ({len(today_raw)}) ===")

for idx, m in enumerate(today_raw, 1):
    subj = m.get("subject") or ""
    from_obj = m.get("from") or {}
    ea = from_obj.get("emailAddress") or {} if isinstance(from_obj, dict) else {}
    from_email = (ea.get("address") or "").strip()
    recv_dt = m.get("receivedDateTime") or ""
    
    print(f"\n[{idx}] {recv_dt} | From: {from_email}")
    print(f"    Subject: {subj}")
    
    body_dict = m.get("body") or {}
    content = body_dict.get("content") or ""
    
    # If HTML, extract text or table rows
    if content:
        soup = BeautifulSoup(content, "html.parser")
        tables = soup.find_all("table")
        print(f"    Tables found: {len(tables)}")
        for t_idx, tbl in enumerate(tables, 1):
            rows = tbl.find_all("tr")
            print(f"    Table #{t_idx} has {len(rows)} rows:")
            for r in rows[:15]:  # print first 15 rows
                cols = [c.get_text(strip=True) for c in r.find_all(["td", "th"])]
                if any(cols):
                    print(f"      {cols}")
