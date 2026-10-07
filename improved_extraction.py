#!/usr/bin/env python3
"""
Improved extraction - accurate skills and location extraction for all emails
"""

import json
import csv
import re
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Any

def extract_skills_improved(text: str) -> tuple[str, str]:
    """Extract skills and mandatory skills accurately"""
    lines = text.split('\n')
    mandatory_skills = []
    all_skills = []
    
    in_mandatory_skills = False
    in_skills = False
    
    for line in lines:
        line_stripped = line.strip()
        line_lower = line_stripped.lower()
        
        # Detect mandatory skills section
        if any(term in line_lower for term in ['mandatory skills', 'skills required', 'required skills']):
            in_mandatory_skills = True
            # Extract skills from same line if present
            if ':' in line_stripped:
                skills_part = line_stripped.split(':', 1)[1].strip()
                if skills_part:
                    mandatory_skills.append(skills_part)
            continue
        
        # Detect regular skills section
        elif any(term in line_lower for term in ['skills:', 'technical skills']) and not in_mandatory_skills:
            in_skills = True
            # Extract skills from same line if present
            if ':' in line_stripped:
                skills_part = line_stripped.split(':', 1)[1].strip()
                if skills_part:
                    all_skills.append(skills_part)
            continue
        
        # Stop conditions
        if in_mandatory_skills or in_skills:
            # Stop at new sections
            if any(term in line_lower for term in ['job description', 'qualification', 'location', 'budget', 'notice', 'experience', 'exp']):
                if in_mandatory_skills:
                    in_mandatory_skills = False
                if in_skills:
                    in_skills = False
                continue
            
            # Collect skills
            if line_stripped and not line_stripped.startswith(' ') and len(line_stripped) > 3:
                # Clean up the skill
                skill = line_stripped.rstrip('.')
                
                if in_mandatory_skills:
                    mandatory_skills.append(skill)
                elif in_skills:
                    all_skills.append(skill)
    
    # If no skills found, try alternative extraction
    if not mandatory_skills and not all_skills:
        # Look for skills in bullet points
        bullet_skills = []
        for line in lines:
            line_stripped = line.strip()
            # Match bullet points or numbered items that look like skills
            if re.match(r'^[\d\.\-\*\+]\s*[A-Za-z]', line_stripped):
                skill = re.sub(r'^[\d\.\-\*\+]\s*', '', line_stripped).strip()
                if len(skill) > 3 and len(skill) < 200:
                    bullet_skills.append(skill)
        
        if bullet_skills:
            mandatory_skills = bullet_skills
            all_skills = bullet_skills
    
    # Format skills
    mandatory_skills_str = "; ".join(mandatory_skills) if mandatory_skills else "Not provided"
    all_skills_str = "; ".join(all_skills) if all_skills else "Not provided"
    
    return mandatory_skills_str, all_skills_str

def extract_location_improved(text: str) -> str:
    """Extract location accurately"""
    lines = text.split('\n')
    
    for line in lines:
        line_stripped = line.strip()
        line_lower = line_stripped.lower()
        
        # Look for location patterns
        if any(term in line_lower for term in ['location', 'work location', 'based at', 'based in']):
            
            # Extract location after the keyword
            if ':' in line_stripped:
                loc_part = line_stripped.split(':', 1)[1].strip()
                if loc_part and loc_part != '-':
                    return loc_part
            
            # Extract location with dash
            if '-' in line_stripped:
                parts = line_stripped.split('-')
                if len(parts) > 1:
                    loc_part = '-'.join(parts[1:]).strip()
                    if loc_part and loc_part != '-':
                        return loc_part
            
            # Extract location with slash
            if '/' in line_stripped:
                parts = line_stripped.split('/')
                if len(parts) > 1:
                    loc_part = '/'.join(parts[1:]).strip()
                    if loc_part and loc_part != '-':
                        return loc_part
    
    # Look for location in subject or first lines
    location_patterns = [
        r'bangalore[/\s]*mysore',
        r'mumbai[/\s]*airoli',
        r'hyderabad[/\s]*gachibowli',
        r'pune[/\s]*hinjewadi',
        r'chennai[/\s]*omr',
        r'delhi[/\s]*ncr'
    ]
    
    for pattern in location_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(0)
    
    # Look for common city names
    cities = ['bangalore', 'mumbai', 'pune', 'hyderabad', 'chennai', 'delhi', 'gurgaon', 'noida', 'kolkata', 'airoli', 'mysore', 'gachibowli', 'hinjewadi', 'omr']
    for city in cities:
        if city.lower() in text.lower():
            return city.capitalize()
    
    return "Not provided"

def extract_budget_improved(text: str) -> Dict[str, str]:
    """Extract budget accurately"""
    lines = text.split('\n')
    monthly_budget = "Not provided"
    yearly_budget = "Not provided"
    
    for line in lines:
        line_lower = line.lower()
        
        # Bill rate patterns
        if 'bill rate' in line_lower:
            rate_match = re.search(r'bill rate[:\-]?\s*([^\n]+)', line, re.IGNORECASE)
            if rate_match:
                rate_text = rate_match.group(1).strip()
                # Extract numbers from rate text
                num_match = re.search(r'[\d,]+', rate_text)
                if num_match:
                    monthly_budget = rate_text
                else:
                    monthly_budget = rate_text
        
        # Monthly patterns
        elif any(term in line_lower for term in ['lpm', '/month', 'per month']):
            num_match = re.search(r'[\d,]+', line)
            if num_match:
                monthly_budget = num_match.group(0)
        
        # Yearly patterns
        elif any(term in line_lower for term in ['lpa', '/year', 'per year']):
            num_match = re.search(r'[\d,]+', line)
            if num_match:
                yearly_budget = num_match.group(0)
    
    return {
        "monthly_budget": monthly_budget,
        "yearly_budget": yearly_budget
    }

