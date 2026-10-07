"""
A6 Dry Run Analysis Script (Read-Only).
Re-runs the new strict mapping pipeline on stored records in memory.
Computes per-field diffs (old value, new value, reason) and summary statistics.
Does NOT modify any database tables.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
from collections import defaultdict
from typing import Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import is_placeholder, is_strict_field_mapping, lpa_implies_inr
from client_identity_validator import is_genuine_client_id
from strict_validator import validate_requirement_before_save, compute_requirement_confidence
from requirement_segmenter import strip_all_exclusion_zones

CANONICAL_FIELDS = (
    "job_title",
    "client_jd_id",
    "number_of_positions",
    "experience_level",
    "employment_type",
    "work_mode",
    "location",
    "overall_experience",
    "notice_period",
    "mandatory_skills",
    "skills",
    "yearly_budget",
    "yearly_budget_min",
    "yearly_budget_max",
    "monthly_budget",
    "monthly_budget_min",
    "monthly_budget_max",
    "budget_currency",
    "priority",
    "type_of_demand",
    "confidence",
)


def normalize_val(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, list):
        cv = [str(x).strip() for x in v if x is not None and not is_placeholder(x)]
        return cv if cv else None
    if is_placeholder(v):
        return None
    s = str(v).strip()
    if s == "":
        return None
    return s


def run_dry_run():
    mf_db_path = "data/metaforge_requirements.db"
    proc_db_path = "data/processed_messages.db"

    conn_mf = sqlite3.connect(mf_db_path)
    conn_mf.row_factory = sqlite3.Row
    mf_rows = conn_mf.execute("SELECT * FROM metaforge_requirements").fetchall()

    conn_proc = sqlite3.connect(proc_db_path)
    conn_proc.row_factory = sqlite3.Row
    mem_rows = conn_proc.execute("SELECT * FROM requirement_memory").fetchall()

    # Index requirement_memory by source_graph_id or job_title_norm
    memory_by_gid = defaultdict(list)
    for m in mem_rows:
        gid = m["source_graph_id"]
        if gid:
            memory_by_gid[gid].append(m)

    total_rows = len(mf_rows)
    recoverable_count = 0
    legacy_unverified_count = 0

    field_nulled_counts = defaultdict(int)
    field_changed_counts = defaultdict(int)
    field_unchanged_counts = defaultdict(int)
    sample_diffs = defaultdict(list)

    row_summaries = []

    for row in mf_rows:
        job_id = row["job_id"]
        raw_payload_str = row["payload_json"]
        try:
            payload = json.loads(raw_payload_str) if raw_payload_str else {}
        except Exception:
            payload = {}

        # Look for recoverable source text
        body_source = (
            payload.get("bodyText")
            or payload.get("body")
            or payload.get("email_body")
            or ""
        )
        if isinstance(body_source, dict):
            body_source = body_source.get("content", "")

        prov = payload.get("_provenance") or {}
        gid = (
            payload.get("graphMessageId")
            or payload.get("id")
            or (prov.get("graph_id") if isinstance(prov, dict) else None)
        )

        mem_source = ""
        if gid and gid in memory_by_gid:
            for mr in memory_by_gid[gid]:
                try:
                    mp = json.loads(mr["payload_json"])
                    mb = mp.get("bodyText") or mp.get("body") or mp.get("email_body") or ""
                    if mb:
                        mem_source = mb
                        break
                except Exception:
                    pass

        effective_source = body_source or mem_source

        if not effective_source or len(effective_source.strip()) < 10:
            legacy_unverified_count += 1
            is_legacy = True
            effective_source = ""
        else:
            recoverable_count += 1
            is_legacy = False

        # Simulate running new pipeline in memory
        new_payload = dict(payload)
        client_name = new_payload.get("requirement_from") or new_payload.get("client_key")

        # Apply strict pre-save validation in memory
        sanitized, should_review, reason = validate_requirement_before_save(
            new_payload,
            block_text=effective_source,
            client=client_name,
        )

        # Compare canonical fields
        row_diffs = []
        for field in CANONICAL_FIELDS:
            old_raw = payload.get(field)
            new_raw = sanitized.get(field)

            old_norm = normalize_val(old_raw)
            new_norm = normalize_val(new_raw)

            # Check special derivations
            field_reason = None
            if old_norm is not None and new_norm is None:
                field_nulled_counts[field] += 1
                if is_placeholder(old_raw):
                    field_reason = "placeholder_removed"
                elif field == "priority" and old_raw in ("Low", "LOW") and "hold" in str(payload.get("job_status", "")).lower():
                    field_reason = "hold_derived_priority_removed"
                elif field == "type_of_demand" and not is_legacy:
                    field_reason = "inferred_type_of_demand_removed"
                elif field == "experience_level" and not is_legacy:
                    field_reason = "derived_experience_level_removed"
                elif field == "budget_currency" and not lpa_implies_inr():
                    field_reason = "assumed_inr_removed"
                elif field == "client_jd_id":
                    field_reason = "invalid_or_budget_range_id_removed"
                elif field in ("mandatory_skills", "skills"):
                    field_reason = "title_or_noise_skill_removed"
                else:
                    field_reason = "no_evidence_or_placeholder_removed"

                row_diffs.append((field, old_raw, None, field_reason))
                if len(sample_diffs[field]) < 3:
                    sample_diffs[field].append((job_id, old_raw, None, field_reason))

            elif old_norm != new_norm:
                field_changed_counts[field] += 1
                field_reason = "value_sanitized_or_corrected"
                row_diffs.append((field, old_raw, new_raw, field_reason))
                if len(sample_diffs[field]) < 3:
                    sample_diffs[field].append((job_id, old_raw, new_raw, field_reason))
            else:
                field_unchanged_counts[field] += 1

        if row_diffs:
            row_summaries.append({
                "job_id": job_id,
                "is_legacy_unverified": is_legacy,
                "diff_count": len(row_diffs),
                "diffs": row_diffs,
            })

    conn_mf.close()
    conn_proc.close()

    return {
        "total_rows": total_rows,
        "recoverable_count": recoverable_count,
        "legacy_unverified_count": legacy_unverified_count,
        "field_nulled_counts": dict(field_nulled_counts),
        "field_changed_counts": dict(field_changed_counts),
        "field_unchanged_counts": dict(field_unchanged_counts),
        "sample_diffs": dict(sample_diffs),
        "total_rows_with_diffs": len(row_summaries),
    }


if __name__ == "__main__":
    res = run_dry_run()
    print("=" * 80)
    print("A6 DRY RUN REPAIR REPORT (READ-ONLY, NO DATA MODIFIED)")
    print("=" * 80)
    print(f"Total Stored Requirements: {res['total_rows']}")
    print(f"  - Recoverable source found: {res['recoverable_count']}")
    print(f"  - Flagged legacy_unverified (no recoverable source): {res['legacy_unverified_count']}")
    print(f"Total rows that would have changes: {res['total_rows_with_diffs']} / {res['total_rows']}")
    print("\n" + "-" * 80)
    print("PER-FIELD IMPACT COUNTS (Values becoming NULL or Changing):")
    print(f"{'FIELD':<24} | {'BECOMING NULL':<15} | {'CHANGING VALUE':<16} | {'UNCHANGED':<12}")
    print("-" * 80)
    for f in CANONICAL_FIELDS:
        nulled = res["field_nulled_counts"].get(f, 0)
        changed = res["field_changed_counts"].get(f, 0)
        unchanged = res["field_unchanged_counts"].get(f, 0)
        print(f"{f:<24} | {nulled:<15} | {changed:<16} | {unchanged:<12}")

    print("\n" + "-" * 80)
    print("SAMPLE FIELD DIFFS (Old Value -> New Value [Reason]):")
    print("-" * 80)
    for f, samples in res["sample_diffs"].items():
        print(f"\n[{f}]")
        for jid, old_v, new_v, reason in samples:
            print(f"  - Row {jid}: {old_v!r} -> {new_v!r} (reason: {reason})")
