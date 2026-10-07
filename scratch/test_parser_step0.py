import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()
from config import Settings
from requirement_parser import parse_requirements_from_email

settings = Settings.from_env()
subject = "Don't work on below requirement"
from_email = "anusha.k@iexcel.co.in"
body = """Hi Team,

Don't work on below requirement.

Req ID | Grade | Skill | Location | Work Mode | Budget | Exp | Education | Status
203483-1 | Grade 9 | Salesforce Omnistudio Platform | Bangalore(BDC-7) | RTO | 2.79 Lakhs | 5 Yrs | Any Graduation | Hold
"""

res = parse_requirements_from_email(subject=subject, body=body, settings=settings, from_email=from_email)
print('Parsed count:', len(res.requirements))
for r in res.requirements:
    print(r.model_dump())
