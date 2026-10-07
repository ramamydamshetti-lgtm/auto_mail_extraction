import json
import sqlite3

def main():
    for db_path in ['data/metaforge_requirements.db', 'data/processed_messages.db']:
        conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
        conn.row_factory = sqlite3.Row
        for tbl in ['metaforge_requirements', 'client_requirements', 'pending_reviews', 'requirement_memory']:
            try:
                rows = conn.execute(f"SELECT * FROM {tbl} WHERE payload_json LIKE '%RQ056293%'").fetchall()
                for r in rows:
                    print(f"==================================================")
                    print(f"DB: {db_path} | Table: {tbl}")
                    print(f"==================================================")
                    for k in r.keys():
                        if k != 'payload_json':
                            print(f"{k}: {r[k]}")
                    p = json.loads(r['payload_json'])
                    print("\nPAYLOAD EXTRACTED FIELDS:")
                    for k in sorted(p.keys()):
                        if k not in ('bodyText', 'bodyHtml', 'body'):
                            print(f"  {k}: {p.get(k)}")
                    print("\nRAW EMAIL SUBJECT:", p.get('subject'))
                    print("\nRAW EMAIL BODY (first 2500 chars):")
                    body = p.get('bodyText') or p.get('body') or ""
                    print(body[:2500])
                    print("\n")
            except Exception as e:
                print(f"Error checking {tbl} in {db_path}: {e}")
        conn.close()

if __name__ == "__main__":
    main()
