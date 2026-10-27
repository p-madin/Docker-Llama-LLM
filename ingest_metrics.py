#!/usr/bin/env python3
"""
ingest_metrics.py - Historical Backfill Utility for Benchmark Database (SQLite)

Scans existing JSON outputs in Test metrics/<model>/*_out.json and populates
benchmark.db idempotently without altering historical filesystem reports.
"""

import sys
import os
import re
import glob
import json
import argparse
from typing import List, Dict, Any, Tuple, Optional
import benchmark_store


def parse_filename_metadata(fpath: str) -> Tuple[str, Optional[str], bool]:
    """
    Extracts model folder name, timestamp string, and archive flag from file path.
    Example: Test metrics/llama3.2/2026-10-26_09-36-06_out.json
             -> ('llama3.2', '2026-10-26 09:36:06', False)
             Test metrics/Archives/llama3.2/2026-10-20_13-40-41_out.json
             -> ('llama3.2', '2026-10-20 13:40:41', True)
    """
    norm_path = os.path.normpath(fpath)
    parts = norm_path.split(os.sep)
    is_archive = "Archives" in parts
    model_dir = parts[-2] if len(parts) >= 2 else "unknown"

    base = os.path.basename(fpath)
    match = re.match(r"^(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})", base)
    if match:
        date_part, time_part = match.groups()
        time_formatted = time_part.replace("-", ":")
        timestamp_str = f"{date_part} {time_formatted}"
    else:
        timestamp_str = None

    return model_dir, timestamp_str, is_archive


def ingest_file(conn, fpath: str, verbose: bool = False) -> bool:
    """Ingests a single JSON report into benchmark.db idempotently. Returns True if newly ingested."""
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Warning: Could not read JSON '{fpath}': {e}", file=sys.stderr)
        return False

    model_dir, file_timestamp, is_archive = parse_filename_metadata(fpath)
    model_name = data.get("model") or model_dir

    base = os.path.basename(fpath)
    prefix = "archive" if is_archive else "import"
    run_uuid = f"{prefix}-{model_dir}-{base.replace('.json', '')}"

    # Check for existing run
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM benchmark_runs WHERE run_uuid = ?", (run_uuid,))
    if cursor.fetchone():
        if verbose:
            print(f"  [SKIPPED] Already ingested: {base} ({model_name})")
        return False

    execution_mode = "Cloud" if "gemini" in model_name.lower() else "GPU"
    environment = "Archive" if is_archive else ("Cloud API" if "gemini" in model_name.lower() else "Docker Local")

    run_id = benchmark_store.record_full_summary(
        conn=conn,
        summary=data,
        environment=environment,
        execution_mode=execution_mode,
        run_uuid=run_uuid,
        timestamp=file_timestamp
    )

    if verbose:
        cases_count = len(data.get("cases", []))
        passed = sum(1 for c in data.get("cases", []) if c.get("case_passed"))
        print(f"  [INGESTED] {base} -> Run #{run_id} ({model_name}: {passed}/{cases_count})")

    return True


def ingest_all(metrics_dir: str = "Test metrics", db_path: str = "benchmark.db",
               include_archives: bool = True, verbose: bool = True) -> int:
    """Finds all *_out.json files in metrics_dir (and optionally Archives) and backfills benchmark.db."""
    conn = benchmark_store.init_db(db_path)
    # First sync questions to ensure test_id mappings are current
    benchmark_store.sync_questions_from_xml(conn, "Questions/*.xml")

    files = glob.glob(os.path.join(metrics_dir, "*", "*_out.json"))
    if include_archives:
        archive_files = glob.glob(os.path.join(metrics_dir, "Archives", "*", "*_out.json"))
        files.extend(archive_files)

    # Filter out comparison files if any
    files = [f for f in files if "_out.json" in f and "comparison" not in f]
    files.sort()

    print(f"\nDiscovered {len(files)} historical benchmark report(s) in '{metrics_dir}' (Archives included: {include_archives}).")
    new_count = 0
    skipped_count = 0

    for fpath in files:
        ingested = ingest_file(conn, fpath, verbose=verbose)
        if ingested:
            new_count += 1
        else:
            skipped_count += 1

    print(f"\nIngestion Complete: {new_count} newly backfilled, {skipped_count} skipped.")
    stats = benchmark_store.get_stats(conn)
    print("\nUpdated Database Health:")
    for k, v in stats.items():
        print(f"  {k:<22} : {v:>6} rows")
    print()

    return new_count


def main():
    parser = argparse.ArgumentParser(
        description="ingest_metrics.py - Backfill Historical Benchmark JSONs into benchmark.db"
    )
    parser.add_argument("--metrics-dir", default="Test metrics", help="Directory containing test metrics. Default: 'Test metrics'")
    parser.add_argument("--db", default=benchmark_store.DEFAULT_DB_PATH, help=f"Database path. Default: {benchmark_store.DEFAULT_DB_PATH}")
    parser.add_argument("--include-archives", action="store_true", default=True, help="Include older runs in Test metrics/Archives/ (default: True).")
    parser.add_argument("--no-archives", dest="include_archives", action="store_false", help="Exclude Test metrics/Archives/.")
    parser.add_argument("--quiet", "-q", action="store_true", help="Suppress per-file logging.")

    args = parser.parse_args()
    ingest_all(metrics_dir=args.metrics_dir, db_path=args.db, include_archives=args.include_archives, verbose=not args.quiet)


if __name__ == "__main__":
    main()
