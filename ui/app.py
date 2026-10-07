"""Flask Web Application for Recruiter Application Requirements Explorer."""

from __future__ import annotations

import atexit
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone, timedelta
from functools import wraps
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import (
    Flask,
    Response,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

_LOG = logging.getLogger("ui.app")

# Add parent directory to path if needed for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ui.db import (
    _parse_to_utc_dt,
    fetch_all_records,
    fetch_field_change_history,
    get_req_id_suggestions,
    get_requirement,
    normalize_id,
    update_status_in_db,
)

app = Flask(__name__)

# --- Auto Scheduler Background Supervision (Zero-Manual Operation) ---
_SCHEDULER_PROCESS: Optional[subprocess.Popen] = None
_SCHEDULER_SUPERVISOR_THREAD: Optional[threading.Thread] = None
_SCHEDULER_LOCK = threading.Lock()
_SCHEDULER_AUTO_START_ATTEMPTED = False


def find_running_scheduler_pid() -> Optional[int]:
    """Check if the canonical Auto Scheduler is already running (S2 lock or Windows process list)."""
    lock_file = Path("data/scheduler.lock")
    if lock_file.exists():
        try:
            content = lock_file.read_text(encoding="utf-8")
            m = re.search(r"pid=(\d+)", content)
            if m:
                lock_pid = int(m.group(1))
                res = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {lock_pid}", "/NH", "/FO", "CSV"],
                    capture_output=True, text=True, timeout=3
                )
                if str(lock_pid) in res.stdout:
                    return lock_pid
        except Exception:
            pass

    try:
        ps_cmd = 'Get-CimInstance Win32_Process -Filter "Name=\'python.exe\'" | Where-Object { $_.CommandLine -like "*main.py*scheduler*" } | Select-Object -ExpandProperty ProcessId'
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=5
        )
        for line in res.stdout.strip().splitlines():
            line_str = line.strip()
            if line_str.isdigit():
                return int(line_str)
    except Exception:
        pass
    return None


def start_scheduler_subprocess() -> int:
    """Launch exactly one canonical Auto Scheduler in a background non-blocking process."""
    global _SCHEDULER_PROCESS
    project_root = Path(__file__).resolve().parent.parent
    logs_dir = project_root / "data" / "service-logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    out_file = open(logs_dir / "scheduler.out.log", "a", encoding="utf-8")
    err_file = open(logs_dir / "scheduler.err.log", "a", encoding="utf-8")

    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NO_WINDOW

    proc = subprocess.Popen(
        [sys.executable, "-u", "main.py", "scheduler"],
        cwd=str(project_root),
        stdout=out_file,
        stderr=err_file,
        creationflags=flags,
    )
    _SCHEDULER_PROCESS = proc
    _LOG.info("Auto Scheduler automatically started in background with PID %s", proc.pid)
    return proc.pid


def ensure_scheduler_running() -> int:
    """Ensure exactly one background Auto Scheduler instance is running. Idempotent."""
    with _SCHEDULER_LOCK:
        pid = find_running_scheduler_pid()
        if pid:
            _LOG.info("Auto Scheduler is already running (PID %s). Reusing existing instance.", pid)
            return pid
        return start_scheduler_subprocess()


def _scheduler_watchdog():
    """Background watchdog thread ensuring the Auto Scheduler remains running while app is up."""
    while True:
        time.sleep(30)
        try:
            pid = find_running_scheduler_pid()
            if not pid:
                _LOG.warning("Auto Scheduler process stopped unexpectedly. Automatically restarting...")
                ensure_scheduler_running()
        except Exception as exc:
            _LOG.warning("Scheduler watchdog exception: %s", exc)


def start_scheduler_supervisor():
    """Start supervisor watchdog thread if not already active."""
    global _SCHEDULER_SUPERVISOR_THREAD
    with _SCHEDULER_LOCK:
        if _SCHEDULER_SUPERVISOR_THREAD is None or not _SCHEDULER_SUPERVISOR_THREAD.is_alive():
            _SCHEDULER_SUPERVISOR_THREAD = threading.Thread(target=_scheduler_watchdog, daemon=True)
            _SCHEDULER_SUPERVISOR_THREAD.start()


