import sqlite3
import json

conn = sqlite3.connect('file:data/processed_messages.db?mode=ro', uri=True)
gid = "AAMkADE3NDllMmZlLTU3NmUtNGI2MS1hZjA4LTEwNzAzZWZjYzUxOABGAAAAAABG8jimhHIeTrzzeDCLnQR9BwAIHnK_cnn0TIdFuplFGEzAAAAAAAEMAAAIHnK_cnn0TIdFuplFGEzAAAB9pNT0AAA="
r = conn.execute("SELECT payload_json FROM requirement_memory WHERE source_graph_id = ? LIMIT 1", (gid,)).fetchone()
if r:
    p = json.loads(r[0])
    print("subject:", p.get("subject"))
    print("from:", p.get("from"))
    print("receivedDateTime:", p.get("receivedDateTime"))
    print("demand_received_date:", p.get("demand_received_date"))
    print("prov:", p.get("_provenance"))
    # Check body text preview
    b = p.get("bodyText") or ""
    print("bodyText length:", len(b))
    print("body preview:\n", b[:300])

conn.close()
