import sys, os
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.abspath("."))
from outlook_graph import acquire_token_from_env, iter_inbox_messages

print("======================================================================")
print("TESTING LIVE OUTLOOK GRAPH INBOX FETCH (recruitment.application@metaforgeit.com)")
print("======================================================================")

try:
    token = acquire_token_from_env()
    print("Azure AD Graph Authentication: SUCCESSful Token Acquisition\n")
    
    messages = list(iter_inbox_messages(token, "recruitment.application@metaforgeit.com", limit=5))
    print(f"Directly fetched {len(messages)} live email(s) from Outlook inbox:\n")
    
    for idx, msg in enumerate(messages, 1):
        subj = msg.get("subject") or "No Subject"
        from_obj = msg.get("from") or {}
        ea = from_obj.get("emailAddress") or {}
        from_email = ea.get("address") or "Unknown"
        recv_dt = msg.get("receivedDateTime") or "Unknown"
        
        print(f"{idx}. Subject : {subj[:70]}")
        print(f"   From    : {from_email}")
        print(f"   Received: {recv_dt}")
        print()

except Exception as err:
    print(f"Error fetching live Outlook emails: {err}")
