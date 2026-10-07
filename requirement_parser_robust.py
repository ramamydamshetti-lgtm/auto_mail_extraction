#!/usr/bin/env python3
"""
ROBUST REQUIREMENT PARSER - Works for ANY unseen client email
Universal patterns for maximum extraction accuracy across all email formats
"""

import json
import csv
import re
from datetime import datetime, date, timedelta
from typing import Dict, List, Any

class RobustFieldParser:
    """Robust parser that works for any email format"""
    
    def __init__(self):
        self.extracted_fields = {}
    
    def extract_positions_robust(self, text: str) -> int:
        """Extract positions with comprehensive patterns"""
        patterns = [
            # Direct patterns
            r'open\s*positions?\s*[-:]?\s*(\d+)',
            r'openings?\s*[-:]?\s*(\d+)',
            r'vacanc(?:y|ies)\s*[-:]?\s*(\d+)',
            r'headcount\s*[-:]?\s*(\d+)',
            r'no\s*of\s*positions?\s*[-:]?\s*(\d+)',
            r'number\s*of\s*positions?\s*[-:]?\s*(\d+)',
            r'(\d+)\s*positions?',
            r'(\d+)\s*openings?',
            r'(\d+)\s*vacanc(?:y|ies)?',
            
            # Context patterns
            r'positions?\s*[-:]?\s*(\d+)',
            r'opening[s]?\s*[-:]?\s*(\d+)',
            r'requirement[s]?\s*[-:]?\s*(\d+)',
            r'role[s]?\s*[-:]?\s*(\d+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                positions = int(match.group(1))
                return positions if positions > 0 else 1
        return 1
    
    def extract_budget_robust(self, text: str) -> Dict[str, str]:
        """Extract budget with comprehensive patterns"""
        monthly_budget = "Not provided"
        yearly_budget = "Not provided"
        
        # Experience-based budget ranges
        exp_budget_patterns = [
            r'(\d+)\s*[-–]\s*(\d+)\s*(?:yrs?|years?)\s*[-:]?\s*([0-9.,]+)\s*K',
            r'(\d+)\s*[-–]\s*(\d+)\s*(?:yrs?|years?)\s*[-:]?\s*([0-9.,]+)\s*L',
            r'([0-9.,]+)\s*K\s*[-:]?\s*(\d+)\s*[-–]\s*(\d+)\s*(?:yrs?|years?)',
            r'([0-9.,]+)\s*L\s*[-:]?\s*(\d+)\s*[-–]\s*(\d+)\s*(?:yrs?|years?)',
        ]
        
        budget_ranges = []
        for pattern in exp_budget_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                if len(match) == 3:
                    exp_from, exp_to, amount = match
                    amount_clean = amount.replace(',', '')
                    # Fix malformed patterns like "70-3 yrs"
                    if int(exp_from) > int(exp_to):
                        exp_from, exp_to = exp_to, exp_from
                    if 'K' in pattern:
                        budget_ranges.append(f"{exp_from}-{exp_to} yrs: {amount_clean}K/month")
                    elif 'L' in pattern:
                        budget_ranges.append(f"{exp_from}-{exp_to} yrs: {amount_clean}L/year")
        
        # Single budget values
        single_patterns = [
            r'bill\s*rate\s*[-:]?\s*([0-9.,]+)\s*K',
            r'([0-9.,]+)\s*K\s*(?:per\s*month|monthly|pm)',
            r'([0-9.,]+)\s*L\s*(?:per\s*annum|yearly|annual|pa)',
            r'budget\s*[-:]?\s*([0-9.,]+)\s*K',
            r'budget\s*[-:]?\s*([0-9.,]+)\s*L',
            r'ctc\s*[-:]?\s*([0-9.,]+)\s*K',
            r'ctc\s*[-:]?\s*([0-9.,]+)\s*L',
            r'salary\s*[-:]?\s*([0-9.,]+)\s*K',
            r'salary\s*[-:]?\s*([0-9.,]+)\s*L',
            r'package\s*[-:]?\s*([0-9.,]+)\s*K',
            r'package\s*[-:]?\s*([0-9.,]+)\s*L',
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
                    monthly_budget = f"{int(float(amount)) * 10}K/month"
                break
        
        # Use budget ranges if found
        if budget_ranges:
            monthly_budget = "; ".join([br for br in budget_ranges if 'K/month' in br])
            yearly_budget = "; ".join([br for br in budget_ranges if 'L/year' in br])
        
        return {
            "monthly_budget": monthly_budget,
            "yearly_budget": yearly_budget
        }
    
    def extract_location_robust(self, text: str, job_title: str) -> tuple[str, str]:
        """Extract location with comprehensive patterns"""
        cities = [
            'bangalore', 'bengaluru', 'mumbai', 'pune', 'hyderabad', 'chennai',
            'delhi', 'gurgaon', 'noida', 'kolkata', 'airoli', 'mysore', 'mysuru',
            'gachibowli', 'hinjewadi', 'omr', 'vadodara', 'baroda', 'ahmedabad',
            'jaipur', 'lucknow', 'indore', 'nagpur', 'coimbatore', 'kochi',
            'trivandrum', 'cochin', 'vizag', 'vijayawada', 'surat', 'bhopal'
        ]
        
        location = "Not provided"
        clean_title = job_title
        
        # Extract location from text
        for city in cities:
            if city.lower() in text.lower():
                location = city.capitalize()
                break
        
        # Extract location from job title
        for city in cities:
            if city.lower() in job_title.lower():
                location = city.capitalize()
                # Remove city from job title
                pattern = rf'\b{re.escape(city)}\b'
                clean_title = re.sub(pattern, '', clean_title, flags=re.IGNORECASE)
                break
        
        # Clean job title
        clean_title = re.sub(r'^TPC\s*[-–]\s*Requirement\s*[-–]\s*', '', clean_title.strip())
        clean_title = re.sub(r'^DPS\s*[-–]\s*', '', clean_title.strip())
        clean_title = re.sub(r'^RE:\s*', '', clean_title.strip())
        clean_title = re.sub(r'^FW:\s*', '', clean_title.strip())
        clean_title = re.sub(r'^Final\s+Follow-Up:\s*', '', clean_title.strip())
        clean_title = re.sub(r'\s*[-–]\s*$', '', clean_title.strip())
        clean_title = re.sub(r'\s*\(\s*\)\s*$', '', clean_title.strip())
        clean_title = re.sub(r'\s*,\s*$', '', clean_title.strip())
        clean_title = re.sub(r'\s*/\s*$', '', clean_title.strip())
        clean_title = re.sub(r'\s+', ' ', clean_title.strip())
        
        return location, clean_title
    
    def extract_experience_robust(self, text: str) -> str:
        """Extract experience with comprehensive patterns"""
        patterns = [
            r'(\d+)\s*[-–]\s*(\d+)\s*(?:years?|yrs?)',
            r'(\d+)\s*\+\s*(?:years?|yrs?)',
            r'(\d+)\s*(?:years?|yrs?)',
            r'exp(?:erience)?:?\s*(\d+)\s*[-–]\s*(\d+)\s*(?:years?|yrs?)',
            r'exp(?:erience)?:?\s*(\d+)\s*\+\s*(?:years?|yrs?)',
            r'exp(?:erience)?:?\s*(\d+)\s*(?:years?|yrs?)',
            r'years?\s*[-:]?\s*(\d+)\s*[-–]\s*(\d+)',
            r'years?\s*[-:]?\s*(\d+)\s*\+',
            r'fresher|0\s*years?',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                if len(match.groups()) == 2:
                    exp_from, exp_to = match.groups()
                    return f"{exp_from}-{exp_to} years"
                elif 'fresher' in pattern.lower() or '0' in match.groups():
                    return "0 years"
                else:
                    return f"{match.group(1)} years"
        
        return "Not specified"
    
    def extract_skills_robust(self, text: str) -> str:
        """Extract skills with comprehensive patterns"""
        skills = []
        
        # Technical skills patterns
        tech_patterns = [
            r'(?i)skills?[:\-]\s*([^\n]+)',
            r'(?i)mandatory\s+skills?[:\-]\s*([^\n]+)',
            r'(?i)technical\s+skills?[:\-]\s*([^\n]+)',
            r'(?i)required\s+skills?[:\-]\s*([^\n]+)',
            r'(?i)key\s+skills?[:\-]\s*([^\n]+)',
            r'(?i)core\s+skills?[:\-]\s*([^\n]+)',
        ]
        
        for pattern in tech_patterns:
            match = re.search(pattern, text)
            if match:
                skills_text = match.group(1).strip()
                # Split by common separators
                skill_list = re.split(r'[,;]\s*', skills_text)
                for skill in skill_list:
                    skill = skill.strip()
                    if skill and len(skill) > 2 and not skill.lower().startswith(('and', 'or', 'with')):
                        skills.append(skill)
                break
        
        # If no explicit skills section, look for technical terms
        if not skills:
            # Common technical skills
            tech_terms = [
                'java', 'python', 'c\+\+', 'c#', 'javascript', 'react', 'angular', 'vue',
                'node\.js', 'spring', 'hibernate', 'django', 'flask', 'rails', 'php',
                'html', 'css', 'bootstrap', 'tailwind', 'sql', 'mysql', 'postgresql',
                'mongodb', 'redis', 'aws', 'azure', 'gcp', 'docker', 'kubernetes',
                'jenkins', 'git', 'linux', 'unix', 'windows', 'mac', 'android',
                'ios', 'swift', 'kotlin', 'flutter', 'react native', ' xamarin',
                'machine learning', 'ai', 'data science', 'analytics', 'big data',
                'hadoop', 'spark', 'tensorflow', 'pytorch', 'keras', 'nlp',
                'selenium', 'junit', 'testng', 'cypress', 'postman', 'jira',
                'agile', 'scrum', 'devops', 'ci/cd', 'microservices', 'rest api',
                'graphql', 'soap', 'json', 'xml', 'yaml', 'markdown',
                'sap', 'abap', 'fico', 'mm', 'sd', 'pp', 'hr', 'basis',
                'salesforce', 'oracle', 'peoplesoft', 'workday', 'successfactors',
                'tekla', 'autocad', 'solidworks', 'catia', 'ansys', 'matlab',
                'labview', 'plc', 'scada', 'hmi', 'pcb', 'vhdl', 'verilog',
                'embedded', 'iot', 'arduino', 'raspberry pi', 'arduino',
                'networking', 'ccna', 'ccnp', 'security', 'firewall', 'vpn',
                'cloud', 'saas', 'paas', 'iaas', 'serverless', 'lambda'
            ]
            
            for term in tech_terms:
                if re.search(rf'\b{re.escape(term)}\b', text, re.IGNORECASE):
                    skills.append(term.title() if term.islower() else term)
        
        # Clean and deduplicate skills
        clean_skills = []
        seen = set()
        for skill in skills:
            skill_clean = skill.strip().rstrip('.')
            if skill_clean and skill_clean not in seen and len(skill_clean) > 2:
                clean_skills.append(skill_clean)
                seen.add(skill_clean)
        
        return "; ".join(clean_skills[:10]) if clean_skills else "Not provided"
    
    def extract_work_mode_robust(self, text: str) -> str:
        """Extract work mode with comprehensive patterns"""
        patterns = [
            (r'hybrid', 'Hybrid'),
            (r'wfo|work\s*from\s*office', 'On-site'),
            (r'remote|wfh|work\s*from\s*home', 'Remote'),
            (r'office|on[-\s]?site', 'On-site'),
            (r'work\s*mode[:\-]\s*(hybrid|remote|wfo|wfh)', lambda m: m.group(1).title() if m.group(1).lower() != 'wfo' else 'On-site'),
        ]
        
        for pattern, mode in patterns:
            if callable(mode):
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    return mode(match)
            else:
                if re.search(pattern, text, re.IGNORECASE):
                    return mode
        
        return "On-site"  # Default
    
    def extract_notice_period_robust(self, text: str) -> str:
        """Extract notice period with comprehensive patterns"""
        if 'immediate' in text.lower() or 'immediate joiner' in text.lower():
            return "Immediate"
        
        patterns = [
            r'(\d+)\s*(?:days?|months?)\s*(?:notice|notice\s*period)',
            r'notice\s*period\s*[-:]?\s*(\d+)\s*(?:days?|months?)',
            r'np\s*[-:]?\s*(\d+)\s*(?:days?|months?)',
            r'joining\s*time\s*[-:]?\s*(\d+)\s*(?:days?|months?)',
            r'join\s*time\s*[-:]?\s*(\d+)\s*(?:days?|months?)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return f"{match.group(1)} days"
        
        return "Not specified"

def process_email_robust(email_data: Dict[str, Any], index: int) -> Dict[str, Any]:
    """Process email with robust field extraction"""
    
    parser = RobustFieldParser()
    body_text = email_data.get('requirement_summary', '')
    subject = email_data.get('subject', '')
    
    # Extract fields with robust patterns
    positions = parser.extract_positions_robust(body_text)
    budget_info = parser.extract_budget_robust(body_text)
    location, clean_job_title = parser.extract_location_robust(body_text, subject)
    experience = parser.extract_experience_robust(body_text)
    skills = parser.extract_skills_robust(body_text)
    work_mode = parser.extract_work_mode_robust(body_text)
    notice_period = parser.extract_notice_period_robust(body_text)
    
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
    
    # Determine experience level
    exp_level = "Mid Senior"
    if experience:
        exp_num = re.search(r'(\d+)', experience)
        if exp_num:
            years = int(exp_num.group(1))
            if years <= 2:
                exp_level = "Junior"
            elif years >= 8:
                exp_level = "Senior"
    
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
        "experience_level": exp_level,
        "employment_type": "Contract",
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

def extract_yesterday_robust():
    """Extract yesterday's requirements with robust patterns"""
    
    yesterday = date.today() - timedelta(days=1)
    target_date = yesterday.strftime('%Y-%m-%d')
    
    print(f"Extracting requirements for yesterday: {target_date}")
    print("Using ROBUST parser - works for ANY unseen client email")
    
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
                requirement = process_email_robust(row, i)
                all_requirements.append(requirement)
                
                print(f"  {i}. {requirement['requirement_from']} | {requirement['job_title']}")
                print(f"      Positions: {requirement['number_of_positions']}")
                print(f"      Budget: {requirement['monthly_budget']}")
                print(f"      Location: {requirement['location']}")
                print(f"      Skills: {requirement['mandatory_skills'][:80]}...")
                
    except Exception as e:
        print(f"Error processing CSV: {e}")
    
    # Save results
    output_json = f"robust_yesterday_requirements_{target_date}.json"
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(all_requirements, f, indent=2, ensure_ascii=False)
    
    print(f"\nExtracted {len(all_requirements)} requirements with robust patterns")
    print(f"Saved to {output_json}")
    
    return all_requirements

if __name__ == "__main__":
    requirements = extract_yesterday_robust()
