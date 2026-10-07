#!/usr/bin/env python3
"""
Precise extraction - capture EXACT content from emails without interpretation
"""

import json
import csv
import re
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Any

def extract_exact_line_content(text: str, keyword: str) -> str:
    """Extract exact content from line containing keyword"""
    lines = text.split('\n')
    for line in lines:
        if keyword.lower() in line.lower():
            return line.strip()
    return "Not specified"

def extract_budget_precise(text: str) -> Dict[str, str]:
    """Extract exact budget without interpretation"""
    lines = text.split('\n')
    monthly_budget = "Not provided"
    yearly_budget = "Not provided"
    
    for line in lines:
        line_lower = line.lower()
        if 'bill rate' in line_lower:
            # Extract exact bill rate
            rate_match = re.search(r'bill rate[:\-]?\s*([^\n]+)', line, re.IGNORECASE)
            if rate_match:
                monthly_budget = rate_match.group(1).strip()
        elif 'lpm' in line_lower or '/month' in line_lower:
            # Extract exact monthly rate
            rate_match = re.search(r'(\d[\d,]*)\s*(?:lpm|/month)', line, re.IGNORECASE)
            if rate_match:
                monthly_budget = rate_match.group(1)
        elif 'lpa' in line_lower or '/year' in line_lower:
            # Extract exact yearly rate
            rate_match = re.search(r'(\d[\d,]*)\s*(?:lpa|/year)', line, re.IGNORECASE)
            if rate_match:
                yearly_budget = rate_match.group(1)
    
    return {
        "monthly_budget": monthly_budget,
        "yearly_budget": yearly_budget
    }

def extract_experience_precise(text: str) -> str:
    """Extract exact experience without interpretation"""
    lines = text.split('\n')
    for line in lines:
        line_lower = line.lower()
        if 'exp' in line_lower:
            # Extract exact experience text
            exp_match = re.search(r'exp[:\-]?\s*([^\n]+)', line, re.IGNORECASE)
            if exp_match:
                return exp_match.group(1).strip()
    return "Not specified"

def extract_skills_precise(text: str) -> str:
    """Extract exact skills without interpretation"""
    lines = text.split('\n')
    skills_section = False
    skills = []
    
    for line in lines:
        line_lower = line.lower().strip()
        
        if any(term in line_lower for term in ['mandatory skills', 'skills:']):
            skills_section = True
            # Extract skills from same line
            if ':' in line:
                skills_part = line.split(':', 1)[1].strip()
                if skills_part:
                    skills.append(skills_part)
            continue
        
        if skills_section:
            # Stop at new section
            if any(term in line_lower for term in ['job description', 'qualification', 'location', 'budget', 'notice']):
                break
            
            if line.strip():
                skills.append(line.strip())
    
    return "; ".join(skills) if skills else "Not provided"

def extract_location_precise(text: str) -> str:
    """Extract exact location without interpretation"""
    lines = text.split('\n')
    for line in lines:
        line_lower = line.lower()
        if 'location' in line_lower:
            # Extract exact location text
            loc_match = re.search(r'location[:\-]?\s*([^\n]+)', line, re.IGNORECASE)
            if loc_match:
                return loc_match.group(1).strip()
    return "Not specified"

def extract_positions_precise(text: str) -> int:
    """Extract exact positions without interpretation"""
    lines = text.split('\n')
    for line in lines:
        line_lower = line.lower()
        if 'no of position' in line_lower or 'position' in line_lower:
            # Extract exact number
            pos_match = re.search(r'(\d+)', line)
            if pos_match:
                return int(pos_match.group(1))
    return 1

def extract_notice_precise(text: str) -> str:
    """Extract exact notice period without interpretation"""
    lines = text.split('\n')
    for line in lines:
        line_lower = line.lower()
        if 'immediate' in line_lower:
            return "Immediate"
        elif 'notice' in line_lower:
            # Extract exact notice text
            notice_match = re.search(r'notice[:\-]?\s*([^\n]+)', line, re.IGNORECASE)
            if notice_match:
                return notice_match.group(1).strip()
    return "Not specified"

def clean_job_title(subject: str) -> str:
    """Clean job title but keep core content"""
    # Remove common prefixes
    prefixes = ['RE: ', 'FW: ', 'FWD: ', 'TPC Requirement - ', 'Requirement - ', 'URGENT ']
    for prefix in prefixes:
        if subject.startswith(prefix):
            subject = subject[len(prefix):]
    
    # Remove extra info in parentheses
    subject = re.sub(r'\s*\([^)]*\)', '', subject)
    
    return subject.strip()

def process_email_precisely(email_data: Dict[str, Any], index: int) -> Dict[str, Any]:
    """Process email with precise extraction"""
    
    # Get the email body
    body_text = email_data.get('body_normalized', '') or email_data.get('requirement_summary', '')
    
    # Extract information precisely
    budget_info = extract_budget_precise(body_text)
    experience = extract_experience_precise(body_text)
    skills = extract_skills_precise(body_text)
    location = extract_location_precise(body_text)
    notice_period = extract_notice_precise(body_text)
    positions = extract_positions_precise(body_text)
    
    # Get client information
    client_key = email_data.get('source_vendor_key', 'Unknown')
    client_display = email_data.get('source_vendor_display', client_key.upper())
    from_email = email_data.get('from_email', '')
    from_name = email_data.get('from_name', '')
    subject = email_data.get('subject', '')
    received_date = email_data.get('received_date_time', '')
    
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
    
    # Default values for required fields
    employment_type = "Contract"  # Default
    work_mode = "On-site"  # Default
    priority = "High"  # Default
    experience_level = "Mid Senior"  # Default
    
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
        "mandatory_skills": skills,
        "skills": skills,
        "source_subject": subject,
        "source_received_time": received_date,
        "source_from_email": from_email,
        "source_from_name": from_name
    }

def extract_todays_precise():
    """Extract today's requirements precisely"""
    
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
                                    requirement = process_email_precisely(row, len(all_requirements) + 1)
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
                                requirement = process_email_precisely(email, len(all_requirements) + 1)
                                all_requirements.append(requirement)
            except Exception as e:
                print(f"Error processing {json_file}: {e}")
    
    # Save precise results
    output_json = f"precise_todays_requirements_{today}.json"
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(all_requirements, f, indent=2, ensure_ascii=False)
    
    print(f"Extracted {len(all_requirements)} precise requirements for {today}")
    print(f"Saved to {output_json}")
    
    return all_requirements

if __name__ == "__main__":
    requirements = extract_todays_precise()
