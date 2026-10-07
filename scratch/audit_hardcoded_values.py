import os
import re

files_to_check = [
    'field_mapper.py',
    'requirement_parser.py',
    'models.py',
    'ui/app.py',
    'ui/db.py',
    'ui/templates/base.html',
    'ui/templates/detail.html',
    'ui/templates/list.html',
    'ui/static/app.js',
]

def audit_codebase():
    results = []
    
    for rel_path in files_to_check:
        if not os.path.exists(rel_path):
            print(f"Skipping {rel_path} (does not exist)")
            continue
            
        with open(rel_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        for i, line in enumerate(lines, 1):
            line_str = line.strip()
            # Check for dict.get(..., 'fallback')
            # Check for jinja or 'fallback' or default('fallback')
            # Check for hardcoded strings like "Not available", "TBD", "Accenture Requirement", "Mid Senior", "Full-time", "On-site"
            patterns = [
                r"\.get\([^,)]+,\s*['\"]([^'\"]+)['\"]\)",
                r"\bor\s+['\"]([^'\"]+)['\"]",
                r"\|\s*default\(['\"]([^'\"]+)['\"]",
                r":\s*['\"](Not available|TBD|Accenture Requirement|Requirement Role|Other company / source|Unassigned)['\"]",
            ]
            
            for pat in patterns:
                for match in re.finditer(pat, line_str):
                    val = match.group(1).strip()
                    # Classify as honest empty-state (a) or fabricated (b)
                    honest_values = {
                        'not specified', 'n/a', 'none', '', '-', '—', 'not assigned', 'not provided'
                    }
                    if val.lower() in honest_values or 'not specified' in val.lower():
                        cat = "(a) Honest empty state"
                    elif val in ('open', 'closed', 'hold', 'reopen', 'single', 'multiple', 'INR', 'USD', 'desc', 'asc', '127.0.0.1', 'admin', 'payload'):
                        cat = "(technical default / config key)"
                    else:
                        cat = "(b) FABRICATED substitute / potential hardcode"
                        
                    results.append({
                        'file': rel_path,
                        'line': i,
                        'content': line_str,
                        'fallback_val': val,
                        'category': cat
                    })

    print(f"Found {len(results)} potential fallback instances:")
    b_count = 0
    for r in results:
        if '(b)' in r['category']:
            b_count += 1
            print(f"  [{r['file']}:{r['line']}] {r['category']}: '{r['fallback_val']}'")
            print(f"     Code: {r['content'][:100]}")
            
    print(f"\nTotal (b) FABRICATED instances: {b_count}")

if __name__ == '__main__':
    audit_codebase()
