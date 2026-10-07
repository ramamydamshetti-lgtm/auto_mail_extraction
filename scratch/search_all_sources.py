import os
import glob
import re
import json
import sqlite3

pattern_domain = re.compile(r"id[e]?xcel(?:\.com|\.co\.in)?", re.I)
pattern_d = re.compile(r"\bD-Client\b|\bDClient\b", re.I)
pattern_p = re.compile(r"\bP-Client\b|\bPClient\b", re.I)

found_domains = {}
found_snippets = []

for root, dirs, files in os.walk("."):
    if ".venv" in root or ".git" in root or "__pycache__" in root:
        continue
    for fname in files:
        if fname.endswith((".csv", ".json", ".db", ".txt", ".md")):
            fpath = os.path.join(root, fname)
            try:
                if fname.endswith(".db"):
                    conn = sqlite3.connect(fpath)
                    cur = conn.cursor()
                    tables = [t[0] for t in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
                    for t in tables:
                        try:
                            rows = cur.execute(f"SELECT * FROM {t}").fetchall()
                            blob = str(rows)
                            d_matches = pattern_domain.findall(blob)
                            for d in d_matches:
                                found_domains[d.lower()] = found_domains.get(d.lower(), 0) + 1
                            if pattern_d.search(blob) or pattern_p.search(blob):
                                found_snippets.append(f"DB {fpath} table {t}")
                        except Exception:
                            pass
                    conn.close()
                else:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        text = f.read()
                        d_matches = pattern_domain.findall(text)
                        for d in d_matches:
                            found_domains[d.lower()] = found_domains.get(d.lower(), 0) + 1
                        if pattern_d.search(text) or pattern_p.search(text):
                            found_snippets.append(f"File {fpath}")
            except Exception:
                pass

print("=== ALL DOMAIN MATCHES ACROSS WORKSPACE ===")
for d, c in found_domains.items():
    print(f"Domain match: '{d}' -> Count: {c}")

print(f"\n=== D-CLIENT / P-CLIENT REFERENCES FOUND IN WORKSPACE: {len(found_snippets)} ===")
for s in found_snippets[:10]:
    print("  ", s)
