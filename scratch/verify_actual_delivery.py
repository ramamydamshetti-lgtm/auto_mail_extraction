import os
import sys
import json
from dotenv import load_dotenv

base_dir = r"g:\Auto_email_extraction (3)-new\Auto_email_extraction"
sys.path.insert(0, base_dir)
load_dotenv(os.path.join(base_dir, ".env"))

from config import Settings
from alerting import AlertManager, AlertType, AlertSeverity, send_graph_alert_email
from processed_store import ProcessedStore

def test_actual_notification_delivery():
    print("Outbound email delivery is PERMANENTLY DISABLED. Pipeline is extraction-only.")
    return False

if __name__ == "__main__":
    test_actual_notification_delivery()

