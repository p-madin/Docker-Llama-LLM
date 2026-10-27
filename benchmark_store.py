#!/usr/bin/env python3
"""
benchmark_store.py - Relational Persistence Layer for LLM Benchmark Metrics (SQLite)

Implements Phase 2 of roadmap.md:
  - Embedded SQLite database (benchmark.db) using Python's standard library sqlite3.
  - Zero external pip dependencies.
  - Foreign-key enforced relational schema (DDL from roadmap.md#L164-241):
      1. models
      2. benchmark_runs
      3. test_suites
      4. questions
      5. assertions
      6. test_results
      7. assertion_results
  - High-performance transactional writes with WAL (Write-Ahead Logging) mode.
  - Question bank XML synchronization and historical ingestion support.
"""

import sys
import os
import re
import json
import uuid
import time
import sqlite3
import argparse
import xml.etree.ElementTree as ET
from typing import Dict, List, Any, Optional, Tuple


DEFAULT_DB_PATH = os.environ.get("DATABASE_PATH", "benchmark.db")

# ==============================================================================
# DDL Schema Definition (roadmap.md#L164-241)
# ==============================================================================

DDL_STATEMENTS = [
    # 1. Models Table
    """
    CREATE TABLE IF NOT EXISTS models (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        family TEXT,
        parameter_size TEXT,
        quantization TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """,

    # 2. Benchmark Runs Table
    """
    CREATE TABLE IF NOT EXISTS benchmark_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_uuid TEXT UNIQUE NOT NULL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        environment TEXT,
        execution_mode TEXT,
        total_duration_sec REAL
    );
    """,

    # 3. Test Suites Table
    """
    CREATE TABLE IF NOT EXISTS test_suites (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        file_path TEXT,
        description TEXT
    );
    """,

    # 4. Questions Table
    """
    CREATE TABLE IF NOT EXISTS questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        suite_id INTEGER REFERENCES test_suites(id) ON DELETE CASCADE,
        test_id TEXT UNIQUE NOT NULL,
        category TEXT,
        difficulty TEXT,
        tier INTEGER DEFAULT 1,
        question_text TEXT NOT NULL,
        system_prompt TEXT,
        temperature REAL DEFAULT 0.0,
        max_tokens INTEGER DEFAULT 1200
    );
    """,

    # 5. Assertions Table
    """
    CREATE TABLE IF NOT EXISTS assertions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question_id INTEGER REFERENCES questions(id) ON DELETE CASCADE,
        assertion_type TEXT NOT NULL,
        expected_value TEXT,
        is_negative INTEGER DEFAULT 0,
        case_sensitive INTEGER DEFAULT 0
    );
    """,

    # 6. Test Results Table
    """
    CREATE TABLE IF NOT EXISTS test_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER REFERENCES benchmark_runs(id) ON DELETE CASCADE,
        model_id INTEGER REFERENCES models(id) ON DELETE CASCADE,
        question_id INTEGER REFERENCES questions(id) ON DELETE CASCADE,
        passed INTEGER NOT NULL,
        raw_output TEXT,
        latency_sec REAL,
        eval_tokens_per_sec REAL,
        prompt_tokens_per_sec REAL,
        prompt_tokens INTEGER,
        completion_tokens INTEGER,
        load_duration_ms REAL
    );
    """,

    # 7. Assertion Results Table
    """
    CREATE TABLE IF NOT EXISTS assertion_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        test_result_id INTEGER REFERENCES test_results(id) ON DELETE CASCADE,
        assertion_id INTEGER REFERENCES assertions(id) ON DELETE SET NULL,
        passed INTEGER NOT NULL,
        message TEXT
    );
    """,

    # Indexes for Analytical Performance
    "CREATE INDEX IF NOT EXISTS idx_questions_suite ON questions(suite_id);",
    "CREATE INDEX IF NOT EXISTS idx_questions_test_id ON questions(test_id);",
    "CREATE INDEX IF NOT EXISTS idx_assertions_question ON assertions(question_id);",
    "CREATE INDEX IF NOT EXISTS idx_test_results_run ON test_results(run_id);",
    "CREATE INDEX IF NOT EXISTS idx_test_results_model ON test_results(model_id);",
    "CREATE INDEX IF NOT EXISTS idx_test_results_question ON test_results(question_id);",
    "CREATE INDEX IF NOT EXISTS idx_assertion_results_tr ON assertion_results(test_result_id);"
]


