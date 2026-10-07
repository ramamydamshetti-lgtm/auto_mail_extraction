from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def _parse_iso_utc(ts: str) -> datetime:
    raw = (ts or "").strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check scheduler heartbeat freshness.")
    parser.add_argument(
        "--heartbeat-path",
        default="data/scheduler_heartbeat.json",
        help="Path to heartbeat JSON file",
    )
    parser.add_argument(
        "--max-age-seconds",
        type=int,
        default=300,
    parser.add_argument(
        "--alert",
        action="store_true",
        help="Trigger automated alerts via AlertManager when heartbeat is stale or missing",
    )
    args = parser.parse_args()

    hb_path = Path(args.heartbeat_path)
    if not hb_path.exists():
        print(f"CRITICAL: heartbeat file missing at {hb_path}")
        if args.alert:
            try:
                from config import Settings
                from processed_store import ProcessedStore
                from alerting import AlertManager
                settings = Settings.from_env()
                store = ProcessedStore(settings.processed_db)
                manager = AlertManager(settings, store)
                manager.check_scheduler_heartbeat(heartbeat_path=hb_path, max_age_seconds=args.max_age_seconds)
            except Exception as e:
                print(f"Alert dispatch failed: {e}")
        return 2

    try:
        data = json.loads(hb_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"CRITICAL: heartbeat file unreadable: {exc}")
        if args.alert:
            try:
                from config import Settings
                from processed_store import ProcessedStore
                from alerting import AlertManager
                settings = Settings.from_env()
                store = ProcessedStore(settings.processed_db)
                manager = AlertManager(settings, store)
                manager.check_scheduler_heartbeat(heartbeat_path=hb_path, max_age_seconds=args.max_age_seconds)
            except Exception as e:
                print(f"Alert dispatch failed: {e}")
        return 2

    status = str(data.get("status") or "").strip().lower()
    ts = str(data.get("timestamp_utc") or "").strip()
    if not ts:
        print("CRITICAL: timestamp_utc missing in heartbeat")
        return 2

    try:
        hb_time = _parse_iso_utc(ts)
    except Exception as exc:
        print(f"CRITICAL: invalid heartbeat timestamp: {exc}")
        return 2

    now = datetime.now(timezone.utc)
    age = int((now - hb_time).total_seconds())
    if age > args.max_age_seconds:
        print(
            f"CRITICAL: heartbeat stale, age={age}s max={args.max_age_seconds}s status={status or 'unknown'}"
        )
        if args.alert:
            try:
                from config import Settings
                from processed_store import ProcessedStore
                from alerting import AlertManager
                settings = Settings.from_env()
                store = ProcessedStore(settings.processed_db)
                manager = AlertManager(settings, store)
                manager.check_scheduler_heartbeat(heartbeat_path=hb_path, max_age_seconds=args.max_age_seconds)
            except Exception as e:
                print(f"Alert dispatch failed: {e}")
        return 2

    if status not in {"running", "degraded"}:
        print(f"WARNING: heartbeat fresh but scheduler status={status or 'unknown'} age={age}s")
        return 1

    print(f"OK: heartbeat healthy status={status} age={age}s")
    if args.alert:
        try:
            from config import Settings
            from processed_store import ProcessedStore
            from alerting import AlertManager
            settings = Settings.from_env()
            store = ProcessedStore(settings.processed_db)
            manager = AlertManager(settings, store)
            manager.check_scheduler_heartbeat(heartbeat_path=hb_path, max_age_seconds=args.max_age_seconds)
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
