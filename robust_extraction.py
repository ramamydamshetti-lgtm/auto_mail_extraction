#!/usr/bin/env python3
"""
Robust extraction - accurate and explicit content extraction from emails
"""

import json
import csv
import re
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Any, Optional

def extract_explicit_skills(text: str) -> tuple[str, str]:
    """Extract skills exactly as mentioned in email"""
    lines = text.split('\n')
    mandatory_skills = []
    all_skills = []
    
    # Find mandatory skills section
    mandatory_section = False
    skills_section = False
    
    for i, line in enumerate(lines):
        line_stripped = line.strip()
        line_lower = line_stripped.lower()
        
        # Detect mandatory skills
        if 'mandatory skills' in line_lower:
            mandatory_section = True
            # Extract skills from same line
            if ':' in line_stripped:
                skills_part = line_stripped.split(':', 1)[1].strip()
                if skills_part:
                    mandatory_skills.append(skills_part)
            continue
        
        # Detect regular skills section
        elif 'skills:' in line_lower and not mandatory_section:
            skills_section = True
            if ':' in line_stripped:
                skills_part = line_stripped.split(':', 1)[1].strip()
                if skills_part:
                    all_skills.append(skills_part)
            continue
        
        # Stop conditions
        if mandatory_section or skills_section:
            # Stop at new section headers
            if any(term in line_lower for term in ['job description', 'qualification', 'location', 'budget', 'notice', 'experience', 'exp', 'work location']):
                if mandatory_section:
                    mandatory_section = False
                if skills_section:
                    skills_section = False
                continue
            
            # Collect skills from subsequent lines
            if line_stripped and not line_stripped.startswith(' ') and len(line_stripped) > 2:
                # Check if this looks like a skill (not just random text)
                if any(char.isalpha() for char in line_stripped):
                    skill = line_stripped.rstrip('.')
                    
                    if mandatory_section:
                        mandatory_skills.append(skill)
                    elif skills_section:
                        all_skills.append(skill)
    
    # If no structured skills found, look for bullet points
    if not mandatory_skills and not all_skills:
        bullet_skills = []
        for line in lines:
            line_stripped = line.strip()
            # Match bullet points or numbered items
            if re.match(r'^[\d\.\-\*\+]\s*[A-Za-z]', line_stripped):
                skill = re.sub(r'^[\d\.\-\*\+]\s*', '', line_stripped).strip()
                if len(skill) > 3 and len(skill) < 200:
                    bullet_skills.append(skill)
        
        if bullet_skills:
            mandatory_skills = bullet_skills
            all_skills = bullet_skills
    
    # Format skills exactly as mentioned
    mandatory_skills_str = "; ".join(mandatory_skills) if mandatory_skills else "Not provided"
    all_skills_str = "; ".join(all_skills) if all_skills else "Not provided"
    
    return mandatory_skills_str, all_skills_str

def extract_explicit_location(text: str) -> str:
    """Extract location exactly as mentioned"""
    lines = text.split('\n')
    
    for line in lines:
        line_stripped = line.strip()
        line_lower = line_stripped.lower()
        
        # Look for explicit location patterns
        if any(term in line_lower for term in ['location', 'work location', 'based at', 'based in']):
            # Extract after colon
            if ':' in line_stripped:
                loc_part = line_stripped.split(':', 1)[1].strip()
                if loc_part and loc_part != '-' and loc_part != 'Not provided':
                    return loc_part
            
            # Extract after dash
            if '-' in line_stripped and len(line_stripped.split('-')) > 1:
                parts = line_stripped.split('-')
                loc_part = '-'.join(parts[1:]).strip()
                if loc_part and loc_part != '-' and loc_part != 'Not provided':
                    return loc_part
    
    # Look for location in content
    location_patterns = [
        r'bangalore[/\s]*mysore',
        r'mumbai[/\s]*airoli',
        r'hyderabad[/\s]*gachibowli',
        r'pune[/\s]*hinjewadi',
        r'chennai[/\s]*omr',
        r'delhi[/\s]*ncr',
        r'kolkata[/\s]*itc office green centre'
    ]
    
    for pattern in location_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(0)
    
    # Look for city names
    cities = ['bangalore', 'mumbai', 'pune', 'hyderabad', 'chennai', 'delhi', 'gurgaon', 'noida', 'kolkata', 'airoli', 'mysore', 'gachibowli', 'hinjewadi', 'omr']
    for city in cities:
        if city.lower() in text.lower():
            return city.capitalize()
    
    return "Not provided"

