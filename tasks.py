"""
Celery worker tasks for asynchronous email pipeline processing.
"""

from __future__ import annotations

import logging
import os

from celery import Celery
from dotenv import load_dotenv
from kombu import Queue

from body_normalizer import normalize_body, scrub_pii
from client_detector import detect_client
from config import Settings
from main import process_single_message
from metaforge_api import IdAllocator
from outlook_graph import acquire_token_from_env, fetch_message_by_id
from processed_store import ProcessedStore
from email_filter import apply_email_filter, is_sender_allowlisted
from requirement_classifier import classify_email, heuristic_obvious_client_requirement
from utils import bind_log_context, clear_log_context, setup_logging

_LOG = logging.getLogger(__name__)

BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", BROKER_URL)
CLASSIFIER_RATE_LIMIT = os.environ.get("CELERY_CLASSIFIER_RATE_LIMIT", "120/m")
HEAVY_RATE_LIMIT = os.environ.get("CELERY_HEAVY_RATE_LIMIT", "50/m")
SYNC_RATE_LIMIT = os.environ.get("CELERY_SYNC_RATE_LIMIT", "120/m")

app = Celery("email_pipeline", broker=BROKER_URL, backend=RESULT_BACKEND)
app.conf.task_acks_late = True
app.conf.task_reject_on_worker_lost = True
app.conf.worker_prefetch_multiplier = 1
app.conf.task_default_queue = "email_pipeline"
app.conf.task_queues = (
    Queue("high_priority"),
    Queue("heavy_ai"),
    Queue("io_bound"),
)
app.conf.task_routes = {
    "tasks.classify_email_task": {"queue": "high_priority"},
    "tasks.process_email_task": {"queue": "heavy_ai"},
    "tasks.sync_metaforge_payload_task": {"queue": "io_bound"},
}


@app.task(
    bind=True,
    max_retries=5,
    default_retry_delay=30,
    rate_limit=CLASSIFIER_RATE_LIMIT,
)
def classify_email_task(self, message_id: str, mailbox: str | None = None) -> dict[str, object]:
    """
    High-priority stage: cheap gatekeeping before heavy extraction.
    """
    load_dotenv()
    settings = Settings.from_env()
    setup_logging(settings.log_level)
    chosen_mailbox = mailbox or settings.mailbox_upn
    msg_id = (message_id or "").strip()
    bind_log_context(message_id=msg_id, task="classify_email_task")
    if not msg_id:
        clear_log_context()
        return {"message_id": message_id, "status": "invalid_message_id"}

    try:
        token = acquire_token_from_env()
        raw = fetch_message_by_id(token, chosen_mailbox, msg_id)
    except Exception as exc:
        delay_s = min(300, 2 ** self.request.retries * 15)
        _LOG.warning("Classifier fetch failed for %s: %s (retry in %ss)", msg_id, exc, delay_s)
        clear_log_context()
        raise self.retry(exc=exc, countdown=delay_s)

    body_obj = raw.get("body") or {}
    content = str(body_obj.get("content") or "")
    body_for_ai = scrub_pii(normalize_body(content, content))
    subject = str(raw.get("subject") or "")
    from_obj = raw.get("from") or {}
    from_email = (
        ((from_obj.get("emailAddress") or {}).get("address") or "")
        if isinstance(from_obj, dict)
        else ""
    )
    has_att = bool(raw.get("hasAttachments"))
    inet_id = str(raw.get("internetMessageId") or "").strip() or None

    with ProcessedStore(settings.processed_db) as store:
        if store.pipeline_should_skip(msg_id, inet_id):
            clear_log_context()
            return {"message_id": msg_id, "status": "already_finalized"}
        if not is_sender_allowlisted(from_email):
            store.pipeline_mark_skipped(msg_id, "sender_not_allowlisted")
            store.log_filtered(graph_id=msg_id, subject=subject, from_email=from_email, reason="sender_not_allowlisted", stage="allowlist")
            clear_log_context()
            return {"message_id": msg_id, "status": "sender_not_allowlisted"}
        if detect_client(subject, body_for_ai, from_email) is None:
            store.pipeline_mark_skipped(msg_id, "unknown_client")
            clear_log_context()
            return {"message_id": msg_id, "status": "skipped_unknown_client"}
        filt = apply_email_filter(
            subject=subject,
            body=body_for_ai,
            has_attachments=has_att,
            from_email=from_email,
        )
        if not filt.allowed:
            store.pipeline_mark_skipped(msg_id, f"filter:{filt.reason}")
            stage = (
                "junk_detector"
                if filt.reason in {"promotional_email", "job_seeker_self_application", "popup_notification"}
                else "email_filter"
            )
            store.log_filtered(graph_id=msg_id, subject=subject, from_email=from_email, reason=filt.reason, stage=stage)
            clear_log_context()
            return {"message_id": msg_id, "status": f"filter:{filt.reason}"}
        if not has_att:
            if not heuristic_obvious_client_requirement(subject, body_for_ai):
                cls_res = classify_email(
                    body_for_ai, subject=subject, settings=settings, from_email=from_email
                )
                if cls_res.label == "NOT_A_REQUIREMENT":
                    store.pipeline_mark_skipped(msg_id, "ai_classifier_no")
                    store.log_filtered(graph_id=msg_id, subject=subject, from_email=from_email, reason="ai_classifier_no", stage="classifier")
                    clear_log_context()
                    return {"message_id": msg_id, "status": "classifier_no"}
        process_email_task.delay(msg_id, chosen_mailbox, True)
        store.pipeline_mark_queued(msg_id, "queued_heavy_ai_after_classifier")
    _LOG.info("ai_classifier_success queued_heavy_ai message_id=%s", msg_id)
    clear_log_context()
    return {"message_id": msg_id, "status": "queued_heavy_ai"}


