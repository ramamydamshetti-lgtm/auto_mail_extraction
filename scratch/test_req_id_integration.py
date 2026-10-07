import unittest
import sqlite3
import json
import os
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, os.path.abspath("."))

from config import ClientIdentityConfig, get_client_identity_config
from processed_store import ProcessedStore
from requirement_parser import extract_req_id_table_requirements


class TestAccentureReqIdIdentity(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = TemporaryDirectory()
        self.db_path = os.path.join(self.tmp_dir.name, "test_processed.db")
        self.store = ProcessedStore(self.db_path)

    def tearDown(self):
        self.store.close()
        self.tmp_dir.cleanup()

    def test_rule_8_config_lookup(self):
        cfg = get_client_identity_config("accenture")
        self.assertIsNotNone(cfg)
        self.assertEqual(cfg.client_key, "accenture")
        self.assertTrue(cfg.use_req_id_identity)
        self.assertIn("accenture.com", cfg.sender_domains)
        self.assertIn("iexcel.co.in", cfg.sender_domains)
        self.assertIn("Request-ID", cfg.table_req_id_headers)

    def test_rule_1_extract_from_table(self):
        html = """
        <table>
            <tr><th>Request-ID</th><th>Equivalent Grade</th><th>Skills - Name</th><th>Priority</th></tr>
            <tr><td>195398-1</td><td>9</td><td>SoC Verification</td><td>P1</td></tr>
        </table>
        """
        items = extract_req_id_table_requirements(html, from_email="anusha.k@iexcel.co.in")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].req_id, "195398-1")
        self.assertEqual(items[0].raw_status, "P1")
        self.assertEqual(items[0].job_title, "SoC Verification")

    def test_rules_2_3_4_5_lifecycle(self):
        req_id = "208707-1"
        payload_1 = {
            "client_jd_id": req_id,
            "requirement_from": "Accenture",
            "job_title": "SAP BTP Application Development",
            "job_status": "hold",
            "priority": "Low"
        }
        # Rule 2: CREATE on new Req ID
        action1, _ = self.store.evaluate_client_requirement_action(
            client_jd_id=req_id, requirement_from="Accenture", payload=payload_1
        )
        self.assertEqual(action1, "CREATE")

        # Rule 3: SKIP on identical payload
        action2, _ = self.store.evaluate_client_requirement_action(
            client_jd_id=req_id, requirement_from="Accenture", payload=payload_1
        )
        self.assertEqual(action2, "SKIP")

        # Rule 4: UPDATE on status change (hold -> open)
        payload_2 = dict(payload_1)
        payload_2["job_status"] = "open"
        payload_2["priority"] = "High"
        action3, _ = self.store.evaluate_client_requirement_action(
            client_jd_id=req_id, requirement_from="Accenture", payload=payload_2
        )
        self.assertEqual(action3, "UPDATE")

        # Rule 5: UPDATE on details change
        payload_3 = dict(payload_2)
        payload_3["job_title"] = "SAP BTP Application Development Lead"
        action4, _ = self.store.evaluate_client_requirement_action(
            client_jd_id=req_id, requirement_from="Accenture", payload=payload_3
        )
        self.assertEqual(action4, "UPDATE")

if __name__ == "__main__":
    unittest.main()
