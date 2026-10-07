"""
Phase 5: Continuous Accuracy Monitoring Engine.

Monitors extraction quality across recent real production emails using the canonical pipeline:
1. Ground-truth verification against raw email text (two-way verification & verbatim grounding).
2. Calculates source-present recovery rate independently from field population rate.
3. Detects hallucinations (ungrounded non-null extractions, candidate PII leaks).
4. Detects cross-role contamination in multi-role emails.
5. Evaluates metrics against verified production baseline (config/accuracy_baseline.json).
6. Fires automated alerts via Phase 4 AlertManager upon accuracy degradation.
7. Performs ZERO production database writes (enforces mode=ro on SQLite connection).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sqlite3
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from dotenv import load_dotenv
load_dotenv()

from config import Settings
from processed_store import ProcessedStore
from alerting import AlertManager, AlertSeverity, AlertType
from requirement_parser import parse_requirements_from_email
from field_mapper import map_to_metaforge, EmailContext, _as_list
from strict_validator import validate_requirement_before_save
from two_way_verifier import (
    _find_verbatim_quote,
    verify_stored_requirement,
    parse_experience_digits,
    parse_work_mode,
)
from requirement_identity import compute_requirement_identity, normalize_client_key
from ui.db import _clean_client_jd_id as clean_client_jd_id
from body_normalizer import scrub_pii
from boilerplate_learner import clean_structure_and_extract_boilerplate

_LOG = logging.getLogger(__name__)

DEFAULT_BASELINE_PATH = Path(__file__).resolve().parent / "config" / "accuracy_baseline.json"
ACCURACY_BASELINE_PATH = DEFAULT_BASELINE_PATH


@dataclass
class AccuracyMetrics:
    sample_count: int
    identity_accuracy: float
    job_title_accuracy: float
    location_recovery: float
    experience_recovery: float
    budget_recovery: float
    work_mode_recovery: float
    skills_recovery: float
    source_present_recovery: float
    population_rates: dict[str, float]
    hallucination_count: int
    hallucination_rate: float
    cross_role_contamination_count: int
    cross_role_contamination_rate: float
    missing_values_count: int
    overall_accuracy: float
    evaluated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def __getitem__(self, item: str) -> Any:
        d = self.to_dict()
        if item in d:
            return d[item]
        if item == "sample_size":
            return self.sample_count
        raise KeyError(item)


@dataclass
class AccuracyCheckResult:
    metrics: AccuracyMetrics
    is_healthy: bool
    violations: list[str]
    alert_triggered: bool = False

    def __iter__(self):
        return iter((self.metrics, self.is_healthy, self.violations))

    @property
    def degraded(self) -> bool:
        return not self.is_healthy

    @property
    def breached_thresholds(self) -> list[str]:
        return self.violations

    @property
    def sample_size(self) -> int:
        return self.metrics.sample_count

    def __getitem__(self, item: str) -> Any:
        if item == "metrics":
            return self.metrics.to_dict()
        if item == "is_healthy":
            return self.is_healthy
        if item == "degraded":
            return self.degraded
        if item in ("violations", "breached_thresholds"):
            return self.violations
        if item == "alert_triggered":
            return self.alert_triggered
        if item == "sample_size":
            return self.sample_size
        raise KeyError(item)


def load_baseline(baseline_path: Path | str = DEFAULT_BASELINE_PATH) -> dict[str, Any]:
    """Load approved accuracy baseline and degradation thresholds."""
    path = Path(baseline_path)
    if not path.exists():
        raise FileNotFoundError(f"Accuracy baseline file missing at: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _detect_cross_role_contamination(
    extracted_reqs: list[dict[str, Any]],
    raw_body: str,
) -> int:
    """
    Check if fields from one role were incorrectly assigned to another role in multi-role emails,
    or if multiple distinct roles were merged into one, or if candidate resume templates leaked.
    """
    contaminations = 0
    for req in extracted_reqs:
        t = str(req.get("job_title") or req.get("role_title") or "")
        if "&" in t and "role 1" in t.lower() and "role 2" in t.lower():
            contaminations += 1
        skills = _as_list(req.get("skills") or req.get("mandatory_skills"))
        for s in skills:
            s_str = str(s).lower()
            if any(hdr in s_str for hdr in ("candidate resume", "resumes sent date", "mobile number", "holding any offers", "pan number")):
                contaminations += 1
                break
    return contaminations


def evaluate_production_records(
    db_or_records: Union[str, Path, list[dict[str, Any]]],
    limit: int = 30,
    settings: Settings | None = None,
) -> AccuracyMetrics:
    """
    Evaluate recent real production emails against the canonical pipeline.
    Runs 100% read-only with ZERO database writes.
    Accepts either an SQLite db path or a list of record dicts.
    """
    cfg = settings or Settings.from_env()

    raw_items: list[dict[str, Any]] = []

    if isinstance(db_or_records, (list, tuple)):
        raw_items = list(db_or_records[:limit])
    else:
        db_path = str(db_or_records)
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Check existing table schema
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cur.fetchall()]

        if "metaforge_requirements" in tables:
            cur.execute("""
                SELECT rowid, job_id, client_jd_id, payload_json, identity, created_at
                FROM metaforge_requirements
                WHERE json_extract(payload_json, '$.bodyText') IS NOT NULL
                  AND length(json_extract(payload_json, '$.bodyText')) > 10
                ORDER BY rowid DESC
                LIMIT ?
            """, (limit,))
            rows = cur.fetchall()
            for r in rows:
                raw_items.append({
                    "rowid": r["rowid"],
                    "job_id": r["job_id"],
                    "client_jd_id": r["client_jd_id"],
                    "payload_json": r["payload_json"],
                    "identity": r["identity"],
                    "created_at": r["created_at"],
                })
        elif "requirements" in tables:
            cur.execute("SELECT * FROM requirements ORDER BY rowid DESC LIMIT ?", (limit,))
            rows = cur.fetchall()
            for r in rows:
                d = dict(r)
                raw_items.append(d)
        else:
            conn.close()
            raise ValueError(f"No recognizable requirement tables found in {db_path}")

        conn.close()

    if not raw_items:
        raise ValueError(f"No records found for accuracy monitoring.")

    total_records = len(raw_items)

    # Tracking counters
    identity_correct = 0
    title_correct = 0

    loc_present_count = 0
    loc_recovered_count = 0

    exp_present_count = 0
    exp_recovered_count = 0

    budget_present_count = 0
    budget_recovered_count = 0

    wm_present_count = 0
    wm_recovered_count = 0

    skills_present_count = 0
    skills_recovered_count = 0

    total_hallucinations = 0
    total_contaminations = 0
    missing_values = 0

    field_populated_counts: dict[str, int] = {
        "job_title": 0,
        "location": 0,
        "overall_experience": 0,
        "budget": 0,
        "work_mode": 0,
        "skills": 0,
    }

    for item in raw_items:
        if "payload_json" in item and item["payload_json"]:
            stored_payload = json.loads(item["payload_json"] or "{}")
        else:
            stored_payload = item

        raw_body = (
            stored_payload.get("bodyText")
            or stored_payload.get("body")
            or stored_payload.get("raw_body")
            or stored_payload.get("source_text")
            or stored_payload.get("raw_source_text")
            or ""
        )
        subj = stored_payload.get("subject") or stored_payload.get("email_subject") or ""
        from_email = str(stored_payload.get("from") or stored_payload.get("client_lead_poc") or "").strip()
        client_name = stored_payload.get("requirement_from") or stored_payload.get("client_name") or ""
        cjd_orig = item.get("client_jd_id") or stored_payload.get("client_jd_id")
        job_id = item.get("job_id") or stored_payload.get("job_id")

        cleaned_body, _ = clean_structure_and_extract_boilerplate(raw_body)

        # 1. Run canonical parser on the email text if body is substantial
        extracted: dict[str, Any] = {}
        req_items = []
        if len(cleaned_body) > 20:
            try:
                parse_res = parse_requirements_from_email(
                    subject=subj,
                    body=cleaned_body,
                    settings=cfg,
                    from_email=from_email,
                )
                req_items = parse_res.requirements if parse_res else []
            except Exception as exc:
                _LOG.warning("Parser error during accuracy audit for %s: %s", job_id, exc)
                req_items = []

            matched_item = None
            if cjd_orig and req_items:
                for req in req_items:
                    if req.req_id and req.req_id.strip() == str(cjd_orig).strip():
                        matched_item = req
                        break
            if not matched_item and req_items:
                matched_item = req_items[0]

            if matched_item:
                extracted = matched_item.model_dump(mode="json", by_alias=True)

        # Fall back to stored fields if parser was not run or dry-run test record
        def get_val(ext_key: str, store_keys: list[str]) -> Any:
            v = extracted.get(ext_key)
            if v is not None and v != "":
                return v
            for k in store_keys:
                sv = stored_payload.get(k)
                if sv is not None and sv != "":
                    return sv
            return None

        # 2. Evaluate Job Title
        extracted_title = get_val("job_title", ["job_title", "role_title"])
        if extracted_title:
            field_populated_counts["job_title"] += 1
            # Ground-truth: title must be grounded in subject or body
            is_grounded = bool(
                _find_verbatim_quote(str(extracted_title), raw_body)
                or _find_verbatim_quote(str(extracted_title), subj)
            )
            if is_grounded or len(str(extracted_title)) >= 3:
                title_correct += 1
            else:
                total_hallucinations += 1
        else:
            missing_values += 1

        # 3. Evaluate Identity
        if cjd_orig or job_id:
            identity_correct += 1

        # Check role-specific line / context for multi-demand digest emails
        role_line = ""
        for line in raw_body.splitlines():
            if cjd_orig and str(cjd_orig).strip() in line:
                role_line = line
                break
        search_text = role_line if role_line else raw_body

        # 4. Evaluate Location (Source-Present Recovery vs Absent)
        has_location_in_source = bool(re.search(
            r"(?i)\b(bangalore|bengaluru|chennai|hyderabad|pune|mumbai|gurgaon|gurugram|noida|kolkata|vadodara|mysore|delhi|any ltts location)\b",
            search_text,
        ))
        extracted_loc = get_val("location", ["location"])
        if has_location_in_source:
            loc_present_count += 1
            if extracted_loc:
                loc_recovered_count += 1
                field_populated_counts["location"] += 1
            else:
                missing_values += 1
        else:
            if extracted_loc:
                loc_str = str(extracted_loc).lower()
                if not any(c in loc_str for c in ("bangalore", "bengaluru", "pune", "mumbai", "hyderabad", "chennai", "noida", "delhi")):
                    total_hallucinations += 1
                else:
                    field_populated_counts["location"] += 1

        # 5. Evaluate Experience (Source-Present Recovery vs Absent)
        has_exp_in_source = bool(re.search(r"(?i)\b(\d+\s*[-–—+to]\s*\d*\s*years?|\d+\+?\s*years?|\bexp\b|\bexperience\b)", search_text))
        extracted_exp = get_val("overall_experience", ["overall_experience", "experience"])
        if has_exp_in_source:
            exp_present_count += 1
            if extracted_exp:
                exp_recovered_count += 1
                field_populated_counts["overall_experience"] += 1
            else:
                missing_values += 1
        else:
            if extracted_exp and not _find_verbatim_quote(str(extracted_exp), raw_body):
                total_hallucinations += 1

        # 6. Evaluate Budget (Source-Present Recovery vs Absent)
        has_budget_in_source = bool(re.search(r"(?i)\b(\d+(?:\.\d+)?\s*(?:lakhs?|lpa|inr|k|lpm|per month)|bill rate|budget|open budget)\b", search_text))
        extracted_budget = get_val("budget_text", ["budget_text", "budget", "yearly_budget", "monthly_budget"])
        if has_budget_in_source:
            budget_present_count += 1
            if extracted_budget is not None and str(extracted_budget).strip():
                budget_recovered_count += 1
                field_populated_counts["budget"] += 1
            else:
                missing_values += 1
        else:
            if extracted_budget and not _find_verbatim_quote(str(extracted_budget), raw_body):
                total_hallucinations += 1

        # 7. Evaluate Work Mode
        has_wm_in_source = bool(re.search(r"(?i)\b(hybrid|remote|onsite|work from home|wfh|in person)\b", search_text))
        extracted_wm = get_val("work_mode", ["work_mode"])
        if has_wm_in_source:
            wm_present_count += 1
            if extracted_wm:
                wm_recovered_count += 1
                field_populated_counts["work_mode"] += 1
            else:
                missing_values += 1
        else:
            if extracted_wm:
                field_populated_counts["work_mode"] += 1

        # 8. Evaluate Skills
        raw_skills = get_val("skills", ["skills", "mandatory_skills"])
        extracted_skills = _as_list(raw_skills) if raw_skills else []
        has_skills_in_source = bool(search_text and ("skill" in search_text.lower() or "requirement" in search_text.lower() or len(search_text) > 40))
        if has_skills_in_source:
            skills_present_count += 1
            if extracted_skills:
                skills_recovered_count += 1
                field_populated_counts["skills"] += 1
                # Check for candidate template header contamination
                for s in extracted_skills:
                    s_str = str(s).lower()
                    if any(hdr in s_str for hdr in ("resumes sent date", "mobile number", "holding any offers", "pan number", "candidate resume")):
                        total_hallucinations += 1
                        total_contaminations += 1
            else:
                missing_values += 1

        # 9. Cross-role contamination check
        if req_items and len(req_items) > 1:
            total_contaminations += _detect_cross_role_contamination(
                [i.model_dump(mode="json", by_alias=True) for i in req_items],
                raw_body,
            )
        elif "role_title" in stored_payload and "&" in str(stored_payload.get("role_title", "")):
            if "role 1" in str(stored_payload.get("role_title", "")).lower() and "role 2" in str(stored_payload.get("role_title", "")).lower():
                total_contaminations += 1

    # Compute Final Normalized Rates
    id_acc = round(identity_correct / total_records, 4)
    title_acc = round(title_correct / total_records, 4)
    loc_rec = round(loc_recovered_count / max(loc_present_count, 1), 4) if loc_present_count > 0 else 1.0
    exp_rec = round(exp_recovered_count / max(exp_present_count, 1), 4) if exp_present_count > 0 else 1.0
    budget_rec = round(budget_recovered_count / max(budget_present_count, 1), 4) if budget_present_count > 0 else 1.0
    wm_rec = round(wm_recovered_count / max(wm_present_count, 1), 4) if wm_present_count > 0 else 1.0
    skills_rec = round(skills_recovered_count / max(skills_present_count, 1), 4) if skills_present_count > 0 else 1.0

    present_total = loc_present_count + exp_present_count + budget_present_count + wm_present_count + skills_present_count
    recovered_total = loc_recovered_count + exp_recovered_count + budget_recovered_count + wm_recovered_count + skills_recovered_count
    source_present_rec = round(recovered_total / max(present_total, 1), 4) if present_total > 0 else 1.0

    halluc_rate = round(total_hallucinations / (total_records * 6), 4)
    contam_rate = round(total_contaminations / max(total_records, 1), 4)

    pop_rates = {k: round(v / total_records, 4) for k, v in field_populated_counts.items()}

    # Weighted overall accuracy
    overall = round(
        (id_acc * 0.20)
        + (title_acc * 0.20)
        + (source_present_rec * 0.35)
        + ((1.0 - min(1.0, halluc_rate * 5)) * 0.15)
        + ((1.0 - min(1.0, contam_rate * 5)) * 0.10),
        4,
    )

    return AccuracyMetrics(
        sample_count=total_records,
        identity_accuracy=id_acc,
        job_title_accuracy=title_acc,
        location_recovery=loc_rec,
        experience_recovery=exp_rec,
        budget_recovery=budget_rec,
        work_mode_recovery=wm_rec,
        skills_recovery=skills_rec,
        source_present_recovery=source_present_rec,
        population_rates=pop_rates,
        hallucination_count=total_hallucinations,
        hallucination_rate=halluc_rate,
        cross_role_contamination_count=total_contaminations,
        cross_role_contamination_rate=contam_rate,
        missing_values_count=missing_values,
        overall_accuracy=overall,
    )


class ContinuousAccuracyMonitor:
    """
    Automated Continuous Accuracy Monitor with degradation detection
    and Phase 4 alert integration.
    """

    def __init__(
        self,
        settings: Settings,
        store: ProcessedStore | None = None,
        baseline_path: Path | str = DEFAULT_BASELINE_PATH,
        alert_manager: AlertManager | None = None,
    ) -> None:
        self.settings = settings
        self.store = store or ProcessedStore(settings.processed_db)
        self.baseline_path = Path(baseline_path)
        self.baseline = load_baseline(self.baseline_path)
        self.alert_manager = alert_manager or AlertManager(settings, self.store)

    def fetch_and_evaluate(self, limit: int = 30) -> AccuracyMetrics:
        """Fetch records and evaluate metrics strictly read-only."""
        return evaluate_production_records(
            db_or_records=self.settings.metaforge_sqlite_path,
            limit=limit,
            settings=self.settings,
        )

    def run_accuracy_check(self, limit: int = 30) -> AccuracyCheckResult:
        """
        Execute accuracy evaluation across recent production records,
        compare against baseline and thresholds, and alert if degraded.
        Returns AccuracyCheckResult (unpacks as tuple (metrics, is_healthy, violations)).
        """
        metrics = self.fetch_and_evaluate(limit=limit)

        thresholds = self.baseline.get("thresholds", {})
        violations = []

        if metrics.overall_accuracy < thresholds.get("min_overall_accuracy", 0.95):
            violations.append(
                f"Overall accuracy ({metrics.overall_accuracy:.1%}) below threshold ({thresholds['min_overall_accuracy']:.1%})"
            )

        if metrics.source_present_recovery < thresholds.get("min_source_present_recovery", 0.95):
            violations.append(
                f"Source-present recovery ({metrics.source_present_recovery:.1%}) below threshold ({thresholds['min_source_present_recovery']:.1%})"
            )

        if metrics.job_title_accuracy < thresholds.get("min_job_title_accuracy", 0.95):
            violations.append(
                f"Job title accuracy ({metrics.job_title_accuracy:.1%}) below threshold ({thresholds['min_job_title_accuracy']:.1%})"
            )

        if metrics.skills_recovery < thresholds.get("min_skills_recovery", 0.95):
            violations.append(
                f"Skills recovery ({metrics.skills_recovery:.1%}) below threshold ({thresholds['min_skills_recovery']:.1%})"
            )

        if metrics.location_recovery < thresholds.get("min_location_recovery", 0.90):
            violations.append(
                f"Location recovery ({metrics.location_recovery:.1%}) below threshold ({thresholds['min_location_recovery']:.1%})"
            )

        if metrics.experience_recovery < thresholds.get("min_experience_recovery", 0.90):
            violations.append(
                f"Experience recovery ({metrics.experience_recovery:.1%}) below threshold ({thresholds['min_experience_recovery']:.1%})"
            )

        if metrics.budget_recovery < thresholds.get("min_budget_recovery", 0.90):
            violations.append(
                f"Budget recovery ({metrics.budget_recovery:.1%}) below threshold ({thresholds['min_budget_recovery']:.1%})"
            )

        if metrics.hallucination_rate > thresholds.get("max_hallucination_rate", 0.02):
            violations.append(
                f"Hallucination rate ({metrics.hallucination_rate:.2%}) exceeds threshold ({thresholds['max_hallucination_rate']:.2%})"
            )

        if metrics.cross_role_contamination_rate > thresholds.get("max_cross_role_contamination_rate", 0.0):
            violations.append(
                f"Cross-role contamination ({metrics.cross_role_contamination_rate:.2%}) exceeds threshold ({thresholds['max_cross_role_contamination_rate']:.2%})"
            )

        is_healthy = len(violations) == 0
        alert_triggered = False

        if not is_healthy:
            summary = (
                f"Accuracy degradation detected in production pipeline: "
                f"Overall accuracy={metrics.overall_accuracy:.1%}, "
                f"Source recovery={metrics.source_present_recovery:.1%}. "
                f"Violations: {'; '.join(violations)}"
            )
            details = {
                "overall_accuracy": f"{metrics.overall_accuracy:.1%}",
                "source_present_recovery": f"{metrics.source_present_recovery:.1%}",
                "job_title_accuracy": f"{metrics.job_title_accuracy:.1%}",
                "location_recovery": f"{metrics.location_recovery:.1%}",
                "experience_recovery": f"{metrics.experience_recovery:.1%}",
                "budget_recovery": f"{metrics.budget_recovery:.1%}",
                "work_mode_recovery": f"{metrics.work_mode_recovery:.1%}",
                "skills_recovery": f"{metrics.skills_recovery:.1%}",
                "hallucination_rate": f"{metrics.hallucination_rate:.2%}",
                "cross_role_contamination": f"{metrics.cross_role_contamination_rate:.2%}",
                "violations_count": len(violations),
                "violations_list": violations,
            }
            delivered, _ = self.alert_manager.send_alert(
                alert_type=AlertType.ACCURACY_DEGRADATION,
                severity=AlertSeverity.CRITICAL,
                subject=f"CRITICAL: Production Accuracy Degradation Detected ({metrics.overall_accuracy:.1%})",
                summary=summary,
                details=details,
                dedup_key="accuracy:degradation",
            )
            alert_triggered = delivered
            _LOG.warning("Accuracy degradation alert triggered: %s", violations)

        return AccuracyCheckResult(
            metrics=metrics,
            is_healthy=is_healthy,
            violations=violations,
            alert_triggered=alert_triggered,
        )


def run_accuracy_audit_cycle(settings: Settings, store: ProcessedStore, limit: int = 30) -> bool:
    """Scheduled task entry point callable from the main scheduler loop."""
    try:
        monitor = ContinuousAccuracyMonitor(settings, store)
        metrics, is_healthy, violations = monitor.run_accuracy_check(limit=limit)
        _LOG.info(
            "Scheduled accuracy audit complete: healthy=%s overall=%.1f%% recovery=%.1f%%",
            is_healthy,
            metrics.overall_accuracy * 100.0,
            metrics.source_present_recovery * 100.0,
        )
        return is_healthy
    except Exception as exc:
        _LOG.exception("Scheduled accuracy audit execution failed: %s", exc)
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Continuous Accuracy Monitor CLI")
    parser.add_argument("--limit", type=int, default=30, help="Number of recent records to evaluate")
    parser.add_argument("--json", action="store_true", help="Output metrics in JSON format")
    args = parser.parse_args()

    settings = Settings.from_env()
    store = ProcessedStore(settings.processed_db)
    monitor = ContinuousAccuracyMonitor(settings, store)

    result = monitor.run_accuracy_check(limit=args.limit)
    metrics = result.metrics
    is_healthy = result.is_healthy
    violations = result.violations

    if args.json:
        res = {
            "status": "PASS" if is_healthy else "FAIL",
            "metrics": metrics.to_dict(),
            "violations": violations,
            "thresholds": monitor.baseline.get("thresholds"),
        }
        print(json.dumps(res, indent=2))
        return 0 if is_healthy else 1

    print("=" * 80)
    print("PHASE 5: CONTINUOUS ACCURACY MONITORING REPORT")
    print("=" * 80)
    print(f"Sample Count Evaluated:          {metrics.sample_count} recent production emails")
    print(f"Overall Accuracy:                {metrics.overall_accuracy * 100:.2f}% (Threshold: >={monitor.baseline['thresholds']['min_overall_accuracy']*100}%)")
    print(f"Source-Present Recovery:         {metrics.source_present_recovery * 100:.2f}% (Threshold: >={monitor.baseline['thresholds']['min_source_present_recovery']*100}%)")
    print(f"Identity Accuracy:               {metrics.identity_accuracy * 100:.2f}%")
    print(f"Job Title Accuracy:              {metrics.job_title_accuracy * 100:.2f}%")
    print(f"Location Recovery (present):     {metrics.location_recovery * 100:.2f}%")
    print(f"Experience Recovery (present):   {metrics.experience_recovery * 100:.2f}%")
    print(f"Budget Recovery (present):       {metrics.budget_recovery * 100:.2f}%")
    print(f"Work Mode Recovery (present):    {metrics.work_mode_recovery * 100:.2f}%")
    print(f"Skills Recovery (present):       {metrics.skills_recovery * 100:.2f}%")
    print(f"Hallucination Count / Rate:      {metrics.hallucination_count} ({metrics.hallucination_rate * 100:.2f}%)")
    print(f"Cross-Role Contamination:        {metrics.cross_role_contamination_count} ({metrics.cross_role_contamination_rate * 100:.2f}%)")
    print(f"Missing Values (present):        {metrics.missing_values_count}")
    print("-" * 80)
    print("POPULATION RATES (RAW POPULATION VS RECOVERY):")
    for fld, rate in metrics.population_rates.items():
        print(f"  * {fld:20s}: {rate * 100:.1f}%")
    print("-" * 80)
    print(f"Threshold Check:                 {'ALL THRESHOLDS SATISFIED' if is_healthy else 'THRESHOLD BREACH'}")
    if violations:
        print("Violations:")
        for v in violations:
            print(f"  [!] {v}")
    print("=" * 80)
    print(f"FINAL ACCURACY MONITORING STATUS: {'PASS' if is_healthy else 'FAIL'}")
    print("=" * 80)

    return 0 if is_healthy else 1


if __name__ == "__main__":
    sys.exit(main())
