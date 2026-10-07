"""
Replay parser on raw_emails/ and compare with ground_truth/ pairs.

Usage:
  python evals/replay_mapping_dataset.py --id req_001
  python evals/replay_mapping_dataset.py --all
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from config import Settings
from requirement_parser import parse_requirements_from_email
from utils import setup_logging

RAW_DIR = ROOT / "raw_emails"
GT_DIR = ROOT / "ground_truth"


def _read_text_loose(path: Path) -> str:
    """
    Read text files exported from mixed mail clients.
    Prefer UTF-8, then fall back to common Windows encodings.
    """
    for enc in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    # Final fallback: decode with replacement to avoid hard failure in bulk runs.
    return path.read_bytes().decode("utf-8", errors="replace")


def _norm(s: Any) -> str:
    t = str(s or "").strip().lower()
    # Normalize common punctuation differences from copied email text.
    t = (
        t.replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2212", "-")
        .replace("\ufffd", "-")
    )
    return " ".join(t.split())


def _norm_skill_token(s: Any) -> str:
    t = _norm(s)
    t = t.replace("(", " ").replace(")", " ")
    t = " ".join(t.split())
    return t


_TITLE_STOPWORDS = {
    "sr",
    "senior",
    "jr",
    "junior",
    "lead",
    "principal",
    "specialist",
    "consultant",
    "experience",
    "years",
    "year",
    "yrs",
    "role",
    "engineer",
}


def _title_tokens(value: Any) -> set[str]:
    t = _norm(value)
    raw = re.split(r"[^a-z0-9+]+", t)
    out: set[str] = set()
    for tok in raw:
        tok = tok.strip()
        if len(tok) < 2:
            continue
        if tok in _TITLE_STOPWORDS:
            continue
        out.add(tok)
    return out


def is_title_match(predicted: Any, ground_truth: Any) -> bool:
    p = _title_tokens(predicted)
    g = _title_tokens(ground_truth)
    if not p and not g:
        return True
    if not p or not g:
        return False
    inter = p & g
    union = p | g
    jaccard = len(inter) / max(len(union), 1)
    # Accept when key role words overlap strongly, even if seniority differs.
    if jaccard >= 0.5:
        return True
    # Fallback: at least one core token overlap for short titles (e.g., "Java Developer").
    return len(inter) >= 1 and (len(g) <= 2 or len(p) <= 2)


def _skill_set(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, list):
        raw = value
    else:
        raw = re.split(r",|/|;|\|", str(value or ""))
    out = {_norm_skill_token(x) for x in raw if _norm_skill_token(x)}
    return out


def _compare_req(pred: dict[str, Any], gt: dict[str, Any]) -> dict[str, Any]:
    checks: dict[str, bool] = {}
    checks["job_title"] = is_title_match(pred.get("job_title"), gt.get("job_title"))
    checks["experience"] = _norm(pred.get("experience")) == _norm(gt.get("experience"))
    pred_loc = ",".join(pred.get("location") or []) if isinstance(pred.get("location"), list) else pred.get("location")
    checks["location"] = _norm(pred_loc) == _norm(gt.get("location"))
    checks["notice_period"] = _norm(pred.get("notice_period")) == _norm(gt.get("notice_period"))
    # Budget can be yearly or monthly; compare textual hints.
    budget_hint = gt.get("budget")
    pred_bud = ""
    if pred.get("monthly_budget_min") or pred.get("monthly_budget_max"):
        pred_bud = f"{pred.get('monthly_budget_min')}-{pred.get('monthly_budget_max')} monthly"
    elif pred.get("yearly_budget_min") or pred.get("yearly_budget_max"):
        pred_bud = f"{pred.get('yearly_budget_min')}-{pred.get('yearly_budget_max')} yearly"
    checks["budget_present"] = bool(budget_hint) == bool(pred_bud)
    gt_skills = _skill_set(gt.get("skills"))
    pred_skills = _skill_set((pred.get("mandatory_skills") or []) + (pred.get("skills") or []))
    # Flexible match: if GT has skills, they should be covered by predicted set.
    checks["skills"] = True if not gt_skills else gt_skills.issubset(pred_skills)
    score = sum(1 for v in checks.values() if v) / max(len(checks), 1)
    return {"checks": checks, "score": score}


def _normalize_gt_requirement(gt_item: dict[str, Any]) -> dict[str, Any]:
    """
    Support both ground-truth shapes:
    1) flat fields: {job_title, experience, ...}
    2) nested fields: {extracted_data: {job_title: {value: ...}, ...}}
    """
    ex = gt_item.get("extracted_data")
    if not isinstance(ex, dict):
        return gt_item

    def _val(field: str) -> Any:
        obj = ex.get(field)
        if isinstance(obj, dict) and "value" in obj:
            return obj.get("value")
        return obj

    return {
        "job_title": _val("job_title"),
        "experience": _val("experience"),
        "location": _val("location"),
        "notice_period": _val("notice_period"),
        "budget": _val("budget"),
        "skills": _val("skills"),
    }


def _run_one(req_id: str, settings: Settings) -> dict[str, Any]:
    raw_path = RAW_DIR / f"{req_id}.txt"
    gt_path = GT_DIR / f"{req_id}.json"
    if not raw_path.exists() or not gt_path.exists():
        return {"id": req_id, "error": "missing_pair_file"}

    raw_text = _read_text_loose(raw_path)
    gt = json.loads(_read_text_loose(gt_path))
    parsed = parse_requirements_from_email(
        subject=f"dataset:{req_id}",
        body=raw_text,
        settings=settings,
        message_id=f"dataset:{req_id}",
    )
    pred_items = [x.model_dump(mode="json", by_alias=True) for x in parsed.requirements]
    gt_items = gt.get("requirements") or []

    comp: list[dict[str, Any]] = []
    for i, gt_item in enumerate(gt_items):
        gt_norm = _normalize_gt_requirement(gt_item if isinstance(gt_item, dict) else {})
        pred = pred_items[i] if i < len(pred_items) else {}
        comp.append(_compare_req(pred, gt_norm))

    overall = sum(x["score"] for x in comp) / max(len(comp), 1) if comp else 0.0
    multi_role_expected = len(gt_items) > 1
    multi_role_detected = len(pred_items) > 1
    multi_role_ok = multi_role_detected == multi_role_expected
    return {
        "id": req_id,
        "predicted_count": len(pred_items),
        "ground_truth_count": len(gt_items),
        "multi_role_expected": multi_role_expected,
        "multi_role_detected": multi_role_detected,
        "multi_role_ok": multi_role_ok,
        "overall_score": overall,
        "comparisons": comp,
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Replay 1:1 mapping dataset")
    p.add_argument("--id", default=None, help="Single req id, e.g. req_001")
    p.add_argument("--all", action="store_true", help="Run all req_*.txt pairs")
    args = p.parse_args()

    load_dotenv()
    settings = Settings.from_env()
    setup_logging(settings.log_level)

    targets: list[str] = []
    if args.id:
        targets = [args.id]
    elif args.all:
        targets = [p.stem for p in RAW_DIR.glob("req_*.txt")]
    else:
        raise SystemExit("Pass --id req_001 or --all")

    results = [_run_one(t, settings) for t in sorted(targets)]
    print(json.dumps({"results": results}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

