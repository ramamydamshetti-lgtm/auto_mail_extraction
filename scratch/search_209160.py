import glob, os, json, sqlite3

print('=== Searching sqlite databases for 209160 ===')
for db in glob.glob('**/*.db', recursive=True):
    try:
        conn = sqlite3.connect(db)
        cur = conn.cursor()
        tables = [t[0] for t in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        for tbl in tables:
            try:
                rows = cur.execute(f"SELECT * FROM {tbl}").fetchall()
                for r in rows:
                    if '209160' in str(r):
                        print(f"Match in {db} -> {tbl}: {str(r)[:200]}")
            except Exception:
                pass
        conn.close()
    except Exception as e:
        pass

print('\n=== Searching JSON/CSV files for 209160 ===')
for fpath in glob.glob('**/*.json', recursive=True) + glob.glob('**/*.csv', recursive=True):
    if 'metaforge_consolidated' in fpath or '.venv' in fpath or 'node_modules' in fpath:
        continue
    try:
        with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
            c = f.read()
            if '209160' in c:
                print('Match in file:', fpath)
    except Exception:
        pass