@app.task(
    bind=True,
    max_retries=5,
    default_retry_delay=30,
    rate_limit=HEAVY_RATE_LIMIT,
)
def process_email_task(
    self,
    message_id: str,
    mailbox: str | None = None,
    skip_classifier: bool = True,
) -> dict[str, object]:
    """
    Consumer task: fetch one Graph email, run AI pipeline, and sync to MetaForge.
    """
    load_dotenv()
    settings = Settings.from_env()
    setup_logging(settings.log_level)
    chosen_mailbox = mailbox or settings.mailbox_upn
    msg_id = (message_id or "").strip()
    bind_log_context(message_id=msg_id, task="process_email_task")
    if not msg_id:
        clear_log_context()
        return {"message_id": message_id, "status": "invalid_message_id"}

    try:
        token = acquire_token_from_env()
        raw = fetch_message_by_id(token, chosen_mailbox, msg_id)
    except Exception as exc:
        delay_s = min(300, 2 ** self.request.retries * 30)
        _LOG.warning("Graph fetch failed for %s: %s (retry in %ss)", msg_id, exc, delay_s)
        clear_log_context()
        raise self.retry(exc=exc, countdown=delay_s)

    id_db = (
        settings.metaforge_sqlite_path
        if settings.metaforge_mode == "sqlite"
        else settings.metaforge_id_db
    )
    allocator = IdAllocator(id_db)
    try:
        with ProcessedStore(settings.processed_db) as store:
            synced = process_single_message(
                raw,
                token=token,
                mailbox=chosen_mailbox,
                settings=settings,
                allocator=allocator,
                store=store,
                skip_classifier=skip_classifier,
                sync_via_task=True,
            )
        clear_log_context()
        return {"message_id": msg_id, "status": "done", "synced_rows": synced}
    except Exception as exc:
        delay_s = min(300, 2 ** self.request.retries * 30)
        _LOG.warning("Task failed for %s: %s (retry in %ss)", msg_id, exc, delay_s)
        clear_log_context()
        raise self.retry(exc=exc, countdown=delay_s)
    finally:
        allocator.close()


@app.task(
    bind=True,
    max_retries=5,
    default_retry_delay=30,
    rate_limit=SYNC_RATE_LIMIT,
)
def sync_metaforge_payload_task(self, payload: dict[str, object]) -> dict[str, object]:
    """
    IO-bound stage: dedicated queue for MetaForge API/storage sync.
    """
    load_dotenv()
    settings = Settings.from_env()
    setup_logging(settings.log_level)
    from metaforge_api import send_to_metaforge

    graph_id = (
        ((payload.get("_provenance") or {}).get("graph_message_id") or "")
        if isinstance(payload, dict)
        else ""
    )
    job_id = str((payload or {}).get("job_id") or "")
    bind_log_context(message_id=graph_id, task="sync_metaforge_payload_task", job_id=job_id)
    try:
        send_to_metaforge(payload, settings)
        if graph_id:
            with ProcessedStore(settings.processed_db) as store:
                cur = store.pipeline_get_state(graph_id)
                if cur != "pending_review":
                    store.pipeline_mark_synced(graph_id, f"sync_task_job_id={job_id}")
        clear_log_context()
        return {"job_id": job_id, "status": "synced"}
    except Exception as exc:
        delay_s = min(300, 2 ** self.request.retries * 30)
        _LOG.warning("Sync failed for job %s: %s (retry in %ss)", job_id, exc, delay_s)
        clear_log_context()
        raise self.retry(exc=exc, countdown=delay_s)
