import re, sys, os
sys.path.insert(0, os.path.abspath('.'))
from strict_validator import _is_candidate_table_noise

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
    "skill",
    "skills",
    "mandatory",
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
)

def is_protected_line(line: str) -> bool:
    low = (line or "").lower()
    return any(k in low for k in PROTECTED_KEYWORDS)

def normalize_bare_line(line: str) -> str:
    line = line.strip().lower()
    line = re.sub(r"\d+", "#", line)
    return " ".join(line.split())

def has_value_separator(line: str) -> bool:
    s = line.strip()
    if ":" in s:
        parts = s.split(":", 1)
        if len(parts[0].strip()) > 0 and len(parts[1].strip()) > 0:
            return True
    for sep in (" - ", " – ", " — ", " –", " -"):
        if sep in s:
            parts = s.split(sep, 1)
            if len(parts[0].strip()) > 0 and len(parts[1].strip()) > 0:
                return True
    return False

_SKILL_HEADER_RE = re.compile(
    r"(?i)^\s*(?:[-*•·]\s*)?(?:primary\s+|mandatory\s+|technical\s+|key\s+|required\s+|core\s+|soft\s+|preferred\s+|good\s+to\s+have\s+|nice\s+to\s+have\s+|must\s+have\s+)?(?:skills?|skill\s*set|tech(?:nical)?\s+stack|technolog(?:y|ies)|tools?|competenc(?:y|ies))\b"
)

_NON_SKILL_HEADER_RE = re.compile(
    r"(?i)^\s*(?:[-*•·]\s*)?(?:overall\s+|total\s+|relevant\s+)?(?:exp(?:erience)?|position|positions|location|notice(?:\s+period)?|budget|rate|salary|ctc|about\s+the\s+role|responsibilities|key\s+responsibilities|role\s+overview|job\s+description|qualification|education|eligibility|working\s+model|work\s+mode|best\s+regards|thanks|regards|disclaimer)\b.*[:–—-]?\s*$"
)

def clean_structure_and_extract_boilerplate_test(text: str) -> tuple[str, list[str]]:
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

        if _SKILL_HEADER_RE.search(stripped):
            in_skill_section = True
            skill_lines_count = 0
            continue

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

        if is_protected_line(stripped):
            continue
        if i > 0 and is_protected_line(lines[i - 1].strip()) and not has_value_separator(lines[i - 1].strip()):
            continue
        words = stripped.split()
        if len(words) <= 6 and not has_value_separator(stripped):
            is_short_bare[i] = True

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

    removed_lines = [lines[i].strip() for i in range(n) if remove_mask[i] and lines[i].strip()]
    cleaned_lines = [lines[i] for i in range(n) if not remove_mask[i]]
    return "\n".join(cleaned_lines), removed_lines

# Test 1: Simple skill list
sample_text = '''Job Title: Backend Developer
Skills:
Python
Django
FastAPI
PostgreSQL
Docker
AWS

Experience: 5-8 years
Location: Bangalore
'''

c_text, rem = clean_structure_and_extract_boilerplate_test(sample_text)
print("=== TEST 1 ===")
print("Cleaned text:\n", c_text)
print("Removed lines:", rem)

# Test 2: Bulleted skill list from 2026/09/11-001
sample_2 = '''Primary Technology Stack
Frontend
· React.js
· TypeScript
· JavaScript
· HTML5
Backend
· Python
· Django
· FastAPI
· REST APIs
'''
c_text2, rem2 = clean_structure_and_extract_boilerplate_test(sample_2)
print("\n=== TEST 2 ===")
print("Cleaned text 2:\n", c_text2)
print("Removed lines 2:", rem2)
