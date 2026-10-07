import sys
sys.path.insert(0, '.')
from requirement_parser import extract_client_jd_id_from_text

subj = "New Requirement - Control & Monitoring RQ056293 (Prasad's Team)"
body = """Work Location: Delhi
Office Model: 3 days work from Office
Monthly Bill Rate:
150000 - 200000
D.client
Please share the profiles on priority on this table format along with the CVs.
Sl. No
Vendor
Applicant Name
Skill
Mobile no
Email ID
Applicant Location
Preferred Location
Current Org
Total Exp
Relevant Exp
Notice Period
Monthly Billing Rates
- Job Posting ID -
DLTJP00062540
Regards,
Rahul Saha"""

print("Extracted ID:", extract_client_jd_id_from_text(subj, body))
