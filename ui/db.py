"""Read-only SQLite Database interface for Recruiter Application UI.

Rule 4: Default sort is updated_at DESC (most recently changed requirement first).
Rule 2: Deduplication by client_jd_id — one record per unique requirement.
Rule 3: Expose field_change_history from both client_requirements and metaforge_requirements.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import time
from datetime import datetime, timezone

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from config import is_strict_field_mapping

_LOG = logging.getLogger(__name__)

# In-memory record cache to accelerate page loads and API lookups
_CACHE_RECORDS: Dict[Any, Tuple[float, Any, List[Dict[str, Any]]]] = {}
_CACHE_TTL: float = 120.0  # seconds
_CACHE_RECORD_MAP: Dict[str, Dict[str, Any]] = {}
_CACHE_SIGNATURE: Any = None


def _populate_record_cache_map(records: List[Dict[str, Any]], rule: dict, db_signature: Any) -> None:
    global _CACHE_RECORD_MAP, _CACHE_SIGNATURE
    _CACHE_RECORD_MAP.clear()
    _CACHE_SIGNATURE = db_signature

    # Pass 1: Former IDs as fallback aliases only
    for rec in records:
        fid = rec.get("former_job_id")
        if fid:
            _CACHE_RECORD_MAP.setdefault(fid, rec)
            _CACHE_RECORD_MAP.setdefault(normalize_id(fid, rule), rec)

    # Pass 2: Active genuine IDs (always take absolute precedence)
    for rec in records:
        ident = rec.get("identity")
        if ident:
            _CACHE_RECORD_MAP[ident] = rec
        rid = rec.get("req_id")
        if rid:
            _CACHE_RECORD_MAP[rid] = rec
            _CACHE_RECORD_MAP[normalize_id(rid, rule)] = rec
        raw_id = rec.get("raw_req_id")
        if raw_id:
            _CACHE_RECORD_MAP[raw_id] = rec
            _CACHE_RECORD_MAP[normalize_id(raw_id, rule)] = rec
        fmt_id = rec.get("fmt_id")
        if fmt_id:
            _CACHE_RECORD_MAP[fmt_id] = rec
        cjd = rec.get("client_jd_id") or rec.get("payload", {}).get("client_jd_id")
        if cjd:
            _CACHE_RECORD_MAP[cjd] = rec
            _CACHE_RECORD_MAP[normalize_id(cjd, rule)] = rec


def _parse_to_utc_dt(dt_val: Any) -> datetime:
    """Parse any datetime value into a timezone-aware UTC datetime object."""
    if not dt_val:
        return datetime.min.replace(tzinfo=timezone.utc)
    s = str(dt_val).strip()
    if not s or s.lower() in ("none", "null", "n/a"):
        return datetime.min.replace(tzinfo=timezone.utc)

    try:
        if s.endswith("Z"):
            return datetime.fromisoformat(s[:-1] + "+00:00").astimezone(timezone.utc)
        if "+" in s[10:] or ("-" in s[10:] and len(s) > 16):
            return datetime.fromisoformat(s).astimezone(timezone.utc)
        if len(s) == 10:
            return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if " " in s[:19]:
            s = s[:10] + "T" + s[11:]
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)


def normalize_id(req_id: str, rule: dict) -> str:
    """Normalize a requirement ID according to configuration rules."""
    if not req_id:
        return ""
    val = req_id
    if rule.get("strip_whitespace", True):
        val = val.strip()
    if rule.get("uppercase", True):
        val = val.upper()
    return val


def _open_ro_connection(db_path: str) -> Optional[sqlite3.Connection]:
    """Open SQLite connection strictly in read-only mode."""
    if not os.path.exists(db_path):
        _LOG.warning("Database file not found: %s", db_path)
        return None
    try:
        uri = f"file:{os.path.abspath(db_path)}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as err:
        _LOG.error("Failed to open DB %s in read-only mode: %s", db_path, err)
        return None


def _format_internal_id(raw_id: str) -> str | None:
    """Format internal requirement ID as YYYY/MM/DD-NNN if matching date sequence."""
    if not raw_id:
        return None
    val = str(raw_id).strip()
    if val.startswith("REQ-"):
        val = val[4:]
    m = re.search(r"(\d{4})[\-\/]?(\d{2})[\-\/]?(\d{2})[\-\/]?(\d{3,})$", val)
    if m:
        return f"{m.group(1)}/{m.group(2)}/{m.group(3)}-{m.group(4)}"
    return None


def _clean_client_jd_id(val: Any, client: str | None = None, context: Any = None) -> str | None:
    """Return genuine client-provided ID or None if invalid/rejected (C1, C2)."""
    from client_identity_validator import is_genuine_client_id
    is_val, clean_id, _ = is_genuine_client_id(client, val, context=context)
    return clean_id if is_val else None


def _extract_real_client_jd_id(payload: dict, raw_id: str, client: str | None = None) -> str | None:
    """Return genuine client-provided ID or None if not extracted from text (never fabricated)."""
    cjd = payload.get("client_jd_id") or payload.get("client_jd_id_override")
    if not cjd or str(cjd).lower() in ("none", "null", "not_found"):
        # Check if raw_id is a client ID (e.g., not YYYY-MM-DD-NNN)
        if raw_id and not _format_internal_id(raw_id):
            cjd = raw_id
        else:
            return None
    return _clean_client_jd_id(cjd, client=client, context=payload)


def _merge_field_change_history(hist_a: list, hist_b: list) -> list:
    """Merge two field_change_history lists, deduplicated by changed_at+source_email_id."""
    seen = set()
    merged = []
    for h in (hist_a + hist_b):
        key = (h.get("changed_at", ""), h.get("source_email_id", ""))
        if key not in seen:
            seen.add(key)
            merged.append(h)
    merged.sort(key=lambda x: x.get("changed_at", ""))
    return merged


def parse_email_budget(body: str) -> tuple[str | None, int | None, int | None, str | None]:
    """Extract monthly compensation or billing rate ranges/values from email body."""
    if not body:
        return None, None, None, None

    text = body.replace('\xa0', ' ')

    def convert_val(val_str: str, unit_str: str) -> int:
        v = float(val_str.replace(',', '').strip())
        u = (unit_str or '').lower().strip()
        if u == 'k':
            return int(v * 1000)
        elif 'l' in u:
            return int(v * 100000)
        elif v < 50:  # E.g. 1.5 - 2 or 1.5 LPM
            return int(v * 100000)
        elif v < 1000:  # E.g. 85 in "85 - 100 K"
            return int(v * 1000)
        else:
            return int(v)

    # Regex targeting rate labels:
    rate_pattern = re.compile(
        r'(?i)(?:^|[\r\n])\s*(?:monthly\s+bill\s+rate|monthly\s+billing\s+rate|monthly\s+budget|bill\s+rate|billing\s+rate)\s*(?:per\s+month(?:\s+for\s+tpc)?)?\s*(?:\([^)]*\))?\s*[:\-–]?\s*([^\r\n]+(?:\r?\n[^\r\n]+)?)'
    )

    for m in rate_pattern.finditer(text):
        chunk = m.group(1).strip()
        lines = [l.strip() for l in chunk.splitlines() if l.strip()]
        for l in lines:
            if re.search(r'(?i)\b(years?|yrs?|experience|qualification|location|shift|customer|immediate)\b', l):
                continue
            # Range e.g. "150000 - 200000", "85 K - 1L / M", "200000-220000 max", "120000 – 140000"
            m_rng = re.search(r'(\d[\d,\.]*)\s*(k|l|lakhs?|lpm)?\s*(?:–|-|to)\s*(\d[\d,\.]*)\s*(k|l|lakhs?|lpm)?', l, re.IGNORECASE)
            if m_rng:
                try:
                    s1, u1 = m_rng.group(1), m_rng.group(2)
                    s2, u2 = m_rng.group(3), m_rng.group(4)
                    eff_u1 = u1 or (u2 if float(s1.replace(',', '')) < 1000 and u2 == 'k' else '')
                    eff_u2 = u2 or (u1 if float(s2.replace(',', '')) < 1000 and u1 == 'k' else '')
                    low_val = convert_val(s1, eff_u1)
                    high_val = convert_val(s2, eff_u2)
                    if 10000 <= low_val <= 10000000 and 10000 <= high_val <= 10000000:
                        return f"{low_val} - {high_val}", low_val, high_val, "INR"
                except Exception:
                    pass
            # Single value e.g. "94 K", "150000", "1.50 L / M", "60000 max", "135000/month", "80 K / M"
            m_sng = re.search(r'(\d[\d,\.]*)\s*(k|l|lakhs?|lpm)?(?:\s*/\s*m(?:onth)?)?', l, re.IGNORECASE)
            if m_sng:
                try:
                    val = convert_val(m_sng.group(1), m_sng.group(2))
                    if 10000 <= val <= 10000000:
                        return str(val), val, val, "INR"
                except Exception:
                    pass

    return None, None, None, None


def clean_notice_period(np_val: Any) -> str | None:
    """Sanitize notice period by removing legal confidentiality/email disclaimer leaks."""
    if not np_val:
        return None
    s = str(np_val).strip()
    if not s or s.lower() in ('none', 'null', 'not specified', 'n/a'):
        return None
    if re.search(r'(?i)\b(this e-?mail|confidential|attachment|intended recipient|privilege|unauthorized|dissemination|disclaimer)\b', s):
        return None
    return s


def clean_skills(skills_val: Any) -> Any:
    """Sanitize skills list by stripping recruiter signatures, addresses, and company legal disclaimers."""
    if not skills_val:
        return skills_val
    if isinstance(skills_val, list):
        cleaned = []
        for sk in skills_val:
            s_str = str(sk).strip()
            if not s_str or len(s_str) < 2:
                continue
            # Drop boilerplate prefixes/labels
            if re.match(r'(?i)^(?:must\s*have\s*[-–]?|must-have|highlighted)$', s_str):
                continue
            # Clean trailing/leading artifacts like " , Highlighted"
            s_str = re.sub(r'(?i)\s*,\s*highlighted\b', '', s_str).strip()
            if not s_str or len(s_str) < 2:
                continue
            # Only drop clear recruiter address/signature lines
            if re.search(r'(?i)(?:pvt\s*ltd|l&t\s+technology\s+services|technology\s+services\s+ltd|karnataka\s*\d*|india\b|iso\s*27001|bhuvanappa\s+layout|crystal\s+plaza|hosur\s+road|bengaluru|tech\s+park|s1\s+building|mob(?:ile)?:\s*\+?[\d\s]+|tel:\s*\+?\d|https?://|talent\s+acquisition\b|recruiter\b|hr\s+team|rahul\s+saha|vaishnavi\s+b|kallol\s+chakraborty|partner\s+engagement|lead-talent|@[a-z0-9\.\-_]+\.[a-z]{2,}|\b\+?91\s*\d{10}\b|engineering\s+the\s+change|^engineering$|^the\s+change$|^uses$|privacy\s+notice|privacy\s+policy|safeguard\s+your\s+privacy|confidential\s+or\s+privileged|intended\s+recipient|delete\s+it\s+from\s+your\s+system)', s_str):
                continue
            cleaned.append(s_str)
        return cleaned
    return skills_val


def extract_role_and_id(html_or_text: str) -> tuple[str | None, str | None]:
    """Extract client JD ID and real role name from table or body text."""
    if not html_or_text:
        return None, None

    from bs4 import BeautifulSoup
    from client_identity_validator import is_genuine_client_id
    client_id = None
    role = None

    if '<table' in html_or_text.lower():
        try:
            soup = BeautifulSoup(html_or_text, 'html.parser')
            for tbl in soup.find_all('table'):
                for tr in tbl.find_all('tr'):
                    cells = [c.get_text(strip=True) for c in tr.find_all(['td', 'th'])]
                    if len(cells) >= 2 and any(term in cells[0].lower() for term in ('request-id', 'req id', 'demand id', 'so id', 'so#')):
                        cand = cells[1].strip()
                        is_val, clean_val, _ = is_genuine_client_id(None, cand, context=html_or_text)
                        if is_val and clean_val:
                            client_id = clean_val
                            break
        except Exception:
            pass

    text = html_or_text
    if not client_id:
        from requirement_parser import extract_client_jd_id_from_text
        client_id = extract_client_jd_id_from_text("", text)

    if not role:
        m_prof = re.search(r'Proficiency in ([^\.\n\r]+)', text, re.IGNORECASE)
        if m_prof:
            role = m_prof.group(1).strip()

    if not role:
        m_comm = re.search(r'Comments for Suppliers:\s*([^R\n\r]+)', text, re.IGNORECASE)
        if m_comm:
            candidate = m_comm.group(1).strip()
            if len(candidate) > 3 and not candidate.lower().startswith('gcc'):
                role = candidate
            elif 'relevant' in candidate.lower():
                role = candidate.split('relevant')[0].strip()

    return client_id, role


def fetch_all_records(config: dict, include_archived: bool = False) -> List[Dict[str, Any]]:
    """
    Fetch requirements from all configured SQLite databases in read-only mode.

    Rule 2: Deduplicates by universal requirement identity (same client ID or same content).
    Rule 4: Default sort is by updated_at (or created_at) descending — most recently
            changed requirement at the top.
    Rule 3: Exposes field_change_history so the UI can show what changed.
    """
    global _CACHE_RECORDS
    if _CACHE_RECORDS is None or not isinstance(_CACHE_RECORDS, dict):
        _CACHE_RECORDS = {}
    now = time.time()
    db_paths = config.get("db_paths", [])
    cache_key = (include_archived, tuple(str(p) for p in db_paths))

    db_signature = tuple(
        (os.path.getmtime(p), os.path.getsize(p))
        for p in db_paths
        if os.path.exists(p)
    )
    cached = _CACHE_RECORDS.get(cache_key)
    if cached is not None:
        cached_time, cached_sig, cached_data = cached
        if (now - cached_time) < _CACHE_TTL and cached_sig == db_signature:
            if not _CACHE_RECORD_MAP or _CACHE_SIGNATURE != db_signature:
                _populate_record_cache_map(cached_data, config.get("id_normalization_rule", {}), db_signature)
            return cached_data

    from client_detector import detect_client
    from requirement_identity import clean_client_jd_id, compute_requirement_identity, normalize_client_key
    from metaforge_api import get_ist_req_date

    identity_metadata: Dict[str, Dict[str, Any]] = {}
    archived_backlog_refs: set = set()

    for db_path in db_paths:
        conn = _open_ro_connection(db_path)
        if not conn:
            continue
        try:
            try:
                cur = conn.execute(
                    "SELECT identity, times_seen, last_seen, first_seen, state FROM requirement_identity"
                )
                for r in cur.fetchall():
                    identity_metadata[str(r[0])] = {
                        "times_seen": r[1],
                        "last_seen": r[2],
                        "first_seen": r[3],
                        "state": r[4],
                    }
            except Exception:
                pass
            try:
                cur = conn.execute("SELECT identity, job_id, client_jd_id FROM archived_backlog")
                for r in cur.fetchall():
                    for v in r:
                        if v:
                            archived_backlog_refs.add(str(v).strip())
            except Exception:
                pass
        finally:
            conn.close()

    cutoff_dt = None
    cutoff_str = config.get("ingest_start_datetime")
    if cutoff_str:
        c_parsed = _parse_to_utc_dt(cutoff_str)
        if c_parsed != datetime.min.replace(tzinfo=timezone.utc):
            cutoff_dt = c_parsed

    # Unified multi-key deduplication structures (Rule 2, Rule 3, S1 & S5)
    unique_records: Dict[str, Dict[str, Any]] = {}
    identity_to_key: Dict[str, str] = {}
    client_jd_to_key: Dict[Tuple[str, str], str] = {}
    global_client_jd_to_key: Dict[str, str] = {}
    raw_id_to_key: Dict[str, str] = {}

    tables_to_query = ["metaforge_requirements", "client_requirements"]
    if include_archived:
        tables_to_query.append("archived_backlog")

    TABLE_PRIORITY = {
        "metaforge_requirements": 10,
        "client_requirements": 5,
        "archived_backlog": 2,
    }

    for db_path in db_paths:
        conn = _open_ro_connection(db_path)
        if not conn:
            continue
        try:
            for tbl in tables_to_query:
                try:
                    rows = conn.execute(f"SELECT * FROM {tbl} ORDER BY created_at ASC").fetchall()
                    tbl_priority = TABLE_PRIORITY.get(tbl, 1)
                    for row in rows:
                        try:
                            payload = json.loads(row["payload_json"])
                            row_keys = row.keys()

                            job_id_db = (
                                row["job_id"] if "job_id" in row_keys else
                                (row["client_jd_id"] if "client_jd_id" in row_keys else "")
                            )
                            job_id_raw = payload.get("job_id") or job_id_db or ""
                            created_at_db = row["created_at"] if "created_at" in row_keys else ""

                            updated_at_db = ""
                            if "updated_at" in row_keys:
                                updated_at_db = str(row["updated_at"] or "")

                            field_change_history = []
                            if "field_change_history" in row_keys and row["field_change_history"]:
                                try:
                                    field_change_history = json.loads(row["field_change_history"]) or []
                                except Exception:
                                    pass

                            prov = payload.get("_provenance") if isinstance(payload.get("_provenance"), dict) else {}
                            fa_raw = (
                                payload.get("receivedDateTime") or
                                prov.get("receivedDateTime") or
                                payload.get("first_arrival_at") or
                                prov.get("received_date_time") or
                                payload.get("received_date_time") or
                                payload.get("email_received_iso") or
                                payload.get("received_at") or
                                created_at_db or
                                payload.get("demand_received_date") or ""
                            )
                            if fa_raw and "T" in str(fa_raw):
                                payload["first_arrival_at"] = str(fa_raw)
                                payload["receivedDateTime"] = str(fa_raw)
                            arr_iso = fa_raw

                            # Dynamic field enrichment & sanitization (legacy mode only)
                            if not is_strict_field_mapping():
                                if not payload.get("monthly_budget"):
                                    body_txt = payload.get("bodyText") or payload.get("body") or payload.get("email_body") or ""
                                    ext_b, low_b, high_b, curr_b = parse_email_budget(body_txt)
                                    if ext_b:
                                        payload["monthly_budget"] = ext_b
                                        payload["monthly_budget_min"] = low_b
                                        payload["monthly_budget_max"] = high_b
                                        if not payload.get("budget_currency"):
                                            payload["budget_currency"] = curr_b or "INR"

                            old_np = payload.get("notice_period")
                            if old_np:
                                payload["notice_period"] = clean_notice_period(old_np)

                            # Sanitize budget / budget_text so raw email dumps are never displayed
                            for bk in ("budget", "budget_text"):
                                b_val = str(payload.get(bk) or "")
                                if b_val and (
                                    len(b_val) > 80
                                    or "\n" in b_val
                                    or any(w in b_val.lower() for w in ("dear", "kindly", "hello", "hi ", "regards", "candidate", "partner"))
                                ):
                                    if payload.get("monthly_budget"):
                                        mb = payload.get("monthly_budget")
                                        payload[bk] = f"{int(mb):,} / month" if isinstance(mb, (int, float)) else f"{mb} / month"
                                    elif payload.get("yearly_budget"):
                                        payload[bk] = f"{payload.get('yearly_budget')} LPA"
                                    else:
                                        payload[bk] = None

                            old_sk = payload.get("skills")
                            if old_sk:
                                payload["skills"] = clean_skills(old_sk)
                            old_mand = payload.get("mandatory_skills")
                            if old_mand:
                                payload["mandatory_skills"] = clean_skills(old_mand)

                            st = str(payload.get("job_status") or "").strip().lower()
                            if not is_strict_field_mapping():
                                if st not in ("open", "hold", "closed", "reopen", "active", "cancelled", "on hold", "on-hold") or len(st) > 20:
                                    payload["job_status"] = "open"
                                    payload["requirement_status"] = "open"

                            if not payload.get("internal_poc_email") and payload.get("to"):
                                to_v = str(payload.get("to")).strip()
                                if "@" in to_v:
                                    payload["internal_poc_email"] = to_v

                            sort_ts = arr_iso or created_at_db or updated_at_db or ""

                            client_jd = None
                            if "client_jd_id" in row_keys and row["client_jd_id"]:
                                client_jd = _clean_client_jd_id(row["client_jd_id"])
                            if not client_jd:
                                client_jd = _extract_real_client_jd_id(payload, job_id_raw)

                            cur_title = str(payload.get("job_title") or "").strip()
                            if not is_strict_field_mapping():
                                is_generic_title = cur_title.lower() in ("", "requirement", "requirement role", "none") or cur_title.lower().endswith(" requirement")
                                if not client_jd or is_generic_title:
                                    body_content = payload.get("bodyText") or payload.get("body") or payload.get("email_body") or ""
                                    ext_cid, ext_role = extract_role_and_id(body_content)
                                    if ext_cid and not client_jd:
                                        client_jd = ext_cid
                                        payload["client_jd_id"] = ext_cid
                                    if ext_role and is_generic_title:
                                        payload["job_title"] = ext_role

                            fmt_id = _format_internal_id(job_id_raw)

                            c_name = payload.get("requirement_from", "")
                            from_addr = (
                                payload.get("from") or
                                payload.get("client_poc") or
                                payload.get("client_lead_poc") or ""
                            )
                            if "idexcel" in str(c_name).lower() or "idexcel" in str(from_addr).lower():
                                subj = payload.get("subject") or payload.get("email_subject") or ""
                                body = payload.get("bodyText") or payload.get("body") or payload.get("email_body") or ""
                                cm = detect_client(subj, body, from_addr)
                                if cm:
                                    payload["requirement_from"] = cm.display_name
                                else:
                                    payload["requirement_from"] = "unresolved"

                            ident = row["identity"] if ("identity" in row_keys and row["identity"]) else None
                            if not ident:
                                ident = compute_requirement_identity(
                                    client=payload.get("requirement_from") or payload.get("client_key") or c_name,
                                    client_jd_id=client_jd,
                                    job_title=payload.get("job_title"),
                                    location=payload.get("location"),
                                    experience=payload.get("overall_experience") or payload.get("experience_level"),
                                    mandatory_skills=payload.get("mandatory_skills"),
                                )

                            # Backlog archival filter
                            if not include_archived:
                                if (
                                    (ident and ident in archived_backlog_refs)
                                    or (job_id_raw and job_id_raw in archived_backlog_refs)
                                    or (client_jd and client_jd in archived_backlog_refs)
                                ):
                                    continue

                            meta = identity_metadata.get(ident, {})

                            record = {
                                "raw_req_id": job_id_raw,
                                "fmt_id": fmt_id,
                                "client_jd_id": client_jd,
                                "identity": ident,
                                "times_seen": meta.get("times_seen", 1),
                                "last_seen": meta.get("last_seen") or arr_iso or created_at_db,
                                "first_seen": meta.get("first_seen") or arr_iso or created_at_db,
                                "first_arrival_at": arr_iso,
                                "arr_iso": arr_iso,
                                "updated_at": updated_at_db,
                                "sort_ts": sort_ts,
                                "source_db": os.path.basename(db_path),
                                "source_table": tbl,
                                "tbl_priority": tbl_priority,
                                "created_at": arr_iso or created_at_db,
                                "former_job_id": row["former_job_id"] if "former_job_id" in row_keys else payload.get("former_job_id"),
                                "payload": payload,
                                "review_fields": row["review_fields"] if "review_fields" in row_keys else None,
                                "field_change_history": field_change_history,
                                "legacy_unverified": bool(row["legacy_unverified"]) if "legacy_unverified" in row_keys else bool(payload.get("legacy_unverified", False)),
                                "mapping_version": row["mapping_version"] if "mapping_version" in row_keys else payload.get("mapping_version", 1),
                                "former_payload": row["former_payload"] if "former_payload" in row_keys else payload.get("former_payload"),
                            }

                            c_key = normalize_client_key(payload.get("requirement_from") or payload.get("client_key") or c_name or "")
                            record["client_key"] = c_key

                            # Unified multi-key deduplication (Rule 2, Rule 3, S1 & S5)
                            match_key = None
                            if ident and ident in identity_to_key:
                                match_key = identity_to_key[ident]
                            elif client_jd and (c_key, client_jd) in client_jd_to_key:
                                match_key = client_jd_to_key[(c_key, client_jd)]
                            elif client_jd and client_jd in global_client_jd_to_key:
                                match_key = global_client_jd_to_key[client_jd]
                            elif fmt_id and fmt_id in raw_id_to_key:
                                match_key = raw_id_to_key[fmt_id]
                            elif job_id_raw and job_id_raw in raw_id_to_key:
                                match_key = raw_id_to_key[job_id_raw]

                            if match_key is None:
                                assigned_key = ident or (f"{c_key}:{client_jd}" if client_jd else (fmt_id or job_id_raw))
                                unique_records[assigned_key] = record
                                if ident:
                                    identity_to_key[ident] = assigned_key
                                if client_jd:
                                    client_jd_to_key[(c_key, client_jd)] = assigned_key
                                    global_client_jd_to_key[client_jd] = assigned_key
                                if fmt_id:
                                    raw_id_to_key[fmt_id] = assigned_key
                                if job_id_raw:
                                    raw_id_to_key[job_id_raw] = assigned_key
                            else:
                                if ident:
                                    identity_to_key[ident] = match_key
                                if client_jd:
                                    client_jd_to_key[(c_key, client_jd)] = match_key
                                    global_client_jd_to_key[client_jd] = match_key
                                if fmt_id:
                                    raw_id_to_key[fmt_id] = match_key
                                if job_id_raw:
                                    raw_id_to_key[job_id_raw] = match_key

                                existing = unique_records[match_key]
                                orig_fa = existing.get("first_arrival_at") or record.get("first_arrival_at")
                                merged_hist = _merge_field_change_history(
                                    existing.get("field_change_history") or [],
                                    field_change_history,
                                )

                                # Fields to enrich in-place if changes occurred or new info provided
                                _enrich_fields = (
                                    "location", "overall_experience", "overall_experience_min", "overall_experience_max",
                                    "skills", "mandatory_skills", "work_mode", "monthly_budget", "yearly_budget",
                                    "budget_currency", "number_of_positions", "job_title", "notice_period", "employment_type"
                                )

                                if (tbl_priority > existing["tbl_priority"] or
                                        (tbl_priority == existing["tbl_priority"] and
                                         sort_ts > existing.get("sort_ts", ""))):
                                    record["field_change_history"] = merged_hist
                                    record["times_seen"] = max(record.get("times_seen", 1), existing.get("times_seen", 1))
                                    record["first_arrival_at"] = orig_fa
                                    record["arr_iso"] = orig_fa
                                    record["payload"]["first_arrival_at"] = orig_fa
                                    if not record.get("client_jd_id") and existing.get("client_jd_id"):
                                        record["client_jd_id"] = existing["client_jd_id"]
                                    if not record.get("fmt_id") and existing.get("fmt_id"):
                                        record["fmt_id"] = existing["fmt_id"]
                                    # Preserve specific client name over unresolved
                                    if str(record.get("requirement_from", "")).lower() in ("unresolved", "unknown", "") and existing.get("requirement_from"):
                                        record["requirement_from"] = existing["requirement_from"]
                                        record["client_key"] = existing.get("client_key", record.get("client_key"))
                                        record["payload"]["requirement_from"] = existing["requirement_from"]
                                    # Retain non-empty fields from existing if record is missing them
                                    p_rec = record.get("payload", {})
                                    p_ex = existing.get("payload", {})
                                    for fn in _enrich_fields:
                                        if not (p_rec.get(fn) or record.get(fn)) and (p_ex.get(fn) or existing.get(fn)):
                                            p_rec[fn] = p_ex.get(fn) or existing.get(fn)
                                            record[fn] = p_rec[fn]
                                    st_old = existing.get("payload", {}).get("job_status") or existing.get("payload", {}).get("requirement_status")
                                    if st_old and existing.get("sort_ts", "") > sort_ts:
                                        record["payload"]["job_status"] = st_old
                                        record["payload"]["requirement_status"] = st_old
                                        record["job_status"] = st_old
                                        record["requirement_status"] = st_old
                                    unique_records[match_key] = record
                                else:
                                    existing["field_change_history"] = merged_hist
                                    existing["times_seen"] = max(record.get("times_seen", 1), existing.get("times_seen", 1))
                                    existing["first_arrival_at"] = orig_fa
                                    existing["arr_iso"] = orig_fa
                                    existing["payload"]["first_arrival_at"] = orig_fa
                                    # In-place enrichment for existing requirement from incoming update
                                    p_ex = existing.get("payload", {})
                                    p_rec = record.get("payload", {})
                                    for fn in _enrich_fields:
                                        new_v = p_rec.get(fn) or record.get(fn)
                                        old_v = p_ex.get(fn) or existing.get(fn)
                                        if new_v and not old_v:
                                            p_ex[fn] = new_v
                                            existing[fn] = new_v
                                        elif new_v and old_v and sort_ts > existing.get("sort_ts", ""):
                                            if str(old_v).lower() in ("unresolved", "unknown", "none", "null", "—"):
                                                p_ex[fn] = new_v
                                                existing[fn] = new_v
                                    st_new = record.get("payload", {}).get("job_status") or record.get("payload", {}).get("requirement_status")
                                    if st_new and (sort_ts >= existing.get("sort_ts", "") or st_new.lower() in ("hold", "closed", "reopen")):
                                        existing["payload"]["job_status"] = st_new
                                        existing["payload"]["requirement_status"] = st_new
                                        existing["job_status"] = st_new
                                        existing["requirement_status"] = st_new
                                    if not existing.get("client_jd_id") and record.get("client_jd_id"):
                                        existing["client_jd_id"] = record["client_jd_id"]

                        except Exception:
                            continue
                except sqlite3.OperationalError:
                    pass
        finally:
            conn.close()

    # Assign stable unique internal IDs in chronological order of arrival
    merged_records: List[Dict[str, Any]] = list(unique_records.values())
    merged_records.sort(
        key=lambda r: (
            _parse_to_utc_dt(r.get("first_arrival_at") or r.get("arr_iso") or r.get("created_at") or ""),
            str(r.get("fmt_id") or r.get("raw_req_id") or "")
        )
    )

    # Pass 1: Record max sequence number for each day from established canonical stored IDs
    day_counters: Dict[str, int] = {}
    for r in merged_records:
        canonical_id = r.get("fmt_id") or _format_internal_id(r.get("raw_req_id") or "")
        if canonical_id:
            m = re.match(r"^(\d{4}[/-]\d{2}[/-]\d{2})[-_](\d+)$", canonical_id)
            if m:
                d_part = m.group(1).replace("-", "/")
                seq = int(m.group(2))
                day_counters[d_part] = max(day_counters.get(d_part, 0), seq)

    # Pass 2: Preserve established IDs and assign sequential IDs to unassigned records without shifting established ones
    records: List[Dict[str, Any]] = []

    for r in merged_records:
        canonical_id = r.get("fmt_id") or _format_internal_id(r.get("raw_req_id") or "")
        m = re.match(r"^(\d{4}[/-]\d{2}[/-]\d{2})[-_](\d+)$", canonical_id) if canonical_id else None

        if m:
            date_part = m.group(1).replace("-", "/")
            seq_num = int(m.group(2))
            seq_str = f"{seq_num:03d}" if seq_num < 1000 else f"{seq_num}"
            internal_id = f"{date_part}-{seq_str}"
        else:
            fa = r.get("first_arrival_at") or r.get("arr_iso") or r.get("created_at") or ""
            date_part = get_ist_req_date(fa)
            day_counters[date_part] = day_counters.get(date_part, 0) + 1
            seq_num = day_counters[date_part]
            seq_str = f"{seq_num:03d}" if seq_num < 1000 else f"{seq_num}"
            internal_id = f"{date_part}-{seq_str}"

        # Preserve former_job_id if internal_id changed
        if r.get("raw_req_id") and r.get("raw_req_id") != internal_id and not r.get("former_job_id"):
            r["former_job_id"] = r.get("raw_req_id")

        r["req_id"] = internal_id
        r["req_seq"] = seq_num

        # Ensure payload has canonical IDs and status synced
        p = r.get("payload", {})
        p["req_id"] = internal_id
        if r.get("client_jd_id"):
            p["client_jd_id"] = r["client_jd_id"]
        status_val = p.get("job_status") or p.get("requirement_status") or r.get("job_status") or r.get("requirement_status") or "open"
        p["job_status"] = status_val
        p["requirement_status"] = status_val
        r["job_status"] = status_val
        r["requirement_status"] = status_val

        records.append(r)

    # Requirement order should always be in descending order (newest requirement on top)
    def _sort_key(r: Dict[str, Any]) -> tuple:
        req_id = str(r.get("req_id") or r.get("raw_req_id") or "").strip()
        m = re.match(r"^(\d{4}[/-]\d{2}[/-]\d{2})[-_](\d+)$", req_id)
        if m:
            req_date = m.group(1).replace("-", "/")
            req_seq = int(m.group(2))
        else:
            req_date = ""
            req_seq = 0

        fa = str(r.get("first_arrival_at") or r.get("arr_iso") or "").strip()
        dt_obj = _parse_to_utc_dt(fa)
        row_id = str(r.get("raw_req_id") or req_id)
        return (req_date, req_seq, dt_obj, row_id)

    records.sort(key=_sort_key, reverse=True)
    _CACHE_RECORDS[cache_key] = (now, db_signature, records)
    _populate_record_cache_map(records, config.get("id_normalization_rule", {}), db_signature)
    return records


def fetch_status_history(config: dict, target_id: str) -> List[Dict[str, Any]]:
    rule = config.get("id_normalization_rule", {})
    target_norm = normalize_id(target_id, rule)
    if not target_norm:
        return []

    history = []
    db_paths = config.get("db_paths", [])
    for db_path in db_paths:
        if not os.path.exists(db_path):
            continue
        try:
            conn = sqlite3.connect(f"file:{os.path.abspath(db_path)}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT id, requirement_id, from_status, to_status, changed_at, source_email_id, changed_by "
                "FROM status_history WHERE requirement_id = ? ORDER BY id ASC",
                (target_norm,),
            ).fetchall()
            for r in rows:
                history.append(dict(r))
            conn.close()
            if history:
                break
        except Exception:
            continue
    return history


def fetch_field_change_history(config: dict, target_id: str) -> List[Dict[str, Any]]:
    """
    Fetch the field-level change history (Rule 3 para 6) for a requirement.
    Returns a list of {changed_at, source_email_id, changes: {field: {old, new}}} dicts.
    """
    rule = config.get("id_normalization_rule", {})
    target_norm = normalize_id(target_id, rule)
    if not target_norm:
        return []

    db_paths = config.get("db_paths", [])
    all_hist: List[Dict[str, Any]] = []

    for db_path in db_paths:
        if not os.path.exists(db_path):
            continue
        try:
            conn = sqlite3.connect(f"file:{os.path.abspath(db_path)}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row

            for tbl, id_col in [
                ("client_requirements", "client_jd_id"),
                ("metaforge_requirements", "client_jd_id"),
            ]:
                try:
                    row = conn.execute(
                        f"SELECT field_change_history FROM {tbl} WHERE {id_col} = ? LIMIT 1",
                        (target_norm,),
                    ).fetchone()
                    if row and row["field_change_history"]:
                        hist = json.loads(row["field_change_history"]) or []
                        all_hist = _merge_field_change_history(all_hist, hist)
                except sqlite3.OperationalError:
                    pass

            conn.close()
        except Exception as err:
            _LOG.error("Failed to fetch field change history from %s: %s", db_path, err)

    # Sort chronologically
    all_hist.sort(key=lambda x: x.get("changed_at", ""))
    return all_hist


def fetch_jd_versions(config: dict, target_id: str) -> List[Dict[str, Any]]:
    """
    Fetch historical versions of the job description for target_id.
    Queries the jd_versions table from configured databases.
    """
    rule = config.get("id_normalization_rule", {})
    target_norm = normalize_id(target_id, rule)
    if not target_norm:
        return []

    db_paths = config.get("db_paths", [])
    versions: List[Dict[str, Any]] = []
    seen_vers = set()

    for db_path in db_paths:
        if not os.path.exists(db_path):
            continue
        try:
            conn = sqlite3.connect(f"file:{os.path.abspath(db_path)}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            try:
                cur = conn.execute(
                    """SELECT version_number, job_description, changes_json, source_email_id, created_at
                       FROM jd_versions
                       WHERE requirement_id = ? OR client_jd_id = ?
                       ORDER BY version_number ASC""",
                    (target_id, target_norm),
                )
                for r in cur.fetchall():
                    vn = r["version_number"]
                    if vn not in seen_vers:
                        seen_vers.add(vn)
                        changes = {}
                        if r["changes_json"]:
                            try:
                                changes = json.loads(r["changes_json"])
                            except Exception:
                                changes = {}
                        versions.append({
                            "version": vn,
                            "job_description": r["job_description"] or "",
                            "changes": changes,
                            "source_email_id": r["source_email_id"] or "",
                            "saved_at": r["created_at"] or "",
                        })
            except sqlite3.OperationalError:
                pass
            conn.close()
        except Exception as err:
            _LOG.error("Failed to fetch jd_versions from %s: %s", db_path, err)

    versions.sort(key=lambda v: v.get("version", 0))
    return versions


def update_status_in_db(config: dict, target_id: str, new_status: str, changed_by: str = "USER") -> bool:
    """
    Update requirement status from the UI.

    Rule 3: Record the status change in field_change_history and append to status_history.
    Rule 4: Refresh updated_at so the record rises to the top of the list immediately.

    Updates BOTH databases:
      - client_requirements in processed_messages.db  (primary store)
      - metaforge_requirements in metaforge_requirements.db (secondary store)
    """
    rule = config.get("id_normalization_rule", {})
    target_norm = normalize_id(target_id, rule)
    if not target_norm:
        return False

    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).isoformat()
    new_st = new_status.strip().lower()

    db_paths = config.get("db_paths", [])
    updated = False

    for db_path in db_paths:
        if not os.path.exists(db_path):
            continue
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row

            # ── Ensure tables exist ──────────────────────────────────────────
            conn.execute(
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

            old_status = "open"
            did_update_any = False

            # ── 1. Update client_requirements (primary, Rule 3 + Rule 4) ────
            try:
                cr_row = conn.execute(
                    "SELECT client_jd_id, status, payload_json, field_change_history "
                    "FROM client_requirements WHERE client_jd_id = ? LIMIT 1",
                    (target_norm,),
                ).fetchone()
                if cr_row:
                    old_status = str(cr_row["status"] or "open").lower()
                    if old_status != new_st:
                        # Rule 3: Update payload json field
                        payload = json.loads(cr_row["payload_json"] or "{}")
                        payload["job_status"] = new_st

                        # Rule 3 para 6: Append to field_change_history
                        try:
                            fch = json.loads(cr_row["field_change_history"] or "[]") or []
                        except Exception:
                            fch = []
                        fch.append({
                            "changed_at": ts,
                            "source_email_id": "",
                            "changes": {
                                "job_status": {"old": old_status, "new": new_st}
                            },
                        })

                        # Rule 4: Refresh updated_at
                        conn.execute(
                            """UPDATE client_requirements
                               SET status = ?, payload_json = ?, updated_at = ?,
                                   field_change_history = ?
                               WHERE client_jd_id = ?""",
                            (
                                new_st,
                                json.dumps(payload, ensure_ascii=False),
                                ts,
                                json.dumps(fch, ensure_ascii=False),
                                target_norm,
                            ),
                        )
                        did_update_any = True
                        _LOG.info(
                            "UI status update: client_requirements client_jd_id=%s %s -> %s",
                            target_norm, old_status, new_st,
                        )
            except sqlite3.OperationalError:
                pass  # Table may not exist in this DB file

            # ── 2. Update metaforge_requirements (secondary) ─────────────────
            try:
                mf_row = conn.execute(
                    "SELECT job_id, payload_json FROM metaforge_requirements WHERE job_id = ? LIMIT 1",
                    (target_norm,),
                ).fetchone()
                if not mf_row:
                    # Scan by client_jd_id
                    rows = conn.execute(
                        "SELECT job_id, payload_json FROM metaforge_requirements"
                    ).fetchall()
                    for r in rows:
                        try:
                            p = json.loads(r["payload_json"])
                            if p.get("client_jd_id") == target_norm or p.get("job_id") == target_norm:
                                mf_row = r
                                break
                        except Exception:
                            continue

                if mf_row:
                    payload_mf = json.loads(mf_row["payload_json"] or "{}")
                    old_status_mf = str(payload_mf.get("job_status") or "open").lower()
                    if old_status_mf != new_st:
                        payload_mf["job_status"] = new_st
                        conn.execute(
                            "UPDATE metaforge_requirements SET payload_json = ?, updated_at = ? WHERE job_id = ?",
                            (json.dumps(payload_mf, ensure_ascii=False), ts, mf_row["job_id"]),
                        )
                        if not did_update_any:
                            old_status = old_status_mf
                        did_update_any = True
                        _LOG.info(
                            "UI status update: metaforge_requirements job_id=%s %s -> %s",
                            mf_row["job_id"], old_status_mf, new_st,
                        )
            except sqlite3.OperationalError:
                pass  # Table may not exist in this DB file

            # ── 3. Always write status_history entry (Rule 3 audit trail) ───
            if did_update_any or True:  # Always record the event
                try:
                    conn.execute(
                        "INSERT INTO status_history "
                        "(requirement_id, from_status, to_status, changed_at, source_email_id, changed_by) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (target_norm, old_status, new_st, ts, "", changed_by),
                    )
                except Exception:
                    pass

            conn.commit()
            conn.close()
            updated = updated or did_update_any

        except Exception as err:
            _LOG.error("Failed to update status in DB %s: %s", db_path, err)

    if updated:
        global _CACHE_RECORDS, _CACHE_RECORD_MAP
        _CACHE_RECORDS = None
        if isinstance(_CACHE_RECORD_MAP, dict):
            _CACHE_RECORD_MAP.clear()

    return updated


def fetch_single_record_direct(config: dict, target_id: str, target_norm: str, target_fmt: str | None, rule: dict) -> Optional[Dict[str, Any]]:
    """Direct, targeted single-requirement lookup without scanning or reloading all emails."""
    candidates = [target_id]
    if target_norm and target_norm not in candidates:
        candidates.append(target_norm)
    if target_fmt and target_fmt not in candidates:
        candidates.append(target_fmt)

    db_paths = config.get("db_paths", [])
    from requirement_identity import compute_requirement_identity, normalize_client_key

    for db_path in db_paths:
        if not os.path.exists(db_path):
            continue
        conn = _open_ro_connection(db_path)
        if not conn:
            continue
        try:
            for tbl, tbl_priority in [
                ("metaforge_requirements", 10),
                ("client_requirements", 5),
                ("pending_reviews", 3),
                ("requirement_memory", 1),
            ]:
                try:
                    col_info = [r[1] for r in conn.execute(f"PRAGMA table_info({tbl})").fetchall()]
                    if not col_info:
                        continue
                    # Tier A: Direct match on active primary keys / client_jd_id / identity
                    primary_clauses = []
                    primary_params = []
                    for c in candidates:
                        if "job_id" in col_info:
                            primary_clauses.append("job_id = ?")
                            primary_params.append(c)
                        if "client_jd_id" in col_info:
                            primary_clauses.append("client_jd_id = ?")
                            primary_params.append(c)
                        if "identity" in col_info:
                            primary_clauses.append("identity = ?")
                            primary_params.append(c)

                    row = None
                    if primary_clauses:
                        q = f"SELECT * FROM {tbl} WHERE (" + " OR ".join(primary_clauses) + ") LIMIT 1"
                        row = conn.execute(q, primary_params).fetchone()

                    # Tier B: Fallback match on former_job_id ONLY if no active record matched
                    if not row and "former_job_id" in col_info:
                        former_clauses = ["former_job_id = ?" for _ in candidates]
                        q = f"SELECT * FROM {tbl} WHERE (" + " OR ".join(former_clauses) + ") LIMIT 1"
                        row = conn.execute(q, candidates).fetchone()

                    if row:
                            payload = json.loads(row["payload_json"])

                            # Sanitize budget / budget_text so raw email dumps are never displayed
                            for bk in ("budget", "budget_text"):
                                b_val = str(payload.get(bk) or "")
                                if b_val and (
                                    len(b_val) > 80
                                    or "\n" in b_val
                                    or any(w in b_val.lower() for w in ("dear", "kindly", "hello", "hi ", "regards", "candidate", "partner"))
                                ):
                                    if payload.get("monthly_budget"):
                                        mb = payload.get("monthly_budget")
                                        payload[bk] = f"{int(mb):,} / month" if isinstance(mb, (int, float)) else f"{mb} / month"
                                    elif payload.get("yearly_budget"):
                                        payload[bk] = f"{payload.get('yearly_budget')} LPA"
                                    else:
                                        payload[bk] = None
                            row_keys = row.keys()
                            job_id_db = (
                                row["job_id"] if "job_id" in row_keys else
                                (row["client_jd_id"] if "client_jd_id" in row_keys else "")
                            )
                            job_id_raw = payload.get("job_id") or job_id_db or ""
                            created_at_db = row["created_at"] if "created_at" in row_keys else ""
                            updated_at_db = str(row["updated_at"] or "") if "updated_at" in row_keys else ""

                            field_change_history = []
                            if "field_change_history" in row_keys and row["field_change_history"]:
                                try:
                                    field_change_history = json.loads(row["field_change_history"]) or []
                                except Exception:
                                    pass

                            prov = payload.get("_provenance") if isinstance(payload.get("_provenance"), dict) else {}
                            fa_raw = (
                                payload.get("first_arrival_at") or
                                prov.get("received_date_time") or
                                prov.get("receivedDateTime") or
                                payload.get("received_date_time") or
                                payload.get("receivedDateTime") or
                                payload.get("email_received_iso") or
                                created_at_db or ""
                            )
                            arr_iso = fa_raw
                            sort_ts = arr_iso or created_at_db or updated_at_db or ""

                            client_jd = None
                            if "client_jd_id" in row_keys and row["client_jd_id"]:
                                client_jd = _clean_client_jd_id(row["client_jd_id"])
                            if not client_jd:
                                client_jd = _extract_real_client_jd_id(payload, job_id_raw)

                            fmt_id = _format_internal_id(job_id_raw)
                            ident = row["identity"] if ("identity" in row_keys and row["identity"]) else None
                            if not ident:
                                ident = compute_requirement_identity(
                                    client=payload.get("requirement_from") or payload.get("client_key") or "",
                                    client_jd_id=client_jd,
                                    job_title=payload.get("job_title"),
                                    location=payload.get("location"),
                                    experience=payload.get("overall_experience") or payload.get("experience_level"),
                                    mandatory_skills=payload.get("mandatory_skills"),
                                )

                            meta = {}
                            try:
                                cur_m = conn.execute(
                                    "SELECT times_seen, last_seen, first_seen, state FROM requirement_identity WHERE identity = ?",
                                    (ident,),
                                ).fetchone()
                                if cur_m:
                                    meta = {
                                        "times_seen": cur_m[0],
                                        "last_seen": cur_m[1],
                                        "first_seen": cur_m[2],
                                        "state": cur_m[3],
                                    }
                            except Exception:
                                pass

                            canonical_id = fmt_id or _format_internal_id(job_id_raw or "")
                            m = re.match(r"^(\d{4}[/-]\d{2}[/-]\d{2})[-_](\d+)$", canonical_id) if canonical_id else None
                            if m:
                                date_part = m.group(1).replace("-", "/")
                                seq_num = int(m.group(2))
                                seq_str = f"{seq_num:03d}" if seq_num < 1000 else f"{seq_num}"
                                internal_id = f"{date_part}-{seq_str}"
                            else:
                                internal_id = canonical_id or job_id_raw
                                seq_num = 0

                            status_val = (
                                payload.get("job_status")
                                or payload.get("requirement_status")
                                or (row["status"] if "status" in row_keys else "open")
                            )
                            payload["job_status"] = status_val
                            payload["requirement_status"] = status_val
                            payload["req_id"] = internal_id
                            if client_jd:
                                payload["client_jd_id"] = client_jd

                            rec = {
                                "raw_req_id": job_id_raw,
                                "fmt_id": fmt_id,
                                "client_jd_id": client_jd,
                                "identity": ident,
                                "times_seen": meta.get("times_seen", 1),
                                "last_seen": meta.get("last_seen") or arr_iso or created_at_db,
                                "first_seen": meta.get("first_seen") or arr_iso or created_at_db,
                                "first_arrival_at": arr_iso,
                                "arr_iso": arr_iso,
                                "updated_at": updated_at_db,
                                "sort_ts": sort_ts,
                                "source_db": os.path.basename(db_path),
                                "source_table": tbl,
                                "tbl_priority": tbl_priority,
                                "created_at": arr_iso or created_at_db,
                                "former_job_id": row["former_job_id"] if "former_job_id" in row_keys else payload.get("former_job_id"),
                                "payload": payload,
                                "review_fields": row["review_fields"] if "review_fields" in row_keys else None,
                                "field_change_history": field_change_history,
                                "legacy_unverified": bool(row["legacy_unverified"]) if "legacy_unverified" in row_keys else bool(payload.get("legacy_unverified", False)),
                                "mapping_version": row["mapping_version"] if "mapping_version" in row_keys else payload.get("mapping_version", 1),
                                "former_payload": row["former_payload"] if "former_payload" in row_keys else payload.get("former_payload"),
                                "client_key": normalize_client_key(payload.get("requirement_from") or payload.get("client_key") or ""),
                                "job_status": status_val,
                                "requirement_status": status_val,
                                "req_id": internal_id,
                                "req_seq": seq_num,
                            }
                            rec["status_history"] = fetch_status_history(config, target_norm) or fetch_status_history(config, internal_id)
                            rec["field_change_history"] = fetch_field_change_history(config, target_norm) or field_change_history
                            rec["version_history"] = payload.get("version_history") or fetch_jd_versions(config, target_norm) or fetch_jd_versions(config, internal_id) or []
                            return rec
                except sqlite3.OperationalError:
                    pass
        finally:
            conn.close()
    return None


def get_requirement(config: dict, target_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve details for a specific requirement ID, including full history.
    
    Fast multi-tier lookup:
      1. Check in-memory index map (_CACHE_RECORD_MAP) in O(1) time (< 0.0001s).
      2. If not cached, query targeted SQLite row directly via fetch_single_record_direct (< 0.05s).
      3. Only falls back to full fetch_all_records if direct query returns nothing.
    """
    rule = config.get("id_normalization_rule", {})
    target_norm = normalize_id(target_id, rule)
    if not target_norm:
        return None

    target_fmt = _format_internal_id(target_id)

    # Tier 1: Instant In-Memory Cache Lookup
    global _CACHE_RECORD_MAP, _CACHE_SIGNATURE
    db_paths = config.get("db_paths", [])
    current_sig = tuple(
        (os.path.getmtime(p), os.path.getsize(p))
        for p in db_paths
        if os.path.exists(p)
    )
    if _CACHE_RECORD_MAP and _CACHE_SIGNATURE == current_sig:
        matched = (
            _CACHE_RECORD_MAP.get(target_id)
            or _CACHE_RECORD_MAP.get(target_norm)
            or (_CACHE_RECORD_MAP.get(target_fmt) if target_fmt else None)
        )
        if matched:
            res = dict(matched)
            res["status_history"] = fetch_status_history(config, target_norm)
            if not res["status_history"] and matched.get("raw_req_id"):
                res["status_history"] = fetch_status_history(config, matched["raw_req_id"])
            if not res.get("field_change_history"):
                res["field_change_history"] = fetch_field_change_history(config, target_norm)
            if not res.get("field_change_history") and matched.get("client_jd_id"):
                res["field_change_history"] = fetch_field_change_history(config, matched["client_jd_id"])
            if not res.get("version_history"):
                res["version_history"] = (
                    (res.get("payload") or {}).get("version_history")
                    or fetch_jd_versions(config, target_norm)
                    or (fetch_jd_versions(config, matched["raw_req_id"]) if matched.get("raw_req_id") else [])
                    or []
                )
            return res

    # Tier 2: Targeted Direct SQLite Query (Loads ONLY this single requirement in ~0.02s)
    direct_rec = fetch_single_record_direct(config, target_id, target_norm, target_fmt, rule)
    if direct_rec:
        if isinstance(_CACHE_RECORD_MAP, dict):
            _CACHE_SIGNATURE = current_sig
            _CACHE_RECORD_MAP[target_id] = direct_rec
            _CACHE_RECORD_MAP[target_norm] = direct_rec
            if target_fmt:
                _CACHE_RECORD_MAP[target_fmt] = direct_rec
            if direct_rec.get("identity"):
                _CACHE_RECORD_MAP[direct_rec["identity"]] = direct_rec
            if direct_rec.get("client_jd_id"):
                _CACHE_RECORD_MAP[direct_rec["client_jd_id"]] = direct_rec
            if direct_rec.get("req_id"):
                _CACHE_RECORD_MAP[direct_rec["req_id"]] = direct_rec
        return direct_rec

    # Tier 3: Safety fallback to fetch_all_records only if direct lookup didn't find the record
    records = fetch_all_records(config, include_archived=True)
    matched = None

    # Tier 0: exact match on universal requirement identity
    for rec in records:
        if rec.get("identity") == target_id:
            matched = rec
            break

    # Tier 1: exact match on immutable stored job_id / raw_req_id / fmt_id
    if not matched:
        for rec in records:
            raw_id = rec.get("raw_req_id") or ""
            fmt_id = rec.get("fmt_id") or ""
            if raw_id and (target_norm == raw_id or normalize_id(raw_id, rule) == target_norm or (target_fmt and raw_id == target_fmt)):
                matched = rec
                break
            if fmt_id and (target_norm == fmt_id or normalize_id(fmt_id, rule) == target_norm or (target_fmt and fmt_id == target_fmt)):
                matched = rec
                break

    # Tier 2: exact match on genuine client_jd_id
    if not matched:
        for rec in records:
            cjd = rec.get("client_jd_id") or rec.get("payload", {}).get("client_jd_id") or ""
            if cjd and (target_norm == cjd or normalize_id(cjd, rule) == target_norm):
                matched = rec
                break

    # Tier 3: match on assigned display req_id
    if not matched:
        for rec in records:
            rid = rec.get("req_id") or ""
            if rid and (target_norm == rid or normalize_id(rid, rule) == target_norm or (target_fmt and rid == target_fmt)):
                matched = rec
                break

    # Tier 4: match on former_job_id for renumbered records (R7)
    if not matched:
        for rec in records:
            fid = rec.get("former_job_id") or rec.get("payload", {}).get("former_job_id") or ""
            if fid and (target_norm == fid or normalize_id(fid, rule) == target_norm or (target_fmt and fid == target_fmt)):
                matched = rec
                break

    if matched:
        res = dict(matched)
        res["status_history"] = fetch_status_history(config, target_norm)
        if not res["status_history"] and matched.get("raw_req_id"):
            res["status_history"] = fetch_status_history(config, matched["raw_req_id"])
        if not res.get("field_change_history"):
            res["field_change_history"] = fetch_field_change_history(config, target_norm)
        if not res.get("field_change_history") and matched.get("client_jd_id"):
            res["field_change_history"] = fetch_field_change_history(config, matched["client_jd_id"])
        if not res.get("version_history"):
            res["version_history"] = (
                (res.get("payload") or {}).get("version_history")
                or fetch_jd_versions(config, target_norm)
                or (fetch_jd_versions(config, matched["raw_req_id"]) if matched.get("raw_req_id") else [])
                or []
            )
        return res

    return None


