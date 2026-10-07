from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import date, datetime
from pathlib import Path

from fpdf import FPDF
from field_mapper import EmailContext, map_to_metaforge

MAILBOX = "recruitment.application@metaforgeit.com"

KNOWN_CLIENTS = {
    "itc": "ITC",
    "kpmg": "KPMG",
    "ust": "UST",
    "ltts": "LTTS",
    "accenture": "Accenture",
    "qbruenax": "Qbruenax",
    "brillio": "Brillio",
    "happiest_minds": "Happiest Minds",
    "metaforge": "Metaforge (Internal)",
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

SKIP_SUBJECT_PHRASES = (
    "interview availability",
    "availability confirmation",
    "interview confirmation",
)

TITLE_STRIP_PREFIXES = ("re:", "fw:", "fwd:")
TITLE_NOISE_PATTERNS = (
    r"\binterview\s+availability\s+confirmation\b",
    r"\bavailability\s+confirmation\b",
    r"\bkindly\s+share\b",
)
ROLE_HINT_PATTERNS = (
    r"(?:role|requirement|position)\s*[:\-]\s*([A-Za-z0-9/+\-& ,]{3,80})",
    r"\bfor\s+([A-Za-z0-9/+\-& ,]{3,80}?)(?:\s*[-|,]\s*(?:bangalore|hyderabad|chennai|vadodara|pune)\b|$)",
)
SKILL_KEYWORDS = (
    "flutter",
    "dart",
    "python",
    "java",
    "sql",
    "aws",
    "azure",
    "terraform",
    "waf",
    "devops",
    "kubernetes",
    "patran",
    "nastran",
    "fea",
    "rtos",
    "linux",
    "android",
    "c++",
    "c/c++",
    "wi-fi",
    "wifi",
)

CITY_WORDS = (
    "bangalore",
    "bengaluru",
    "hyderabad",
    "chennai",
    "vadodara",
    "pune",
    "mumbai",
    "noida",
    "gurgaon",
    "gurugram",
    "delhi",
)

ATOMIC_SKILL_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bpspice\b", "PSPICE"),
    (r"\bltspice\b", "LTSpice"),
    (r"\bmathcad\b", "MATHCAD"),
    (r"\borcad\b", "OrCAD"),
    (r"\baltium\b", "Altium"),
    (r"\bdxdesigner\b", "DxDesigner"),
    (r"\bpatran\b", "Patran"),
    (r"\bnastran\b", "Nastran"),
    (r"\bhyper ?mesh\b", "HyperMesh"),
    (r"\bfea\b", "FEA"),
    (r"\bfbd\b", "FBD"),
    (r"\bload path\b", "Load path analysis"),
    (r"\bp&id\b|\bpids\b", "P&ID"),
    (r"\bdatasheet\b", "Datasheet preparation"),
    (r"\bsld\b", "SLD"),
    (r"\bplc\b", "PLC"),
    (r"\bdcs\b", "DCS"),
    (r"\bexcel\b", "Excel"),
    (r"\baccess\b", "MS Access"),
    (r"\brtos\b", "RTOS"),
    (r"\bzephyr\b", "Zephyr"),
    (r"\bhal\b", "HAL"),
    (r"\bpdl\b", "PDL"),
    (r"\bpython\b", "Python"),
    (r"\bjava\b", "Java"),
    (r"\bsql\b", "SQL"),
    (r"\baws\b", "AWS"),
    (r"\bazure\b", "Azure"),
)

ROLE_SKILL_PACKS: dict[str, list[str]] = {
    "data analyst": ["P&ID", "Datasheet preparation", "SLD", "Excel", "MS Access", "PLC", "DCS"],
    "stress analysis": ["Patran", "Nastran", "FEA", "FBD", "Load path analysis", "Linear/Non-linear analysis"],
    "automotive hardware": ["PSPICE", "LTSpice", "MATHCAD", "OrCAD", "Altium", "DxDesigner", "Hardware documentation"],
    "piping checker": ["Piping isometrics", "Piping GA drawings", "Pipe support drawings", "Navisworks", "P&ID"],
}


