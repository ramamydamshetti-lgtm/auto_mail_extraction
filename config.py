"""
Central configuration from environment variables (.env supported via load_dotenv in main).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

MetaforgeMode = Literal["api", "sqlite"]


@dataclass(frozen=True)
class ClientIdentityConfig:
    """Configurable identity rules for client requirements (Rule 8)."""

    client_key: str
    display_name: str
    sender_domains: tuple[str, ...]
    table_req_id_headers: tuple[str, ...]
    table_status_headers: tuple[str, ...]
    status_words_hold: tuple[str, ...]
    status_words_open: tuple[str, ...]
    status_mapping: dict[str, str]
    use_req_id_identity: bool = True


DEFAULT_CLIENT_IDENTITY_CONFIGS: dict[str, ClientIdentityConfig] = {
    "accenture": ClientIdentityConfig(
        client_key="accenture",
        display_name="Accenture",
        sender_domains=("accenture.com", "iexcel.co.in"),
        table_req_id_headers=(
            "Request-ID",
            "Request ID",
            "Req ID",
            "Req-ID",
            "ReqID",
            "SO ID",
            "Demand ID",
        ),
        table_status_headers=("Priority", "Status", "Job Status", "Demand Status"),
        status_words_hold=("hold", "on hold", "on-hold", "paused", "deferred"),
        status_words_open=("p1", "p2", "p3", "open", "active", "urgent", "immediate"),
        status_mapping={
            "hold": "hold",
            "on hold": "hold",
            "on-hold": "hold",
            "p1": "open",
            "p2": "open",
            "p3": "open",
            "open": "open",
        },
        use_req_id_identity=True,
    ),
}

# Client ID patterns (C1) - user editable
DEFAULT_CLIENT_ID_PATTERNS: dict[str, str | None] = {
    "accenture": r"^\d{5,7}-\d{1,3}$",
    "kpmg": r"^RQ\d{4,8}$",
    "deloitte": r"^(DLTJP\d{6,10}|RQ\d{4,8})$",
    # pwc, ltts, itc, and others have no pattern yet (None):
    # they require an explicit label in email and 4-20 chars
    "pwc": None,
    "ltts": None,
    "itc": None,
}

EXPLICIT_ID_LABELS: tuple[str, ...] = (
    "req id",
    "req-id",
    "reqid",
    "request id",
    "request-id",
    "requestid",
    "requisition no",
    "requisition id",
    "requisition-id",
    "jd id",
    "jd-id",
    "jdid",
    "demand id",
    "demand-id",
    "demandid",
    "so#",
    "so id",
    "so-id",
    "job id",
    "job-id",
    "job posting id",
    "ref id",
    "ref-id",
    "requirement id",
)


def get_client_identity_config(client_key_or_domain: str) -> ClientIdentityConfig | None:
    """Lookup client identity config by key, domain, or email address."""
    key = (client_key_or_domain or "").strip().lower()
    if "@" in key:
        key = key.rsplit("@", 1)[-1]
    if key in DEFAULT_CLIENT_IDENTITY_CONFIGS:
        return DEFAULT_CLIENT_IDENTITY_CONFIGS[key]
    for cfg in DEFAULT_CLIENT_IDENTITY_CONFIGS.values():
        if key == cfg.client_key or any(key == d or key.endswith("." + d) for d in cfg.sender_domains):
            return cfg
    return None


CANONICAL_PLACEHOLDERS: frozenset[str] = frozenset({
    "not mentioned",
    "not-mentioned",
    "notmentioned",
    "n/a",
    "na",
    "nil",
    "none",
    "null",
    "undefined",
    "unknown",
    "tbd",
    "tba",
    "-",
    "--",
    "---",
    "as discussed",
    "to be shared",
    "to be decided",
    "to be discussed",
    "not specified",
    "not provided",
    "unassigned",
})


def is_placeholder(val: object) -> bool:
    if val is None:
        return True
    s = str(val).strip().lower()
    return s in CANONICAL_PLACEHOLDERS or s == ""


def is_strict_field_mapping() -> bool:
    v = os.environ.get("STRICT_FIELD_MAPPING", "true").strip().lower()
    return v in ("true", "1", "yes", "on")


def lpa_implies_inr() -> bool:
    v = os.environ.get("LPA_IMPLIES_INR", "false").strip().lower()
    return v in ("true", "1", "yes", "on")


def skills_from_requirement_sections() -> bool:
    """Returns True if technologies mentioned in requirement/qualification sections are included in skills."""
    v = os.environ.get("SKILLS_FROM_REQUIREMENT_SECTIONS", "true").strip().lower()
    return v in ("true", "1", "yes", "on")


FIELD_LABEL_SYNONYMS: dict[str, tuple[str, ...]] = {
    "location": (
        "work location",
        "base location",
        "job location",
        "locations",
        "location",
    ),
    "experience": (
        "years of experience",
        "total experience",
        "overall experience",
        "relevant experience",
        "overall exp",
        "total exp",
        "relevant exp",
        "years of exp",
        "experience",
        "exp",
    ),
    "budget": (
        "budget",
        "salary",
        "package",
        "rate",
        "bill rate",
        "bill rate per month",
        "rate / pm",
        "rate/pm",
        "tpc rate",
        "tpc rates",
        "monthly budget",
        "billing rate",
    ),
    "mandatory_skills": (
        "mandatory skills",
        "mandatory skill",
        "mandatory",
        "must have skills",
        "must have skill(s)",
        "must have",
        "must-have",
        "must to have skills",
        "must to have skill",
        "must to have",
        "must-to-have",
        "required skills",
        "primary skills",
        "primary skill",
        "primary skill(s)",
        "key skills",
        "key skill",
        "key skill(s)",
    ),
    "skills": (
        "technical skills",
        "skill set",
        "good to have",
        "good to have skills",
        "preferred skills",
        "preferred",
        "secondary skills",
        "additional skills",
        "skills and expertise",
        "skills & expertise",
        "professional & technical skills",
        "professional and technical skills",
        "skills",
        "skill",
    ),
    "notice_period": (
        "notice period",
        "notice",
        "np",
        "joining time",
        "joining period",
        "turnaround time",
    ),
    "work_mode": (
        "work mode",
        "working mode",
        "work model",
        "work location type",
        "mode of work",
        "rto/hybrid/wfh",
        "rto/hybrid",
        "rto",
    ),
}


@dataclass(frozen=True)
class Settings:
    """Application settings loaded from the environment."""

    azure_tenant_id: str
    azure_client_id: str
    azure_client_secret: str
    mailbox_upn: str
    openai_api_key: str
    openai_model: str
    metaforge_api_url: str
    metaforge_requirements_endpoint: str
    metaforge_mode: MetaforgeMode
    metaforge_sqlite_path: str
    metaforge_id_db: str
    processed_db: str
    log_level: str = "INFO"
    openai_min_confidence: float = 0.0
    internal_poc_default: str = "offshore demands"
    scheduler_mode: str = "inline"
    scheduler_poll_seconds: int = 120
    scheduler_error_backoff_seconds: int = 30
    scheduler_heartbeat_path: str = "scheduler_heartbeat.json"
    file_listener_enabled: bool = False
    file_listener_inbox_dir: str = "inbox"
    file_listener_archive_dir: str = "archive"
    ingest_start_datetime: str = "2026-09-01T00:00:00+05:30"
    fingerprint_window_days: int | None = None
    similarity_weights: dict[str, float] | None = None
    similarity_thresholds: dict[str, float] | None = None
    alert_recipient_email: str = "recruitment.application@metaforgeit.com"
    alert_cooldown_seconds: int = 900
    alert_heartbeat_max_age_seconds: int = 300
    alert_failure_threshold: int = 3
    accuracy_monitor_enabled: bool = True
    accuracy_monitor_cycle_interval: int = 30
    accuracy_monitor_sample_limit: int = 30

    @staticmethod
    def from_env() -> Settings:
        def _req(name: str) -> str:
            v = os.environ.get(name, "").strip()
            return v
        def _int(name: str, default: int) -> int:
            raw = _req(name)
            if not raw:
                return default
            try:
                return int(raw)
            except ValueError:
                return default
        def _bool(name: str, default: bool) -> bool:
            raw = _req(name).lower()
            if not raw:
                return default
            return raw in {"1", "true", "yes", "y", "on"}

        mode_raw = _req("METAFORGE_MODE").lower() or "api"
        if mode_raw not in ("api", "sqlite"):
            mode_raw = "api"

        min_conf_s = _req("OPENAI_MIN_CONFIDENCE") or "0"
        try:
            min_conf = float(min_conf_s)
        except ValueError:
            min_conf = 0.0

        # Load rules from pipeline_rules.json if present
        rules = {}
        try:
            rules_path = os.path.join(os.path.dirname(__file__), "config", "pipeline_rules.json")
            if os.path.exists(rules_path):
                import json
                with open(rules_path, "r", encoding="utf-8") as rf:
                    rules = json.load(rf)
        except Exception:
            rules = {}

        ingest_start = _req("INGEST_START_DATETIME") or rules.get("ingest_start_datetime") or "2026-09-01T00:00:00+05:30"
        fp_win_raw = _req("FINGERPRINT_WINDOW_DAYS")
        if fp_win_raw:
            try:
                fp_win: int | None = int(fp_win_raw)
            except ValueError:
                fp_win = None
        else:
            fp_win = rules.get("fingerprint_window_days", None)

        return Settings(
            azure_tenant_id=_req("AZURE_TENANT_ID"),
            azure_client_id=_req("AZURE_CLIENT_ID"),
            azure_client_secret=_req("AZURE_CLIENT_SECRET"),
            mailbox_upn=_req("MAILBOX_UPN") or "recruitment.application@metaforgeit.com",
            openai_api_key=_req("OPENAI_API_KEY") or _req("GEMINI_API_KEY"),
            openai_model=_req("OPENAI_MODEL") or _req("LLM_MODEL") or "gpt-4o-mini",
            metaforge_api_url=_req("METAFORGE_API_URL").rstrip("/"),
            metaforge_requirements_endpoint=_req("METAFORGE_REQUIREMENTS_ENDPOINT")
            or "api/internal/requirements/ingest-email",
            metaforge_mode=mode_raw,  # type: ignore[arg-type]
            metaforge_sqlite_path=_req("METAFORGE_SQLITE_PATH") or "data/metaforge_requirements.db",
            metaforge_id_db=_req("METAFORGE_ID_DB") or "data/metaforge_sequences.db",
            processed_db=_req("PROCESSED_DB") or "data/processed_messages.db",
            log_level=_req("LOG_LEVEL") or "INFO",
            openai_min_confidence=min_conf,
            internal_poc_default=_req("INTERNAL_POC_DEFAULT") or "offshore demands",
            scheduler_mode=_req("SCHEDULER_MODE").lower() or "inline",
            scheduler_poll_seconds=max(15, _int("SCHEDULER_POLL_SECONDS", 120)),
            scheduler_error_backoff_seconds=max(5, _int("SCHEDULER_ERROR_BACKOFF_SECONDS", 30)),
            scheduler_heartbeat_path=_req("SCHEDULER_HEARTBEAT_PATH")
            or "data/scheduler_heartbeat.json",
            file_listener_enabled=_bool("FILE_LISTENER_ENABLED", True),
            file_listener_inbox_dir=_req("FILE_LISTENER_INBOX_DIR") or "data/mail-drop/inbox",
            file_listener_archive_dir=_req("FILE_LISTENER_ARCHIVE_DIR") or "data/mail-drop/archive",
            ingest_start_datetime=ingest_start,
            fingerprint_window_days=fp_win,
            similarity_weights=rules.get("similarity_weights"),
            similarity_thresholds=rules.get("similarity_thresholds"),
            alert_recipient_email=_req("ALERT_RECIPIENT_EMAIL") or _req("MAILBOX_UPN") or "recruitment.application@metaforgeit.com",
            alert_cooldown_seconds=_int("ALERT_COOLDOWN_SECONDS", 900),
            alert_heartbeat_max_age_seconds=_int("ALERT_HEARTBEAT_MAX_AGE_SECONDS", 300),
            alert_failure_threshold=_int("ALERT_FAILURE_THRESHOLD", 3),
            accuracy_monitor_enabled=_bool("ACCURACY_MONITOR_ENABLED", True),
            accuracy_monitor_cycle_interval=max(1, _int("ACCURACY_MONITOR_CYCLE_INTERVAL", 30)),
            accuracy_monitor_sample_limit=max(5, _int("ACCURACY_MONITOR_SAMPLE_LIMIT", 30)),
        )


