#!/usr/bin/env python3
"""
Comprehensive extraction of yesterday's client requirements with accurate field mapping
"""

import json
import csv
import re
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Any

def extract_budget_from_text(text: str) -> Dict[str, str]:
    """Extract budget information from email text"""
    monthly_budget = ""
    yearly_budget = ""
    
    # Monthly patterns
    monthly_patterns = [
        r'(\d+(?:,\d+)*)\s*(?:/month|per month|pm|lpm)',
        r'bill rate[:\-]\s*(\d+(?:,\d+)*)\s*(?:/month|per month|pm|lpm)',
        r'(\d+(?:,\d+)*)\s*month'
    ]
    
    # Yearly patterns  
    yearly_patterns = [
        r'(\d+(?:,\d+)*)\s*(?:/year|per year|pa|lpa)',
        r'budget[:\-]\s*(\d+(?:,\d+)*)\s*(?:/year|per year|pa|lpa)',
        r'(\d+(?:,\d+)*)\s*lpa'
    ]
    
    for pattern in monthly_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            monthly_budget = match.group(1).replace(',', '')
            break
    
    for pattern in yearly_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            yearly_budget = match.group(1).replace(',', '')
            break
    
    return {
        "monthly_budget": monthly_budget,
        "yearly_budget": yearly_budget
    }

