import sqlite3
import json
from collections import Counter

def analyze_payload_fields():
    conn = sqlite3.connect('data/metaforge_requirements.db')
    c = conn.cursor()
    c.execute("SELECT job_id, payload_json FROM metaforge_requirements")
    rows = c.fetchall()
    total = len(rows)
    print(f"Total requirements: {total}")
    
    field_counts = Counter()
    populated_counts = Counter()
    all_keys = set()
    
    sample_records = []
    
    for job_id, p_json in rows:
        try:
            p = json.loads(p_json)
        except:
            continue
        all_keys.update(p.keys())
        for k, v in p.items():
            field_counts[k] += 1
            is_empty = False
            if v is None:
                is_empty = True
            elif isinstance(v, (str, list, dict)) and len(v) == 0:
                is_empty = True
            elif isinstance(v, str) and v.strip() in ("", "None", "null", "[]"):
                is_empty = True
            
            if not is_empty:
                populated_counts[k] += 1
                
        if len(sample_records) < 3:
            sample_records.append((job_id, p))

    print("\n=== PAYLOAD JSON FIELD POPULATION (Sorted by population %) ===")
    for k in sorted(all_keys):
        present = field_counts[k]
        pop = populated_counts[k]
        pct = (pop / total * 100) if total else 0
        print(f"  {k:30}: {pop:4d} / {total} populated ({pct:5.1f}%) [key present in {present}]")

    print("\n=== SAMPLE PAYLOAD RECORD ===")
    job_id, s = sample_records[0]
    print(f"Job ID: {job_id}")
    for k, v in s.items():
        if v is not None and str(v).strip() not in ("", "[]", "None"):
            val_str = str(v)
            if len(val_str) > 70:
                val_str = val_str[:67] + "..."
            print(f"  {k:28}: {val_str}")

if __name__ == '__main__':
    analyze_payload_fields()
