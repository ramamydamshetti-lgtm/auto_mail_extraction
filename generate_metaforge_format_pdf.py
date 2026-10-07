#!/usr/bin/env python3
"""
Generate PDF report in the exact MetaForge Requirement Mapping format
"""

import json
from datetime import datetime, date
from pathlib import Path
from fpdf import FPDF

def _latin(s: str) -> str:
    return (s or "").encode("latin-1", errors="replace").decode("latin-1")

def generate_metaforge_format_pdf(input_json: str, output_pdf: str):
    """
    Generate PDF in the exact MetaForge format specified by the user
    """
    # Load the data
    with open(input_json, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # Create PDF
    pdf = FPDF()
    pdf.add_page()
    
    # Header
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, _latin("MetaForge Requirement Mapping Demo"), ln=1)
    
    pdf.set_font("Arial", "", 12)
    pdf.cell(0, 7, _latin("Mailbox: recruitment.application@metaforgeit.com"), ln=1)
    
    # Get date from data or use today
    report_date = data.get('date', date.today().strftime('%Y-%m-%d'))
    pdf.cell(0, 7, _latin(f"Date: {report_date}"), ln=1)
    pdf.cell(0, 7, _latin(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"), ln=1)
    
    # Count mapped requirements
    if isinstance(data, dict) and 'emails' in data:
        mapped_count = len(data['emails'])
    elif isinstance(data, list):
        mapped_count = len(data)
    else:
        mapped_count = 1
    
    pdf.cell(0, 7, _latin(f"Mapped requirements: {mapped_count}"), ln=1)
    pdf.ln(10)
    
    # Process each requirement
    requirements = []
    
    if isinstance(data, dict) and 'emails' in data:
        # Format from today_client_emails_exhaustive format
        for i, email in enumerate(data['emails'], 1):
            req = {
                "job_id": f"REQ-{report_date}-{i:03d}",
                "demand_received_date": report_date,
                "internal_poc": "offshore demands",
                "requirement_from": email.get('source_vendor_key', 'Unknown').upper(),
                "client_jd_id": f"{email.get('source_vendor_key', 'Unknown').upper()}-{report_date}-{i:03d}",
                "client_lead_poc": email.get('from_email', ''),
                "client_poc": email.get('from_email', ''),
                "job_title": email.get('job_title', ''),
                "job_status": "Open",
                "closed_date": "N/A",
                "type_of_demand": "Single",
                "priority": "High",
                "number_of_positions": 1,
                "experience_level": "Mid Senior",
                "employment_type": "Contract",
                "budget_currency": "INR",
                "yearly_budget": "Not provided",
                "monthly_budget": "Not provided",
                "work_mode": "On-site",
                "location": email.get('location', [''])[0] if email.get('location') else '',
                "overall_experience": email.get('experience', ''),
                "notice_period": email.get('notice_period', ''),
                "mandatory_skills": "; ".join(email.get('skills', [])) if email.get('skills') else "Not provided",
                "skills": "; ".join(email.get('skills', [])) if email.get('skills') else "Not provided"
            }
            requirements.append(req)
    
    elif isinstance(data, list):
        # Direct list of requirements
        requirements = data
    
    # Output each requirement in the exact format
    for i, req in enumerate(requirements, 1):
        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 8, _latin(f"Requirement {i}"), ln=1)
        
        pdf.set_font("Arial", "", 10)
        
        # Format each field exactly as specified
        fields = [
            ("Job Id", req.get('job_id', '')),
            ("Demand Received Date", req.get('demand_received_date', '')),
            ("Internal Poc", req.get('internal_poc', '')),
            ("Requirement From", req.get('requirement_from', '')),
            ("Client Jd Id", req.get('client_jd_id', '')),
            ("Client Lead Poc", req.get('client_lead_poc', '')),
            ("Client Poc", req.get('client_poc', '')),
            ("Job Title", req.get('job_title', '')),
            ("Job Status", req.get('job_status', '')),
            ("Closed Date", req.get('closed_date', '')),
            ("Type Of Demand", req.get('type_of_demand', '')),
            ("Priority", req.get('priority', '')),
            ("Number Of Positions", req.get('number_of_positions', '')),
            ("Experience Level", req.get('experience_level', '')),
            ("Employment Type", req.get('employment_type', '')),
            ("Budget Currency", req.get('budget_currency', '')),
            ("Yearly Budget", req.get('yearly_budget', '')),
            ("Monthly Budget", req.get('monthly_budget', '')),
            ("Work Mode", req.get('work_mode', '')),
            ("Location", req.get('location', '')),
            ("Overall Experience", req.get('overall_experience', '')),
            ("Notice Period", req.get('notice_period', '')),
            ("Mandatory Skills", req.get('mandatory_skills', '')),
            ("Skills", req.get('skills', ''))
        ]
        
        for field_name, field_value in fields:
            if field_value:
                # Handle long text wrapping for skills
                if field_name in ["Mandatory Skills", "Skills"] and len(str(field_value)) > 80:
                    pdf.set_font("Arial", "", 9)
                    # Split long skills into multiple lines
                    words = str(field_value).split('; ')
                    current_line = ""
                    for word in words:
                        if len(current_line + word) > 80:
                            if current_line:
                                pdf.cell(0, 5, _latin(f"{field_name}: {current_line}"), ln=1)
                                current_line = "  " + word
                            else:
                                current_line = word
                        else:
                            if current_line:
                                current_line += "; " + word
                            else:
                                current_line = word
                    if current_line:
                        pdf.cell(0, 5, _latin(f"{field_name}: {current_line}"), ln=1)
                    pdf.set_font("Arial", "", 10)
                else:
                    pdf.cell(0, 5, _latin(f"{field_name}: {field_value}"), ln=1)
        
        pdf.ln(8)
    
    # Save PDF
    pdf.output(output_pdf)
    print(f"Generated {output_pdf} with {mapped_count} requirements")

if __name__ == "__main__":
    # Generate PDF for yesterday's data in the exact format
    generate_metaforge_format_pdf(
        "today_client_emails_exhaustive_2026-04-22.json",
        "metaforge_requirements_2026-04-22_exact_format.pdf"
    )
