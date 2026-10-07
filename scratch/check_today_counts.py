import sqlite3
import json
from datetime import datetime, timezone, timedelta

ist_tz = timezone(timedelta(hours=5, minutes=30))

for db_path in ['data/metaforge_requirements.db', 'data/processed_messages.db']:
    try:
        conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
        conn.row_factory = sqlite3.Row
        
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        print(f"=== DB: {db_path} ===")
        for tbl in tables:
            rows = conn.execute(f"SELECT * FROM {tbl}").fetchall()
            print(f"  Table: {tbl} ({len(rows)} rows)")
            
            # Count by dates
            dates_count = {}
            for r in rows:
                keys = r.keys()
                # look for date or payload
                dt_str = ""
                if 'created_at' in keys and r['created_at']:
                    dt_str = str(r['created_at'])
                elif 'received_date_time' in keys and r['received_date_time']:
                    dt_str = str(r['received_date_time'])
                elif 'payload_json' in keys:
                    try:
                        p = json.loads(r['payload_json'])
                        dt_str = p.get('receivedDateTime') or p.get('demand_received_date') or ""
                    except Exception:
                        pass
                        
                date_part = dt_str[:10] if len(dt_str) >= 10 else "Unknown"
                dates_count[date_part] = dates_count.get(date_part, 0) + 1
                
            sorted_dates = sorted(dates_count.items(), reverse=True)
            for d, c in sorted_dates[:6]:
                print(f"    {d}: {c} records")
        conn.close()
    except Exception as e:
        print(f"Error checking {db_path}: {e}")
