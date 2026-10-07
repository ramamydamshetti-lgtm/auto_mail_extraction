import json
from email_filter import validate_email_access

test_emails = [
    "rkarnam@metaforgeit.com",
    "rahima.s@metaforgeit.com",
    "anusha.k@iexcel.co.in",
    "test@idexcel.com",
    "hr@kpmg.com",
    "divya@itcinfotech.com",
    "kallol@ltts.com",
    "subdomain@mail.kpmg.com",
    "spoof@kpmg.co",
    "accenture@accenture.com",
    "invalid-email-string"
]

print("=== EMAIL ACCESS CONTROL VALIDATION RESULTS ===")
for e in test_emails:
    res = validate_email_access(e)
    print(json.dumps(res, indent=2))
