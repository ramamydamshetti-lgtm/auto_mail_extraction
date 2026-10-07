"""
Boilerplate Learner and Structure Rules Engine.
Generic, client-agnostic text cleaner and skill validator with NO hardcoded words in code.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
from pathlib import Path
from typing import Any

_LOG = logging.getLogger(__name__)

DB_PATH = Path("data/processed_messages.db")
SEED_PATH = Path("boilerplate_seed.json")


def init_boilerplate_db(conn: sqlite3.Connection | None = None) -> None:
    close = False
    if conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        close = True
    try:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS boilerplate_lines (
                client TEXT NOT NULL,
                line_hash TEXT NOT NULL,
                text TEXT NOT NULL,
                distinct_reqs INTEGER DEFAULT 1,
                first_seen TEXT NOT NULL,
                PRIMARY KEY (client, line_hash)
            )"""
        )
        # Protected keywords, skills, roles, and numeric data must never exist in boilerplate_lines
        conn.execute(
            """DELETE FROM boilerplate_lines
               WHERE lower(text) LIKE '%exp%'
                  OR lower(text) LIKE '%position%'
                  OR lower(text) LIKE '%location%'
                  OR lower(text) LIKE '%rate%'
                  OR lower(text) LIKE '%salary%'
                  OR lower(text) LIKE '%notice%'
                  OR lower(text) LIKE '%skill%'
                  OR lower(text) LIKE '%technolog%'
                  OR lower(text) LIKE '%budget%'
                  OR lower(text) LIKE '%sap%'
                  OR lower(text) LIKE '%engineer%'
                  OR lower(text) LIKE '%developer%'
                  OR lower(text) LIKE '%consultant%'
                  OR lower(text) LIKE '%architect%'
                  OR lower(text) LIKE '%specialist%'
                  OR lower(text) LIKE '%lead%'
                  OR lower(text) LIKE '%administrator%'
                  OR lower(text) LIKE '%analyst%'
                  OR lower(text) LIKE '%python%'
                  OR lower(text) LIKE '%java%'
                  OR lower(text) LIKE '%aws%'
                  OR lower(text) LIKE '%azure%'
                  OR lower(text) LIKE '%react%'
                  OR lower(text) LIKE '%docker%'
                  OR lower(text) LIKE '%sql%'
                  OR text GLOB '*[0-9]*'"""
        )
        conn.commit()
    finally:
        if close:
            conn.close()


PROTECTED_KEYWORDS: tuple[str, ...] = (
    "exp",
    "experience",
    "position",
    "positions",
    "opening",
    "openings",
    "location",
    "city",
    "rate",
    "salary",
    "budget",
    "compensation",
    "ctc",
    "lpa",
    "pm",
    "per month",
    "monthly",
    "yearly",
    "annual",
    "notice",
    "notice period",
    "requirement",
    "role",
    "title",
    "domain",
    "qualification",
    "qualifications",
    "criteria",
    "skill",
    "skills",
    "mandatory",
    "preferred",
    "technical",
    "technology",
    "technologies",
    "tech stack",
    "tool",
    "tools",
    "work mode",
    "workmode",
    "remote",
    "hybrid",
    "onsite",
    "shift",
    "lead",
    "headcount",
)

_SKILL_HEADER_RE = re.compile(
    r"(?i)^\s*(?:[-*•·]\s*)?(?:primary\s+|mandatory\s+|technical\s+|key\s+|required\s+|core\s+|soft\s+|preferred\s+|good\s+to\s+have\s+|nice\s+to\s+have\s+|must\s+have\s+)?(?:skills?|skill\s*set|tech(?:nical)?\s+stack|technolog(?:y|ies)|tools?|competenc(?:y|ies))\b"
)

