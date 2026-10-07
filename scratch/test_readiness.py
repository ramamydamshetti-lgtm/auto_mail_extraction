import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from config import Settings
from main import extract_and_map
from field_mapper import check_ui_readiness
from metaforge_api import IdAllocator
import json

settings = Settings.from_env()
allocator = IdAllocator('data/metaforge_requirements.db')
msg = {
    'id': 'MSG-ACCENTURE-203483',
    'conversationId': 'CONV-ACCENTURE-203483',
    'subject': "Don't work on below requirement",
    'from': {'emailAddress': {'address': 'anusha.k@iexcel.co.in', 'name': 'Anusha K'}},
    'toRecipients': [{'emailAddress': {'address': 'hiring@iexcel.co.in', 'name': 'Hiring'}}],
    'ccRecipients': [{'emailAddress': {'address': 'rkarnam@metaforgeit.com', 'name': 'Raghu Karnam'}}],
    'receivedDateTime': '2026-09-30T10:00:00Z',
    'hasAttachments': False,
    'body': {
        'contentType': 'html',
        'content': "<p>Hi Team,</p><p>Don't work on below requirement.</p><table><tr><th>Req ID</th><th>Grade</th><th>Skill</th><th>Location</th><th>Work Mode</th><th>Budget</th><th>Exp</th><th>Education</th><th>Status</th></tr><tr><td>203483-1</td><td>Grade 9</td><td>Salesforce Omnistudio Platform</td><td>Bangalore(BDC-7)</td><td>RTO</td><td>2.79 Lakhs</td><td>5 Yrs</td><td>Any Graduation</td><td>Hold</td></tr></table>"
    }
}

status, payloads, body = extract_and_map(msg, token='TOKEN', mailbox='box', settings=settings, allocator=allocator)
for p in payloads:
    print(json.dumps(p, indent=2))
    print("READINESS:", check_ui_readiness(p))
