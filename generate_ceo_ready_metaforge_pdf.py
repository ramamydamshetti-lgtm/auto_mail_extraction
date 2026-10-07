from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from fpdf import FPDF

from client_detector import detect_client
from config import Settings
from email_filter import apply_email_filter
from field_mapper import map_to_ui_payload
from requirement_classifier import classify_email
from requirement_parser import parse_requirements_from_email

MAILBOX = "recruitment.application@metaforgeit.com"


def _latin(s: str) -> str:
    return (s or "").encode("latin-1", errors="replace").decode("latin-1")


def _as_list(raw: str) -> list[str]:
    return [x.strip() for x in str(raw or "").split(";") if x.strip()]


def _fmt(value: object) -> str:
    if value is None:
        return "Not provided"
    text = str(value).strip()
    return text if text else "Not provided"


def _fmt_list(value: object) -> str:
    if isinstance(value, list):
        tokens = [str(x).strip() for x in value if str(x).strip()]
        return "; ".join(tokens) if tokens else "Not provided"
    return _fmt(value)


def _soft_wrap_hard_tokens(text: str, max_token: int = 35) -> str:
    parts: list[str] = []
    for tok in str(text or "").split(" "):
        if len(tok) <= max_token:
            parts.append(tok)
            continue
        chunks = [tok[i : i + max_token] for i in range(0, len(tok), max_token)]
        parts.append(" ".join(chunks))
    return " ".join(parts)


def _dedupe_key(row: dict[str, str]) -> str:
    return "|".join(
        (
            row.get("requirement_from", "").strip().lower(),
            row.get("job_title", "").strip().lower(),
            row.get("location", "").strip().lower(),
            row.get("overall_experience", "").strip().lower(),
        )
    )