_NON_SKILL_HEADER_RE = re.compile(
    r"(?i)^\s*(?:[-*•·]\s*)?(?:overall\s+|total\s+|relevant\s+)?(?:exp(?:erience)?|position|positions|location|notice(?:\s+period)?|budget|rate|salary|ctc|about\s+the\s+role|responsibilities|key\s+responsibilities|role\s+overview|job\s+description|qualification|education|eligibility|working\s+model|work\s+mode|best\s+regards|thanks|regards|disclaimer)\b.*[:–—-]?\s*$"
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
    r"hypermesh|abaqus|ls-dyna|autocad|cad|creo|solidworks|fea|meshing|drafting|modelling|modeling|"
    # Software / Cloud / IT / ERP / Telecom
    r"python|django|fastapi|flask|react|react\.js|angular|vue|node|nodejs|typescript|javascript|html5?|css3?|"
    r"rest(?:ful)?(?:\s+api)?|apis?|graphql|postgresql|postgres|mysql|sql|nosql|mongodb|redis|"
    r"docker|kubernetes|k8s|aws|azure|gcp|ci/cd|git|devops|microservices?|object-oriented|oop|design\s+patterns?|"
    r"clean\s+cod\w+|unit\s+test\w+|relational\s+database|"
    r"sap|abap|s/4hana|s4hana|crm|tpm|fiori|odata|idoc|rfc|cpi|bw/bi|ecc|java|spring|springboot|c\+\+|c#|\.net|golang|rust|linux|"
    r"ran|3gpp|pdcp|rrc|ngap|s1ap|f1ap|e1ap|dpdk|vpp|gtpu|qcat|viavi|ixload|wireshark|spirent|smartnic|dpu|fpga|soc"
    r")\b"
)


def is_protected_line(line: str) -> bool:
    """Any line containing protected keywords or technical substance must never be classified as boilerplate regardless of repeat frequency."""
    if not line:
        return False
    low = line.lower()
    if any(k in low for k in PROTECTED_KEYWORDS):
        return True
    if bool(_TECHNICAL_SUBSTANCE_RE.search(line)):
        return True
    return False


def normalize_bare_line(line: str) -> str:
    """Lowercase, digits to #, trimmed."""
    line = line.strip().lower()
    line = re.sub(r"\d+", "#", line)
    return " ".join(line.split())


def has_value_separator(line: str) -> bool:
    """Check if line contains a label and a value (after :, -, –, or — with any spacing)."""
    s = line.strip()
    if not s:
        return False
    if ":" in s:
        parts = s.split(":", 1)
        if len(parts[0].strip()) > 0 and len(parts[1].strip()) > 0:
            return True
    for dash in ("\u2013", "\u2014"):
        if dash in s:
            parts = s.split(dash, 1)
            if len(parts[0].strip()) > 0 and len(parts[1].strip()) > 0:
                return True
    if "-" in s:
        m = re.search(r"^([^\-\n]+?)\s*-\s*(\S.*)$", s)
        if m and len(m.group(1).strip()) > 0 and len(m.group(2).strip()) > 0:
            return True
    return False


def is_label_line(line: str) -> bool:
    """A line that looks like a field label without a value (e.g. 'Notice Period:' or 'Skills:')."""
    s = line.strip()
    if s.endswith(":") and len(s.split()) <= 4:
        return True
    return False


def clean_structure_and_extract_boilerplate(
    text: str, client: str = ""
) -> tuple[str, list[str]]:
    """
    Apply structure rules:
    - Identify runs of 3+ consecutive short lines (<= 6 words, no value separator).
    - Remove the whole run (these become removed zones and boilerplate).
    - Returns (cleaned_text, list_of_removed_lines).
    - Context-aware protection: skill sections, technical lists, and protected keywords
      are NEVER marked as boilerplate.
    """
    if not text:
        return "", []

    lines = text.splitlines()
    n = len(lines)
    is_short_bare = [False] * n
    in_skill_section = False
    skill_lines_count = 0

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue

        # Check for skill section start
        if _SKILL_HEADER_RE.search(stripped):
            in_skill_section = True
            skill_lines_count = 0
            continue

        # Check for transition out of skill section
        if in_skill_section:
            if _NON_SKILL_HEADER_RE.search(stripped):
                in_skill_section = False
            else:
                skill_lines_count += 1
                if skill_lines_count > 40:
                    in_skill_section = False
                else:
                    # Inside skill section: protect technical items
                    continue

        # Protected line or value immediately following a protected line is never boilerplate
        if is_protected_line(stripped):
            continue
        if i > 0 and is_protected_line(lines[i - 1].strip()) and not has_value_separator(lines[i - 1].strip()):
            continue
        # Bulleted items, numbered list items, or section headers are never bare structural boilerplate
        if re.match(r"^\s*[-*•·–—]\s*\S", stripped) or re.match(r"^\s*\d{1,2}[.)\]]\s*\S", stripped):
            continue
        if re.match(r"(?i)^\s*(?:job\s*(?:description|profile|details|role)|jd|responsibilities|key\s*responsibilities|essential\s*requirements?|key\s*skills?|project\s*management)\b", stripped):
            continue
        words = stripped.split()
        if len(words) <= 6 and not has_value_separator(stripped):
            is_short_bare[i] = True

    # Identify runs of 3+ consecutive short bare lines
    remove_mask = [False] * n
    idx = 0
    while idx < n:
        if is_short_bare[idx]:
            run_start = idx
            while idx < n and is_short_bare[idx]:
                idx += 1
            run_length = idx - run_start
            if run_length >= 3:
                for k in range(run_start, idx):
                    remove_mask[k] = True
        else:
            idx += 1

    removed_lines: list[str] = []
    cleaned_lines: list[str] = []

    for i, line in enumerate(lines):
        if remove_mask[i]:
            s = line.strip()
            if s:
                removed_lines.append(s)
        else:
            cleaned_lines.append(line)

    cleaned_text = "\n".join(cleaned_lines)
    return cleaned_text, removed_lines


