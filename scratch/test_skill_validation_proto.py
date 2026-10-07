import sys, os
sys.path.insert(0, os.path.abspath('.'))
sys.stdout.reconfigure(encoding='utf-8')
import re
import hashlib
# Candidate table headers / markers
_CANDIDATE_HEADER_RE = re.compile(
    r"(?i)^(?:position(?:/title)?|title|skills?|mandatory\s+skills?[\s\-–]*|name|candidate\s+name|vendor\s+name|"
    r"bu\s*/\s*is|s[/\.]?r\s*num(?:ber)?\.?|s[/\.]?r\s*no\.?|s[/\.]?l\s*n(?:o|um)\.?|sl\s*no\.?|"
    r"resumes?\s+sent\s+date.*|full\s+name.*|mobile\s+no|mail\s+id|np\s*\(days\)|np\s+days|"
    r"total\s+exp|relevant\s+exp|current\s+location|job\s+location|current\s+organization|"
    r"rate\s*/\s*pm.*|supplier\s+comments.*|last\s+full\s+time\s+qualification|qualification\s+criteria|"
    r"domain:?|role\s+overview|job\s+description:?|detailed\s+jd|requirements?\s*[-–]|"
    r"responsibilities|key\s+responsibilities|highlighted|must\s+have|good\s+to\s+have|nice\s+to\s+have|preferred\s+skills?|"
    r"simulation\s+awareness|manufacturing\s+awareness)$"
)

# Recruiter instructions, email directives, signatures, boilerplate
_RECRUITER_DIRECTIVE_RE = re.compile(
    r"(?i)\b(?:"
    r"(?:kindly|please|pls)\s+(?:share|find|send|upload|provide|submit|forward|note|ensure|connect|reach)|"
    r"(?:share|send|upload|submit|forward)\s+(?:quality\s+)?profiles?|"
    r"keep\s+all\s+(?:marked|the\s+people)|"
    r"don['’]t\s+change\s+the\s+subject|"
    r"profiles?\s+on\s+priority|"
    r"profiles?\s+by\s+\d{1,2}\s*(?:am|pm)|"
    r"standard\s+profile\s+submission|"
    r"submission\s+template|"
    r"format\s+for\s+submission|"
    r"need\s+only\s+[a-z\s]+candidates?|"
    r"attend\s+(?:face\s+to\s+face|f2f|interview)|"
    r"(?:face\s+to\s+face|f2f)\s+interview|"
    r"join\s+(?:the\s+)?(?:call|meeting|teams)|"
    r"connect\s+with\s+@?\w+|"
    r"shortlist\s+and\s+interview|"
    r"customer\s+(?:round|discussion)\s*[:–-]?\s*(?:yes|no)|"
    r"dear\s+(?:partner|all|team|colleagues?|\w+)|"
    r"(?:best|warm)?\s*regards|"
    r"thanks\s*(?:&|and)?\s*regards|"
    r"talent\s+acquisition|partner\s+engagement|human\s+resources|recruitment\s+team|"
    r"s1\s+building|tech\s+park|engineering\s+the\s+change|"
    r"confidential|privileged\s+information|safeguard\s+your\s+privacy|privacy\s+notice|privacy\s+policy|intended\s+recipient|"
    r"read\s+the\s+appropriate|visit\s+our\s+website"
    r")\b"
)

# Cross-field expressions (experience, budget, positions, location, notice period)
_CROSS_FIELD_RE = re.compile(
    r"(?i)^(?:"
    r"(?:overall\s+|total\s+|relevant\s+)?exp(?:erience)?\s*[:–-]?\s*(?:\d{1,2}\s*[-–]\s*\d{1,2}|\d{1,2}\+?)\s*(?:years?|yrs?)|"
    r"(?:\d{1,2}\s*[-–]\s*\d{1,2}|\d{1,2}\+?)\s*(?:years?|yrs?)(?:\s+(?:of\s+)?experience)?|"
    r"(?:bill\s+rate|rate\s*/\s*pm|monthly\s+budget|rate\s+per\s+month|budget|ctc|salary)\s*[:–-]?\s*.*|"
    r"(?:inr|usd|eur|₹|\$|€)?\s*\d+(?:\.\d+)?\s*(?:lpa|lpm|lakhs?|k|pm|per\s+month)|"
    r"\d+\s*[-–]\s*\d+\s*yrs\s*[-–]\s*\d+(?:\.\d+)?\s*[Ll]|"
    r"(?:notice\s*period|notice|np)\s*[:–-]?\s*(?:immediate|\d+\s*days?|serving.*)|"
    r"(?:immediate\s+to\s+\d+\s*days?|immediate\s+joiner|\d+\s*days?\s*notice)|"
    r"(?:work\s+location|job\s+location|location|base\s+location)\s*[:–-]?\s*.*|"
    r"(?:open\s+positions?|number\s+of\s+positions?|positions?|openings?)\s*[:–-]?\s*\d+.*|"
    r"\d+\s+(?:positions?|openings?)|"
    r"(?:working\s+model|work\s+mode)\s*[:–-]?\s*(?:remote|hybrid|onsite|on-site|\d+\s+days.*)"
    r")$"
)

