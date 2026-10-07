from __future__ import annotations

import csv
import json
import re
import textwrap
from datetime import datetime
from pathlib import Path

from fpdf import FPDF

KNOWN_CLIENTS = {
    "itc",
    "kpmg",
    "ust",
    "ltts",
    "accenture",
    "qbruenax",
    "brillio",
    "happiest_minds",
    "metaforge",
}

ALLOW_PHRASES = (
    "we are hiring",
    "looking for",
    "requirement",
    "jd",
    "position",
    "role",
    "open postion",
    "open positions",
    "openings",
)

SKIP_PHRASES = (
    "not a requirement",
    "position closed",
    "thanks",
    "acknowledged",
    "update",
    "follow up",
)


def collect_rows(input_csv: Path, target_date: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with input_csv.open("r", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            dt = (r.get("received_date_time") or "").strip()
            if not dt.startswith(target_date):
                continue

            subject = (r.get("subject") or "").strip()
            s = subject.lower()
            body = (r.get("body_normalized") or "").strip()
            b = body.lower()
            vendor = (r.get("source_vendor_key") or "").strip().lower()
            has_att = (r.get("attachment_count") or "").strip() not in ("", "0")

            if s.startswith(("re:", "fw:", "fwd:")):
                continue
            if vendor not in KNOWN_CLIENTS:
                continue
            if any(x in b for x in SKIP_PHRASES):
                continue
            if len(body) < 50 and not has_att:
                continue
            if not has_att and not any(a in s or a in b for a in ALLOW_PHRASES):
                continue

            req = {}
            try:
                req = json.loads(r.get("requirement_json") or "{}")
            except Exception:
                req = {}

            exp = req.get("experience_mentions") or []
            m = re.search(r"(\d{1,3})\s*(?:positions?|openings?)", b)
            positions = m.group(1) if m else "1"
            summary = (req.get("summary") or body)[:700]

            rows.append(
                {
                    "received": dt,
                    "client": (r.get("source_vendor_display") or vendor or "Other").strip(),
                    "subject": subject,
                    "from": (r.get("from_email") or "").strip(),
                    "to": (r.get("to_recipients") or "").strip(),
                    "positions": positions,
                    "experience": (exp[0] if exp else "").strip(),
                    "summary": summary.strip(),
                }
            )
    return rows


def build_pdf(output_pdf: Path, rows: list[dict[str, str]], target_date: str) -> None:
    def _latin(s: str) -> str:
        return (s or "").encode("latin-1", errors="replace").decode("latin-1")

    def _safe_para(s: str, max_len: int = 500) -> str:
        t = re.sub(r"\s+", " ", s or "").strip()
        t = t[:max_len]
        # Break very long tokens so PDF layout does not fail.
        t = re.sub(r"([A-Za-z0-9@._-]{35})(?=[A-Za-z0-9@._-])", r"\1 ", t)
        return _latin(t)

    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, _latin(f"MetaForge Daily Requirement Summary ({target_date})"), ln=1)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 7, _latin("Mailbox: recruitment.application@metaforgeit.com"), ln=1)
    pdf.cell(0, 7, _latin(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"), ln=1)
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, _latin(f"Total requirement emails identified: {len(rows)}"), ln=1)

    if not rows:
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(
            0,
            6,
            _latin(
                "No genuine requirement emails matched today after applying reply/forward, "
                "known-client, and requirement-signal filters."
            ),
        )
        pdf.output(str(output_pdf))
        return

    headers = [
        ("Time(UTC)", 30),
        ("Client", 26),
        ("Subject", 105),
        ("From", 55),
        ("Positions", 20),
        ("Experience", 25),
    ]
    pdf.set_font("Helvetica", "B", 9)
    for header, width in headers:
        pdf.cell(width, 8, header, border=1)
    pdf.ln()

    pdf.set_font("Helvetica", "", 8)
    for row in rows:
        values = [
            row["received"][11:19],
            row["client"][:18],
            row["subject"][:85],
            row["from"][:42],
            str(row["positions"]),
            row["experience"][:18],
        ]
        for value, (_, width) in zip(values, headers):
            pdf.cell(width, 7, _latin(value), border=1)
        pdf.ln()

    pdf.ln(4)
    for i, row in enumerate(rows, 1):
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 6, _latin(f"Requirement {i}: {row['subject'][:110]}"), ln=1)
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(
            0,
            5,
            _latin(f"Client: {row['client']} | From: {row['from']} | To: {row['to']}"),
        )
        summary = _safe_para(f"Summary: {row['summary']}")
        for line in textwrap.wrap(summary, width=180, break_long_words=True, break_on_hyphens=True):
            pdf.cell(0, 5, line, ln=1)
        pdf.ln(2)

    pdf.output(str(output_pdf))


def main() -> int:
    target_date = "2026-04-10"
    input_csv = Path("today_fetch.csv")
    output_json = Path("today_requirements_2026-04-10.json")
    output_pdf = Path("CEO_demo_requirements_2026-04-10.pdf")

    rows = collect_rows(input_csv, target_date)
    output_json.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    build_pdf(output_pdf, rows, target_date)
    print(f"Wrote {len(rows)} requirement row(s) to {output_json} and {output_pdf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
