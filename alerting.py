"""
Phase 4: Automated Alerting System for Production Recruitment Email Extraction.

Provides enterprise-grade operational monitoring, alert dispatching, and duplicate suppression:
1. Stale scheduler heartbeat / processing halt detection and recovery notification.
2. Repeated extraction, validation, and verification failure alerting.
3. Terminal needs_attention (pending_reviews) routing alerting.
4. Scheduled operational health summary reporting.
5. Email notification delivery via Microsoft Graph API.
6. Cooldown-based duplicate alert suppression to prevent notification storms.
7. Alert ledger recording (attempts, delivery outcomes, suppression logs).
8. Strict operational sanitization: zero candidate PII, raw email bodies, or tokens exposed.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests

from config import Settings
from processed_store import ProcessedStore
from outlook_graph import _token_client_credentials, _encode_user, GRAPH

_LOG = logging.getLogger(__name__)


class AlertSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    WARNING = "WARNING"
    INFO = "INFO"


class AlertType(str, Enum):
    SCHEDULER_HEARTBEAT_STALE = "SCHEDULER_HEARTBEAT_STALE"
    SCHEDULER_HEARTBEAT_RECOVERED = "SCHEDULER_HEARTBEAT_RECOVERED"
    REPEATED_EXTRACTION_FAILURES = "REPEATED_EXTRACTION_FAILURES"
    REPEATED_VALIDATION_FAILURES = "REPEATED_VALIDATION_FAILURES"
    REPEATED_VERIFICATION_FAILURES = "REPEATED_VERIFICATION_FAILURES"
    TERMINAL_NEEDS_ATTENTION = "TERMINAL_NEEDS_ATTENTION"
    OPERATIONAL_HEALTH_SUMMARY = "OPERATIONAL_HEALTH_SUMMARY"
    ACCURACY_DEGRADATION = "ACCURACY_DEGRADATION"


_SENSITIVE_KEY_PATTERNS = re.compile(
    r"(?i)(token|secret|password|key|auth|credential|body|raw_body|bodytext|bodyhtml|source_text|email_body|candidate|resume|phone|mobile|cv)"
)


def sanitize_alert_details(data: Any) -> Any:
    """Recursively strip candidate PII, credentials, tokens, and raw email contents."""
    if isinstance(data, dict):
        sanitized = {}
        for k, v in data.items():
            if _SENSITIVE_KEY_PATTERNS.search(str(k)):
                continue
            sanitized[k] = sanitize_alert_details(v)
        return sanitized
    elif isinstance(data, list):
        return [sanitize_alert_details(item) for item in data]
    elif isinstance(data, str):
        # Redact JWTs or bearer tokens
        if len(data) > 60 and ("ey" in data[:10] or "bearer" in data.lower()):
            return "[REDACTED_TOKEN]"
        return data
    return data


def parse_iso_utc(ts: str) -> datetime:
    """Parse an ISO 8601 timestamp string into a timezone-aware UTC datetime."""
    raw = (ts or "").strip()
    if not raw:
        return datetime.min.replace(tzinfo=timezone.utc)
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)


def send_graph_alert_email(
    settings: Settings,
    to_email: str,
    subject: str,
    text_content: str,
    html_content: str | None = None,
) -> tuple[bool, str | None]:
    """
    Send an operational alert email using the Microsoft Graph API.
    Reuses existing Azure OAuth2 client credentials from Settings.
    """
    if not (settings.azure_tenant_id and settings.azure_client_id and settings.azure_client_secret):
        return False, "Azure credentials missing in Settings"
    if not settings.mailbox_upn:
        return False, "Mailbox UPN missing in Settings"
    if not to_email:
        return False, "Target recipient email is empty"

    try:
        token = _token_client_credentials(
            settings.azure_tenant_id,
            settings.azure_client_id,
            settings.azure_client_secret,
        )
    except Exception as exc:
        return False, f"Graph token acquisition failed: {exc}"

    url = f"{GRAPH}/users/{_encode_user(settings.mailbox_upn)}/sendMail"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "message": {
            "subject": subject,
            "body": {
                "contentType": "HTML" if html_content else "Text",
                "content": html_content if html_content else text_content,
            },
            "toRecipients": [
                {
                    "emailAddress": {
                        "address": to_email.strip(),
                    }
                }
            ],
        },
        "saveToSentItems": False,
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        if resp.status_code in (200, 202):
            return True, None
        return False, f"Graph API returned status {resp.status_code}: {resp.text[:300]}"
    except Exception as exc:
        return False, f"HTTP request failed: {exc}"


def build_alert_email_body(
    alert_type: str,
    severity: str,
    summary: str,
    details: dict[str, Any],
) -> tuple[str, str]:
    """Generate both Plaintext and HTML formatted operational alert bodies."""
    color_map = {
        AlertSeverity.CRITICAL.value: "#d9534f",
        AlertSeverity.WARNING.value: "#f0ad4e",
        AlertSeverity.INFO.value: "#5bc0de",
    }
    badge_color = color_map.get(severity, "#777777")
    timestamp_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # Clean plaintext
    plain_lines = [
        f"[{severity}] {alert_type}",
        "=" * 60,
        f"Timestamp: {timestamp_str}",
        f"Summary:   {summary}",
        "-" * 60,
        "OPERATIONAL METRICS / DETAILS:",
    ]
    for k, v in details.items():
        plain_lines.append(f"  * {k}: {v}")
    plain_lines.append("-" * 60)
    plain_lines.append("Notice: This is an automated system alert from the Email Extraction Pipeline.")
    plain_text = "\n".join(plain_lines)

    # Clean, modern responsive HTML
    detail_rows = "".join(
        f"<tr><td style='padding:6px 12px;font-weight:600;color:#333;border-bottom:1px solid #eee;'>{k}</td>"
        f"<td style='padding:6px 12px;color:#555;border-bottom:1px solid #eee;'>{v}</td></tr>"
        for k, v in details.items()
    )
    html_text = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset='utf-8'>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f7f9fa; margin: 0; padding: 20px; }}
    .container {{ max-width: 650px; margin: 0 auto; background: #ffffff; border-radius: 8px; border: 1px solid #e1e4e8; overflow: hidden; }}
    .header {{ background-color: {badge_color}; color: #ffffff; padding: 18px 24px; }}
    .header h2 {{ margin: 0; font-size: 18px; font-weight: 600; }}
    .content {{ padding: 24px; color: #24292e; }}
    .summary {{ font-size: 15px; line-height: 1.5; margin-bottom: 20px; color: #24292e; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 13px; }}
    .footer {{ padding: 14px 24px; font-size: 11px; color: #6a737d; background: #fafbfc; border-top: 1px solid #e1e4e8; }}
  </style>
</head>
<body>
  <div class='container'>
    <div class='header'>
      <h2>[{severity}] {alert_type}</h2>
    </div>
    <div class='content'>
      <div class='summary'><strong>Summary:</strong> {summary}</div>
      <table cellpadding='0' cellspacing='0'>
        {detail_rows}
      </table>
    </div>
    <div class='footer'>
      System Alert &bull; Timestamp: {timestamp_str} &bull; Pipeline Operational Notification
    </div>
  </div>
</body>
</html>"""

    return plain_text, html_text


