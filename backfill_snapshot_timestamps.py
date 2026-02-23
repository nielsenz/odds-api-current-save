#!/usr/bin/env python3
"""Backfill timestamp columns in existing odds CSV files without API calls.

Adds missing columns:
- snapshot_taken_at_utc
- response_received_at_utc
- bookmaker_last_update_utc

Inference rules for snapshot_taken_at_utc:
- historical file name `odds_YYYY-MM-DD.csv` -> `YYYY-MM-DDT17:00:00Z` by default
- timestamped daily file name `odds_YYYY-MM-DD_<label>_YYYYMMDDTHHMMSSZ.csv` -> parsed timestamp
- plain daily file name `odds_YYYY-MM-DD.csv` -> `YYYY-MM-DDT00:00:00Z`
"""

import argparse
import csv
import re
from pathlib import Path

TIMESTAMP_COLUMNS = [
    "snapshot_taken_at_utc",
    "api_snapshot_timestamp_utc",
    "response_received_at_utc",
    "bookmaker_last_update_utc",
]

HISTORICAL_DATE_RE = re.compile(r"^odds_(\d{4}-\d{2}-\d{2})\.csv$")
TIMESTAMPED_RE = re.compile(r"^odds_(\d{4}-\d{2}-\d{2})_[^_]+_(\d{8}T\d{6}Z)\.csv$")
PLAIN_DATE_RE = re.compile(r"^odds_(\d{4}-\d{2}-\d{2})\.csv$")


def infer_snapshot_timestamp(path: Path, historical_hour_utc: int) -> str:
    name = path.name
    m = TIMESTAMPED_RE.match(name)
    if m:
        raw = m.group(2)
        return f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}T{raw[9:11]}:{raw[11:13]}:{raw[13:15]}Z"

    m = HISTORICAL_DATE_RE.match(name)
    if m and "historical" in path.parts:
        return f"{m.group(1)}T{historical_hour_utc:02d}:00:00Z"

    m = PLAIN_DATE_RE.match(name)
    if m:
        return f"{m.group(1)}T00:00:00Z"

    return ""


def process_file(path: Path, historical_hour_utc: int, dry_run: bool) -> tuple[bool, str]:
    with path.open("r", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            return False, "empty/no header"
        rows = list(reader)
        fieldnames = list(reader.fieldnames)

    changed = False
    for col in TIMESTAMP_COLUMNS:
        if col not in fieldnames:
            fieldnames.append(col)
            changed = True

    if not rows:
        if changed and not dry_run:
            with path.open("w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
        return changed, "header-only update" if changed else "already up to date"

    inferred_snapshot = infer_snapshot_timestamp(path, historical_hour_utc)
    for row in rows:
        if not row.get("snapshot_taken_at_utc", "") and inferred_snapshot:
            row["snapshot_taken_at_utc"] = inferred_snapshot
            changed = True
        if "api_snapshot_timestamp_utc" not in row or row.get("api_snapshot_timestamp_utc", None) is None:
            row["api_snapshot_timestamp_utc"] = ""
            changed = True
        if "response_received_at_utc" not in row or row.get("response_received_at_utc", None) is None:
            row["response_received_at_utc"] = ""
            changed = True
        if "bookmaker_last_update_utc" not in row or row.get("bookmaker_last_update_utc", None) is None:
            row["bookmaker_last_update_utc"] = ""
            changed = True

    if changed and not dry_run:
        with path.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    return changed, "updated" if changed else "already up to date"


def iter_csv_files(paths: list[Path]):
    for base in paths:
        if not base.exists():
            continue
        if base.is_file() and base.suffix == ".csv":
            yield base
            continue
        if base.is_dir():
            for p in sorted(base.rglob("odds_*.csv")):
                yield p


def main():
    parser = argparse.ArgumentParser(description="Backfill timestamp columns for existing odds CSV files.")
    parser.add_argument(
        "--paths",
        nargs="+",
        default=["odds-data/historical", "odds-data"],
        help="Directories/files to process",
    )
    parser.add_argument(
        "--historical-hour-utc",
        type=int,
        default=17,
        help="Hour used when inferring historical snapshot_taken_at_utc (default: 17)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report changes without writing files")
    args = parser.parse_args()

    if args.historical_hour_utc < 0 or args.historical_hour_utc > 23:
        raise SystemExit("--historical-hour-utc must be between 0 and 23")

    targets = [Path(p) for p in args.paths]
    files = list(iter_csv_files(targets))
    updated = 0
    unchanged = 0

    for path in files:
        changed, reason = process_file(path, args.historical_hour_utc, args.dry_run)
        if changed:
            updated += 1
            print(f"UPDATED {path} ({reason})")
        else:
            unchanged += 1

    mode = "DRY RUN" if args.dry_run else "WRITE"
    print(f"{mode} complete: {updated} updated, {unchanged} unchanged, {len(files)} scanned")


if __name__ == "__main__":
    main()
