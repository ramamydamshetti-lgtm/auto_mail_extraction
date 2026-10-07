#!/usr/bin/env python3
"""
Corrected extraction system using CSV data directly to match analysis
"""

import json
import csv
import re
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, List, Any

def extract_skills_from_text(text: str) -> tuple[str, str]:
    """Extract skills from email text"""
    lines = text.split('\n')
    mandatory_skills = []
    all_skills = []
    
    in_mandatory_skills = False
    in_skills = False
    
    for line in lines:
        line_stripped = line.strip()
        line_lower = line_stripped.lower()
        
        if 'mandatory skills' in line_lower:
            in_mandatory_skills = True
            if ':' in line_stripped:
                skills_part = line_stripped.split(':', 1)[1].strip()
                if skills_part:
                    mandatory_skills.append(skills_part)
            continue
        
        elif 'skills:' in line_lower and not in_mandatory_skills:
            in_skills = True
            if ':' in line_stripped:
                skills_part = line_stripped.split(':', 1)[1].strip()
                if skills_part:
                    all_skills.append(skills_part)
            continue
        
        if in_mandatory_skills or in_skills:
            if any(term in line_lower for term in ['job description', 'qualification', 'location', 'budget', 'notice', 'experience', 'exp']):
                if in_mandatory_skills:
                    in_mandatory_skills = False
                if in_skills:
                    in_skills = False
                continue
            
            if line_stripped and not line_stripped.startswith(' ') and len(line_stripped) > 3:
                skill = line_stripped.rstrip('.')
                
                if in_mandatory_skills:
                    mandatory_skills.append(skill)
                elif in_skills:
                    all_skills.append(skill)
    
    mandatory_skills_str = "; ".join(mandatory_skills) if mandatory_skills else "Not provided"
    all_skills_str = "; ".join(all_skills) if all_skills else "Not provided"
    
    return mandatory_skills_str, all_skills_str

def extract_budget_from_text(text: str) -> Dict[str, str]:
    """Extract budget from email text"""
    lines = text.split('\n')
    monthly_budget = "Not provided"
    yearly_budget = "Not provided"
    
    for line in lines:
        line_stripped = line.strip()
        line_lower = line_stripped.lower()
        
        if 'bill rate' in line_lower:
            rate_match = re.search(r'bill rate[:\-]?\s*([^\n]+)', line_stripped, re.IGNORECASE)
            if rate_match:
                rate_text = rate_match.group(1).strip()
                num_match = re.search(r'[\d,]+', rate_text)
                if num_match:
                    monthly_budget = rate_text
        
        elif any(term in line_lower for term in ['lpm', '/month', 'per month']):
            num_match = re.search(r'[\d,]+', line_stripped)
            if num_match:
                monthly_budget = num_match.group(0)
        
        elif any(term in line_lower for term in ['lpa', '/year', 'per year']):
            lpa_match = re.search(r'(\d+)lpa', line_lower)
            if lpa_match:
                yearly_budget = f"{lpa_match.group(1)}LPA"
            else:
                num_match = re.search(r'[\d,]+', line_stripped)
                if num_match:
                    yearly_budget = num_match.group(0)
    
    return {
        "monthly_budget": monthly_budget,
        "yearly_budget": yearly_budget
    }

def extract_experience_from_text(text: str) -> str:
    """Extract experience from email text"""
    lines = text.split('\n')
    
    for line in lines:
        line_stripped = line.strip()
        line_lower = line_stripped.lower()
        
        if any(term in line_lower for term in ['exp', 'experience']):
            exp_match = re.search(r'(\d+)\s*[-–]\s*(\d+)\s*(?:years?|yrs?)', line_stripped, re.IGNORECASE)
            if exp_match:
                return f"{exp_match.group(1)}-{exp_match.group(2)} years"
            
            exp_match = re.search(r'(\d+)\s*\+\s*(?:years?|yrs?)', line_stripped, re.IGNORECASE)
            if exp_match:
                return f"{exp_match.group(1)}+ years"
            
            exp_match = re.search(r'(\d+)\s*(?:years?|yrs?)', line_stripped, re.IGNORECASE)
            if exp_match:
                return f"{exp_match.group(1)} years"
            
            exp_match = re.search(r'exp[:\-]?\s*([^\n]+)', line_stripped, re.IGNORECASE)
            if exp_match:
                return exp_match.group(1).strip()
            
            exp_match = re.search(r'overall exp[:\-]?\s*([^\n]+)', line_stripped, re.IGNORECASE)
            if exp_match:
                return exp_match.group(1).strip()
    
    return "Not specified"

