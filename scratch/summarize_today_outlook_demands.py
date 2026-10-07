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

print(f"=== LIVE OUTLOOK INBOX AUDIT FOR TODAY (2026-09-30) ===")
print(f"Total Emails Received in Outlook Inbox Today: {len(today_raw)}\n")

for idx, m in enumerate(today_raw, 1):
    subj = m.get("subject") or "No Subject"
    from_obj = m.get("from") or {}
    ea = from_obj.get("emailAddress") or {} if isinstance(from_obj, dict) else {}
    from_email = (ea.get("address") or "Unknown").strip()
    from_name = (ea.get("name") or "Unknown").strip()
    recv_dt = m.get("receivedDateTime") or ""
    
    print(f"Email #{idx}:")
    print(f"  Received : {recv_dt}")
    print(f"  From     : {from_name} <{from_email}>")
    print(f"  Subject  : {subj}")
    
    body_dict = m.get("body") or {}
    content = body_dict.get("content") or ""
    
    if content:
        soup = BeautifulSoup(content, "html.parser")
        tables = soup.find_all("table")
        if tables:
            first_tbl = tables[0]
            rows = first_tbl.find_all("tr")
            demands = []
            headers = [c.get_text(strip=True) for c in rows[0].find_all(["td", "th"])]
            for r in rows[1:]:
                cols = [c.get_text(strip=True) for c in r.find_all(["td", "th"])]
                if len(cols) >= 3:
                    demands.append(cols)
            if demands:
                print(f"  --> Contains Accenture Demands Table ({len(demands)} rows):")
                print(f"      Headers: {headers[:8]}")
                for d_i, d in enumerate(demands, 1):
                    # Try to pick req_id, title, location, exp, budget
                    req_id = d[0] if len(d) > 0 else "N/A"
                    title = d[1] if len(d) > 1 else "N/A"
                    exp = d[2] if len(d) > 2 else "N/A"
                    loc = d[3] if len(d) > 3 else "N/A"
                    budget = d[4] if len(d) > 4 else "N/A"
                    print(f"      {d_i}. [{req_id}] Title: {title} | Exp: {exp} | Loc: {loc} | Budget: {budget}")
    print()
