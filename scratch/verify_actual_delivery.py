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
    print("=" * 80)
    print("TESTING ACTUAL NOTIFICATION DELIVERY VIA MICROSOFT GRAPH API")
    print("=" * 80)
    
    settings = Settings.from_env()
    print(f"Tenant ID:       {settings.azure_tenant_id[:8]}...")
    print(f"Client ID:       {settings.azure_client_id[:8]}...")
    print(f"Mailbox UPN:     {settings.mailbox_upn}")
    print(f"Alert Recipient: {settings.alert_recipient_email}")
    print("-" * 80)

    # 1. Test direct send_graph_alert_email call
    subject = "Automated Alerting Verification Probe (Phase 4)"
    plain_text = (
        "[INFO] OPERATIONAL ALERT DELIVERY VERIFICATION\n"
        "This is an automated verification probe confirming that automated alerts\n"
        "are actually delivered via Microsoft Graph API to the configured recipient."
    )
    html_text = (
        "<html><body style='font-family: sans-serif;'>"
        "<div style='border: 1px solid #ddd; padding: 20px; border-radius: 6px;'>"
        "<h3 style='color: #0275d8;'>[INFO] Phase 4: Automated Alerting Live Delivery Probe</h3>"
        "<p>This confirms that operational notifications are <strong>actually delivered</strong> "
        "to the configured mailbox via Microsoft Graph API.</p>"
        "<p>Status: <strong>VERIFIED & DELIVERED</strong></p>"
        "</div></body></html>"
    )

    success, err = send_graph_alert_email(
        settings=settings,
        to_email=settings.alert_recipient_email,
        subject=subject,
        text_content=plain_text,
        html_content=html_text,
    )

    print(f"Delivery Outcome: {'SUCCESS (HTTP 202 Accepted)' if success else f'FAILED: {err}'}")
    print("=" * 80)
    return success

if __name__ == "__main__":
    ok = test_actual_notification_delivery()
    sys.exit(0 if ok else 1)
