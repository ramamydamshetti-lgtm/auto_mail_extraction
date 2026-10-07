#!/usr/bin/env python3
"""
Check today's emails to understand the extraction issue
"""

import csv
from datetime import date

def check_todays_emails():
    """Check what emails were actually received today"""
    
    today = date.today().strftime('%Y-%m-%d')
    print(f"Checking emails for today: {today}")
    
    # Check today_fetch.csv
    print("\n=== Checking today_fetch.csv ===")
    try:
        with open('today_fetch.csv', 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            count = 0
            today_emails = []
            for row in reader:
                received_date = row.get('received_date_time', '')
                if today in received_date:
                    count += 1
                    today_emails.append({
                        'received_date_time': received_date,
                        'subject': row.get('subject', ''),
                        'from_email': row.get('from_email', ''),
                        'client': row.get('source_vendor_key', '')
                    })
            
            print(f"Emails from {today}: {count}")
            for email in today_emails:
                print(f"  - {email['received_date_time']} | {email['client']} | {email['subject'][:50]}...")
    except Exception as e:
        print(f"Error reading today_fetch.csv: {e}")
    
    # Check other CSV files
    other_files = ['today_fetch_2026-04-20.csv', 'today_fetch_2026-04-16.csv']
    for csv_file in other_files:
        print(f"\n=== Checking {csv_file} ===")
        if csv_file in today:
            continue  # Skip if it's today's file
            
        try:
            with open(csv_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                count = 0
                for row in reader:
                    received_date = row.get('received_date_time', '')
                    if today in received_date:
                        count += 1
                        print(f"  - {received_date} | {row.get('subject', '')[:50]}...")
                
                if count > 0:
                    print(f"Found {count} emails from {today} in {csv_file}")
        except Exception as e:
            print(f"Error reading {csv_file}: {e}")
    
    # Check JSON files
    json_files = [
        f"today_client_emails_exhaustive_{today}.json",
        f"today_client_emails_exhaustive_{today}_accurate.json",
        f"today_client_emails_exhaustive_{today}_high_conf.json"
    ]
    
    for json_file in json_files:
        print(f"\n=== Checking {json_file} ===")
        try:
            import json
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict) and 'emails' in data:
                    emails = data['emails']
                    count = len(emails)
                    print(f"Found {count} emails in {json_file}")
                    for email in emails[:3]:  # Show first 3
                        print(f"  - {email.get('received_date_time', '')} | {email.get('subject', '')[:50]}...")
                else:
                    print(f"No emails found in {json_file}")
        except Exception as e:
            print(f"Error reading {json_file}: {e}")

if __name__ == "__main__":
    check_todays_emails()
