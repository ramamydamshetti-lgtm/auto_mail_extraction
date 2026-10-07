#!/usr/bin/env python3
"""
Test refactored system on yesterday's client emails
Uses zero-skip policy and expert recruiter interpretation
"""

import json
import csv
import re
from datetime import datetime, date, timedelta
from typing import Dict, List, Any

def extract_field_expert(text: str, field_name: str) -> str:
    """Extract field using expert recruiter interpretation - only explicit content"""
    import re
    lines = text.split('\n')
    
    for line in lines:
        line_stripped = line.strip()
        line_lower = line_stripped.lower()
        
        if field_name == 'budget':
            if any(term in line_lower for term in ['budget', 'ctc', 'salary', 'lpa', 'lpm', 'bill rate']):
                # Extract exact content after keyword
                if ':' in line_stripped:
                    budget_part = line_stripped.split(':', 1)[1].strip()
                    if budget_part:
                        return budget_part
                # Extract numbers from line
                import re
                num_match = re.search(r'[\d,]+', line_stripped)
                if num_match:
                    return num_match.group(0)
        
        elif field_name == 'experience':
            if any(term in line_lower for term in ['exp', 'experience', 'yoe']):
                if ':' in line_stripped:
                    exp_part = line_stripped.split(':', 1)[1].strip()
                    if exp_part:
                        return exp_part
                # Extract experience range
                exp_match = re.search(r'(\d+)\s*[-–]\s*(\d+)\s*(?:years?|yrs?)', line_stripped, re.IGNORECASE)
                if exp_match:
                    return f"{exp_match.group(1)}-{exp_match.group(2)} years"
                exp_match = re.search(r'(\d+)\s*(?:years?|yrs?)', line_stripped, re.IGNORECASE)
                if exp_match:
                    return f"{exp_match.group(1)} years"
        
        elif field_name == 'location':
            if any(term in line_lower for term in ['location', 'work location', 'based at']):
                if ':' in line_stripped:
                    loc_part = line_stripped.split(':', 1)[1].strip()
                    if loc_part:
                        return loc_part
                # Extract location patterns
                locations = ['bangalore', 'mumbai', 'pune', 'hyderabad', 'chennai', 'delhi', 'gurgaon', 'noida', 'kolkata', 'airoli', 'mysore', 'vadodara']
                for loc in locations:
                    if loc in line_lower:
                        return loc.capitalize()
        
        elif field_name == 'notice_period':
            if 'immediate' in line_lower:
                return "Immediate"
            if any(term in line_lower for term in ['notice', 'np', 'joining']):
                if ':' in line_stripped:
                    notice_part = line_stripped.split(':', 1)[1].strip()
                    if notice_part:
                        return notice_part
                # Extract notice period
                notice_match = re.search(r'(\d+)\s*(?:days?|months?)', line_stripped, re.IGNORECASE)
                if notice_match:
                    return f"{notice_match.group(1)} days"
        
        elif field_name == 'skills':
            if any(term in line_lower for term in ['skills', 'mandatory skills', 'required skills']):
                if ':' in line_stripped:
                    skills_part = line_stripped.split(':', 1)[1].strip()
                    if skills_part:
                        return skills_part
    
    return "Not provided"

def extract_skills_expert(text: str) -> List[str]:
    """Extract skills using expert interpretation"""
    lines = text.split('\n')
    skills = []
    
    in_skills_section = False
    skills_keywords = ['skills', 'technical skills', 'mandatory skills', 'required skills']
    
    for line in lines:
        line_stripped = line.strip()
        line_lower = line_stripped.lower()
        
        # Check if entering skills section
        if any(keyword in line_lower for keyword in skills_keywords):
            in_skills_section = True
            if ':' in line_stripped:
                skills_part = line_stripped.split(':', 1)[1].strip()
                if skills_part:
                    skills.extend([s.strip() for s in skills_part.split(',') if s.strip()])
            continue
        
        # Check if leaving skills section
        if in_skills_section and any(term in line_lower for term in ['job description', 'qualification', 'location', 'budget']):
            in_skills_section = False
            continue
        
        # Extract skills in section
        if in_skills_section:
            if line_stripped and len(line_stripped) > 2:
                skills.append(line_stripped.rstrip('.'))
    
    return skills if skills else []

