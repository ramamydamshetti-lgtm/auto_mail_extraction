import re

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
Email:- anusha.k@iexcel.co.in
Phone:- 7676151765
"""

pattern = re.compile(r"(\b\d{5,7}\-\d{1,2}\b)")

lines = sample_text.splitlines()
extracted = []
for line in lines:
    m = pattern.search(line)
    if m:
        req_id = m.group(1)
        # Parse fields by splitting tab / multiple spaces
        parts = [p.strip() for p in re.split(r"\t+|\s{2,}", line) if p.strip()]
        # Or position-based parsing
        extracted.append({
            "req_id": req_id,
            "line_parts": parts,
            "full_line": line
        })

print(f"Extracted {len(extracted)} Accenture requirements:")
for item in extracted:
    print(item["req_id"], "->", item["line_parts"])
