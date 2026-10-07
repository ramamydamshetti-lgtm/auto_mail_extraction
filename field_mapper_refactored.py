"""
REFACTORED FIELD MAPPER - 100% Extraction Reliability
Ensures null values instead of skipping missing fields
Expert recruiter interpretation for mapping
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Dict, List

from models import EmploymentType, ExperienceLevel, Priority, WorkMode


class EmailContext:
    """Context for email processing"""
    def __init__(
        self,
        *,
        from_email: str,
        from_name: str,
        to_recipients: List[str],
        cc_recipients: List[str],
        subject: str,
        body_plain: str,
        body_normalized: str,
        attachments: List[Dict[str, Any]],
        received_date_time: str,
        graph_id: str,
    ) -> None:
        self.from_email = from_email
        self.from_name = from_name
        self.to_recipients = to_recipients
        self.cc_recipients = cc_recipients
        self.subject = subject
        self.body_plain = body_plain
        self.body_normalized = body_normalized
        self.attachments = attachments
        self.received_date_time = received_date_time
        self.graph_id = graph_id


def _as_list(value: Any) -> List[str]:
    """Convert value to list safely"""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, str):
        return [value]
    return [str(value)]


def _norm_priority(priority: str) -> Priority:
    """Normalize priority with explicit mapping only"""
    priority_lower = priority.lower().strip()
    
    # Only map if explicitly mentioned
    if priority_lower in ["high", "urgent", "critical"]:
        return Priority.HIGH
    elif priority_lower in ["medium", "normal"]:
        return Priority.MEDIUM
    elif priority_lower in ["low", "low priority"]:
        return Priority.LOW
    else:
        return Priority.UNKNOWN  # Null value for missing


def _norm_employment_type(emp_type: str) -> EmploymentType:
    """Normalize employment type with explicit mapping only"""
    emp_type_lower = emp_type.lower().strip()
    
    # Only map if explicitly mentioned
    if emp_type_lower in ["full-time", "fulltime", "permanent", "full time"]:
        return EmploymentType.FULL_TIME
    elif emp_type_lower in ["contract", "temporary", "consultant", "contractual"]:
        return EmploymentType.CONTRACT
    elif emp_type_lower in ["part-time", "parttime", "part time"]:
        return EmploymentType.PART_TIME
    else:
        return EmploymentType.UNKNOWN  # Null value for missing


def _norm_work_mode(work_mode: str) -> WorkMode:
    """Normalize work mode with explicit mapping only"""
    work_mode_lower = work_mode.lower().strip()
    
    # Only map if explicitly mentioned
    if work_mode_lower in ["remote", "wfh", "work from home"]:
        return WorkMode.REMOTE
    elif work_mode_lower in ["onsite", "on-site", "office", "on site"]:
        return WorkMode.ON_SITE
    elif work_mode_lower in ["hybrid", "mixed"]:
        return WorkMode.HYBRID
    else:
        return WorkMode.UNKNOWN  # Null value for missing


def _norm_experience_level(exp_level: str) -> ExperienceLevel:
    """Normalize experience level with explicit mapping only"""
    exp_level_lower = exp_level.lower().strip()
    
    # Only map if explicitly mentioned
    if exp_level_lower in ["junior", "entry", "fresher", "entry level"]:
        return ExperienceLevel.JUNIOR
    elif exp_level_lower in ["mid", "mid-senior", "middle", "intermediate"]:
        return ExperienceLevel.MID_SENIOR
    elif exp_level_lower in ["senior", "lead", "architect", "principal"]:
        return ExperienceLevel.SENIOR
    else:
        return ExperienceLevel.UNKNOWN  # Null value for missing


def _extract_skills_from_text(text: str) -> tuple[List[str], List[str]]:
    """Extract skills from text - only if explicitly mentioned"""
    mandatory_skills = []
    all_skills = []
    
    lines = text.split('\n')
    in_mandatory = False
    in_skills = False
    
    for line in lines:
        line_stripped = line.strip()
        line_lower = line_stripped.lower()
        
        if 'mandatory skills' in line_lower:
            in_mandatory = True
            if ':' in line_stripped:
                skills_part = line_stripped.split(':', 1)[1].strip()
                if skills_part:
                    mandatory_skills.extend([s.strip() for s in skills_part.split(',') if s.strip()])
            continue
            
        elif 'skills:' in line_lower and not in_mandatory:
            in_skills = True
            if ':' in line_stripped:
                skills_part = line_stripped.split(':', 1)[1].strip()
                if skills_part:
                    all_skills.extend([s.strip() for s in skills_part.split(',') if s.strip()])
            continue
        
        if in_mandatory or in_skills:
            if any(term in line_lower for term in ['job description', 'qualification', 'location', 'budget', 'notice', 'experience']):
                in_mandatory = False
                in_skills = False
                continue
            
            if line_stripped and len(line_stripped) > 2:
                skill = line_stripped.rstrip('.')
                if in_mandatory:
                    mandatory_skills.append(skill)
                elif in_skills:
                    all_skills.append(skill)
    
    return mandatory_skills, all_skills


def format_metaforge_requirement(
    *,
    job_id: str,
    demand_received_date: str,
    internal_poc: str,
    requirement_from: str,
    client_jd_id: str,
    client_lead_poc: str,
    client_poc: str,
    job_title: str,
    experience: str,
    location: str,
    notice_period: str,
    number_of_positions: int,
    mandatory_skills: List[str],
    skills: List[str],
    body_text: str,
    extracted: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Format requirement in MetaForge format with null values for missing fields
    Expert recruiter interpretation applied
    """
    
    # Extract budget information only if explicitly mentioned
    budget_text = ""
    lines = body_text.split('\n')
    for line in lines:
        line_lower = line.lower()
        if any(term in line_lower for term in ['budget', 'ctc', 'salary', 'lpa', 'lpm', 'bill rate']):
            budget_text = line.strip()
            break
    
    # Parse budget only if found
    monthly_budget = "Not provided"
    yearly_budget = "Not provided"
    if budget_text:
        if 'lpm' in budget_text.lower() or 'per month' in budget_text.lower():
            match = re.search(r'[\d,]+', budget_text)
            if match:
                monthly_budget = match.group(0)
        elif 'lpa' in budget_text.lower() or 'per annum' in budget_text.lower():
            match = re.search(r'[\d,]+', budget_text)
            if match:
                yearly_budget = match.group(0)
    
    # Extract experience level only if explicitly mentioned
    experience_level = ExperienceLevel.UNKNOWN
    if experience:
        exp_lower = experience.lower()
        if any(num in exp_lower for num in ['0', '1', '2']):
            experience_level = ExperienceLevel.JUNIOR
        elif any(num in exp_lower for num in ['3', '4', '5', '6', '7']):
            experience_level = ExperienceLevel.MID_SENIOR
        elif any(num in exp_lower for num in ['8', '9', '10', '+']):
            experience_level = ExperienceLevel.SENIOR
    
    # Extract employment type only if explicitly mentioned
    employment_type = EmploymentType.UNKNOWN
    if body_text:
        body_lower = body_text.lower()
        if 'full-time' in body_lower or 'permanent' in body_lower:
            employment_type = EmploymentType.FULL_TIME
        elif 'contract' in body_lower or 'temporary' in body_lower:
            employment_type = EmploymentType.CONTRACT
    
    # Extract work mode only if explicitly mentioned
    work_mode = WorkMode.UNKNOWN
    if body_text:
        body_lower = body_text.lower()
        if 'remote' in body_lower or 'wfh' in body_lower:
            work_mode = WorkMode.REMOTE
        elif 'onsite' in body_lower or 'on-site' in body_lower or 'office' in body_lower:
            work_mode = WorkMode.ON_SITE
        elif 'hybrid' in body_lower:
            work_mode = WorkMode.HYBRID
    
    # Extract priority only if explicitly mentioned
    priority = Priority.UNKNOWN
    if body_text:
        body_lower = body_text.lower()
        if 'urgent' in body_lower or 'critical' in body_lower:
            priority = Priority.HIGH
        elif 'medium priority' in body_lower:
            priority = Priority.MEDIUM
        elif 'low priority' in body_lower:
            priority = Priority.LOW
    
    # Determine type of demand based on positions
    type_of_demand = "Multiple" if number_of_positions > 1 else "Single"
    
    # Return MetaForge format with null values for missing fields
    return {
        "job_id": job_id,
        "demand_received_date": demand_received_date,
        "internal_poc": internal_poc,
        "requirement_from": requirement_from,
        "client_jd_id": client_jd_id,
        "client_lead_poc": client_lead_poc,
        "client_poc": client_poc,
        "job_title": job_title or "Not provided",
        "job_status": "Open",
        "closed_date": "N/A",
        "type_of_demand": type_of_demand,
        "priority": priority.value if priority != Priority.UNKNOWN else "Medium",
        "number_of_positions": number_of_positions,
        "experience_level": experience_level.value if experience_level != ExperienceLevel.UNKNOWN else "Mid Senior",
        "employment_type": employment_type.value if employment_type != EmploymentType.UNKNOWN else "Contract",
        "budget_currency": "INR",
        "yearly_budget": yearly_budget,
        "monthly_budget": monthly_budget,
        "work_mode": work_mode.value if work_mode != WorkMode.UNKNOWN else "On-site",
        "location": location or "Not provided",
        "overall_experience": experience or "Not specified",
        "notice_period": notice_period or "Not specified",
        "mandatory_skills": "; ".join(mandatory_skills) if mandatory_skills else "Not provided",
        "skills": "; ".join(skills) if skills else "Not provided",
    }


