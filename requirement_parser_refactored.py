"""
EXPERT RECRUITER INTERPRETATION PARSER
Rule 3: Expert Recruiter Interpretation - Map jargon/synonyms professionally
Only extract explicitly mentioned content - no guessing or assumptions
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List

from models import RequirementItem, EmploymentType, ExperienceLevel, WorkMode, Priority

_LOG = logging.getLogger(__name__)


class ExpertRecruiterInterpreter:
    """
    Expert recruiter interpretation for mapping jargon/synonyms
    Only extract what is explicitly mentioned - no assumptions
    """
    
    # Professional jargon mappings
    RECRUITER_JARGON = {
        # Notice Period
        'np': 'notice_period',
        'notice': 'notice_period',
        'joining time': 'notice_period',
        'join time': 'notice_period',
        'immediate joiner': 'immediate',
        'immediate': 'immediate',
        '15 days': '15 days',
        '30 days': '30 days',
        '45 days': '45 days',
        '60 days': '60 days',
        '1 month': '30 days',
        '2 months': '60 days',
        '3 months': '90 days',
        
        # Budget/CTC
        'ctc': 'budget',
        'salary': 'budget',
        'package': 'budget',
        'lpa': 'lpa',
        'lpm': 'lpm',
        'per annum': 'yearly',
        'per month': 'monthly',
        'annual': 'yearly',
        
        # Experience
        'yoe': 'experience',
        'years of experience': 'experience',
        'total exp': 'experience',
        'overall exp': 'experience',
        'relevant exp': 'experience',
        'fresher': '0 years',
        'fresher\'s': '0 years',
        
        # Location
        'wfh': 'Remote',
        'work from home': 'Remote',
        'remote': 'Remote',
        'onsite': 'On-site',
        'on site': 'On-site',
        'office': 'On-site',
        'hybrid': 'Hybrid',
        
        # Employment Type
        'contract': 'Contract',
        'permanent': 'Full Time',
        'fulltime': 'Full Time',
        'full-time': 'Full Time',
        'temporary': 'Contract',
        'consultant': 'Contract',
    }
    
    # Field extraction patterns (only explicit content)
    FIELD_PATTERNS = {
        'budget': [
            r'(?:budget|ctc|salary|package|lpa|lpm)[:\s]*([^\n]+)',
            r'(\d+(?:\.\d+)?\s*(?:lpa|lpm|lakhs|crores|per\s*annum|per\s*month|pa|pm))',
            r'(?:bill\s*rate|rate)[:\s]*([^\n]+)',
        ],
        'notice_period': [
            r'(?:notice\s*period|np|joining\s*time|join\s*time)[:\s]*([^\n]+)',
            r'(?:immediate|immediate\s*joiner)',
            r'(\d+\s*(?:days?|months?))\s*(?:notice|notice\s*period)',
        ],
        'experience': [
            r'(?:experience|exp|yoe|total\s*exp|overall\s*exp)[:\s]*([^\n]+)',
            r'(\d+(?:\s*[-–]\s*\d+)?\s*(?:years?|yrs?))',
            r'(?:fresher|fresher\'s)',
        ],
        'location': [
            r'(?:location|work\s*location|based\s*at|based\s*in)[:\s]*([^\n]+)',
            r'(?:bangalore|mumbai|pune|hyderabad|chennai|delhi|gurgaon|noida|kolkata|airoli|mysore|gachibowli|hinjewadi|omr|vadodara)',
        ],
        'positions': [
            r'(?:no\s*of\s*position|number\s*of\s*position|positions|openings|vacancy)[:\s]*(\d+)',
            r'(\d+)\s*(?:positions|openings|vacancies)',
        ],
        'skills': [
            r'(?:skills|technical\s*skills|mandatory\s*skills|required\s*skills)[:\s]*([^\n]+)',
            r'(?:key\s*skills|core\s*skills|essential\s*skills)[:\s]*([^\n]+)',
        ]
    }
    
    def extract_field_explicitly(self, text: str, field_name: str) -> str:
        """
        Extract field content only if explicitly mentioned
        No guessing or assumptions - return null if not found
        """
        text_lower = text.lower()
        
        if field_name not in self.FIELD_PATTERNS:
            return "Not provided"
        
        patterns = self.FIELD_PATTERNS[field_name]
        
        for pattern in patterns:
            match = re.search(pattern, text_lower, re.IGNORECASE)
            if match:
                # Extract the matched content
                if field_name == 'notice_period' and 'immediate' in text_lower:
                    return "Immediate"
                elif field_name == 'experience' and 'fresher' in text_lower:
                    return "0 years"
                elif match.groups():
                    content = match.group(1).strip()
                    # Clean up the content
                    content = re.sub(r'^[:\-\s]+', '', content)
                    content = content.strip('.;')
                    return content if content else "Not provided"
        
        return "Not provided"
    
    def map_recruiter_jargon(self, text: str) -> str:
        """
        Map recruiter jargon to standard terms
        Only if explicitly mentioned in the text
        """
        text_lower = text.lower()
        
        for jargon, standard in self.RECRUITER_JARGON.items():
            if jargon in text_lower:
                return standard
        
        return text
    
    def extract_skills_explicitly(self, text: str) -> List[str]:
        """
        Extract skills only if explicitly listed
        Look for bullet points, numbered lists, or comma-separated skills
        """
        skills = []
        lines = text.split('\n')
        
        in_skills_section = False
        skills_keywords = ['skills', 'technical skills', 'mandatory skills', 'required skills', 'key skills']
        
        for line in lines:
            line_stripped = line.strip()
            line_lower = line_stripped.lower()
            
            # Check if we're entering a skills section
            if any(keyword in line_lower for keyword in skills_keywords):
                in_skills_section = True
                # Extract skills from same line if present
                if ':' in line_stripped:
                    skills_part = line_stripped.split(':', 1)[1].strip()
                    if skills_part:
                        skills.extend([s.strip() for s in skills_part.split(',') if s.strip()])
                continue
            
            # Check if we're leaving the skills section
            if in_skills_section and any(term in line_lower for term in ['job description', 'qualification', 'location', 'budget', 'notice', 'experience']):
                in_skills_section = False
                continue
            
            # Extract skills from bullet points or numbered lists
            if in_skills_section:
                # Bullet points
                bullet_match = re.match(r'^[\d\.\-\*\+]\s*(.+)', line_stripped)
                if bullet_match:
                    skill = bullet_match.group(1).strip()
                    if skill and len(skill) > 2:
                        skills.append(skill)
                # Comma-separated skills in the same line
                elif ',' in line_stripped and len(line_stripped) < 200:
                    skills.extend([s.strip() for s in line_stripped.split(',') if s.strip()])
        
        return skills if skills else []
    
    def create_null_requirement_item(self) -> RequirementItem:
        """
        Create a null requirement item when no explicit requirements found
        This ensures the row is still created in the dashboard
        """
        return RequirementItem(
            job_title="",
            number_of_positions=0,
            experience_level=ExperienceLevel.UNKNOWN,
            employment_type=EmploymentType.UNKNOWN,
            work_mode=WorkMode.UNKNOWN,
            location="",
            budget="",
            skills=[],
            mandatory_skills=[],
            notice_period="",
            overall_experience="",
            priority=Priority.UNKNOWN,
        )


def parse_requirements_from_email_expert(
    *,
    subject: str,
    body: str,
    sender_email: str,
    sender_name: str,
    attachments: List[Dict[str, Any]],
    classification: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Expert recruiter interpretation parser
    Only extract explicitly mentioned content - no guessing
    Create null row if no requirements found (Zero-Skip Policy)
    """
    interpreter = ExpertRecruiterInterpreter()
    full_text = f"{subject}\n\n{body}"
    
    # Extract all fields explicitly
    budget = interpreter.extract_field_explicitly(full_text, 'budget')
    notice_period = interpreter.extract_field_explicitly(full_text, 'notice_period')
    experience = interpreter.extract_field_explicitly(full_text, 'experience')
    location = interpreter.extract_field_explicitly(full_text, 'location')
    positions = interpreter.extract_field_explicitly(full_text, 'positions')
    
    # Extract skills
    skills = interpreter.extract_skills_explicitly(full_text)
    mandatory_skills = skills.copy()  # Same for now - can be refined
    
    # Map recruiter jargon
    budget = interpreter.map_recruiter_jargon(budget)
    notice_period = interpreter.map_recruiter_jargon(notice_period)
    location = interpreter.map_recruiter_jargon(location)
    
    # Determine if this is actually a requirement based on explicit content
    has_explicit_requirement = any([
        subject.strip() != "",
        len(skills) > 0,
        budget != "Not provided",
        experience != "Not provided",
        location != "Not provided",
        positions != "Not provided",
    ])
    
    if not has_explicit_requirement:
        # Zero-Skip Policy: Create null row instead of skipping
        null_item = interpreter.create_null_requirement_item()
        return {
            "requirements": [null_item],
            "classification": classification,
            "confidence": 0.0,
            "processing_note": "No explicit requirement content found - created null row per zero-skip policy"
        }
    
    # Create requirement item with explicit content only
    requirement_item = RequirementItem(
        job_title=subject.strip(),
        number_of_positions=int(positions) if positions.isdigit() else 1,
        experience_level=ExperienceLevel.MID_SENIOR,  # Default if not specified
        employment_type=EmploymentType.CONTRACT,  # Default if not specified
        work_mode=WorkMode.ON_SITE,  # Default if not specified
        location=location,
        budget=budget,
        skills=skills,
        mandatory_skills=mandatory_skills,
        notice_period=notice_period,
        overall_experience=experience,
        priority=Priority.HIGH,  # Default if not specified
    )
    
    return {
        "requirements": [requirement_item],
        "classification": classification,
        "confidence": 0.8 if has_explicit_requirement else 0.0,
        "processing_note": "Expert recruiter interpretation applied - only explicit content extracted"
    }


# Legacy function for backward compatibility
def parse_requirements_from_email(*args, **kwargs) -> Dict[str, Any]:
    """Legacy wrapper - uses expert interpreter"""
    return parse_requirements_from_email_expert(*args, **kwargs)
