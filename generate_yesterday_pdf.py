#!/usr/bin/env python3
"""
Generate PDF report for yesterday's client requirements
"""

import json
from datetime import datetime
from pathlib import Path
from fpdf import FPDF

def _latin(s: str) -> str:
    return (s or "").encode("latin-1", errors="replace").decode("latin-1")

def generate_yesterday_pdf():
    # Load yesterday's data
    with open("today_client_emails_exhaustive_2026-04-22.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # Create PDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, _latin(f"Client Requirements Report - {data['date']}"), ln=1)
    
    pdf.set_font("Arial", "", 12)
    pdf.cell(0, 7, _latin(f"Total Client Emails: {data['total_client_emails']}"), ln=1)
    pdf.cell(0, 7, _latin(f"Unique Demands: {data['unique_demands']}"), ln=1)
    pdf.cell(0, 7, _latin(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"), ln=1)
    pdf.ln(10)
    
    # Process each email
    for email in data['emails']:
        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 8, _latin(f"Client: {email['source_vendor_key'].upper()}"), ln=1)
        pdf.set_font("Arial", "", 11)
        pdf.cell(0, 6, _latin(f"From: {email['from_name']} ({email['from_email']})"), ln=1)
        pdf.cell(0, 6, _latin(f"Subject: {email['subject']}"), ln=1)
        pdf.cell(0, 6, _latin(f"Received: {email['received_date_time']}"), ln=1)
        
        if email.get('job_title'):
            pdf.set_font("Arial", "B", 11)
            pdf.cell(0, 6, _latin(f"Job Title: {email['job_title']}"), ln=1)
            pdf.set_font("Arial", "", 10)
            
            if email.get('experience'):
                pdf.cell(0, 5, _latin(f"Experience: {email['experience']}"), ln=1)
            
            if email.get('location'):
                locations = ", ".join(email['location']) if isinstance(email['location'], list) else email['location']
                pdf.cell(0, 5, _latin(f"Location: {locations}"), ln=1)
            
            if email.get('skills'):
                skills = ", ".join(email['skills']) if isinstance(email['skills'], list) else email['skills']
                pdf.cell(0, 5, _latin(f"Skills: {skills}"), ln=1)
            
            if email.get('notice_period'):
                pdf.cell(0, 5, _latin(f"Notice Period: {email['notice_period']}"), ln=1)
        
        pdf.cell(0, 5, _latin(f"Confidence: {email.get('parsed_overall_confidence', 0):.2f}"), ln=1)
        pdf.ln(8)
    
    # Save PDF
    output_file = "yesterday_client_requirements_2026-04-22.pdf"
    pdf.output(output_file)
    print(f"Generated {output_file}")

if __name__ == "__main__":
    generate_yesterday_pdf()
