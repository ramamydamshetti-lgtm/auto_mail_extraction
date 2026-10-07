"""Unit tests for Recruiter Application Flask UI."""

import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from ui.app import app, load_config
from ui.db import _open_ro_connection, fetch_all_records, get_requirement


class TestUI(unittest.TestCase):

    def setUp(self):
        # Create temporary database file
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp_dir.name, "test_reqs.db")

        # Initialize test schema and seed data
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """CREATE TABLE metaforge_requirements (
                job_id TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )"""
        )

        test_payloads = [
            {
                "job_id": "2026/04/24-001",
                "client_jd_id": "203421-1",
                "requirement_from": "Accenture",
                "job_title": "Python Engineer",
                "location": "Bangalore",
                "number_of_positions": 3,
                "job_status": "Open",
            },
            {
                "job_id": "2026/04/24-002",
                "client_jd_id": "LTTS-REQ-1002",
                "requirement_from": "LTTS",
                "job_title": "React Developer",
                "location": "Mumbai",
                "number_of_positions": 1,
                "job_status": "Hold",
            },
        ]

        for p in test_payloads:
            conn.execute(
                "INSERT INTO metaforge_requirements (job_id, payload_json, created_at) VALUES (?, ?, ?)",
                (p["job_id"], json.dumps(p), "2026-04-24T10:00:00Z"),
            )
        conn.commit()
        conn.close()

        # Configure test Flask app
        app.config["TESTING"] = True
        self.client = app.test_client()

        # Override app UI config for testing
        from ui.app import UI_CONFIG
        UI_CONFIG["db_paths"] = [self.db_path]
        UI_CONFIG["default_page_size"] = 10

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir.name, ignore_errors=True)

    def test_read_only_connection_prevents_writes(self):
        """Verify that opening DB in read-only mode prevents any write operations."""
        conn = _open_ro_connection(self.db_path)
        self.assertIsNotNone(conn)
        with self.assertRaises(sqlite3.OperationalError):
            conn.execute(
                "INSERT INTO metaforge_requirements (job_id, payload_json, created_at) VALUES ('FAIL', '{}', '2026-01-01')"
            )
        conn.close()

    def test_list_page_loads(self):
        """Test home page loads with seed requirements."""
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"2026/04/24-001", res.data)
        self.assertIn(b"203421-1", res.data)

    def test_search_and_filter(self):
        """Test searching and filtering parameters."""
        # Filter by client
        res = self.client.get("/?client=Accenture")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"2026/04/24-001", res.data)
        self.assertNotIn(b"LTTS-REQ-1002", res.data)

        # Filter by search query
        res = self.client.get("/?q=React")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"2026/04/24-002", res.data)
        self.assertNotIn(b"203421-1", res.data)

    def test_detail_page(self):
        """Test requirement detail view."""
        res = self.client.get("/requirement/2026/04/24-001")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Python Engineer", res.data)

    def test_unknown_requirement_detail(self):
        """Test that unknown requirement returns 404 error page."""
        res = self.client.get("/requirement/UNKNOWN-ID-999")
        self.assertEqual(res.status_code, 404)
        self.assertIn(b"not found", res.data.lower())

    def test_api_requirement_autofill(self):
        """Test API endpoint for requirement detail autofill."""
        res = self.client.get("/api/requirement/2026/04/24-001")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["req_id"], "2026/04/24-001")
        self.assertEqual(data["payload"]["job_title"], "Python Engineer")

    def test_api_req_ids_suggestions(self):
        """Test API endpoint for requirement ID suggestions."""
        res = self.client.get("/api/req-ids?prefix=2026")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
    def test_no_fabricated_fallback_values(self):
        """Test that missing fields render honest 'Not specified' and never fabricated placeholders."""
        # Insert a requirement with completely null optional fields
        conn = sqlite3.connect(self.db_path)
        null_payload = {
            "job_id": "2026/04/24-003",
            "client_jd_id": "TEST-NULL-003",
            "requirement_from": None,
            "job_title": None,
            "location": None,
            "number_of_positions": None,
            "job_status": None,
            "priority": None,
            "monthly_budget": None,
            "yearly_budget": None,
            "notice_period": None,
            "client_lead_poc": None,
            "internal_poc_email": None,
        }
        conn.execute(
            "INSERT INTO metaforge_requirements (job_id, payload_json, created_at) VALUES (?, ?, ?)",
            (null_payload["job_id"], json.dumps(null_payload), "2026-04-24T12:00:00Z"),
        )
        conn.commit()
        conn.close()

        # Invalidate cache
        from ui import db
        db._CACHE_RECORDS = None

        res_detail = self.client.get("/requirement/2026/04/24-003")
        self.assertEqual(res_detail.status_code, 200)
        html_detail = res_detail.data.decode("utf-8")

        # Prohibited fabricated strings that must never appear as fallbacks
        prohibited_fabricated_strings = [
            "Accenture Requirement",
            "Requirement Role",
            "Other company / source",
            "anusha.k@iexcel.co.in",
            "Accenture open demands for 30th Sep",
            "4+ years of experience in ServiceNow",
            "9 days",
        ]

        for s in prohibited_fabricated_strings:
            self.assertNotIn(s, html_detail, f"Fabricated string '{s}' appeared in detail view!")

        res_list = self.client.get("/")
        self.assertEqual(res_list.status_code, 200)
        html_list = res_list.data.decode("utf-8")

        for s in ["Accenture Requirement", "Requirement Role", "Other company / source"]:
            self.assertNotIn(s, html_list, f"Fabricated string '{s}' appeared in list view!")


if __name__ == "__main__":
    unittest.main()