def extract_experience_from_text(text: str) -> str:
    """Extract experience range from text"""
    patterns = [
        r'(\d+)\s*[-–]\s*(\d+)\s*(?:years?|yrs?)',
        r'(\d+)\s*[-–]\s*(\d+)\s*(?:years?|yrs?)',
        r'(\d+)\s*\+\s*(?:years?|yrs?)',
        r'exp[:\-]\s*(\d+)\s*[-–]\s*(\d+)',
        r'exp[:\-]\s*(\d+)\s*\+'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            if '+' in match.group(0):
                return f"{match.group(1)}+ years"
            else:
                return f"{match.group(1)}-{match.group(2)} years"
    
    return "Not specified"

def extract_skills_from_text(text: str) -> List[str]:
    """Extract skills from email text"""
    skills = []
    
    # Common skill patterns
    skill_patterns = [
        r'mandatory skills?[:\-]\s*(.+?)(?:\n\n|\n[A-Z]|\n\d+|$)',
        r'skills?[:\-]\s*(.+?)(?:\n\n|\n[A-Z]|\n\d+|$)',
        r'technical skills?[:\-]\s*(.+?)(?:\n\n|\n[A-Z]|\n\d+|$)',
    ]
    
    for pattern in skill_patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            skill_text = match.group(1).strip()
            # Split by common separators
            skill_list = re.split(r'[,;]\s*|\n\s*[-•]\s*', skill_text)
            for skill in skill_list:
                skill = skill.strip()
                if len(skill) > 2 and len(skill) < 100:
                    skills.append(skill)
    
    return skills

def extract_locations_from_text(text: str) -> List[str]:
    """Extract locations from text"""
    locations = []
    
    patterns = [
        r'location[:\-]\s*(.+?)(?:\n|$)',
        r'work location[:\-]\s*(.+?)(?:\n|$)',
        r'based at[:\-]\s*(.+?)(?:\n|$)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            loc_text = match.group(1).strip()
            # Split by common separators
            loc_list = re.split(r'[,/]\s*|\s*[-–]\s*', loc_text)
            for loc in loc_list:
                loc = loc.strip()
                if len(loc) > 2 and len(loc) < 50:
                    locations.append(loc)
    
    return locations

def determine_employment_type(text: str) -> str:
    """Determine employment type from text"""
    text_lower = text.lower()
    if any(term in text_lower for term in ['contract', 'c2h', 'c2c', 'tpc']):
        return "Contract"
    elif any(term in text_lower for term in ['full-time', 'full time', 'permanent', 'fte']):
        return "Full Time"
    else:
        return "Contract"  # Default

def determine_work_mode(text: str) -> str:
    """Determine work mode from text"""
    text_lower = text.lower()
    if any(term in text_lower for term in ['remote', 'wfh', 'work from home']):
        return "Remote"
    elif any(term in text_lower for term in ['hybrid']):
        return "Hybrid"
    else:
        return "On-site"  # Default

def determine_priority(text: str) -> str:
    """Determine priority from text"""
    text_lower = text.lower()
    if any(term in text_lower for term in ['urgent', 'critical', 'immediate']):
        return "High"
    elif any(term in text_lower for term in ['medium priority']):
        return "Medium"
    elif any(term in text_lower for term in ['low priority']):
        return "Low"
    else:
        return "High"  # Default

def determine_experience_level(exp_text: str) -> str:
    """Determine experience level from experience text"""
    exp_lower = exp_text.lower()
    if any(num in exp_lower for num in ['0', '1', '2']):
        return "Junior"
    elif any(num in exp_lower for num in ['3', '4', '5', '6', '7']):
        return "Mid Senior"
    elif any(num in exp_lower for num in ['8', '9', '10', '+']):
        return "Senior"
    else:
        return "Mid Senior"

def extract_notice_period(text: str) -> str:
    """Extract notice period from text"""
    patterns = [
        r'notice period[:\-]\s*(.+?)(?:\n|$)',
        r'np[:\-]\s*(.+?)(?:\n|$)',
        r'join[:\-]\s*(.+?)(?:\n|$)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    
    # Look for immediate joiner
    if any(term in text.lower() for term in ['immediate', 'immediate joiner', 'immediate joining']):
        return "Immediate"
    
    return "Not specified"

def extract_number_of_positions(text: str) -> int:
    """Extract number of positions from text"""
    patterns = [
        r'no of position[:\-]\s*(\d+)',
        r'number of position[:\-]\s*(\d+)',
        r'positions?[:\-]\s*(\d+)',
        r'openings?[:\-]\s*(\d+)',
        r'(\d+)\s*position',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return int(match.group(1))
    
    return 1  # Default

def process_email_to_metaforge_format(email_data: Dict[str, Any], index: int) -> Dict[str, Any]:
    """Process email data into MetaForge format"""
    
    # Get the email body
    body_text = email_data.get('body_normalized', '') or email_data.get('requirement_summary', '')
    
    # Extract information using robust methods
    budget_info = extract_budget_from_text(body_text)
    experience = extract_experience_from_text(body_text)
    skills = extract_skills_from_text(body_text)
    locations = extract_locations_from_text(body_text)
    notice_period = extract_notice_period(body_text)
    positions = extract_number_of_positions(body_text)
    
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
    employment_type = determine_employment_type(body_text)
    work_mode = determine_work_mode(body_text)
    priority = determine_priority(body_text)
    experience_level = determine_experience_level(experience)
    
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
        "job_title": subject,
        "job_status": "Open",
        "closed_date": "N/A",
        "type_of_demand": "Single",
        "priority": priority,
        "number_of_positions": positions,
        "experience_level": experience_level,
        "employment_type": employment_type,
        "budget_currency": "INR",
        "yearly_budget": budget_info["yearly_budget"] or "Not provided",
        "monthly_budget": budget_info["monthly_budget"] or "Not provided",
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

def comprehensive_yesterday_extraction():
    """Extract all yesterday's client requirements comprehensively"""
    
    # Load all available data sources
    data_sources = [
        "today_fetch.csv",
        "today_fetch_2026-04-20.csv", 
        "today_fetch_2026-04-16.csv",
        "structured_recruitment_data.csv"
    ]
    
    all_requirements = []
    processed_ids = set()
    
    # Process CSV files
    for csv_file in data_sources:
        if Path(csv_file).exists():
            print(f"Processing {csv_file}...")
            try:
                with open(csv_file, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        # Filter for yesterday's date (2026-04-22) and client emails
                        received_date = row.get('received_date_time', '')
                        if '2026-04-22' in received_date or '2026-04-23' in received_date:
                            graph_id = row.get('graph_id', '')
                            if graph_id and graph_id not in processed_ids:
                                # Check if it's from a known client
                                client_key = row.get('source_vendor_key', '')
                                if client_key and client_key != 'unknown':
                                    processed_ids.add(graph_id)
                                    requirement = process_email_to_metaforge_format(row, len(all_requirements) + 1)
                                    all_requirements.append(requirement)
            except Exception as e:
                print(f"Error processing {csv_file}: {e}")
    
    # Also process JSON files
    json_files = [
        "today_client_emails_exhaustive_2026-04-22.json",
        "today_client_emails_exhaustive_2026-04-23.json"
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
                                requirement = process_email_to_metaforge_format(email, len(all_requirements) + 1)
                                all_requirements.append(requirement)
            except Exception as e:
                print(f"Error processing {json_file}: {e}")
    
    # Save comprehensive results
    output_json = "comprehensive_yesterday_requirements_2026-04-22.json"
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(all_requirements, f, indent=2, ensure_ascii=False)
    
    print(f"Extracted {len(all_requirements)} comprehensive requirements")
    print(f"Saved to {output_json}")
    
    return all_requirements

if __name__ == "__main__":
    requirements = comprehensive_yesterday_extraction()
