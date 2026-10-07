"""
MetaForge integration: REST POST or local SQLite persistence.
Also owns daily sequence generation for job_id / client_jd_id.

IDENTITY RULES (enforced here, universal - not client-specific):
  Rule 1: Every requirement gets ONE unique ID, assigned once.
           Prefer the real client-provided req_id (client_jd_id) if present.
           Fall back to internal job_id (YYYY/MM/DD-NNN) only when no real ID exists.
  Rule 2: Same client_jd_id = same requirement, NEVER create a second row.
  Rule 3: On a repeat email for the same req_id, update ONLY the fields that
           actually changed; never overwrite existing data with blank/null.
           Record every field-level change with from/to/when.
  Rule 4: updated_at refreshed on every field change; default UI sort is
           most-recently-updated first.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin

import requests

from requirement_identity import normalize_client_key

if TYPE_CHECKING:
    from config import Settings

_LOG = logging.getLogger(__name__)

# Fields we track for field-level diff (Rule 3 / Rule 4)
_TRACKED_FIELDS = [
    "job_title", "location", "overall_experience", "notice_period",
    "number_of_positions", "yearly_budget", "monthly_budget",
    "mandatory_skills", "skills", "job_status", "priority",
    "experience_level", "employment_type", "client_poc",
    "requirement_from", "demand_received_date",
]


def _requirements_url(base: str) -> str:
    b = (base or "").strip().rstrip("/")
    if not b:
        return ""
    if b.lower().endswith("requirements") or b.lower().endswith("ingest-email"):
        return b
    return urljoin(b + "/", "api/internal/requirements/ingest-email")


class IdAllocator:
    """Thread-safe enough for single-process CLI: SQLite-backed daily sequences."""

    def __init__(self, db_path: str) -> None:
        self._path = db_path
        parent = Path(db_path).resolve().parent
        parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._path)
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS mf_sequences (
                name TEXT PRIMARY KEY,
                value INTEGER NOT NULL DEFAULT 0
            )"""
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def _next(self, name: str) -> int:
        self._conn.execute(
            "INSERT INTO mf_sequences(name, value) VALUES (?, 0) ON CONFLICT(name) DO NOTHING",
            (name,),
        )
        cur = self._conn.execute("SELECT value FROM mf_sequences WHERE name = ?", (name,))
        row = cur.fetchone()
        n = int(row[0]) + 1 if row else 1
        self._conn.execute("UPDATE mf_sequences SET value = ? WHERE name = ?", (n, name))
        self._conn.commit()
        return n

    def next_job_id(self, day: date | None = None) -> str:
        d_str = (day or date.today()).strftime("%Y/%m/%d")
        seq = self._next(f"job:{d_str}")
        return f"{d_str}-{seq:03d}"

    def next_client_jd_id(self, client_slug: str) -> str | None:
        """Returns None if no client-provided ID exists in source text (never fabricate placeholders)."""
        return None


