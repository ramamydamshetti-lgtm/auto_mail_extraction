"""
Evaluation harness for parser quality against a gold dataset.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from config import Settings
from requirement_parser import parse_requirements_from_email
from utils import setup_logging

TEXT_FIELDS = ("job_title", "experience")
SET_FIELDS = ("skills", "location")
HALLUCINATION_FIELDS = ("budget", "number_of_positions", "client_name")


@dataclass
class EvalSampleResult:
    sample_id: str
    schema_compliant: bool
    field_scores: dict[str, float]
    hallucination_count: int
    expected_req: dict[str, Any]
    actual_req: dict[str, Any]


def _norm_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _levenshtein_distance(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i]
        for j, cb in enumerate(b, start=1):
            insert_cost = cur[j - 1] + 1
            delete_cost = prev[j] + 1
            sub_cost = prev[j - 1] + (0 if ca == cb else 1)
            cur.append(min(insert_cost, delete_cost, sub_cost))
        prev = cur
    return prev[-1]


def _text_similarity(a: Any, b: Any) -> float:
    aa = _norm_text(a)
    bb = _norm_text(b)
    if not aa and not bb:
        return 1.0
    denom = max(len(aa), len(bb), 1)
    return max(0.0, 1.0 - (_levenshtein_distance(aa, bb) / denom))


def _as_tokens(value: Any) -> set[str]:
    if isinstance(value, list):
        raw = ",".join(str(x) for x in value)
    else:
        raw = str(value or "")
    parts = []
    for chunk in raw.replace(";", ",").split(","):
        t = _norm_text(chunk)
        if t:
            parts.append(t)
    return set(parts)


def _set_similarity(a: Any, b: Any) -> float:
    sa = _as_tokens(a)
    sb = _as_tokens(b)
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _first_requirement(obj: dict[str, Any]) -> dict[str, Any]:
    reqs = obj.get("requirements")
    if not isinstance(reqs, list) or not reqs:
        return {}
    first = reqs[0]
    if not isinstance(first, dict):
        return {}
    return first


def _requirements_list(obj: dict[str, Any]) -> list[dict[str, Any]]:
    reqs = obj.get("requirements")
    if not isinstance(reqs, list):
        return []
    out: list[dict[str, Any]] = []
    for item in reqs:
        if isinstance(item, dict):
            out.append(item)
    return out


def _pair_field_scores(expected_req: dict[str, Any], actual_req: dict[str, Any]) -> dict[str, float]:
    scores: dict[str, float] = {}
    for field in TEXT_FIELDS:
        scores[field] = _text_similarity(actual_req.get(field), expected_req.get(field))
    for field in SET_FIELDS:
        scores[field] = _set_similarity(actual_req.get(field), expected_req.get(field))
    return scores


def _pair_overall_score(expected_req: dict[str, Any], actual_req: dict[str, Any]) -> float:
    # Keep title weighted slightly higher; it anchors role identity in multi-role emails.
    fs = _pair_field_scores(expected_req, actual_req)
    weights = {"job_title": 0.4, "experience": 0.2, "skills": 0.2, "location": 0.2}
    return sum(fs[k] * w for k, w in weights.items())


def _greedy_best_matches(
    expected_reqs: list[dict[str, Any]], actual_reqs: list[dict[str, Any]]
) -> list[tuple[int, int, float]]:
    scored_pairs: list[tuple[int, int, float]] = []
    for exp_idx, exp_req in enumerate(expected_reqs):
        for act_idx, act_req in enumerate(actual_reqs):
            scored_pairs.append((exp_idx, act_idx, _pair_overall_score(exp_req, act_req)))
    scored_pairs.sort(key=lambda item: item[2], reverse=True)

    used_expected: set[int] = set()
    used_actual: set[int] = set()
    matches: list[tuple[int, int, float]] = []
    for exp_idx, act_idx, score in scored_pairs:
        if exp_idx in used_expected or act_idx in used_actual:
            continue
        matches.append((exp_idx, act_idx, score))
        used_expected.add(exp_idx)
        used_actual.add(act_idx)
    return matches


def _is_schema_compliant(processing_note: str | None) -> bool:
    note = (processing_note or "").lower()
    if not note:
        return True
    return not any(
        bad in note for bad in ("schema_validation_error", "json_decode_error", "parser_output_not")
    )


def evaluate_samples(samples: list[dict[str, Any]], settings: Settings) -> tuple[list[EvalSampleResult], dict[str, float]]:
    results: list[EvalSampleResult] = []
    agg: dict[str, list[float]] = {k: [] for k in (*TEXT_FIELDS, *SET_FIELDS)}
    schema_ok = 0
    halluc_total = 0

    for idx, sample in enumerate(samples):
        sample_id = str(sample.get("id") or f"sample_{idx + 1}")
        subject = str(sample.get("subject") or "")
        body = str(sample.get("body") or "")
        expected = sample.get("expected") or {}
        if not isinstance(expected, dict):
            expected = {}

        try:
            parsed = parse_requirements_from_email(
                subject=subject,
                body=body,
                settings=settings,
                message_id=f"eval:{sample_id}",
            )
        except Exception as exc:
            # Never crash eval runs; record as a failure and continue.
            parsed = None
            results.append(
                EvalSampleResult(
                    sample_id=sample_id,
                    schema_compliant=False,
                    field_scores={k: 0.0 for k in (*TEXT_FIELDS, *SET_FIELDS)},
                    hallucination_count=0,
                    expected_req=_first_requirement(expected),
                    actual_req={"_error": str(exc)},
                )
            )
            continue
        actual_reqs = [item.model_dump(mode="json", by_alias=True) for item in (parsed.requirements if parsed else [])]
        expected_reqs = _requirements_list(expected)
        matches = _greedy_best_matches(expected_reqs, actual_reqs)

        per_field_sums: dict[str, float] = {k: 0.0 for k in (*TEXT_FIELDS, *SET_FIELDS)}
        halluc_count = 0
        for exp_idx, act_idx, _ in matches:
            expected_req = expected_reqs[exp_idx]
            actual_req = actual_reqs[act_idx]
            fs = _pair_field_scores(expected_req, actual_req)
            for field, score in fs.items():
                per_field_sums[field] += score
            for field in HALLUCINATION_FIELDS:
                if _norm_text(expected_req.get(field)) == "" and _norm_text(actual_req.get(field)) != "":
                    halluc_count += 1

        # Penalize unmatched roles by dividing by the larger count.
        role_denominator = max(len(expected_reqs), len(actual_reqs), 1)
        per_field: dict[str, float] = {}
        for field in (*TEXT_FIELDS, *SET_FIELDS):
            score = per_field_sums[field] / role_denominator
            per_field[field] = score
            agg[field].append(score)

        matched_actual_idx = {act_idx for _, act_idx, _ in matches}
        for act_idx, actual_req in enumerate(actual_reqs):
            if act_idx in matched_actual_idx:
                continue
            for field in HALLUCINATION_FIELDS:
                if _norm_text(actual_req.get(field)) != "":
                    halluc_count += 1
        halluc_total += halluc_count

        compliant = _is_schema_compliant(parsed.processing_note)
        if compliant:
            schema_ok += 1

        expected_req = expected_reqs[matches[0][0]] if matches else _first_requirement(expected)
        actual_req = actual_reqs[matches[0][1]] if matches else (actual_reqs[0] if actual_reqs else {})

        results.append(
            EvalSampleResult(
                sample_id=sample_id,
                schema_compliant=compliant,
                field_scores=per_field,
                hallucination_count=halluc_count,
                expected_req=expected_req,
                actual_req=actual_req,
            )
        )

    n = max(len(results), 1)
    summary = {
        "overall_accuracy": sum(sum(r.field_scores.values()) / len(r.field_scores) for r in results) / n,
        "job_title_accuracy": sum(agg["job_title"]) / max(len(agg["job_title"]), 1),
        "experience_accuracy": sum(agg["experience"]) / max(len(agg["experience"]), 1),
        "skills_accuracy": sum(agg["skills"]) / max(len(agg["skills"]), 1),
        "location_accuracy": sum(agg["location"]) / max(len(agg["location"]), 1),
        "schema_compliance_rate": schema_ok / n,
        "hallucination_rate": halluc_total / n,
        "samples_evaluated": float(len(results)),
    }
    return results, summary


def _failure_rows(results: list[EvalSampleResult], threshold: float) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for r in results:
        low_fields = [k for k, v in r.field_scores.items() if v < threshold]
        if r.schema_compliant and r.hallucination_count == 0 and not low_fields:
            continue
        rows.append(
            {
                "id": r.sample_id,
                "schema_compliant": r.schema_compliant,
                "hallucination_count": r.hallucination_count,
                "low_score_fields": ",".join(low_fields),
                "job_title_expected": r.expected_req.get("job_title", ""),
                "job_title_actual": r.actual_req.get("job_title", ""),
                "experience_expected": r.expected_req.get("experience", ""),
                "experience_actual": r.actual_req.get("experience", ""),
                "skills_expected": r.expected_req.get("skills", ""),
                "skills_actual": r.actual_req.get("skills", ""),
                "location_expected": r.expected_req.get("location", ""),
                "location_actual": r.actual_req.get("location", ""),
            }
        )
    return rows


def _write_failures_csv(rows: list[dict[str, Any]], output_csv: Path) -> None:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "id",
        "schema_compliant",
        "hallucination_count",
        "low_score_fields",
        "job_title_expected",
        "job_title_actual",
        "experience_expected",
        "experience_actual",
        "skills_expected",
        "skills_actual",
        "location_expected",
        "location_actual",
    ]
    with output_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_failures_pdf(rows: list[dict[str, Any]], output_pdf: Path, threshold: float) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(output_pdf), pagesize=A4)
    styles = getSampleStyleSheet()
    story = []
    story.append(Paragraph("Evaluation Failures Report", styles["Title"]))
    story.append(Paragraph(f"Failure threshold: {threshold:.2f}", styles["Normal"]))
    story.append(Paragraph(f"Total failures: {len(rows)}", styles["Normal"]))
    story.append(Spacer(1, 12))
    for i, row in enumerate(rows, start=1):
        story.append(Paragraph(f"{i}. {row['id']}", styles["Heading3"]))
        story.append(
            Paragraph(
                f"Schema compliant: {row['schema_compliant']} | Hallucinations: {row['hallucination_count']} | Low fields: {row['low_score_fields']}",
                styles["Normal"],
            )
        )
        story.append(Paragraph(f"Job title: {row['job_title_actual']} (expected: {row['job_title_expected']})", styles["Normal"]))
        story.append(Paragraph(f"Experience: {row['experience_actual']} (expected: {row['experience_expected']})", styles["Normal"]))
        story.append(Paragraph(f"Skills: {row['skills_actual']} (expected: {row['skills_expected']})", styles["Normal"]))
        story.append(Paragraph(f"Location: {row['location_actual']} (expected: {row['location_expected']})", styles["Normal"]))
        story.append(Spacer(1, 10))
    doc.build(story)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run parser quality evaluation against gold dataset")
    parser.add_argument("--input", default="evals/gold_standard.json", help="Gold dataset file path")
    parser.add_argument("--limit", type=int, default=None, help="Optional max samples")
    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Skip the first N samples (for batch runs)",
    )
    parser.add_argument("--output", default=None, help="Optional path to save detailed JSON results")
    parser.add_argument(
        "--fail-threshold",
        type=float,
        default=0.8,
        help="Field similarity threshold below which a sample is flagged",
    )
    parser.add_argument(
        "--failures-csv",
        default=None,
        help="Optional output CSV path for failure review",
    )
    parser.add_argument(
        "--failures-pdf",
        default=None,
        help="Optional output PDF path for failure review",
    )
    args = parser.parse_args()

    load_dotenv()
    settings = Settings.from_env()
    setup_logging(settings.log_level)

    in_path = Path(args.input)
    if not in_path.exists():
        raise SystemExit(f"Input not found: {in_path}")

    raw = json.loads(in_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise SystemExit("Gold dataset must be a JSON array")
    offset = max(0, int(args.offset or 0))
    if args.limit is None:
        samples = raw[offset:]
    else:
        samples = raw[offset : offset + int(args.limit)]

    results, summary = evaluate_samples(samples, settings)

    print(f"Samples evaluated: {int(summary['samples_evaluated'])}")
    print(f"Overall Accuracy: {summary['overall_accuracy'] * 100:.2f}%")
    print(f"Job Title: {summary['job_title_accuracy'] * 100:.2f}%")
    print(f"Experience: {summary['experience_accuracy'] * 100:.2f}%")
    print(f"Skills: {summary['skills_accuracy'] * 100:.2f}%")
    print(f"Location: {summary['location_accuracy'] * 100:.2f}%")
    print(f"Schema Compliance: {summary['schema_compliance_rate'] * 100:.2f}%")
    print(f"Hallucination Rate (avg fields/sample): {summary['hallucination_rate']:.2f}")

    if args.output:
        out = {
            "summary": summary,
            "samples": [
                {
                    "id": r.sample_id,
                    "schema_compliant": r.schema_compliant,
                    "field_scores": r.field_scores,
                    "hallucination_count": r.hallucination_count,
                    "expected_requirement": r.expected_req,
                    "actual_requirement": r.actual_req,
                }
                for r in results
            ],  
        }
        Path(args.output).write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(f"Detailed results written: {args.output}")

    failures = _failure_rows(results, threshold=args.fail_threshold)
    if args.failures_csv:
        out_csv = Path(args.failures_csv)
        _write_failures_csv(failures, out_csv)
        print(f"Failure CSV report written: {out_csv}")
    if args.failures_pdf:
        out_pdf = Path(args.failures_pdf)
        _write_failures_pdf(failures, out_pdf, threshold=args.fail_threshold)
        print(f"Failure PDF report written: {out_pdf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