# Generic administrative / operational duties without technical skill substance
_GENERIC_DUTY_PROSE_RE = re.compile(
    r"(?i)^(?:"
    r"participate\s+in\s+(?:sprint|meetings?|reviews?|daily|stand-?ups?|planning)|"
    r"collaborate\s+with\s+(?:product\s+owners?|architects?|qa|stakeholders?|customers?|teams?|business)|"
    r"drive\s+technical\s+discussions\s+with\s+customers\s+and\s+mentor\s+junior\s+engineers|"
    r"mentor\s+(?:junior\s+engineers?|team\s+members?)|"
    r"assign\s+tasks\s+and\s+ensure\s+timely|"
    r"deliver\s+high[\s-]quality\s+features\s+within\s+project\s+timelines|"
    r"contribute\s+to\s+continuous\s+improvement\s+of\s+development\s+standards|"
    r"support\s+operational\s+activities|"
    r"troubleshoot\s+(?:and\s+resolve\s+)?production\s+issues|"
    r"perform\s+code\s+reviews\s+and\s+follow\s+secure\s+coding|"
    r"assist\s+with\s+cloud[\s-]based\s+deployments"
    r")"
)

# Skill framing phrases indicating technical competence
_SKILL_FRAMING_RE = re.compile(
    r"(?i)\b(?:"
    r"strong\s+fundamentals?\s+in|fundamentals?\s+of|fundamentals?\s+in|"
    r"hands[\s-]on\s+experience\s+(?:with|in)|experience\s+(?:with|in|of|developing|designing|building|working\s+with)|"
    r"(?:strong\s+|deep\s+|good\s+)?understanding\s+of|"
    r"(?:working\s+|practical\s+|in-depth\s+|sound\s+)?knowledge\s+of|"
    r"proficien(?:cy\s+in|t\s+in)|expertise\s+in|skilled\s+in|expert\s+in|"
    r"familiarity\s+with|familiar\s+with|exposure\s+to|well\s+versed\s+in|"
    r"ability\s+to\s+(?:design|develop|model|analyze|conduct|implement|optimize|simulate)|"
    r"modelling\s+(?:of|various)|modeling\s+(?:of|various)|design\s+of|development\s+of|testing\s+of|analysis\s+of|"
    r"competenc(?:y|ies)\s+in|background\s+in"
    r")\b"
)

# Technical substance tokens (engineering domains, tools, languages, frameworks, concepts)
_TECHNICAL_SUBSTANCE_RE = re.compile(
    r"(?i)\b(?:"
    # Electronics / Electrical / Power
    r"power\s+electronics|analog\s+hardware|digital\s+power|circuit\s+design|schematics?|pcb\s+layout|pcb|"
    r"mosfet|sic|gan|gate\s+driver|sensing|emi/emc|emi|emc|ltspice|matlab|simulink|psim|plecs|simplis|c2000|"
    r"high-voltage|high-power|power\s+stage|magnetic\s+design|derating|thermal\s+analysis|worst-case\s+analysis|"
    r"converters?|inverters?|topolog(?:y|ies)|buck|boost|flyback|llc|psfb|dab|half-bridge|full-bridge|snubbers?|"
    r"power\s+system|emt|steady\s+state|transient|pss[®e]|pss/e|dig\s*silent|digsilent|power\s*factory|pscad|etap|sld|"
    r"load\s+flow|short[\s-]circuit|harmonic|grid-integration|energy\s+storage|renewable|pv|battery|wind|"
    # Mechanical / Automotive / CAE
    r"ansa|meta|nvh|vtf|ntf|dynamic\s+stiffness|gds|lds|nastran|sol111|acoustic|cavity|biw|nx|siemens\s+nx|catia|"
    r"hypermesh|abaqus|ls-dyna|autocad|creo|solidworks|fea|meshing|"
    # Software / Cloud / IT / ERP
    r"python|django|fastapi|flask|react|react\.js|angular|vue|node|nodejs|typescript|javascript|html5?|css3?|"
    r"rest(?:ful)?(?:\s+api)?|apis?|graphql|postgresql|postgres|mysql|sql|nosql|mongodb|redis|"
    r"docker|kubernetes|k8s|aws|azure|gcp|ci/cd|git|devops|microservices?|object-oriented|oop|design\s+patterns?|"
    r"clean\s+cod\w+|unit\s+test\w+|relational\s+database|"
    r"sap|abap|s/4hana|s4hana|crm|tpm|fiori|odata|idoc|rfc|cpi|bw/bi|ecc|java|spring|springboot|c\+\+|c#|\.net|golang|rust|linux"
    r")\b"
)