def send_to_metaforge(payload: dict[str, Any], settings: Settings) -> str:
    """
    Dispatch payload according to METAFORGE_MODE (api | sqlite).
    Returns the assigned job_id.
    """
    mode = settings.metaforge_mode
    if mode == "sqlite":
        assigned_id = _sqlite_upsert(payload, settings.metaforge_sqlite_path)
        _LOG.info("Stored requirement %s in SQLite", assigned_id)
        return assigned_id

    endpoint = getattr(settings, "metaforge_requirements_endpoint", "").strip().strip("/")
    if endpoint:
        url = urljoin(settings.metaforge_api_url.rstrip("/") + "/", endpoint)
    else:
        url = _requirements_url(settings.metaforge_api_url)
    if not url:
        # Fail-safe behavior: when API mode is configured but URL is missing,
        # keep pipeline productive by persisting to local SQLite.
        assigned_id = _sqlite_upsert(payload, settings.metaforge_sqlite_path)
        _LOG.warning(
            "METAFORGE_API_URL missing in api mode; stored requirement %s in SQLite fallback",
            assigned_id,
        )
        return assigned_id

    headers = {"Content-Type": "application/json"}
    import os

    key = os.environ.get("METAFORGE_API_KEY", "").strip()
    if key:
        headers["Authorization"] = f"Bearer {key}"
        headers["x-internal-api-key"] = key

    body = {k: v for k, v in payload.items() if not str(k).startswith("_")}
    # Let the API assign REQ-YYYY-MM-DD-001, 002 on the live DB (ignore local allocator ids).
    body.pop("job_id", None)
    body.pop("client_jd_id", None)
    body["pipeline_extracted"] = True
    r = requests.post(url, json=body, headers=headers, timeout=120)
    if r.status_code >= 400:
        _LOG.error("MetaForge API error %s: %s", r.status_code, r.text[:500])
        r.raise_for_status()
    try:
        resp_json = r.json()
    except Exception:
        resp_json = {}
    data = resp_json.get("data") if isinstance(resp_json, dict) else {}
    if isinstance(data, dict) and data.get("ignored"):
        reason = str(data.get("reason") or "ignored by API")
        _LOG.error("MetaForge API ignored requirement %s: %s", payload.get("job_id"), reason)
        raise RuntimeError(f"MetaForge API ignored payload: {reason}")
    if isinstance(data, dict) and data.get("deduped") and not data.get("requirementId"):
        reason = str(data.get("reason") or "duplicate")
        _LOG.warning("MetaForge API deduped requirement %s: %s", payload.get("job_id"), reason)
    _LOG.info("Posted requirement %s to MetaForge API", payload.get("job_id"))


def post_recruitment_payload(
    payload: dict[str, Any],
    settings: Settings,
    *,
    endpoint_path: str = "requirements",
) -> None:
    """
    POST mapped payload to recruitment app endpoint.
    Uses METAFORGE_API_URL as base URL.
    """
    base = (settings.metaforge_api_url or "").rstrip("/")
    if not base:
        raise RuntimeError("METAFORGE_API_URL is required for recruitment API posting")
    endpoint = endpoint_path.strip().lstrip("/")
    url = f"{base}/{endpoint}"
    headers = {"Content-Type": "application/json"}
    key = os.environ.get("METAFORGE_API_KEY", "").strip()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    body = {k: v for k, v in payload.items() if not str(k).startswith("_")}
    r = requests.post(url, json=body, headers=headers, timeout=120)
    if r.status_code >= 400:
        _LOG.error("Recruitment API error %s: %s", r.status_code, r.text[:500])
        r.raise_for_status()
    _LOG.info("Posted requirement %s to recruitment endpoint %s", payload.get("job_id"), endpoint)


# ---------------------------------------------------------------------------
# SQLite persistence - enforces Rules 1-4
# ---------------------------------------------------------------------------

import re
from datetime import date, datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))


