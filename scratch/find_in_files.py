import os
import csv
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

def find_accenture_demands_in_files():
    for f in os.listdir('.'):
        if f.endswith('.csv') or f.endswith('.json'):
            path = os.path.join('.', f)
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as fp:
                    content = fp.read()
                    if 'anusha' in content.lower() or 'accenture open demands' in content.lower() or 'req id' in content.lower():
                        count_anusha = content.lower().count('anusha')
                        count_demands = content.lower().count('open demands')
                        count_reqid = content.lower().count('req id')
                        print(f"File: {f} -> anusha={count_anusha}, open demands={count_demands}, req id={count_reqid}")
            except Exception as e:
                print(f"Error reading {f}: {e}")

if __name__ == '__main__':
    find_accenture_demands_in_files()
