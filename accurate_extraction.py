#!/usr/bin/env python3
"""
Accurate extraction of client requirements with exact content from emails
"""

import json
import csv
import re
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Any, Optional

def extract_exact_budget(text: str) -> Dict[str, str]:
    """Extract exact budget information from text"""
    monthly_budget = ""
    yearly_budget = ""
    
    # Look for exact budget mentions
    lines = text.split('\n')
    for line in lines:
        line_lower = line.lower().strip()
        
        # Monthly patterns
        if any(term in line_lower for term in ['/month', 'per month', 'pm', 'lpm', 'bill rate']):
            # Extract numbers from the line
            numbers = re.findall(r'[\d,]+', line)
            if numbers:
                monthly_budget = numbers[0].replace(',', '')
                break
        
        # Yearly patterns
        elif any(term in line_lower for term in ['/year', 'per year', 'pa', 'lpa']):
            numbers = re.findall(r'[\d,]+', line)
            if numbers:
                yearly_budget = numbers[0].replace(',', '')
                break
    
    return {
        "monthly_budget": monthly_budget or "Not provided",
        "yearly_budget": yearly_budget or "Not provided"
    }

def extract_exact_experience(text: str) -> str:
    """Extract exact experience from text"""
    lines = text.split('\n')
    for line in lines:
        line_lower = line.lower().strip()
        
        # Look for experience patterns
        if any(term in line_lower for term in ['exp', 'experience', 'years', 'yrs']):
            # Extract experience range
            exp_match = re.search(r'(\d+)\s*[-–]\s*(\d+)\s*(?:years?|yrs?)', line, re.IGNORECASE)
            if exp_match:
                return f"{exp_match.group(1)}-{exp_match.group(2)} years"
            
            exp_match = re.search(r'(\d+)\s*\+\s*(?:years?|yrs?)', line, re.IGNORECASE)
            if exp_match:
                return f"{exp_match.group(1)}+ years"
            
            exp_match = re.search(r'(\d+)\s*(?:years?|yrs?)', line, re.IGNORECASE)
            if exp_match:
                return f"{exp_match.group(1)} years"
    
    return "Not specified"

def extract_exact_skills(text: str) -> List[str]:
    """Extract exact skills from text"""
    skills = []
    lines = text.split('\n')
    
    for i, line in enumerate(lines):
        line_lower = line.lower().strip()
        
        # Look for skills section
        if any(term in line_lower for term in ['mandatory skills', 'skills', 'technical skills']):
            # Get the next few lines as they might contain the skills
            for j in range(i+1, min(i+5, len(lines))):
                next_line = lines[j].strip()
                if not next_line:
                    continue
                
                # Stop if we hit a new section
                if any(term in next_line.lower() for term in ['job description', 'qualification', 'location', 'budget', 'notice']):
                    break
                
                # Extract skills from the line
                if ',' in next_line:
                    skill_parts = [part.strip() for part in next_line.split(',')]
                    skills.extend([skill for skill in skill_parts if skill and len(skill) > 2])
                elif ';' in next_line:
                    skill_parts = [part.strip() for part in next_line.split(';')]
                    skills.extend([skill for skill in skill_parts if skill and len(skill) > 2])
                elif len(next_line) > 3 and len(next_line) < 100:
                    skills.append(next_line)
    
    return skills

def extract_exact_locations(text: str) -> List[str]:
    """Extract exact locations from text"""
    locations = []
    lines = text.split('\n')
    
    for line in lines:
        line_lower = line.lower().strip()
        
        # Look for location patterns
        if any(term in line_lower for term in ['location', 'work location', 'based at']):
            # Extract locations from the line
            if '/' in line:
                loc_parts = [part.strip() for part in line.split('/')]
                locations.extend([loc for loc in loc_parts if loc and len(loc) > 2])
            elif ',' in line:
                loc_parts = [part.strip() for part in line.split(',')]
                locations.extend([loc for loc in loc_parts if loc and len(loc) > 2])
            else:
                # Extract location after the keyword
                loc_match = re.search(r'location[:\-]\s*(.+)', line, re.IGNORECASE)
                if loc_match:
                    locations.append(loc_match.group(1).strip())
    
    return locations

def extract_exact_notice_period(text: str) -> str:
    """Extract exact notice period from text"""
    lines = text.split('\n')
    
    for line in lines:
        line_lower = line.lower().strip()
        
        # Look for notice period patterns
        if any(term in line_lower for term in ['notice period', 'np', 'join', 'joining']):
            if 'immediate' in line_lower:
                return "Immediate"
            
            # Extract notice period
            notice_match = re.search(r'(\d+)\s*(?:days?|months?)', line, re.IGNORECASE)
            if notice_match:
                return f"{notice_match.group(1)} days"
            
            # Return the line content if it contains notice info
            if 'notice' in line_lower or 'join' in line_lower:
                return line.strip()
    
    return "Not specified"

def extract_exact_positions(text: str) -> int:
    """Extract exact number of positions"""
    lines = text.split('\n')
    
    for line in lines:
        line_lower = line.lower().strip()
        
        # Look for position patterns
        if any(term in line_lower for term in ['no of position', 'number of position', 'positions', 'openings']):
            # Extract numbers
            pos_match = re.search(r'(\d+)', line)
            if pos_match:
                return int(pos_match.group(1))
    
    return 1

