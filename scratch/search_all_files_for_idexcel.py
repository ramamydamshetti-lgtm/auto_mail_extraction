import os
import glob
import re
import csv
import json

pattern_idexcel = re.compile(r"\b[a-zA-Z0-9._%+-]*id[e]?xcel[a-zA-Z0-9._%+-]*\b", re.I)
pattern_d_client = re.compile(r"\bD-Client\b", re.I)
pattern_p_client = re.compile(r"\bP-Client\b", re.I)

print("=== SEARCHING ALL CSV / JSON FILES ===")

files_to_check = glob.glob("*.csv") + glob.glob("*.json") + glob.glob("data/*.csv") + glob.glob("data/*.json")

for fpath in files_to_check:
    try:
        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
            
            m_idexcel = set(pattern_idexcel.findall(content))
            m_dclient = pattern_d_client.findall(content)
            m_pclient = pattern_p_client.findall(content)
            
            if m_idexcel or m_dclient or m_pclient:
                print(f"\nFile: {fpath}")
                if m_idexcel:
                    print(f"  idexcel matches ({len(m_idexcel)} unique): {m_idexcel}")
                if m_dclient:
                    print(f"  D-Client matches count: {len(m_dclient)}")
                if m_pclient:
                    print(f"  P-Client matches count: {len(m_pclient)}")
    except Exception as e:
        pass
