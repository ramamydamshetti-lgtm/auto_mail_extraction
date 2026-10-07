import sqlite3
import json

print("================ SEPTEMBER 01, 2026 TO SEPTEMBER 28, 2026 FULL SUMMARY ================")

# Connect to processed_messages.db (requirement_memory)
conn_mem = sqlite3.connect("file:data/processed_messages.db?mode=ro", uri=True)
conn_mem.row_factory = sqlite3.Row

rows_mem = conn_mem.execute("""
    SELECT requirement_from, payload_json, created_at 
    FROM requirement_memory 
    WHERE DATE(created_at) >= '2026-09-01' AND DATE(created_at) <= '2026-09-28'
""").fetchall()

client_counts = {}
daily_counts = {}

for r in rows_mem:
    p = json.loads(r["payload_json"])
    client_raw = (p.get("requirement_from") or r["requirement_from"] or "Other").strip()
    date_str = r["created_at"][:10]

    # Normalize client names
    client = client_raw
    c_lower = client_raw.lower()
    if "accenture" in c_lower or "iexcel" in c_lower:
        client = "Accenture"
    elif "ltts" in c_lower or "l&t" in c_lower:
        client = "LTTS"
    elif "itc" in c_lower:
        client = "ITC Infotech"
    elif "kpmg" in c_lower:
        client = "KPMG"

    client_counts[client] = client_counts.get(client, 0) + 1
    
    if date_str not in daily_counts:
        daily_counts[date_str] = {}
    daily_counts[date_str][client] = daily_counts[date_str].get(client, 0) + 1

conn_mem.close()

total_sept = sum(client_counts.values())

print(f"\nTOTAL REQUIREMENTS RECEIVED (01/09/2026 to 28/09/2026): {total_sept}")

print("\n--- CLIENT BREAKDOWN ---")
for client, count in sorted(client_counts.items(), key=lambda x: x[1], reverse=True):
    print(f" • {client:<20}: {count} requirements")

print("\n--- DAILY BREAKDOWN ---")
for d in sorted(daily_counts.keys()):
    day_total = sum(daily_counts[d].values())
    c_str = ", ".join([f"{c}: {cnt}" for c, cnt in daily_counts[d].items()])
    print(f" Date {d}: Total = {day_total:<3} ({c_str})")
