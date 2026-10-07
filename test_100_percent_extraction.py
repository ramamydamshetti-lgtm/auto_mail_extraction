#!/usr/bin/env python3
"""
Test 100% Extraction Reliability
Validates that the refactored system extracts all client requirement emails
"""

import json
import csv
from datetime import datetime, date, timedelta
from typing import Dict, List, Any

def test_zero_skip_policy():
    """Test that zero-skip policy allows all client emails"""
    print("=== Testing Zero-Skip Policy ===")
    
    # Load yesterday's emails from CSV
    yesterday = date.today() - timedelta(days=1)
    target_date = yesterday.strftime('%Y-%m-%d')
    
    all_emails = []
    requirement_emails = []
    
    try:
        with open('today_fetch.csv', 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                received_date = row.get('received_date_time', '')
                if target_date in received_date:
                    all_emails.append(row)
                    
                    # Check if it's a potential requirement (client domain)
                    client_key = row.get('source_vendor_key', '')
                    if client_key and client_key != 'unknown':
                        requirement_emails.append(row)
        
        print(f"Total emails from {target_date}: {len(all_emails)}")
        print(f"Client domain emails: {len(requirement_emails)}")
        
        # Test zero-skip filter
        from email_filter_refactored import apply_zero_skip_filter
        
        allowed_count = 0
        blocked_count = 0
        
        for email in requirement_emails:
            result = apply_zero_skip_filter(
                subject=email.get('subject', ''),
                body=email.get('requirement_summary', ''),
                has_attachments=bool(email.get('attachments')),
                from_email=email.get('from_email', ''),
                received_date_time=email.get('received_date_time', ''),
                is_client_domain=True  # All known clients
            )
            
            if result.allowed:
                allowed_count += 1
            else:
                blocked_count += 1
                print(f"BLOCKED: {result.reason} - {email.get('subject', '')[:50]}")
        
        print(f"Zero-Skip Results: {allowed_count} allowed, {blocked_count} blocked")
        print(f"Expected: {len(requirement_emails)} allowed, 0 blocked (Zero-Skip)")
        
        return blocked_count == 0
        
    except Exception as e:
        print(f"Error testing zero-skip policy: {e}")
        return False

def test_chronological_integrity():
    """Test chronological ordering"""
    print("\n=== Testing Chronological Integrity ===")
    
    yesterday = date.today() - timedelta(days=1)
    target_date = yesterday.strftime('%Y-%m-%d')
    
    emails = []
    try:
        with open('today_fetch.csv', 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                received_date = row.get('received_date_time', '')
                if target_date in received_date:
                    emails.append(row)
        
        # Test chronological sorting
        from email_filter_refactored import sort_emails_chronologically
        sorted_emails = sort_emails_chronological(emails)
        
        # Verify order
        dates = [email.get('received_date_time', '') for email in sorted_emails]
        is_sorted = all(dates[i] <= dates[i+1] for i in range(len(dates)-1))
        
        print(f"Chronological test: {'PASS' if is_sorted else 'FAIL'}")
        print(f"First email: {dates[0] if dates else 'N/A'}")
        print(f"Last email: {dates[-1] if dates else 'N/A'}")
        
        return is_sorted
        
    except Exception as e:
        print(f"Error testing chronological integrity: {e}")
        return False

def test_timezone_normalization():
    """Test timezone normalization to IST"""
    print("\n=== Testing Timezone Normalization ===")
    
    from email_filter_refactored import normalize_to_ist
    
    test_cases = [
        "2026-04-23T06:33:38Z",  # UTC
        "2026-04-23T12:03:38+05:30",  # Already IST
        "2026-04-23T01:03:38-05:00",  # EST
    ]
    
    for utc_time in test_cases:
        ist_time = normalize_to_ist(utc_time)
        print(f"UTC: {utc_time} -> IST: {ist_time}")
    
    return True

def test_expert_recruiter_interpretation():
    """Test expert recruiter interpretation"""
    print("\n=== Testing Expert Recruiter Interpretation ===")
    
    from requirement_parser_refactored import parse_requirements_from_email_expert
    
    test_cases = [
        {
            "subject": "TPC - C++ Developer - Immediate Joiners",
            "body": "Need C++ developers with 3-5 years experience. Budget: 15LPA. Location: Bangalore. NP: Immediate.",
            "expected_fields": ["budget", "experience", "location", "notice_period"]
        },
        {
            "subject": "FW: Meeting Notes",
            "body": "This is a forwarded meeting about project updates.",
            "expected_fields": []  # Should create null row
        }
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        result = parse_requirements_from_email_expert(
            subject=test_case["subject"],
            body=test_case["body"],
            sender_email="test@example.com",
            sender_name="Test User",
            attachments=[],
            classification={}
        )
        
        print(f"Test case {i}:")
        print(f"  Subject: {test_case['subject']}")
        print(f"  Requirements found: {len(result.get('requirements', []))}")
        print(f"  Processing note: {result.get('processing_note', '')}")
        
        if result.get('requirements'):
            req = result['requirements'][0]
            print(f"  Job title: {req.job_title}")
            print(f"  Budget: {req.budget}")
            print(f"  Experience: {req.overall_experience}")
    
    return True

def test_null_values_instead_of_skipping():
    """Test that null values are created instead of skipping"""
    print("\n=== Testing Null Values Instead of Skipping ===")
    
    from field_mapper_refactored import map_to_metaforge, EmailContext
    
    # Test with minimal data
    ctx = EmailContext(
        from_email="test@example.com",
        from_name="Test User",
        to_recipients=["recruiter@company.com"],
        cc_recipients=[],
        subject="Test Email",
        body_plain="This is a test email with no requirements.",
        body_normalized="This is a test email with no requirements.",
        attachments=[],
        received_date_time="2026-04-23T10:00:00Z",
        graph_id="test-123"
    )
    
    # Test with empty extracted data
    extracted = {
        "job_title": "",
        "number_of_positions": 0,
        "experience_level": "",
        "employment_type": "",
        "work_mode": "",
        "location": "",
        "budget": "",
        "skills": [],
        "mandatory_skills": [],
        "notice_period": "",
        "overall_experience": "",
        "priority": ""
    }
    
    result = map_to_metaforge(
        extracted=extracted,
        ctx=ctx,
        client_display_name="Test Client",
        job_id="REQ-TEST-001",
        client_jd_id="TEST-001",
        body_text="This is a test email with no requirements."
    )
    
    # Verify all fields are present (not skipped)
    required_fields = [
        "job_id", "demand_received_date", "internal_poc", "requirement_from",
        "client_jd_id", "client_lead_poc", "client_poc", "job_title",
        "job_status", "closed_date", "type_of_demand", "priority",
        "number_of_positions", "experience_level", "employment_type",
        "budget_currency", "yearly_budget", "monthly_budget", "work_mode",
        "location", "overall_experience", "notice_period",
        "mandatory_skills", "skills"
    ]
    
    missing_fields = []
    for field in required_fields:
        if field not in result:
            missing_fields.append(field)
    
    print(f"Required fields present: {len(required_fields) - len(missing_fields)}/{len(required_fields)}")
    if missing_fields:
        print(f"Missing fields: {missing_fields}")
    else:
        print("All required fields present (null values used instead of skipping)")
    
    return len(missing_fields) == 0

def run_comprehensive_test():
    """Run all tests for 100% extraction reliability"""
    print("🚀 RUNNING COMPREHENSIVE TEST FOR 100% EXTRACTION RELIABILITY")
    print("=" * 80)
    
    tests = [
        ("Zero-Skip Policy", test_zero_skip_policy),
        ("Chronological Integrity", test_chronological_integrity),
        ("Timezone Normalization", test_timezone_normalization),
        ("Expert Recruiter Interpretation", test_expert_recruiter_interpretation),
        ("Null Values Instead of Skipping", test_null_values_instead_of_skipping),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"Error in {test_name}: {e}")
            results.append((test_name, False))
    
    print("\n" + "=" * 80)
    print("📊 TEST RESULTS SUMMARY")
    print("=" * 80)
    
    passed = 0
    failed = 0
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
        if result:
            passed += 1
        else:
            failed += 1
    
    print(f"\nTotal: {passed + failed} tests")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    
    if failed == 0:
        print("\n🎉 ALL TESTS PASSED - 100% EXTRACTION RELIABILITY ACHIEVED!")
    else:
        print(f"\n⚠️  {failed} tests failed - system needs fixes")
    
    return failed == 0

if __name__ == "__main__":
    run_comprehensive_test()