def _clean_skill_token(token: str) -> str:
    t = re.sub(r"\s+", " ", (token or "").strip(" .:-\t\r\n"))
    if not t:
        return ""
    t = re.sub(r"(?i)^(mandatory skills?|skills?)\s*[:\-]?\s*", "", t).strip()
    t = re.sub(r"(?i)\betc\.?$", "", t).strip(" .,-")
    if not re.search(r"[A-Za-z0-9]", t):
        return ""
    if len(t) > 70:
        return ""
    return t


def _is_missing_like(value: str) -> bool:
    v = (value or "").strip().lower()
    return v in {"", "not specified", "none", "-", "–", "n/a", "na"}


def _compact_skill_phrase(text: str) -> str:
    s = re.sub(r"\s+", " ", (text or "").strip(" .:-\t\r\n"))
    s = re.sub(r"^[•\-–—]+\s*", "", s)
    s = re.sub(r"(?i)^(mandatory skills?|skills?)\s*[:\-]?\s*", "", s).strip()
    if not s:
        return ""
    low = s.lower()
    if any(
        noise in low
        for noise in (
            "to interact with clients",
            "good communication",
            "customers",
            "stakeholders",
            "responsible for",
            "ability to",
        )
    ):
        return ""
    # Convert overlong bullets into concise technical fragments.
    if len(s) > 80:
        return ""
    return s


def _extract_atomic_skills(text: str) -> list[str]:
    src = text or ""
    found: list[str] = []
    for pat, label in ATOMIC_SKILL_PATTERNS:
        if re.search(pat, src, re.IGNORECASE):
            found.append(label)

    # Parse common "skills: a, b, c" style lines.
    for ln in src.splitlines():
        if not re.search(r"(?i)\b(?:mandatory skills?|skills?|tech stack)\b", ln):
            continue
        rhs = re.split(r"(?i)(?:mandatory skills?|skills?|tech stack)\s*[:\-]?", ln, maxsplit=1)
        payload = rhs[1] if len(rhs) > 1 else ln
        for tok in re.split(r",|/|\||;|\band\b|\(", payload):
            c = _compact_skill_phrase(tok)
            if c:
                found.append(c)
    return _dedupe_strings(found)


def _role_pack_skills(subject: str, body: str) -> list[str]:
    ctx = f"{subject}\n{body}".lower()
    pack: list[str] = []
    for role_hint, skills in ROLE_SKILL_PACKS.items():
        if role_hint in ctx:
            pack.extend(skills)
    return _dedupe_strings(pack)


