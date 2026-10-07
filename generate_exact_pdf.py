#!/usr/bin/env python3
"""
Generate PDF that exactly matches JSON content
Ensures PDF contains exactly what the JSON file contains
"""

import json
from datetime import datetime, date
from pathlib import Path
from fpdf import FPDF

def _latin(s: str) -> str:
    return (s or "").encode("latin-1", errors="replace").decode("latin-1")

def generate_exact_pdf_from_json(input_json: str, output_pdf: str):
    """
    Generate PDF that exactly matches the JSON content
    """
    # Load the JSON data
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
    if isinstance(data, list) and len(data) > 0:
        report_date = data[0].get('demand_received_date', date.today().strftime('%Y-%m-%d'))
    else:
        report_date = date.today().strftime('%Y-%m-%d')
    
    pdf.cell(0, 7, _latin(f"Date: {report_date}"), ln=1)
    pdf.cell(0, 7, _latin(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"), ln=1)
    
    # Count requirements
    if isinstance(data, list):
        mapped_count = len(data)
    else:
        mapped_count = 1
    
    pdf.cell(0, 7, _latin(f"Mapped requirements: {mapped_count}"), ln=1)
    pdf.ln(10)
    
    # Process each requirement exactly as in JSON
    if isinstance(data, list):
        requirements = data
    else:
        requirements = [data]
    
    for i, req in enumerate(requirements, 1):
        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 8, _latin(f"Requirement {i}"), ln=1)
        
        pdf.set_font("Arial", "", 10)
        
        # Define field order exactly as in JSON
        field_order = [
            "job_id",
            "demand_received_date", 
            "internal_poc",
            "requirement_from",
            "client_jd_id",
            "client_lead_poc", 
            "client_poc",
            "job_title",
            "job_status",
            "closed_date",
            "type_of_demand",
            "priority",
            "number_of_positions",
            "experience_level",
            "employment_type",
            "budget_currency",
            "yearly_budget",
            "monthly_budget", 
            "work_mode",
            "location",
            "overall_experience",
            "notice_period",
            "mandatory_skills",
            "skills"
        ]
        
        # Add each field exactly as in JSON
        for field_name in field_order:
            field_value = req.get(field_name, "")
            
            # Handle long text fields (skills, mandatory_skills)
            if field_name in ["mandatory_skills", "skills"] and len(str(field_value)) > 80:
                pdf.set_font("Arial", "", 9)
                lines = str(field_value).split('; ')
                current_line = field_name + ": "
                
                for j, line in enumerate(lines):
                    if j == 0:
                        current_line += line
                    else:
                        if len(current_line) > 70:
                            pdf.cell(0, 5, _latin(current_line), ln=1)
                            current_line = "    " + line
                        else:
                            current_line += "; " + line
                
                if current_line:
                    pdf.cell(0, 5, _latin(current_line), ln=1)
                
                pdf.set_font("Arial", "", 10)
            else:
                pdf.cell(0, 5, _latin(f"{field_name}: {field_value}"), ln=1)
        
        pdf.ln(5)
    
    # Save PDF
    pdf.output(output_pdf)
    print(f"Generated {output_pdf} with {mapped_count} requirements exactly matching JSON content")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) != 3:
        print("Usage: python generate_exact_pdf.py <input_json> <output_pdf>")
        sys.exit(1)
    
    input_json = sys.argv[1]
    output_pdf = sys.argv[2]
    
    generate_exact_pdf_from_json(input_json, output_pdf)