def extract_explicit_budget(text: str) -> Dict[str, str]:
    """Extract budget exactly as mentioned"""
    lines = text.split('\n')
    monthly_budget = "Not provided"
    yearly_budget = "Not provided"
    
    for line in lines:
        line_stripped = line.strip()
        line_lower = line_stripped.lower()
        
        # Bill rate extraction
        if 'bill rate' in line_lower:
            rate_match = re.search(r'bill rate[:\-]?\s*([^\n]+)', line_stripped, re.IGNORECASE)
            if rate_match:
                rate_text = rate_match.group(1).strip()
                if rate_text:
                    monthly_budget = rate_text
        
        # Monthly patterns
        elif any(term in line_lower for term in ['lpm', '/month', 'per month']):
            num_match = re.search(r'[\d,]+', line_stripped)
            if num_match:
                monthly_budget = num_match.group(0)
        
        # Yearly patterns
        elif any(term in line_lower for term in ['lpa', '/year', 'per year']):
            num_match = re.search(r'[\d,]+', line_stripped)
            if num_match:
                yearly_budget = num_match.group(0)
    
    return {
        "monthly_budget": monthly_budget,
        "yearly_budget": yearly_budget
    }

def extract_explicit_experience(text: str) -> str:
    """Extract experience exactly as mentioned"""
    lines = text.split('\n')
    
    for line in lines:
        line_stripped = line.strip()
        line_lower = line_stripped.lower()
        
        if any(term in line_lower for term in ['exp', 'experience']):
            # Extract exact experience range
            exp_match = re.search(r'(\d+)\s*[-–]\s*(\d+)\s*(?:years?|yrs?)', line_stripped, re.IGNORECASE)
            if exp_match:
                return f"{exp_match.group(1)}-{exp_match.group(2)} years"
            
            exp_match = re.search(r'(\d+)\s*\+\s*(?:years?|yrs?)', line_stripped, re.IGNORECASE)
            if exp_match:
                return f"{exp_match.group(1)}+ years"
            
            exp_match = re.search(r'(\d+)\s*(?:years?|yrs?)', line_stripped, re.IGNORECASE)
            if exp_match:
                return f"{exp_match.group(1)} years"
            
            # Extract exact experience text
            exp_match = re.search(r'exp[:\-]?\s*([^\n]+)', line_stripped, re.IGNORECASE)
            if exp_match:
                return exp_match.group(1).strip()
            
            # Look for overall exp
            exp_match = re.search(r'overall exp[:\-]?\s*([^\n]+)', line_stripped, re.IGNORECASE)
            if exp_match:
                return exp_match.group(1).strip()
    
    return "Not specified"

def extract_explicit_positions(text: str) -> int:
    """Extract positions exactly as mentioned"""
    lines = text.split('\n')
    
    for line in lines:
        line_stripped = line.strip()
        line_lower = line_stripped.lower()
        
        if any(term in line_lower for term in ['no of position', 'number of position', 'positions', 'openings', 'open positions']):
            pos_match = re.search(r'(\d+)', line_stripped)
            if pos_match:
                return int(pos_match.group(1))
    
    return 1

def extract_explicit_notice(text: str) -> str:
    """Extract notice period exactly as mentioned"""
    lines = text.split('\n')
    
    for line in lines:
        line_stripped = line.strip()
        line_lower = line_stripped.lower()
        
        if 'immediate' in line_lower:
            return "Immediate"
        
        if any(term in line_lower for term in ['notice', 'join']):
            # Extract exact notice text
            notice_match = re.search(r'(\d+)\s*(?:days?|months?)', line_stripped, re.IGNORECASE)
            if notice_match:
                return f"{notice_match.group(1)} days"
            
            # Extract month/year joiners
            if 'april / may joiners' in line_lower:
                return "April / May joiners"
            
            notice_match = re.search(r'notice[:\-]?\s*([^\n]+)', line_stripped, re.IGNORECASE)
            if notice_match:
                return notice_match.group(1).strip()
    
    return "Not specified"

def clean_job_title_explicit(subject: str) -> str:
    """Clean job title but keep essential content"""
    # Remove common prefixes
    prefixes = ['RE: ', 'FW: ', 'FWD: ', 'TPC Requirement - ', 'Requirement - ', 'URGENT ', 'TPC -', 'Recall: ']
    for prefix in prefixes:
        if subject.startswith(prefix):
            subject = subject[len(prefix):]
    
    # Remove extra info in parentheses
    subject = re.sub(r'\s*\([^)]*\)$', '', subject)
    
    # Clean up special characters
    subject = subject.replace('\u2013', ' - ').replace('\u2014', ' - ')
    
    return subject.strip()

