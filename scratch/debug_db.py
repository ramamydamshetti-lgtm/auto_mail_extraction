import sys, os, sqlite3, json
sys.path.insert(0, '.')
from ui.app import load_config
from ui.db import _open_ro_connection

cfg = load_config()
print("Config db_paths:", cfg.get("db_paths"))
for path in cfg.get("db_paths", []):
    print("Path:", path, "Exists:", os.path.exists(path))
    conn = _open_ro_connection(path)
    if conn:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        print("  Tables:", tables)
        conn.close()