def build_rows(
    input_csv: Path,
    target_date: str,
    *,
    settings: Settings,
    min_confidence: float,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    seq = 0

    with input_csv.open("r", encoding="utf-8", newline="") as f:
        for raw in csv.DictReader(f):
            received = str(raw.get("received_date_time") or "").strip()
            if not received.startswith(target_date):
                continue

            subject = str(raw.get("subject") or "").strip()
            body = str(raw.get("body_normalized") or "").strip()
            from_email = str(raw.get("from_email") or "").strip()
            has_attachments = str(raw.get("attachment_count") or "0").strip() not in {"", "0"}

            client = detect_client(subject, body, from_email)
            if client is None:
                continue
            if client.key == "metaforge":
                # CEO report should represent client-originated requirements only.
                continue

            filt = apply_email_filter(
                subject=subject,
                body=body,
                has_attachments=has_attachments,
                from_email=from_email,
            )
            if not filt.allowed:
                continue

            cls_res = classify_email(body, subject=subject, settings=settings)
            if cls_res.label == "NOT_A_REQUIREMENT":
                continue

            parsed = parse_requirements_from_email(
                subject=subject,
                body=body,
                settings=settings,
                message_id=f"ceo:{target_date}:{received}:{subject[:40]}",
            )
            if not parsed.requirements:
                continue

            received_date = received[:10] if len(received) >= 10 else target_date
            to_emails = _as_list(str(raw.get("to_recipients") or ""))
            cc_emails = _as_list(str(raw.get("cc_recipients") or ""))

            for item in parsed.requirements:
                if float(item.confidence or 0.0) < min_confidence:
                    continue

                seq += 1
                mapped = map_to_ui_payload(
                    item.model_dump(mode="json", by_alias=True),
                    email_metadata={
                        "job_id": f"REQ-{target_date}-{seq:03d}",
                        "client_jd_id": f"{client.key.upper()}-{target_date}-{seq:03d}",
                        "date": received_date,
                        "count": f"{seq:03d}",
                        "requirement_from": client.display_name,
                        "from_email": from_email,
                        "cc_emails": cc_emails,
                        "to_emails": to_emails or [settings.internal_poc_default],
                    },
                )

                row = {
                    "job_id": _fmt(mapped.get("job_id")),
                    "demand_received_date": _fmt(mapped.get("demand_received_date")),
                    "internal_poc": _fmt(mapped.get("internal_poc_email")),
                    "requirement_from": _fmt(mapped.get("requirement_from")),
                    "client_jd_id": _fmt(mapped.get("client_jd_id")),
                    "client_lead_poc": _fmt(mapped.get("client_lead_poc_email")),
                    "client_poc": _fmt(mapped.get("client_poc_emails")),
                    "job_title": _fmt(mapped.get("job_title")),
                    "job_status": _fmt(str(mapped.get("job_status") or "").title()),
                    "closed_date": _fmt(mapped.get("closed_date")),
                    "type_of_demand": _fmt(str(mapped.get("type_of_demand") or "").title()),
                    "priority": _fmt(str(mapped.get("priority") or "").title()),
                    "number_of_positions": _fmt(mapped.get("number_of_positions")),
                    "experience_level": _fmt(mapped.get("experience_level")),
                    "employment_type": _fmt(mapped.get("employment_type")),
                    "budget_currency": _fmt(mapped.get("budget_currency")),
                    "yearly_budget": _fmt(mapped.get("yearly_budget")),
                    "monthly_budget": _fmt(mapped.get("monthly_budget")),
                    "work_mode": _fmt(mapped.get("work_mode")),
                    "location": _fmt(mapped.get("location")),
                    "overall_experience": _fmt(mapped.get("overall_experience")),
                    "notice_period": _fmt(mapped.get("notice_period")),
                    "mandatory_skills": _fmt_list(mapped.get("mandatory_skills")),
                    "skills": _fmt_list(mapped.get("skills")),
                    "source_subject": subject,
                    "source_received_time": received,
                    "source_graph_id": str(raw.get("graph_id") or "").strip(),
                }

                key = _dedupe_key(row)
                if key in seen:
                    continue
                seen.add(key)
                rows.append(row)

    return rows


def write_pdf(rows: list[dict[str, str]], output_pdf: Path, *, target_date: str, mailbox: str) -> None:
    pdf = FPDF()
    pdf.set_compression(False)
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 14)
    pdf.set_x(10)
    pdf.multi_cell(190, 9, _latin("MetaForge Requirement Mapping Demo"))
    pdf.set_font("Helvetica", "", 10)
    pdf.set_x(10)
    pdf.multi_cell(190, 7, _latin(f"Mailbox: {mailbox}"))
    pdf.set_x(10)
    pdf.multi_cell(190, 7, _latin(f"Date: {target_date}"))
    pdf.set_x(10)
    pdf.multi_cell(190, 7, _latin(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
    pdf.set_x(10)
    pdf.multi_cell(190, 7, _latin(f"Mapped requirements: {len(rows)}"))
    pdf.ln(2)

    if not rows:
        pdf.multi_cell(0, 6, _latin("No requirements matched for the selected date."))
        pdf.output(str(output_pdf))
        return

    ordered_fields = [
        "job_id",
        "demand_received_date",
        "internal_poc",
        "requirement_from",
        "client_jd_id",
        "client_lead_poc",
        "client_poc",
        "job_title",
        "job_status",
        "closed_date",
        "type_of_demand",
        "priority",
        "number_of_positions",
        "experience_level",
        "employment_type",
        "budget_currency",
        "yearly_budget",
        "monthly_budget",
        "work_mode",
        "location",
        "overall_experience",
        "notice_period",
        "mandatory_skills",
        "skills",
    ]

    for i, row in enumerate(rows, 1):
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_x(10)
        pdf.multi_cell(190, 7, _latin(f"Requirement {i}"))
        pdf.set_font("Helvetica", "", 9)
        for key in ordered_fields:
            label = key.replace("_", " ").title()
            line = f"{label}: {row.get(key, 'Not provided')}"
            line = _soft_wrap_hard_tokens(line)
            pdf.set_x(10)
            pdf.multi_cell(190, 5, _latin(line))
        pdf.ln(2)
        if i != len(rows):
            pdf.set_draw_color(200, 200, 200)
            y = pdf.get_y()
            pdf.line(10, y, 200, y)
            pdf.ln(2)

    pdf.output(str(output_pdf))


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate CEO-ready mapped requirements JSON + PDF")
    parser.add_argument("--input-csv", default="today_fetch.csv")
    parser.add_argument("--target-date", required=True, help="Date to include (YYYY-MM-DD)")
    parser.add_argument("--mailbox", default=MAILBOX)
    parser.add_argument("--min-confidence", type=float, default=0.85)
    parser.add_argument("--output-json", default=None)
    parser.add_argument("--output-pdf", default=None)
    args = parser.parse_args()

    load_dotenv()
    settings = Settings.from_env()

    target_date = args.target_date
    output_json = Path(args.output_json or f"metaforge_mapped_requirements_{target_date}_ceo_ready.json")
    output_pdf = Path(args.output_pdf or f"CEO_demo_metaforge_mapping_{target_date}_ceo_ready.pdf")

    rows = build_rows(
        Path(args.input_csv),
        target_date,
        settings=settings,
        min_confidence=float(args.min_confidence),
    )
    output_json.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    write_pdf(rows, output_pdf, target_date=target_date, mailbox=args.mailbox)
    print(f"Wrote {len(rows)} rows to {output_json} and {output_pdf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