def _cleanup_scheduler():
    """Cleanly terminate background scheduler subprocess on application shutdown."""
    global _SCHEDULER_PROCESS
    if _SCHEDULER_PROCESS and _SCHEDULER_PROCESS.poll() is None:
        try:
            _LOG.info("Terminating background scheduler PID %s on application exit...", _SCHEDULER_PROCESS.pid)
            _SCHEDULER_PROCESS.terminate()
            _SCHEDULER_PROCESS.wait(timeout=5)
        except Exception:
            try:
                _SCHEDULER_PROCESS.kill()
            except Exception:
                pass


atexit.register(_cleanup_scheduler)


@app.before_request
def _auto_start_scheduler_hook():
    """Hook to guarantee Auto Scheduler is started upon first HTTP request if not already started."""
    global _SCHEDULER_AUTO_START_ATTEMPTED
    if not _SCHEDULER_AUTO_START_ATTEMPTED:
        _SCHEDULER_AUTO_START_ATTEMPTED = True
        try:
            ensure_scheduler_running()
            start_scheduler_supervisor()
        except Exception as exc:
            _LOG.warning("Failed to auto-start scheduler in before_request hook: %s", exc)

# Load configuration from file or environment
CONFIG_FILE = os.environ.get("UI_CONFIG_PATH", str(Path(__file__).parent / "config.json"))


def load_config() -> Dict[str, Any]:
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception as err:
        cfg = {}
    
    # Allow environment overrides
    cfg["host"] = os.environ.get("UI_HOST", cfg.get("host", "127.0.0.1"))
    cfg["port"] = int(os.environ.get("UI_PORT", cfg.get("port", 5000)))
    if os.environ.get("UI_DB_PATH"):
        cfg["db_paths"] = [os.environ["UI_DB_PATH"]]
    return cfg


UI_CONFIG = load_config()


def check_auth(username: str, password: str) -> bool:
    expected_password = os.environ.get("UI_PASSWORD") or os.environ.get("FLASK_PASSWORD")
    if not expected_password:
        return True
    expected_user = os.environ.get("UI_USERNAME", "admin")
    return username == expected_user and password == expected_password


def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        expected_password = os.environ.get("UI_PASSWORD") or os.environ.get("FLASK_PASSWORD")
        if not expected_password:
            return f(*args, **kwargs)
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return Response(
                "Authentication required",
                401,
                {"WWW-Authenticate": 'Basic realm="Login Required"'},
            )
        return f(*args, **kwargs)

    return decorated


@app.route("/api/requirement/<path:req_id>/status", methods=["POST"])
@requires_auth
def api_update_status(req_id: str):
    data = request.get_json() or {}
    new_status = str(data.get("status") or "").strip().lower()
    if new_status not in {"open", "hold", "reopen", "closed"}:
        return jsonify({"error": "invalid status, allowed: open, hold, reopen, closed"}), 400

    changed_by = str(data.get("changed_by") or "USER").strip()
    success = update_status_in_db(UI_CONFIG, req_id, new_status, changed_by=changed_by)
    if not success:
        return jsonify({"error": "requirement not found or update failed"}), 404
    return jsonify({"success": True, "req_id": req_id, "new_status": new_status})


def get_field_val(record: dict, key: str) -> Any:
    payload = record.get("payload", {})
    if key in record:
        return record[key]
    if key in payload:
        return payload[key]
    return ""