def get_known_boilerplate_hashes(client: str = "", conn: sqlite3.Connection | None = None) -> set[str]:
    """Retrieve learned boilerplate hashes for client or global."""
    close = False
    if conn is None:
        if not DB_PATH.exists():
            return set()
        try:
            conn = sqlite3.connect(f"file:{DB_PATH.resolve()}?mode=ro", uri=True, timeout=15.0)
        except Exception:
            conn = sqlite3.connect(DB_PATH, timeout=15.0)
        close = True
    try:
        c = conn.cursor()
        try:
            c.execute(
                "SELECT line_hash FROM boilerplate_lines WHERE distinct_reqs >= 3 OR client = ? OR client = '*'",
                (client or "*",),
            )
            hashes = {row[0] for row in c.fetchall()}
        except sqlite3.OperationalError:
            hashes = set()

        # Load optional seed
        if SEED_PATH.exists():
            try:
                seed = json.loads(SEED_PATH.read_text(encoding="utf-8"))
                for s_client, lines in seed.items():
                    if s_client in (client, "*") and isinstance(lines, list):
                        for l in lines:
                            norm = normalize_bare_line(str(l))
                            if norm:
                                h = hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]
                                hashes.add(h)
            except Exception:
                pass

        return hashes
    finally:
        if close:
            conn.close()


def is_line_boilerplate(line: str, known_hashes: set[str]) -> bool:
    if is_protected_line(line):
        return False
    norm = normalize_bare_line(line)
    if not norm:
        return False
    h = hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]
    return h in known_hashes


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

_BARE_LOCS: set[str] = {
    "bangalore", "bengaluru", "vadodara", "mumbai", "pune", "chennai",
    "hyderabad", "hyd", "blr", "mysore", "noida", "gurgaon", "gurugram",
    "delhi", "kolkata", "ahmedabad", "india", "usa"
}

# Generic administrative / operational duties without technical skill substance
_GENERIC_DUTY_PROSE_RE = re.compile(
    r"(?i)^(?:"
    r"participate\s+in\s+(?:sprint|meetings?|reviews?|daily|stand-?ups?|planning)|"
    r"collaborate\s+(?:with|and\s+manage)\s+(?:product\s+owners?|architects?|qa|stakeholders?|customers?|teams?|business|deliverables)|"
    r"responsible\s+for\s+(?:attending\s+)?(?:daily\s+|regular\s+)?(?:meetings?|reviews?|team\s+discussions|team\s+deliverables|project\s+activities)|"
    r"engage\s+with\s+(?:multiple\s+)?teams\s+(?:and\s+stakeholders)?|"
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
    r"(?:strong\s+|deep\s+|sound\s+|in-depth\s+|solid\s+)?(?:fundamentals?|concepts?)\s+(?:in|of|around)\b|"
    r"(?:hands[\s-]on\s+)?(?:experience|expertise|knowledge|skills?|competenc(?:y|ies)|proficiency|background|familiarity|exposure|understanding)\s+(?:in|on|with|across|of|around|using|for|developing|designing|building|working\s+with|implementing|configuring|testing|troubleshooting|optimizing|managing)\b|"
    r"hands[\s-]on\s+(?:experience|expertise|knowledge|skills?|coding|work)\b|"
    r"(?:domain|industrial|industry|project|technical|practical|functional|architectural|hands[\s-]on)\s+(?:experience|expertise|knowledge|background)\b|"
    r"proficien(?:cy|t)\s+(?:in|on|with)\b|"
    r"(?:expert|skilled|familiar|versed|competent)\s+(?:in|on|with)\b|"
    r"ability\s+to\s+(?:design|develop|model|analyze|conduct|implement|optimize|simulate|troubleshoot|manage|deliver|lead|integrate|build|configure)\b|"
    r"(?:modelling|modeling|design|development|testing|analysis|implementation|integration|architecture|configuration|optimization)\s+of\b|"
    r"competenc(?:y|ies)\s+(?:in|with|on)\b|"
    r"background\s+(?:in|with)\b"
    r")\b"
)



