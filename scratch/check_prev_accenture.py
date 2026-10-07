import sys, os
sys.path.insert(0, r"g:\Auto_email_extraction (3)-new\Auto_email_extraction")
from dotenv import load_dotenv
load_dotenv(r"g:\Auto_email_extraction (3)-new\Auto_email_extraction\.env")
from outlook_graph import acquire_token_from_env, iter_inbox_messages
from bs4 import BeautifulSoup
import re

token = acquire_token_from_env()
messages = list(iter_inbox_messages(token, "recruitment.application@metaforgeit.com", limit=10))

for m in messages:
    subj = m.get("subject") or ""
    rec = m.get("receivedDateTime") or ""
    if "accenture" in subj.lower():
        print(f"Found Accenture email: Date={rec} | Subj={subj}")
        # Let's extract Request-IDs from this email
        body = m.get("body", {}).get("content", "")
        req_ids = re.findall(r"\b\d{5,8}-\d+\b", body)
        print(f"  Total Req IDs found: {len(set(req_ids))}")
        print(f"  Is 200964-1 in it? {'200964-1' in req_ids}")
