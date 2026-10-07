from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from fpdf import FPDF
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import Settings
from client_detector import detect_client
from email_filter import apply_email_filter
from requirement_classifier import classify_email
from requirement_parser import parse_requirements_from_email


def _latin(text: Any) -> str:
    t = str(text or "")
    t = (
        t.replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2212", "-")
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\ufffd", "-")
    )
    return t.encode("latin-1", errors="replace").decode("latin-1")


def _wrap_hard_tokens(text: str, max_token: int = 35) -> str:
    parts: list[str] = []
    for tok in (text or "").split(" "):
        if len(tok) <= max_token:
            parts.append(tok)
            continue
        chunks = [tok[i : i + max_token] for i in range(0, len(tok), max_token)]
        parts.append(" ".join(chunks))
    return " ".join(parts)


def _first_requirement(req_obj: Any) -> dict[str, Any]:
    if not isinstance(req_obj, dict):
        return {}
    reqs = req_obj.get("requirements")
    if isinstance(reqs, list) and reqs and isinstance(reqs[0], dict):
        return reqs[0]
    return {}


def _join_skills(req: dict[str, Any]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for key in ("mandatory_skills", "soft_skills", "skills"):
        value = req.get(key)
        if not isinstance(value, list):
            continue
        for token in value:
            t = str(token or "").strip()
            k = t.lower()
            if not t or k in seen:
                continue
            seen.add(k)
            merged.append(t)
    return merged


def _clean_skills_for_display(skills: list[str]) -> list[str]:
    tech_hint = re.compile(
        r"(?i)\b(sap|abap|odata|idoc|cds|s4hana|ooabap|api|java|python|azure|databricks|salesforce|oauth|saml|oidc|piping|isometric|ga drawings?|pipe support|stlc|postman)\b"
    )
    out: list[str] = []
    seen: set[str] = set()
    for raw in skills:
        s = re.sub(r"\s+", " ", str(raw or "")).strip(" .:-|,")
        if not s:
            continue
        low = s.lower()
        if low in {"development", "segw)", "or pp is a plus"}:
            continue
        if len(s.split()) > 6:
            continue
        if low in {"information systems", "computer science", "or related field", "qualifications"}:
            continue
        if len(s.split()) > 4 and not tech_hint.search(s):
            continue
        if s.endswith(")") and "(" not in s:
            continue
        s = s.replace("ODATA", "OData").replace("S/4HANA", "S4HANA")
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out[:12]


def _extract_location_tokens(text: str) -> list[str]:
    if not text:
        return []
    cities = []
    for token in text.replace("/", ",").split(","):
        t = token.strip(" .:-|")
        if len(t) < 3:
            continue
        if t.lower() in {"location", "drive loc", "joining loc", "same as drive location"}:
            continue
        if t.lower() not in {x.lower() for x in cities}:
            cities.append(t)
    return cities[:8]


def _is_update_without_role(subject: str, body: str) -> bool:
    s = (subject or "").lower()
    b = (body or "").lower()
    return (
        ("so id" in b or "upload" in b or "drive loc" in b)
        and not any(k in s for k in ("developer", "engineer", "analyst", "consultant", "checker", "architect"))
    )


def _subject_core(subject: str) -> str:
    s = (subject or "").strip().lower()
    s = re.sub(r"^(re|fw|fwd|recall)\s*:\s*", "", s)
    s = re.sub(r"\b\d{1,2}(st|nd|rd|th)?\b", "", s)
    s = re.sub(r"\b(today|tomorrow|urgent|priority|face to face)\b", "", s)
    s = re.sub(r"[^a-z0-9+/#& ]+", " ", s)
    return " ".join(s.split())


def _demand_key(rec: dict[str, Any]) -> str:
    title = str(rec.get("job_title") or "").strip().lower()
    title = re.sub(r"\b(developer|consultant|engineer|analyst|checker)\b", "", title)
    title = " ".join(title.split())
    subject_core = _subject_core(str(rec.get("subject") or ""))
    seed = title or subject_core
    skill_seed = ",".join((rec.get("skills") or [])[:3]).lower()
    loc = str(rec.get("location") or "").lower()
    vendor = str(rec.get("source_vendor_key") or "").lower()
    return f"{vendor}|{seed}|{skill_seed}|{loc}"


def _record_rank(rec: dict[str, Any]) -> tuple[float, int, int, int]:
    return (
        float(rec.get("parsed_overall_confidence") or 0.0),
        int(rec.get("parsed_requirements_count") or 0),
        len(rec.get("skills") or []),
        0 if rec.get("fallback_reason") else 1,
    )


def _is_quality_requirement(rec: dict[str, Any], *, min_confidence: float) -> bool:
    conf = float(rec.get("parsed_overall_confidence") or 0.0)
    if conf < min_confidence:
        return False
    title = str(rec.get("job_title") or "").strip()
    if not title:
        return False

    title_norm = " ".join(title.lower().split())
    generic_weak_titles = {"cloud", "jd", "requirement", "opening"}
    skills = rec.get("skills") or []
    experience = str(rec.get("experience") or "").strip()
    location = rec.get("location") or []

    # Guardrail against vague thread updates being treated as requirements.
    if title_norm in generic_weak_titles and not experience and not location and len(skills) <= 1:
        return False
    return True


def build_reports(input_csv: Path, target_date: str, min_confidence: float) -> tuple[Path, Path, int]:
    load_dotenv()
    settings = Settings.from_env()
    rows = list(csv.DictReader(input_csv.open("r", encoding="utf-8", newline="")))
    today_client_rows: list[dict[str, Any]] = []
    for row in rows:
        ts = (row.get("received_date_time") or "").strip()
        if not ts.startswith(target_date):
            continue
        subject = (row.get("subject") or "").strip()
        body = (row.get("body_normalized") or "").strip()
        from_email = (row.get("from_email") or "").strip()
        has_attachments = False
        try:
            has_attachments = int(str(row.get("attachment_count") or "0")) > 0
        except ValueError:
            has_attachments = False

        # Robust "client demand" gating for any sender/client, including unseen ones.
        client_match = detect_client(subject, body, from_email)
        if client_match is None:
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
        today_client_rows.append(row)

    today_client_rows.sort(
        key=lambda r: ((r.get("received_date_time") or "").strip(), (r.get("subject") or "").strip())
    )

    normalized: list[dict[str, Any]] = []
    for idx, row in enumerate(today_client_rows, 1):
        fallback_req_obj: dict[str, Any] = {}
        try:
            fallback_req_obj = json.loads(row.get("requirement_json") or "{}")
        except Exception:
            fallback_req_obj = {}
        fallback_first = _first_requirement(fallback_req_obj)
        subject = (row.get("subject") or "").strip()
        body = (row.get("body_normalized") or "").strip()
        from_email = (row.get("from_email") or "").strip()
        client_match = detect_client(subject, body, from_email)
        source_vendor_key = client_match.key if client_match is not None else (row.get("source_vendor_key") or "")
        parsed = parse_requirements_from_email(
            subject=subject,
            body=body,
            settings=settings,
            message_id=f"today:{target_date}:{idx}",
        )
        parsed_first: dict[str, Any] = {}
        if parsed.requirements:
            parsed_first = parsed.requirements[0].model_dump()
        chosen = parsed_first or fallback_first
        fallback_reason = ""

        if not chosen.get("job_title") and _is_update_without_role(subject, body):
            # Thread-context carry-forward for short update emails with no explicit role text.
            for prev in reversed(normalized):
                if prev.get("from_email", "").lower() != (row.get("from_email") or "").strip().lower():
                    continue
                if prev.get("job_title"):
                    chosen = {
                        "job_title": prev.get("job_title"),
                        "mandatory_skills": prev.get("skills") or [],
                        "experience": prev.get("experience") or "",
                        "notice_period": prev.get("notice_period") or "",
                        "location": prev.get("location") or [],
                    }
                    fallback_reason = f"thread_context_from_email_{prev.get('seq')}"
                    break

        loc_value = chosen.get("location")
        if (not loc_value) and _is_update_without_role(subject, body):
            loc_guess = _extract_location_tokens(subject) or _extract_location_tokens(body)
            if loc_guess:
                loc_value = loc_guess

        normalized.append(
            {
                "seq": idx,
                "received_date_time": (row.get("received_date_time") or "").strip(),
                "source_vendor_key": str(source_vendor_key).strip(),
                "from_name": (row.get("from_name") or "").strip(),
                "from_email": from_email,
                "subject": subject,
                "graph_id": (row.get("graph_id") or "").strip(),
                "job_title": chosen.get("job_title"),
                "skills": _clean_skills_for_display(_join_skills(chosen)),
                "experience": chosen.get("experience"),
                "location": loc_value,
                "notice_period": chosen.get("notice_period"),
                "parsed_requirements_count": len(parsed.requirements),
                "parsed_overall_confidence": parsed.overall_confidence,
                "parsed_processing_note": parsed.processing_note or "",
                "fallback_reason": fallback_reason,
                "raw_requirement_json": fallback_req_obj,
            }
        )

    # Collapse duplicate/update emails that represent the same demand.
    grouped: dict[str, dict[str, Any]] = {}
    for rec in normalized:
        key = _demand_key(rec)
        if key not in grouped:
            grouped[key] = {
                "best": rec,
                "seqs": [rec["seq"]],
            }
            continue
        grouped[key]["seqs"].append(rec["seq"])
        if _record_rank(rec) > _record_rank(grouped[key]["best"]):
            grouped[key]["best"] = rec

    deduped: list[dict[str, Any]] = []
    for g in grouped.values():
        best = dict(g["best"])
        seqs = sorted(g["seqs"])
        best["duplicate_group_size"] = len(seqs)
        best["merged_from_seq"] = seqs
        deduped.append(best)

    deduped.sort(key=lambda r: (r.get("received_date_time") or "", r.get("subject") or ""))
    quality_deduped = [r for r in deduped if _is_quality_requirement(r, min_confidence=min_confidence)]

    output_json = Path(f"today_client_emails_exhaustive_{target_date}.json")
    output_json.write_text(
        json.dumps(
            {
                "date": target_date,
                "total_client_emails": len(normalized),
                "unique_demands": len(quality_deduped),
                "dropped_duplicate_emails": len(normalized) - len(deduped),
                "dropped_low_quality_demands": len(deduped) - len(quality_deduped),
                "min_confidence": min_confidence,
                "emails": quality_deduped,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    output_pdf = Path(f"today_client_emails_exhaustive_{target_date}.pdf")
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, _latin(f"Today Client Emails Exhaustive - {target_date}"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(
        0,
        6,
        _latin(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"),
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.cell(0, 6, _latin(f"Total client emails included: {len(normalized)}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, _latin(f"Unique demands after dedupe + quality gate: {len(quality_deduped)}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, _latin(f"Quality gate min confidence: {min_confidence:.2f}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    for idx, rec in enumerate(quality_deduped, 1):
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(
            0,
            6,
            _latin(f"Demand {idx}: {str(rec['subject'])[:120]}"),
            new_x="LMARGIN",
            new_y="NEXT",
        )
        pdf.set_font("Helvetica", "", 9)
        skills = rec["skills"] if isinstance(rec["skills"], list) else []
        lines = [
            f"Time: {rec['received_date_time']}",
            f"Client: {rec['source_vendor_key']} | From: {rec['from_name']} ({rec['from_email']})",
            f"Graph ID: {rec['graph_id']}",
            f"Job Title: {rec['job_title'] or 'N/A'}",
            f"Experience: {rec['experience'] or 'N/A'} | Location: {rec['location'] or 'N/A'} | Notice: {rec['notice_period'] or 'N/A'}",
            f"Skills: {', '.join(str(x) for x in skills) if skills else 'N/A'}",
            f"Parsed requirements: {rec['parsed_requirements_count']} | Parser note: {rec['parsed_processing_note'] or 'N/A'}",
            f"Fallback: {rec['fallback_reason'] or 'none'}",
            f"Merged duplicate emails: {rec.get('merged_from_seq')}",
        ]
        for line in lines:
            pdf.set_x(10)
            pdf.multi_cell(190, 5, _latin(_wrap_hard_tokens(line)))
        pdf.ln(1)
        pdf.set_draw_color(200, 200, 200)
        y = pdf.get_y()
        pdf.line(10, y, 200, y)
        pdf.ln(2)

    pdf.output(str(output_pdf))
    return output_json, output_pdf, len(quality_deduped)


def main() -> int:
    p = argparse.ArgumentParser(description="Generate exhaustive client-email report for a date.")
    p.add_argument("--input-csv", default="today_fetch.csv")
    p.add_argument("--target-date", required=True, help="Date in YYYY-MM-DD format")
    p.add_argument("--min-confidence", type=float, default=0.85)
    args = p.parse_args()

    out_json, out_pdf, count = build_reports(
        Path(args.input_csv),
        args.target_date,
        float(args.min_confidence),
    )
    print(f"Wrote {count} client emails to {out_json} and {out_pdf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
