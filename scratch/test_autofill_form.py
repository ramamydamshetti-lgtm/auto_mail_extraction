import sys
import urllib.parse
import urllib.request
from pathlib import Path
from bs4 import BeautifulSoup

def main():
    req_id = "2026/09/21-356"
    url = f"http://127.0.0.1:5000/requirement/{urllib.parse.quote(req_id)}"
    req = urllib.request.Request(url, headers={"User-Agent": "TestAutofill/1.0"})
    with urllib.request.urlopen(req) as resp:
        html = resp.read().decode("utf-8")
        
    soup = BeautifulSoup(html, "html.parser")
    form = soup.find("form", id="editRequirementForm")
    assert form is not None, "editRequirementForm not found!"
    
    print("=" * 80)
    print(f"VERIFYING AUTO-FILL EDIT FORM FOR: {req_id}")
    print("=" * 80)
    
    form_fields = {}
    for inp in form.find_all(["input", "select", "textarea"]):
        fid = inp.get("id")
        if not fid:
            continue
        if inp.name == "select":
            selected = inp.find("option", selected=True)
            form_fields[fid] = selected.get("value", "") if selected else ""
        else:
            form_fields[fid] = inp.get("value", "")
            
    for k, v in form_fields.items():
        print(f"{k:<30}: {v}")
        
    # Assert critical fields are pre-populated correctly
    assert form_fields["form_req_id"] == "2026/09/21-356"
    assert "Senior Python Resources" in form_fields["form_job_title"]
    assert form_fields["form_requirement_from"] == "Deloitte"
    assert form_fields["form_number_of_positions"] == "2"
    assert form_fields["form_experience_level"] == "Senior Level"
    assert form_fields["form_overall_experience"] == "10-8 years"
    assert form_fields["form_monthly_budget"] == "130000"
    assert form_fields["form_yearly_budget"] == "3000000"
    assert "Python" in form_fields["form_mandatory_skills"]
    assert "PostgreSQL" in form_fields["form_skills"]
    assert form_fields["form_location"] == "Mumbai"
    assert form_fields["form_budget_currency"] == "INR"
    assert form_fields["form_job_status"] == "open"
    assert form_fields["form_priority"] == "HIGH"
    
    print("\nSUCCESS: All auto-fill form fields pre-populated accurately from extracted data!")

if __name__ == "__main__":
    main()