def get_req_id_suggestions(config: dict, prefix: str, limit: int = 15) -> List[str]:
    """Retrieve autocomplete suggestion list for requirement IDs."""
    rule = config.get("id_normalization_rule", {})
    pfx_norm = normalize_id(prefix, rule)

    # 1. Use memory cache if available
    global _CACHE_RECORDS
    cached = None
    if isinstance(_CACHE_RECORDS, dict):
        for k, v in _CACHE_RECORDS.items():
            if v and len(v) == 3:
                cached = v[2]
                break
    if cached:
        suggestions = []
        for rec in cached:
            rid = rec["req_id"]
            if not pfx_norm or pfx_norm in rid:
                suggestions.append(rid)
                if len(suggestions) >= limit:
                    break
        return suggestions

    # 2. Direct fast indexed query on metaforge_requirements without scanning all payloads
    suggestions = []
    db_paths = config.get("db_paths", [])
    for db_path in db_paths:
        if not os.path.exists(db_path):
            continue
        try:
            conn = _open_ro_connection(db_path)
            if not conn:
                continue
            rows = conn.execute(
                "SELECT job_id FROM metaforge_requirements WHERE job_id LIKE ? ORDER BY job_id DESC LIMIT ?",
                (f"%{prefix}%", limit),
            ).fetchall()
            for r in rows:
                if r["job_id"] and r["job_id"] not in suggestions:
                    suggestions.append(r["job_id"])
                    if len(suggestions) >= limit:
                        break
            conn.close()
            if suggestions:
                break
        except Exception:
            pass
    return suggestions
