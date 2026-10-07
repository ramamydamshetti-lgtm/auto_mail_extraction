#!/usr/bin/env python3
"""
Check recent emails to find the one received today
"""

import csv
from datetime import datetime, date, timedelta

def check_recent_emails():
    """Check recent emails from today and yesterday"""
    
    today = date.today().strftime('%Y-%m-%d')
    yesterday = (date.today() - timedelta(days=1)).strftime('%Y-%m-%d')
    
    print(f"Checking emails for today: {today}")
    print(f"Checking emails for yesterday: {yesterday}")
    
    # Check today_fetch.csv for recent emails
    print("\n=== Recent emails from today_fetch.csv ===")
    try:
        with open('today_fetch.csv', 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            recent_emails = []
            for row in reader:
                received_date = row.get('received_date_time', '')
                if today in received_date or yesterday in received_date:
                    recent_emails.append({
                        'received_date_time': received_date,
                        'subject': row.get('subject', ''),
                        'from_email': row.get('from_email', ''),
                        'client': row.get('source_vendor_key', ''),
                        'graph_id': row.get('graph_id', '')
                    })
            
            print(f"Recent emails found: {len(recent_emails)}")
            for email in recent_emails:
                print(f"  {email['received_date_time']} | {email['client']} | {email['from_email']} | {email['subject'][:60]}...")
    except Exception as e:
        print(f"Error reading today_fetch.csv: {e}")
    
    # Check if there are any files with today's date
    import os
    print(f"\n=== Files with today's date ({today}) ===")
    for file in os.listdir('.'):
        if today in file and file.endswith('.json'):
            print(f"  {file}")
    
    # Check the most recent emails in the CSV
    print(f"\n=== Most recent emails overall ===")
    try:
        with open('today_fetch.csv', 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            # Get last 10 emails by date
            recent_rows = sorted(rows, key=lambda x: x.get('received_date_time', ''), reverse=True)[:10]
            
            for row in recent_rows:
                print(f"  {row.get('received_date_time', '')} | {row.get('source_vendor_key', '')} | {row.get('subject', '')[:60]}...")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_recent_emails()