def extract_experience_improved(text: str) -> str:
    """Extract experience accurately"""
    lines = text.split('\n')
    
    for line in lines:
        line_lower = line.lower()
        
        if any(term in line_lower for term in ['exp', 'experience']):
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
            
            # Extract exact experience text
            exp_match = re.search(r'exp[:\-]?\s*([^\n]+)', line, re.IGNORECASE)
            if exp_match:
                return exp_match.group(1).strip()
    
    return "Not specified"

def extract_positions_improved(text: str) -> int:
    """Extract positions accurately"""
    lines = text.split('\n')
    
    for line in lines:
        line_lower = line.lower()
        
        if any(term in line_lower for term in ['no of position', 'number of position', 'positions', 'openings']):
            pos_match = re.search(r'(\d+)', line)
            if pos_match:
                return int(pos_match.group(1))
    
    return 1

def extract_notice_improved(text: str) -> str:
    """Extract notice period accurately"""
    lines = text.split('\n')
    
    for line in lines:
        line_lower = line.lower()
        
        if 'immediate' in line_lower:
            return "Immediate"
        
        if any(term in line_lower for term in ['notice', 'join']):
            notice_match = re.search(r'(\d+)\s*(?:days?|months?)', line, re.IGNORECASE)
            if notice_match:
                return f"{notice_match.group(1)} days"
            
            # Extract exact notice text
            notice_match = re.search(r'notice[:\-]?\s*([^\n]+)', line, re.IGNORECASE)
            if notice_match:
                return notice_match.group(1).strip()
    
    return "Not specified"

def clean_job_title_improved(subject: str) -> str:
    """Clean job title but keep core content"""
    # Remove common prefixes
    prefixes = ['RE: ', 'FW: ', 'FWD: ', 'TPC Requirement - ', 'Requirement - ', 'URGENT ', 'TPC -']
    for prefix in prefixes:
        if subject.startswith(prefix):
            subject = subject[len(prefix):]
    
    # Remove extra info in parentheses at the end
    subject = re.sub(r'\s*\([^)]*\)$', '', subject)
    
    return subject.strip()

def process_email_improved(email_data: Dict[str, Any], index: int) -> Dict[str, Any]:
    """Process email with improved extraction"""
    
    # Get the email body
    body_text = email_data.get('body_normalized', '') or email_data.get('requirement_summary', '')
    
    # Extract information with improved methods
    budget_info = extract_budget_improved(body_text)
    experience = extract_experience_improved(body_text)
    mandatory_skills, all_skills = extract_skills_improved(body_text)
    location = extract_location_improved(body_text)
    notice_period = extract_notice_improved(body_text)
    positions = extract_positions_improved(body_text)
    
    # Get client information
    client_key = email_data.get('source_vendor_key', 'Unknown')
    client_display = email_data.get('source_vendor_display', client_key.upper())
    from_email = email_data.get('from_email', '')
    from_name = email_data.get('from_name', '')
    subject = email_data.get('subject', '')
    received_date = email_data.get('received_date_time', '')
    
    # Clean job title
    job_title = clean_job_title_improved(subject)
    
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
    
    # Default values
    employment_type = "Contract"
    work_mode = "On-site"
    priority = "High"
    experience_level = "Mid Senior"
    
    # Try to infer from text
    if 'full-time' in body_text.lower() or 'permanent' in body_text.lower():
        employment_type = "Full Time"
    if 'remote' in body_text.lower() or 'wfh' in body_text.lower():
        work_mode = "Remote"
    if 'hybrid' in body_text.lower():
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
        "source_subject": subject,
        "source_received_time": received_date,
        "source_from_email": from_email,
        "source_from_name": from_name
    }

def extract_todays_improved():
    """Extract today's requirements with improved accuracy"""
    
    today = date.today().strftime('%Y-%m-%d')
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
                        # Filter for today's emails
                        received_date = row.get('received_date_time', '')
                        if today in received_date:
                            graph_id = row.get('graph_id', '')
                            if graph_id and graph_id not in processed_ids:
                                # Check if it's from a known client
                                client_key = row.get('source_vendor_key', '')
                                if client_key and client_key != 'unknown':
                                    processed_ids.add(graph_id)
                                    requirement = process_email_improved(row, len(all_requirements) + 1)
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
                                requirement = process_email_improved(email, len(all_requirements) + 1)
                                all_requirements.append(requirement)
            except Exception as e:
                print(f"Error processing {json_file}: {e}")
    
    # Save improved results
    output_json = f"improved_todays_requirements_{today}.json"
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(all_requirements, f, indent=2, ensure_ascii=False)
    
    print(f"Extracted {len(all_requirements)} improved requirements for {today}")
    print(f"Saved to {output_json}")
    
    return all_requirements

if __name__ == "__main__":
    requirements = extract_todays_improved()