class AlertManager:
    """
    Central operational alerting manager with duplicate suppression,
    Graph API delivery, and alert history auditing.
    """

    def __init__(
        self,
        settings: Settings,
        store: ProcessedStore,
        custom_sender: Callable[[Settings, str, str, str, str | None], tuple[bool, str | None]] | None = None,
    ) -> None:
        self.settings = settings
        self.store = store
        self.custom_sender = custom_sender

    def send_alert(
        self,
        alert_type: AlertType | str,
        severity: AlertSeverity | str,
        subject: str,
        summary: str,
        details: dict[str, Any] | None = None,
        dedup_key: str | None = None,
        cooldown_seconds: int | None = None,
    ) -> tuple[bool, str]:
        """
        Evaluate cooldown suppression, log attempt, deliver alert, and record outcome.
        Returns (delivered: bool, message: str).
        """
        a_type = alert_type.value if isinstance(alert_type, AlertType) else str(alert_type)
        sev = severity.value if isinstance(severity, AlertSeverity) else str(severity)
        sanitized_details = sanitize_alert_details(details or {})
        recipient = self.settings.alert_recipient_email or self.settings.mailbox_upn

        cooldown = cooldown_seconds if cooldown_seconds is not None else self.settings.alert_cooldown_seconds
        d_key = dedup_key or a_type

        # Duplicate suppression check (recovery alerts bypass suppression)
        if a_type != AlertType.SCHEDULER_HEARTBEAT_RECOVERED.value and cooldown > 0:
            last_alert = self.store.get_last_alert_by_dedup_key(d_key)
            if last_alert and last_alert.get("status") in ("DELIVERED", "SUPPRESSED"):
                last_time = parse_iso_utc(last_alert.get("created_at", ""))
                age = (datetime.now(timezone.utc) - last_time).total_seconds()
                if age < cooldown:
                    # Suppress to prevent notification storms
                    self.store.record_alert(
                        alert_type=a_type,
                        severity=sev,
                        recipient=recipient,
                        subject=subject,
                        summary=summary,
                        status="SUPPRESSED",
                        error_message=f"Suppressed within {int(cooldown - age)}s cooldown window",
                        dedup_key=d_key,
                    )
                    _LOG.info(
                        "Alert '%s' suppressed (dedup_key=%s, age=%.1fs, cooldown=%ss)",
                        a_type,
                        d_key,
                        age,
                        cooldown,
                    )
                    return False, f"suppressed: within cooldown ({int(age)}s < {cooldown}s)"

        # Prepare messages
        plain_body, html_body = build_alert_email_body(
            alert_type=a_type,
            severity=sev,
            summary=summary,
            details=sanitized_details,
        )

        full_subject = f"[{sev}] {subject}"

        # Dispatch via configured sender or Graph API
        sender_fn = self.custom_sender or send_graph_alert_email
        success, err = sender_fn(
            self.settings,
            recipient,
            full_subject,
            plain_body,
            html_body,
        )

        outcome_status = "DELIVERED" if success else "FAILED"
        self.store.record_alert(
            alert_type=a_type,
            severity=sev,
            recipient=recipient,
            subject=full_subject,
            summary=summary,
            status=outcome_status,
            error_message=err,
            dedup_key=d_key,
        )

        if success:
            _LOG.info("Alert '%s' successfully delivered to %s", a_type, recipient)
            return True, "delivered"
        else:
            _LOG.error("Alert '%s' delivery failed to %s: %s", a_type, recipient, err)
            return False, f"delivery_failed: {err}"

    # -------------------------------------------------------------------------
    # Trigger 1: Scheduler Heartbeat Freshness & Recovery
    # -------------------------------------------------------------------------
    def check_scheduler_heartbeat(
        self,
        heartbeat_path: str | Path | None = None,
        max_age_seconds: int | None = None,
    ) -> tuple[bool, str]:
        """
        Check whether scheduler heartbeat is fresh.
        Alerts when heartbeat is stale or stopped.
        Alerts when scheduler recovers from a previous stale state.
        """
        path = Path(heartbeat_path or self.settings.scheduler_heartbeat_path)
        limit_seconds = max_age_seconds if max_age_seconds is not None else self.settings.alert_heartbeat_max_age_seconds
        dedup_key = "scheduler:heartbeat"

        last_alert = self.store.get_last_alert_by_dedup_key(dedup_key)
        was_previously_stale = (
            last_alert is not None
            and last_alert.get("alert_type") == AlertType.SCHEDULER_HEARTBEAT_STALE.value
            and last_alert.get("status") == "DELIVERED"
        )

        if not path.exists():
            # Missing heartbeat file
            summary = f"Heartbeat file missing at '{path}'"
            self.send_alert(
                alert_type=AlertType.SCHEDULER_HEARTBEAT_STALE,
                severity=AlertSeverity.CRITICAL,
                subject="Scheduler Heartbeat File Missing",
                summary=summary,
                details={"heartbeat_path": str(path), "status": "missing"},
                dedup_key=dedup_key,
            )
            return False, "heartbeat_missing"

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            summary = f"Heartbeat file at '{path}' unreadable: {exc}"
            self.send_alert(
                alert_type=AlertType.SCHEDULER_HEARTBEAT_STALE,
                severity=AlertSeverity.CRITICAL,
                subject="Scheduler Heartbeat Unreadable",
                summary=summary,
                details={"heartbeat_path": str(path), "error": str(exc)},
                dedup_key=dedup_key,
            )
            return False, "heartbeat_unreadable"

        status = str(data.get("status") or "").strip().lower()
        ts_str = str(data.get("timestamp_utc") or "").strip()
        hb_time = parse_iso_utc(ts_str)
        now = datetime.now(timezone.utc)
        age_seconds = int((now - hb_time).total_seconds())

        is_stale = age_seconds > limit_seconds or status in ("failed", "stopped", "critical")

        if is_stale:
            summary = (
                f"Scheduler heartbeat is stale or stopped. Age={age_seconds}s "
                f"(threshold={limit_seconds}s), reported status='{status or 'unknown'}'."
            )
            details = {
                "age_seconds": age_seconds,
                "threshold_seconds": limit_seconds,
                "reported_status": status or "unknown",
                "last_timestamp_utc": ts_str,
                "heartbeat_path": str(path),
            }
            delivered, msg = self.send_alert(
                alert_type=AlertType.SCHEDULER_HEARTBEAT_STALE,
                severity=AlertSeverity.CRITICAL,
                subject=f"Scheduler Heartbeat Stale (Age: {age_seconds}s)",
                summary=summary,
                details=details,
                dedup_key=dedup_key,
            )
            return False, f"stale:{msg}"

        # If healthy and was previously stale, fire recovery alert!
        if was_previously_stale:
            recovery_summary = f"Scheduler has resumed normal operations. Heartbeat age={age_seconds}s, status='{status}'."
            self.send_alert(
                alert_type=AlertType.SCHEDULER_HEARTBEAT_RECOVERED,
                severity=AlertSeverity.INFO,
                subject="Scheduler Heartbeat Recovered",
                summary=recovery_summary,
                details={
                    "age_seconds": age_seconds,
                    "reported_status": status,
                    "resumed_timestamp_utc": ts_str,
                },
                dedup_key=dedup_key,
                cooldown_seconds=0,
            )
            return True, "recovered"

        return True, "healthy"

    # -------------------------------------------------------------------------
    # Trigger 2: Repeated Extraction, Validation, or Verification Failures
    # -------------------------------------------------------------------------
    def check_repeated_failures(
        self,
        threshold: int | None = None,
        window_minutes: int = 30,
    ) -> tuple[bool, int]:
        """
        Check for repeated failures within a rolling time window.
        Alerts when the failure count reaches the threshold.
        """
        fail_thresh = threshold if threshold is not None else self.settings.alert_failure_threshold
        cutoff_dt = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
        cutoff_iso = cutoff_dt.isoformat()

        # Query recent failures from scheduler_heartbeats
        cur = self.store._conn.execute(
            """SELECT COUNT(*), COALESCE(SUM(failed), 0)
               FROM scheduler_heartbeats
               WHERE created_at >= ? AND (failed > 0 OR status != 'ok')""",
            (cutoff_iso,),
        )
        hb_row = cur.fetchone()
        hb_failed = hb_row[1] if hb_row else 0

        # Query recent failed email dispositions
        cur = self.store._conn.execute(
            """SELECT COUNT(*)
               FROM email_dispositions
               WHERE created_at >= ? AND disposition IN ('failed', 'error')""",
            (cutoff_iso,),
        )
        disp_row = cur.fetchone()
        disp_failed = disp_row[0] if disp_row else 0

        total_failures = max(hb_failed, disp_failed)

        if total_failures >= fail_thresh:
            summary = (
                f"Detected {total_failures} failures in the last {window_minutes} minutes "
                f"(configured threshold: {fail_thresh})."
            )
            details = {
                "failures_count": total_failures,
                "window_minutes": window_minutes,
                "threshold": fail_thresh,
                "heartbeat_failures": hb_failed,
                "disposition_failures": disp_failed,
            }
            self.send_alert(
                alert_type=AlertType.REPEATED_EXTRACTION_FAILURES,
                severity=AlertSeverity.WARNING,
                subject=f"Repeated Pipeline Failures Detected ({total_failures} in {window_minutes}m)",
                summary=summary,
                details=details,
                dedup_key=f"failures:window:{window_minutes}",
            )
            return False, total_failures

        return True, total_failures

    # -------------------------------------------------------------------------
    # Trigger 3: Terminal needs_attention (pending_reviews) Routing
    # -------------------------------------------------------------------------
    def check_terminal_needs_attention(
        self,
        max_age_hours: int = 24,
    ) -> tuple[int, int]:
        """
        Scan pending_reviews table and alert for requirements routed to human review.
        Guarantees that each unreviewed requirement is alerted once (or per cooldown).
        """
        cutoff_iso = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).isoformat()
        cur = self.store._conn.execute(
            """SELECT id, graph_id, job_id, client_jd_id, review_fields, status, created_at
               FROM pending_reviews
               WHERE created_at >= ? AND status = 'PENDING_REVIEW'
               ORDER BY id ASC""",
            (cutoff_iso,),
        )
        rows = cur.fetchall()
        total_pending = len(rows)
        alerted_count = 0

        for r in rows:
            p_id = r[0]
            gid = r[1]
            jid = r[2]
            cjd = r[3]
            review_fields = r[4]
            created_at = r[6]

            dedup_key = f"terminal:pending_review:{p_id}"
            last_alert = self.store.get_last_alert_by_dedup_key(dedup_key)
            if last_alert and last_alert.get("status") == "DELIVERED":
                continue

            summary = (
                f"Requirement {jid} routed to terminal PENDING_REVIEW queue. "
                f"Review required for fields: {review_fields}."
            )
            details = {
                "job_id": jid,
                "client_jd_id": cjd or "N/A",
                "graph_id": gid,
                "review_fields": review_fields,
                "routed_at": created_at,
            }

            delivered, _ = self.send_alert(
                alert_type=AlertType.TERMINAL_NEEDS_ATTENTION,
                severity=AlertSeverity.WARNING,
                subject=f"Action Required: Requirement {jid} routed to Pending Review",
                summary=summary,
                details=details,
                dedup_key=dedup_key,
                cooldown_seconds=86400,  # 24 hour cooldown per record
            )
            if delivered:
                alerted_count += 1

        return total_pending, alerted_count

    # -------------------------------------------------------------------------
    # Trigger 4: Scheduled Operational Health Summary
    # -------------------------------------------------------------------------
    def generate_operational_health_summary(
        self,
        hours: int = 24,
    ) -> dict[str, Any]:
        """
        Aggregate operational metrics for the period and send an operational health digest.
        """
        cutoff_iso = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

        # 1. Total processed / seen messages
        cur = self.store._conn.execute(
            "SELECT count(*) FROM seen_messages WHERE seen_at >= ?", (cutoff_iso,)
        )
        seen_count = cur.fetchone()[0]

        # 2. Email dispositions summary
        cur = self.store._conn.execute(
            """SELECT disposition, count(*)
               FROM email_dispositions
               WHERE created_at >= ?
               GROUP BY disposition""",
            (cutoff_iso,),
        )
        disp_counts = dict(cur.fetchall())
        extracted_disp = disp_counts.get("extracted", 0)
        filtered_disp = disp_counts.get("filtered", 0) + disp_counts.get("not_a_requirement", 0)
        duplicate_disp = disp_counts.get("duplicate", 0)
        failed_disp = disp_counts.get("failed", 0) + disp_counts.get("error", 0)

        # 3. Pending reviews
        cur = self.store._conn.execute(
            "SELECT count(*) FROM pending_reviews WHERE created_at >= ?", (cutoff_iso,)
        )
        pending_count = cur.fetchone()[0]

        # 4. Scheduler heartbeats stats
        cur = self.store._conn.execute(
            """SELECT count(*), COALESCE(SUM(fetched), 0), COALESCE(SUM(extracted), 0), COALESCE(SUM(failed), 0)
               FROM scheduler_heartbeats
               WHERE created_at >= ?""",
            (cutoff_iso,),
        )
        hb_stats = cur.fetchone()
        cycles_count = hb_stats[0] if hb_stats else 0
        total_fetched = hb_stats[1] if hb_stats else 0
        total_extracted = hb_stats[2] if hb_stats else 0
        total_failed = hb_stats[3] if hb_stats else 0

        # Calculate accuracy / reliability
        total_attempts = total_extracted + total_failed + failed_disp
        success_rate_pct = 100.0 if total_attempts == 0 else round((total_extracted / total_attempts) * 100.0, 1)

        summary_metrics = {
            "period_hours": hours,
            "messages_seen": seen_count,
            "requirements_extracted": total_extracted or extracted_disp,
            "duplicates_suppressed": duplicate_disp,
            "non_demands_filtered": filtered_disp,
            "pending_review_queue": pending_count,
            "processing_failures": total_failed or failed_disp,
            "scheduler_cycles": cycles_count,
            "processing_success_rate": f"{success_rate_pct}%",
        }

        digest_summary = (
            f"Operational Health Report ({hours}h): "
            f"{summary_metrics['requirements_extracted']} requirements extracted, "
            f"{summary_metrics['duplicates_suppressed']} duplicates filtered, "
            f"{summary_metrics['pending_review_queue']} pending reviews, "
            f"success rate: {summary_metrics['processing_success_rate']}."
        )

        dedup_key = f"health_summary:{datetime.now(timezone.utc).strftime('%Y-%m-%d')}"

        self.send_alert(
            alert_type=AlertType.OPERATIONAL_HEALTH_SUMMARY,
            severity=AlertSeverity.INFO,
            subject=f"Daily Operational Health Summary ({summary_metrics['requirements_extracted']} extracted, {summary_metrics['processing_success_rate']} success)",
            summary=digest_summary,
            details=summary_metrics,
            dedup_key=dedup_key,
            cooldown_seconds=3600 * 20,  # Once per day
        )

        return summary_metrics


