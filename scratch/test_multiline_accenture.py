import sqlite3
import json
import re

def extract_accenture_requirements_from_body(body_text):
    lines = [l.strip() for l in body_text.splitlines() if l.strip()]
    items = []
    seen_ids = set()

    for idx, line in enumerate(lines):
        m = re.match(r"^(\d{5,7}-\d{1,2}|20\d{5}-\d|19\d{5}-\d|17\d{5}-\d)$", line)
        if m:
            cid = m.group(1)
            if cid in seen_ids or re.match(r"^202\d-\d{2}-\d{2}-\d{3}$", cid):
                continue

            window = lines[idx+1 : idx+10]
            title = ""
            loc = ""
            exp = ""
            budget = ""
            status = "open"

            for w in window:
                wl = w.lower()
                # Stop if next line is another req ID
                if re.match(r"^(\d{5,7}-\d{1,2})$", w):
                    break
                if not title and len(w) >= 3 and not w.isdigit() and "rto" not in wl and "graduation" not in wl and "lakhs" not in wl and "yrs" not in wl and "hold" not in wl and "open" not in wl and "p1" not in wl and "p2" not in wl:
                    title = w
                elif any(city in wl for city in ["bangalore", "mumbai", "pan india", "hyderabad", "pune", "chennai", "gurgaon", "noida", "kolkata", "delhi", "bdc"]) and not loc:
                    loc = w
                elif ("yrs" in wl or "year" in wl or "exp" in wl) and not exp:
                    exp = w
                elif ("lakh" in wl or "budget" in wl) and not budget:
                    budget = w
                elif wl in ("hold", "open", "reopen", "p1", "p2", "closed"):
                    status = "hold" if "hold" in wl else ("open" if wl in ("open", "p1", "p2") else wl)

            seen_ids.add(cid)
            items.append({
                "client_jd_id": cid,
                "job_title": title or "Accenture Requirement",
                "location": loc,
                "experience": exp,
                "budget": budget,
                "job_status": status
            })

    return items

conn = sqlite3.connect(r'data\processed_messages.db')
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT * FROM pending_reviews WHERE payload_json LIKE '%anusha.k@iexcel.co.in%'").fetchall()

print(f"Analyzing {len(rows)} Accenture email records from pending_reviews:")
all_extracted = []
for r in rows:
    p = json.loads(r['payload_json'])
    body = p.get('bodyText') or p.get('body') or p.get('email_body') or ""
    subj = p.get('subject') or p.get('email_subject') or ""
    items = extract_accenture_requirements_from_body(body)
    print(f"\nEmail: '{subj}' -> Extracted {len(items)} Accenture requirements:")
    for item in items:
        print(" ", item["client_jd_id"], "|", item["job_title"], "|", item["location"], "|", item["experience"], "| Status:", item["job_status"])
        all_extracted.append(item)

print(f"\nTOTAL Accenture requirements extracted across all emails: {len(all_extracted)}")