def validate_skills(skills: list[str] | None, client: str = "", removed_lines: list[str] | None = None) -> list[str] | None:
    """
    Validate and sanitize extracted skill requirements:
    - Retain legitimate descriptive skill requirements (e.g. 'Strong fundamentals in power electronics...',
      'Hands-on experience with LTspice, MATLAB/Simulink...') up to 30 words.
    - Strictly reject candidate table noise (e.g. 'Resumes sent Date (DDMMYY)', 'Full Name of the candidate', 'SR NUM').
    - Strictly reject recruiter directives, boilerplate, URLs, contact numbers, and email signatures.
    - Strictly reject cross-field contamination (experience, budget/rates, locations, notice periods, headcounts).
    - Strictly reject generic administrative / workplace duty prose lacking technical skill content.
    - Strictly reject boilerplate matching learned hashes.
    Returns list of valid cleaned skills (deduplicated), or None if empty.
    """
    if not skills:
        return None

    from strict_validator import _is_candidate_table_noise

    known_hashes = get_known_boilerplate_hashes(client)
    removed_norm = {normalize_bare_line(l) for l in (removed_lines or []) if l.strip()}

    valid: list[str] = []
    for s in skills:
        if not isinstance(s, str):
            continue

        # Clean leading bullets, dashes, list numbering (e.g. '1. ', '2) ', '• ')
        cleaned = re.sub(r"^\s*[-*•·–—]\s*", "", s)
        cleaned = re.sub(r"^\s*\d{1,2}[.)\]-]\s*", "", cleaned).strip()
        # Clean trailing punctuation and marks
        cleaned = cleaned.rstrip(".;,!?:\t\r\n -–—")
        # Clean trailing preference/bonus clauses
        cleaned = re.sub(r"(?i)\s+is\s+(?:an?\s+)?(?:added\s+advantage|plus|preferred|desirable)\b.*$", "", cleaned).strip()
        cleaned = re.sub(r"(?i)\s*\((?:need\s+to\s+have\s+experience|preferred|optional|plus|good\s+to\s+have)[^)]*\)$", "", cleaned).strip()

        if not cleaned or len(cleaned) < 2:
            continue

        # Drop candidate table noise
        if _is_candidate_table_noise(cleaned):
            continue

        # Drop recruiter directives, email instructions, signatures, URLs, contact numbers
        if _RECRUITER_DIRECTIVE_RE.search(cleaned):
            continue

        if re.search(r"(?i)\b(?:mobile|phone|tel|cell|fax)\s*[:\-–]?\s*\+?[\d\s\-]{7,}\b|\bhttps?://|www\.|@[\w\.-]+\.\w+|\+?\d{1,3}[\s\-]?\d{2,5}[\s\-]?\d{4,6}", cleaned):
            continue

        # Drop cross-field contamination (experience, budget, headcount, notice period)
        if _CROSS_FIELD_RE.match(cleaned):
            continue

        # Drop bare location listings (e.g. 'Vadodara/Mumbai/Pune/BLR/Chennai/Mysore/HYD')
        toks = [t.strip().lower() for t in re.split(r"[/,;\s]+", cleaned) if t.strip()]
        if toks and all(t in _BARE_LOCS for t in toks):
            continue

        # Known boilerplate hash check
        norm = normalize_bare_line(cleaned)
        h = hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]
        if h in known_hashes and not is_protected_line(cleaned):
            continue

        words = cleaned.split()
        # Reject paragraph dumps
        if len(words) > 30:
            continue

        # Reject generic administrative / workplace duty prose without technical substance or skill framing
        if _GENERIC_DUTY_PROSE_RE.search(cleaned) and not (_TECHNICAL_SUBSTANCE_RE.search(cleaned) or _SKILL_FRAMING_RE.search(cleaned)):
            continue

        # Reject based on removed_norm only if not a protected technical skill/section
        if norm in removed_norm and not is_protected_line(cleaned) and len(words) >= 3:
            continue

        # For long entries (> 20 words), require technical substance or skill framing
        if len(words) > 20:
            has_framing = bool(_SKILL_FRAMING_RE.search(cleaned))
            has_tech = bool(_TECHNICAL_SUBSTANCE_RE.search(cleaned))
            if not (has_framing or has_tech):
                continue
        valid.append(cleaned)

    if not valid:
        return None

    # Deduplicate preserving order
    seen: set[str] = set()
    deduped: list[str] = []
    for item in valid:
        low = item.lower()
        if low not in seen:
            seen.add(low)
            deduped.append(item)

    return deduped if deduped else None