def run_alerting_cli() -> int:
    """Command-line interface to evaluate alerts and print status."""
    parser = argparse.ArgumentParser(description="Run Automated Alerting Evaluation")
    parser.add_argument("--check-heartbeat", action="store_true", help="Check scheduler heartbeat")
    parser.add_argument("--check-failures", action="store_true", help="Check repeated pipeline failures")
    parser.add_argument("--check-pending", action="store_true", help="Check terminal pending reviews")
    parser.add_argument("--summary", action="store_true", help="Generate operational health summary")
    parser.add_argument("--all", action="store_true", help="Run all alert checks")
    args = parser.parse_args()

    settings = Settings.from_env()
    store = ProcessedStore(settings.processed_db)
    manager = AlertManager(settings, store)

    print("=" * 80)
    print("PHASE 4: AUTOMATED ALERTING SYSTEM EVALUATION")
    print("=" * 80)
    print(f"Target Alert Recipient: {settings.alert_recipient_email}")
    print(f"Heartbeat Threshold:    {settings.alert_heartbeat_max_age_seconds}s")
    print(f"Failure Threshold:      {settings.alert_failure_threshold}")
    print(f"Alert Cooldown Window:  {settings.alert_cooldown_seconds}s")
    print("-" * 80)

    if args.check_heartbeat or args.all:
        ok, msg = manager.check_scheduler_heartbeat()
        print(f"Scheduler Heartbeat Check: {'OK' if ok else 'ALERT TRIGGERED'} ({msg})")

    if args.check_failures or args.all:
        ok, count = manager.check_repeated_failures()
        print(f"Repeated Failures Check:   {'OK' if ok else 'ALERT TRIGGERED'} (Count: {count})")

    if args.check_pending or args.all:
        total, alerted = manager.check_terminal_needs_attention()
        print(f"Pending Reviews Check:     Total Pending: {total}, New Alerts Dispatched: {alerted}")

    if args.summary or args.all:
        metrics = manager.generate_operational_health_summary(hours=24)
        print("Operational Health Summary:")
        for k, v in metrics.items():
            print(f"  * {k}: {v}")

    print("=" * 80)
    return 0


if __name__ == "__main__":
    sys.exit(run_alerting_cli())