def get_ist_req_date(first_arrival_at: str | None) -> str:
    """
    Format IST date as YYYY/MM/DD for first_arrival_at.
    Never uses processing date if first_arrival_at is provided.
    """
    if not first_arrival_at:
        return datetime.now(IST).strftime("%Y/%m/%d")
    s = str(first_arrival_at).strip()
    dt = None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        pass
    if dt is None:
        try:
            from dateutil.parser import parse as parse_date
            dt = parse_date(s)
        except Exception:
            pass
    if dt is not None:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        ist_dt = dt.astimezone(IST)
        return ist_dt.strftime("%Y/%m/%d")
    m = re.match(r"^(\d{4})[-/](\d{2})[-/](\d{2})", s)
    if m:
        return f"{m.group(1)}/{m.group(2)}/{m.group(3)}"
    return datetime.now(IST).strftime("%Y/%m/%d")


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Create/migrate metaforge_requirements table. ALTER TABLE ADD COLUMN preserves existing data."""
    conn.execute(
        """CREATE TABLE IF NOT EXISTS metaforge_requirements (
            job_id           TEXT PRIMARY KEY,
            payload_json     TEXT NOT NULL,
            created_at       TEXT NOT NULL,
            client_jd_id     TEXT,
            updated_at       TEXT,
            field_change_history TEXT
        )"""
    )
    # Migrate older tables that lack the new columns (safe - preserves all existing data)
    existing_cols = {r[1] for r in conn.execute("PRAGMA table_info(metaforge_requirements)").fetchall()}
    for col, ddl in [
        ("client_jd_id",         "TEXT"),
        ("updated_at",           "TEXT"),
        ("field_change_history", "TEXT"),
        ("identity",             "TEXT"),
        ("req_date",             "TEXT"),
        ("seq",                  "INTEGER"),
        ("former_job_id",        "TEXT"),
        ("former_client_id",     "TEXT"),
    ]:
        if col not in existing_cols:
            conn.execute(f"ALTER TABLE metaforge_requirements ADD COLUMN {col} {ddl}")
    # Index for fast client_jd_id lookups (Rule 2)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_mf_req_client_jd_id ON metaforge_requirements(client_jd_id)"
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_mf_req_identity ON metaforge_requirements(identity) WHERE identity IS NOT NULL"
    )
    # Unique index on (req_date, seq) for sequence numbering (R2)
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_mf_req_date_seq ON metaforge_requirements(req_date, seq) WHERE req_date IS NOT NULL AND seq IS NOT NULL"
    )
    conn.commit()


def _field_diff(old_payload: dict, new_payload: dict) -> dict:
    """
    Return a dict of field: {old_val, new_val} for every tracked field that genuinely changed.
    Fields where new_payload has None/blank are EXCLUDED - blank never counts as a change (Rule 3 para 4).
    """
    changes: dict = {}
    for field in _TRACKED_FIELDS:
        old_val = old_payload.get(field)
        new_val = new_payload.get(field)
        # Only update if new value is genuinely provided (not None/blank)
        if new_val is None or new_val == "" or new_val == []:
            continue
        old_norm = str(old_val).strip().lower() if old_val is not None else ""
        new_norm = str(new_val).strip().lower()
        if old_norm != new_norm:
            changes[field] = {"old": old_val, "new": new_val}
    return changes


IMMUTABLE_FIELDS = {
    "job_id",
    "client_jd_id",
    "created_at",
    "demand_received_date",
    "receivedDateTime",
    "email_received_iso",
    "first_arrival_at",
    "_provenance",
}


def _merge_payload(existing: dict, new_payload: dict) -> dict:
    """
    Selective merge implementing Rule 3 & Rule A5:
    - Immutable fields from existing record are strictly preserved.
    - Non-blank new values overwrite stored values for mutable fields.
    - Blank/null new values leave stored values untouched.
    """
    merged = dict(existing)
    for key, new_val in new_payload.items():
        if key in IMMUTABLE_FIELDS and existing.get(key) is not None:
            # Preserve immutable field from existing record
            continue
        if key.startswith("_"):
            # Always propagate provenance / internal metadata
            if key == "_provenance" and isinstance(new_val, dict) and isinstance(merged.get("_provenance"), dict):
                merged["_provenance"] = {**new_val, **merged["_provenance"]}
            else:
                merged[key] = new_val
            continue
        if new_val is None or new_val == "" or new_val == []:
            # Rule 3 para 4: do NOT overwrite existing data with blank
            continue
        merged[key] = new_val
    return merged


def _sqlite_upsert(payload: dict[str, Any], db_path: str) -> str:
    """
    Identity-aware upsert into metaforge_requirements with atomic sequence allocation (R1-R4).

    Rule 1: Sequence number is allocated inside the same transaction as insert (MAX(seq) + 1).
    Rule 2: Unique index on (req_date, seq) with retry on conflict.
    Rule 3: On error or rollback, no number is burned.
    """
    import time
    parent = os.path.dirname(os.path.abspath(db_path))
    if parent:
        os.makedirs(parent, exist_ok=True)

    conn = sqlite3.connect(db_path, timeout=30.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    _ensure_schema(conn)

    now = datetime.now(timezone.utc).isoformat()
    cjd_raw = payload.get("client_jd_id")
    cjd = None
    if cjd_raw:
        s_cjd = str(cjd_raw).strip()
        from client_identity_validator import _is_numeric_range
        if _is_numeric_range(s_cjd) or re.match(r"^(LTTS|ACC|REQ)[-_](?:19\d\d|20\d\d)[-_/]", s_cjd, re.I):
            payload["former_client_id"] = s_cjd
            payload["client_jd_id"] = None
            cjd = None
        else:
            cjd = s_cjd or None

    job_id = str(payload.get("job_id") or "").strip()
    ident = payload.get("identity")
    if not ident:
        try:
            from requirement_identity import compute_requirement_identity
            ident = compute_requirement_identity(
                client=payload.get("requirement_from"),
                client_jd_id=cjd,
                job_title=payload.get("job_title"),
                location=payload.get("location"),
                experience=payload.get("overall_experience") or payload.get("experience_level"),
                mandatory_skills=payload.get("mandatory_skills"),
            )
            payload["identity"] = ident
        except Exception:
            ident = None

    max_retries = 15
    for attempt in range(max_retries):
        try:
            conn.execute("BEGIN IMMEDIATE")

            existing_row = None
            # Permanent identity check first
            if ident:
                row = conn.execute(
                    "SELECT job_id, payload_json, field_change_history, identity "
                    "FROM metaforge_requirements WHERE identity = ? LIMIT 1",
                    (ident,),
                ).fetchone()
                if row:
                    existing_row = row
                elif cjd and cjd.lower() not in ("none", "null", "not_found", ""):
                    norm_client = normalize_client_key(payload.get("requirement_from") or payload.get("client_key"))
                    legacy_rows = conn.execute(
                        "SELECT job_id, payload_json, field_change_history, identity "
                        "FROM metaforge_requirements WHERE client_jd_id = ? AND (identity IS NULL OR identity = '')",
                        (cjd,),
                    ).fetchall()
                    for l_row in legacy_rows:
                        try:
                            lp = json.loads(l_row["payload_json"])
                            if normalize_client_key(lp.get("requirement_from") or lp.get("client_key")) == norm_client:
                                existing_row = l_row
                                break
                        except Exception:
                            pass
            elif cjd and cjd.lower() not in ("none", "null", "not_found", ""):
                norm_client = normalize_client_key(payload.get("requirement_from") or payload.get("client_key"))
                candidate_rows = conn.execute(
                    "SELECT job_id, payload_json, field_change_history, identity "
                    "FROM metaforge_requirements WHERE client_jd_id = ?",
                    (cjd,),
                ).fetchall()
                for c_row in candidate_rows:
                    try:
                        cp = json.loads(c_row["payload_json"])
                        if normalize_client_key(cp.get("requirement_from") or cp.get("client_key")) == norm_client:
                            existing_row = c_row
                            break
                    except Exception:
                        pass

            # Fall back to job_id lookup if present and not a template
            if existing_row is None and job_id:
                row = conn.execute(
                    "SELECT job_id, payload_json, field_change_history, identity "
                    "FROM metaforge_requirements WHERE job_id = ? LIMIT 1",
                    (job_id,),
                ).fetchone()
                if row:
                    existing_row = row

            # Fall back to Outlook conversationId / thread lookup
            if existing_row is None:
                prov = payload.get("_provenance") if isinstance(payload.get("_provenance"), dict) else {}
                cid = str(prov.get("conversation_id") or payload.get("conversationId") or payload.get("conversation_id") or "").strip()
                if cid:
                    cur_all = conn.execute(
                        "SELECT job_id, payload_json, field_change_history, identity "
                        "FROM metaforge_requirements ORDER BY rowid ASC"
                    )
                    c_rows = []
                    for r_chk in cur_all.fetchall():
                        try:
                            p_chk = json.loads(r_chk["payload_json"])
                            pr = p_chk.get("_provenance") if isinstance(p_chk.get("_provenance"), dict) else {}
                            if (
                                pr.get("conversation_id") == cid
                                or p_chk.get("conversationId") == cid
                                or p_chk.get("conversation_id") == cid
                            ):
                                c_rows.append((r_chk, p_chk))
                        except Exception:
                            continue
                    if c_rows:
                        matched = None
                        incoming_cjd = str(cjd or payload.get("client_jd_id") or "").strip().lower()
                        incoming_title = str(payload.get("job_title") or "").strip().lower()
                        for r_chk, p_chk in c_rows:
                            cand_cjd = str(p_chk.get("client_jd_id") or "").strip().lower()
                            cand_title = str(p_chk.get("job_title") or "").strip().lower()
                            if incoming_cjd and cand_cjd and incoming_cjd == cand_cjd:
                                matched = r_chk
                                break
                            if incoming_title and cand_title and incoming_title == cand_title:
                                matched = r_chk
                                break
                        if not matched and len(c_rows) == 1:
                            matched = c_rows[0][0]
                        if matched:
                            existing_row = matched

            # Fall back to whole-requirement profile duplicate matching (W1-W5, Rule 2)
            if existing_row is None:
                try:
                    from requirement_comparator import build_requirement_profile, compare_requirements
                    incoming_prof = payload.get("_profile") or build_requirement_profile(payload)
                    cur_all = conn.execute(
                        "SELECT job_id, client_jd_id, payload_json, field_change_history, identity "
                        "FROM metaforge_requirements ORDER BY rowid ASC"
                    )
                    for r_chk in cur_all.fetchall():
                        try:
                            p_chk = json.loads(r_chk["payload_json"])
                            cand_prof = p_chk.get("_profile") or build_requirement_profile(p_chk)
                            dec, score, rule = compare_requirements(incoming_prof, cand_prof)
                            if dec == "DUPLICATE":
                                _LOG.info(
                                    "Upsert duplicate detected for %s against %s (score=%.2f, rule=%s)",
                                    payload.get("job_title"), r_chk["job_id"], score, rule,
                                )
                                existing_row = r_chk
                                break
                        except Exception:
                            continue
                except Exception as _ex:
                    _LOG.debug("Error in whole-requirement fallback matching: %s", _ex)

            if existing_row is not None:
                # --- UPDATE PATH (Rules 2-4) ---
                stored_job_id = existing_row["job_id"]
                try:
                    old_payload = json.loads(existing_row["payload_json"])
                except Exception:
                    old_payload = {}

                # Compute field-level diff BEFORE merging
                changes = _field_diff(old_payload, payload)
                if not changes:
                    # Nothing actually changed - true duplicate, skip (Rule 2)
                    _LOG.debug("DEDUP: client_jd_id=%s is unchanged - skipping", cjd or job_id)
                    conn.execute("COMMIT")
                    conn.close()
                    return stored_job_id

                # Check if caller is attempting to modify immutable fields (A5)
                forbidden_changes = [f for f in ("demand_received_date", "created_at", "receivedDateTime", "email_received_iso", "first_arrival_at", "job_id") if f in changes]
                if forbidden_changes:
                    _LOG.error("Attempt to modify immutable field in _sqlite_upsert: %s", forbidden_changes)
                    conn.execute("ROLLBACK")
                    conn.close()
                    raise ValueError(f"Cannot modify immutable field in requirement: {forbidden_changes}")

                # Rule 3: merge - keep existing values for any field not mentioned in new email
                merged = _merge_payload(old_payload, payload)
                merged["job_id"] = stored_job_id
                if cjd:
                    merged["client_jd_id"] = cjd
                if ident:
                    merged["identity"] = ident

                # Append to field change history
                try:
                    history = json.loads(existing_row["field_change_history"] or "[]")
                except Exception:
                    history = []
                history.append({
                    "changed_at": now,
                    "source_email_id": str(payload.get("graphMessageId") or ""),
                    "changes": changes,
                })

                conn.execute(
                    """UPDATE metaforge_requirements
                       SET payload_json = ?, updated_at = ?, field_change_history = ?, client_jd_id = ?, identity = COALESCE(identity, ?)
                       WHERE job_id = ?""",
                    (
                        json.dumps(merged, ensure_ascii=False),
                        now,
                        json.dumps(history, ensure_ascii=False),
                        cjd or stored_job_id,
                        ident,
                        stored_job_id,
                    ),
                )
                conn.execute("COMMIT")
                conn.close()
                _LOG.info(
                    "UPSERT-UPDATE job_id=%s client_jd_id=%s changed_fields=%s",
                    stored_job_id, cjd, list(changes.keys()),
                )
                return stored_job_id

            else:
                # --- CREATE PATH (R1, R2, R4) ---
                fa = payload.get("first_arrival_at") or payload.get("receivedDateTime") or payload.get("email_received_iso") or now
                payload["first_arrival_at"] = fa
                req_date = get_ist_req_date(fa)

                explicit_job_id = str(payload.get("job_id") or "").strip()
                m_jid = re.match(r"^(\d{4}[/-]\d{2}[/-]\d{2})[-_](\d+)$", explicit_job_id) if explicit_job_id else None

                if m_jid:
                    req_date = m_jid.group(1).replace("-", "/")
                    seq = int(m_jid.group(2))
                    seq_str = f"{seq:03d}" if seq < 1000 else f"{seq}"
                    assigned_job_id = f"{req_date}-{seq_str}"
                else:
                    # Allocate atomically inside the transaction: NNN = MAX(seq) + 1 (R1)
                    cur_max = conn.execute(
                        "SELECT COALESCE(MAX(seq), 0) FROM metaforge_requirements WHERE req_date = ?",
                        (req_date,),
                    ).fetchone()
                    max_seq = cur_max[0] if cur_max and cur_max[0] is not None else 0
                    seq = max_seq + 1
                    seq_str = f"{seq:03d}" if seq < 1000 else f"{seq}"
                    assigned_job_id = f"{req_date}-{seq_str}"

                payload["job_id"] = assigned_job_id
                payload["req_date"] = req_date
                payload["seq"] = seq

                conn.execute(
                    """INSERT INTO metaforge_requirements
                       (job_id, payload_json, created_at, client_jd_id, updated_at, field_change_history, identity, req_date, seq)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        assigned_job_id,
                        json.dumps(payload, ensure_ascii=False),
                        now,
                        cjd if cjd else None,
                        now,
                        json.dumps([], ensure_ascii=False),
                        ident,
                        req_date,
                        seq,
                    ),
                )
                conn.execute("COMMIT")
                conn.close()
                _LOG.info("UPSERT-CREATE job_id=%s req_date=%s seq=%s client_jd_id=%s identity=%s", assigned_job_id, req_date, seq, cjd, ident)
                return assigned_job_id

        except sqlite3.OperationalError as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            if "locked" in str(e).lower() or "busy" in str(e).lower():
                time.sleep(0.05 * (attempt + 1))
                continue
            conn.close()
            raise
        except sqlite3.IntegrityError as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            # Unique constraint conflict on (req_date, seq) or job_id -> retry with next sequence (R2)
            if "idx_mf_req_date_seq" in str(e) or "req_date" in str(e) or "UNIQUE" in str(e):
                time.sleep(0.02 * (attempt + 1))
                continue
            conn.close()
            raise
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            conn.close()
            raise

    conn.close()
    raise RuntimeError("Failed to allocate requirement sequence after max retries")


# Backward compatibility alias for any code that imports _sqlite_insert directly
_sqlite_insert = _sqlite_upsert
