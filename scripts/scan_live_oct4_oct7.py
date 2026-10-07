import os
import sys
import json
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, ".")
from outlook_graph import acquire_token_from_env, iter_inbox_messages

def main():
    token = acquire_token_from_env()
    mailbox = os.getenv("MAILBOX_UPN", "recruitment.application@metaforgeit.com").strip()

    print("Scanning live inbox for Oct 4-7, 2026...")
    msgs_by_date = {"2026-10-04": [], "2026-10-05": [], "2026-10-06": [], "2026-10-07": []}
    other_msgs = []

    for raw in iter_inbox_messages(token, mailbox, min_received_time="2026-10-04T00:00:00Z", limit=300):
        rdt = str(raw.get("receivedDateTime") or "")
        d = rdt[:10]
        ea = str(((raw.get("from") or {}).get("emailAddress") or {}).get("address") or "")
        subj = str(raw.get("subject") or "")
        gid = str(raw.get("id") or "")
        item = {"time": rdt, "from": ea, "subj": subj, "id": gid}
        if d in msgs_by_date:
            msgs_by_date[d].append(item)
        else:
            other_msgs.append(item)

    for d, msgs in sorted(msgs_by_date.items()):
        print(f"=== Date {d}: {len(msgs)} messages ===")
        for m in msgs:
            print(f"  [{m['time']}] From: {m['from']} | Subj: {m['subj'][:70]}")
    if other_msgs:
        print(f"=== Other dates: {len(other_msgs)} messages ===")

if __name__ == "__main__":
    main()
