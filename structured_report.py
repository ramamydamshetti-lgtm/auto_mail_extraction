from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

from reportlab.lib import colors
from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
EXP_RE = re.compile(
    r"(?i)\b(\d{1,2}\s*[-–]\s*\d{1,2}\s*(?:yrs?|years?)|\d{1,2}\s*\+\s*(?:yrs?|years?)|\d+(?:\.\d+)?\s*(?:yrs?|years?))\b"
)
NP_RE = re.compile(r"(?i)\b(?:notice period|np)\s*[:\-]?\s*([A-Za-z0-9+ ]{2,30})")
ROLE_RE = re.compile(r"(?i)\b(?:role|position|job title|title)\s*[:\-]\s*(.+)")
SKILL_LINE_RE = re.compile(r"(?i)\b(?:skills?|required skills?|tech stack)\s*[:\-]\s*(.+)")
OPENINGS_RE = re.compile(r"(?i)\b(\d{1,3})\s*(?:positions?|openings?|resources?)\b")
CC_LINE_RE = re.compile(r"(?im)^cc:\s*(.+)$")

FIELDS = [
    "Job ID",
    "Demand Received Date",
    "Internal POC Email",
    "Requirement From",
    "Client JD-ID",
    "Client Lead POC Email",
    "Client POC Emails",
    "Job Title",
    "Job Status",
    "Closed Date",
    "Type of Demand",
    "Priority",
    "Number of Positions",
    "Experience Level",
    "Employment Type",
    "Budget Currency",
    "Yearly Budget",
    "Monthly Budget",
    "Work Mode",
    "Location",
    "Overall Experience",
    "Notice Period",
    "Mandatory Skills",
    "Skills",
]