def format_received_time(dt_val: Any) -> str:
    """Format Outlook receivedDateTime timestamp into MM/DD/YYYY hh:mm AM/PM local time (IST)."""
    if not dt_val:
        return "—"
    dt_str = str(dt_val).strip()
    if not dt_str or dt_str.lower() in ("none", "null", "n/a", "not specified"):
        return "—"

    from datetime import datetime, timezone, timedelta
    ist_tz = timezone(timedelta(hours=5, minutes=30))

    try:
        # Date only (YYYY-MM-DD)
        if len(dt_str) == 10 and dt_str.count('-') == 2:
            dt = datetime.strptime(dt_str, '%Y-%m-%d')
            return dt.strftime('%m/%d/%Y')

        # Handle ISO-8601 with Z or explicit offset
        if dt_str.endswith('Z'):
            dt = datetime.fromisoformat(dt_str[:-1] + '+00:00')
            dt_local = dt.astimezone(ist_tz)
        elif '+' in dt_str[10:] or ('-' in dt_str[10:] and len(dt_str) > 16):
            dt = datetime.fromisoformat(dt_str)
            dt_local = dt.astimezone(ist_tz)
        else:
            dt = datetime.fromisoformat(dt_str)
            if dt.tzinfo is None:
                dt_local = dt.replace(tzinfo=ist_tz)
            else:
                dt_local = dt.astimezone(ist_tz)

        return dt_local.strftime('%m/%d/%Y %I:%M %p')
    except Exception:
        return dt_str


@app.template_filter('format_received_time')
def _jinja_filter_format_received_time(s):
    return format_received_time(s)


def format_utc_instant(dt_val: Any) -> str:
    """Format arrival timestamp as full UTC ISO string with seconds for tooltip (T2)."""
    if not dt_val:
        return "—"
    dt_utc = _parse_to_utc_dt(dt_val)
    if dt_utc == datetime.min.replace(tzinfo=timezone.utc):
        return str(dt_val)
    return dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")


@app.template_filter('format_utc_instant')
def _jinja_filter_format_utc_instant(s):
    return format_utc_instant(s)


@app.route("/health")
def health_endpoint():
    """
    S5: /health endpoint reports the age of the last heartbeat;
    warn if it is older than 5 minutes (300 seconds).
    """
    db_path = UI_CONFIG.get("processed_db", "data/processed_messages.db")
    heartbeat = None
    age_seconds = None
    status = "ok"

    try:
        from processed_store import ProcessedStore
        with ProcessedStore(db_path) as store:
            heartbeat = store.get_last_scheduler_heartbeat()
    except Exception:
        pass

    if not heartbeat:
        hb_path = Path("data/scheduler_heartbeat.json")
        if hb_path.exists():
            try:
                with open(hb_path, "r", encoding="utf-8") as f:
                    heartbeat = json.load(f)
            except Exception:
                pass

    if heartbeat:
        ts_str = heartbeat.get("timestamp_utc") or heartbeat.get("started_at") or heartbeat.get("created_at")
        if ts_str:
            try:
                hb_dt = _parse_to_utc_dt(ts_str)
                now_dt = datetime.now(timezone.utc)
                age_seconds = (now_dt - hb_dt).total_seconds()
                if age_seconds > 300:
                    status = "warning"
            except Exception:
                pass
    else:
        status = "degraded"

    scheduler_pid = find_running_scheduler_pid()
    scheduler_is_running = scheduler_pid is not None

    code = 200 if status in ("ok", "warning") else 503
    return jsonify({
        "status": status,
        "age_seconds": round(age_seconds, 1) if age_seconds is not None else None,
        "is_older_than_5_minutes": (age_seconds > 300) if age_seconds is not None else True,
        "heartbeat": heartbeat,
        "scheduler_running": scheduler_is_running,
        "scheduler_pid": scheduler_pid,
    }), code


def format_open_since(dt_val: Any) -> str:
    """Format arrival date as 'MMM DD, YYYY (N days)' using local IST timezone (UTC+5:30)."""
    if not dt_val:
        return "N/A"
    dt_str = str(dt_val).strip()
    if not dt_str or dt_str.lower() in ("none", "null", "n/a"):
        return "N/A"
    from datetime import datetime, timezone, timedelta
    ist_tz = timezone(timedelta(hours=5, minutes=30))
    now = datetime.now(ist_tz)
    try:
        if dt_str.endswith('Z'):
            dt = datetime.fromisoformat(dt_str[:-1] + '+00:00').astimezone(ist_tz)
        elif '+' in dt_str[10:] or ('-' in dt_str[10:] and len(dt_str) > 16):
            dt = datetime.fromisoformat(dt_str).astimezone(ist_tz)
        elif len(dt_str) == 10:
            dt = datetime.strptime(dt_str, '%Y-%m-%d').replace(tzinfo=ist_tz)
        else:
            dt = datetime.fromisoformat(dt_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=ist_tz)

        days = max(0, (now.date() - dt.date()).days)
        return f"{dt.strftime('%b %d, %Y')} ({days} days)"
    except Exception:
        return dt_str


