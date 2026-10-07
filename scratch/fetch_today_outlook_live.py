import sys, os
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.abspath("."))
from outlook_graph import acquire_token_from_env, iter_inbox_messages

print("======================================================================")
print("FETCHING LIVE OUTLOOK INBOX FOR TODAY (2026-09-30)")
print("======================================================================")

target_date = "2026-09-30"

try:
    token = acquire_token_from_env()
    print("Azure AD Graph Token: OK\n")
    
    mailbox = os.environ.get("OUTLOOK_MAILBOX", "recruitment.application@metaforgeit.com")
    print(f"Mailbox: {mailbox}")
    
    # Fetch top 100 messages from inbox
    messages = list(iter_inbox_messages(token, mailbox, limit=100))
    print(f"Fetched {len(messages)} recent messages from Inbox.\n")
    
    today_msgs = []
    for m in messages:
        recv_dt = m.get("receivedDateTime") or ""
        if target_date in recv_dt or "2026-09-30" in recv_dt:
            today_msgs.append(m)
            
    print(f"=== Messages Received Today ({target_date}) in Outlook: {len(today_msgs)} ===")
    for idx, msg in enumerate(today_msgs, 1):
        subj = msg.get("subject") or "No Subject"
        from_obj = msg.get("from") or {}
        ea = from_obj.get("emailAddress") or {}
        from_email = ea.get("address") or "Unknown"
        recv_dt = msg.get("receivedDateTime") or "Unknown"
        print(f"{idx}. Received: {recv_dt} | From: {from_email}")
        print(f"   Subject: {subj}")
        print()

    if len(messages) > 0 and len(today_msgs) == 0:
        print("Most recent 5 emails in Inbox:")
        for idx, msg in enumerate(messages[:5], 1):
            subj = msg.get("subject") or "No Subject"
            from_obj = msg.get("from") or {}
            ea = from_obj.get("emailAddress") or {}
            from_email = ea.get("address") or "Unknown"
            recv_dt = msg.get("receivedDateTime") or "Unknown"
            print(f"  {idx}. Received: {recv_dt} | From: {from_email} | Subject: {subj[:60]}")

except Exception as err:
    print(f"Error checking live Outlook Graph API: {err}")
