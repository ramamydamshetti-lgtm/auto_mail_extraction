#!/usr/bin/env python3
"""
FIXED REQUIREMENT PARSER - Strict Field Isolation
Field Isolation: Extract specific field values and place them in correct fields
Positional Synonyms: Map 'Open Positions' → number_of_positions
Budget/Bill Rate Mapping: Map 'Monthly Bill' → monthly_budget
Location Cleaning: Extract cities from job_title to location field
Work Mode: Map 'Hybrid/WFO/Remote/WFH' → work_mode field
"""

import json
import csv
import re
from datetime import datetime, date, timedelta
from typing import Dict, List, Any

class FixedFieldParser:
    """Fixed parser with strict field isolation"""
    
    # Positional synonyms for number_of_positions
    POSITIONAL_SYNONYMS = [
        r'open\s*positions?\s*[-:]?\s*(\d+)',
        r'openings?\s*[-:]?\s*(\d+)',
        r'vacanc(?:y|ies)\s*[-:]?\s*(\d+)',
        r'headcount\s*[-:]?\s*(\d+)',
        r'no\s*of\s*positions?\s*[-:]?\s*(\d+)',
        r'number\s*of\s*positions?\s*[-:]?\s*(\d+)',
    ]
    
    # Budget/Bill rate patterns
    BUDGET_PATTERNS = [
        r'monthly\s*bill\s*(?:rate)?\s*[-:]?\s*([\d,]+)',
        r'bill\s*rate\s*[-:]?\s*([\d,]+)',
        r'per\s*month\s*[-:]?\s*([\d,]+)',
        r'monthly\s*ctc\s*[-:]?\s*([\d,]+)',
        r'bill\s*rate\s*per\s*month\s*[-:]?\s*([\d,]+)',
        r'budget\s*[-:]?\s*([\d,]+)',
        r'lpm\s*[-:]?\s*([\d,]+)',
        r'lpa\s*[-:]?\s*([\d,]+)',
    ]
    
    # Work mode patterns
    WORK_MODE_PATTERNS = [
        (r'hybrid', 'Hybrid'),
        (r'wfo|work\s*from\s*office', 'On-site'),
        (r'remote|wfh|work\s*from\s*home', 'Remote'),
        (r'office|on[-\s]?site', 'On-site'),
    ]
    
    # Cities for location extraction
    CITIES = [
        'bangalore', 'bengaluru', 'mumbai', 'pune', 'hyderabad', 'chennai',
        'delhi', 'gurgaon', 'noida', 'kolkata', 'airoli', 'mysore', 'mysuru',
        'gachibowli', 'hinjewadi', 'omr', 'vadodara', 'baroda', 'ahmedabad',
        'jaipur', 'lucknow', 'indore', 'nagpur', 'coimbatore', 'kochi'
    ]
    
    def __init__(self):
        self.extracted_fields = {}
    
    def extract_positions(self, text: str) -> int:
        """Extract number of positions using positional synonyms"""
        for pattern in self.POSITIONAL_SYNONYMS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return int(match.group(1))
        return 1
    
    def extract_budget(self, text: str) -> Dict[str, str]:
        """Extract budget with proper field mapping"""
        monthly_budget = "Not provided"
        yearly_budget = "Not provided"
        
        for pattern in self.BUDGET_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                amount = match.group(1).replace(',', '')
                
                # Determine if monthly or yearly
                pattern_lower = pattern.lower()
                if any(term in pattern_lower for term in ['monthly', 'bill', 'per month', 'lpm']):
                    monthly_budget = amount
                    # Calculate yearly automatically
                    yearly_budget = str(int(amount) * 12)
                elif 'lpa' in pattern_lower:
                    yearly_budget = amount + "LPA"
                else:
                    # Default to monthly if unclear
                    monthly_budget = amount
                    yearly_budget = str(int(amount) * 12)
                break
        
        return {
            "monthly_budget": monthly_budget,
            "yearly_budget": yearly_budget
        }
    
    def extract_work_mode(self, text: str) -> str:
        """Extract work mode with proper mapping"""
        text_lower = text.lower()
        for pattern, mode in self.WORK_MODE_PATTERNS:
            if re.search(pattern, text_lower):
                return mode
        return "On-site"  # Default
    
    def extract_location_from_title(self, job_title: str, text: str) -> tuple[str, str]:
        """Extract location from job_title and clean job_title"""
        locations_found = []
        clean_title = job_title
        
        # Find cities in job title
        for city in self.CITIES:
            if city.lower() in job_title.lower():
                locations_found.append(city.capitalize())
                # Remove city from job title
                clean_title = re.sub(f'\\b{re.escape(city)}\\b', '', clean_title, flags=re.IGNORECASE)
        
        # Find cities in text if not found in title
        if not locations_found:
            for city in self.CITIES:
                if city.lower() in text.lower():
                    locations_found.append(city.capitalize())
                    break
        
        # Clean up job title
        clean_title = re.sub(r'\s*[-–]\s*$', '', clean_title.strip())  # Remove trailing dash
        clean_title = re.sub(r'\s+', ' ', clean_title.strip())  # Clean up spaces
        
        location = "; ".join(locations_found) if locations_found else "Not provided"
        
        return location, clean_title
    
    def extract_experience(self, text: str) -> str:
        """Extract experience with proper field mapping"""
        patterns = [
            r'(\d+)\s*[-–]\s*(\d+)\s*(?:years?|yrs?)',
            r'(\d+)\s*\+\s*(?:years?|yrs?)',
            r'(\d+)\s*(?:years?|yrs?)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                if len(match.groups()) == 2:
                    return f"{match.group(1)}-{match.group(2)} years"
                else:
                    return f"{match.group(1)} years"
        
        return "Not specified"
    
    def extract_notice_period(self, text: str) -> str:
        """Extract notice period with proper mapping"""
        if 'immediate' in text.lower():
            return "Immediate"
        
        patterns = [
            r'(\d+)\s*(?:days?|months?)\s*(?:notice|notice\s*period)',
            r'notice\s*period\s*[-:]?\s*(\d+)\s*(?:days?|months?)',
            r'np\s*[-:]?\s*(\d+)\s*(?:days?|months?)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return f"{match.group(1)} days"
        
        return "Not specified"
    
    def clean_skills_field(self, skills_text: str, extracted_fields: Dict[str, Any]) -> str:
        """Remove extracted field values from skills text"""
        if not skills_text or skills_text == "Not provided":
            return "Not provided"
        
        clean_skills = skills_text
        
        # Remove budget information
        budget_patterns = [
            r'bill\s*rate\s*[-:]?\s*[\d,]+',
            r'monthly\s*bill\s*[-:]?\s*[\d,]+',
            r'budget\s*[-:]?\s*[\d,]+',
            r'lpm\s*[-:]?\s*[\d,]+',
            r'lpa\s*[-:]?\s*[\d,]+',
        ]
        
        for pattern in budget_patterns:
            clean_skills = re.sub(pattern, '', clean_skills, flags=re.IGNORECASE)
        
        # Remove positions information
        position_patterns = [
            r'open\s*positions?\s*[-:]?\s*\d+',
            r'openings?\s*[-:]?\s*\d+',
            r'vacanc(?:y|ies)\s*[-:]?\s*\d+',
            r'headcount\s*[-:]?\s*\d+',
        ]
        
        for pattern in position_patterns:
            clean_skills = re.sub(pattern, '', clean_skills, flags=re.IGNORECASE)
        
        # Remove work mode information
        work_mode_patterns = [
            r'work\s*mode\s*[-:]?\s*\w+',
            r'hybrid',
            r'wfo',
            r'remote',
            r'wfh',
        ]
        
        for pattern in work_mode_patterns:
            clean_skills = re.sub(pattern, '', clean_skills, flags=re.IGNORECASE)
        
        # Clean up bullet points and formatting
        clean_skills = re.sub(r'^[\s•\-\*]+', '', clean_skills, flags=re.MULTILINE)
        clean_skills = re.sub(r'\s*;\s*$', '', clean_skills)  # Remove trailing semicolon
        clean_skills = re.sub(r'\s+', ' ', clean_skills)  # Clean up spaces
        
        return clean_skills.strip() if clean_skills.strip() else "Not provided"

def process_email_fixed(email_data: Dict[str, Any], index: int) -> Dict[str, Any]:
    """Process email with fixed field isolation"""
    
    parser = FixedFieldParser()
    body_text = email_data.get('requirement_summary', '')
    subject = email_data.get('subject', '')
    
    # Extract fields with proper isolation
    positions = parser.extract_positions(body_text)
    budget_info = parser.extract_budget(body_text)
    work_mode = parser.extract_work_mode(body_text)
    experience = parser.extract_experience(body_text)
    notice_period = parser.extract_notice_period(body_text)
    
    # Extract location and clean job title
    location, clean_job_title = parser.extract_location_from_title(subject, body_text)
    
    # Get client information
    client_key = email_data.get('source_vendor_key', 'Unknown')
    client_display = email_data.get('source_vendor_display', client_key.upper())
    from_email = email_data.get('from_email', '')
    from_name = email_data.get('from_name', '')
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
    
    # Extract skills (will be cleaned)
    skills_text = body_text  # Use full body text for skills extraction
    clean_skills = parser.clean_skills_field(skills_text, {
        'budget': budget_info,
        'positions': positions,
        'work_mode': work_mode,
        'location': location
    })
    
    return {
        "job_id": job_id,
        "demand_received_date": demand_date,
        "internal_poc": "offshore demands",
        "requirement_from": client_display,
        "client_jd_id": client_jd_id,
        "client_lead_poc": from_email,
        "client_poc": from_email,
        "job_title": clean_job_title,
        "job_status": "Open",
        "closed_date": "N/A",
        "type_of_demand": "Multiple" if positions > 1 else "Single",
        "priority": "High",
        "number_of_positions": positions,
        "experience_level": "Mid Senior",
        "employment_type": "Contract",
        "budget_currency": "INR",
        "yearly_budget": budget_info["yearly_budget"],
        "monthly_budget": budget_info["monthly_budget"],
        "work_mode": work_mode,
        "location": location,
        "overall_experience": experience,
        "notice_period": notice_period,
        "mandatory_skills": clean_skills,
        "skills": clean_skills,
        "source_subject": subject,
        "source_received_time": received_date,
        "source_from_email": from_email,
        "source_from_name": from_name
    }

def extract_yesterday_fixed():
    """Extract yesterday's requirements with fixed field isolation"""
    
    yesterday = date.today() - timedelta(days=1)
    target_date = yesterday.strftime('%Y-%m-%d')
    
    print(f"Extracting requirements for yesterday: {target_date}")
    print("Using FIXED parser with strict field isolation")
    
    all_requirements = []
    
    # Process CSV file
    try:
        with open('today_fetch.csv', 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            requirement_emails = []
            
            for row in reader:
                received_date = row.get('received_date_time', '')
                if target_date in received_date:
                    client_key = row.get('source_vendor_key', '')
                    if client_key and client_key != 'unknown':
                        requirement_emails.append(row)
            
            print(f"Found {len(requirement_emails)} client emails")
            
            # Sort chronologically
            requirement_emails.sort(key=lambda x: x.get('received_date_time', ''))
            
            # Process each email
            for i, row in enumerate(requirement_emails, 1):
                requirement = process_email_fixed(row, i)
                all_requirements.append(requirement)
                
                print(f"  {i}. {requirement['requirement_from']} | {requirement['job_title']}")
                print(f"      Positions: {requirement['number_of_positions']}, Budget: {requirement['monthly_budget']}, Location: {requirement['location']}")
                
    except Exception as e:
        print(f"Error processing CSV: {e}")
    
    # Save results
    output_json = f"fixed_yesterday_requirements_{target_date}.json"
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(all_requirements, f, indent=2, ensure_ascii=False)
    
    print(f"\nExtracted {len(all_requirements)} requirements with fixed field isolation")
    print(f"Saved to {output_json}")
    
    return all_requirements

if __name__ == "__main__":
    requirements = extract_yesterday_fixed()
