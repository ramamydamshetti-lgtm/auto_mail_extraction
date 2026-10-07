import json

with open('Auto_email_extraction/scratch/audit_results_15.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print(f"Total requirements loaded: {len(data)}")

# Let's inspect each requirement's exact values for all 13 fields
matrix = []
for req_id, r in data.items():
    parsed = r.get("parsed_item") or {}
    mapped = r.get("mapped") or {}
    val = r.get("validated") or {}
    db = r.get("db") or {}
    ui = r.get("ui") or {}
    
    # Extract source facts from snippet
    body = r.get("source_text_snippet", "")
    
    entry = {
        "req_id": req_id,
        "client": r.get("client"),
        "cjd": r.get("cjd"),
        "fields": {
            "job_title": {
                "source": db.get("job_title"),
                "llm": parsed.get("job_title"),
                "mapped": mapped.get("job_title"),
                "validated": val.get("job_title"),
                "db": db.get("job_title"),
                "ui": ui.get("job_title")
            },
            "location": {
                "source": "See text",
                "llm": parsed.get("location"),
                "mapped": mapped.get("location"),
                "validated": val.get("location"),
                "db": db.get("location"),
                "ui": ui.get("location")
            },
            "mandatory_skills": {
                "llm": parsed.get("mandatory_skills"),
                "mapped": mapped.get("mandatory_skills"),
                "validated": val.get("mandatory_skills"),
                "db": db.get("mandatory_skills"),
                "ui": ui.get("mandatory_skills")
            },
            "skills": {
                "llm": parsed.get("soft_skills"),
                "mapped": mapped.get("skills"),
                "validated": val.get("skills"),
                "db": db.get("skills"),
                "ui": ui.get("skills")
            },
            "experience": {
                "llm": parsed.get("experience_text"),
                "mapped": mapped.get("overall_experience"),
                "validated": val.get("overall_experience"),
                "db": db.get("overall_experience"),
                "ui": ui.get("overall_experience") or ui.get("experience")
            },
            "number_of_positions": {
                "llm": parsed.get("number_of_positions"),
                "mapped": mapped.get("number_of_positions"),
                "validated": val.get("number_of_positions"),
                "db": db.get("number_of_positions"),
                "ui": ui.get("number_of_positions")
            },
            "notice_period": {
                "llm": parsed.get("notice_period"),
                "mapped": mapped.get("notice_period"),
                "validated": val.get("notice_period"),
                "db": db.get("notice_period"),
                "ui": ui.get("notice_period")
            },
            "work_mode": {
                "llm": parsed.get("work_mode"),
                "mapped": mapped.get("work_mode"),
                "validated": val.get("work_mode"),
                "db": db.get("work_mode"),
                "ui": ui.get("work_mode")
            },
            "monthly_budget": {
                "llm": parsed.get("monthly_budget"),
                "mapped": mapped.get("monthly_budget"),
                "validated": val.get("monthly_budget"),
                "db": db.get("monthly_budget"),
                "ui": ui.get("monthly_budget")
            },
            "yearly_budget": {
                "llm": parsed.get("yearly_budget_max") or parsed.get("yearly_budget_min"),
                "mapped": mapped.get("yearly_budget"),
                "validated": val.get("yearly_budget"),
                "db": db.get("yearly_budget"),
                "ui": ui.get("yearly_budget")
            },
            "tiered_budget": {
                "llm": parsed.get("budget_text"),
                "mapped": mapped.get("budget_text"),
                "validated": val.get("budget_text"),
                "db": db.get("budget_text"),
                "ui": ui.get("budget_text")
            },
            "employment_type": {
                "llm": parsed.get("employment_type"),
                "mapped": mapped.get("employment_type"),
                "validated": val.get("employment_type"),
                "db": db.get("employment_type"),
                "ui": ui.get("employment_type")
            },
            "client_jd_id": {
                "llm": parsed.get("req_id") or parsed.get("client_jd_id"),
                "mapped": mapped.get("client_jd_id"),
                "validated": val.get("client_jd_id"),
                "db": db.get("client_jd_id"),
                "ui": ui.get("client_jd_id")
            }
        }
    }
    matrix.append(entry)

with open('Auto_email_extraction/scratch/matrix_15.json', 'w', encoding='utf-8') as f:
    json.dump(matrix, f, indent=2, ensure_ascii=False)

print("Saved matrix_15.json successfully.")
