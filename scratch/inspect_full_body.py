import json
import sqlite3

def main():
    conn = sqlite3.connect('file:data/metaforge_requirements.db?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM metaforge_requirements WHERE payload_json LIKE '%RQ056293%'").fetchall()
    for r in rows:
        p = json.loads(r['payload_json'])
        print("=== PROVENANCE ===")
        print(json.dumps(p.get('_provenance'), indent=2))
        print("=== FULL BODYTEXT ===")
        body = p.get('bodyText') or ""
        print(body)
        print("=== END BODYTEXT ===")
    conn.close()

if __name__ == "__main__":
    main()