def process_email_robust(email_data: Dict[str, Any], index: int) -> Dict[str, Any]:
    """Process email with robust explicit extraction"""
    
    # Get email body
    body_text = email_data.get('body_normalized', '') or email_data.get('requirement_summary', '')
    
    # Use existing parsed data if available and accurate
    existing_skills = email_data.get('skills', [])
    existing_experience = email_data.get('experience', '')
    existing_location = email_data.get('location', [])
    existing_notice = email_data.get('notice_period', '')
    
    # Extract information explicitly
    budget_info = extract_explicit_budget(body_text)
    
    # Use existing data if available, otherwise extract
    if existing_experience:
        experience = existing_experience
    else:
        experience = extract_explicit_experience(body_text)
    
    if existing_skills and existing_skills != []:
        mandatory_skills = "; ".join(existing_skills)
        all_skills = "; ".join(existing_skills)
    else:
        mandatory_skills, all_skills = extract_explicit_skills(body_text)
    
    if existing_location and existing_location != []:
        location = existing_location[0] if existing_location else "Not provided"
    else:
        location = extract_explicit_location(body_text)
    
    if existing_notice:
        notice_period = existing_notice
    else:
        notice_period = extract_explicit_notice(body_text)
    
    positions = extract_explicit_positions(body_text)
    
    # Get client information
    client_key = email_data.get('source_vendor_key', 'Unknown')
    client_display = email_data.get('source_vendor_display', client_key.upper())
    from_email = email_data.get('from_email', '')
    from_name = email_data.get('from_name', '')
    subject = email_data.get('subject', '')
    received_date = email_data.get('received_date_time', '')
    
    # Clean job title
    job_title = clean_job_title_explicit(subject)
    
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
    
    # Determine other fields from content
    employment_type = "Contract"
    work_mode = "On-site"
    priority = "High"
    experience_level = "Mid Senior"
    
    # Infer from text
    text_lower = body_text.lower()
    if 'full-time' in text_lower or 'permanent' in text_lower:
        employment_type = "Full Time"
    if 'remote' in text_lower or 'wfh' in text_lower:
        work_mode = "Remote"
    if 'hybrid' in text_lower:
        work_mode = "Hybrid"
    if 'urgent' in text_lower or 'critical' in text_lower:
        priority = "High"
    elif 'medium priority' in text_lower:
        priority = "Medium"
    elif 'low priority' in text_lower:
        priority = "Low"
    
    # Determine experience level
    exp_lower = experience.lower()
    if any(num in exp_lower for num in ['0', '1', '2']):
        experience_level = "Junior"
    elif any(num in exp_lower for num in ['3', '4', '5', '6', '7']):
        experience_level = "Mid Senior"
    elif any(num in exp_lower for num in ['8', '9', '10', '+']):
        experience_level = "Senior"
    
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

def extract_robust_requirements(target_date: str = None):
    """Extract requirements with robust explicit extraction"""
    
    if not target_date:
        target_date = date.today().strftime('%Y-%m-%d')
    
    all_requirements = []
    processed_ids = set()
    
    # Process CSV files
    csv_files = [
        "today_fetch.csv",
        "today_fetch_2026-04-20.csv", 
        "today_fetch_2026-04-16.csv",
        "structured_recruitment_data.csv"
    ]
    
    for csv_file in csv_files:
        if Path(csv_file).exists():
            print(f"Processing {csv_file}...")
            try:
                with open(csv_file, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        # Filter for target date
                        received_date = row.get('received_date_time', '')
                        if target_date in received_date:
                            graph_id = row.get('graph_id', '')
                            if graph_id and graph_id not in processed_ids:
                                # Check if it's from a known client
                                client_key = row.get('source_vendor_key', '')
                                if client_key and client_key != 'unknown':
                                    processed_ids.add(graph_id)
                                    requirement = process_email_robust(row, len(all_requirements) + 1)
                                    all_requirements.append(requirement)
            except Exception as e:
                print(f"Error processing {csv_file}: {e}")
    
    # Process JSON files
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
                                requirement = process_email_robust(email, len(all_requirements) + 1)
                                all_requirements.append(requirement)
            except Exception as e:
                print(f"Error processing {json_file}: {e}")
    
    # Save robust results
    output_json = f"robust_requirements_{target_date}.json"
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(all_requirements, f, indent=2, ensure_ascii=False)
    
    print(f"Extracted {len(all_requirements)} robust requirements for {target_date}")
    print(f"Saved to {output_json}")
    
    return all_requirements

if __name__ == "__main__":
    # Extract for yesterday (2026-04-22) to fix the PDF issues
    requirements = extract_robust_requirements("2026-04-22")