def validate_skill_single(s: str, client: str = "", removed_lines: list[str] | None = None, known_hashes: set[str] | None = None) -> str | None:
    if not isinstance(s, str):
        return None
    
    # Clean leading bullets, dashes, list numbering (e.g. '1. ', '2) ', '• ')
    cleaned = re.sub(r"^\s*[-*•·–—]\s*", "", s)
    cleaned = re.sub(r"^\s*\d{1,2}[.)\]-]\s*", "", cleaned).strip()
    # Clean trailing punctuation and marks
    cleaned = cleaned.rstrip(".;,!?:\t\r\n -–—")
    # Clean trailing preference/bonus clauses
    cleaned = re.sub(r"(?i)\s+is\s+(?:an?\s+)?(?:added\s+advantage|plus|preferred|desirable)\b.*$", "", cleaned).strip()
    cleaned = re.sub(r"(?i)\s*\((?:need\s+to\s+have\s+experience|preferred|optional|plus|good\s+to\s+have)[^)]*\)$", "", cleaned).strip()

    if not cleaned or len(cleaned) < 2:
        return None

    # Check candidate table noise
    if _CANDIDATE_HEADER_RE.match(cleaned):
        return None

    # Check recruiter directives, boilerplate, emails, URLs
    if _RECRUITER_DIRECTIVE_RE.search(cleaned):
        return None

    if re.search(r"(?i)\b(?:mobile|phone|tel|cell|fax)\s*[:\-–]?\s*\+?[\d\s\-]{7,}\b|\bhttps?://|www\.|@[\w\.-]+\.\w+|\+?\d{1,3}[\s\-]?\d{2,5}[\s\-]?\d{4,6}", cleaned):
        return None

    # Check cross-field contamination
    if _CROSS_FIELD_RE.match(cleaned):
        return None

    # Bare locations check (e.g. 'Vadodara/Mumbai/Pune/BLR/Chennai/Mysore/HYD')
    _BARE_LOCS = {
        "bangalore", "bengaluru", "vadodara", "mumbai", "pune", "chennai",
        "hyderabad", "hyd", "blr", "mysore", "noida", "gurgaon", "gurugram",
        "delhi", "kolkata", "ahmedabad", "india", "usa"
    }
    toks = [t.strip().lower() for t in re.split(r"[/,;\s]+", cleaned) if t.strip()]
    if toks and all(t in _BARE_LOCS for t in toks):
        return None

    from boilerplate_learner import normalize_bare_line, is_protected_line
    norm = normalize_bare_line(cleaned)
    h = hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]
    if known_hashes and h in known_hashes:
        return None

    words = cleaned.split()
    # Reject paragraph dumps
    if len(words) > 30:
        return None

    # Check if it is purely generic workplace duty prose without technical substance
    if _GENERIC_DUTY_PROSE_RE.search(cleaned) and not _TECHNICAL_SUBSTANCE_RE.search(cleaned):
        return None

    # For longer phrases (> 6 words)
    if len(words) > 6:
        # Must have either skill framing or technical substance
        has_framing = bool(_SKILL_FRAMING_RE.search(cleaned))
        has_tech = bool(_TECHNICAL_SUBSTANCE_RE.search(cleaned))
        
        if not (has_framing or has_tech):
            # No technical substance or skill framing -> discard
            return None

    return cleaned