@app.template_filter('format_open_since')
def _jinja_filter_format_open_since(s):
    return format_open_since(s)


@app.context_processor
def inject_globals():
    return {
        "config": UI_CONFIG,
        "badge_colors": UI_CONFIG.get("status_badge_colors", {}),
        "label_overrides": UI_CONFIG.get("field_label_overrides", {}),
        "format_received_time": format_received_time,
        "format_open_since": format_open_since,
    }


@app.errorhandler(404)
def not_found_error(error):
    return render_template("error.html", code=404, message="Page or Requirement Not Found"), 404


@app.errorhandler(500)
def internal_error(error):
    return render_template("error.html", code=500, message="An internal server error occurred"), 500


@app.route("/filtered-mails")
def filtered_mails():
    """V6: Filtered mails view — shows emails that were blocked at the intake gate."""
    db_path = UI_CONFIG.get("processed_db", "data/processed_messages.db")
    rows = []
    error_msg = None
    try:
        import sqlite3 as _sqlite3
        conn = _sqlite3.connect(db_path)
        conn.row_factory = _sqlite3.Row
        raw = conn.execute(
            """SELECT graph_id, reason, sender, subject, received_at, created_at
               FROM filtered_log ORDER BY created_at DESC LIMIT 200"""
        ).fetchall()
        rows = [dict(r) for r in raw]
        conn.close()
    except Exception as e:
        error_msg = str(e)
    return render_template("filtered_mails.html", rows=rows, error=error_msg)



def parse_sort_tuple(item: dict) -> tuple:
    """
    Requirement order should always be in descending order (newest requirement on top):
    1. REQ date segment (e.g. '2026/10/06' or '2026/10/01')
    2. REQ sequence number (integer, so 100 > 99, 9 > 8)
    3. first_arrival_at (parsed as a timezone-aware datetime)
    4. row id / req_id.
    """
    p = item.get("payload", {})
    req_id = str(item.get("req_id") or item.get("raw_req_id") or p.get("job_id") or "").strip()
    m = re.match(r"^(\d{4})[/-](\d{2})[/-](\d{2})[-_](\d+)$", req_id)
    if m:
        req_date = f"{m.group(1)}/{m.group(2)}/{m.group(3)}"
        req_seq = int(m.group(4))
    else:
        req_date = ""
        req_seq = 0

    fa = str(item.get("first_arrival_at") or p.get("first_arrival_at") or item.get("arr_iso") or p.get("receivedDateTime") or item.get("created_at") or "").strip()
    dt_obj = _parse_to_utc_dt(fa)
    row_id = str(item.get("raw_req_id") or req_id)
    return (req_date, req_seq, dt_obj, row_id)


def filter_and_sort_records(records: List[dict], q: str, client: str, status: str, sort: str, order: str) -> List[dict]:
    res = []
    q_lower = q.lower().strip() if q else ""
    client_lower = client.lower().strip() if client else ""
    status_lower = status.lower().strip() if status else ""

    for rec in records:
        payload = rec.get("payload", {})
        rec_client = str(payload.get("requirement_from", "")).lower()
        rec_status = str(payload.get("job_status", "")).lower()

        if client_lower and client_lower != rec_client:
            continue
        if status_lower and status_lower != rec_status:
            continue
        if q_lower:
            blob = json.dumps(rec).lower()
            if q_lower not in blob:
                continue
        res.append(rec)

    sort_clean = (sort or "").strip().lower()
    reverse = (order.lower() != "asc")  # default order is descending

    if not sort_clean or sort_clean in ("req_id", "requirement", "default", "job_id"):
        res.sort(key=parse_sort_tuple, reverse=reverse)
    elif sort_clean in ("first_arrival_at", "arr_iso", "receiveddatetime", "created_at", "sort_ts"):
        def arrival_sort_key(item):
            p = item.get("payload", {})
            fa = str(item.get("first_arrival_at") or p.get("first_arrival_at") or item.get("arr_iso") or p.get("receivedDateTime") or item.get("created_at") or "").strip()
            return (_parse_to_utc_dt(fa), parse_sort_tuple(item))
        res.sort(key=arrival_sort_key, reverse=reverse)
    else:
        def general_sort_key(item):
            val = item.get(sort) or item.get("payload", {}).get(sort)
            val_str = str(val).lower() if val is not None else ""
            return (val_str, parse_sort_tuple(item))
        res.sort(key=general_sort_key, reverse=reverse)


    return res