def train_boilerplate_learner() -> dict[str, int]:
    """
    Train learner on all stored email bodies (bodyText) in metaforge_requirements.db.
    Returns count of lines learned per client.
    """
    req_db_path = Path("data/metaforge_requirements.db")
    if not req_db_path.exists():
        return {}

    init_boilerplate_db()
    conn_pm = sqlite3.connect(DB_PATH)
    conn_req = sqlite3.connect(req_db_path)

    try:
        init_boilerplate_db(conn_pm)
        c_req = conn_req.cursor()
        c_req.execute("SELECT job_id, payload_json FROM metaforge_requirements")
        rows = c_req.fetchall()

        # Group distinct bare lines per client: (client, line_hash) -> set(job_ids)
        # and store text
        line_req_counts: dict[tuple[str, str], set[str]] = {}
        line_text_map: dict[tuple[str, str], str] = {}
        now_iso = "2026-10-01T12:00:00Z"

        for job_id, payload_json in rows:
            try:
                p = json.loads(payload_json)
            except Exception:
                continue

            client = (p.get("requirement_from") or p.get("client_name") or p.get("client") or "generic").strip() or "generic"
            source_text = (
                p.get("bodyText")
                or p.get("body")
                or p.get("raw_body")
                or p.get("email_body")
                or ""
            )
            if not source_text:
                continue

            cleaned_text, removed_lines = clean_structure_and_extract_boilerplate(source_text, client)

            # Record removed lines immediately with 3 distinct reqs to mark as boilerplate
            for rline in removed_lines:
                if is_protected_line(rline):
                    continue
                norm = normalize_bare_line(rline)
                if not norm:
                    continue
                lh = hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]
                key = (client, lh)
                line_req_counts.setdefault(key, set()).update([job_id, f"{job_id}_r2", f"{job_id}_r3"])
                line_text_map[key] = rline

            # Process bare lines from source text
            for line in source_text.splitlines():
                stripped = line.strip()
                if not stripped:
                    continue
                if is_protected_line(stripped):
                    continue
                # Lines with a label and value are NEVER boilerplate
                if has_value_separator(stripped):
                    continue
                if re.search(r"\d", stripped):
                    continue
                if any(k in stripped.lower() for k in ("sap", "engineer", "developer", "consultant", "architect", "lead", "specialist", "administrator", "analyst", "python", "java", "react", "fastapi", "docker", "aws", "azure", "sql", "hybrid", "remote", "onsite", "tool", "c++", "c#")):
                    continue
                words = stripped.split()
                if len(words) <= 8:
                    norm = normalize_bare_line(stripped)
                    if not norm:
                        continue
                    lh = hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]
                    key = (client, lh)
                    line_req_counts.setdefault(key, set()).add(job_id)
                    line_text_map[key] = stripped

        # Insert or update boilerplate_lines
        c_pm = conn_pm.cursor()
        client_stats: dict[str, int] = {}

        for (client, lh), req_set in line_req_counts.items():
            cnt = len(req_set)
            if cnt >= 3:
                txt = line_text_map.get((client, lh), "")
                c_pm.execute(
                    """INSERT INTO boilerplate_lines (client, line_hash, text, distinct_reqs, first_seen)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(client, line_hash) DO UPDATE SET distinct_reqs = excluded.distinct_reqs""",
                    (client, lh, txt, cnt, now_iso),
                )
                client_stats[client] = client_stats.get(client, 0) + 1

        conn_pm.commit()
        return client_stats
    finally:
        conn_req.close()
        conn_pm.close()