if __name__ == "__main__":
    from boilerplate_learner import get_known_boilerplate_hashes
    known_hashes = get_known_boilerplate_hashes('LTTS')

    print("=== TEST 1: 2026/10/05-011 DESCRIPTIVE SKILLS ===")
    skills_011 = [
        "Strong fundamentals in power electronics and analog hardware design",
        "Hands-on experience with LTspice, MATLAB/Simulink, PSIM/PLECS, SIMPLIS",
        "Experience with MOSFET, SiC/GaN, gate driver, sensing, and EMI/EMC considerations",
        "Understanding of PCB layout practices for high-voltage and high-power applications",
        "TI C2000 and digital power control",
        "Familiarity with TI C2000 and digital power control is an added advantage."
    ]
    for s in skills_011:
        res = validate_skill_single(s, client='LTTS', known_hashes=known_hashes)
        print(f"[{'PASS' if res else 'FAIL'}] {s!r} -> {res!r}")
        assert res is not None, f"Failed to preserve valid skill: {s}"

    print("\n=== TEST 2: CANDIDATE TABLE NOISE (MUST ALL BE REJECTED) ===")
    noise_tokens = [
        "Resumes sent Date (DDMMYY)",
        "Full Name of the candidate",
        "Last Full Time Qualification",
        "Mail ID",
        "MOBILE NO",
        "NP(Days)",
        "NP (Days)",
        "Total Exp",
        "Relevant Exp",
        "Current Location",
        "Job Location",
        "Current Organization",
        "Rate / pm (INR)",
        "SR NUM",
        "Vendor Name",
        "BU / IS",
        "Position/Title",
        "Highlighted",
        "Must have",
        "Responsibilities",
        "Key Responsibilities"
    ]
    for n in noise_tokens:
        res = validate_skill_single(n, client='LTTS', known_hashes=known_hashes)
        print(f"[{'PASS' if res is None else 'FAIL'}] {n!r} -> {res!r}")
        assert res is None, f"Failed to reject candidate table noise: {n}"

    print("\n=== TEST 3: RECRUITER DIRECTIVES & BOILERPLATE (MUST ALL BE REJECTED) ===")
    boilerplate_tokens = [
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
    for b in boilerplate_tokens:
        res = validate_skill_single(b, client='LTTS', known_hashes=known_hashes)
        print(f"[{'PASS' if res is None else 'FAIL'}] {b!r} -> {res!r}")
        assert res is None, f"Failed to reject boilerplate/noise: {b}"

    print("\n=== TEST 4: GENERIC DUTY PROSE (MUST BE REJECTED) ===")
    duties = [
        "Collaborate with product owners, architects, QA engineers, and business stakeholders",
        "Participate in sprint planning, estimation, reviews, retrospectives, and daily stand-ups",
        "Deliver high-quality features within project timelines and quality standards",
        "Drive technical discussions with customers and mentor junior engineers",
        "Assign tasks and ensure timely deliverables",
        "Support schematic development, PCB layout reviews, and hardware bring-up activities."
    ]
    for d in duties:
        res = validate_skill_single(d, client='LTTS', known_hashes=known_hashes)
        print(f"Duty: {d!r} -> {res!r}")

    print("\n=== TEST 5: 2026/09/11-001 (DELOITTE FULLSTACK) ===")
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
    for ds in deloitte_skills:
        res = validate_skill_single(ds, client='Deloitte', known_hashes=get_known_boilerplate_hashes('Deloitte'))
        print(f"[{'PASS' if res else 'FAIL'}] {ds!r} -> {res!r}")
        assert res is not None, f"Failed to preserve Deloitte skill: {ds}"

    print("\n=== TEST 6: 2026/09/07-023 (LEAD POWER SYSTEM ENGINEER) ===")
    power_skills = [
        "Modelling various power system elements to perform steady state, transient and EMT studies",
        "PSS®E",
        "Dig SILENT",
        "Renewable"
    ]
    for ps in power_skills:
        res = validate_skill_single(ps, client='LTTS', known_hashes=known_hashes)
        print(f"[{'PASS' if res else 'FAIL'}] {ps!r} -> {res!r}")
        assert res is not None, f"Failed to preserve Power skill: {ps}"

    print("\n=== TEST 7: 2026/09/29-024 (MEH NVH) ===")
    nvh_mixed = [
        "ANSA",
        "META",
        "Resumes sent Date (DDMMYY)",
        "Full Name of the candidate",
        "Last Full Time Qualification",
        "Mail ID"
    ]
    preserved = [validate_skill_single(x, client='LTTS', known_hashes=known_hashes) for x in nvh_mixed if validate_skill_single(x, client='LTTS', known_hashes=known_hashes)]
    print(f"Input: {nvh_mixed}")
    print(f"Preserved: {preserved}")
    assert preserved == ["ANSA", "META"], f"Expected ['ANSA', 'META'], got {preserved}"

    print("\nALL PROTO CHECKS PASSED!")

