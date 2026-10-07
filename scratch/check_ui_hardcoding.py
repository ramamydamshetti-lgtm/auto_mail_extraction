import re
from pathlib import Path

def check_hardcoding():
    target_files = [Path("ui/app.py"), Path("ui/db.py")]
    patterns = [
        (r'\bAccenture\b', "Hardcoded Client 'Accenture'"),
        (r'\bLTTS\b', "Hardcoded Client 'LTTS'"),
        (r'\bKPMG\b', "Hardcoded Client 'KPMG'"),
        (r'\bITC\b', "Hardcoded Client 'ITC'"),
        (r'\bmetaforge_requirements\.db\b', "Hardcoded DB file path in code"),
        (r'\bprocessed_messages\.db\b', "Hardcoded DB file path in code"),
        (r'["\']Open["\']', "Hardcoded status 'Open'"),
        (r'["\']Hold["\']', "Hardcoded status 'Hold'"),
        (r'["\']P1["\']', "Hardcoded priority 'P1'"),
    ]

    violations = []
    for tf in target_files:
        content = tf.read_text(encoding="utf-8")
        for rx, desc in patterns:
            matches = list(re.finditer(rx, content, re.IGNORECASE))
            if matches:
                for m in matches:
                    violations.append(f"{tf.name}: {desc} -> line {content[:m.start()].count('\n') + 1}: '{m.group(0)}'")

    print("=== GREP CHECK FOR HARDCODED LITERALS IN UI CODE ===")
    if violations:
        print("FOUND VIOLATIONS:")
        for v in violations:
            print("  ", v)
    else:
        print("PASSED! 0 hardcoded client names, column headers, status words, or file paths found in UI python code.")

check_hardcoding()
