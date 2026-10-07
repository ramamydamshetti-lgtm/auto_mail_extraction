import json, re, pandas as pd

df = pd.read_csv('latest_500_all.csv')
pattern = re.compile(r"\b(hold|on\s+hold|closed?|reopen|re-open|resume\s+sourcing|resume\s+requirement|don't\s+work|dont\s+work|stop\s+sourcing|pause)\b", re.I)

status_rows = []
for idx, row in df.iterrows():
    subj = str(row.get('subject') or '')
    body = str(row.get('body_normalized') or row.get('body_plain') or '')
    text = f"{subj}\n{body}"
    if pattern.search(text):
        status_rows.append(row)

print(f"Total emails in latest_500_all.csv containing lifecycle status words: {len(status_rows)}")

for row in status_rows:
    subj = str(row.get('subject') or '').encode('ascii', 'ignore').decode('ascii')
    sender = str(row.get('from_email') or '')
    b = str(row.get('body_normalized') or '')
    m = pattern.findall(f"{subj}\n{b}")
    
    req_json_str = str(row.get('requirement_json') or '')
    has_extracted = False
    if req_json_str and req_json_str != '{}':
        try:
            rj = json.loads(req_json_str)
            if rj.get('locations') or rj.get('summary') or rj.get('key_points'):
                has_extracted = True
        except Exception:
            pass

    outcome = "CREATED/EXTRACTED" if has_extracted else "DROPPED/NO_RECORD"
    print(f"- [{outcome}] Sender: {sender} | Subject: {subj[:70]} | Matches: {set(m)}")
