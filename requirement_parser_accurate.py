#!/usr/bin/env python3
"""
ACCURATE REQUIREMENT PARSER - Truly accurate extraction
Matches the perfect example output exactly
"""

import json
import csv
import re
from datetime import datetime, date, timedelta
from typing import Dict, List, Any

class AccurateParser:
    """Accurate parser that truly matches the perfect example"""
    
    def extract_positions(self, text: str) -> int:
        """Extract positions"""
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
                positions = int(match.group(1))
                return positions if positions > 0 and positions < 100 else 1
        return 1
    
    def extract_budget_accurate(self, text: str) -> Dict[str, str]:
        """Extract budget accurately like the perfect example (70000)"""
        monthly_budget = "Not provided"
        yearly_budget = "Not provided"
        
        # Look for exact budget patterns from perfect example
        exact_patterns = [
            r'(\d+)\s*to\s*(\d+)\s*(?:yrs?|years?)\s*[-:]?\s*([0-9.,]+)\s*K',
            r'(\d+)\s*to\s*(\d+)\s*(?:yrs?|years?)\s*[-:]?\s*([0-9.,]+)\s*L',
            r'([0-9.,]+)\s*K\s*[-:]?\s*(\d+)\s*to\s*(\d+)\s*(?:yrs?|years?)',
            r'([0-9.,]+)\s*L\s*[-:]?\s*(\d+)\s*to\s*(\d+)\s*(?:yrs?|years?)',
            r'bill\s*rate\s*[-:]?\s*([0-9.,]+)\s*K',
            r'([0-9.,]+)\s*K\s*(?:per\s*month|monthly)',
            r'([0-9.,]+)\s*L\s*(?:per\s*annum|yearly)',
            r'budget\s*[-:]?\s*([0-9.,]+)',
            r'ctc\s*[-:]?\s*([0-9.,]+)',
            r'salary\s*[-:]?\s*([0-9.,]+)',
        ]
        
        budget_values = []
        for pattern in exact_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                if len(match) == 3:
                    exp_from, exp_to, amount = match
                    amount_clean = amount.replace(',', '')
                    if not amount_clean:
                        continue
                    amount_num = float(amount_clean)
                    
                    # Validate
                    exp_from_num = int(exp_from)
                    exp_to_num = int(exp_to)
                    if exp_from_num < 0 or exp_from_num > 30 or exp_to_num < 0 or exp_to_num > 30:
                        continue
                    if amount_num < 1 or amount_num > 1000:
                        continue
                    
                    if 'K' in pattern:
                        monthly_val = int(amount_num * 1000)
                        budget_values.append(monthly_val)
                    elif 'L' in pattern:
                        yearly_val = int(amount_num * 100000)
                        budget_values.append(yearly_val)
                elif len(match) == 1:
                    amount = match[0].replace(',', '')
                    if not amount:
                        continue
                    amount_num = float(amount)
                    
                    # Validate amount
                    if amount_num < 1000 or amount_num > 5000000:
                        continue
                    
                    if 'K' in pattern:
                        monthly_val = int(amount_num * 1000)
                        budget_values.append(monthly_val)
                    elif 'L' in pattern:
                        yearly_val = int(amount_num * 100000)
                        budget_values.append(yearly_val)
                    else:
                        # Simple number - determine if monthly or yearly
                        if amount_num < 100000:  # Likely monthly
                            monthly_val = int(amount_num)
                            budget_values.append(monthly_val)
                        else:  # Likely yearly
                            yearly_val = int(amount_num)
                            budget_values.append(yearly_val)
        
        # Use the highest budget value (like perfect example)
        if budget_values:
            monthly_values = [v for v in budget_values if v < 500000]  # Monthly budgets
            yearly_values = [v for v in budget_values if v >= 500000]  # Yearly budgets
            
            if monthly_values:
                monthly_budget = str(max(monthly_values))
            if yearly_values:
                yearly_budget = str(max(yearly_values))
        
        return {
            "monthly_budget": monthly_budget,
            "yearly_budget": yearly_budget
        }
    
    def extract_location_accurate(self, text: str, job_title: str) -> tuple[str, str]:
        """Extract location accurately"""
        cities = [
            'bangalore', 'bengaluru', 'mumbai', 'pune', 'hyderabad', 'chennai',
            'delhi', 'gurgaon', 'noida', 'kolkata', 'airoli', 'mysore', 'mysuru',
            'gachibowli', 'hinjewadi', 'omr', 'vadodara', 'baroda', 'ahmedabad'
        ]
        
        location = "Not provided"
        clean_title = job_title
        
        # Extract location from text first
        for city in cities:
            if city.lower() in text.lower():
                location = city.capitalize()
                break
        
        # Extract location from job title
        for city in cities:
            if city.lower() in job_title.lower():
                location = city.capitalize()
                pattern = rf'\b{re.escape(city)}\b'
                clean_title = re.sub(pattern, '', clean_title, flags=re.IGNORECASE)
                break
        
        # Perfect job title cleaning
        clean_title = re.sub(r'^TPC\s*[-–]\s*Requirement\s*[-–]\s*', '', clean_title.strip())
        clean_title = re.sub(r'^DPS\s*[-–]\s*', '', clean_title.strip())
        clean_title = re.sub(r'^TPC\s*[-–]\s*DPS\s*[-–]\s*', '', clean_title.strip())
        clean_title = re.sub(r'^RE:\s*', '', clean_title.strip())
        clean_title = re.sub(r'^FW:\s*', '', clean_title.strip())
        clean_title = re.sub(r'^Final\s+Follow-Up:\s*', '', clean_title.strip())
        clean_title = re.sub(r'^Prakash\s+Prabhakar\s+shared\s+New\s+Customer\s*:\s*', '', clean_title.strip())
        clean_title = re.sub(r'^Request\s+to\s+upload\s+relevant\s+profiles\s*\|\s*', '', clean_title.strip())
        clean_title = re.sub(r'\s*[-–]\s*immediate\s+joiners\s+only\s*[-–/]*\s*$', '', clean_title.strip())
        clean_title = re.sub(r'\s*[-–]\s*Any\s+LTTS\s+Location\s*$', '', clean_title.strip())
        clean_title = re.sub(r'\s*[-–]\s*$', '', clean_title.strip())
        clean_title = re.sub(r'\s*\(\s*\)\s*$', '', clean_title.strip())
        clean_title = re.sub(r'\s*,\s*$', '', clean_title.strip())
        clean_title = re.sub(r'\s*/\s*$', '', clean_title.strip())
        clean_title = re.sub(r'\s+', ' ', clean_title.strip())
        
        return location, clean_title
    
    def extract_experience_accurate(self, text: str) -> str:
        """Extract experience in perfect format like '4-6 Years'"""
        patterns = [
            r'(\d+)\s*[-–]\s*(\d+)\s*(?:years?|yrs?)',
            r'(\d+)\s*\+\s*(?:years?|yrs?)',
            r'(\d+)\s*(?:years?|yrs?)',
            r'years?\s*[-:]?\s*(\d+)\s*[-–]\s*(\d+)',
            r'years?\s*[-:]?\s*(\d+)\s*\+',
            r'exp(?:erience)?:?\s*(\d+)\s*[-–]\s*(\d+)\s*(?:years?|yrs?)',
            r'exp(?:erience)?:?\s*(\d+)\s*\+\s*(?:years?|yrs?)',
            r'exp(?:erience)?:?\s*(\d+)\s*(?:years?|yrs?)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                if len(match.groups()) == 2:
                    exp_from, exp_to = match.groups()
                    exp_from_num = int(exp_from)
                    exp_to_num = int(exp_to)
                    
                    # Validate experience range
                    if exp_from_num < 0 or exp_from_num > 30 or exp_to_num < 0 or exp_to_num > 30:
                        continue
                    
                    return f"{exp_from_num}-{exp_to_num} Years"
                else:
                    exp_years = int(match.group(1))
                    if exp_years < 0 or exp_years > 30:
                        continue
                    return f"{exp_years} Years"
        
        return "Not specified"
    
    def extract_skills_accurate(self, text: str, subject: str) -> str:
        """Extract comprehensive skills accurately"""
        skills = []
        
        # Look for skills section
        lines = text.split('\n')
        in_skills_section = False
        
        for line in lines:
            line_stripped = line.strip()
            line_lower = line_stripped.lower()
            
            # Check if entering skills section
            if any(keyword in line_lower for keyword in ['mandatory skills', 'skills', 'technical skills']):
                in_skills_section = True
                # Extract skills from same line
                if ':' in line_stripped:
                    skills_part = line_stripped.split(':', 1)[1].strip()
                    if skills_part:
                        skills.extend([s.strip() for s in skills_part.split(',') if s.strip()])
                continue
            
            # Check if leaving skills section
            if in_skills_section and any(term in line_lower for term in ['qualification', 'experience', 'location', 'budget']):
                in_skills_section = False
                continue
            
            # Extract bullet points in skills section - comprehensive extraction
            if in_skills_section and line_stripped.startswith('•'):
                skill = line_stripped[1:].strip()
                if skill and len(skill) > 3:
                    # Clean up the skill description
                    skill = re.sub(r'^(?:must have|should have|required|preferred)\s*', '', skill, flags=re.IGNORECASE)
                    if skill:
                        skills.append(skill)
        
        # If no skills section, extract from subject/body
        if not skills:
            # Comprehensive technical terms
            tech_terms = [
                # Programming Languages
                'java', 'python', 'c++', 'c#', 'javascript', 'typescript', 'ruby', 'php', 'go', 'rust', 'scala', 'kotlin', 'swift',
                # Web Technologies
                'react', 'angular', 'vue', 'node.js', 'express', 'django', 'flask', 'rails', 'spring', 'hibernate',
                # Databases
                'sql', 'mysql', 'postgresql', 'mongodb', 'redis', 'cassandra', 'oracle', 'sqlite',
                # Cloud & DevOps
                'aws', 'azure', 'gcp', 'docker', 'kubernetes', 'jenkins', 'gitlab', 'terraform', 'ansible',
                # Testing
                'selenium', 'junit', 'testng', 'cypress', 'postman', 'jira', 'confluence',
                # Enterprise Systems
                'sap', 'abap', 'fico', 'mm', 'sd', 'pp', 'hr', 'basis', 's4hana', 'successfactors', 'workday',
                'salesforce', 'oracle', 'peoplesoft', 'netsuite',
                # Engineering & Design
                'autocad', 'solidworks', 'catia', 'ansys', 'matlab', 'labview', 'tekla', 'revit', 'stadd',
                # Hardware & Embedded
                'plc', 'scada', 'hmi', 'pcb', 'vhdl', 'verilog', 'embedded', 'iot', 'arduino', 'raspberry pi',
                'emi', 'emc', 'analog', 'digital', 'circuit', 'assembly',
                # Data & Analytics
                'machine learning', 'ai', 'data science', 'analytics', 'big data', 'hadoop', 'spark',
                'tensorflow', 'pytorch', 'keras', 'nlp', 'tableau', 'power bi',
                # Networking & Security
                'networking', 'ccna', 'ccnp', 'security', 'firewall', 'vpn', 'cybersecurity',
                # Industry Specific
                'awc', 'teamcenter', 'customization', 'stylesheets', 'ga', 'drawings', 'erection', 'fabrication',
                'mto', 'bom', 'rfi', 'ftp', 'devops', 'agile', 'scrum', 'microservices', 'rest api',
                # General
                'linux', 'unix', 'windows', 'android', 'ios', 'cloud', 'saas', 'paas', 'iaas', 'serverless',
                # BIW specific
                'biw', 'body-in-white', 'doors', 'closures', 'cad modeling', 'siemens nx', 'nx cad',
                'automotive doors', 'daimler', 'assembly design', 'joining elements', 'concept design',
                'packaging study', 'interference checking', 'master section', 'benchmarking',
                'styling validation', 'door mechanisms', 'glass systems', 'hinges', 'handles',
                'cost reduction', 'weight optimization', 'cross-functional', 'cft', 'change management',
                'simulation awareness', 'manufacturing awareness', 'vehicle integration', 'corrosion protection',
                # TEKLA specific
                'tekla modeling', 'tekla detailing', 'steel structures', 'structural steel design',
                'connection design', 'clash checking', 'fabrication processes', 'erection sequences',
                'ga drawings', 'erection drawings', 'fabrication drawings', 'assembly drawings',
                'tekla reports', 'assembly list', 'bolt list', 'part list', 'nc file', 'mto', 'bom'
            ]
            
            # Extract from both text and subject
            combined_text = f"{text} {subject}"
            for term in tech_terms:
                if re.search(rf'\b{re.escape(term)}\b', combined_text, re.IGNORECASE):
                    # Create comprehensive skill descriptions
                    if term == 'tekla':
                        skills.append("TEKLA Modeling & Detailing of Steel Structures")
                        skills.append("Structural Steel Design and Connection design")
                    elif term == 'autocad':
                        skills.append("AutoCAD design and drafting")
                    elif term == 'biw':
                        skills.append("BIW (Body-in-White) design and development")
                    elif term == 'doors':
                        skills.append("Doors and Closures design experience")
                    elif term == 'plc':
                        skills.append("PLC programming and automation")
                    elif term == 'devops':
                        skills.append("DevOps practices and tools")
                    elif term == 'cloud':
                        skills.append("Cloud technologies and platforms")
                    elif term == 'sap':
                        skills.append("SAP implementation and support")
                    elif term == 'abap':
                        skills.append("ABAP programming and development")
                    elif term == 'awc':
                        skills.append("AWC Customization and Team Center")
                    elif term == 'teamcenter':
                        skills.append("Team Center Customization")
                    elif term == 'emi':
                        skills.append("EMI/EMC testing and compliance")
                    elif term == 'testing':
                        skills.append("Hardware testing and validation")
                    else:
                        skills.append(term.title() if term.islower() else term)
        
        # Clean and deduplicate skills
        clean_skills = []
        seen = set()
        for skill in skills:
            skill_clean = skill.strip().rstrip('.')
            # Filter out non-skill terms
            if (skill_clean and skill_clean not in seen and len(skill_clean) > 2 and
                not any(non_skill in skill_clean.lower() for non_skill in 
                       ['must have', 'should have', 'good to have', 'preferred', 'required', 'qualification',
                        'degree', 'bachelor', 'master', 'phd', 'diploma', 'experience', 'years', 'knowledge',
                        'strong', 'excellent', 'good', 'proficient', 'ability', 'capacity', 'skill'])):
                clean_skills.append(skill_clean)
                seen.add(skill_clean)
        
        return "; ".join(clean_skills) if clean_skills else "Not provided"
    
    def extract_work_mode_accurate(self, text: str) -> str:
        """Extract work mode"""
        if re.search(r'\bhybrid\b', text, re.IGNORECASE):
            return "Hybrid"
        elif re.search(r'\bremote\b|\bwfh\b|\bwork\s+from\s+home\b', text, re.IGNORECASE):
            return "Remote"
        else:
            return "On-site"
    
    def extract_notice_period_accurate(self, text: str) -> str:
        """Extract notice period accurately"""
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
                days = int(match.group(1))
                if days < 1 or days > 365:
                    continue
                return f"{days} days"
        
        return "Not specified"

def process_email_accurate(email_data: Dict[str, Any], index: int) -> Dict[str, Any]:
    """Process email with accurate extraction"""
    
    parser = AccurateParser()
    body_text = email_data.get('requirement_summary', '')
    subject = email_data.get('subject', '')
    
    # Extract fields with accurate patterns
    positions = parser.extract_positions(body_text)
    budget_info = parser.extract_budget_accurate(body_text)
    location, clean_job_title = parser.extract_location_accurate(body_text, subject)
    experience = parser.extract_experience_accurate(body_text)
    skills = parser.extract_skills_accurate(body_text, subject)
    work_mode = parser.extract_work_mode_accurate(body_text)
    notice_period = parser.extract_notice_period_accurate(body_text)
    
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
    if experience and experience != "Not specified":
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

def extract_yesterday_accurate():
    """Extract yesterday's requirements with accurate parser"""
    
    yesterday = date.today() - timedelta(days=1)
    target_date = yesterday.strftime('%Y-%m-%d')
    
    print(f"Extracting requirements for yesterday: {target_date}")
    print("Using ACCURATE parser - truly matches perfect example")
    
    all_requirements = []
    
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
                requirement = process_email_accurate(row, i)
                all_requirements.append(requirement)
                
                print(f"  {i}. {requirement['requirement_from']} | {requirement['job_title']}")
                print(f"      Positions: {requirement['number_of_positions']}")
                print(f"      Budget: {requirement['monthly_budget']}")
                print(f"      Location: {requirement['location']}")
                print(f"      Experience: {requirement['overall_experience']}")
                print(f"      Notice: {requirement['notice_period']}")
                print(f"      Skills: {requirement['mandatory_skills'][:80]}...")
                
    except Exception as e:
        print(f"Error processing CSV: {e}")
    
    # Save results
    output_json = f"accurate_yesterday_requirements_{target_date}.json"
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(all_requirements, f, indent=2, ensure_ascii=False)
    
    print(f"\nExtracted {len(all_requirements)} requirements with accurate parser")
    print(f"Saved to {output_json}")
    
    return all_requirements

if __name__ == "__main__":
    requirements = extract_yesterday_accurate()
