import re

def parse_text_lines(body_text):
    pattern = re.compile(r"\b(\d{5,8}-\d{1,2}|\d{5,8}|RQ\d{5,8})\b", re.IGNORECASE)
    items = []
    seen = set()
    for line in body_text.splitlines():
        line_str = line.strip()
        if not line_str:
            continue
        m = pattern.search(line_str)
        if m:
            req_id = m.group(1).strip()
            if req_id in seen or re.match(r"^202\d-\d{2}-\d{2}-\d{3}$", req_id):
                continue
            parts = [p.strip() for p in re.split(r"\t+|\s{2,}", line_str) if p.strip()]
            if len(parts) >= 3:
                seen.add(req_id)
                raw_stat = parts[-1]
                title_val = parts[2] if len(parts) > 2 else ""
                loc_val = parts[3] if len(parts) > 3 else ""
                exp_val = parts[6] if len(parts) > 6 else ""
                items.append({
                    "req_id": req_id,
                    "title": title_val,
                    "location": loc_val,
                    "exp": exp_val,
                    "raw_status": raw_stat
                })
    return items

sample_text = """
Please don't work on below demands:

195414-1	9	Memory Design	Bangalore	RTO	3.50 Lakhs(Budget Flex)	6 Yrs	Any Graduation	Hold
195379-1	10	Memory Design	Bangalore	RTO	2.50 Lakhs(Budget Flex)	4 Yrs	Any Graduation	Hold
195320-1	9	RTL Coding	Bangalore(BDC6F)	RTO	3.50 Lakhs	6 Yrs	Any Graduation	Hold
195398-1	9	SoC Verification	Bangalore(BDC6F)	RTO	279067(Budget Flex)	5 Yrs	Any Graduation	Hold
174902-1	8	SoC Verification	Bangalore(BDC6F)	RTO	3.20 Lakhs(Budget Flex)	7.5 Yrs	Any Graduation	Hold
203501-1	10	Embedded C++	PAN India	RTO	2.45 Lakhs	4 Yrs	Any Graduation	Hold
203486-1	9	Embedded C++	PAN India	RTO	2.80 Lakhs(Budget Flex)	5 Yrs	Any Graduation	Hold
203489-1	10	Embedded C++	PAN India	RTO	2.45 Lakhs(Budget Flex)	4 Yrs	Any Graduation	Hold
203495-1	10	Embedded C++	PAN India	RTO	2.45 Lakhs(Budget Flex)	4 Yrs	Any Graduation	Hold

Thanks & Regards
Anusha S K
"""

res = parse_text_lines(sample_text)
print(f"Parsed {len(res)} items:")
for r in res:
    print(r)
