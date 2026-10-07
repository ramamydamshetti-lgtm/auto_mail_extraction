import sqlite3
import json
from bs4 import BeautifulSoup

conn = sqlite3.connect('file:data/processed_messages.db?mode=ro', uri=True)
gid = "AAMkADE3NDllMmZlLTU3NmUtNGI2MS1hZjA4LTEwNzAzZWZjYzUxOABGAAAAAABG8jimhHIeTrzzeDCLnQR9BwAIHnK_cnn0TIdFuplFGEzAAAAAAAEMAAAIHnK_cnn0TIdFuplFGEzAAAB9pNT0AAA="
r = conn.execute("SELECT payload_json FROM requirement_memory WHERE source_graph_id = ? LIMIT 1", (gid,)).fetchone()
p = json.loads(r[0])
html = p.get("bodyHtml") or ""
soup = BeautifulSoup(html, "html.parser")
tables = soup.find_all("table")
print(f"Total HTML tables: {len(tables)}")
for i, t in enumerate(tables):
    rows = t.find_all("tr")
    print(f"Table {i}: {len(rows)} rows")
    if len(rows) > 10:
        # Print header
        hdr = [c.get_text(strip=True) for c in rows[0].find_all(["th", "td"])]
        print("Header:", hdr)
        client_ids = []
        for row in rows[1:]:
            cells = [c.get_text(strip=True) for c in row.find_all(["th", "td"])]
            if cells:
                client_ids.append(cells[0])
        print(f"Total client IDs found in table: {len(client_ids)}")
        print("Client IDs:", client_ids)

conn.close()