def _dedupe_strings(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in items:
        norm = _clean_skill_token(raw)
        if not norm:
            continue
        k = norm.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(norm)
    return out


def _latin(s: str) -> str:
    return (s or "").encode("latin-1", errors="replace").decode("latin-1")


def _safe_int(v: str, d: int) -> int:
    try:
        return int(v)
    except Exception:
        return d


def _norm_text(value: object) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _detect_positions(body: str, fallback: int = 1) -> int:
    bl = body.lower()
    m = re.search(r"(\d{1,3})\s*(?:positions?|postions?|openings?|resources?)", bl)
    if not m:
        m = re.search(r"(?:positions?|postions?|openings?|resources?)\s*[:\-]?\s*(\d{1,3})", bl)
    return _safe_int(m.group(1), fallback) if m else fallback


def _detect_experience(body: str, req: dict) -> str:
    mentions = req.get("experience_mentions") or []
    if isinstance(mentions, list) and mentions:
        return str(mentions[0]).strip()
    m = re.search(r"(\d{1,2}\s*[-–]\s*\d{1,2}\s*(?:years?|yrs?)|\d{1,2}\+?\s*(?:years?|yrs?))", body, re.I)
    return m.group(1).strip() if m else ""


def _exp_level(exp: str) -> str:
    if not exp:
        return "Mid Senior"
    m = re.search(r"(\d+(?:\.\d+)?)", exp)
    if not m:
        return "Mid Senior"
    n = float(m.group(1))
    if n < 3:
        return "Junior"
    if n < 7:
        return "Mid Senior"
    return "Senior"


def _infer_employment_type(body: str) -> str:
    b = body.lower()
    if any(x in b for x in ("contract", "c2h", "c2c", "bill rate", "per month", "/month", "monthly")):
        return "Contract"
    return "Full Time"


def _budget_fields(body: str, employment_type: str) -> tuple[str, str, str]:
    b = body.lower()
    currency = "INR" if any(x in b for x in ("inr", "rs", "lpa", "lakh")) else "USD" if "usd" in b else "EUR" if "eur" in b else "INR"
    yearly = ""
    monthly = ""

    m_range_lpa = re.search(r"(\d+(?:\.\d+)?)\s*[-to–—]+\s*(\d+(?:\.\d+)?)\s*lpa", b, re.I)
    if m_range_lpa:
        yearly = f"{int(float(m_range_lpa.group(1)) * 100000)}-{int(float(m_range_lpa.group(2)) * 100000)}"
    else:
        m_lpa = re.search(r"(\d+(?:\.\d+)?)\s*lpa", b, re.I)
        if m_lpa:
            yearly = str(int(float(m_lpa.group(1)) * 100000))

    m_month = re.search(r"(?:bill rate|monthly|per month|/month)[^0-9]*(\d{4,8})", b, re.I)
    if not m_month:
        m_month = re.search(r"\b(\d{5,7})\b", b)
    if m_month:
        monthly = m_month.group(1)

    if employment_type == "Contract" and not monthly and yearly:
        # fallback estimate if only yearly found
        if "-" in yearly:
            lo, hi = yearly.split("-", 1)
            monthly = f"{int(int(lo) / 12)}-{int(int(hi) / 12)}"
        else:
            monthly = str(int(int(yearly) / 12))

    return currency, yearly, monthly


def _work_mode(body: str) -> str:
    b = body.lower()
    if "hybrid" in b:
        return "Hybrid"
    if "remote" in b or "wfh" in b:
        return "Remote"
    if any(x in b for x in ("on-site", "onsite", "work from office")):
        return "On-site"
    return "On-site"


def _location(req: dict, body: str, subject: str = "") -> str:
    locs = req.get("locations") or []
    if isinstance(locs, list) and locs:
        return ", ".join(str(x).strip() for x in locs[:5] if str(x).strip())
    cities = (
        "bangalore",
        "bengaluru",
        "hyderabad",
        "pune",
        "chennai",
        "mumbai",
        "gurugram",
        "noida",
        "delhi",
        "kochi",
        "trivandrum",
    )
    b = body.lower()
    for c in cities:
        if c in b:
            return c.title()
    m = re.search(r"\b(?:in|at)\s+([A-Za-z ]{3,40})", body, re.I)
    if m:
        candidate = m.group(1).strip()
        bad_phrase = candidate.lower()
        if bad_phrase not in {"terms of inr", "inr", "our end", "client end"}:
            return candidate
    src = f"{subject} {body}".lower()
    for city in CITY_WORDS:
        if re.search(rf"\b{re.escape(city)}\b", src):
            return city.title()
    return "India"


def _sla_priority(body: str) -> str:
    b = body.lower()
    m = re.search(r"(\d{1,2})\s*(?:business\s*)?days?", b)
    if m:
        d = int(m.group(1))
        if d <= 2:
            return "High"
        if d <= 5:
            return "Medium"
        return "Low"
    if any(x in b for x in ("urgent", "asap", "immediate", "critical")):
        return "High"
    return "High"


def _skills(req: dict, body: str, subject: str) -> tuple[str, str]:
    out: list[str] = []
    mand: list[str] = []
    kp = req.get("key_points") or []
    if isinstance(kp, list):
        for k in kp[:20]:
            s = str(k).strip()
            if not s:
                continue
            s_low = s.lower()
            if any(t in s_low for t in ("mandatory", "must", "hands on", "strong in")):
                mand.extend(_extract_atomic_skills(s))
            if any(t in s_low for t in SKILL_KEYWORDS) or re.search(r"[A-Za-z]{2,}", s):
                out.extend(_extract_atomic_skills(s))

    body_lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    for ln in body_lines:
        ll = ln.lower()
        if "mandatory skill" in ll:
            rhs = re.split(r"(?i)mandatory skills?\s*[:\-]?", ln, maxsplit=1)
            source = rhs[1] if len(rhs) > 1 else ln
            atoms = _extract_atomic_skills(source)
            mand.extend(atoms)
            out.extend(atoms)
            continue
        if re.search(r"(?i)\b(?:skills?|tech stack)\s*[:\-]", ln):
            rhs = re.split(r"(?i)(?:skills?|tech stack)\s*[:\-]", ln, maxsplit=1)
            source = rhs[1] if len(rhs) > 1 else ln
            out.extend(_extract_atomic_skills(source))
            continue
        if any(kw in ll for kw in SKILL_KEYWORDS):
            out.extend(_extract_atomic_skills(ln))

    out.extend(_extract_atomic_skills(body))
    out.extend(_role_pack_skills(subject, body))
    mand.extend(_role_pack_skills(subject, body))

    out = _dedupe_strings([_compact_skill_phrase(x) for x in out])
    mand = _dedupe_strings([_compact_skill_phrase(x) for x in mand])
    if not mand and out:
        mand = out[: min(8, len(out))]
    return "; ".join(mand[:12]), "; ".join(out[:20])


def _clean_job_title(subject: str, body: str) -> str:
    s = re.sub(r"\s+", " ", (subject or "")).strip()
    s_lower = s.lower()
    for p in TITLE_STRIP_PREFIXES:
        if s_lower.startswith(p):
            s = s[len(p) :].strip()
            s_lower = s.lower()

    s = re.sub(r"\bwith\s+metaforgeit\b", "", s, flags=re.I)
    for pat in TITLE_NOISE_PATTERNS:
        s = re.sub(pat, "", s, flags=re.I)
    s = re.sub(r"(?i)\b(?:tpc)\b", "", s)
    s = re.sub(r"(?i)\b(?:requirement|requirements|opening|openings|role|position)\b", "", s)
    s = re.sub(
        rf"(?i)\bfor\s+(?:{'|'.join(CITY_WORDS)})(?:\s*[-|/]\s*(?:tpc|ltts|kpmg))?\b",
        "",
        s,
    )
    s = re.sub(rf"(?i)\b(?:{'|'.join(CITY_WORDS)})\b\s*[-|/]\s*(?:tpc|ltts|kpmg)\b", "", s)
    s = re.sub(rf"(?i)\s*[-|/]\s*(?:{'|'.join(CITY_WORDS)})\s*$", "", s)
    s = re.sub(rf"(?i)\s*[–—-]?\s*(?:{'|'.join(CITY_WORDS)})[.,]?\s*$", "", s)
    s = re.sub(r"(?i)\s*[-|/]\s*(?:tpc|ltts|kpmg)\s*$", "", s)
    s = re.sub(r"[-|,:/ ]{2,}", " ", s).strip(" -,:|/")
    s = re.sub(r"^[^\w]+", "", s).strip()
    if s and len(s) >= 4:
        return s

    text = f"{subject}\n{body}"[:2500]
    for pat in ROLE_HINT_PATTERNS:
        m = re.search(pat, text, flags=re.I)
        if m:
            candidate = re.sub(r"\s+", " ", m.group(1)).strip(" -,:|/")
            if len(candidate) >= 4:
                return candidate
    return (subject or "Unknown Role").strip()


def _infer_skill_tokens(subject: str, body: str) -> list[str]:
    source = f"{subject}\n{body}".lower()
    found: list[str] = []
    for kw in SKILL_KEYWORDS:
        if re.search(rf"\b{re.escape(kw)}\b", source):
            found.append(kw.upper() if kw in {"aws", "sql", "waf", "rtos", "fea"} else kw.title())
    return list(dict.fromkeys(found))


def _dedupe_key(row: dict[str, str]) -> str:
    return "|".join(
        [
            _norm_text(row.get("requirement_from")),
            _norm_text(row.get("job_title")),
            _norm_text(row.get("location")),
            _norm_text(row.get("overall_experience")),
        ]
    )


def map_rows(input_csv: Path, target_date: str) -> list[dict[str, str]]:
    mapped: list[dict[str, str]] = []
    seen_keys: set[str] = set()
    seq = 0
    with input_csv.open("r", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            received = (r.get("received_date_time") or "").strip()
            if not received.startswith(target_date):
                continue

            subject = (r.get("subject") or "").strip()
            body = (r.get("body_normalized") or "").strip()
            s = subject.lower()
            b = body.lower()
            has_att = (r.get("attachment_count") or "").strip() not in ("", "0")
            source_key = (r.get("source_vendor_key") or "").strip().lower()
            if source_key not in KNOWN_CLIENTS:
                continue
            # This report is for external client demand mails only.
            if source_key == "metaforge":
                continue
            if s.startswith(("re:", "fw:", "fwd:")):
                continue
            if any(x in s for x in SKIP_SUBJECT_PHRASES):
                continue
            if any(x in b for x in SKIP_PHRASES):
                continue
            if len(body) < 50 and not has_att:
                continue
            if not has_att and not any(x in s or x in b for x in ALLOW_PHRASES):
                continue

            seq += 1
            req = {}
            try:
                req = json.loads(r.get("requirement_json") or "{}")
            except Exception:
                req = {}

            positions = _detect_positions(body, 1)
            # CEO-demo rule: classify by count of JDs in the requirement, not by openings.
            # In this demo CSV, each row corresponds to one JD.
            jd_count = 1
            demand_type = "Single" if jd_count == 1 else "Multiple" if jd_count <= 9 else "Bulk"
            overall_exp = _detect_experience(body, req) or "3-6 years"
            exp_level = _exp_level(overall_exp)
            employment = _infer_employment_type(body)
            currency, yearly, monthly = _budget_fields(body, employment)
            work_mode = _work_mode(body)
            location = _location(req, body, subject)
            priority = _sla_priority(body)
            job_title = _clean_job_title(subject, body)
            parsed_mandatory, parsed_skills = _skills(req, body, subject)
            client_name = KNOWN_CLIENTS[source_key]
            from_email = (r.get("from_email") or "").strip()
            to_email = (r.get("to_recipients") or "").strip()
            client_poc = from_email
            ctx = EmailContext(
                graph_message_id=(r.get("graph_id") or "").strip(),
                internet_message_id=(r.get("internet_message_id") or "").strip(),
                to_emails=[x.strip() for x in to_email.split(";") if x.strip()],
                cc_emails=[],
                from_email=from_email,
                from_name=(r.get("from_name") or "").strip(),
            )
            enriched = map_to_metaforge(
                {
                    "job_title": job_title,
                    "number_of_positions": positions,
                    "experience": overall_exp,
                    "experience_level": "mid" if exp_level.lower().startswith("mid") else exp_level.lower(),
                    "employment_type": "contract" if employment.lower().startswith("contract") else "full-time",
                    "budget": f"{monthly} per month" if monthly else yearly,
                    "work_mode": work_mode.lower(),
                    "location": location,
                    "notice_period": "Immediate",
                    "priority": priority.upper(),
                    "skills": parsed_skills,
                    "mandatory_skills": parsed_mandatory,
                },
                ctx=ctx,
                client_display_name=client_name,
                job_id=f"REQ-{target_date}-{seq:03d}",
                client_jd_id=f"{source_key.upper()}-{target_date}-{seq:03d}",
                body_text=body,
                internal_poc_default="offshore demands",
                demand_received_date=date.fromisoformat(target_date),
            )
            mandatory_skills = str(enriched.get("mandatory_skills") or "")
            skills = str(enriched.get("skills") or "")
            if _is_missing_like(skills):
                inferred = _infer_skill_tokens(job_title, body)
                if inferred:
                    skills = "; ".join(inferred[:15])
            if _is_missing_like(mandatory_skills):
                mandatory_skills = skills
            overall_exp = str(enriched.get("overall_experience") or overall_exp)
            notice_period = str(enriched.get("notice_period") or "Immediate")
            row = {
                "job_id": f"REQ-{target_date}-{seq:03d}",
                "demand_received_date": target_date,
                "internal_poc": str(enriched.get("internal_poc") or "offshore demands"),
                "requirement_from": client_name,
                "client_jd_id": f"{source_key.upper()}-{target_date}-{seq:03d}",
                "client_lead_poc": from_email,
                "client_poc": client_poc,
                "job_title": job_title,
                "job_status": "Open",
                "closed_date": "N/A",
                "type_of_demand": demand_type,
                "priority": priority,
                "number_of_positions": str(positions),
                "experience_level": exp_level,
                "employment_type": employment,
                "budget_currency": currency,
                "yearly_budget": yearly,
                "monthly_budget": monthly,
                "work_mode": work_mode,
                "location": location,
                "overall_experience": overall_exp,
                "notice_period": notice_period,
                "mandatory_skills": mandatory_skills or "Not specified",
                "skills": skills or "Not specified",
                "source_subject": subject,
                "source_received_time": received,
            }
            dk = _dedupe_key(row)
            if dk in seen_keys:
                continue
            seen_keys.add(dk)
            mapped.append(row)
    return mapped


def write_pdf(
    rows: list[dict[str, str]],
    output_pdf: Path,
    *,
    target_date: str,
    mailbox: str = MAILBOX,
) -> None:
    pdf = FPDF()
    # Keep PDFs broadly compatible with lightweight viewers by avoiding compressed streams.
    pdf.set_compression(False)
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 9, _latin("MetaForge Requirement Mapping Demo"), ln=1)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 7, _latin(f"Mailbox: {mailbox}"), ln=1)
    pdf.cell(0, 7, _latin(f"Date: {target_date}"), ln=1)
    pdf.cell(0, 7, _latin(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"), ln=1)
    pdf.cell(0, 7, _latin(f"Mapped requirements: {len(rows)}"), ln=1)
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
        pdf.cell(0, 7, _latin(f"Requirement {i}"), ln=1)
        pdf.set_font("Helvetica", "", 9)
        for key in ordered_fields:
            v = str(row.get(key, "") or "")
            v = re.sub(r"\s+", " ", v).strip()
            if not v:
                v = "Not provided"
            label = key.replace("_", " ").title()
            line = f"{label}: {v}"
            line = re.sub(r"([A-Za-z0-9@._-]{35})(?=[A-Za-z0-9@._-])", r"\1 ", line)
            for wrapped in re.findall(r".{1,150}(?:\s+|$)", line):
                if wrapped.strip():
                    pdf.cell(0, 5, _latin(wrapped.strip()), ln=1)
        pdf.ln(2)
        if i != len(rows):
            pdf.set_draw_color(200, 200, 200)
            y = pdf.get_y()
            pdf.line(10, y, 200, y)
            pdf.ln(2)

    pdf.output(str(output_pdf))


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate mapped requirements JSON + PDF")
    parser.add_argument(
        "--input-csv",
        default="today_fetch.csv",
        help="Input CSV from mailbox dump",
    )
    parser.add_argument(
        "--target-date",
        default=date.today().isoformat(),
        help="Date to include (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--mailbox",
        default=MAILBOX,
        help="Mailbox label to show in PDF",
    )
    parser.add_argument(
        "--output-json",
        default=None,
        help="Optional output JSON path",
    )
    parser.add_argument(
        "--output-pdf",
        default=None,
        help="Optional output PDF path",
    )
    args = parser.parse_args()

    input_csv = Path(args.input_csv)
    target_date = args.target_date
    output_json = Path(
        args.output_json or f"metaforge_mapped_requirements_{target_date}.json"
    )
    output_pdf = Path(args.output_pdf or f"CEO_demo_metaforge_mapping_{target_date}.pdf")

    rows = map_rows(input_csv, target_date)
    output_json.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    write_pdf(rows, output_pdf, target_date=target_date, mailbox=args.mailbox)
    print(f"Wrote {len(rows)} rows to {output_json} and {output_pdf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

