#!/usr/bin/env python3
"""
Extract yesterday's requirements with corrected system
"""

import json
import csv
import re
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, List, Any

def extract_skills_corrected(text: str, existing_skills: List[str] = None) -> tuple[str, str]:
    """Extract skills with correct formatting"""
    if existing_skills and existing_skills != []:
        mandatory_skills = "; ".join(existing_skills)
        all_skills = "; ".join(existing_skills)
        return mandatory_skills, all_skills
    
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

def extract_budget_corrected(text: str) -> Dict[str, str]:
    """Extract budget with correct formatting"""
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

def process_email_corrected(email_data: Dict[str, Any], index: int) -> Dict[str, Any]:
    """Process email with all corrections applied"""
    
    body_text = email_data.get('body_normalized', '') or email_data.get('requirement_summary', '')
    
    existing_skills = email_data.get('skills', [])
    existing_experience = email_data.get('experience', '')
    existing_location = email_data.get('location', [])
    existing_notice = email_data.get('notice_period', '')
    
    budget_info = extract_budget_corrected(body_text)
    
    # Use existing data if available
    experience = existing_experience if existing_experience != "" else "Not specified"
    mandatory_skills, all_skills = extract_skills_corrected(body_text, existing_skills)
    location = existing_location[0] if existing_location and existing_location != [] else "Not provided"
    notice_period = existing_notice if existing_notice != "" else "Not specified"
    
    client_key = email_data.get('source_vendor_key', 'Unknown')
    client_display = email_data.get('source_vendor_display', client_key.upper())
    from_email = email_data.get('from_email', '')
    from_name = email_data.get('from_name', '')
    subject = email_data.get('subject', '')
    received_date = email_data.get('received_date_time', '')
    
    # Clean job title
    prefixes = ['RE: ', 'FW: ', 'FWD: ', 'TPC Requirement - ', 'Requirement - ', 'URGENT ', 'TPC -', 'Recall: ', 'New Customer : ']
    for prefix in prefixes:
        if subject.startswith(prefix):
            subject = subject[len(prefix):]
    
    subject = re.sub(r'\s*\([^)]*\)$', '', subject)
    subject = subject.replace('\u2013', ' - ').replace('\u2014', ' - ')
    job_title = subject.strip()
    
    if received_date:
        try:
            date_obj = datetime.fromisoformat(received_date.replace('Z', '+00:00'))
            demand_date = date_obj.date().isoformat()
        except:
            demand_date = date.today().isoformat()
    else:
        demand_date = date.today().isoformat()
    
    job_id = f"REQ-{demand_date.replace('-', '')}-{index:03d}"
    client_jd_id = f"{client_key.upper()}-{demand_date.replace('-', '')}-{index:03d}"
    
    # Determine other fields
    employment_type = "Contract"
    work_mode = "On-site"
    priority = "High"
    positions = 1
    experience_level = "Mid Senior"
    
    text_lower = body_text.lower()
    if 'full-time' in text_lower or 'permanent' in text_lower:
        employment_type = "Full Time"
    if 'remote' in text_lower or 'wfh' in text_lower:
        work_mode = "Remote"
    if 'hybrid' in text_lower:
        work_mode = "Hybrid"
    
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
        "source_subject": email_data.get('subject', ''),
        "source_received_time": received_date,
        "source_from_email": from_email,
        "source_from_name": from_name
    }

def extract_yesterday_requirements():
    """Extract yesterday's requirements with corrected system"""
    
    yesterday = date.today() - timedelta(days=1)
    target_date = yesterday.strftime('%Y-%m-%d')
    
    print(f"Extracting requirements for yesterday: {target_date}")
    
    all_requirements = []
    processed_ids = set()
    
    # Process JSON files for yesterday
    json_files = [
        f"today_client_emails_exhaustive_{target_date}.json",
        f"today_client_emails_exhaustive_{target_date}_accurate.json",
        f"today_client_emails_exhaustive_{target_date}_high_conf.json"
    ]
    
    for json_file in json_files:
        if Path(json_file).exists():
            print(f"Processing {json_file}...")
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, dict) and 'emails' in data:
                        for email in data['emails']:
                            graph_id = email.get('graph_id', '')
                            if graph_id and graph_id not in processed_ids:
                                processed_ids.add(graph_id)
                                requirement = process_email_corrected(email, len(all_requirements) + 1)
                                all_requirements.append(requirement)
            except Exception as e:
                print(f"Error processing {json_file}: {e}")
    
    # Save yesterday's results
    output_json = f"yesterday_corrected_requirements_{target_date}.json"
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(all_requirements, f, indent=2, ensure_ascii=False)
    
    print(f"Extracted {len(all_requirements)} corrected requirements for {target_date}")
    print(f"Saved to {output_json}")
    
    return all_requirements

if __name__ == "__main__":
    requirements = extract_yesterday_requirements()