def extract_location_from_text(text: str) -> str:
    """Extract location from email text"""
    lines = text.split('\n')
    
    for line in lines:
        line_stripped = line.strip()
        line_lower = line_stripped.lower()
        
        if any(term in line_lower for term in ['location', 'work location', 'based at', 'based in']):
            if ':' in line_stripped:
                loc_part = line_stripped.split(':', 1)[1].strip()
                if loc_part and loc_part != '-' and loc_part != 'Not provided':
                    return loc_part
            
            if '-' in line_stripped and len(line_stripped.split('-')) > 1:
                parts = line_stripped.split('-')
                loc_part = '-'.join(parts[1:]).strip()
                if loc_part and loc_part != '-' and loc_part != 'Not provided':
                    return loc_part
    
    # Look for location patterns
    location_patterns = [
        r'bangalore[/\s]*mysore',
        r'mumbai[/\s]*airoli',
        r'hyderabad[/\s]*gachibowli',
        r'pune[/\s]*hinjewadi',
        r'chennai[/\s]*omr',
        r'delhi[/\s]*ncr',
        r'vadodara'
    ]
    
    for pattern in location_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(0)
    
    cities = ['bangalore', 'mumbai', 'pune', 'hyderabad', 'chennai', 'delhi', 'gurgaon', 'noida', 'kolkata', 'airoli', 'mysore', 'gachibowli', 'hinjewadi', 'omr', 'vadodara']
    for city in cities:
        if city.lower() in text.lower():
            return city.capitalize()
    
    return "Not provided"

def clean_job_title(subject: str) -> str:
    """Clean job title"""
    prefixes = ['RE: ', 'FW: ', 'FWD: ', 'TPC Requirement - ', 'Requirement - ', 'URGENT ', 'TPC -', 'Recall: ', 'New Customer : ']
    for prefix in prefixes:
        if subject.startswith(prefix):
            subject = subject[len(prefix):]
    
    subject = re.sub(r'\s*\([^)]*\)$', '', subject)
    subject = subject.replace('\u2013', ' - ').replace('\u2014', ' - ')
    
    return subject.strip()

def process_csv_email(row: Dict[str, Any], index: int) -> Dict[str, Any]:
    """Process email from CSV data"""
    
    # Get email body
    body_text = row.get('requirement_summary', '')
    
    # Extract information
    budget_info = extract_budget_from_text(body_text)
    experience = extract_experience_from_text(body_text)
    mandatory_skills, all_skills = extract_skills_from_text(body_text)
    location = extract_location_from_text(body_text)
    
    # Get client information
    client_key = row.get('source_vendor_key', 'Unknown')
    client_display = row.get('source_vendor_display', client_key.upper())
    from_email = row.get('from_email', '')
    from_name = row.get('from_name', '')
    subject = row.get('subject', '')
    received_date = row.get('received_date_time', '')
    
    # Clean job title
    job_title = clean_job_title(subject)
    
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
    notice_period = "Not specified"
    
    text_lower = body_text.lower()
    if 'full-time' in text_lower or 'permanent' in text_lower:
        employment_type = "Full Time"
    if 'remote' in text_lower or 'wfh' in text_lower:
        work_mode = "Remote"
    if 'hybrid' in text_lower:
        work_mode = "Hybrid"
    
    # Extract positions
    pos_match = re.search(r'no of position[:\-]?\s*(\d+)', text_lower)
    if pos_match:
        positions = int(pos_match.group(1))
    
    # Extract notice period
    if 'immediate' in text_lower:
        notice_period = "Immediate"
    elif 'april / may joiners' in text_lower:
        notice_period = "April / May joiners"
    
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
        "yearly_budget": budget_info["yearly_budget"],
        "monthly_budget": budget_info["monthly_budget"],
        "work_mode": work_mode,
        "location": location,
        "overall_experience": experience,
        "notice_period": notice_period,
        "mandatory_skills": mandatory_skills,
        "skills": all_skills,
        "source_subject": subject,
        "source_received_time": received_date,
        "source_from_email": from_email,
        "source_from_name": from_name
    }

def extract_corrected_yesterday_requirements():
    """Extract yesterday's requirements using CSV data directly"""
    
    yesterday = date.today() - timedelta(days=1)
    target_date = yesterday.strftime('%Y-%m-%d')
    
    print(f"Extracting requirements for yesterday: {target_date}")
    
    all_requirements = []
    
    # Process CSV file directly
    print(f"\n=== Processing CSV for {target_date} ===")
    try:
        with open('today_fetch.csv', 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            requirement_emails = []
            
            for row in reader:
                received_date = row.get('received_date_time', '')
                if target_date in received_date:
                    subject = row.get('subject', '')
                    client_key = row.get('source_vendor_key', '')
                    
                    # Check if it's a requirement email
                    subject_lower = subject.lower()
                    if any(term in subject_lower for term in ['requirement', 'tpc -', 'job', 'position', 'hiring']):
                        requirement_emails.append(row)
            
            print(f"Found {len(requirement_emails)} requirement emails in CSV")
            
            # Process each requirement email
            for i, row in enumerate(requirement_emails, 1):
                requirement = process_csv_email(row, i)
                all_requirements.append(requirement)
                
                print(f"  {i}. {requirement['requirement_from']} | {requirement['job_title']}")
                
    except Exception as e:
        print(f"Error processing CSV: {e}")
    
    # Save corrected results
    output_json = f"corrected_yesterday_requirements_{target_date}.json"
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(all_requirements, f, indent=2, ensure_ascii=False)
    
    print(f"\nExtracted {len(all_requirements)} corrected requirements for {target_date}")
    print(f"Saved to {output_json}")
    
    return all_requirements

if __name__ == "__main__":
    requirements = extract_corrected_yesterday_requirements()
