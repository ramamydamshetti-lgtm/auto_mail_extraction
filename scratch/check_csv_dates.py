import pandas as pd
import glob
import os

print("=== Checking CSV dates ===")
for path in ["today_fetch.csv", "latest_500_all.csv", "extractions.csv", "structured_recruitment_data.csv"]:
    if os.path.exists(path):
        print(f"\n--- File: {path} ---")
        try:
            df = pd.read_csv(path, low_memory=False)
            print(f"Columns: {list(df.columns[:8])}")
            date_cols = [c for c in df.columns if "date" in c.lower() or "time" in c.lower() or "created" in c.lower()]
            print(f"Date columns found: {date_cols}")
            for col in date_cols[:3]:
                series = df[col].dropna().astype(str)
                dates = series.str[:10].unique()
                sorted_dates = sorted([d for d in dates if len(d) == 10 and d[0].isdigit()], reverse=True)
                print(f"  Col '{col}' latest 5 dates: {sorted_dates[:5]}")
        except Exception as e:
            print(f"  Error reading {path}: {e}")
