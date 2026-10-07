"""
Track processed Graph message IDs to avoid duplicate extraction and pipeline re-runs.
Uses the original ``processed`` table for legacy dump mode, and ``pipeline_state`` for
the MetaForge pipeline (skip on successful sync or explicit skip).

Rules 1-4 identity engine:
  Rule 1: Every requirement gets ONE stable ID (client_jd_id when available).
  Rule 2: Same ID = same requirement, never a second record.
  Rule 3: Only fields with a new non-blank value are updated; blank does NOT overwrite.
           Every field change is recorded in field_change_history.
  Rule 4: updated_at refreshed on every real change; default UI sort is newest first.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json as _json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Iterable

_LOG = logging.getLogger(__name__)

# Fields tracked for per-field change history (Rule 3 para 6)
_TRACKED_FIELDS: list[str] = [
    "job_title", "location", "overall_experience", "notice_period",
    "number_of_positions", "yearly_budget", "monthly_budget",
    "mandatory_skills", "skills", "job_status", "priority",
    "experience_level", "employment_type", "requirement_from",
    "demand_received_date", "work_mode", "budget_currency",
]


class ProcessedStore:
    """SQLite-backed store for Graph message IDs."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, timeout=60.0)
        try:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=60000")
        except Exception:
            pass
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS processed (graph_id TEXT PRIMARY KEY, processed_at TEXT)"
        )
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS pipeline_state (
                graph_id TEXT PRIMARY KEY,
                updated_at TEXT NOT NULL,
                state TEXT NOT NULL,
                detail TEXT
            )"""
        )
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS pending_reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                graph_id TEXT NOT NULL,
                job_id TEXT NOT NULL,
                client_jd_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                review_fields TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING_REVIEW',
                created_at TEXT NOT NULL,
                identity TEXT,
                possible_duplicate_of TEXT
            )"""
        )
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS requirement_fingerprints (
                fingerprint TEXT PRIMARY KEY,
                graph_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            )"""
        )
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS file_listener_state (
                fingerprint TEXT PRIMARY KEY,
                file_path TEXT NOT NULL,
                processed_at TEXT NOT NULL
            )"""
        )
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS requirement_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                requirement_from TEXT NOT NULL,
                job_title_norm TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                source_graph_id TEXT,
                created_at TEXT NOT NULL
            )"""
        )
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS filtered_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                graph_id TEXT NOT NULL,
                subject TEXT,
                from_email TEXT,
                reason TEXT NOT NULL,
                stage TEXT NOT NULL,
                created_at TEXT NOT NULL
            )"""
        )
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS client_requirements (
                client_jd_id TEXT PRIMARY KEY,
                requirement_from TEXT NOT NULL,
                status TEXT NOT NULL,
                details_hash TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                field_change_history TEXT
            )"""
        )
        # Migration: add field_change_history column if missing (preserves all data)
        try:
            existing_cols = {
                r[1] for r in self._conn.execute(
                    "PRAGMA table_info(client_requirements)"
                ).fetchall()
            }
            if "field_change_history" not in existing_cols:
                self._conn.execute(
                    "ALTER TABLE client_requirements ADD COLUMN field_change_history TEXT"
                )
        except Exception:
            pass
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS status_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                requirement_id TEXT NOT NULL,
                from_status TEXT NOT NULL,
                to_status TEXT NOT NULL,
                changed_at TEXT NOT NULL,
                source_email_id TEXT,
                changed_by TEXT NOT NULL
            )"""
        )
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS seen_messages (
                graph_id TEXT PRIMARY KEY,
                internet_message_id TEXT,
                seen_at TEXT NOT NULL,
                subject TEXT,
                source TEXT
            )"""
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_seen_messages_inet_id ON seen_messages(internet_message_id)"
        )
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS ingest_watermark (
                key TEXT PRIMARY KEY,
                watermark_iso TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )"""
        )
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS requirement_identity (
                identity TEXT PRIMARY KEY,
                client TEXT NOT NULL,
                client_jd_id TEXT,
                city TEXT,
                state TEXT NOT NULL,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                times_seen INTEGER NOT NULL DEFAULT 1,
                original_record_ref TEXT,
                last_graph_id TEXT,
                profile_json TEXT,
                text_fingerprint TEXT
            )"""
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_req_identity_client_jd_id ON requirement_identity(client_jd_id)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_req_identity_client_city ON requirement_identity(client, city)"
        )

        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS duplicate_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_email_id TEXT NOT NULL,
                matched_requirement_id TEXT NOT NULL,
                score REAL NOT NULL,
                deciding_rule TEXT NOT NULL,
                decision TEXT NOT NULL,
                created_at TEXT NOT NULL
            )"""
        )

        # Migration: ensure requirement_identity has city, profile_json, text_fingerprint
        try:
            ri_cols = {
                r[1] for r in self._conn.execute("PRAGMA table_info(requirement_identity)").fetchall()
            }
            if "city" not in ri_cols:
                self._conn.execute("ALTER TABLE requirement_identity ADD COLUMN city TEXT")
            if "profile_json" not in ri_cols:
                self._conn.execute("ALTER TABLE requirement_identity ADD COLUMN profile_json TEXT")
            if "text_fingerprint" not in ri_cols:
                self._conn.execute("ALTER TABLE requirement_identity ADD COLUMN text_fingerprint TEXT")
        except Exception:
            pass

        # Migration: ensure pending_reviews has identity & possible_duplicate_of columns and unique index
        try:
            pr_cols = {
                r[1] for r in self._conn.execute("PRAGMA table_info(pending_reviews)").fetchall()
            }
            if "identity" not in pr_cols:
                self._conn.execute("ALTER TABLE pending_reviews ADD COLUMN identity TEXT")
            if "possible_duplicate_of" not in pr_cols:
                self._conn.execute("ALTER TABLE pending_reviews ADD COLUMN possible_duplicate_of TEXT")
            self._conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_pending_reviews_identity ON pending_reviews(identity) WHERE identity IS NOT NULL"
            )
        except Exception:
            pass

        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS email_dispositions (
                message_id TEXT PRIMARY KEY,
                graph_id TEXT,
                internet_message_id TEXT,
                subject TEXT,
                from_email TEXT,
                received_date_time TEXT,
                disposition TEXT NOT NULL,
                requirements_count INTEGER DEFAULT 0,
                reason TEXT,
                attempts INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )"""
        )

        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS scheduler_heartbeats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                fetched INTEGER DEFAULT 0,
                extracted INTEGER DEFAULT 0,
                failed INTEGER DEFAULT 0,
                status TEXT NOT NULL,
                error_message TEXT,
                created_at TEXT NOT NULL
            )"""
        )

        # Seed seen_messages from legacy processed and pipeline_state tables
        try:
            self._conn.execute(
                """INSERT OR IGNORE INTO seen_messages (graph_id, seen_at, source)
                   SELECT graph_id, COALESCE(processed_at, datetime('now')), 'legacy_processed' FROM processed"""
            )
            self._conn.execute(
                """INSERT OR IGNORE INTO seen_messages (graph_id, seen_at, source)
                   SELECT graph_id, updated_at, 'legacy_pipeline_state' FROM pipeline_state
                   WHERE state IN ('synced', 'skipped', 'pending_sync', 'pending_review')"""
            )
        except Exception:
            pass

        self._conn.commit()

    def is_message_seen(self, graph_id: str | None = None, internet_message_id: str | None = None) -> bool:
        """Check if message was already seen in seen_messages, processed, or pipeline_state."""
        gid = str(graph_id or "").strip()
        inet_id = str(internet_message_id or "").strip()
        if gid:
            cur = self._conn.execute("SELECT 1 FROM seen_messages WHERE graph_id = ? LIMIT 1", (gid,))
            if cur.fetchone() is not None:
                return True
            cur = self._conn.execute("SELECT 1 FROM processed WHERE graph_id = ? LIMIT 1", (gid,))
            if cur.fetchone() is not None:
                return True
            cur = self._conn.execute(
                "SELECT 1 FROM pipeline_state WHERE graph_id = ? AND state IN ('synced', 'skipped', 'pending_sync', 'pending_review') LIMIT 1",
                (gid,),
            )
            if cur.fetchone() is not None:
                return True
        if inet_id:
            cur = self._conn.execute("SELECT 1 FROM seen_messages WHERE internet_message_id = ? LIMIT 1", (inet_id,))
            if cur.fetchone() is not None:
                return True
        return False

    def mark_message_seen(
        self,
        graph_id: str,
        internet_message_id: str | None = None,
        subject: str | None = None,
        source: str = "pipeline",
    ) -> None:
        """Record message as seen in seen_messages and processed tables."""
        from datetime import datetime, timezone

        gid = str(graph_id or "").strip()
        if not gid:
            return
        inet_id = str(internet_message_id or "").strip() or None
        ts = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """INSERT OR REPLACE INTO seen_messages (graph_id, internet_message_id, seen_at, subject, source)
               VALUES (?, ?, ?, ?, ?)""",
            (gid, inet_id, ts, subject or "", source),
        )
        self._conn.execute(
            """INSERT OR IGNORE INTO processed (graph_id, processed_at) VALUES (?, ?)""",
            (gid, ts),
        )
        self._conn.commit()

    def get_watermark(self, key: str = "default") -> str | None:
        """Get the saved watermark ISO timestamp."""
        cur = self._conn.execute(
            "SELECT watermark_iso FROM ingest_watermark WHERE key = ? LIMIT 1",
            (key,),
        )
        row = cur.fetchone()
        return str(row[0]) if row and row[0] else None

    def set_watermark(self, watermark_iso: str, key: str = "default") -> None:
        """Set the watermark ISO timestamp for ingestion tracking."""
        from datetime import datetime, timezone

        ts = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """INSERT OR REPLACE INTO ingest_watermark (key, watermark_iso, updated_at)
               VALUES (?, ?, ?)""",
            (key, str(watermark_iso), ts),
        )
        self._conn.commit()

    def get_requirement_identity(self, identity: str) -> dict[str, Any] | None:
        """Look up requirement identity."""
        ident = str(identity or "").strip()
        if not ident:
            return None
        cur = self._conn.execute(
            """SELECT identity, client, client_jd_id, state, first_seen, last_seen, times_seen, original_record_ref, last_graph_id
               FROM requirement_identity WHERE identity = ? LIMIT 1""",
            (ident,),
        )
        r = cur.fetchone()
        if not r:
            return None
        return {
            "identity": r[0],
            "client": r[1],
            "client_jd_id": r[2],
            "state": r[3],
            "first_seen": r[4],
            "last_seen": r[5],
            "times_seen": r[6],
            "original_record_ref": r[7],
            "last_graph_id": r[8],
        }

    @contextmanager
    def atomic_claim(self):
        """Atomic transaction lock ensuring mutual exclusion during candidate check and insertion (W8)."""
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            yield
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def log_duplicate_decision(
        self,
        *,
        source_email_id: str,
        matched_requirement_id: str,
        score: float,
        deciding_rule: str,
        decision: str,
    ) -> None:
        """Log a duplicate decision (W7)."""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """INSERT INTO duplicate_decisions
               (source_email_id, matched_requirement_id, score, deciding_rule, decision, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (source_email_id, matched_requirement_id, score, deciding_rule, decision, now),
        )
        self._conn.commit()

    def _get_sibling_metaforge_db(self, override_path: Path | str | None = None) -> Path | None:
        if override_path:
            p = Path(override_path)
            return p if p.exists() else None
        p = self.path.parent / "metaforge_requirements.db"
        if p.exists():
            return p
        test_mf = self.path.parent / "test_metaforge.db"
        if test_mf.exists():
            return test_mf
        data_p = Path(__file__).resolve().parent / "data" / "metaforge_requirements.db"
        if data_p.exists() and self.path.parent.resolve() == data_p.parent.resolve():
            return data_p
        return None

    def find_requirement_duplicate(
        self,
        profile: dict[str, Any],
        rules_config: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any] | None, float, str]:
        """
        Compare profile against stored & pending requirements of same client and city (W4, W5).
        Returns (decision, matched_candidate, score, deciding_rule).
        """
        from requirement_comparator import compare_requirements

        client = profile.get("client") or "unknown"
        city = profile.get("city")

        # Candidate query: same client, matching city (or if either city is None/unspecified)
        if city:
            cur = self._conn.execute(
                """SELECT identity, client, client_jd_id, city, state, original_record_ref,
                          profile_json, text_fingerprint, times_seen, last_seen
                   FROM requirement_identity
                   WHERE client = ? AND (city = ? OR city IS NULL OR city = '')""",
                (client, city),
            )
        else:
            cur = self._conn.execute(
                """SELECT identity, client, client_jd_id, city, state, original_record_ref,
                          profile_json, text_fingerprint, times_seen, last_seen
                   FROM requirement_identity
                   WHERE client = ?""",
                (client,),
            )
        rows = cur.fetchall()

        best_possible: tuple[dict[str, Any], float, str] | None = None

        for r in rows:
            cand = {
                "identity": r[0],
                "client": r[1],
                "client_jd_id": r[2],
                "city": r[3],
                "state": r[4],
                "original_record_ref": r[5],
                "profile_json": r[6],
                "text_fingerprint": r[7],
                "times_seen": r[8],
                "last_seen": r[9],
            }
            cand_profile = None
            if cand["profile_json"]:
                try:
                    cand_profile = _json.loads(cand["profile_json"])
                except Exception:
                    cand_profile = None
            if not cand_profile:
                cand_profile = {
                    "client": cand["client"],
                    "client_jd_id": cand["client_jd_id"],
                    "city": cand["city"],
                    "title": cand["identity"].split(":")[-1] if "hash" not in cand["identity"] else "",
                    "mandatory_skills": [],
                    "additional_skills": [],
                    "cleaned_text": "",
                    "text_fingerprint": cand["text_fingerprint"] or "",
                }

            dec, score, rule = compare_requirements(profile, cand_profile, rules_config=rules_config)
            if dec == "DUPLICATE":
                return ("DUPLICATE", cand, score, rule)
            if dec == "POSSIBLE_DUPLICATE":
                if best_possible is None or score > best_possible[1]:
                    best_possible = (cand, score, rule)

        # Unified self-healing store lookup (Rules N1 & A4):
        # A requirement is NEW only if absent from EVERY store:
        # requirement_identity, client_requirements, metaforge_requirements, pending_reviews, duplicates_archive.
        cjd = profile.get("client_jd_id")
        client_norm = (client or "").strip().lower()

        # 1. Check client_requirements
        if cjd:
            try:
                cur_cr = self._conn.execute(
                    "SELECT client_jd_id, requirement_from, status, payload_json FROM client_requirements WHERE client_jd_id = ? OR json_extract(payload_json, '$.client_jd_id') = ?",
                    (cjd, cjd),
                )
                for cr_row in cur_cr.fetchall():
                    cr_from = (cr_row[1] or "").strip().lower()
                    is_unresolved = (not client_norm) or (not cr_from) or client_norm in ("unresolved", "unknown", "idexcel_unresolved") or cr_from in ("unresolved", "unknown", "idexcel_unresolved") or ("unresolved" in client_norm)
                    if cr_from and client_norm and client_norm not in cr_from and cr_from not in client_norm and not is_unresolved:
                        continue
                    cr_payload = _json.loads(cr_row[3]) if cr_row[3] else {}
                    orig_ref = cr_payload.get("job_id") or cjd
                    cr_cand = {
                        "identity": f"{client}:{cjd}",
                        "client": client,
                        "client_jd_id": cjd,
                        "city": city,
                        "state": "stored",
                        "original_record_ref": orig_ref,
                        "profile_json": _json.dumps(profile),
                        "text_fingerprint": profile.get("text_fingerprint") or "",
                        "times_seen": 1,
                        "last_seen": "",
                    }
                    self.register_requirement_identity(
                        identity=cr_cand["identity"],
                        client=client,
                        client_jd_id=cjd,
                        city=city,
                        profile=profile,
                        state="stored",
                        original_record_ref=orig_ref,
                    )
                    return ("DUPLICATE", cr_cand, 1.0, f"CLIENT_REQUIREMENTS_MATCH ({cjd})")
            except Exception:
                pass

        # 2. Check metaforge_requirements (sibling metaforge_requirements.db or test_metaforge.db)
        mf_path = self._get_sibling_metaforge_db()
        if mf_path and mf_path.exists():
            try:
                conn_mf = sqlite3.connect(f"file:{mf_path}?mode=ro", uri=True)
                if cjd:
                    cur_mf = conn_mf.execute(
                        "SELECT job_id, client_jd_id, payload_json FROM metaforge_requirements WHERE client_jd_id = ? OR json_extract(payload_json, '$.client_jd_id') = ?",
                        (cjd, cjd),
                    )
                    for mf_row in cur_mf.fetchall():
                        orig_ref = mf_row[0]
                        mf_payload = _json.loads(mf_row[2]) if mf_row[2] else {}
                        mf_client = (mf_payload.get("requirement_from") or mf_payload.get("client") or "").strip().lower()
                        is_unresolved = (not client_norm) or (not mf_client) or client_norm in ("unresolved", "unknown", "idexcel_unresolved") or mf_client in ("unresolved", "unknown", "idexcel_unresolved") or ("unresolved" in client_norm)
                        if mf_client and client_norm and client_norm not in mf_client and mf_client not in client_norm and not is_unresolved:
                            continue
                        mf_cand = {
                            "identity": f"{client}:{cjd}",
                            "client": client,
                            "client_jd_id": cjd,
                            "city": city,
                            "state": "stored",
                            "original_record_ref": orig_ref,
                            "profile_json": _json.dumps(profile),
                            "text_fingerprint": profile.get("text_fingerprint") or "",
                            "times_seen": 1,
                            "last_seen": "",
                        }
                        conn_mf.close()
                        self.register_requirement_identity(
                            identity=mf_cand["identity"],
                            client=client,
                            client_jd_id=cjd,
                            city=city,
                            profile=profile,
                            state="stored",
                            original_record_ref=orig_ref,
                        )
                        return ("DUPLICATE", mf_cand, 1.0, f"METAFORGE_REQUIREMENTS_MATCH ({cjd})")

                # If no client ID, check whole requirement comparison against records in metaforge_requirements
                cur_mf_all = conn_mf.execute("SELECT job_id, client_jd_id, payload_json FROM metaforge_requirements")
                for m_jid, m_cjd, m_pstr in cur_mf_all.fetchall():
                    try:
                        m_p = _json.loads(m_pstr)
                        m_client = (m_p.get("requirement_from") or m_p.get("client") or "").strip().lower()
                        if m_client and client_norm and client_norm not in m_client and m_client not in client_norm:
                            continue
                        m_prof = build_requirement_profile(m_p)
                        dec, score, rule = compare_requirements(profile, m_prof, rules_config=rules_config)
                        if dec == "DUPLICATE":
                            m_cand = {
                                "identity": f"{client}:{m_cjd or m_jid}",
                                "client": client,
                                "client_jd_id": m_cjd,
                                "city": m_prof.get("city"),
                                "state": "stored",
                                "original_record_ref": m_jid,
                                "profile_json": _json.dumps(m_prof),
                                "text_fingerprint": m_prof.get("text_fingerprint") or "",
                                "times_seen": 1,
                                "last_seen": "",
                            }
                            conn_mf.close()
                            self.register_requirement_identity(
                                identity=m_cand["identity"],
                                client=client,
                                client_jd_id=m_cjd,
                                city=m_prof.get("city"),
                                profile=m_prof,
                                state="stored",
                                original_record_ref=m_jid,
                            )
                            return ("DUPLICATE", m_cand, score, rule)
                    except Exception:
                        continue
                conn_mf.close()
            except Exception:
                pass

        # 3. Check pending_reviews
        if cjd:
            try:
                cur_pr = self._conn.execute(
                    "SELECT identity, job_id, client_jd_id, payload_json FROM pending_reviews WHERE client_jd_id = ?",
                    (cjd,),
                )
                for pr_row in cur_pr.fetchall():
                    pr_payload = _json.loads(pr_row[3]) if pr_row[3] else {}
                    pr_client = (pr_payload.get("requirement_from") or pr_payload.get("client") or "").strip().lower()
                    is_unresolved = (not client_norm) or (not pr_client) or client_norm in ("unresolved", "unknown", "idexcel_unresolved") or pr_client in ("unresolved", "unknown", "idexcel_unresolved") or ("unresolved" in client_norm)
                    if pr_client and client_norm and client_norm not in pr_client and pr_client not in client_norm and not is_unresolved:
                        continue
                    pr_cand = {
                        "identity": pr_row[0] or f"{client}:{cjd}",
                        "client": client,
                        "client_jd_id": cjd,
                        "city": city,
                        "state": "pending_review",
                        "original_record_ref": pr_row[1] or f"pending:{cjd}",
                        "profile_json": _json.dumps(profile),
                        "text_fingerprint": profile.get("text_fingerprint") or "",
                        "times_seen": 1,
                        "last_seen": "",
                    }
                    return ("DUPLICATE", pr_cand, 1.0, f"PENDING_REVIEWS_MATCH ({cjd})")
            except Exception:
                pass

        # 4. Check duplicates_archive
        if cjd:
            try:
                has_archive = self._conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='duplicates_archive'"
                ).fetchone()
                if has_archive:
                    cur_da = self._conn.execute(
                        "SELECT job_id, original_job_id, client FROM duplicates_archive WHERE client_jd_id = ?",
                        (cjd,),
                    )
                    for da_row in cur_da.fetchall():
                        da_client = (da_row[2] or "").strip().lower() if len(da_row) > 2 else ""
                        if da_client and client_norm and client_norm not in da_client and da_client not in client_norm:
                            continue
                        da_cand = {
                            "identity": f"{client}:{cjd}",
                            "client": client,
                            "client_jd_id": cjd,
                            "city": city,
                            "state": "stored",
                            "original_record_ref": da_row[1] or da_row[0],
                            "profile_json": _json.dumps(profile),
                            "text_fingerprint": profile.get("text_fingerprint") or "",
                            "times_seen": 1,
                            "last_seen": "",
                        }
                        return ("DUPLICATE", da_cand, 1.0, f"DUPLICATES_ARCHIVE_MATCH ({cjd})")
            except Exception:
                pass

        if best_possible:
            return ("POSSIBLE_DUPLICATE", best_possible[0], best_possible[1], best_possible[2])

        return ("NOT_DUPLICATE", None, 0.0, "NO_MATCHING_CANDIDATE")

    def register_requirement_identity(
        self,
        *,
        identity: str,
        client: str,
        client_jd_id: str | None = None,
        state: str,
        original_record_ref: str | None = None,
        graph_id: str | None = None,
        seen_at: str | None = None,
        profile: dict[str, Any] | None = None,
        city: str | None = None,
        profile_json: str | None = None,
        text_fingerprint: str | None = None,
    ) -> bool:
        """Register identity immediately. Returns True if newly registered, False if already exists."""
        from datetime import datetime, timezone

        ident = str(identity or "").strip()
        if not ident:
            return False
        now = seen_at or datetime.now(timezone.utc).isoformat()
        cur = self._conn.execute("SELECT 1 FROM requirement_identity WHERE identity = ? LIMIT 1", (ident,))
        if cur.fetchone() is not None:
            return False

        if profile:
            city = city or profile.get("city")
            profile_json = profile_json or _json.dumps(profile, ensure_ascii=False)
            text_fingerprint = text_fingerprint or profile.get("text_fingerprint")

        self._conn.execute(
            """INSERT INTO requirement_identity
               (identity, client, client_jd_id, city, state, first_seen, last_seen, times_seen, original_record_ref, last_graph_id, profile_json, text_fingerprint)
               VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)""",
            (ident, client, client_jd_id, city, state, now, now, original_record_ref, graph_id, profile_json, text_fingerprint),
        )
        self._conn.commit()
        return True

    def update_identity_seen(
        self,
        identity: str,
        graph_id: str | None = None,
        seen_at: str | None = None,
    ) -> None:
        """Update last_seen timestamp and increment times_seen counter."""
        from datetime import datetime, timezone

        ident = str(identity or "").strip()
        if not ident:
            return
        now = seen_at or datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """UPDATE requirement_identity
               SET times_seen = times_seen + 1,
                   last_seen = ?,
                   last_graph_id = COALESCE(?, last_graph_id)
               WHERE identity = ?""",
            (now, graph_id, ident),
        )
        self._conn.commit()

    def update_identity_state(
        self,
        identity: str,
        state: str,
        original_record_ref: str | None = None,
    ) -> None:
        """Update requirement identity state (e.g. pending_review -> stored)."""
        ident = str(identity or "").strip()
        if not ident:
            return
        if original_record_ref:
            self._conn.execute(
                """UPDATE requirement_identity
                   SET state = ?, original_record_ref = ?
                   WHERE identity = ?""",
                (state, original_record_ref, ident),
            )
        else:
            self._conn.execute(
                """UPDATE requirement_identity
                   SET state = ?
                   WHERE identity = ?""",
                (state, ident),
            )
        self._conn.commit()

    def record_status_change(
        self,
        *,
        requirement_id: str,
        from_status: str,
        to_status: str,
        source_email_id: str | None = None,
        changed_by: str = "RULE_ENGINE",
    ) -> None:
        from datetime import datetime, timezone

        ts = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """INSERT INTO status_history
               (requirement_id, from_status, to_status, changed_at, source_email_id, changed_by)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (requirement_id, from_status, to_status, ts, source_email_id or "", changed_by),
        )
        self._conn.commit()

    def get_status_history(self, requirement_id: str) -> list[dict]:
        cur = self._conn.execute(
            """SELECT id, requirement_id, from_status, to_status, changed_at, source_email_id, changed_by
               FROM status_history
               WHERE requirement_id = ?
               ORDER BY id ASC""",
            (requirement_id,),
        )
        rows = cur.fetchall()
        return [
            {
                "id": r[0],
                "requirement_id": r[1],
                "from_status": r[2],
                "to_status": r[3],
                "changed_at": r[4],
                "source_email_id": r[5],
                "changed_by": r[6],
            }
            for r in rows
        ]

    def find_requirements_by_conversation_id(self, conversation_id: str) -> list[tuple[str, dict]]:
        """Return all stored requirements belonging to an Outlook conversation ID."""
        import json
        cid = str(conversation_id or "").strip()
        if not cid:
            return []
        results: list[tuple[str, dict]] = []
        seen_refs: set[str] = set()

        # 1. Search metaforge_requirements.db (primary source of truth)
        mf_path = self._get_sibling_metaforge_db()
        if mf_path and mf_path.exists():
            try:
                conn_mf = sqlite3.connect(mf_path)
                cur_mf = conn_mf.execute("SELECT job_id, client_jd_id, payload_json FROM metaforge_requirements")
                for jid, cjd, pstr in cur_mf.fetchall():
                    try:
                        p = json.loads(pstr)
                        prov = p.get("_provenance", {}) if isinstance(p.get("_provenance"), dict) else {}
                        if (
                            prov.get("conversation_id") == cid
                            or prov.get("graph_message_id") == cid
                            or p.get("graphMessageId") == cid
                            or p.get("conversationId") == cid
                            or p.get("conversation_id") == cid
                        ):
                            ref = jid or cjd
                            if ref and ref not in seen_refs:
                                seen_refs.add(ref)
                                results.append((ref, p))
                    except Exception:
                        continue
                conn_mf.close()
            except Exception:
                pass

        # 2. Search client_requirements
        try:
            cur = self._conn.execute("SELECT client_jd_id, payload_json FROM client_requirements")
            for cjd, payload_str in cur.fetchall():
                try:
                    p = json.loads(payload_str)
                    prov = p.get("_provenance", {}) if isinstance(p.get("_provenance"), dict) else {}
                    if (
                        prov.get("conversation_id") == cid
                        or prov.get("graph_message_id") == cid
                        or p.get("graphMessageId") == cid
                        or p.get("conversationId") == cid
                        or p.get("conversation_id") == cid
                    ):
                        ref = cjd or p.get("job_id")
                        if ref and ref not in seen_refs:
                            seen_refs.add(ref)
                            results.append((ref, p))
                except Exception:
                    continue
        except Exception:
            pass

        # 3. Search requirement_memory
        try:
            cur = self._conn.execute("SELECT payload_json FROM requirement_memory ORDER BY created_at DESC")
            for (payload_str,) in cur.fetchall():
                try:
                    p = json.loads(payload_str)
                    prov = p.get("_provenance", {}) if isinstance(p.get("_provenance"), dict) else {}
                    if (
                        prov.get("conversation_id") == cid
                        or prov.get("graph_message_id") == cid
                        or p.get("graphMessageId") == cid
                        or p.get("conversationId") == cid
                        or p.get("conversation_id") == cid
                    ):
                        ref = p.get("job_id") or p.get("client_jd_id") or ""
                        if ref and ref not in seen_refs:
                            seen_refs.add(ref)
                            results.append((ref, p))
                except Exception:
                    continue
        except Exception:
            pass

        return results

    def find_requirement_by_conversation_id(
        self,
        conversation_id: str,
        title: str | None = None,
        client_jd_id: str | None = None,
    ) -> tuple[str, dict] | None:
        """Find matching requirement in thread. If multiple exist, match by client_jd_id or title."""
        reqs = self.find_requirements_by_conversation_id(conversation_id)
        if not reqs:
            return None
        if len(reqs) == 1:
            return reqs[0]
        # Multi-role: match by client_jd_id if given
        cjd_norm = str(client_jd_id or "").strip().lower()
        if cjd_norm:
            for ref, p in reqs:
                cand_cjd = str(p.get("client_jd_id") or "").strip().lower()
                if cand_cjd and cand_cjd == cjd_norm:
                    return ref, p
        # Match by title if given
        title_norm = str(title or "").strip().lower()
        if title_norm:
            for ref, p in reqs:
                cand_title = str(p.get("job_title") or "").strip().lower()
                if cand_title and (cand_title in title_norm or title_norm in cand_title):
                    return ref, p
        return reqs[0]

    def find_requirement_by_message_id(self, message_id: str) -> tuple[str, dict] | None:
        """Find existing requirement by parent message ID (In-Reply-To or References)."""
        import json
        mid = str(message_id or "").strip()
        if not mid:
            return None
        mid_clean = mid.strip("<>").strip()

        # 1. Search metaforge_requirements.db
        mf_path = self._get_sibling_metaforge_db()
        if mf_path and mf_path.exists():
            try:
                conn_mf = sqlite3.connect(mf_path)
                cur_mf = conn_mf.execute("SELECT job_id, client_jd_id, payload_json FROM metaforge_requirements")
                for jid, cjd, pstr in cur_mf.fetchall():
                    try:
                        p = json.loads(pstr)
                        prov = p.get("_provenance", {}) if isinstance(p.get("_provenance"), dict) else {}
                        g_id = str(prov.get("graph_message_id") or p.get("graphMessageId") or "").strip()
                        i_id = str(prov.get("internet_message_id") or p.get("internetMessageId") or "").strip().strip("<>")
                        if mid == g_id or mid_clean == g_id or mid == i_id or mid_clean == i_id:
                            conn_mf.close()
                            return (jid or cjd), p
                    except Exception:
                        continue
                conn_mf.close()
            except Exception:
                pass

        # 2. Search client_requirements
        try:
            cur = self._conn.execute("SELECT client_jd_id, payload_json FROM client_requirements")
            for cjd, payload_str in cur.fetchall():
                try:
                    p = json.loads(payload_str)
                    prov = p.get("_provenance", {}) if isinstance(p.get("_provenance"), dict) else {}
                    g_id = str(prov.get("graph_message_id") or p.get("graphMessageId") or "").strip()
                    i_id = str(prov.get("internet_message_id") or p.get("internetMessageId") or "").strip().strip("<>")
                    if mid == g_id or mid_clean == g_id or mid == i_id or mid_clean == i_id:
                        return cjd, p
                except Exception:
                    continue
        except Exception:
            pass
        return None

    def find_requirement_by_req_id(self, req_id: str) -> tuple[str, dict] | None:
        import json

        rid = str(req_id or "").strip()
        if not rid:
            return None
        cur = self._conn.execute(
            """SELECT payload_json FROM client_requirements WHERE client_jd_id = ? LIMIT 1""",
            (rid,),
        )
        row = cur.fetchone()
        if row:
            try:
                p = json.loads(row[0])
                return rid, p
            except Exception:
                pass
        # Check requirement_identity for original_record_ref or client_jd_id
        cur = self._conn.execute(
            """SELECT original_record_ref, client_jd_id FROM requirement_identity WHERE identity = ? OR client_jd_id = ? OR original_record_ref = ? LIMIT 1""",
            (rid, rid, rid),
        )
        row = cur.fetchone()
        if row:
            ref = row[1] or row[0]
            if ref:
                cur2 = self._conn.execute(
                    """SELECT payload_json FROM client_requirements WHERE client_jd_id = ? LIMIT 1""",
                    (ref,),
                )
                row2 = cur2.fetchone()
                if row2:
                    try:
                        p = json.loads(row2[0])
                        return ref, p
                    except Exception:
                        pass
        cur = self._conn.execute(
            """SELECT payload_json FROM requirement_memory ORDER BY created_at DESC"""
        )
        for (payload_str,) in cur.fetchall():
            try:
                p = json.loads(payload_str)
                if p.get("client_jd_id") == rid or p.get("job_id") == rid or p.get("identity") == rid:
                    return rid, p
            except Exception:
                continue

        # Check sibling metaforge_requirements.db or test_metaforge.db
        mf_path = self._get_sibling_metaforge_db()
        if mf_path and mf_path.exists():
            try:
                conn_mf = sqlite3.connect(mf_path)
                cur_mf = conn_mf.execute(
                    "SELECT job_id, client_jd_id, payload_json FROM metaforge_requirements WHERE job_id = ? OR client_jd_id = ? LIMIT 1",
                    (rid, rid),
                )
                mf_row = cur_mf.fetchone()
                if mf_row:
                    p = json.loads(mf_row[2])
                    conn_mf.close()
                    return mf_row[0], p
                conn_mf.close()
            except Exception:
                pass
        return None

    def find_requirement_by_subject(self, subject: str) -> tuple[str, dict] | None:
        """
        Find existing requirement whose original email subject matches this email's subject
        (stripping RE:, FW:, FWD: prefixes).
        """
        import re
        import json
        if not subject:
            return None

        def clean_subj(s: str) -> str:
            cleaned = re.sub(r"(?i)^(?:re|fwd|fw)\s*:\s*", "", (s or "").strip())
            while re.match(r"(?i)^(?:re|fwd|fw)\s*:\s*", cleaned):
                cleaned = re.sub(r"(?i)^(?:re|fwd|fw)\s*:\s*", "", cleaned).strip()
            return re.sub(r"\s+", " ", cleaned).strip().lower()

        target_subj = clean_subj(subject)
        if len(target_subj) < 5:
            return None

        # 1. Search metaforge_requirements.db
        mf_path = self._get_sibling_metaforge_db()
        if mf_path and mf_path.exists():
            try:
                conn_mf = sqlite3.connect(mf_path)
                cur = conn_mf.execute("SELECT job_id, client_jd_id, payload_json FROM metaforge_requirements")
                for jid, cjd, pstr in cur.fetchall():
                    try:
                        p = json.loads(pstr)
                        s = p.get("subject") or p.get("email_subject") or ""
                        if s and clean_subj(s) == target_subj:
                            conn_mf.close()
                            return (jid or cjd), p
                    except Exception:
                        continue
                conn_mf.close()
            except Exception:
                pass

        # 2. Search client_requirements
        try:
            cur = self._conn.execute("SELECT client_jd_id, payload_json FROM client_requirements")
            for cjd, pstr in cur.fetchall():
                try:
                    p = json.loads(pstr)
                    s = p.get("subject") or p.get("email_subject") or ""
                    if s and clean_subj(s) == target_subj:
                        return cjd, p
                except Exception:
                    continue
        except Exception:
            pass

        # 3. Search requirement_memory
        try:
            cur = self._conn.execute("SELECT payload_json FROM requirement_memory ORDER BY created_at DESC")
            for (pstr,) in cur.fetchall():
                try:
                    p = json.loads(pstr)
                    s = p.get("subject") or p.get("email_subject") or ""
                    if s and clean_subj(s) == target_subj:
                        return (p.get("job_id") or p.get("client_jd_id") or ""), p
                except Exception:
                    continue
        except Exception:
            pass

        return None

    def find_requirement_by_client_and_title(self, client: str, title: str) -> tuple[str, dict] | None:
        """
        Find existing requirement by client and fuzzy/token title match (>= 0.80).
        """
        import json
        import difflib
        from requirement_identity import normalize_identity_text, normalize_client_key
        if not client or not title:
            return None

        norm_c = normalize_client_key(client)
        norm_t = normalize_identity_text(title)
        if len(norm_t) < 3:
            return None

        def title_match(t1: str, t2: str) -> bool:
            if not t1 or not t2:
                return False
            if t1 == t2:
                return True
            seq = difflib.SequenceMatcher(None, t1, t2).ratio()
            tok1 = set(t1.split())
            tok2 = set(t2.split())
            jacc = len(tok1 & tok2) / len(tok1 | tok2) if (tok1 and tok2) else 0.0
            return max(seq, jacc) >= 0.80

        mf_path = self._get_sibling_metaforge_db()
        if mf_path and mf_path.exists():
            try:
                conn_mf = sqlite3.connect(mf_path)
                cur = conn_mf.execute("SELECT job_id, client_jd_id, payload_json FROM metaforge_requirements")
                for jid, cjd, pstr in cur.fetchall():
                    try:
                        p = json.loads(pstr)
                        p_client = normalize_client_key(p.get("requirement_from") or p.get("client") or "")
                        if p_client == norm_c:
                            p_title = normalize_identity_text(p.get("job_title") or "")
                            if title_match(norm_t, p_title):
                                conn_mf.close()
                                return (jid or cjd), p
                    except Exception:
                        continue
                conn_mf.close()
            except Exception:
                pass

        try:
            cur = self._conn.execute("SELECT client_jd_id, requirement_from, payload_json FROM client_requirements")
            for cjd, c_from, pstr in cur.fetchall():
                try:
                    p = json.loads(pstr)
                    p_client = normalize_client_key(c_from or p.get("requirement_from") or "")
                    if p_client == norm_c:
                        p_title = normalize_identity_text(p.get("job_title") or "")
                        if title_match(norm_t, p_title):
                            return cjd, p
                except Exception:
                    continue
        except Exception:
            pass

        return None

    def update_requirement_status(
        self,
        *,
        requirement_id: str,
        new_status: str,
        source_email_id: str | None = None,
        changed_by: str = "RULE_ENGINE",
        metaforge_db_path: Path | str | None = None,
    ) -> bool:
        import json
        from datetime import datetime, timezone

        req_info = self.find_requirement_by_req_id(requirement_id)
        if not req_info:
            return False

        cjd, payload = req_info
        old_status = payload.get("job_status", "open")
        norm_new_status = new_status.lower()
        if old_status.lower() == norm_new_status.lower():
            return True

        payload["job_status"] = norm_new_status
        payload_str = json.dumps(payload, ensure_ascii=False)
        new_hash = self._compute_requirement_details_hash(payload)
        now = datetime.now(timezone.utc).isoformat()

        self._conn.execute(
            """UPDATE client_requirements
               SET status = ?, details_hash = ?, payload_json = ?, updated_at = ?
               WHERE client_jd_id = ?""",
            (norm_new_status, new_hash, payload_str, now, cjd),
        )

        mf_db = self._get_sibling_metaforge_db(metaforge_db_path)
        if mf_db and mf_db.exists():
            try:
                conn_mf = sqlite3.connect(mf_db)
                job_id = payload.get("job_id")
                ident = payload.get("identity")
                cur_mf = conn_mf.execute("SELECT job_id, payload_json FROM metaforge_requirements")
                for r_jid, r_pstr in cur_mf.fetchall():
                    try:
                        p_obj = json.loads(r_pstr)
                        if (
                            (cjd and p_obj.get("client_jd_id") == cjd)
                            or (job_id and p_obj.get("job_id") == job_id)
                            or (job_id and r_jid == job_id)
                            or (requirement_id and (r_jid == requirement_id or p_obj.get("job_id") == requirement_id or p_obj.get("client_jd_id") == requirement_id))
                            or (ident and p_obj.get("identity") == ident)
                        ):
                            p_obj["job_status"] = norm_new_status
                            p_obj["requirement_status"] = norm_new_status
                            p_obj["updated_at"] = now
                            conn_mf.execute(
                                "UPDATE metaforge_requirements SET payload_json = ?, updated_at = ? WHERE job_id = ?",
                                (json.dumps(p_obj, ensure_ascii=False), now, r_jid),
                            )
                    except Exception:
                        pass
                try:
                    conn_mf.execute(
                        "INSERT INTO status_history (requirement_id, from_status, to_status, changed_at, source_email_id, changed_by) VALUES (?, ?, ?, ?, ?, ?)",
                        (requirement_id or cjd or job_id, old_status, norm_new_status, now, source_email_id or "", changed_by),
                    )
                except Exception:
                    pass
                conn_mf.commit()
                conn_mf.close()
            except Exception as ex:
                _LOG.warning("Failed to update metaforge_requirements.db status: %s", ex)

        self.record_status_change(
            requirement_id=requirement_id or cjd or payload.get("job_id") or "",
            from_status=old_status,
            to_status=norm_new_status,
            source_email_id=source_email_id,
            changed_by=changed_by,
        )
        self._conn.commit()
        return True

    def update_requirement_fields_in_place(
        self,
        *,
        requirement_id: str,
        incoming_payload: dict[str, Any],
        source_email_id: str | None = None,
        metaforge_db_path: Path | str | None = None,
    ) -> bool:
        """
        Modify existing requirement in place when changes occur in duplicate/reply emails.
        Ensures a requirement is stored only once, updating fields (location, experience, skills, budget, etc.)
        and recording the changes in field_change_history.
        """
        import json
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        updated_any = False

        cjd = incoming_payload.get("client_jd_id") or ""
        ref = requirement_id or cjd

        mf_db = self._get_sibling_metaforge_db(metaforge_db_path)

        fields_to_check = [
            "skills", "mandatory_skills", "monthly_budget", "yearly_budget",
            "budget_currency", "number_of_positions", "location", "overall_experience",
            "overall_experience_min", "overall_experience_max",
            "work_mode", "job_title", "notice_period", "priority",
            "experience_level", "employment_type", "job_status", "requirement_status"
        ]

        if mf_db.exists():
            try:
                conn_mf = sqlite3.connect(mf_db)
                conn_mf.row_factory = sqlite3.Row
                cur_mf = conn_mf.execute(
                    "SELECT job_id, client_jd_id, payload_json, field_change_history, identity FROM metaforge_requirements WHERE job_id = ? OR client_jd_id = ? OR identity = ? OR former_job_id = ?",
                    (ref, cjd or ref, ref, ref),
                )
                rows = list(cur_mf.fetchall())
                if not rows and ref:
                    cur_all = conn_mf.execute("SELECT job_id, client_jd_id, payload_json, field_change_history, identity FROM metaforge_requirements")
                    for r_all in cur_all.fetchall():
                        try:
                            p_chk = json.loads(r_all["payload_json"]) if r_all["payload_json"] else {}
                            if (
                                p_chk.get("job_id") == ref
                                or p_chk.get("client_jd_id") == ref
                                or p_chk.get("identity") == ref
                                or (cjd and p_chk.get("client_jd_id") == cjd)
                            ):
                                rows.append(r_all)
                        except Exception:
                            continue

                for r in rows:
                    r_jid = r["job_id"]
                    try:
                        p_obj = json.loads(r["payload_json"]) if r["payload_json"] else {}
                        hist = []
                        if "field_change_history" in r.keys() and r["field_change_history"]:
                            try:
                                hist = json.loads(r["field_change_history"]) or []
                            except Exception:
                                hist = []

                        row_updated = False
                        for fld in fields_to_check:
                            new_val = incoming_payload.get(fld)
                            if new_val is not None and str(new_val).strip() and str(new_val).strip().lower() not in ("none", "null", "unresolved", "unknown", "—"):
                                old_val = p_obj.get(fld)
                                is_changed = False
                                if not old_val or str(old_val).strip() in ("", "None", "null", "unresolved", "unknown", "—"):
                                    is_changed = True
                                elif isinstance(new_val, list) or isinstance(old_val, list):
                                    l_new = [str(x).strip().lower() for x in (new_val if isinstance(new_val, list) else [new_val]) if str(x).strip()]
                                    l_old = [str(x).strip().lower() for x in (old_val if isinstance(old_val, list) else [old_val]) if str(x).strip()]
                                    if set(l_new) != set(l_old):
                                        is_changed = True
                                elif str(new_val).strip().lower() != str(old_val).strip().lower():
                                    is_changed = True

                                if is_changed:
                                    p_obj[fld] = new_val
                                    hist.append({
                                        "field": fld,
                                        "old_value": old_val,
                                        "new_value": new_val,
                                        "changed_at": now,
                                        "source": source_email_id or "email_update",
                                    })
                                    row_updated = True

                        if row_updated:
                            p_obj["updated_at"] = now
                            conn_mf.execute(
                                "UPDATE metaforge_requirements SET payload_json = ?, field_change_history = ?, updated_at = ? WHERE job_id = ?",
                                (json.dumps(p_obj, ensure_ascii=False), json.dumps(hist, ensure_ascii=False), now, r_jid),
                            )
                            updated_any = True
                    except Exception:
                        pass
                conn_mf.commit()
                conn_mf.close()
            except Exception as ex:
                _LOG.warning("Failed to update metaforge_requirements in-place: %s", ex)

        # Also update client_requirements in processed_messages.db if present
        try:
            cur_cr = self._conn.execute(
                "SELECT client_jd_id, payload_json FROM client_requirements WHERE client_jd_id = ? OR client_jd_id = ?",
                (cjd or ref, ref),
            )
            cr_row = cur_cr.fetchone()
            if cr_row and cr_row[1]:
                p_cr = json.loads(cr_row[1])
                cr_updated = False
                for fld in fields_to_check:
                    new_val = incoming_payload.get(fld)
                    if new_val is not None and str(new_val).strip() and str(new_val).strip().lower() not in ("none", "null", "unresolved", "unknown", "—"):
                        old_cr_val = p_cr.get(fld)
                        if not old_cr_val or str(old_cr_val).strip() in ("", "None", "null", "unresolved", "unknown", "—"):
                            p_cr[fld] = new_val
                            cr_updated = True
                        elif isinstance(new_val, list) or isinstance(old_cr_val, list):
                            l_new = [str(x).strip().lower() for x in (new_val if isinstance(new_val, list) else [new_val]) if str(x).strip()]
                            l_old = [str(x).strip().lower() for x in (old_cr_val if isinstance(old_cr_val, list) else [old_cr_val]) if str(x).strip()]
                            if set(l_new) != set(l_old):
                                p_cr[fld] = new_val
                                cr_updated = True
                        elif str(new_val).strip().lower() != str(old_cr_val).strip().lower():
                            p_cr[fld] = new_val
                            cr_updated = True
                if cr_updated:
                    new_hash = self._compute_requirement_details_hash(p_cr)
                    self._conn.execute(
                        "UPDATE client_requirements SET payload_json = ?, details_hash = ?, updated_at = ? WHERE client_jd_id = ?",
                        (json.dumps(p_cr, ensure_ascii=False), new_hash, now, cr_row[0]),
                    )
                    self._conn.commit()
        except Exception:
            pass

        # Clean up any pending_reviews that matched this client_jd_id
        if cjd:
            try:
                self._conn.execute("DELETE FROM pending_reviews WHERE client_jd_id = ?", (cjd,))
                self._conn.commit()
            except Exception:
                pass

        return updated_any


    def log_filtered(
        self,
        *,
        graph_id: str,
        subject: str | None = None,
        from_email: str | None = None,
        reason: str,
        stage: str,
    ) -> None:
        from datetime import datetime, timezone

        ts = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """INSERT INTO filtered_log
               (graph_id, subject, from_email, reason, stage, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (graph_id, subject or "", from_email or "", reason, stage, ts),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> ProcessedStore:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    # --- Legacy dump mode (mark every exported message) ---

    def is_processed(self, graph_id: str) -> bool:
        cur = self._conn.execute(
            "SELECT 1 FROM processed WHERE graph_id = ? LIMIT 1", (graph_id,)
        )
        return cur.fetchone() is not None

    def mark(self, graph_id: str) -> None:
        from datetime import datetime, timezone

        ts = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT OR REPLACE INTO processed (graph_id, processed_at) VALUES (?, ?)",
            (graph_id, ts),
        )
        self._conn.commit()

    def mark_many(self, ids: Iterable[str]) -> None:
        for i in ids:
            self.mark(i)

    # --- MetaForge pipeline states ---

    def pipeline_get_state(self, graph_id: str) -> str | None:
        cur = self._conn.execute(
            "SELECT state FROM pipeline_state WHERE graph_id = ? LIMIT 1",
            (graph_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return str(row[0] or "").strip().lower() or None

    def pipeline_should_skip(self, graph_id: str, internet_message_id: str | None = None) -> bool:
        if self.is_message_seen(graph_id, internet_message_id):
            return True
        state = self.pipeline_get_state(graph_id)
        # terminal or handoff-complete states should not be re-enqueued
        return state in {"synced", "skipped", "pending_sync", "pending_review"}

    def pipeline_clear_stale_inflight(self, max_age_seconds: int = 1800) -> int:
        """Drop queued/processing rows stuck longer than max_age_seconds so they can be re-enqueued."""
        from datetime import datetime, timezone

        cutoff = datetime.now(timezone.utc).timestamp() - max_age_seconds
        rows = self._conn.execute(
            """SELECT graph_id, updated_at, state FROM pipeline_state
               WHERE state IN ('queued', 'processing')"""
        ).fetchall()
        cleared = 0
        for graph_id, updated_at, state in rows:
            try:
                ts = datetime.fromisoformat(str(updated_at).replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if ts.timestamp() >= cutoff:
                    continue
            except Exception:
                pass
            self._conn.execute(
                "DELETE FROM pipeline_state WHERE graph_id = ? AND state = ?",
                (graph_id, state),
            )
            cleared += 1
        if cleared:
            self._conn.commit()
        return cleared

    def pipeline_pending_sync_with_memory(self, limit: int = 5) -> list[tuple[str, str]]:
        cur = self._conn.execute(
            """SELECT ps.graph_id, rm.payload_json
               FROM pipeline_state ps
               JOIN requirement_memory rm ON rm.source_graph_id = ps.graph_id
               WHERE ps.state = 'pending_sync'
               ORDER BY ps.updated_at ASC
               LIMIT ?""",
            (max(1, limit),),
        )
        return [(str(gid), str(payload)) for gid, payload in cur.fetchall()]

    def pipeline_mark_queued(self, graph_id: str, detail: str | None = None) -> None:
        from datetime import datetime, timezone

        ts = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """INSERT OR REPLACE INTO pipeline_state (graph_id, updated_at, state, detail)
               VALUES (?, ?, 'queued', ?)""",
            (graph_id, ts, (detail or "")[:2000]),
        )
        self._conn.commit()

    def pipeline_mark_processing(self, graph_id: str, detail: str | None = None) -> None:
        from datetime import datetime, timezone

        ts = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """INSERT OR REPLACE INTO pipeline_state (graph_id, updated_at, state, detail)
               VALUES (?, ?, 'processing', ?)""",
            (graph_id, ts, (detail or "")[:2000]),
        )
        self._conn.commit()

    def pipeline_mark_pending_sync(self, graph_id: str, detail: str | None = None) -> None:
        from datetime import datetime, timezone

        ts = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """INSERT OR REPLACE INTO pipeline_state (graph_id, updated_at, state, detail)
               VALUES (?, ?, 'pending_sync', ?)""",
            (graph_id, ts, (detail or "")[:2000]),
        )
        self._conn.commit()

    def pipeline_mark_pending_review(self, graph_id: str, detail: str | None = None) -> None:
        from datetime import datetime, timezone

        ts = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """INSERT OR REPLACE INTO pipeline_state (graph_id, updated_at, state, detail)
               VALUES (?, ?, 'pending_review', ?)""",
            (graph_id, ts, (detail or "")[:2000]),
        )
        self._conn.commit()

    def add_pending_review(
        self,
        *,
        graph_id: str,
        job_id: str,
        client_jd_id: str,
        payload_json: str,
        review_fields: str,
        identity: str | None = None,
        possible_duplicate_of: str | None = None,
    ) -> None:
        from datetime import datetime, timezone

        ts = datetime.now(timezone.utc).isoformat()
        if identity:
            self._conn.execute(
                """INSERT OR IGNORE INTO pending_reviews
                   (graph_id, job_id, client_jd_id, payload_json, review_fields, status, created_at, identity, possible_duplicate_of)
                   VALUES (?, ?, ?, ?, ?, 'PENDING_REVIEW', ?, ?, ?)""",
                (graph_id, job_id, client_jd_id, payload_json, review_fields, ts, identity, possible_duplicate_of),
            )
        else:
            self._conn.execute(
                """INSERT INTO pending_reviews
                   (graph_id, job_id, client_jd_id, payload_json, review_fields, status, created_at, possible_duplicate_of)
                   VALUES (?, ?, ?, ?, ?, 'PENDING_REVIEW', ?, ?)""",
                (graph_id, job_id, client_jd_id, payload_json, review_fields, ts, possible_duplicate_of),
            )
        self._conn.commit()

    def approve_pending_review(
        self,
        pending_id: int,
        allocator: Any,
        settings: Any = None,
    ) -> tuple[bool, str, dict[str, Any] | None]:
        """
        Approve a pending review item with whole-requirement duplicate check (W9).
        Returns (success, result_message_or_job_id, matched_info_if_duplicate).
        """
        from datetime import date
        from requirement_comparator import build_requirement_profile
        from metaforge_api import send_to_metaforge

        with self.atomic_claim():
            cur = self._conn.execute("SELECT * FROM pending_reviews WHERE id = ?", (pending_id,))
            row = cur.fetchone()
            if not row:
                return (False, "not_found", None)

            cols = [d[0] for d in cur.description]
            pending_item = dict(zip(cols, row))
            if pending_item.get("status") != "PENDING_REVIEW":
                return (False, f"already_{str(pending_item.get('status', 'resolved')).lower()}", None)

            try:
                payload = _json.loads(pending_item["payload_json"])
            except Exception:
                payload = {}

            profile = build_requirement_profile(payload)
            rules_cfg = {
                "similarity_weights": getattr(settings, "similarity_weights", None) if settings else None,
                "similarity_thresholds": getattr(settings, "similarity_thresholds", None) if settings else None,
            }

            decision, matched, score, rule = self.find_requirement_duplicate(profile, rules_config=rules_cfg)
            if decision == "DUPLICATE" and matched:
                matched_id = matched.get("identity") or matched.get("original_record_ref") or "known_dup"
                self.log_duplicate_decision(
                    source_email_id=pending_item.get("graph_id", ""),
                    matched_requirement_id=matched_id,
                    score=score,
                    deciding_rule=rule,
                    decision=decision,
                )
                self.update_identity_seen(matched["identity"])
                self._conn.execute(
                    "UPDATE pending_reviews SET status = 'DUPLICATE_RESOLVED' WHERE id = ?",
                    (pending_id,),
                )
                self._conn.commit()
                return (False, "duplicate", matched)

            # Not duplicate: allocate REQ number inside transaction and store (R1, R3)
            job_id = None
            if settings:
                job_id = send_to_metaforge(payload, settings)
            if not job_id:
                job_id = payload.get("job_id") or (allocator.next_job_id(date.today()) if allocator else "")
                payload["job_id"] = job_id

            ident = pending_item.get("identity") or f"{profile.get('client', 'unknown')}:{job_id}"

            self.register_requirement_identity(
                identity=ident,
                client=profile.get("client", "unknown"),
                client_jd_id=profile.get("client_jd_id"),
                city=profile.get("city"),
                profile=profile,
                state="stored",
                original_record_ref=job_id,
                graph_id=pending_item.get("graph_id"),
            )

            self._conn.execute(
                "UPDATE pending_reviews SET status = 'APPROVED', job_id = ? WHERE id = ?",
                (job_id, pending_id),
            )
            self._conn.commit()
            return (True, job_id, None)

    def pipeline_mark_skipped(self, graph_id: str, reason: str) -> None:
        from datetime import datetime, timezone

        ts = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """INSERT OR REPLACE INTO pipeline_state (graph_id, updated_at, state, detail)
               VALUES (?, ?, 'skipped', ?)""",
            (graph_id, ts, reason[:2000] if reason else ""),
        )
        self._conn.commit()

    def pipeline_mark_synced(self, graph_id: str, detail: str | None = None) -> None:
        from datetime import datetime, timezone

        ts = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """INSERT OR REPLACE INTO pipeline_state (graph_id, updated_at, state, detail)
               VALUES (?, ?, 'synced', ?)""",
            (graph_id, ts, (detail or "")[:2000]),
        )
        self._conn.commit()

    # --- Cross-message dedupe ---

    def requirement_fingerprint_exists(
        self,
        *,
        requirement_from: str,
        job_title: str,
        location: str,
        budget_period: str,
        hours: int = 24,
    ) -> bool:
        from datetime import datetime, timedelta, timezone

        fp = self._make_requirement_fingerprint(
            requirement_from=requirement_from,
            job_title=job_title,
            location=location,
            budget_period=budget_period,
        )
        threshold = (datetime.now(timezone.utc) - timedelta(hours=max(1, hours))).isoformat()
        cur = self._conn.execute(
            """SELECT 1 FROM requirement_fingerprints
               WHERE fingerprint = ? AND created_at >= ?
               LIMIT 1""",
            (fp, threshold),
        )
        return cur.fetchone() is not None

    def add_requirement_fingerprint(
        self,
        *,
        graph_id: str,
        requirement_from: str,
        job_title: str,
        location: str,
        budget_period: str,
    ) -> None:
        from datetime import datetime, timezone

        fp = self._make_requirement_fingerprint(
            requirement_from=requirement_from,
            job_title=job_title,
            location=location,
            budget_period=budget_period,
        )
        ts = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """INSERT OR REPLACE INTO requirement_fingerprints (fingerprint, graph_id, created_at)
               VALUES (?, ?, ?)""",
            (fp, graph_id, ts),
        )
        self._conn.commit()

    # --- File listener dedupe ---

    def is_file_event_processed(self, fingerprint: str) -> bool:
        cur = self._conn.execute(
            "SELECT 1 FROM file_listener_state WHERE fingerprint = ? LIMIT 1",
            (fingerprint,),
        )
        return cur.fetchone() is not None

    def mark_file_event_processed(self, *, fingerprint: str, file_path: str) -> None:
        from datetime import datetime, timezone

        ts = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """INSERT OR REPLACE INTO file_listener_state (fingerprint, file_path, processed_at)
               VALUES (?, ?, ?)""",
            (fingerprint, file_path, ts),
        )
        self._conn.commit()

    # --- Requirement historical memory for autofill ---

    def add_requirement_memory(
        self,
        *,
        requirement_from: str,
        job_title: str,
        payload_json: str,
        source_graph_id: str | None = None,
    ) -> None:
        from datetime import datetime, timezone

        ts = datetime.now(timezone.utc).isoformat()
        title_norm = str(job_title or "").strip().lower()
        req_from = str(requirement_from or "").strip().lower()
        self._conn.execute(
            """INSERT INTO requirement_memory
               (requirement_from, job_title_norm, payload_json, source_graph_id, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (req_from, title_norm, payload_json, source_graph_id, ts),
        )
        self._conn.commit()

    def get_requirement_memory_candidates(
        self,
        *,
        requirement_from: str,
        job_title: str,
        limit: int = 20,
    ) -> list[str]:
        req_from = str(requirement_from or "").strip().lower()
        title_norm = str(job_title or "").strip().lower()
        if not req_from or not title_norm:
            return []
        cur = self._conn.execute(
            """SELECT payload_json FROM requirement_memory
               WHERE requirement_from = ? AND job_title_norm = ?
               ORDER BY created_at DESC
               LIMIT ?""",
            (req_from, title_norm, max(1, limit)),
        )
        return [str(r[0]) for r in cur.fetchall()]

    def get_requirement_memory_exact(
        self,
        *,
        requirement_from: str,
        job_title: str,
        limit: int = 5,
    ) -> list[str]:
        """Return memory payloads that match BOTH requirement_from AND job_title_norm exactly.

        Intentionally has NO client-only fallback.  The old
        ``get_requirement_memory_candidates`` fell back to a client-name-only
        query when no exact title match was found, which caused completely
        unrelated roles (e.g. SAP CO Management Accounting) to be returned as
        candidates for "Pega Marketing" and their skills to be autofilled
        onto the wrong record (Bug A).  This method returns [] instead of a
        wrong-role record.
        """
        req_from = str(requirement_from or "").strip().lower()
        title_norm = str(job_title or "").strip().lower()
        if not req_from or not title_norm:
            return []
        cur = self._conn.execute(
            """SELECT payload_json FROM requirement_memory
               WHERE requirement_from = ? AND job_title_norm = ?
               ORDER BY created_at DESC
               LIMIT ?""",
            (req_from, title_norm, max(1, limit)),
        )
        return [str(r[0]) for r in cur.fetchall()]

    @staticmethod
    def _make_requirement_fingerprint(
        *,
        requirement_from: str,
        job_title: str,
        location: str,
        budget_period: str,
    ) -> str:
        raw = "|".join(
            [
                str(requirement_from or "").strip().lower(),
                str(job_title or "").strip().lower(),
                str(location or "").strip().lower(),
                str(budget_period or "").strip().lower(),
            ]
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _compute_requirement_details_hash(self, payload: dict) -> str:
        """Hash key fields to detect details/status changes (Rules 4 & 5)."""
        import json
        import hashlib

        details = {
            "job_title": str(payload.get("job_title") or "").strip().lower(),
            "location": str(payload.get("location") or "").strip().lower(),
            "overall_experience": str(payload.get("overall_experience") or "").strip().lower(),
            "notice_period": str(payload.get("notice_period") or "").strip().lower(),
            "number_of_positions": payload.get("number_of_positions"),
            "yearly_budget": payload.get("yearly_budget"),
            "monthly_budget": payload.get("monthly_budget"),
            "mandatory_skills": payload.get("mandatory_skills"),
            "skills": payload.get("skills"),
            "job_status": str(payload.get("job_status") or "open").strip().lower(),
            "priority": str(payload.get("priority") or "").strip().lower(),
        }
        blob = json.dumps(details, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def _find_existing_client_requirement(self, client_jd_id: str) -> tuple[str, str, str, str] | None:
        """
        Search for existing stored requirement by client_jd_id across client_requirements,
        pending_reviews, and metaforge_requirements.db.
        Returns (req_id, status, details_hash, payload_json) or None.
        """
        cjd = str(client_jd_id or "").strip()
        if not cjd or cjd.lower() in ("none", "null", "not_found"):
            return None

        # 1. Check client_requirements table
        try:
            cur = self._conn.execute(
                "SELECT client_jd_id, status, details_hash, payload_json FROM client_requirements WHERE client_jd_id = ? LIMIT 1",
                (cjd,),
            )
            row = cur.fetchone()
            if row:
                try:
                    p = json.loads(row[3])
                    int_id = str(p.get("job_id") or row[0])
                except Exception:
                    int_id = str(row[0])
                return (int_id, str(row[1]), str(row[2]), str(row[3]))
        except Exception:
            pass

        # 2. Check pending_reviews table
        try:
            cur = self._conn.execute(
                "SELECT job_id, status, payload_json FROM pending_reviews WHERE client_jd_id = ? LIMIT 1",
                (cjd,),
            )
            row = cur.fetchone()
            if row:
                p_str = str(row[2])
                try:
                    p_dict = json.loads(p_str)
                    d_hash = self._compute_requirement_details_hash(p_dict)
                except Exception:
                    d_hash = ""
                return (str(row[0]), str(row[1]), d_hash, p_str)
        except Exception:
            pass

        # 3. Check metaforge_requirements.db
        mf_db = self._get_sibling_metaforge_db()
        if mf_db and mf_db.exists():
            try:
                conn_mf = sqlite3.connect(f"file:{mf_db.resolve()}?mode=ro", uri=True)
                conn_mf.row_factory = sqlite3.Row
                rows = conn_mf.execute("SELECT job_id, payload_json FROM metaforge_requirements").fetchall()
                for r in rows:
                    try:
                        p = json.loads(r["payload_json"])
                        if p.get("client_jd_id") == cjd or p.get("client_jd_id_override") == cjd:
                            d_hash = self._compute_requirement_details_hash(p)
                            st = str(p.get("job_status") or "open").lower()
                            conn_mf.close()
                            return (str(r["job_id"]), st, d_hash, r["payload_json"])
                    except Exception:
                        continue
                conn_mf.close()
            except Exception:
                pass

        return None

    # ---------------------------------------------------------------------------
    # Field-level diff helpers (Rule 3 para 6)
    # ---------------------------------------------------------------------------

    @staticmethod
    def _field_diff(old_payload: dict, new_payload: dict) -> dict:
        """
        Return {field: {old, new}} for every tracked field that genuinely changed.
        Fields where new_payload has None/blank are EXCLUDED:
        blank never overwrites existing data (Rule 3 para 4).
        """
        changes: dict = {}
        for field in _TRACKED_FIELDS:
            old_val = old_payload.get(field)
            new_val = new_payload.get(field)
            # Only update if new value is genuinely provided (not None/blank/empty list)
            if new_val is None or new_val == "" or new_val == []:
                continue
            old_norm = str(old_val).strip().lower() if old_val is not None else ""
            new_norm = str(new_val).strip().lower()
            if old_norm != new_norm:
                changes[field] = {"old": old_val, "new": new_val}
        return changes

    @staticmethod
    def _merge_payload(existing: dict, new_payload: dict) -> dict:
        """
        Selective merge implementing Rule 3:
        - Non-blank new values overwrite stored values.
        - Blank/null/empty-list new values leave stored values untouched.
        - _provenance dicts are deep-merged, not replaced entirely.
        """
        merged = dict(existing)
        for key, new_val in new_payload.items():
            if key.startswith("_"):
                if key == "_provenance" and isinstance(new_val, dict) and isinstance(merged.get("_provenance"), dict):
                    merged["_provenance"] = {**merged["_provenance"], **new_val}
                else:
                    merged[key] = new_val
                continue
            if new_val is None or new_val == "" or new_val == []:
                # Rule 3 para 4: blank never overwrites existing data
                continue
            merged[key] = new_val
        return merged

    def get_field_change_history(self, requirement_id: str) -> list[dict]:
        """Return the field-level change history for a requirement (Rule 3 para 6)."""
        cjd = str(requirement_id or "").strip()
        if not cjd:
            return []
        cur = self._conn.execute(
            "SELECT field_change_history FROM client_requirements WHERE client_jd_id = ? LIMIT 1",
            (cjd,),
        )
        row = cur.fetchone()
        if not row or not row[0]:
            return []
        try:
            return _json.loads(row[0]) or []
        except Exception:
            return []

    def evaluate_client_requirement_action(
        self,
        *,
        client_jd_id: str,
        requirement_from: str,
        payload: dict,
    ) -> tuple[str, dict | None]:
        """
        Evaluate identity and lifecycle for requirements with a unique Req ID (Rules 1-4).

        Rule 1: Use client_jd_id as the stable unique identity (never changes).
        Rule 2: Same ID already exists -> never create a second record.
        Rule 3: Only update fields with genuinely new non-blank values;
                blank values leave existing data untouched.
                Record every field change in field_change_history.
        Rule 4: Refresh updated_at on every real change.

        Returns ("CREATE", payload), ("UPDATE", merged_payload), or ("SKIP", existing_payload).
        """
        from datetime import datetime, timezone

        cjd = str(client_jd_id or "").strip()
        if not cjd or cjd.lower() in ("none", "null", "not_found"):
            return "CREATE", payload

        new_status = str(payload.get("job_status") or "open").strip().lower()
        now = datetime.now(timezone.utc).isoformat()

        stored_rec = self._find_existing_client_requirement(cjd)
        if not stored_rec:
            # Rule 1: Req ID never seen before -> CREATE new record
            payload_str = _json.dumps(payload, ensure_ascii=False)
            new_hash = self._compute_requirement_details_hash(payload)
            self._conn.execute(
                """INSERT INTO client_requirements
                   (client_jd_id, requirement_from, status, details_hash,
                    payload_json, created_at, updated_at, field_change_history)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (cjd, requirement_from, new_status, new_hash,
                 payload_str, now, now, _json.dumps([])),
            )
            self._conn.commit()
            return "CREATE", payload

        stored_id, stored_status, stored_hash, stored_payload_str = stored_rec

        # Rule 2: Req ID already exists -> never create second record
        try:
            old_payload = _json.loads(stored_payload_str)
        except Exception:
            old_payload = {}

        # Rule 3: Field-level diff — only consider fields with real new values
        field_changes = self._field_diff(old_payload, payload)
        status_changed = (stored_status.lower() != new_status.lower())

        if not field_changes and not status_changed:
            # True duplicate: same ID, nothing changed -> SKIP
            return "SKIP", old_payload

        # Rule 3: Selective merge — blank fields in new email keep old values
        merged = self._merge_payload(old_payload, payload)
        # Rule 1: The original job_id (internal ID) never changes
        merged["job_id"] = old_payload.get("job_id") or payload.get("job_id") or ""
        merged["client_jd_id"] = cjd

        # Rule 4: Update status in the dedicated status_history table
        if status_changed:
            self.record_status_change(
                requirement_id=stored_id,
                from_status=stored_status,
                to_status=new_status,
                source_email_id=str(payload.get("graphMessageId") or ""),
                changed_by="RULE_ENGINE",
            )
            merged["job_status"] = new_status

        # Rule 3 para 6: Append this event to the field_change_history
        try:
            existing_hist_row = self._conn.execute(
                "SELECT field_change_history FROM client_requirements WHERE client_jd_id = ?",
                (cjd,)
            ).fetchone()
            existing_hist = _json.loads(
                (existing_hist_row[0] if existing_hist_row and existing_hist_row[0] else "[]")
            )
        except Exception:
            existing_hist = []

        if field_changes or status_changed:
            all_changes = dict(field_changes)
            if status_changed and "job_status" not in all_changes:
                all_changes["job_status"] = {"old": stored_status, "new": new_status}
            existing_hist.append({
                "changed_at": now,
                "source_email_id": str(payload.get("graphMessageId") or ""),
                "changes": all_changes,
            })

        new_hash = self._compute_requirement_details_hash(merged)
        merged_str = _json.dumps(merged, ensure_ascii=False)
        hist_str = _json.dumps(existing_hist, ensure_ascii=False)

        # Rule 4: Update the record; updated_at is refreshed now
        self._conn.execute(
            """UPDATE client_requirements
               SET status = ?, details_hash = ?, payload_json = ?,
                   updated_at = ?, field_change_history = ?
               WHERE client_jd_id = ?""",
            (new_status, new_hash, merged_str, now, hist_str, cjd),
        )
        self._conn.commit()
        return "UPDATE", merged

    def record_email_disposition(
        self,
        message_id: str,
        graph_id: str | None = None,
        internet_message_id: str | None = None,
        subject: str | None = None,
        from_email: str | None = None,
        received_date_time: str | None = None,
        disposition: str = "extracted",
        requirements_count: int = 0,
        reason: str | None = None,
        attempts: int = 1,
    ) -> None:
        """
        N1: Record disposition of every fetched message in email_dispositions.
        disposition in {'extracted', 'duplicate', 'filtered', 'not_a_requirement', 'failed'}.
        """
        now = datetime.now(timezone.utc).isoformat()
        mid = str(message_id or graph_id or "").strip()
        if not mid:
            return
        gid = str(graph_id or mid).strip()
        self._conn.execute(
            """INSERT INTO email_dispositions (
                message_id, graph_id, internet_message_id, subject, from_email,
                received_date_time, disposition, requirements_count, reason,
                attempts, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(message_id) DO UPDATE SET
                disposition = excluded.disposition,
                requirements_count = excluded.requirements_count,
                reason = excluded.reason,
                attempts = excluded.attempts,
                updated_at = excluded.updated_at
            """,
            (
                mid,
                gid,
                str(internet_message_id or ""),
                str(subject or ""),
                str(from_email or ""),
                str(received_date_time or ""),
                disposition,
                requirements_count,
                str(reason or "") if reason else None,
                attempts,
                now,
                now,
            ),
        )
        self._conn.commit()

    def reconcile_disposition_ledger(self, fetched_message_ids: list[str]) -> tuple[bool, int, list[str]]:
        """
        N1: After each run, reconcile: messages fetched = ledger rows.
        Returns (is_reconciled, missing_count, missing_ids).
        """
        if not fetched_message_ids:
            return True, 0, []
        placeholders = ",".join("?" for _ in fetched_message_ids)
        cur = self._conn.execute(
            f"SELECT message_id, graph_id FROM email_dispositions WHERE message_id IN ({placeholders}) OR graph_id IN ({placeholders})",
            fetched_message_ids + fetched_message_ids,
        )
        recorded = set()
        for r in cur.fetchall():
            if r[0]:
                recorded.add(r[0])
            if r[1]:
                recorded.add(r[1])
        missing = [m for m in fetched_message_ids if m not in recorded]
        return len(missing) == 0, len(missing), missing

    def record_scheduler_heartbeat(
        self,
        started_at: str,
        finished_at: str | None = None,
        fetched: int = 0,
        extracted: int = 0,
        failed: int = 0,
        status: str = "ok",
        error_message: str | None = None,
    ) -> None:
        """S5: Heartbeat row every tick."""
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """INSERT INTO scheduler_heartbeats (
                started_at, finished_at, fetched, extracted, failed, status, error_message, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (started_at, finished_at, fetched, extracted, failed, status, error_message, now),
        )
        self._conn.commit()

    def get_last_scheduler_heartbeat(self) -> dict[str, Any] | None:
        """S5: Retrieve the most recent scheduler heartbeat."""
        cur = self._conn.execute(
            "SELECT id, started_at, finished_at, fetched, extracted, failed, status, error_message, created_at FROM scheduler_heartbeats ORDER BY id DESC LIMIT 1"
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "started_at": row[1],
            "finished_at": row[2],
            "fetched": row[3],
            "extracted": row[4],
            "failed": row[5],
            "status": row[6],
            "error_message": row[7],
            "created_at": row[8],
        }

    def get_filtered_emails(self, limit: int = 100) -> list[dict[str, Any]]:
        """N3: Retrieve filtered emails for view."""
        cur = self._conn.execute(
            "SELECT message_id, subject, from_email, received_date_time, disposition, reason, created_at FROM email_dispositions WHERE disposition IN ('filtered', 'not_a_requirement') ORDER BY id DESC LIMIT ?",
            (limit,)
        )
        out = []
        for r in cur.fetchall():
            out.append({
                "message_id": r[0],
                "subject": r[1],
                "from_email": r[2],
                "received_date_time": r[3],
                "disposition": r[4],
                "reason": r[5],
                "created_at": r[6],
            })
        return out

    def _ensure_alert_table(self) -> None:
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS alert_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                recipient TEXT NOT NULL,
                subject TEXT NOT NULL,
                summary TEXT NOT NULL,
                status TEXT NOT NULL,
                error_message TEXT,
                dedup_key TEXT,
                created_at TEXT NOT NULL
            )"""
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_alert_history_dedup ON alert_history(dedup_key, created_at)"
        )
        self._conn.commit()

    def record_alert(
        self,
        alert_type: str,
        severity: str,
        recipient: str,
        subject: str,
        summary: str,
        status: str,
        error_message: str | None = None,
        dedup_key: str | None = None,
        created_at: str | None = None,
    ) -> int:
        """Record an alert event and delivery outcome in the alert history ledger."""
        self._ensure_alert_table()
        now = created_at or datetime.now(timezone.utc).isoformat()
        cur = self._conn.execute(
            """INSERT INTO alert_history (
                alert_type, severity, recipient, subject, summary, status, error_message, dedup_key, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (alert_type, severity, recipient, subject, summary, status, error_message, dedup_key, now),
        )
        self._conn.commit()
        return cur.lastrowid or 0

    def get_last_alert_by_dedup_key(self, dedup_key: str) -> dict[str, Any] | None:
        """Retrieve the most recent alert event matching the deduplication key."""
        self._ensure_alert_table()
        cur = self._conn.execute(
            "SELECT id, alert_type, severity, recipient, subject, summary, status, error_message, dedup_key, created_at FROM alert_history WHERE dedup_key = ? ORDER BY id DESC LIMIT 1",
            (dedup_key,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "alert_type": row[1],
            "severity": row[2],
            "recipient": row[3],
            "subject": row[4],
            "summary": row[5],
            "status": row[6],
            "error_message": row[7],
            "dedup_key": row[8],
            "created_at": row[9],
        }

    def get_recent_alerts(self, limit: int = 50) -> list[dict[str, Any]]:
        """Retrieve recent alerts for monitoring, reporting, and dashboard feeds."""
        self._ensure_alert_table()
        cur = self._conn.execute(
            "SELECT id, alert_type, severity, recipient, subject, summary, status, error_message, dedup_key, created_at FROM alert_history ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        out = []
        for r in cur.fetchall():
            out.append({
                "id": r[0],
                "alert_type": r[1],
                "severity": r[2],
                "recipient": r[3],
                "subject": r[4],
                "summary": r[5],
                "status": r[6],
                "error_message": r[7],
                "dedup_key": r[8],
                "created_at": r[9],
            })
        return out