def extract_exact_job_title(subject: str, text: str) -> str:
    """Extract exact job title from subject and text"""
    # Clean up the subject
    job_title = subject.strip()
    
    # Remove common prefixes
    prefixes_to_remove = [
        'RE:', 'FW:', 'FWD:', 'TPC Requirement', 'Requirement', 'URGENT', 'Immediate'
    ]
    
    for prefix in prefixes_to_remove:
        if job_title.startswith(prefix):
            job_title = job_title[len(prefix):].strip()
    
    # Remove email addresses and extra info
    job_title = re.sub(r'<[^>]+>', '', job_title)
    job_title = re.sub(r'\([^)]*\)', '', job_title)
    
    return job_title if job_title else "Not specified"

def determine_exact_employment_type(text: str) -> str:
    """Determine exact employment type"""
    text_lower = text.lower()
    
    if any(term in text_lower for term in ['contract', 'c2h', 'c2c', 'tpc']):
        return "Contract"
    elif any(term in text_lower for term in ['full-time', 'full time', 'permanent', 'fte']):
        return "Full Time"
    else:
        return "Contract"

def determine_exact_work_mode(text: str) -> str:
    """Determine exact work mode"""
    text_lower = text.lower()
    
    if any(term in text_lower for term in ['remote', 'wfh', 'work from home']):
        return "Remote"
    elif any(term in text_lower for term in ['hybrid']):
        return "Hybrid"
    else:
        return "On-site"

def determine_exact_priority(text: str) -> str:
    """Determine exact priority"""
    text_lower = text.lower()
    
    if any(term in text_lower for term in ['urgent', 'critical', 'immediate', 'super critical']):
        return "High"
    elif any(term in text_lower for term in ['medium priority']):
        return "Medium"
    elif any(term in text_lower for term in ['low priority']):
        return "Low"
    else:
        return "High"

def determine_exact_experience_level(exp_text: str) -> str:
    """Determine exact experience level"""
    exp_lower = exp_text.lower()
    
    if any(num in exp_lower for num in ['0', '1', '2']):
        return "Junior"
    elif any(num in exp_lower for num in ['3', '4', '5', '6', '7']):
        return "Mid Senior"
    elif any(num in exp_lower for num in ['8', '9', '10', '+']):
        return "Senior"
    else:
        return "Mid Senior"

def process_email_accurately(email_data: Dict[str, Any], index: int) -> Dict[str, Any]:
    """Process email with accurate extraction"""
    
    # Get the email body
    body_text = email_data.get('body_normalized', '') or email_data.get('requirement_summary', '')
    
    # Extract information accurately
    budget_info = extract_exact_budget(body_text)
    experience = extract_exact_experience(body_text)
    skills = extract_exact_skills(body_text)
    locations = extract_exact_locations(body_text)
    notice_period = extract_exact_notice_period(body_text)
    positions = extract_exact_positions(body_text)
    job_title = extract_exact_job_title(email_data.get('subject', ''), body_text)
    
    # Get client information
    client_key = email_data.get('source_vendor_key', 'Unknown')
    client_display = email_data.get('source_vendor_display', client_key.upper())
    from_email = email_data.get('from_email', '')
    from_name = email_data.get('from_name', '')
    subject = email_data.get('subject', '')
    received_date = email_data.get('received_date_time', '')
    
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
    employment_type = determine_exact_employment_type(body_text)
    work_mode = determine_exact_work_mode(body_text)
    priority = determine_exact_priority(body_text)
    experience_level = determine_exact_experience_level(experience)
    
    # Use first location if multiple
    location = locations[0] if locations else ""
    
    # Format skills
    mandatory_skills = "; ".join(skills) if skills else "Not provided"
    all_skills = "; ".join(skills) if skills else "Not provided"
    
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

def extract_todays_requirements_accurately():
    """Extract today's client requirements accurately"""
    
    today = date.today().strftime('%Y-%m-%d')
    all_requirements = []
    processed_ids = set()
    
    # Process all CSV files
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
                        # Filter for today's emails
                        received_date = row.get('received_date_time', '')
                        if today in received_date:
                            graph_id = row.get('graph_id', '')
                            if graph_id and graph_id not in processed_ids:
                                # Check if it's from a known client
                                client_key = row.get('source_vendor_key', '')
                                if client_key and client_key != 'unknown':
                                    processed_ids.add(graph_id)
                                    requirement = process_email_accurately(row, len(all_requirements) + 1)
                                    all_requirements.append(requirement)
            except Exception as e:
                print(f"Error processing {csv_file}: {e}")
    
    # Process JSON files
    json_files = [
        f"today_client_emails_exhaustive_{today}.json",
        f"today_client_emails_exhaustive_{today}_accurate.json",
        f"today_client_emails_exhaustive_{today}_high_conf.json"
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
                                requirement = process_email_accurately(email, len(all_requirements) + 1)
                                all_requirements.append(requirement)
            except Exception as e:
                print(f"Error processing {json_file}: {e}")
    
    # Save accurate results
    output_json = f"accurate_todays_requirements_{today}.json"
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(all_requirements, f, indent=2, ensure_ascii=False)
    
    print(f"Extracted {len(all_requirements)} accurate requirements for {today}")
    print(f"Saved to {output_json}")
    
    return all_requirements

if __name__ == "__main__":
    requirements = extract_todays_requirements_accurately()
