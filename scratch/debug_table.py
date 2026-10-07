import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bs4 import BeautifulSoup
from requirement_parser import extract_req_id_table_requirements

body = "<p>Hi Team,</p><p>Don't work on below requirement.</p><table><tr><th>Req ID</th><th>Grade</th><th>Skill</th><th>Location</th><th>Work Mode</th><th>Budget</th><th>Exp</th><th>Education</th><th>Status</th></tr><tr><td>203483-1</td><td>Grade 9</td><td>Salesforce Omnistudio Platform</td><td>Bangalore(BDC-7)</td><td>RTO</td><td>2.79 Lakhs</td><td>5 Yrs</td><td>Any Graduation</td><td>Hold</td></tr></table>"

items = extract_req_id_table_requirements(body=body, subject="Don't work on below requirement", from_email="anusha.k@iexcel.co.in")
print("Items count:", len(items))
for it in items:
    print(it.model_dump())
