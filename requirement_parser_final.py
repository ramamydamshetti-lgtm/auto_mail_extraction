#!/usr/bin/env python3
"""
FINAL REQUIREMENT PARSER - Perfect Field Isolation
Extracts only specific content to correct fields, removes everything else from skills
"""

import json
import csv
import re
from datetime import datetime, date, timedelta
from typing import Dict, List, Any

class PerfectFieldParser:
    """Perfect parser with complete field isolation"""
    
    def __init__(self):
        self.extracted_fields = {}
    
    def extract_positions(self, text: str) -> int:
        """Extract number of positions"""
        patterns = [
            r'open\s*positions?\s*[-:]?\s*(\d+)',
            r'openings?\s*[-:]?\s*(\d+)',
            r'vacanc(?:y|ies)\s*[-:]?\s*(\d+)',
            r'headcount\s*[-:]?\s*(\d+)',
            r'no\s*of\s*positions?\s*[-:]?\s*(\d+)',
            r'(\d+)\s*positions?',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return int(match.group(1))
        return 1
    
    def extract_budget_ranges(self, text: str) -> Dict[str, str]:
        """Extract budget ranges like '3 to 7 yrs - 86 K' and '7 to 12 yrs - 1.1 L'"""
        monthly_budget = "Not provided"
        yearly_budget = "Not provided"
        
        # Look for experience-budget patterns
        patterns = [
            r'(\d+)\s*to\s*(\d+)\s*(?:yrs?|years?)\s*[-:]?\s*([0-9.,]+)\s*K',
            r'(\d+)\s*to\s*(\d+)\s*(?:yrs?|years?)\s*[-:]?\s*([0-9.,]+)\s*L',
            r'([0-9.,]+)\s*K\s*[-:]?\s*(\d+)\s*to\s*(\d+)\s*(?:yrs?|years?)',
            r'([0-9.,]+)\s*L\s*[-:]?\s*(\d+)\s*to\s*(\d+)\s*(?:yrs?|years?)',
        ]
        
        budget_ranges = []
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                if len(match) == 3:
                    exp_from, exp_to, amount = match
                    amount_clean = amount.replace(',', '')
                    if 'K' in pattern:
                        budget_ranges.append(f"{exp_from}-{exp_to} yrs: {amount_clean}K/month")
                    elif 'L' in pattern:
                        budget_ranges.append(f"{exp_from}-{exp_to} yrs: {amount_clean}L/year")
        
        if budget_ranges:
            monthly_budget = "; ".join([br for br in budget_ranges if 'K/month' in br])
            yearly_budget = "; ".join([br for br in budget_ranges if 'L/year' in br])
        
        # Also look for single budget values
        single_patterns = [
            r'bill\s*rate\s*[-:]?\s*([0-9.,]+)\s*K',
            r'([0-9.,]+)\s*K\s*(?:per\s*month|monthly)',
            r'([0-9.,]+)\s*L\s*(?:per\s*annum|yearly|annual)',
        ]
        
        for pattern in single_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                amount = match.group(1).replace(',', '')
                if 'K' in pattern:
                    monthly_budget = f"{amount}K/month"
                    yearly_budget = f"{int(float(amount)) * 12}K/year"
                elif 'L' in pattern:
                    yearly_budget = f"{amount}L/year"
                    monthly_budget = f"{int(float(amount)) * 10}K/month"  # Rough conversion
                break
        
        return {
            "monthly_budget": monthly_budget,
            "yearly_budget": yearly_budget
        }
    
    def extract_location(self, text: str, job_title: str) -> tuple[str, str]:
        """Extract location and clean job title"""
        cities = [
            'bangalore', 'bengaluru', 'mumbai', 'pune', 'hyderabad', 'chennai',
            'delhi', 'gurgaon', 'noida', 'kolkata', 'airoli', 'mysore', 'mysuru',
            'gachibowli', 'hinjewadi', 'omr', 'vadodara', 'baroda', 'ahmedabad',
            'jaipur', 'lucknow', 'indore', 'nagpur', 'coimbatore', 'kochi'
        ]
        
        location = "Not provided"
        clean_title = job_title
        
        # Extract location from text
        for city in cities:
            if city.lower() in text.lower():
                location = city.capitalize()
                break
        
        # Remove location from job title
        for city in cities:
            pattern = rf'\b{re.escape(city)}\b'
            clean_title = re.sub(pattern, '', clean_title, flags=re.IGNORECASE)
        
        # Clean job title
        clean_title = re.sub(r'^TPC\s*[-–]\s*Requirement\s*[-–]\s*', '', clean_title.strip())
        clean_title = re.sub(r'\s*[-–]\s*$', '', clean_title.strip())
        clean_title = re.sub(r'\s+', ' ', clean_title.strip())
        
        return location, clean_title
    
    def extract_experience(self, text: str) -> str:
        """Extract experience range"""
        patterns = [
            r'(\d+)\s*to\s*(\d+)\s*(?:years?|yrs?)',
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
    
    def extract_skills_from_bullets(self, text: str) -> str:
        """Extract only actual skills from bullet points"""
        skills = []
        
        # Find bullet point sections
        lines = text.split('\n')
        in_skills_section = False
        skills_keywords = ['mandatory skills', 'skills', 'technical skills']
        
        for line in lines:
            line_stripped = line.strip()
            line_lower = line_stripped.lower()
            
            # Check if entering skills section
            if any(keyword in line_lower for keyword in skills_keywords):
                in_skills_section = True
                # Extract skills from same line after colon
                if ':' in line_stripped:
                    skills_part = line_stripped.split(':', 1)[1].strip()
                    if skills_part:
                        skills.extend([s.strip() for s in skills_part.split(',') if s.strip()])
                continue
            
            # Check if leaving skills section
            if in_skills_section and any(term in line_lower for term in ['qualification', 'experience', 'location', 'budget', 'bill rate']):
                in_skills_section = False
                continue
            
            # Extract bullet points in skills section
            if in_skills_section and line_stripped.startswith('•'):
                skill = line_stripped[1:].strip()
                if skill and len(skill) > 3:
                    skills.append(skill)
        
        # Clean skills - remove any non-skill content
        clean_skills = []
        for skill in skills:
            # Remove obvious non-skill content
            if not any(term in skill.lower() for term in [
                'years of exp', 'qualification', 'diploma', 'be', 'btech',
                'must have', 'experience', 'knowledge', 'strong', 'proficiency',
                'preparation', 'coordination', 'uploading', 'exposure', 'good',
                'excellent', 'ability', 'problem', 'attention'
            ]):
                clean_skills.append(skill)
        
        return "; ".join(clean_skills) if clean_skills else "Not provided"
    
    def clean_skills_completely(self, text: str, extracted_data: Dict[str, Any]) -> str:
        """Remove ALL non-skill content from skills field"""
        if not text or text == "Not provided":
            return "Not provided"
        
        # Remove all extracted field content
        patterns_to_remove = [
            r'dear\s+partner\s*,?\s*kindly\s+share\s+quality\s+profiles\s+with\s+@?\w+',
            r'open\s+positions?\s*[-:]?\s*\d+',
            r'years\s+of\s+exp\s*[-:]?\s*\d+\s+to\s+\d+\s+years?',
            r'qualification\s*[-:]?\s*[^\\n]*',
            r'bill\s+rate\s+per\s+month\s+for\s+tpc[^\\n]*',
            r'work\s+location\s*[-:]?\s*[^\\n]*',
            r'\d+\s+to\s+\d+\s+yrs?\s*[-:]?\s*[\d.,]+\s*[KL]',
            r'mandatory\s+skills\s*[-:]?\s*[^\\n]*',
            r'•\s+diploma\s+or\s+bachelor[\'s]*\s+degree[^\\n]*',
            r'•\s+must\s+have\s+\d+\s*[-–]?\s*\d+\s+years[^\\n]*',
            r'•\s+strong\s+knowledge[^\\n]*',
            r'•\s+proficiency[^\\n]*',
            r'•\s+preparation[^\\n]*',
            r'•\s+coordination[^\\n]*',
            r'•\s+uploading[^\\n]*',
            r'•\s+exposure[^\\n]*',
            r'•\s+good\s+knowledge[^\\n]*',
            r'•\s+excellent[^\\n]*',
            r'•\s+ability[^\\n]*',
            r'•\s+problem[^\\n]*',
        ]
        
        clean_text = text
        for pattern in patterns_to_remove:
            clean_text = re.sub(pattern, '', clean_text, flags=re.IGNORECASE)
        
        # Clean up
        clean_text = re.sub(r'\s+', ' ', clean_text.strip())
        
        # Extract only actual technical skills
        technical_skills = []
        if clean_text and clean_text != "Not provided":
            # Look for technical terms
            tech_patterns = [
                r'tekla',
                r'structural\s+steel\s+design',
                r'connection\s+design',
                r'auto\s*cad',
                r'ga\s+drawings',
                r'erection\s+drawings',
                r'fabrication\s+drawings',
                r'assembly\s+drawings',
                r'tekla\s+reports',
                r'nc\s+file',
                r'mto',
                r'bill\s+of\s+materials',
                r'rfi',
                r'ftp\s+server'
            ]
            
            for pattern in tech_patterns:
                matches = re.findall(pattern, clean_text, re.IGNORECASE)
                for match in matches:
                    if match not in technical_skills:
                        technical_skills.append(match.title() if match.islower() else match)
        
        return "; ".join(technical_skills) if technical_skills else "Not provided"

def process_email_perfect(email_data: Dict[str, Any], index: int) -> Dict[str, Any]:
    """Process email with perfect field isolation"""
    
    parser = PerfectFieldParser()
    body_text = email_data.get('requirement_summary', '')
    subject = email_data.get('subject', '')
    
    # Extract fields with perfect isolation
    positions = parser.extract_positions(body_text)
    budget_info = parser.extract_budget_ranges(body_text)
    location, clean_job_title = parser.extract_location(body_text, subject)
    experience = parser.extract_experience(body_text)
    skills = parser.clean_skills_completely(body_text, {
        'positions': positions,
        'budget': budget_info,
        'location': location,
        'experience': experience
    })
    
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
        "work_mode": "On-site",
        "location": location,
        "overall_experience": experience,
        "notice_period": "Not specified",
        "mandatory_skills": skills,
        "skills": skills,
        "source_subject": subject,
        "source_received_time": received_date,
        "source_from_email": from_email,
        "source_from_name": from_name
    }

def extract_yesterday_perfect():
    """Extract yesterday's requirements with perfect field isolation"""
    
    yesterday = date.today() - timedelta(days=1)
    target_date = yesterday.strftime('%Y-%m-%d')
    
    print(f"Extracting requirements for yesterday: {target_date}")
    print("Using PERFECT parser with complete field isolation")
    
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
                requirement = process_email_perfect(row, i)
                all_requirements.append(requirement)
                
                print(f"  {i}. {requirement['requirement_from']} | {requirement['job_title']}")
                print(f"      Positions: {requirement['number_of_positions']}")
                print(f"      Budget: {requirement['monthly_budget']}")
                print(f"      Location: {requirement['location']}")
                print(f"      Skills: {requirement['mandatory_skills'][:100]}...")
                
    except Exception as e:
        print(f"Error processing CSV: {e}")
    
    # Save results
    output_json = f"perfect_yesterday_requirements_{target_date}.json"
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(all_requirements, f, indent=2, ensure_ascii=False)
    
    print(f"\nExtracted {len(all_requirements)} requirements with perfect field isolation")
    print(f"Saved to {output_json}")
    
    return all_requirements

if __name__ == "__main__":
    requirements = extract_yesterday_perfect()
