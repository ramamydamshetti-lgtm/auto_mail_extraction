import os
import csv
import json
import re

def search_accenture_tables():
    print("Searching for Accenture tables and emails across files...")
    
    # 1. Check latest_500_all.json
    if os.path.exists('latest_500_all.json'):
        with open('latest_500_all.json', 'r', encoding='utf-8', errors='ignore') as f:
            data = json.load(f)
            print(f"latest_500_all.json has {len(data)} items")
            for idx, item in enumerate(data):
                text = json.dumps(item).lower()
                if 'accenture' in text or 'req id' in text or 'open demands' in text:
                    print(f"JSON Item {idx}: Subject={item.get('subject')}, From={item.get('from_email') or item.get('from')}")
                    body = item.get('body_normalized') or item.get('body') or item.get('body_text') or ''
                    print("Snippet:", body[:300])
                    print("="*50)

if __name__ == '__main__':
    search_accenture_tables()
