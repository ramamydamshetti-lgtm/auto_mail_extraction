"""
Unit tests for 2-way requirement classifier.
"""

from unittest.mock import MagicMock, patch
import pytest

from config import Settings
from requirement_classifier import (
    ClassificationResult,
    classify_email,
)


def mock_settings():
    return Settings(
        azure_tenant_id="test",
        azure_client_id="test",
        azure_client_secret="test",
        mailbox_upn="test@example.com",
        openai_api_key="sk-fake",
        openai_model="gpt-4o-mini",
        metaforge_api_url="https://api.test",
        metaforge_requirements_endpoint="api/ingest",
        metaforge_mode="sqlite",
        metaforge_sqlite_path="data/test.db",
        metaforge_id_db="data/seq.db",
        processed_db="data/proc.db",
        log_level="INFO",
        openai_min_confidence=0.0,
        internal_poc_default="offshore",
        scheduler_poll_seconds=120,
        scheduler_error_backoff_seconds=30,
        scheduler_heartbeat_path="data/hb.json",
        file_listener_enabled=False,
        file_listener_inbox_dir="inbox",
        file_listener_archive_dir="archive",
    )


def test_heuristic_obvious_requirement_returns_high_confidence_requirement():
    s = mock_settings()
    body = (
        "Requirement for Senior Python Developer.\n"
        "Bill Rate: $65/hr\n"
        "Open Positions: 3\n"
        "Mandatory Skills: Python, Django, AWS\n"
        "Kindly share profiles ASAP."
    )
    res = classify_email(body, subject="Urgent Requirement: Senior Python Dev", settings=s)
    assert isinstance(res, ClassificationResult)
    assert res.label == "REQUIREMENT"
    assert res.confidence >= 0.90


def test_pre_classify_block_returns_not_a_requirement():
    s = mock_settings()
    res = classify_email(
        "Please find our weekly submission report attached.",
        subject="Weekly Tracker Report",
        settings=s,
        from_email="no-reply@company.com",
    )
    assert res.label == "NOT_A_REQUIREMENT"
    assert res.confidence == 1.0


def test_missing_api_key_raises_runtime_error(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    s = mock_settings()
    s = Settings(**{**s.__dict__, "openai_api_key": ""})
    with pytest.raises(RuntimeError, match="Classifier misconfigured: missing API key"):
        classify_email("Some body", subject="Subject", settings=s)


@patch("time.sleep", return_value=None)
@patch("openai.OpenAI")
def test_llm_failure_retries_and_defaults_to_requirement(mock_openai_cls, mock_sleep):
    s = mock_settings()
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client
    mock_client.chat.completions.create.side_effect = Exception("API rate limit exceeded")

    res = classify_email("Random text", subject="Ambiguous email", settings=s)

    # 3 total attempts (1 initial + 2 retries)
    assert mock_client.chat.completions.create.call_count == 3
    assert res.label == "REQUIREMENT"
    assert res.confidence == 0.0


@patch("openai.OpenAI")
def test_requirement_label_passes_through(mock_openai_cls):
    s = mock_settings()
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content='{"label": "REQUIREMENT", "confidence": 0.95}'))
    ]
    mock_client.chat.completions.create.return_value = mock_response

    body = "New job requisition for DevOps Engineer."
    res = classify_email(body, subject="New requisition", settings=s)

    assert res.label == "REQUIREMENT"
    assert res.confidence == 0.95