def _norm_space(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def _safe(v: str) -> str:
    return _norm_space(v) if _norm_space(v) else "Not Provided"


def _safe_json_loads(raw: str) -> Dict[str, Any]:
    try:
        obj = json.loads(raw or "{}")
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def normalize_experience(text: str) -> str:
    t = (text or "").strip().lower()
    if not t:
        return ""
    t = t.replace("yrs", "years").replace("yr", "year")
    t = re.sub(r"\s+", " ", t)
    m = re.search(r"(\d{1,2})\s*[-–]\s*(\d{1,2})\s*years?", t)
    if m:
        return f"{m.group(1)}-{m.group(2)} years"
    m = re.search(r"(\d{1,2}(?:\.\d+)?)\s*\+\s*years?", t)
    if m:
        return f"{m.group(1)}+ years"
    m = re.search(r"(\d{1,2}(?:\.\d+)?)\s*years?", t)
    if m:
        return f"{m.group(1)} years"
    return text.strip()


def normalize_date(dt: str) -> str:
    v = (dt or "").strip()
    if not v:
        return ""
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d", "%d-%b-%y", "%d-%b-%Y"):
        try:
            return datetime.strptime(v, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return v[:10]


def _extract_role(req: Dict[str, Any], body: str) -> str:
    cand = req.get("candidate_submissions") or []
    if isinstance(cand, list) and cand:
        c0 = cand[0] if isinstance(cand[0], dict) else {}
        role = c0.get("skill") or c0.get("role")
        if isinstance(role, str) and role.strip():
            return _norm_space(role)
    roles_table = req.get("roles_table") or []
    if isinstance(roles_table, list) and roles_table:
        r0 = roles_table[0] if isinstance(roles_table[0], dict) else {}
        role = r0.get("role")
        if isinstance(role, str) and role.strip():
            return _norm_space(role)
    m = ROLE_RE.search(body or "")
    if m:
        return _norm_space(m.group(1))
    return _norm_space(str(req.get("subject") or ""))


def _extract_skills(req: Dict[str, Any], body: str) -> Tuple[str, str]:
    all_skills: List[str] = []
    mandatory: List[str] = []
    cand = req.get("candidate_submissions") or []
    if isinstance(cand, list) and cand:
        c0 = cand[0] if isinstance(cand[0], dict) else {}
        sk = c0.get("skill")
        if isinstance(sk, str) and sk.strip():
            all_skills.append(_norm_space(sk))
    m = SKILL_LINE_RE.search(body or "")
    if m:
        all_skills.extend([_norm_space(x) for x in re.split(r",|/|\|", m.group(1)) if _norm_space(x)])
    for line in (req.get("key_points") or [])[:20]:
        if not isinstance(line, str):
            continue
        s = _norm_space(line)
        if not s:
            continue
        if any(k in s.lower() for k in ("mandatory", "must have", "must-have", "hands on", "strong in")):
            mandatory.append(s)
        if any(tok in s.lower() for tok in ("java", "python", "sap", "sql", "aws", "azure", "react", "android", "kotlin", "testing", "devops")):
            all_skills.append(s)
    dedup_all = list(dict.fromkeys([x for x in all_skills if x]))
    dedup_mand = list(dict.fromkeys([x for x in mandatory if x]))
    return "\n".join(dedup_mand[:10]), "\n".join(dedup_all[:15])


def _extract_experience(req: Dict[str, Any], body: str) -> str:
    ex = req.get("experience_mentions") or []
    if isinstance(ex, list) and ex:
        return normalize_experience(str(ex[0]))
    m = EXP_RE.search(body or "")
    return normalize_experience(m.group(1)) if m else ""


def _experience_level(overall: str) -> str:
    if not overall or overall == "Not Provided":
        return "Not Provided"
    m = re.search(r"(\d+(?:\.\d+)?)", overall)
    if not m:
        return "Not Provided"
    yrs = float(m.group(1))
    if yrs < 3:
        return "Junior"
    if yrs < 7:
        return "Mid"
    return "Senior"


def _extract_location(req: Dict[str, Any]) -> str:
    locs = req.get("locations") or []
    if isinstance(locs, list) and locs:
        return ", ".join([_norm_space(str(x)).title() for x in locs if str(x).strip()][:4])
    cand = req.get("candidate_submissions") or []
    if isinstance(cand, list) and cand:
        c0 = cand[0] if isinstance(cand[0], dict) else {}
        for k in ("preferred_location", "current_location"):
            v = _norm_space(str(c0.get(k) or ""))
            if v:
                return v.title()
    return ""


def _extract_notice_period(req: Dict[str, Any], body: str) -> str:
    cand = req.get("candidate_submissions") or []
    if isinstance(cand, list) and cand:
        c0 = cand[0] if isinstance(cand[0], dict) else {}
        np = _norm_space(str(c0.get("np") or ""))
        if np:
            return np
    m = NP_RE.search(body or "")
    return _norm_space(m.group(1)) if m else ""


def _extract_budget(body: str) -> Tuple[str, str, str]:
    b = body or ""
    currency = ""
    yearly = ""
    monthly = ""
    if re.search(r"(?i)\b(inr|rs\.?|lpa)\b", b):
        currency = "INR"
    elif re.search(r"(?i)\busd\b", b):
        currency = "USD"
    elif re.search(r"(?i)\beur\b", b):
        currency = "EUR"
    m_lpa = re.search(r"(?i)\b(\d+(?:\.\d+)?)\s*lpa\b", b)
    if m_lpa:
        yearly = f"{m_lpa.group(1)} LPA"
    m_pm = re.search(r"(?i)\b(\d+(?:,\d{3})*(?:\.\d+)?)\s*(?:per month|/month|pm)\b", b)
    if m_pm:
        monthly = m_pm.group(1)
    return currency, yearly, monthly


def _employment_type(body: str) -> str:
    b = (body or "").lower()
    if any(k in b for k in ("contract", "c2h", "contract to hire")):
        return "Contract"
    if any(k in b for k in ("full time", "full-time", "fte", "permanent")):
        return "Full Time"
    return ""


def _work_mode(body: str) -> str:
    b = (body or "").lower()
    if "hybrid" in b:
        return "Hybrid"
    if "remote" in b or "wfh" in b:
        return "Remote"
    if any(k in b for k in ("on-site", "onsite", "work from office")):
        return "On-site"
    return ""


def _priority(subject: str, body: str) -> str:
    s = f"{subject} {body}".lower()
    if any(k in s for k in ("urgent", "immediate", "asap", "critical")):
        return "High"
    if any(k in s for k in ("low priority", "whenever possible")):
        return "Low"
    return "Medium"


def _num_positions(req: Dict[str, Any], body: str) -> int:
    roles = req.get("roles_table") or []
    if isinstance(roles, list) and roles:
        return len(roles)
    m = OPENINGS_RE.search(body or "")
    if m:
        return int(m.group(1))
    return 1


def _demand_type(n: int) -> str:
    if n >= 6:
        return "Bulk"
    if n >= 2:
        return "Multiple"
    return "Single"


def _parse_cc_from_body(body: str) -> List[str]:
    out: List[str] = []
    m = CC_LINE_RE.search(body or "")
    if m:
        out.extend(EMAIL_RE.findall(m.group(1)))
    return out


def build_structured_rows(input_csv: Path) -> List[Dict[str, str]]:
    out_rows: List[Dict[str, str]] = []
    daily_counter: Dict[str, int] = {}

    with input_csv.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            req = _safe_json_loads(r.get("requirement_json", ""))
            body = r.get("body_normalized", "") or ""
            subject = r.get("subject", "") or ""
            source = req.get("source") if isinstance(req.get("source"), dict) else {}

            demand_date = normalize_date(r.get("received_date_time", ""))
            day_key = demand_date if demand_date else "0000-00-00"
            daily_counter[day_key] = daily_counter.get(day_key, 0) + 1
            seq = f"{daily_counter[day_key]:03d}"

            role = _extract_role(req, body)
            mandatory_skills, skills = _extract_skills(req, body)
            overall_exp = _extract_experience(req, body)
            location = _extract_location(req)
            notice_period = _extract_notice_period(req, body)
            currency, yearly_budget, monthly_budget = _extract_budget(body)
            emp_type = _employment_type(body)
            positions = _num_positions(req, body)
            from_email = _norm_space(str(source.get("sender_email") or r.get("from_email", "")))
            to_emails = _norm_space(r.get("to_recipients", ""))
            cc_emails = _parse_cc_from_body(body)
            poc_emails = list(dict.fromkeys([from_email] + cc_emails))

            row = {
                "Job ID": f"REQ-{day_key}-{seq}" if demand_date else f"REQ-0000-00-00-{seq}",
                "Demand Received Date": _safe(demand_date),
                "Internal POC Email": _safe(to_emails),
                "Requirement From": _safe(str(source.get("vendor_display") or "Other")),
                "Client JD-ID": f"CLIENT-{day_key}-{seq}" if demand_date else f"CLIENT-0000-00-00-{seq}",
                "Client Lead POC Email": _safe(from_email),
                "Client POC Emails": _safe("; ".join([x for x in poc_emails if x])),
                "Job Title": _safe(role),
                "Job Status": "Open",
                "Closed Date": "N/A",
                "Type of Demand": _demand_type(positions),
                "Priority": _priority(subject, body),
                "Number of Positions": str(positions),
                "Experience Level": _experience_level(_safe(overall_exp)),
                "Employment Type": _safe(emp_type),
                "Budget Currency": _safe(currency),
                "Yearly Budget": _safe(yearly_budget),
                "Monthly Budget": _safe(monthly_budget),
                "Work Mode": _safe(_work_mode(body)),
                "Location": _safe(location),
                "Overall Experience": _safe(overall_exp),
                "Notice Period": _safe(notice_period),
                "Mandatory Skills": _safe(mandatory_skills),
                "Skills": _safe(skills),
            }
            out_rows.append(row)
    return out_rows


def write_csv(rows: List[Dict[str, str]], out_csv: Path) -> None:
    with out_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def write_pdf(rows: List[Dict[str, str]], out_pdf: Path) -> None:
    doc = SimpleDocTemplate(str(out_pdf), pagesize=landscape(A3), leftMargin=12, rightMargin=12, topMargin=12, bottomMargin=12)
    styles = getSampleStyleSheet()
    story: List[Any] = [Paragraph("Recruitment Demand Extraction Report", styles["Title"]), Spacer(1, 8)]

    col_widths = [56, 62, 78, 62, 62, 78, 90, 80, 42, 52, 50, 44, 44, 48, 56, 48, 52, 52, 48, 62, 60, 56, 90, 110]
    chunk_size = 22

    def _pdf_cell(v: str, *, cap: int = 180) -> str:
        s = (v or "Not Provided").strip()
        if len(s) > cap:
            s = s[: cap - 1].rstrip() + "…"
        return s.replace("\n", "<br/>")

    for i in range(0, len(rows), chunk_size):
        chunk = rows[i : i + chunk_size]
        data: List[List[Any]] = [FIELDS]
        for r in chunk:
            data.append([Paragraph(_pdf_cell(r.get(k, "Not Provided")), styles["BodyText"]) for k in FIELDS])

        table = Table(data, repeatRows=1, colWidths=col_widths)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E78")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 6),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("GRID", (0, 0), (-1, -1), 0.2, colors.grey),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.HexColor("#F2F2F2")]),
                    ("LEFTPADDING", (0, 0), (-1, -1), 2),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                ]
            )
        )
        story.append(table)
        if i + chunk_size < len(rows):
            story.append(PageBreak())
    doc.build(story)


def main() -> int:
    p = argparse.ArgumentParser(description="Build structured recruitment table from extracted email CSV")
    p.add_argument("--input", default="extractions.csv", help="Input CSV from main.py output")
    p.add_argument("--output-csv", default="structured_recruitment_data.csv", help="Output structured CSV file")
    p.add_argument("--output-pdf", default="structured_recruitment_report.pdf", help="Output PDF report file")
    args = p.parse_args()

    in_csv = Path(args.input)
    if not in_csv.exists():
        raise SystemExit(f"Input file not found: {in_csv}")

    rows = build_structured_rows(in_csv)
    write_csv(rows, Path(args.output_csv))
    write_pdf(rows, Path(args.output_pdf))
    print(f"Wrote {len(rows)} rows to {args.output_csv} and {args.output_pdf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
