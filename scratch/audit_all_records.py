import sqlite3
import json
import re

def audit():
    conn = sqlite3.connect('file:data/metaforge_requirements.db?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM metaforge_requirements").fetchall()
    
    print(f"Total rows to audit: {len(rows)}")
    
    field_stats = {}
    
    for r in rows:
        p = json.loads(r['payload_json'])
        for k, v in p.items():
            if k in ('bodyText', 'bodyHtml', 'body'):
                continue
            if k not in field_stats:
                field_stats[k] = {'populated': 0, 'none_or_empty': 0, 'sample_values': set()}
            if v is not None and v != '' and v != []:
                field_stats[k]['populated'] += 1
                if len(field_stats[k]['sample_values']) < 3:
                    field_stats[k]['sample_values'].add(str(v)[:40])
            else:
                field_stats[k]['none_or_empty'] += 1
                
    print("\nFIELD STATISTICS:")
    for k in sorted(field_stats.keys()):
        stats = field_stats[k]
        samples = list(stats['sample_values'])
        print(f"  {k:25s}: {stats['populated']:3d} populated, {stats['none_or_empty']:3d} empty | Samples: {samples[:2]}")
        
    conn.close()

if __name__ == '__main__':
    audit()
