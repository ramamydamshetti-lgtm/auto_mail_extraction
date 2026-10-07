import sys, os
sys.path.insert(0, os.path.abspath('.'))
sys.stdout.reconfigure(encoding='utf-8')
import json
import sqlite3
from boilerplate_learner import validate_skills
from strict_validator import _is_candidate_table_noise

print("======================================================================")
print("PHASE 2A: SKILL VALIDATION INDEPENDENT VERIFICATION")
print("======================================================================")

# 1. 2026/10/05-011 (LTTS Power Electronics Hardware Design)
print("\n--- 1. VERIFY 2026/10/05-011 DESCRIPTIVE SKILLS ---")
skills_011_extracted = [
    "Strong fundamentals in power electronics and analog hardware design",
    "Hands-on experience with LTspice, MATLAB/Simulink, PSIM/PLECS, SIMPLIS",
    "Experience with MOSFET, SiC/GaN, gate driver, sensing, and EMI/EMC considerations",
    "Understanding of PCB layout practices for high-voltage and high-power applications",
    "TI C2000 and digital power control",
    "Familiarity with TI C2000 and digital power control is an added advantage."
]
res_011 = validate_skills(skills_011_extracted, client="LTTS")
print(f"Input ({len(skills_011_extracted)} items):")
for s in skills_011_extracted:
    print(f"  - {s}")
print(f"Output ({len(res_011)} items):")
for s in res_011:
    print(f"  + {s}")

expected_011 = [
    "Strong fundamentals in power electronics and analog hardware design",
    "Hands-on experience with LTspice, MATLAB/Simulink, PSIM/PLECS, SIMPLIS",
    "Experience with MOSFET, SiC/GaN, gate driver, sensing, and EMI/EMC considerations",
    "Understanding of PCB layout practices for high-voltage and high-power applications",
    "TI C2000 and digital power control",
]
for exp in expected_011:
    assert exp in res_011, f"FAIL: Expected skill missing: {exp}"
print("PASS: All 5 descriptive skills for 2026/10/05-011 survived validation!")

# 2. 2026/09/11-001 (Deloitte Fullstack Developer)
print("\n--- 2. VERIFY 2026/09/11-001 (DELOITTE FULLSTACK) ---")
deloitte_skills = [
    "Strong experience in Python development using Django and/or FastAPI.",
    "Proficiency in TypeScript and modern JavaScript.",
    "Hands-on experience with Python backend development.",
    "Experience developing enterprise applications using Django and/or FastAPI.",
    "Strong understanding of REST API design and implementation.",
    "Experience with PostgreSQL or other relational databases.",
    "Good understanding of frontend architecture, component-driven development, and reusable design patterns.",
    "Experience with Git and modern development workflows.",
    "Knowledge of Docker and application deployment practices.",
    "Familiarity with cloud platforms such as AWS or Azure."
]
res_deloitte = validate_skills(deloitte_skills, client="Deloitte")
print(f"Input: {len(deloitte_skills)} items")
print(f"Output: {len(res_deloitte)} items")
for s in res_deloitte:
    print(f"  + {s}")
assert len(res_deloitte) == 10, f"FAIL: Expected 10 skills, got {len(res_deloitte)}"
print("PASS: All 10 technical skills for 2026/09/11-001 survived validation!")

# 3. 2026/09/29-024 (LTTS MEH NVH)
print("\n--- 3. VERIFY 2026/09/29-024 (CANDIDATE TABLE NOISE REJECTION) ---")
nvh_input = [
    "ANSA",
    "META",
    "Resumes sent Date (DDMMYY)",
    "Full Name of the candidate",
    "Last Full Time Qualification",
    "Mail ID"
]
res_nvh = validate_skills(nvh_input, client="LTTS")
print(f"Input: {nvh_input}")
print(f"Output: {res_nvh}")
assert res_nvh == ["ANSA", "META"], f"FAIL: Expected ['ANSA', 'META'], got {res_nvh}"
print("PASS: All candidate table noise rejected; real skills ANSA & META preserved!")

# 4. 2026/09/07-023 (LTTS Lead Power System Engineer)
print("\n--- 4. VERIFY 2026/09/07-023 (LEAD POWER SYSTEM ENGINEER) ---")
power_input = [
    "Modelling various power system elements to perform steady state, transient and EMT studies",
    "PSS®E",
    "Dig SILENT",
    "Renewable"
]
res_power = validate_skills(power_input, client="LTTS")
print(f"Input: {power_input}")
print(f"Output: {res_power}")
for s in power_input:
    assert s in res_power, f"FAIL: Expected {s} in output"
print("PASS: Descriptive modelling skill and tools preserved!")

# 5. REJECTION OF RECRUITER BOILERPLATE, SIGNATURES & DIRECTIVES
print("\n--- 5. VERIFY REJECTION OF RECRUITER BOILERPLATE & SIGNATURES ---")
boilerplate_inputs = [
    "Kindly share quality profiles after proper validation with @Vinaya on priority",
    "(keep all marked in this email while sharing the profiles & don’t change the subject line)",
    "Pls ensure that your share the profiles with standard profile submission template:",
    "Best Regards,",
    "Kallol Chakraborty",
    "Partner Engagement Head - Talent Acquisition",
    "L&T Technology Services Ltd., S1 Building, L&T Tech Park, Bengaluru, Karnataka 560092 India",
    "Mobile: +91 96 8610 0177",
    "ENGINEERING THE CHANGE | www.LTTS.com",
    "L&T Technology Services Limited (LTTS) is committed to safeguard your privacy.",
    "8 - 12 years",
    "8 – 9 yrs – 2 L",
    "Vadodara/Mumbai/Pune/BLR/Chennai/Mysore/HYD",
    "Open Positions- 2 positions",
    "Customer discussion - Yes",
    "Customer Round – Yes"
]
res_bp = validate_skills(boilerplate_inputs, client="LTTS")
print(f"Boilerplate inputs count: {len(boilerplate_inputs)}")
print(f"Boilerplate survived: {res_bp}")
assert res_bp is None, f"FAIL: Boilerplate leaked into skills: {res_bp}"
print("PASS: 100% of recruiter directives, signatures, and cross-field noise rejected!")

# 6. REJECTION OF GENERIC DUTY PROSE
print("\n--- 6. VERIFY REJECTION OF GENERIC WORKPLACE DUTY PROSE ---")
duty_inputs = [
    "Collaborate with product owners, architects, QA engineers, and business stakeholders",
    "Participate in sprint planning, estimation, reviews, retrospectives, and daily stand-ups",
    "Deliver high-quality features within project timelines and quality standards",
    "Drive technical discussions with customers and mentor junior engineers",
    "Assign tasks and ensure timely deliverables"
]
res_duty = validate_skills(duty_inputs, client="Deloitte")
print(f"Duty prose inputs count: {len(duty_inputs)}")
print(f"Duty prose survived: {res_duty}")
assert res_duty is None, f"FAIL: Generic duty prose leaked into skills: {res_duty}"
print("PASS: 100% of generic operational duty prose rejected!")

print("\n======================================================================")
print("ALL PHASE 2A VERIFICATION CHECKS COMPLETED SUCCESSFULLY!")
print("======================================================================")
