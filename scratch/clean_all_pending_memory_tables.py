import sqlite3
import os

db_proc = 'data/processed_messages.db'
if os.path.exists(db_proc):
    conn = sqlite3.connect(db_proc)
    cur = conn.cursor()
    
    print("=== TABLES IN processed_messages.db ===")
    tables = [t[0] for t in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    for t in tables:
        count = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f" Table '{t}': {count} rows")
        
    # Clear pending_reviews and requirement_memory so UI reads purely from metaforge_requirements table
    cur.execute("DELETE FROM pending_reviews")
    cur.execute("DELETE FROM requirement_memory")
    cur.execute("DELETE FROM client_requirements")
    conn.commit()
    print("\nCleared pending_reviews, requirement_memory, and client_requirements from processed_messages.db!")
    conn.close()
