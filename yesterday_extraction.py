#!/usr/bin/env python3
"""
Extract yesterday's requirements to verify date/time filtering
"""

import json
import csv
import re
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, List, Any

def extract_yesterday_requirements():
    """Extract yesterday's requirements"""
    
    yesterday = date.today() - timedelta(days=1)
    target_date = yesterday.strftime('%Y-%m-%d')
    
    print(f"Extracting requirements for yesterday: {target_date}")
    
    all_requirements = []
    processed_ids = set()
    
    # Check yesterday's emails in CSV
    print(f"\n=== Checking yesterday's emails in CSV ===")
    try:
        with open('today_fetch.csv', 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            yesterday_emails = []
            for row in reader:
                received_date = row.get('received_date_time', '')
                if target_date in received_date:
                    yesterday_emails.append({
                        'received_date_time': received_date,
                        'subject': row.get('subject', ''),
                        'from_email': row.get('from_email', ''),
                        'client': row.get('source_vendor_key', ''),
                        'graph_id': row.get('graph_id', '')
                    })
            
            print(f"Found {len(yesterday_emails)} emails from {target_date}")
            
            # Process only requirement emails
            requirement_emails = []
            for email in yesterday_emails:
                subject = email['subject'].lower()
                # Simple requirement detection
                if any(term in subject for term in ['requirement', 'tpc -', 'job', 'position', 'hiring']):
                    requirement_emails.append(email)
            
            print(f"Identified {len(requirement_emails)} requirement emails")
            for email in requirement_emails:
                print(f"  - {email['received_date_time']} | {email['client']} | {email['subject'][:50]}...")
                
    except Exception as e:
        print(f"Error: {e}")
    
    # Process JSON files for yesterday
    json_files = [
        f"today_client_emails_exhaustive_{target_date}.json",
        f"today_client_emails_exhaustive_{target_date}_accurate.json",
        f"today_client_emails_exhaustive_{target_date}_high_conf.json"
    ]
    
    print(f"\n=== Processing JSON files for {target_date} ===")
    for json_file in json_files:
        if Path(json_file).exists():
            print(f"Processing {json_file}...")
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, dict) and 'emails' in data:
                        emails = data['emails']
                        print(f"Found {len(emails)} emails in {json_file}")
                        
                        # Count requirement emails
                        req_count = 0
                        for email in emails:
                            graph_id = email.get('graph_id', '')
                            if graph_id and graph_id not in processed_ids:
                                processed_ids.add(graph_id)
                                req_count += 1
                        
                        print(f"Processed {req_count} unique requirements")
            except Exception as e:
                print(f"Error processing {json_file}: {e}")
    
    # Generate yesterday's output
    print(f"\n=== Yesterday's Extraction Summary ===")
    print(f"Date: {target_date}")
    print(f"Total emails found: {len(yesterday_emails) if 'yesterday_emails' in locals() else 0}")
    print(f"Requirement emails identified: {len(requirement_emails) if 'requirement_emails' in locals() else 0}")
    print(f"Requirements processed: {len(processed_ids)}")
    
    return len(yesterday_emails) if 'yesterday_emails' in locals() else 0

if __name__ == "__main__":
    extract_yesterday_requirements()