# ==============================================================================
# Database Connection & Initialization
# ==============================================================================

def get_connection(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Returns an SQLite connection configured with WAL mode and foreign keys enabled."""
    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str = DEFAULT_DB_PATH, auto_sync_questions: bool = True) -> sqlite3.Connection:
    """Executes the DDL statements to initialize all tables and indexes, and auto-seeds questions if empty."""
    conn = get_connection(db_path)
    with conn:
        for stmt in DDL_STATEMENTS:
            conn.execute(stmt)
        # Check and migrate columns if upgrading from earlier schema versions
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(questions)")
        cols = [row[1] for row in cursor.fetchall()]
        if cols and "tier" not in cols:
            cursor.execute("ALTER TABLE questions ADD COLUMN tier INTEGER DEFAULT 1")

    # Auto-seed questions DML if the questions table is empty on a fresh database
    if auto_sync_questions and os.path.isdir("Questions"):
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM questions")
        count = cursor.fetchone()[0]
        if count == 0:
            sync_questions_from_xml(conn, "Questions/*.xml")

    return conn


# ==============================================================================
# Model Metadata Inferencer & Registry
# ==============================================================================

MODEL_METADATA_DEFAULTS = {
    "llama3.2": {"family": "Llama", "parameter_size": "3.2B", "quantization": "Q4_K_M"},
    "qwen2.5-coder:3b": {"family": "Qwen", "parameter_size": "3.1B", "quantization": "Q4_K_M"},
    "smollm2:latest": {"family": "SmolLM", "parameter_size": "1.7B", "quantization": "Q4_K_M"},
    "phi3:mini": {"family": "Phi", "parameter_size": "3.8B", "quantization": "Q4_K_M"},
    "gemma3:1b": {"family": "Gemma", "parameter_size": "1.0B", "quantization": "Q4_K_M"},
    "deepseek-r1:1.5b": {"family": "DeepSeek", "parameter_size": "1.8B", "quantization": "Q4_K_M"},
    "gemini-3.8-flash": {"family": "Gemini", "parameter_size": "Frontier", "quantization": "Cloud API"},
    "gemini-3.1-flash-lite": {"family": "Gemini", "parameter_size": "Compact", "quantization": "Cloud API"},
    "gemini-flash-latest": {"family": "Gemini", "parameter_size": "Frontier", "quantization": "Cloud API"},
}


def get_or_create_model(conn: sqlite3.Connection, name: str,
                         family: Optional[str] = None,
                         parameter_size: Optional[str] = None,
                         quantization: Optional[str] = None) -> int:
    """Retrieves an existing model ID or inserts a new model record."""
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM models WHERE name = ?", (name,))
    row = cursor.fetchone()
    if row:
        return row[0]

    # Infer defaults if unspecified
    meta = MODEL_METADATA_DEFAULTS.get(name.lower(), {})
    family = family or meta.get("family") or ("Gemini" if name.lower().startswith("gemini") else "Unknown")
    parameter_size = parameter_size or meta.get("parameter_size") or ("Cloud" if "gemini" in name.lower() else "Unknown")
    quantization = quantization or meta.get("quantization") or ("Cloud API" if "gemini" in name.lower() else "Unknown")

    cursor.execute(
        """
        INSERT INTO models (name, family, parameter_size, quantization)
        VALUES (?, ?, ?, ?)
        """,
        (name, family, parameter_size, quantization)
    )
    return cursor.lastrowid


def get_or_create_suite(conn: sqlite3.Connection, name: str,
                         file_path: str = "", description: str = "") -> int:
    """Retrieves an existing test suite ID or inserts a new suite record."""
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM test_suites WHERE name = ?", (name,))
    row = cursor.fetchone()
    if row:
        return row[0]

    cursor.execute(
        """
        INSERT INTO test_suites (name, file_path, description)
        VALUES (?, ?, ?)
        """,
        (name, file_path, description)
    )
    return cursor.lastrowid


# ==============================================================================
# Question & Assertion Synchronization (from XML files)
# ==============================================================================

def sync_questions_from_xml(conn: sqlite3.Connection, xml_path_or_pattern: str = "Questions/*.xml") -> Dict[str, int]:
    """
    Parses test cases and assertions from XML files and syncs them into
    test_suites, questions, and assertions tables.
    Returns a mapping of {test_id: question_id}.
    """
    import glob
    if os.path.isdir(xml_path_or_pattern):
        xml_files = glob.glob(os.path.join(xml_path_or_pattern, "*.xml"))
    elif "*" in xml_path_or_pattern or "?" in xml_path_or_pattern:
        xml_files = glob.glob(xml_path_or_pattern)
    elif os.path.isfile(xml_path_or_pattern):
        xml_files = [xml_path_or_pattern]
    else:
        fallback = os.path.join("Questions", xml_path_or_pattern)
        xml_files = glob.glob(os.path.join(fallback, "*.xml")) if os.path.isdir(fallback) else glob.glob(xml_path_or_pattern)

    xml_files = [f for f in xml_files if f.lower().endswith(".xml")]
    xml_files.sort()

    question_id_map: Dict[str, int] = {}

    with conn:
        for fpath in xml_files:
            fname = os.path.basename(fpath)
            try:
                tree = ET.parse(fpath)
            except Exception as e:
                print(f"Warning: Could not parse XML '{fpath}': {e}", file=sys.stderr)
                continue

            root = tree.getroot()
            suite_name = root.attrib.get("name", fname)
            suite_id = get_or_create_suite(conn, suite_name, file_path=fpath, description=f"Imported from {fname}")

            for tc in root.findall("test_case"):
                test_id = tc.attrib.get("id")
                if not test_id:
                    continue

                category = tc.attrib.get("category", "general")
                difficulty = tc.attrib.get("difficulty", "medium")
                tier_val = tc.attrib.get("tier", "1")
                tier = int(tier_val) if tier_val and tier_val.isdigit() else 1
                name = tc.findtext("name", test_id).strip()
                question_text = tc.findtext("question", "").strip()
                system_prompt = tc.findtext("system_prompt", "").strip()

                temp_val = tc.findtext("temperature", "0.0").strip()
                temperature = float(temp_val) if temp_val else 0.0

                max_tok_val = tc.findtext("max_tokens", "1200").strip()
                max_tokens = int(max_tok_val) if max_tok_val else 1200

                # Upsert Question
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM questions WHERE test_id = ?", (test_id,))
                q_row = cursor.fetchone()
                if q_row:
                    q_id = q_row[0]
                    cursor.execute(
                        """
                        UPDATE questions
                        SET suite_id = ?, category = ?, difficulty = ?, tier = ?, question_text = ?,
                            system_prompt = ?, temperature = ?, max_tokens = ?
                        WHERE id = ?
                        """,
                        (suite_id, category, difficulty, tier, question_text, system_prompt, temperature, max_tokens, q_id)
                    )
                else:
                    cursor.execute(
                        """
                        INSERT INTO questions (suite_id, test_id, category, difficulty, tier, question_text, system_prompt, temperature, max_tokens)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (suite_id, test_id, category, difficulty, tier, question_text, system_prompt, temperature, max_tokens)
                    )
                    q_id = cursor.lastrowid

                question_id_map[test_id] = q_id

                # Synchronize Assertions
                assertions_elem = tc.find("assertions")
                if assertions_elem is not None:
                    # Remove old assertions for clean sync
                    cursor.execute("DELETE FROM assertions WHERE question_id = ?", (q_id,))
                    for assert_elem in assertions_elem.findall("assert"):
                        rule_type = assert_elem.attrib.get("type", "contains").strip()
                        case_sensitive = 1 if assert_elem.attrib.get("case_sensitive", "false").lower() == "true" else 0
                        is_negative = 1 if rule_type.startswith("not_") else 0

                        expected_tags = assert_elem.findall("expected")
                        if expected_tags:
                            expected_list = [e.text.strip() for e in expected_tags if e.text]
                            expected_val = json.dumps(expected_list)
                        else:
                            expected_val = assert_elem.text.strip() if assert_elem.text else ""

                        cursor.execute(
                            """
                            INSERT INTO assertions (question_id, assertion_type, expected_value, is_negative, case_sensitive)
                            VALUES (?, ?, ?, ?, ?)
                            """,
                            (q_id, rule_type, expected_val, is_negative, case_sensitive)
                        )

    return question_id_map


