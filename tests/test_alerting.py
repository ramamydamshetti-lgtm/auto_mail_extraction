"""
Unit and integration tests for Phase 4 Automated Alerting.
All tests use isolated temporary directories and databases, guaranteeing ZERO production writes.
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import dataclasses
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from config import Settings
from processed_store import ProcessedStore
from alerting import (
    AlertManager,
    AlertSeverity,
    AlertType,
    sanitize_alert_details,
    send_graph_alert_email,
    build_alert_email_body,
)


@pytest.fixture
def temp_alert_env(tmp_path: Path):
    """Provide isolated environment with temp databases and mock settings."""
    db_path = tmp_path / "test_processed.db"
    store = ProcessedStore(str(db_path))

    hb_path = tmp_path / "scheduler_heartbeat.json"

    settings = Settings(
        azure_tenant_id="test-tenant",
        azure_client_id="test-client-id",
        azure_client_secret="test-secret",
        mailbox_upn="recruitment.application@metaforgeit.com",
        openai_api_key="mock-key",
        openai_model="gpt-4o-mini",
        metaforge_api_url="http://localhost:8000",
        metaforge_requirements_endpoint="api/internal/requirements/ingest-email",
        metaforge_mode="sqlite",
        metaforge_sqlite_path=str(tmp_path / "metaforge.db"),
        metaforge_id_db=str(tmp_path / "seq.db"),
        processed_db=str(db_path),
        scheduler_heartbeat_path=str(hb_path),
        alert_recipient_email="ops-alerts@metaforgeit.com",
        alert_cooldown_seconds=600,
        alert_heartbeat_max_age_seconds=300,
        alert_failure_threshold=3,
    )

    sent_alerts: list[dict] = []

    def mock_sender(cfg, recipient, subject, plain, html):
        sent_alerts.append({
            "recipient": recipient,
            "subject": subject,
            "plain": plain,
            "html": html,
        })
        return True, None

    manager = AlertManager(settings, store, custom_sender=mock_sender)

    return {
        "tmp_path": tmp_path,
        "store": store,
        "hb_path": hb_path,
        "settings": settings,
        "manager": manager,
        "sent_alerts": sent_alerts,
    }


def test_sanitize_alert_details():
    """Verify that sensitive keys, tokens, bodies, and candidate PII are stripped."""
    raw = {
        "job_id": "2026/09/01-001",
        "client": "Accenture",
        "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.sensitive_token_payload",
        "secret": "my-client-secret",
        "password": "super-secret-password",
        "bodyText": "Dear recruiter, here is John Doe's resume for Java dev",
        "candidate": "John Doe",
        "phone": "+91 9876543210",
        "nested": {
            "email_body": "Full body text with private info",
            "safe_metric": 42,
        },
    }

    sanitized = sanitize_alert_details(raw)

    assert "job_id" in sanitized
    assert "client" in sanitized
    assert "token" not in sanitized
    assert "secret" not in sanitized
    assert "password" not in sanitized
    assert "bodyText" not in sanitized
    assert "candidate" not in sanitized
    assert "phone" not in sanitized
    assert sanitized["nested"] == {"safe_metric": 42}


def test_scheduler_heartbeat_stale_alert(temp_alert_env):
    """Verify alert triggers when scheduler heartbeat is older than threshold."""
    manager = temp_alert_env["manager"]
    hb_path = temp_alert_env["hb_path"]
    sent = temp_alert_env["sent_alerts"]
    store = temp_alert_env["store"]

    # Write a stale heartbeat (600s ago)
    old_time = (datetime.now(timezone.utc) - timedelta(seconds=600)).isoformat()
    hb_path.write_text(json.dumps({
        "status": "running",
        "timestamp_utc": old_time,
    }), encoding="utf-8")

    ok, msg = manager.check_scheduler_heartbeat(max_age_seconds=300)

    assert not ok
    assert "stale" in msg
    assert len(sent) == 1
    assert "[CRITICAL]" in sent[0]["subject"]
    assert "Scheduler Heartbeat Stale" in sent[0]["subject"]

    # Check alert logged in store
    recent = store.get_recent_alerts(limit=10)
    assert len(recent) == 1
    assert recent[0]["alert_type"] == AlertType.SCHEDULER_HEARTBEAT_STALE.value
    assert recent[0]["status"] == "DELIVERED"
    assert recent[0]["severity"] == "CRITICAL"


def test_scheduler_heartbeat_recovery(temp_alert_env):
    """Verify recovery alert triggers after scheduler becomes fresh again."""
    manager = temp_alert_env["manager"]
    hb_path = temp_alert_env["hb_path"]
    sent = temp_alert_env["sent_alerts"]

    # 1. Stale state
    old_time = (datetime.now(timezone.utc) - timedelta(seconds=500)).isoformat()
    hb_path.write_text(json.dumps({
        "status": "running",
        "timestamp_utc": old_time,
    }), encoding="utf-8")

    manager.check_scheduler_heartbeat(max_age_seconds=300)
    assert len(sent) == 1

    # 2. Resumed fresh state
    fresh_time = datetime.now(timezone.utc).isoformat()
    hb_path.write_text(json.dumps({
        "status": "running",
        "timestamp_utc": fresh_time,
    }), encoding="utf-8")

    ok, msg = manager.check_scheduler_heartbeat(max_age_seconds=300)
    assert ok
    assert msg == "recovered"
    assert len(sent) == 2
    assert "[INFO]" in sent[1]["subject"]
    assert "Scheduler Heartbeat Recovered" in sent[1]["subject"]


def test_duplicate_alert_suppression(temp_alert_env):
    """Verify duplicate alerts within cooldown window are suppressed."""
    manager = temp_alert_env["manager"]
    hb_path = temp_alert_env["hb_path"]
    sent = temp_alert_env["sent_alerts"]
    store = temp_alert_env["store"]

    stale_time = (datetime.now(timezone.utc) - timedelta(seconds=600)).isoformat()
    hb_path.write_text(json.dumps({
        "status": "running",
        "timestamp_utc": stale_time,
    }), encoding="utf-8")

    # First check: delivered
    manager.check_scheduler_heartbeat(max_age_seconds=300)
    assert len(sent) == 1

    # Second check 10 seconds later: should be suppressed
    ok2, msg2 = manager.check_scheduler_heartbeat(max_age_seconds=300)
    assert not ok2
    assert "suppressed" in msg2
    assert len(sent) == 1  # No second email sent!

    # Check alert history logged suppression
    recent = store.get_recent_alerts(limit=5)
    assert len(recent) == 2
    assert recent[0]["status"] == "SUPPRESSED"
    assert recent[1]["status"] == "DELIVERED"


def test_repeated_failures_alert(temp_alert_env):
    """Verify alert triggers when failure threshold is reached."""
    manager = temp_alert_env["manager"]
    store = temp_alert_env["store"]
    sent = temp_alert_env["sent_alerts"]

    # Record 4 failures in scheduler_heartbeats
    now_iso = datetime.now(timezone.utc).isoformat()
    for _ in range(4):
        store.record_scheduler_heartbeat(
            started_at=now_iso,
            finished_at=now_iso,
            fetched=1,
            extracted=0,
            failed=1,
            status="error",
            error_message="ValidationException: mandatory field missing",
        )

    ok, count = manager.check_repeated_failures(threshold=3, window_minutes=60)
    assert not ok
    assert count >= 4
    assert len(sent) == 1
    assert "Repeated Pipeline Failures Detected" in sent[0]["subject"]
    assert "[WARNING]" in sent[0]["subject"]


def test_terminal_needs_attention_alert(temp_alert_env):
    """Verify alert triggers when item reaches pending_reviews with zero PII."""
    manager = temp_alert_env["manager"]
    store = temp_alert_env["store"]
    sent = temp_alert_env["sent_alerts"]

    # Add a pending review item
    now_iso = datetime.now(timezone.utc).isoformat()
    store.add_pending_review(
        graph_id="gid-test-12345",
        job_id="2026/09/01-999",
        client_jd_id="CJD-999",
        payload_json=json.dumps({"job_title": "Java Architect", "raw_body": "SECRET CANDIDATE INFO"}),
        review_fields="missing_mandatory_skills",
        identity="test:identity:hash",
    )

    total, alerted = manager.check_terminal_needs_attention(max_age_hours=24)
    assert total >= 1
    assert alerted >= 1
    assert len(sent) == 1
    assert "Pending Review" in sent[0]["subject"]
    # Verify no raw body / candidate information is exposed
    assert "SECRET CANDIDATE INFO" not in sent[0]["plain"]
    assert "SECRET CANDIDATE INFO" not in sent[0]["html"]
    assert "missing_mandatory_skills" in sent[0]["plain"]


def test_operational_health_summary(temp_alert_env):
    """Verify scheduled operational health summary aggregates metrics correctly."""
    manager = temp_alert_env["manager"]
    store = temp_alert_env["store"]
    sent = temp_alert_env["sent_alerts"]

    now_iso = datetime.now(timezone.utc).isoformat()

    # Record some messages and heartbeats
    store._conn.execute(
        "INSERT INTO seen_messages (graph_id, seen_at, source) VALUES (?, ?, ?)",
        ("gid-1", now_iso, "test"),
    )
    store.record_email_disposition(
        message_id="msg-1",
        disposition="extracted",
        requirements_count=1,
        graph_id="gid-1",
    )
    store.record_email_disposition(
        message_id="msg-2",
        disposition="duplicate",
        requirements_count=0,
        graph_id="gid-2",
    )
    store.record_scheduler_heartbeat(
        started_at=now_iso,
        finished_at=now_iso,
        fetched=2,
        extracted=1,
        failed=0,
        status="ok",
    )

    metrics = manager.generate_operational_health_summary(hours=24)
    assert metrics["messages_seen"] >= 1
    assert metrics["requirements_extracted"] >= 1
    assert metrics["duplicates_suppressed"] >= 1
    assert "processing_success_rate" in metrics

    assert len(sent) == 1
    assert "Operational Health Summary" in sent[0]["subject"]
    assert "[INFO]" in sent[0]["subject"]


def test_graph_api_send_mail_contract(temp_alert_env):
    """Verify Microsoft Graph sendMail contract matches specifications."""
    settings = dataclasses.replace(temp_alert_env["settings"], outbound_email_enabled=True)

    with patch("alerting._token_client_credentials", return_value="mock-token-abc"):
        with patch("alerting.requests.post") as mock_post:
            mock_post.return_value.status_code = 202
            mock_post.return_value.text = ""

            success, err = send_graph_alert_email(
                settings=settings,
                to_email="alerts@metaforgeit.com",
                subject="Test Subject",
                text_content="Plain body",
                html_content="<p>HTML body</p>",
            )

            assert success
            assert err is None

            mock_post.assert_called_once()
            call_url = mock_post.call_args[0][0]
            call_json = mock_post.call_args[1]["json"]
            call_headers = mock_post.call_args[1]["headers"]

            assert "sendMail" in call_url
            assert call_headers["Authorization"] == "Bearer mock-token-abc"
            assert call_json["message"]["subject"] == "Test Subject"
            assert call_json["message"]["toRecipients"][0]["emailAddress"]["address"] == "alerts@metaforgeit.com"
            assert call_json["message"]["body"]["contentType"] == "HTML"
            assert call_json["saveToSentItems"] is False


def test_outbound_email_blocked_by_default(temp_alert_env):
    """Verify that by default, send_graph_alert_email is blocked (extraction-only mode)."""
    settings = dataclasses.replace(temp_alert_env["settings"], outbound_email_enabled=False)

    success, err = send_graph_alert_email(
        settings=settings,
        to_email="alerts@external.com",
        subject="Test",
        text_content="Body",
    )
    assert not success
    assert "extraction-only policy" in err


def test_outbound_email_blocked_to_recruitment_mailbox(temp_alert_env):
    """Verify that sending to recruitment.application@metaforgeit.com is unconditionally blocked."""
    settings = dataclasses.replace(temp_alert_env["settings"], outbound_email_enabled=True)

    success, err = send_graph_alert_email(
        settings=settings,
        to_email="recruitment.application@metaforgeit.com",
        subject="Test Alert",
        text_content="Alert body",
    )
    assert not success
    assert "recruitment.application@metaforgeit.com is strictly prohibited" in err


