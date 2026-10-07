import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import json
from email_filter import is_sender_allowlisted, has_requirement_structure, apply_email_filter
from intake_gates import pre_classify_block_reason, is_status_or_tracker_report
from client_detector import detect_client
from status_tracker import evaluate_status_short_circuit, detect_status_keyword
from requirement_classifier import classify_email, heuristic_obvious_client_requirement
from processed_store import ProcessedStore
from config import Settings

subject = "Don't work on below requirement"
from_email = "anusha.k@iexcel.co.in"
body = """Hi Team,

Don't work on below requirement.

Req ID | Grade | Skill | Location | Work Mode | Budget | Exp | Education | Status
203483-1 | Grade 9 | Salesforce Omnistudio Platform | Bangalore(BDC-7) | RTO | 2.79 Lakhs | 5 Yrs | Any Graduation | Hold
"""

print("=== STEP 0 DIAGNOSIS ===")
print("1. Sender allowlist check:")
allowlisted = is_sender_allowlisted(from_email)
print("   is_sender_allowlisted:", allowlisted)

print("\n2. Client detection:")
client = detect_client(subject, body, from_email)
print("   Detected client:", client.display_name if client else None)

print("\n3. Intake gate pre-classify block check:")
block_reason = pre_classify_block_reason(from_email, subject, body)
print("   pre_classify_block_reason:", block_reason)
print("   is_status_or_tracker_report:", is_status_or_tracker_report(subject, body))

print("\n4. Requirement structure check:")
struct_pass = has_requirement_structure(body)
print("   has_requirement_structure:", struct_pass)

print("\n5. Email filter check:")
filter_res = apply_email_filter(from_email, body)
print("   apply_email_filter allowed:", filter_res.allowed, "reason:", filter_res.reason)

print("\n6. Status short-circuit evaluation:")
with ProcessedStore("data/processed_messages.db") as store:
    status_act, target_id = evaluate_status_short_circuit(
        subject=subject,
        body=body,
        conversation_id="TEST-CONV-203483",
        graph_id="TEST-GRAPH-203483",
        store=store,
        from_email=from_email,
    )
print("   detected_status_keyword:", detect_status_keyword(subject, body))
print("   evaluate_status_short_circuit action:", status_act, "target_id:", target_id)

print("\n7. AI Classifier evaluation:")
settings = Settings.from_env()
heuristic_pass = heuristic_obvious_client_requirement(subject, body)
print("   heuristic_obvious_client_requirement:", heuristic_pass)
cls_res = classify_email(body, subject=subject, settings=settings, from_email=from_email)
print("   classify_email result label:", cls_res.label, "confidence:", cls_res.confidence)
