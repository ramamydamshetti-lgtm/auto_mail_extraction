#!/usr/bin/env python3
"""
Compare CSV analysis with JSON output to identify discrepancy
"""

import csv
import json
from datetime import datetime, date, timedelta

def compare_extraction_sources():
    """Compare what was found in CSV vs what's in JSON output"""
    
    target_date = "2026-04-23"
    
    print(f"=== Comparison Analysis for {target_date} ===")
    
    # 1. Get requirement emails from CSV
    print(f"\n1. CSV Analysis Results:")
    csv_requirements = []
    try:
        with open('today_fetch.csv', 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                received_date = row.get('received_date_time', '')
                if target_date in received_date:
                    subject = row.get('subject', '')
                    client = row.get('source_vendor_key', '')
                    from_email = row.get('from_email', '')
                    
                    # Check if it's a requirement email
                    subject_lower = subject.lower()
                    if any(term in subject_lower for term in ['requirement', 'tpc -', 'job', 'position', 'hiring']):
                        csv_requirements.append({
                            'subject': subject,
                            'client': client,
                            'from_email': from_email,
                            'received_date_time': received_date
                        })
        
        print(f"CSV found {len(csv_requirements)} requirement emails:")
        for i, req in enumerate(csv_requirements, 1):
            print(f"  {i}. {req['client']} | {req['subject']}")
            
    except Exception as e:
        print(f"Error reading CSV: {e}")
    
    # 2. Get requirements from JSON output
    print(f"\n2. JSON Output Results:")
    json_requirements = []
    try:
        with open('yesterday_corrected_requirements_2026-04-23.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            for req in data:
                json_requirements.append({
                    'job_title': req.get('job_title', ''),
                    'client': req.get('requirement_from', ''),
                    'from_email': req.get('source_from_email', ''),
                    'received_date_time': req.get('source_received_time', '')
                })
        
        print(f"JSON contains {len(json_requirements)} requirements:")
        for i, req in enumerate(json_requirements, 1):
            print(f"  {i}. {req['client']} | {req['job_title']}")
            
    except Exception as e:
        print(f"Error reading JSON: {e}")
    
    # 3. Compare and identify discrepancies
    print(f"\n3. Discrepancy Analysis:")
    
    csv_subjects = [req['subject'] for req in csv_requirements]
    json_titles = [req['job_title'] for req in json_requirements]
    
    print(f"CSV subjects: {len(csv_subjects)}")
    print(f"JSON titles: {len(json_titles)}")
    
    # Find missing in JSON
    missing_in_json = []
    for csv_req in csv_requirements:
        found = False
        for json_req in json_requirements:
            if csv_req['subject'] in json_req['job_title'] or json_req['job_title'] in csv_req['subject']:
                found = True
                break
        if not found:
            missing_in_json.append(csv_req)
    
    # Find extra in JSON
    extra_in_json = []
    for json_req in json_requirements:
        found = False
        for csv_req in csv_requirements:
            if csv_req['subject'] in json_req['job_title'] or json_req['job_title'] in csv_req['subject']:
                found = True
                break
        if not found:
            extra_in_json.append(json_req)
    
    print(f"\nMissing in JSON (found in CSV but not in output): {len(missing_in_json)}")
    for req in missing_in_json:
        print(f"  - {req['client']} | {req['subject']}")
    
    print(f"\nExtra in JSON (in output but not found in CSV): {len(extra_in_json)}")
    for req in extra_in_json:
        print(f"  - {req['client']} | {req['job_title']}")
    
    # 4. Check source JSON files
    print(f"\n4. Source JSON Files Check:")
    json_files = [
        f"today_client_emails_exhaustive_{target_date}.json",
        f"today_client_emails_exhaustive_{target_date}_accurate.json",
        f"today_client_emails_exhaustive_{target_date}_high_conf.json"
    ]
    
    for json_file in json_files:
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict) and 'emails' in data:
                    emails = data['emails']
                    print(f"{json_file}: {len(emails)} emails")
                    
                    # Show first few subjects
                    for email in emails[:3]:
                        print(f"  - {email.get('source_vendor_key', '')} | {email.get('subject', '')[:50]}...")
        except Exception as e:
            print(f"Error reading {json_file}: {e}")

if __name__ == "__main__":
    compare_extraction_sources()