def process_email_refactored(email_data: Dict[str, Any], index: int) -> Dict[str, Any]:
    """Process email using refactored system with expert interpretation"""
    
    body_text = email_data.get('requirement_summary', '')
    
    # Extract fields using expert interpretation
    budget = extract_field_expert(body_text, 'budget')
    experience = extract_field_expert(body_text, 'experience')
    location = extract_field_expert(body_text, 'location')
    notice_period = extract_field_expert(body_text, 'notice_period')
    skills_list = extract_skills_expert(body_text)
    
    # Get client information
    client_key = email_data.get('source_vendor_key', 'Unknown')
    client_display = email_data.get('source_vendor_display', client_key.upper())
    from_email = email_data.get('from_email', '')
    from_name = email_data.get('from_name', '')
    subject = email_data.get('subject', '')
    received_date = email_data.get('received_date_time', '')
    
    # Clean job title
    prefixes = ['RE: ', 'FW: ', 'FWD: ', 'TPC Requirement - ', 'Requirement - ', 'URGENT ', 'TPC -', 'Recall: ', 'New Customer : ']
    job_title = subject
    for prefix in prefixes:
        if job_title.startswith(prefix):
            job_title = job_title[len(prefix):]
    
    job_title = job_title.strip()
    
    # Parse date
    if received_date:
        try:
            date_obj = datetime.fromisoformat(received_date.replace('Z', '+00:00'))
            demand_date = date_obj.date().isoformat()
        except:
            demand_date = date.today().isoformat()
    else:
        demand_date = date.today().isoformat()
    
    # Generate IDs
    job_id = f"REQ-{demand_date.replace('-', '')}-{index:03d}"
    client_jd_id = f"{client_key.upper()}-{demand_date.replace('-', '')}-{index:03d}"
    
    # Determine other fields
    employment_type = "Contract"
    work_mode = "On-site"
    priority = "High"
    positions = 1
    experience_level = "Mid Senior"
    
    # Extract positions
    pos_match = re.search(r'no of position[:\-]?\s*(\d+)', body_text.lower())
    if pos_match:
        positions = int(pos_match.group(1))
    
    # Map recruiter jargon
    if 'lpa' in budget.lower():
        yearly_budget = budget
        monthly_budget = "Not provided"
    elif 'lpm' in budget.lower():
        monthly_budget = budget
        yearly_budget = "Not provided"
    else:
        monthly_budget = budget if budget != "Not provided" else "Not provided"
        yearly_budget = "Not provided"
    
    # Format skills
    mandatory_skills = "; ".join(skills_list) if skills_list else "Not provided"
    skills = "; ".join(skills_list) if skills_list else "Not provided"
    
    return {
        "job_id": job_id,
        "demand_received_date": demand_date,
        "internal_poc": "offshore demands",
        "requirement_from": client_display,
        "client_jd_id": client_jd_id,
        "client_lead_poc": from_email,
        "client_poc": from_email,
        "job_title": job_title,
        "job_status": "Open",
        "closed_date": "N/A",
        "type_of_demand": "Single",
        "priority": priority,
        "number_of_positions": positions,
        "experience_level": experience_level,
        "employment_type": employment_type,
        "budget_currency": "INR",
        "yearly_budget": yearly_budget,
        "monthly_budget": monthly_budget,
        "work_mode": work_mode,
        "location": location,
        "overall_experience": experience,
        "notice_period": notice_period,
        "mandatory_skills": mandatory_skills,
        "skills": skills,
        "source_subject": subject,
        "source_received_time": received_date,
        "source_from_email": from_email,
        "source_from_name": from_name
    }

def extract_yesterday_refactored():
    """Extract yesterday's requirements using refactored system"""
    
    yesterday = date.today() - timedelta(days=1)
    target_date = yesterday.strftime('%Y-%m-%d')
    
    print(f"Extracting requirements for yesterday: {target_date}")
    print("Using refactored system with zero-skip policy and expert interpretation")
    
    all_requirements = []
    
    # Process CSV file with zero-skip policy
    try:
        with open('today_fetch.csv', 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            requirement_emails = []
            
            for row in reader:
                received_date = row.get('received_date_time', '')
                if target_date in received_date:
                    # Zero-Skip Policy: Process ALL client domain emails
                    client_key = row.get('source_vendor_key', '')
                    if client_key and client_key != 'unknown':
                        requirement_emails.append(row)
            
            print(f"Found {len(requirement_emails)} client emails (zero-skip policy)")
            
            # Sort chronologically (oldest to newest)
            requirement_emails.sort(key=lambda x: x.get('received_date_time', ''))
            
            # Process each email
            for i, row in enumerate(requirement_emails, 1):
                requirement = process_email_refactored(row, i)
                all_requirements.append(requirement)
                
                print(f"  {i}. {requirement['requirement_from']} | {requirement['job_title']}")
                
    except Exception as e:
        print(f"Error processing CSV: {e}")
    
    # Save results
    output_json = f"refactored_yesterday_requirements_{target_date}.json"
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(all_requirements, f, indent=2, ensure_ascii=False)
    
    print(f"\nExtracted {len(all_requirements)} requirements using refactored system")
    print(f"Saved to {output_json}")
    
    return all_requirements

if __name__ == "__main__":
    requirements = extract_yesterday_refactored()
