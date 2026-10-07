"""
Script: run_real_data_extraction_dump.py
Executes the full intake pipeline (email_filter -> requirement_classifier -> requirement_parser)
against real historical data from latest_500_all.csv and dumps the results into real_data_extraction_results.csv.

Does NOT sync to MetaForge or modify processed_store state.
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv

# Ensure workspace root is in sys.path
workspace_root = Path(__file__).resolve().parent.parent
if str(workspace_root) not in sys.path:
    sys.path.insert(0, str(workspace_root))

load_dotenv(workspace_root / ".env")

from config import Settings
import email_filter
import requirement_classifier
import requirement_parser

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
_LOG = logging.getLogger("real_data_dump")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run real data extraction dump against latest_500_all.csv"
    )
    parser.add_argument(
        "--input-csv",
        default=str(workspace_root / "latest_500_all.csv"),
        help="Input CSV path (default: latest_500_all.csv)",
    )
    parser.add_argument(
        "--output-csv",
        default=str(workspace_root / "real_data_extraction_results.csv"),
        help="Output CSV path (default: real_data_extraction_results.csv)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of emails to process (default: all)",
    )
    args = parser.parse_args()

    settings = Settings.from_env()
    _LOG.info("Loaded settings (METAFORGE_MODE=%s)", settings.metaforge_mode)

    input_path = Path(args.input_csv)
    if not input_path.exists():
        _LOG.error("Input CSV not found at %s", input_path)
        sys.exit(1)

    emails: list[dict[str, Any]] = []
    with open(input_path, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if args.limit is not None and i >= args.limit:
                break
            emails.append({
                "subject": row.get("subject") or "",
                "from_email": row.get("from_email") or row.get("sender_email") or "",
                "from_name": row.get("from_name") or row.get("sender_name") or "",
                "body": row.get("body_normalized") or row.get("body") or "",
                "has_attachments": str(row.get("has_attachments") or "").lower() in ("true", "1", "yes"),
                "received_date_time": row.get("received_date_time") or "",
            })

    total_emails = len(emails)
    _LOG.info("Loaded %d emails from %s", total_emails, input_path.name)

    fieldnames = [
        "subject",
        "sender",
        "filter_allowed",
        "filter_reason",
        "classification_label",
        "classification_confidence",
        "role_index",
        "job_title",
        "location",
        "number_of_positions",
        "experience_level",
        "employment_type",
        "work_mode",
        "mandatory_skills",
        "notice_period",
        "yearly_budget_min",
        "yearly_budget_max",
        "overall_confidence",
    ]

    counts = {
        "total_emails": total_emails,
        "total_rows_written": 0,
        "filtered_out": 0,
        "classified_not_requirement": 0,
        "classified_uncertain": 0,
        "classified_requirement": 0,
        "errors": 0,
    }

    output_path = Path(args.output_csv)
    with open(output_path, "w", encoding="utf-8", newline="") as out_f:
        writer = csv.DictWriter(out_f, fieldnames=fieldnames)
        writer.writeheader()

        for idx, em in enumerate(emails, 1):
            subject = em["subject"]
            from_email = em["from_email"]
            body = em["body"]
            has_att = em["has_attachments"]

            base_row = {
                "subject": subject,
                "sender": from_email,
                "filter_allowed": False,
                "filter_reason": "",
                "classification_label": "",
                "classification_confidence": "",
                "role_index": 1,
                "job_title": "",
                "location": "",
                "number_of_positions": "",
                "experience_level": "",
                "employment_type": "",
                "work_mode": "",
                "mandatory_skills": "",
                "notice_period": "",
                "yearly_budget_min": "",
                "yearly_budget_max": "",
                "overall_confidence": "",
            }

            try:
                # Step a: Email Filter
                filt = email_filter.apply_email_filter(
                    subject=subject,
                    body=body,
                    has_attachments=has_att,
                    from_email=from_email,
                )

                if not filt.allowed:
                    counts["filtered_out"] += 1
                    base_row["filter_allowed"] = False
                    base_row["filter_reason"] = str(filt.reason)
                    writer.writerow(base_row)
                    counts["total_rows_written"] += 1
                    continue

                base_row["filter_allowed"] = True
                base_row["filter_reason"] = ""

                # Step b: Requirement Classifier (pacing pause to respect 15 RPM LLM tier limits)
                time.sleep(1.2)
                cls_res = requirement_classifier.classify_email(
                    body=body,
                    subject=subject,
                    from_email=from_email,
                    settings=settings,
                )

                label = cls_res.label if hasattr(cls_res, "label") else str(cls_res)
                confidence = cls_res.confidence if hasattr(cls_res, "confidence") else 0.0

                base_row["classification_label"] = label
                base_row["classification_confidence"] = f"{confidence:.4f}"

                if label == "NOT_A_REQUIREMENT":
                    counts["classified_not_requirement"] += 1
                    writer.writerow(base_row)
                    counts["total_rows_written"] += 1
                    continue
                elif label == "UNCERTAIN":
                    counts["classified_uncertain"] += 1
                    writer.writerow(base_row)
                    counts["total_rows_written"] += 1
                    continue
                elif label != "REQUIREMENT":
                    _LOG.warning("Unexpected classification label %r for subject %r", label, subject)
                    writer.writerow(base_row)
                    counts["total_rows_written"] += 1
                    continue

                counts["classified_requirement"] += 1

                # Step c: Requirement Parser
                time.sleep(1.2)
                parse_res = requirement_parser.parse_requirements_from_email(
                    subject=subject,
                    body=body,
                    settings=settings,
                )

                reqs = parse_res.requirements if parse_res else []
                overall_conf = parse_res.overall_confidence if parse_res else 0.0

                if not reqs:
                    base_row["overall_confidence"] = f"{overall_conf:.4f}"
                    writer.writerow(base_row)
                    counts["total_rows_written"] += 1
                else:
                    for role_idx, r in enumerate(reqs, 1):
                        row = dict(base_row)
                        row["role_index"] = role_idx
                        row["job_title"] = r.job_title or ""
                        row["location"] = ", ".join(r.location) if isinstance(r.location, list) else str(r.location or "")
                        row["number_of_positions"] = r.number_of_positions if r.number_of_positions is not None else ""
                        row["experience_level"] = str(r.experience_level or "")
                        row["employment_type"] = str(r.employment_type or "")
                        row["work_mode"] = str(r.work_mode or "")
                        skills_merged = list(r.mandatory_skills or []) + list(r.soft_skills or [])
                        row["mandatory_skills"] = ", ".join(skills_merged)
                        row["notice_period"] = str(r.notice_period or "")
                        row["yearly_budget_min"] = r.yearly_budget_min if r.yearly_budget_min is not None else ""
                        row["yearly_budget_max"] = r.yearly_budget_max if r.yearly_budget_max is not None else ""
                        row["overall_confidence"] = f"{r.confidence:.4f}" if r.confidence is not None else f"{overall_conf:.4f}"
                        writer.writerow(row)
                        counts["total_rows_written"] += 1

            except Exception as exc:
                _LOG.error("Error processing email #%d (%s): %s", idx, subject, exc)
                counts["errors"] += 1
                base_row["filter_reason"] = f"error:{exc}"
                writer.writerow(base_row)
                counts["total_rows_written"] += 1

            if idx % 20 == 0 or idx == total_emails:
                _LOG.info("Progress: %d/%d emails processed (Rows written: %d)...", idx, total_emails, counts["total_rows_written"])

    _LOG.info("Extraction complete! Output written to: %s", output_path.resolve())
    _LOG.info("Counts Summary: %s", counts)


if __name__ == "__main__":
    main()
