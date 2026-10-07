"""
Comprehensive end-to-end verification of today's 30 production updated records via running UI and API.
Guarantees ZERO production database writes.
"""

import os
import sys
import json
import urllib.request
import urllib.error
import sqlite3

BASE_URL = "http://127.0.0.1:5000"
REPO_DIR = r"g:\Auto_email_extraction (3)-new\Auto_email_extraction"
DRY_RUN_JSON = os.path.join(REPO_DIR, "scratch", "production_dry_run_results.json")
MF_DB = os.path.join(REPO_DIR, "data", "metaforge_requirements.db")

def check_db_count():
    conn = sqlite3.connect(f"file:{MF_DB}?mode=ro", uri=True)
    cnt = conn.execute("SELECT count(*) FROM metaforge_requirements").fetchone()[0]
    conn.close()
    return cnt

def run_verification():
    cnt_before = check_db_count()
    print(f"Pre-check MetaForge requirements count: {cnt_before}")

    with open(DRY_RUN_JSON, "r", encoding="utf-8") as f:
        dry_run = json.load(f)

    records = dry_run.get("records_with_changes_detail", [])
    print(f"Loaded {len(records)} verified records from today's production write.\n")

    results = []
    failed_records = []

    for idx, expected in enumerate(records, 1):
        job_id = expected["job_id"]
        cjd = expected.get("cjd")
        client = expected.get("client")
        title = expected.get("title")

        # 1. Test API endpoint for requirement
        api_url = f"{BASE_URL}/api/requirement/{urllib.parse.quote(job_id)}"
        req_data = None
        try:
            req = urllib.request.Request(api_url, headers={"User-Agent": "VerificationScript/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    req_data = json.loads(resp.read().decode())
                else:
                    failed_records.append((idx, job_id, f"API HTTP {resp.status}"))
                    continue
        except Exception as e:
            # Try by client_jd_id if job_id didn't route directly
            if cjd:
                try:
                    alt_url = f"{BASE_URL}/api/requirement/{urllib.parse.quote(cjd)}"
                    with urllib.request.urlopen(alt_url, timeout=10) as resp:
                        if resp.status == 200:
                            req_data = json.loads(resp.read().decode())
                except Exception:
                    pass
            if not req_data:
                failed_records.append((idx, job_id, f"API Exception: {e}"))
                continue

        # 2. Test Frontend HTML endpoint
        html_url = f"{BASE_URL}/requirement/{urllib.parse.quote(job_id)}"
        html_content = ""
        try:
            req_html = urllib.request.Request(html_url, headers={"User-Agent": "VerificationScript/1.0"})
            with urllib.request.urlopen(req_html, timeout=10) as resp:
                if resp.status in (200, 302):
                    html_content = resp.read().decode()
                else:
                    failed_records.append((idx, job_id, f"HTML HTTP {resp.status}"))
        except Exception as e:
            failed_records.append((idx, job_id, f"HTML Exception: {e}"))

        # Verify fields in returned API payload
        payload = req_data.get("payload", {})
        ui_req_id = req_data.get("req_id")
        ui_client = payload.get("requirement_from")
        ui_cjd = payload.get("client_jd_id") or req_data.get("client_jd_id")
        ui_title = payload.get("job_title")
        ui_location = payload.get("location")
        ui_experience = payload.get("overall_experience")
        ui_budget = payload.get("monthly_budget") or payload.get("yearly_budget") or payload.get("budget_text")
        ui_work_mode = payload.get("work_mode")
        ui_skills = payload.get("mandatory_skills") or payload.get("skills")

        # Routing check: job_id matches or canonical ID matches
        routing_ok = (ui_req_id == job_id or req_data.get("raw_req_id") == job_id or req_data.get("job_id") == job_id)
        if not routing_ok and cjd and ui_cjd == cjd:
            routing_ok = True

        # Check expected changes from today's write
        changes = expected.get("changes", {})
        changes_verified = True
        change_diffs = []
        for fld, diff in changes.items():
            to_val = diff.get("to")
            curr_ui_val = payload.get(fld)
            # Accept list vs string matching for skills
            if isinstance(to_val, list):
                curr_list = curr_ui_val if isinstance(curr_ui_val, list) else [curr_ui_val]
                if not any(item in curr_list for item in to_val):
                    changes_verified = False
                    change_diffs.append(f"{fld}: expected {to_val}, got {curr_ui_val}")
            elif to_val is None:
                if curr_ui_val not in (None, "", "—"):
                    changes_verified = False
                    change_diffs.append(f"{fld}: expected None/empty, got {curr_ui_val}")
            else:
                if str(curr_ui_val or "").strip() != str(to_val).strip():
                    changes_verified = False
                    change_diffs.append(f"{fld}: expected '{to_val}', got '{curr_ui_val}'")

        rec_res = {
            "index": idx,
            "job_id": job_id,
            "cjd": cjd,
            "routing_ok": routing_ok,
            "ui_req_id": ui_req_id,
            "ui_client": ui_client,
            "ui_title": ui_title,
            "ui_location": ui_location,
            "ui_experience": ui_experience,
            "ui_budget": ui_budget,
            "ui_work_mode": ui_work_mode,
            "skills_count": len(ui_skills) if isinstance(ui_skills, list) else (1 if ui_skills else 0),
            "changes_verified": changes_verified,
            "change_diffs": change_diffs,
            "html_rendered": len(html_content) > 500,
        }
        results.append(rec_res)

        status_str = "PASS" if routing_ok and changes_verified else "FAIL"
        print(f"[{status_str}] Record {idx:02d}: {job_id} | Client: {ui_client} | Title: {ui_title[:30] if ui_title else 'None'} | Loc: {ui_location} | Exp: {ui_experience} | Changes: {'OK' if changes_verified else change_diffs}")

    cnt_after = check_db_count()
    print("\n" + "=" * 80)
    print(f"VERIFICATION SUMMARY:")
    print(f"Total Records Tested:   {len(results)}")
    print(f"Successful Routing:     {sum(1 for r in results if r['routing_ok'])} / {len(results)}")
    print(f"Changes Verified in UI: {sum(1 for r in results if r['changes_verified'])} / {len(results)}")
    print(f"HTML Detail Rendered:   {sum(1 for r in results if r['html_rendered'])} / {len(results)}")
    print(f"Database Writes:        {cnt_after - cnt_before} (Before: {cnt_before}, After: {cnt_after})")
    print("=" * 80)

    # Specific checks requested by user:
    # 1. R23 / R24
    print("\nChecking R23 / R24 Routing:")
    r23 = next((r for r in results if r["index"] == 23), None)
    r24 = next((r for r in results if r["index"] == 24), None)
    if r23:
        print(f"  R23: job_id={r23['job_id']}, ui_req_id={r23['ui_req_id']}, title={r23['ui_title']}, routing_ok={r23['routing_ok']}")
    if r24:
        print(f"  R24: job_id={r24['job_id']}, ui_req_id={r24['ui_req_id']}, title={r24['ui_title']}, routing_ok={r24['routing_ok']}")

    # 2. 2026/09/04 records
    print("\nChecking 2026/09/04 Records:")
    sep4_records = [r for r in results if "2026/09/04" in r["job_id"]]
    for r in sep4_records:
        print(f"  {r['job_id']}: ui_req_id={r['ui_req_id']}, title={r['ui_title']}, routing_ok={r['routing_ok']}")

    return results

if __name__ == "__main__":
    run_verification()
