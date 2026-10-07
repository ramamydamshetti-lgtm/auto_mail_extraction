"""
Unit and integration tests for Phase 5 Continuous Accuracy Monitoring.
Ensures baseline evaluation, source-grounded recovery calculations, hallucination checks,
cross-role isolation, alerting on degradation, and strict zero-production-write enforcement.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from accuracy_monitor import (
    ContinuousAccuracyMonitor,
    evaluate_production_records,
    run_accuracy_audit_cycle,
    AccuracyMetrics,
    ACCURACY_BASELINE_PATH,
)
from alerting import AlertManager, AlertType, AlertSeverity
from config import Settings
from processed_store import ProcessedStore


@pytest.fixture
def temp_monitor_env(tmp_path: Path):
    """Provides isolated test databases and mock settings."""
    proc_db = tmp_path / "test_processed.db"
    req_db = tmp_path / "test_metaforge.db"

    # Setup metaforge requirements DB
    with sqlite3.connect(req_db) as conn:
        conn.execute(
            """
            CREATE TABLE requirements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                raw_req_id TEXT,
                job_id TEXT,
                client_id TEXT,
                client_name TEXT,
                role_title TEXT,
                skills TEXT,
                experience TEXT,
                location TEXT,
                budget TEXT,
                work_mode TEXT,
                status TEXT,
                first_arrival_timestamp TEXT,
                raw_source_text TEXT
            )
            """
        )

    store = ProcessedStore(str(proc_db))

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
        metaforge_sqlite_path=str(req_db),
        metaforge_id_db=str(tmp_path / "seq.db"),
        processed_db=str(proc_db),
        scheduler_heartbeat_path=str(tmp_path / "heartbeat.json"),
        alert_recipient_email="ops-alerts@metaforgeit.com",
        accuracy_monitor_enabled=True,
        accuracy_monitor_sample_limit=10,
    )

    return {
        "settings": settings,
        "store": store,
        "req_db": str(req_db),
        "proc_db": str(proc_db),
    }


def test_baseline_and_thresholds_loaded():
    """Verify accuracy_baseline.json exists, contains valid schema and reasonable thresholds."""
    assert Path(ACCURACY_BASELINE_PATH).exists(), f"Baseline file missing: {ACCURACY_BASELINE_PATH}"
    with open(ACCURACY_BASELINE_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "metrics" in data
    assert "thresholds" in data
    thresholds = data["thresholds"]

    assert thresholds["min_overall_accuracy"] >= 0.90
    assert thresholds["min_source_present_recovery"] >= 0.90
    assert thresholds["min_job_title_accuracy"] >= 0.90
    assert thresholds["min_skills_recovery"] >= 0.90
    assert thresholds["max_hallucination_rate"] <= 0.05
    assert thresholds["max_cross_role_contamination_rate"] == 0.0


def test_source_present_recovery_vs_population_rate():
    """
    Verify that if a field (like experience or budget) is absent from the source body,
    omission by the extractor is NOT treated as an extraction failure in recovery rate,
    while population rate accurately reflects whether a value is present.
    """
    # Record 1: Source has Java and Bangalore, but NO experience or budget
    records = [
        {
            "id": 1,
            "job_id": "REQ-1",
            "client_name": "Accenture",
            "role_title": "Java Developer",
            "skills": "Java, Spring Boot",
            "experience": None,  # Correctly None because source mentions no experience
            "location": "Bengaluru",
            "budget": None,      # Correctly None because source mentions no budget
            "work_mode": "Hybrid",
            "raw_source_text": "We need Java Developer with Java, Spring Boot skills in Bangalore office. Work mode: Hybrid."
        }
    ]

    metrics = evaluate_production_records(records)
    assert metrics["sample_size"] == 1
    assert metrics["hallucination_count"] == 0
    assert metrics["cross_role_contamination_count"] == 0
    assert metrics["source_present_recovery"] == 1.0
    assert metrics["experience_recovery"] == 1.0  # Source absent -> no recovery penalty


def test_hallucination_detection():
    """Verify that candidate boilerplate or fabricated values are flagged as hallucinations."""
    records = [
        {
            "id": 1,
            "job_id": "REQ-1",
            "client_name": "Accenture",
            "role_title": "Java Developer",
            "skills": "Java, Python, C++, Rust, Kubernetes, GCP, Azure, AWS",  # invented skills
            "experience": "10-15 Years",  # invented experience
            "location": "London",         # invented location
            "budget": "50 LPA",           # invented budget
            "work_mode": "Remote",
            "raw_source_text": "Looking for Java Developer in Mumbai. Candidate must have 3-5 years exp."
        }
    ]

    metrics = evaluate_production_records(records)
    assert metrics["hallucination_count"] > 0
    assert metrics["hallucination_rate"] > 0.0
    assert metrics["overall_accuracy"] < 0.90


def test_cross_role_contamination_detection():
    """Verify cross-role contamination detection when candidate template or wrong titles leak."""
    records = [
        {
            "id": 1,
            "job_id": "REQ-10",
            "client_name": "LTTS",
            "role_title": "Role 1: DevOps & Role 2: QA Engineer",  # merged roles
            "skills": "Please find attached candidate resume with 5 years experience",  # template leakage
            "experience": "5 Years",
            "location": "Pune",
            "budget": None,
            "work_mode": None,
            "raw_source_text": "Role 1: DevOps Engineer in Pune. Role 2: QA Engineer in Pune."
        }
    ]

    metrics = evaluate_production_records(records)
    assert metrics["cross_role_contamination_count"] > 0
    assert metrics["cross_role_contamination_rate"] > 0.0


def test_alert_triggered_on_accuracy_degradation(temp_monitor_env):
    """Verify that when metrics drop below threshold, an ACCURACY_DEGRADATION alert is dispatched."""
    settings = temp_monitor_env["settings"]
    store = temp_monitor_env["store"]

    mock_alert_mgr = MagicMock(spec=AlertManager)
    mock_alert_mgr.send_alert.return_value = (True, "Delivered")

    monitor = ContinuousAccuracyMonitor(settings=settings, alert_manager=mock_alert_mgr)

    mock_metrics = AccuracyMetrics(
        sample_count=30,
        overall_accuracy=0.82,  # threshold is 0.95
        source_present_recovery=0.85,  # threshold is 0.95
        job_title_accuracy=0.90,
        skills_recovery=0.80,
        location_recovery=0.85,
        experience_recovery=0.80,
        budget_recovery=0.80,
        work_mode_recovery=0.80,
        identity_accuracy=0.90,
        hallucination_count=3,
        hallucination_rate=0.10,  # threshold is 0.02
        cross_role_contamination_count=1,  # threshold is 0.0
        cross_role_contamination_rate=0.033,
        missing_values_count=5,
        population_rates={"skills": 0.8},
    )

    with patch.object(monitor, "fetch_and_evaluate", return_value=mock_metrics):
        result = monitor.run_accuracy_check(limit=30)

    assert result["degraded"] is True
    assert len(result["breached_thresholds"]) > 0
    assert result["alert_triggered"] is True

    # Check alert dispatch details
    assert mock_alert_mgr.send_alert.called
    call_args = mock_alert_mgr.send_alert.call_args[1]
    assert call_args["alert_type"] == AlertType.ACCURACY_DEGRADATION
    assert call_args["severity"] == AlertSeverity.CRITICAL


def test_healthy_metrics_no_alert_triggered(temp_monitor_env):
    """Verify that when metrics are above threshold, no alert is dispatched."""
    settings = temp_monitor_env["settings"]
    mock_alert_mgr = MagicMock(spec=AlertManager)

    monitor = ContinuousAccuracyMonitor(settings=settings, alert_manager=mock_alert_mgr)

    mock_metrics = AccuracyMetrics(
        sample_count=30,
        overall_accuracy=1.0,
        source_present_recovery=1.0,
        job_title_accuracy=1.0,
        skills_recovery=1.0,
        location_recovery=1.0,
        experience_recovery=1.0,
        budget_recovery=1.0,
        work_mode_recovery=1.0,
        identity_accuracy=1.0,
        hallucination_count=0,
        hallucination_rate=0.0,
        cross_role_contamination_count=0,
        cross_role_contamination_rate=0.0,
        missing_values_count=0,
        population_rates={"skills": 1.0},
    )

    with patch.object(monitor, "fetch_and_evaluate", return_value=mock_metrics):
        result = monitor.run_accuracy_check(limit=30)

    assert result["degraded"] is False
    assert len(result["breached_thresholds"]) == 0
    assert result["alert_triggered"] is False
    assert not mock_alert_mgr.send_alert.called


def test_read_only_database_guarantee(temp_monitor_env):
    """Verify that monitoring performs strictly ZERO writes or mutations to the requirements table."""
    req_db_path = temp_monitor_env["req_db"]

    # Insert a sample record
    with sqlite3.connect(req_db_path) as conn:
        conn.execute(
            """
            INSERT INTO requirements (
                job_id, client_name, role_title, skills, experience, location, budget, work_mode, raw_source_text
            ) VALUES (
                'TEST-1', 'Accenture', 'Java Engineer', 'Java, Spring', '5+ Years', 'Hyderabad', '20 LPA', 'Hybrid',
                'Looking for Java Engineer with Java, Spring, 5+ Years experience in Hyderabad. Budget 20 LPA. Work mode: Hybrid'
            )
            """
        )

    # Capture initial count & state
    with sqlite3.connect(req_db_path) as conn:
        count_before = conn.execute("SELECT COUNT(*) FROM requirements").fetchone()[0]
        rows_before = conn.execute("SELECT * FROM requirements").fetchall()

    settings = temp_monitor_env["settings"]
    monitor = ContinuousAccuracyMonitor(settings=settings)
    metrics = monitor.fetch_and_evaluate(limit=10)

    assert metrics["sample_size"] == 1
    assert metrics["overall_accuracy"] >= 0.90

    # Verify zero mutations
    with sqlite3.connect(req_db_path) as conn:
        count_after = conn.execute("SELECT COUNT(*) FROM requirements").fetchone()[0]
        rows_after = conn.execute("SELECT * FROM requirements").fetchall()

    assert count_before == count_after == 1
    assert rows_before == rows_after