@app.route("/")
@requires_auth
def index():
    include_archived = request.args.get("include_archived", "0") in ("1", "true", "True")
    try:
        all_records = fetch_all_records(UI_CONFIG, include_archived=include_archived)
    except Exception as err:
        return render_template("error.html", code=500, message=f"Database Access Error: {str(err)}"), 500

    # S6: Set "is_new" marker if first_arrival_at falls within the current IST day
    ist_tz = timezone(timedelta(hours=5, minutes=30))
    today_ist = datetime.now(timezone.utc).astimezone(ist_tz).strftime("%Y-%m-%d")
    for rec in all_records:
        fa = rec.get("first_arrival_at") or rec.get("arr_iso") or rec.get("payload", {}).get("first_arrival_at")
        if fa:
            try:
                dt_ist = _parse_to_utc_dt(fa).astimezone(ist_tz)
                rec["is_new"] = (dt_ist.strftime("%Y-%m-%d") == today_ist)
            except Exception:
                rec["is_new"] = False
        else:
            rec["is_new"] = False

    q = request.args.get("q", "").strip()
    client = request.args.get("client", "").strip()
    status = request.args.get("status", "").strip()
    sort = request.args.get("sort", UI_CONFIG.get("default_sort", "req_id")).strip()
    order = request.args.get("order", UI_CONFIG.get("default_sort_order", "desc")).strip()

    filtered = filter_and_sort_records(all_records, q, client, status, sort, order)

    # Collect distinct clients and statuses for dropdown filters
    distinct_clients = sorted(list({str(r.get("payload", {}).get("requirement_from", "")).strip() for r in all_records if r.get("payload", {}).get("requirement_from")}))
    distinct_statuses = sorted(list({str(r.get("payload", {}).get("job_status", "")).strip() for r in all_records if r.get("payload", {}).get("job_status")}))

    # Pagination logic
    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1

    page_size = UI_CONFIG.get("default_page_size", 20)
    total_count = len(filtered)
    total_pages = max(1, (total_count + page_size - 1) // page_size)
    page = min(page, total_pages)

    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    items = filtered[start_idx:end_idx]

    unassigned_count = sum(1 for r in all_records if not r.get("payload", {}).get("owner") or r.get("payload", {}).get("owner") == "Unassigned")
    assigned_count = len(all_records) - unassigned_count
    open_count = sum(1 for r in all_records if str(r.get("payload", {}).get("job_status", "")).lower() in ("open", "active"))
    hold_count = sum(1 for r in all_records if "hold" in str(r.get("payload", {}).get("job_status", "")).lower())
    closed_count = sum(1 for r in all_records if str(r.get("payload", {}).get("job_status", "")).lower() in ("closed", "cancelled"))
    submissions_count = sum(int(r.get("payload", {}).get("submissions_count") or 0) for r in all_records)

    kpis = {
        "total": len(all_records),
        "submissions": submissions_count,
        "unassigned": unassigned_count,
        "assigned": assigned_count,
        "open": open_count,
        "hold": hold_count,
        "closed": closed_count,
    }

    return render_template(
        "list.html",
        items=items,
        total_count=total_count,
        page=page,
        total_pages=total_pages,
        q=q,
        client=client,
        status=status,
        sort=sort,
        order=order,
        distinct_clients=distinct_clients,
        distinct_statuses=distinct_statuses,
        columns=UI_CONFIG.get("columns", []),
        kpis=kpis,
    )


@app.route("/requirement/<path:req_id>")
@requires_auth
def requirement_detail(req_id: str):
    rec = get_requirement(UI_CONFIG, req_id)
    if not rec:
        return render_template("error.html", code=404, message=f"Requirement '{req_id}' Not Found"), 404
    canonical_id = rec.get("req_id")
    former_id = rec.get("former_job_id") or rec.get("payload", {}).get("former_job_id")
    if canonical_id and req_id != canonical_id and former_id and req_id == former_id:
        return redirect(url_for("requirement_detail", req_id=canonical_id), code=302)
    return render_template("detail.html", item=rec)


@app.route("/api/requirements")
@requires_auth
def api_requirements():
    include_archived = request.args.get("include_archived", "0") in ("1", "true", "True")
    all_records = fetch_all_records(UI_CONFIG, include_archived=include_archived)

    # S6: Set "is_new" marker if first_arrival_at falls within the current IST day
    ist_tz = timezone(timedelta(hours=5, minutes=30))
    today_ist = datetime.now(timezone.utc).astimezone(ist_tz).strftime("%Y-%m-%d")
    for rec in all_records:
        fa = rec.get("first_arrival_at") or rec.get("arr_iso") or rec.get("payload", {}).get("first_arrival_at")
        if fa:
            try:
                dt_ist = _parse_to_utc_dt(fa).astimezone(ist_tz)
                rec["is_new"] = (dt_ist.strftime("%Y-%m-%d") == today_ist)
            except Exception:
                rec["is_new"] = False
        else:
            rec["is_new"] = False

    q = request.args.get("q", "").strip()
    client = request.args.get("client", "").strip()
    status = request.args.get("status", "").strip()
    sort = request.args.get("sort", UI_CONFIG.get("default_sort", "req_id")).strip()
    order = request.args.get("order", UI_CONFIG.get("default_sort_order", "desc")).strip()

    filtered = filter_and_sort_records(all_records, q, client, status, sort, order)

    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1

    page_size = min(int(request.args.get("page_size", UI_CONFIG.get("default_page_size", 20))), UI_CONFIG.get("max_page_size", 100))
    total_count = len(filtered)
    total_pages = max(1, (total_count + page_size - 1) // page_size)
    page = min(page, total_pages)

    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    items = filtered[start_idx:end_idx]

    return jsonify({
        "total_count": total_count,
        "page": page,
        "total_pages": total_pages,
        "page_size": page_size,
        "data": items,
    })


@app.route("/api/requirement/<path:req_id>/field-history")
@requires_auth
def api_field_history(req_id: str):
    """Return field-level change history for a requirement (Rule 3 para 6)."""
    history = fetch_field_change_history(UI_CONFIG, req_id)
    return jsonify({"req_id": req_id, "field_change_history": history})


@app.route("/api/requirement/<path:req_id>")
@requires_auth
def api_requirement_detail(req_id: str):
    rec = get_requirement(UI_CONFIG, req_id)
    if not rec:
        return jsonify({"error": "not found", "req_id": req_id}), 404
    return jsonify(rec)


@app.route("/api/req-ids")
@requires_auth
def api_req_ids():
    prefix = request.args.get("prefix", "").strip()
    limit = min(int(request.args.get("limit", UI_CONFIG.get("max_suggestion_limit", 15))), UI_CONFIG.get("max_suggestion_limit", 15))
    suggestions = get_req_id_suggestions(UI_CONFIG, prefix, limit)
    return jsonify({"suggestions": suggestions})


if __name__ == "__main__":
    _LOG.info("Application starting: ensuring Auto Scheduler is running in background...")
    ensure_scheduler_running()
    start_scheduler_supervisor()
    host = UI_CONFIG.get("host", "127.0.0.1")
    port = UI_CONFIG.get("port", 5000)
    app.run(host=host, port=port, debug=False, threaded=True)