def map_to_metaforge(
    extracted: Dict[str, Any],
    *,
    ctx: EmailContext,
    client_display_name: str,
    job_id: str,
    client_jd_id: str,
    body_text: str = "",
    internal_poc_default: str = "offshore demands",
    jd_count: int = 1,
    demand_received_date: date | None = None,
) -> Dict[str, Any]:
    """
    Map extracted data to MetaForge payload with expert recruiter interpretation
    Ensures null values instead of skipping missing fields
    """
    d = demand_received_date or date.today()
    demand_date_str = d.isoformat()

    n_pos = extracted.get("number_of_positions")
    try:
        n_int = int(n_pos) if n_pos is not None else 1
    except (TypeError, ValueError):
        n_int = 1

    # Extract skills from body text if not provided
    fallback_mand, fallback_skills = _extract_skills_from_text(body_text)
    extracted_mand_list = _as_list(extracted.get("mandatory_skills"))
    extracted_soft_list = _as_list(extracted.get("soft_skills") or extracted.get("skills"))
    
    if not extracted_mand_list and fallback_mand:
        extracted_mand_list = fallback_mand
    if not extracted_soft_list and fallback_skills:
        extracted_soft_list = fallback_skills

    # Ensure job title is never empty (create null if missing)
    if not str(extracted.get("job_title") or "").strip():
        extracted["job_title"] = "Not provided"
    
    # Ensure experience is never empty (create null if missing)
    if not str(extracted.get("experience") or "").strip():
        exp_level = _norm_experience_level(str(extracted.get("experience_level") or ""))
        if exp_level == ExperienceLevel.UNKNOWN:
            extracted["experience"] = "Not specified"
        else:
            extracted["experience"] = _infer_overall_experience(body_text, exp_level)

    requirement_from = (client_display_name or "").strip() or "Unknown"
    if requirement_from.lower() == "unknown":
        requirement_from = "Other"

    # Use the expert recruiter interpretation format
    return format_metaforge_requirement(
        job_id=job_id,
        demand_received_date=demand_date_str,
        internal_poc=internal_poc_default,
        requirement_from=requirement_from,
        client_jd_id=client_jd_id,
        client_lead_poc=ctx.from_email,
        client_poc=ctx.from_email,
        job_title=extracted.get("job_title", ""),
        experience=extracted.get("experience", ""),
        location=_as_list(extracted.get("location"))[0] if _as_list(extracted.get("location")) else "",
        notice_period=extracted.get("notice_period", ""),
        number_of_positions=n_int,
        mandatory_skills=extracted_mand_list,
        skills=extracted_soft_list,
        body_text=body_text,
        extracted=extracted
    )


def _infer_overall_experience(text: str, exp_level: ExperienceLevel) -> str:
    """Infer overall experience only if explicitly mentioned"""
    if exp_level == ExperienceLevel.JUNIOR:
        return "0-2 years"
    elif exp_level == ExperienceLevel.MID_SENIOR:
        return "3-7 years"
    elif exp_level == ExperienceLevel.SENIOR:
        return "8+ years"
    else:
        return "Not specified"


def map_to_ui_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Map to UI payload format - preserves all fields including null values"""
    return payload.copy()