# ==============================================================================
# Transactional Benchmark Execution Recording
# ==============================================================================

def record_run(conn: sqlite3.Connection,
               run_uuid: Optional[str] = None,
               environment: str = "local",
               execution_mode: str = "GPU",
               total_duration_sec: float = 0.0,
               timestamp: Optional[str] = None) -> int:
    """Creates a new record in benchmark_runs and returns its integer run_id."""
    run_uuid = run_uuid or str(uuid.uuid4())
    cursor = conn.cursor()
    if timestamp:
        cursor.execute(
            """
            INSERT INTO benchmark_runs (run_uuid, timestamp, environment, execution_mode, total_duration_sec)
            VALUES (?, ?, ?, ?, ?)
            """,
            (run_uuid, timestamp, environment, execution_mode, total_duration_sec)
        )
    else:
        cursor.execute(
            """
            INSERT INTO benchmark_runs (run_uuid, environment, execution_mode, total_duration_sec)
            VALUES (?, ?, ?, ?)
            """,
            (run_uuid, environment, execution_mode, total_duration_sec)
        )
    return cursor.lastrowid


def record_full_summary(conn: sqlite3.Connection,
                        summary: Dict[str, Any],
                        environment: str = "local",
                        execution_mode: Optional[str] = None,
                        run_uuid: Optional[str] = None,
                        timestamp: Optional[str] = None) -> int:
    """
    Persists a complete benchmark summary dictionary (as produced by testLLM.py)
    into models, benchmark_runs, test_results, and assertion_results tables.
    """
    model_name = summary.get("model", "unknown")
    if not execution_mode:
        execution_mode = "Cloud" if "gemini" in model_name.lower() else "GPU"

    total_duration = summary.get("total_latency_sec", 0.0)

    # Sync questions first to ensure question_id mapping exists
    cursor = conn.cursor()
    cursor.execute("SELECT test_id, id FROM questions")
    q_map = {row[0]: row[1] for row in cursor.fetchall()}

    with conn:
        model_id = get_or_create_model(conn, model_name)
        run_id = record_run(conn, run_uuid=run_uuid, environment=environment,
                            execution_mode=execution_mode, total_duration_sec=total_duration,
                            timestamp=timestamp)

        for case in summary.get("cases", []):
            test_id = case.get("test_id")
            question_id = q_map.get(test_id)

            if not question_id:
                # Create a placeholder question if not found in database
                cursor.execute(
                    """
                    INSERT INTO questions (test_id, question_text, category)
                    VALUES (?, ?, ?)
                    """,
                    (test_id, case.get("question", test_id), "unclassified")
                )
                question_id = cursor.lastrowid
                q_map[test_id] = question_id

            passed = 1 if case.get("case_passed") else 0
            raw_output = case.get("output", "")
            metrics = case.get("metrics", {})

            latency_sec = metrics.get("latency_sec", 0.0)
            eval_tps = metrics.get("eval_tokens_per_sec", 0.0)
            prompt_tps = metrics.get("prompt_tokens_per_sec", 0.0)
            prompt_tok = metrics.get("prompt_tokens", 0)
            completion_tok = metrics.get("completion_tokens", 0)
            load_ms = metrics.get("load_duration_ms", 0.0)

            cursor.execute(
                """
                INSERT INTO test_results (
                    run_id, model_id, question_id, passed, raw_output,
                    latency_sec, eval_tokens_per_sec, prompt_tokens_per_sec,
                    prompt_tokens, completion_tokens, load_duration_ms
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (run_id, model_id, question_id, passed, raw_output,
                 latency_sec, eval_tps, prompt_tps, prompt_tok, completion_tok, load_ms)
            )
            test_result_id = cursor.lastrowid

            # Record assertion results
            for ar in case.get("assertions", []):
                ar_passed = 1 if ar.get("passed") else 0
                ar_msg = ar.get("message", "")

                cursor.execute(
                    """
                    INSERT INTO assertion_results (test_result_id, passed, message)
                    VALUES (?, ?, ?)
                    """,
                    (test_result_id, ar_passed, ar_msg)
                )

    return run_id


# ==============================================================================
# Reporting & Inspection Queries
# ==============================================================================

def get_stats(conn: sqlite3.Connection) -> Dict[str, int]:
    """Returns row counts across all relational tables."""
    tables = [
        "models", "benchmark_runs", "test_suites",
        "questions", "assertions", "test_results", "assertion_results"
    ]
    counts = {}
    cursor = conn.cursor()
    for t in tables:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {t}")
            counts[t] = cursor.fetchone()[0]
        except sqlite3.OperationalError:
            counts[t] = 0
    return counts


def get_latest_matrix(conn: sqlite3.Connection, min_questions: int = 10) -> List[Dict[str, Any]]:
    """
    Returns summary statistics for the latest run of each evaluated model.
    Filters by min_questions (default: 10) to avoid replacing full benchmark evaluations with ad-hoc smoke tests.
    """
    cursor = conn.cursor()
    query = """
    WITH qualifying_runs AS (
        SELECT tr.model_id, tr.run_id, br.timestamp, COUNT(tr.id) as q_count
        FROM test_results tr
        JOIN benchmark_runs br ON tr.run_id = br.id
        GROUP BY tr.model_id, tr.run_id
        HAVING COUNT(tr.id) >= ?
    ),
    latest_runs AS (
        SELECT qr.model_id, qr.run_id, qr.timestamp
        FROM qualifying_runs qr
        WHERE qr.run_id = (
            SELECT MAX(qr2.run_id)
            FROM qualifying_runs qr2
            WHERE qr2.model_id = qr.model_id
        )
    )
    SELECT
        m.name AS model_name,
        m.family,
        m.parameter_size,
        COUNT(tr.id) AS total_questions,
        SUM(tr.passed) AS questions_solved,
        ROUND((CAST(SUM(tr.passed) AS REAL) / COUNT(tr.id)) * 100, 1) AS pass_rate_pct,
        ROUND(AVG(tr.eval_tokens_per_sec), 2) AS avg_speed_tps,
        ROUND(SUM(tr.latency_sec), 2) AS total_latency_sec,
        lr.timestamp AS run_timestamp,
        lr.run_id AS run_id
    FROM latest_runs lr
    JOIN test_results tr ON tr.model_id = lr.model_id AND tr.run_id = lr.run_id
    JOIN models m ON m.id = lr.model_id
    GROUP BY m.id, lr.run_id, lr.timestamp
    ORDER BY pass_rate_pct DESC, avg_speed_tps DESC;
    """
    cursor.execute(query, (min_questions,))
    rows = cursor.fetchall()
    return [dict(r) for r in rows]


# ==============================================================================
# CLI Entry Point
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="benchmark_store.py - Relational SQLite Persistence Store Manager"
    )
    parser.add_argument("--db", default=DEFAULT_DB_PATH, help=f"Path to SQLite database file. Default: {DEFAULT_DB_PATH}")
    parser.add_argument("--init", action="store_true", help="Initialize database schema and DDL.")
    parser.add_argument("--sync-questions", default=None, nargs="?", const="Questions/*.xml",
                        help="Sync questions and assertions from XML suite into database.")
    parser.add_argument("--stats", action="store_true", help="Print table row counts and database health.")
    parser.add_argument("--matrix", action="store_true", help="Print comparative matrix from latest model runs.")
    parser.add_argument("--min-questions", type=int, default=10, help="Minimum questions in a run to be considered in matrix. Default: 10")

    args = parser.parse_args()

    # Always ensure tables exist
    conn = init_db(args.db)

    if args.init:
        print(f"Database initialized successfully at: {os.path.abspath(args.db)}")

    if args.sync_questions:
        q_pattern = args.sync_questions
        q_map = sync_questions_from_xml(conn, q_pattern)
        print(f"Synchronized {len(q_map)} question(s) from '{q_pattern}' into '{args.db}'.")

    if args.stats or (not args.init and not args.sync_questions and not args.matrix):
        stats = get_stats(conn)
        print("\n" + "=" * 50)
        print(f"  Benchmark Database Status: {os.path.abspath(args.db)}")
        print("=" * 50)
        for tbl, count in stats.items():
            print(f"  {tbl:<22} : {count:>6} rows")
        print("=" * 50 + "\n")

    if args.matrix:
        matrix = get_latest_matrix(conn, min_questions=args.min_questions)
        print("\n" + "=" * 80)
        print("  LATEST BENCHMARK MATRIX (SQLite)")
        print("=" * 80)
        print(f"{'Model':<24} | {'Solved':<10} | {'Pass %':<8} | {'Avg Speed':<12} | {'Latency':<10}")
        print("-" * 80)
        for row in matrix:
            q_str = f"{row['questions_solved']}/{row['total_questions']}"
            pct_str = f"{row['pass_rate_pct']}%"
            spd_str = f"{row['avg_speed_tps']} tok/s"
            lat_str = f"{row['total_latency_sec']}s"
            print(f"{row['model_name']:<24} | {q_str:<10} | {pct_str:<8} | {spd_str:<12} | {lat_str:<10}")
        print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
