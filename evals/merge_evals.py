"""
Auto-merge labeled eval entries into gold dataset.

Behavior:
- Merges one or more source JSON files into target dataset.
- Uses `id` as primary key; latest source wins on conflict.
- Optional deterministic holdout split written to a separate file.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any


def _load_array(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"{path} must be a JSON array")
    out: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict):
            out.append(item)
    return out


def _save_array(path: Path, arr: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(arr, indent=2, ensure_ascii=False), encoding="utf-8")


def _stable_split(
    rows: list[dict[str, Any]], holdout_ratio: float, seed: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    keyed = sorted(rows, key=lambda x: str(x.get("id") or ""))
    rng = random.Random(seed)
    idxs = list(range(len(keyed)))
    rng.shuffle(idxs)
    n_holdout = max(1, int(len(keyed) * holdout_ratio)) if keyed else 0
    holdout_set = set(idxs[:n_holdout])
    holdout, train = [], []
    for i, row in enumerate(keyed):
        (holdout if i in holdout_set else train).append(row)
    return train, holdout


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge eval datasets by id")
    parser.add_argument(
        "--target",
        default="evals/gold_standard.json",
        help="Target gold dataset path",
    )
    parser.add_argument(
        "--sources",
        nargs="+",
        required=True,
        help="Source JSON array files to merge",
    )
    parser.add_argument(
        "--write-holdout",
        default=None,
        help="Optional holdout output path (e.g. evals/test_holdout.json)",
    )
    parser.add_argument(
        "--holdout-ratio",
        type=float,
        default=0.2,
        help="Holdout split ratio when --write-holdout is provided",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Deterministic random seed for holdout split",
    )
    args = parser.parse_args()

    target_path = Path(args.target)
    merged_map: dict[str, dict[str, Any]] = {}

    for row in _load_array(target_path):
        rid = str(row.get("id") or "").strip()
        if rid:
            merged_map[rid] = row

    for src in args.sources:
        for row in _load_array(Path(src)):
            rid = str(row.get("id") or "").strip()
            if not rid:
                continue
            merged_map[rid] = row

    merged = sorted(merged_map.values(), key=lambda x: str(x.get("id") or ""))
    if args.write_holdout:
        train, holdout = _stable_split(merged, args.holdout_ratio, args.seed)
        _save_array(target_path, train)
        _save_array(Path(args.write_holdout), holdout)
        print(
            f"Merged {len(merged)} unique entries -> train={len(train)}, holdout={len(holdout)}"
        )
    else:
        _save_array(target_path, merged)
        print(f"Merged {len(merged)} unique entries into {target_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
