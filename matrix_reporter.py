#!/usr/bin/env python3
"""
matrix_reporter.py - Multi-Dimensional Matrix & Comparative Analytics Engine

Implements Phase 4 of the roadmap:
  1. Model x Question Pass/Fail Discrimination Heatmap Matrix (M x N)
  2. Cognitive Tier Breakdown Matrix (Tiers 1-4)
  3. Pareto Efficiency Frontier (Speed vs. Accuracy) with 2D ASCII Plot
  4. Regression & Delta Engine (Detecting regressions and tracking performance deltas)
  5. Multi-format Exporters (Console ANSI, GitHub Markdown, and JSON)

Zero external pip dependencies: strictly uses Python standard library.
"""

import argparse
import json
import os
import sqlite3
import sys
import time
from typing import Dict, List, Any, Optional, Tuple, Set


# ==============================================================================
# Console Colors & Formatting
# ==============================================================================

class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    MAGENTA = "\033[95m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"

    @classmethod
    def disable(cls):
        cls.GREEN = ""
        cls.RED = ""
        cls.YELLOW = ""
        cls.BLUE = ""
        cls.CYAN = ""
        cls.MAGENTA = ""
        cls.BOLD = ""
        cls.DIM = ""
        cls.RESET = ""


# ==============================================================================
# Database Access & Analytical Queries
# ==============================================================================

DEFAULT_DB_PATH = "benchmark.db"


def get_db_connection(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Connects to SQLite database with Row factory."""
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Benchmark database not found at: {db_path}")
    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn


def get_latest_qualifying_runs(conn: sqlite3.Connection,
                                min_questions: int = 10,
                                model_filter: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """
    Retrieves the latest qualifying benchmark run for each model.
    Filters by minimum questions (default: 10) to avoid ad-hoc smoke tests.
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
        SELECT qr.model_id, qr.run_id, qr.timestamp, qr.q_count
        FROM qualifying_runs qr
        WHERE qr.run_id = (
            SELECT MAX(qr2.run_id)
            FROM qualifying_runs qr2
            WHERE qr2.model_id = qr.model_id
        )
    )
    SELECT
        m.id AS model_id,
        m.name AS model_name,
        m.family,
        m.parameter_size,
        lr.run_id,
        lr.timestamp AS run_timestamp,
        lr.q_count AS total_questions,
        SUM(tr.passed) AS questions_solved,
        ROUND((CAST(SUM(tr.passed) AS REAL) / COUNT(tr.id)) * 100, 1) AS pass_rate_pct,
        ROUND(AVG(tr.eval_tokens_per_sec), 2) AS avg_speed_tps,
        ROUND(SUM(tr.latency_sec), 2) AS total_latency_sec
    FROM latest_runs lr
    JOIN test_results tr ON tr.model_id = lr.model_id AND tr.run_id = lr.run_id
    JOIN models m ON m.id = lr.model_id
    GROUP BY m.id, lr.run_id, lr.timestamp, lr.q_count
    ORDER BY pass_rate_pct DESC, avg_speed_tps DESC;
    """
    cursor.execute(query, (min_questions,))
    rows = [dict(r) for r in cursor.fetchall()]

    if model_filter:
        lower_filter = [m.lower().strip() for m in model_filter]
        rows = [r for r in rows if r["model_name"].lower() in lower_filter]

    return rows


def get_all_active_questions(conn: sqlite3.Connection, include_archived: bool = False) -> List[Dict[str, Any]]:
    """Retrieves active questions ordered by Cognitive Tier and question ID."""
    cursor = conn.cursor()
    filter_sql = "" if include_archived else "WHERE q.suite_id IS NOT NULL"
    query = f"""
    SELECT q.id, q.test_id, q.tier, q.category, q.difficulty, q.question_text, ts.name AS suite_name
    FROM questions q
    LEFT JOIN test_suites ts ON q.suite_id = ts.id
    {filter_sql}
    ORDER BY q.tier ASC, q.test_id ASC;
    """
    cursor.execute(query)
    return [dict(r) for r in cursor.fetchall()]


# ==============================================================================
# Analytical Engines
# ==============================================================================

def build_model_question_matrix(conn: sqlite3.Connection,
                                 latest_runs: List[Dict[str, Any]],
                                 questions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Builds the M x N Model x Question Pass/Fail Discrimination Matrix.
    Classifies each probe as Universal Baseline, Universal Bottleneck, or High-Discrimination.
    """
    if not latest_runs:
        return {"models": [], "questions": [], "matrix": {}, "discrimination": {}}

    cursor = conn.cursor()
    run_ids = [r["run_id"] for r in latest_runs]
    placeholders = ",".join("?" for _ in run_ids)

    query = f"""
    SELECT tr.run_id, m.name AS model_name, q.test_id, tr.passed, tr.eval_tokens_per_sec, tr.latency_sec
    FROM test_results tr
    JOIN models m ON tr.model_id = m.id
    JOIN questions q ON tr.question_id = q.id
    WHERE tr.run_id IN ({placeholders})
    """
    cursor.execute(query, run_ids)
    test_rows = cursor.fetchall()

    # Index results: {test_id: {model_name: dict}}
    raw_matrix: Dict[str, Dict[str, Any]] = {}
    for row in test_rows:
        tid = row["test_id"]
        mname = row["model_name"]
        if tid not in raw_matrix:
            raw_matrix[tid] = {}
        raw_matrix[tid][mname] = {
            "passed": bool(row["passed"]),
            "eval_tps": row["eval_tokens_per_sec"],
            "latency": row["latency_sec"]
        }

    # Discrimination classification
    discrimination: Dict[str, Dict[str, Any]] = {}
    model_names = [r["model_name"] for r in latest_runs]

    for q in questions:
        tid = q["test_id"]
        tested_statuses = []
        for mname in model_names:
            if mname in raw_matrix.get(tid, {}):
                tested_statuses.append(raw_matrix[tid][mname]["passed"])

        tested_count = len(tested_statuses)
        passed_count = sum(1 for s in tested_statuses if s)

        if tested_count == 0:
            category = "UNTESTED"
            label = "Untested"
        elif passed_count == tested_count:
            category = "BASELINE"
            label = "Universal Baseline"
        elif passed_count == 0:
            category = "BOTTLENECK"
            label = "Universal Bottleneck"
        else:
            category = "DISCRIMINATION"
            label = "High Discrimination"

        discrimination[tid] = {
            "category": category,
            "label": label,
            "passed_count": passed_count,
            "tested_count": tested_count,
            "pass_rate_pct": round((passed_count / tested_count) * 100, 1) if tested_count > 0 else 0.0
        }

    return {
        "models": latest_runs,
        "questions": questions,
        "matrix": raw_matrix,
        "discrimination": discrimination
    }


def build_tier_breakdown_matrix(conn: sqlite3.Connection,
                                 latest_runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Computes pass rates and counts across Cognitive Tiers (Tier 1-4) for each evaluated model.
    """
    if not latest_runs:
        return {}

    cursor = conn.cursor()
    run_ids = [r["run_id"] for r in latest_runs]
    placeholders = ",".join("?" for _ in run_ids)

    query = f"""
    SELECT m.name AS model_name, q.tier, COUNT(tr.id) AS total_evaluated, SUM(tr.passed) AS total_passed
    FROM test_results tr
    JOIN models m ON tr.model_id = m.id
    JOIN questions q ON tr.question_id = q.id
    WHERE tr.run_id IN ({placeholders})
    GROUP BY m.name, q.tier
    ORDER BY m.name, q.tier;
    """
    cursor.execute(query, run_ids)
    rows = cursor.fetchall()

    breakdown: Dict[str, Dict[str, Any]] = {}
    for r in latest_runs:
        mname = r["model_name"]
        breakdown[mname] = {
            "model_name": mname,
            "overall_solved": r["questions_solved"],
            "overall_total": r["total_questions"],
            "overall_pct": r["pass_rate_pct"],
            "tiers": {
                1: {"passed": 0, "total": 0, "pct": 0.0},
                2: {"passed": 0, "total": 0, "pct": 0.0},
                3: {"passed": 0, "total": 0, "pct": 0.0},
                4: {"passed": 0, "total": 0, "pct": 0.0},
            }
        }

    for row in rows:
        mname = row["model_name"]
        tier = row["tier"] or 1
        tot = row["total_evaluated"]
        pas = row["total_passed"]
        pct = round((pas / tot) * 100, 1) if tot > 0 else 0.0
        if mname in breakdown and tier in breakdown[mname]["tiers"]:
            breakdown[mname]["tiers"][tier] = {"passed": pas, "total": tot, "pct": pct}

    return breakdown


def compute_pareto_frontier(latest_runs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Computes the Pareto Efficiency Frontier (Throughput tok/s vs. Benchmark Accuracy %).
    A model M is Pareto optimal if no other model dominates it (>= in both metrics, > in at least one).
    """
    models_data = []
    for r in latest_runs:
        models_data.append({
            "name": r["model_name"],
            "family": r.get("family", "Other"),
            "parameter_size": r.get("parameter_size", "-"),
            "speed_tps": r["avg_speed_tps"],
            "pass_rate_pct": r["pass_rate_pct"],
            "latency": r.get("total_latency_sec", 0.0),
            "solved": r["questions_solved"],
            "total": r["total_questions"],
            "is_pareto": True,
            "dominated_by": []
        })

    for i, m in enumerate(models_data):
        s = m["speed_tps"]
        a = m["pass_rate_pct"]
        for j, other in enumerate(models_data):
            if i == j:
                continue
            s_o = other["speed_tps"]
            a_o = other["pass_rate_pct"]
            if (s_o >= s and a_o >= a) and (s_o > s or a_o > a):
                m["is_pareto"] = False
                m["dominated_by"].append(other["name"])

    return models_data


def compare_runs_regression(conn: sqlite3.Connection,
                             run_id_a: int,
                             run_id_b: int) -> Dict[str, Any]:
    """
    Compares two benchmark runs (e.g. baseline run A vs candidate run B) to detect:
      - Regressions (PASS in A -> FAIL in B)
      - Improvements (FAIL in A -> PASS in B)
      - Throughput, latency, and assertion deltas
    """
    cursor = conn.cursor()

    # Fetch run metadata
    cursor.execute("""
        SELECT r.id, r.timestamp, m.name as model_name,
               COUNT(tr.id) as q_count, SUM(tr.passed) as passed_count,
               AVG(tr.eval_tokens_per_sec) as avg_speed, SUM(tr.latency_sec) as total_lat
        FROM benchmark_runs r
        JOIN test_results tr ON tr.run_id = r.id
        JOIN models m ON tr.model_id = m.id
        WHERE r.id IN (?, ?)
        GROUP BY r.id
    """, (run_id_a, run_id_b))
    run_meta = {r["id"]: dict(r) for r in cursor.fetchall()}

    if run_id_a not in run_meta or run_id_b not in run_meta:
        raise ValueError(f"One or both run IDs ({run_id_a}, {run_id_b}) could not be resolved in database.")

    # Fetch question-by-question outcomes
    query_cases = """
    SELECT tr.run_id, q.test_id, q.tier, q.category, tr.passed, tr.latency_sec, tr.eval_tokens_per_sec, tr.raw_output
    FROM test_results tr
    JOIN questions q ON tr.question_id = q.id
    WHERE tr.run_id IN (?, ?)
    """
    cursor.execute(query_cases, (run_id_a, run_id_b))

    cases_a = {}
    cases_b = {}
    for r in cursor.fetchall():
        if r["run_id"] == run_id_a:
            cases_a[r["test_id"]] = dict(r)
        else:
            cases_b[r["test_id"]] = dict(r)

    regressions = []
    improvements = []
    persistent_passes = []
    persistent_fails = []
    common_questions = sorted(set(cases_a.keys()).intersection(set(cases_b.keys())))

    for qid in common_questions:
        pass_a = bool(cases_a[qid]["passed"])
        pass_b = bool(cases_b[qid]["passed"])
        tier = cases_b[qid]["tier"]

        if pass_a and not pass_b:
            regressions.append({
                "test_id": qid,
                "tier": tier,
                "output_a": cases_a[qid].get("raw_output", "")[:100],
                "output_b": cases_b[qid].get("raw_output", "")[:100]
            })
        elif not pass_a and pass_b:
            improvements.append({
                "test_id": qid,
                "tier": tier,
                "output_a": cases_a[qid].get("raw_output", "")[:100],
                "output_b": cases_b[qid].get("raw_output", "")[:100]
            })
        elif pass_a and pass_b:
            persistent_passes.append(qid)
        else:
            persistent_fails.append(qid)

    meta_a = run_meta[run_id_a]
    meta_b = run_meta[run_id_b]

    acc_a = (meta_a["passed_count"] / meta_a["q_count"] * 100) if meta_a["q_count"] else 0.0
    acc_b = (meta_b["passed_count"] / meta_b["q_count"] * 100) if meta_b["q_count"] else 0.0

    speed_a = meta_a["avg_speed"] or 0.0
    speed_b = meta_b["avg_speed"] or 0.0

    lat_a = meta_a["total_lat"] or 0.0
    lat_b = meta_b["total_lat"] or 0.0

    return {
        "run_a": meta_a,
        "run_b": meta_b,
        "delta": {
            "accuracy_pct": round(acc_b - acc_a, 1),
            "speed_tps": round(speed_b - speed_a, 2),
            "latency_sec": round(lat_b - lat_a, 2),
            "solved_count": meta_b["passed_count"] - meta_a["passed_count"]
        },
        "regressions": regressions,
        "improvements": improvements,
        "persistent_passes_count": len(persistent_passes),
        "persistent_fails_count": len(persistent_fails),
        "evaluated_in_both": len(common_questions)
    }


def find_latest_two_runs_for_model(conn: sqlite3.Connection, model_name: str) -> Tuple[int, int]:
    """Finds the last two benchmark runs for a given model to run regression check."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT tr.run_id
        FROM test_results tr
        JOIN models m ON tr.model_id = m.id
        WHERE m.name = ?
        ORDER BY tr.run_id DESC
        LIMIT 2
    """, (model_name,))
    rows = cursor.fetchall()
    if len(rows) < 2:
        raise ValueError(f"Model '{model_name}' has only {len(rows)} run(s) recorded. Minimum 2 runs required for delta check.")
    return rows[1][0], rows[0][0]


# ==============================================================================
# Rendering & Visual Formatters
# ==============================================================================

def render_ascii_pareto_plot(models_data: List[Dict[str, Any]], width: int = 68, height: int = 14) -> str:
    """Renders a 2D ASCII scatter plot of Throughput vs Accuracy."""
    if not models_data:
        return "No model data available for plot."

    max_x = max(m["speed_tps"] for m in models_data)
    max_x = max(max_x * 1.15, 60.0)
    min_x = 0.0
    min_y = 0.0
    max_y = 100.0

    grid = [[" " for _ in range(width)] for _ in range(height)]
    legend = []

    for idx, m in enumerate(models_data, 1):
        x_val = m["speed_tps"]
        y_val = m["pass_rate_pct"]

        col = int((x_val - min_x) / (max_x - min_x) * (width - 1))
        row = height - 1 - int((y_val - min_y) / (max_y - min_y) * (height - 1))
        col = max(0, min(width - 1, col))
        row = max(0, min(height - 1, row))

        marker = str(idx) if idx < 10 else chr(ord('A') + idx - 10)
        grid[row][col] = marker
        star = " ★ PARETO OPTIMAL" if m["is_pareto"] else ""
        legend.append(f"  [{marker}] {m['name']:<22} | Speed: {x_val:>5.1f} tok/s | Acc: {y_val:>5.1f}%{star}")

    lines = []
    lines.append("   Accuracy (%)")
    lines.append("   ^")
    for r in range(height):
        y_label = 100 - int(r * (100 / (height - 1)))
        row_str = "".join(grid[r])
        lines.append(f"{y_label:>3}| {row_str}")
    lines.append("   +" + "-" * width + "> Throughput (tok/s)")
    lines.append(f"    0{' ' * (width - 10)}{max_x:>6.1f}")
    lines.append("\n  Legend & Pareto Analysis:")
    lines.extend(legend)
    return "\n".join(lines)


def format_matrix_terminal(matrix_data: Dict[str, Any], use_color: bool = True) -> str:
    """Formats the M x N discrimination matrix for terminal display."""
    models = matrix_data["models"]
    questions = matrix_data["questions"]
    matrix = matrix_data["matrix"]
    discrim = matrix_data["discrimination"]

    if not models or not questions:
        return "No data to display in matrix."

    lines = []
    title = "MODEL x QUESTION DISCRIMINATION MATRIX (M x N HEATMAP)"
    lines.append(f"\n{Colors.BOLD}{Colors.CYAN}{'='*112}{Colors.RESET}")
    lines.append(f"{Colors.BOLD}{title:^112}{Colors.RESET}")
    lines.append(f"{Colors.BOLD}{Colors.CYAN}{'='*112}{Colors.RESET}")

    # Header
    col_w = 12
    hdr = f"{'Question ID':<26} | {'Tier':<4} | " + " | ".join(f"{m['model_name'][:col_w]:^{col_w}}" for m in models) + " | Discrimination"
    lines.append(hdr)
    lines.append("-" * len(hdr))

    current_tier = None
    for q in questions:
        tid = q["test_id"]
        tier = q["tier"] or 1

        # Tier separator
        if tier != current_tier:
            current_tier = tier
            lines.append(f"{Colors.DIM}--- [Tier {current_tier}: {q['category'].replace('_', ' ').title()}] {'-'*75}{Colors.RESET}")

        cells = []
        for m in models:
            mname = m["model_name"]
            res = matrix.get(tid, {}).get(mname)
            if res is None:
                cells.append(f"{Colors.DIM}{'-':^{col_w}}{Colors.RESET}")
            elif res["passed"]:
                val = f"{Colors.GREEN}PASS{Colors.RESET}" if use_color else "PASS"
                cells.append(f"{val:^{col_w + (len(val) - 4)}}")
            else:
                val = f"{Colors.RED}FAIL{Colors.RESET}" if use_color else "FAIL"
                cells.append(f"{val:^{col_w + (len(val) - 4)}}")

        d_info = discrim.get(tid, {})
        d_cat = d_info.get("category", "")
        if d_cat == "BASELINE":
            d_tag = f"{Colors.GREEN}Baseline (100%){Colors.RESET}" if use_color else "Baseline (100%)"
        elif d_cat == "BOTTLENECK":
            d_tag = f"{Colors.RED}Bottleneck (0%){Colors.RESET}" if use_color else "Bottleneck (0%)"
        else:
            pct = d_info.get("pass_rate_pct", 0)
            d_tag = f"{Colors.YELLOW}Split ({pct:.0f}%){Colors.RESET}" if use_color else f"Split ({pct:.0f}%)"

        short_tid = tid[:25]
        row_str = f"{short_tid:<26} | T{tier:<3} | " + " | ".join(cells) + f" | {d_tag}"
        lines.append(row_str)

    # Footer metrics
    lines.append("-" * len(hdr))
    q_solved_cells = [f"{str(m['questions_solved']) + '/' + str(m['total_questions']):^{col_w}}" for m in models]
    lines.append(f"{'Questions Solved':<26} |      | " + " | ".join(q_solved_cells) + " |")

    pass_rate_cells = []
    for m in models:
        pct = m['pass_rate_pct']
        color = Colors.GREEN if pct >= 90 else (Colors.YELLOW if pct >= 70 else Colors.RED)
        raw_str = f"{pct:.1f}%"
        val = f"{color}{raw_str}{Colors.RESET}" if use_color else raw_str
        pass_rate_cells.append(f"{val:^{col_w + (len(val) - len(raw_str))}}")
    lines.append(f"{'Overall Pass Rate':<26} |      | " + " | ".join(pass_rate_cells) + " |")

    speed_cells = [f"{str(round(m['avg_speed_tps'], 1)) + ' tok/s':^{col_w}}" for m in models]
    lines.append(f"{'Avg Speed':<26} |      | " + " | ".join(speed_cells) + " |")
    lines.append(f"{Colors.BOLD}{Colors.CYAN}{'='*112}{Colors.RESET}\n")

    return "\n".join(lines)


def format_tier_terminal(tier_data: Dict[str, Any], use_color: bool = True) -> str:
    """Formats the Cognitive Tier breakdown table for terminal display."""
    lines = []
    title = "COGNITIVE TAXONOMY TIER BREAKDOWN (TIERS 1 - 4)"
    lines.append(f"\n{Colors.BOLD}{Colors.CYAN}{'='*96}{Colors.RESET}")
    lines.append(f"{Colors.BOLD}{title:^96}{Colors.RESET}")
    lines.append(f"{Colors.BOLD}{Colors.CYAN}{'='*96}{Colors.RESET}")
    header = f"{'Model':<22} | {'Tier 1 (Factual)':<16} | {'Tier 2 (Reasoning)':<18} | {'Tier 3 (Illusion)':<17} | {'Tier 4 (Hard)':<13}"
    lines.append(header)
    lines.append("-" * 96)

    for mname, data in tier_data.items():
        t1 = data["tiers"].get(1, {})
        t2 = data["tiers"].get(2, {})
        t3 = data["tiers"].get(3, {})
        t4 = data["tiers"].get(4, {})

        t1_str = f"{t1.get('passed',0)}/{t1.get('total',0)} ({t1.get('pct',0):.0f}%)"
        t2_str = f"{t2.get('passed',0)}/{t2.get('total',0)} ({t2.get('pct',0):.0f}%)"
        t3_str = f"{t3.get('passed',0)}/{t3.get('total',0)} ({t3.get('pct',0):.0f}%)"
        t4_str = f"{t4.get('passed',0)}/{t4.get('total',0)} ({t4.get('pct',0):.0f}%)"

        lines.append(f"{mname:<22} | {t1_str:<16} | {t2_str:<18} | {t3_str:<17} | {t4_str:<13}")

    lines.append(f"{Colors.BOLD}{Colors.CYAN}{'='*96}{Colors.RESET}\n")
    return "\n".join(lines)


def format_pareto_terminal(pareto_models: List[Dict[str, Any]], use_color: bool = True) -> str:
    """Formats Pareto Efficiency analysis and ASCII scatter plot for terminal display."""
    lines = []
    title = "PARETO EFFICIENCY FRONTIER (SPEED vs. ACCURACY)"
    lines.append(f"\n{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.RESET}")
    lines.append(f"{Colors.BOLD}{title:^80}{Colors.RESET}")
    lines.append(f"{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.RESET}")

    plot_str = render_ascii_pareto_plot(pareto_models, width=64, height=13)
    lines.append(plot_str)

    lines.append("\nPareto Frontier Classification:")
    lines.append(f"{'Model':<24} | {'Throughput':<12} | {'Accuracy':<10} | {'Status'}")
    lines.append("-" * 80)
    for m in pareto_models:
        status = f"{Colors.GREEN}★ PARETO OPTIMAL{Colors.RESET}" if (m["is_pareto"] and use_color) else ("★ PARETO OPTIMAL" if m["is_pareto"] else f"Dominated by {', '.join(m['dominated_by'][:2])}")
        lines.append(f"{m['name']:<24} | {m['speed_tps']:>6.1f} tok/s | {m['pass_rate_pct']:>6.1f}%   | {status}")

    lines.append(f"{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.RESET}\n")
    return "\n".join(lines)


def format_regression_terminal(delta_report: Dict[str, Any], use_color: bool = True) -> str:
    """Formats a regression delta comparison between two runs."""
    ra = delta_report["run_a"]
    rb = delta_report["run_b"]
    d = delta_report["delta"]
    regs = delta_report["regressions"]
    imps = delta_report["improvements"]

    lines = []
    title = f"BENCHMARK DELTA & REGRESSION REPORT: Run #{ra['id']} vs. Run #{rb['id']}"
    lines.append(f"\n{Colors.BOLD}{Colors.CYAN}{'='*88}{Colors.RESET}")
    lines.append(f"{Colors.BOLD}{title:^88}{Colors.RESET}")
    lines.append(f"{Colors.BOLD}{Colors.CYAN}{'='*88}{Colors.RESET}")

    lines.append(f"Model: {Colors.BOLD}{rb['model_name']}{Colors.RESET}")
    lines.append(f"Baseline Run:  #{ra['id']} ({ra['timestamp']}) - Solved {ra['passed_count']}/{ra['q_count']} ({ra['passed_count']/ra['q_count']*100:.1f}%) | {ra['avg_speed']:.1f} tok/s")
    lines.append(f"Candidate Run: #{rb['id']} ({rb['timestamp']}) - Solved {rb['passed_count']}/{rb['q_count']} ({rb['passed_count']/rb['q_count']*100:.1f}%) | {rb['avg_speed']:.1f} tok/s")

    acc_sign = "+" if d["accuracy_pct"] >= 0 else ""
    spd_sign = "+" if d["speed_tps"] >= 0 else ""
    lines.append(f"\nPerformance Delta: Accuracy: {acc_sign}{d['accuracy_pct']}% | Speed: {spd_sign}{d['speed_tps']} tok/s | Latency: {d['latency_sec']}s")

    lines.append("\n" + "-" * 88)
    if regs:
        tag = f"{Colors.RED}⚠️ REGRESSIONS DETECTED ({len(regs)}){Colors.RESET}" if use_color else f"⚠️ REGRESSIONS DETECTED ({len(regs)})"
        lines.append(tag)
        for r in regs:
            lines.append(f"  [-] [{r['test_id']}] (Tier {r['tier']}) - Previously PASSED, now FAILED!")
            lines.append(f"      Candidate Output: {r['output_b']}")
    else:
        tag = f"{Colors.GREEN}✅ ZERO REGRESSIONS: No previously passing questions regressed.{Colors.RESET}" if use_color else "✅ ZERO REGRESSIONS"
        lines.append(tag)

    if imps:
        tag = f"{Colors.GREEN}🚀 IMPROVEMENTS ({len(imps)}){Colors.RESET}" if use_color else f"🚀 IMPROVEMENTS ({len(imps)})"
        lines.append(tag)
        for im in imps:
            lines.append(f"  [+] [{im['test_id']}] (Tier {im['tier']}) - Previously FAILED, now PASSED!")

    lines.append(f"\nShared Probes Tested: {delta_report['evaluated_in_both']} | Persistent Passes: {delta_report['persistent_passes_count']} | Persistent Fails: {delta_report['persistent_fails_count']}")
    lines.append(f"{Colors.BOLD}{Colors.CYAN}{'='*88}{Colors.RESET}\n")

    return "\n".join(lines)


# ==============================================================================
# Markdown & JSON Exporters
# ==============================================================================

def export_markdown_report(matrix_data: Dict[str, Any],
                           tier_data: Dict[str, Any],
                           pareto_data: List[Dict[str, Any]],
                           output_path: str,
                           regression_data: Optional[Dict[str, Any]] = None) -> str:
    """Exports a comprehensive multi-dimensional report to Markdown."""
    models = matrix_data["models"]
    questions = matrix_data["questions"]
    matrix = matrix_data["matrix"]
    discrim = matrix_data["discrimination"]

    timestamp_str = time.strftime("%Y-%m-%d %H:%M:%S")
    md = [
        "# LLM Benchmark Discrimination Matrix & Comparative Analytics",
        f"*Generated at: {timestamp_str} | Relational Persistence: `benchmark.db`*\n",
        "## 1. Executive Summary & Pareto Efficiency Frontier\n",
        "| Model | Family | Parameter Size | Questions Solved | Pass Rate | Generation Speed | Latency | Pareto Status |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |"
    ]

    for p in pareto_data:
        p_status = "**★ Pareto Optimal**" if p["is_pareto"] else f"Dominated by {p['dominated_by'][0]}"
        md.append(f"| **{p['name']}** | {p['family']} | {p.get('parameter_size','-')} | {p['solved']}/{p['total']} | **{p['pass_rate_pct']}%** | {p['speed_tps']} tok/s | {p.get('latency', '-')}s | {p_status} |")

    md.append("\n### Pareto Efficiency Scatter Plot (Speed vs. Accuracy)\n")
    md.append("```text")
    md.append(render_ascii_pareto_plot(pareto_data, width=64, height=14))
    md.append("```\n")

    # Section 2: Cognitive Tier Breakdown
    md.append("## 2. 4-Tier Cognitive Taxonomy Breakdown\n")
    md.append("| Model | Tier 1 (Basic & Code) | Tier 2 (Multi-Step Reasoning) | Tier 3 (Illusion Resilience) | Tier 4 (Tokenizer & Hard) | Overall Solved |")
    md.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
    for mname, data in tier_data.items():
        t1 = data["tiers"].get(1, {})
        t2 = data["tiers"].get(2, {})
        t3 = data["tiers"].get(3, {})
        t4 = data["tiers"].get(4, {})
        t1_s = f"{t1.get('passed',0)}/{t1.get('total',0)} ({t1.get('pct',0):.0f}%)"
        t2_s = f"{t2.get('passed',0)}/{t2.get('total',0)} ({t2.get('pct',0):.0f}%)"
        t3_s = f"{t3.get('passed',0)}/{t3.get('total',0)} ({t3.get('pct',0):.0f}%)"
        t4_s = f"{t4.get('passed',0)}/{t4.get('total',0)} ({t4.get('pct',0):.0f}%)"
        ov_s = f"**{data['overall_solved']}/{data['overall_total']} ({data['overall_pct']}%)**"
        md.append(f"| **{mname}** | {t1_s} | {t2_s} | {t3_s} | {t4_s} | {ov_s} |")

    # Section 3: Model x Question Pass/Fail Matrix
    md.append("\n## 3. Model $\\times$ Question Discrimination Heatmap Matrix\n")
    model_headers = " | ".join(f"`{m['model_name']}`" for m in models)
    align_bars = " | ".join(":---:" for _ in models)
    md.append(f"| Question ID | Tier | {model_headers} | Probe Classification |")
    md.append(f"| :--- | :--- | {align_bars} | :--- |")

    for q in questions:
        tid = q["test_id"]
        tier = q["tier"] or 1
        cells = []
        for m in models:
            mname = m["model_name"]
            res = matrix.get(tid, {}).get(mname)
            if res is None:
                cells.append("`-`")
            elif res["passed"]:
                cells.append("✅ PASS")
            else:
                cells.append("❌ FAIL")

        d_info = discrim.get(tid, {})
        d_cat = d_info.get("category", "")
        if d_cat == "BASELINE":
            d_label = "🟢 **Baseline (100%)**"
        elif d_cat == "BOTTLENECK":
            d_label = "🔴 **Bottleneck (0%)**"
        else:
            pct = d_info.get("pass_rate_pct", 0)
            d_label = f"⚡ **High-Discrim ({pct:.0f}%)**"

        md.append(f"| `{tid}` | T{tier} | {' | '.join(cells)} | {d_label} |")

    # Section 4: Regression Report if available
    if regression_data:
        md.append("\n## 4. Regression & Delta Engine Analysis\n")
        ra = regression_data["run_a"]
        rb = regression_data["run_b"]
        d = regression_data["delta"]
        regs = regression_data["regressions"]
        imps = regression_data["improvements"]

        md.append(f"- **Target Model**: `{rb['model_name']}`")
        md.append(f"- **Baseline Run**: `#{ra['id']}` ({ra['timestamp']}) - Solved {ra['passed_count']}/{ra['q_count']} ({ra['passed_count']/ra['q_count']*100:.1f}%)")
        md.append(f"- **Candidate Run**: `#{rb['id']}` ({rb['timestamp']}) - Solved {rb['passed_count']}/{rb['q_count']} ({rb['passed_count']/rb['q_count']*100:.1f}%)")
        md.append(f"- **Delta**: Accuracy: `{d['accuracy_pct']:+}%` | Speed: `{d['speed_tps']:+} tok/s` | Latency: `{d['latency_sec']}s`\n")

        if regs:
            md.append("### ⚠️ Regressions Detected\n")
            md.append("| Question ID | Tier | Candidate Output Snippet |")
            md.append("| :--- | :--- | :--- |")
            for r in regs:
                md.append(f"| `{r['test_id']}` | Tier {r['tier']} | `{r['output_b'].strip().replace(chr(10), ' ')}` |")
        else:
            md.append("> [!TIP]\n> **Zero Regressions**: No previously passing questions regressed in this candidate run.\n")

        if imps:
            md.append("\n### 🚀 New Improvements\n")
            md.append("| Question ID | Tier | Candidate Output Snippet |")
            md.append("| :--- | :--- | :--- |")
            for im in imps:
                md.append(f"| `{im['test_id']}` | Tier {im['tier']} | `{im['output_b'].strip().replace(chr(10), ' ')}` |")

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md))

    return output_path


def export_json_report(matrix_data: Dict[str, Any],
                       tier_data: Dict[str, Any],
                       pareto_data: List[Dict[str, Any]],
                       output_path: str,
                       regression_data: Optional[Dict[str, Any]] = None) -> str:
    """Exports structured JSON representation of the comparative analytics for web UI ingestion."""
    payload = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "models": matrix_data["models"],
        "questions": matrix_data["questions"],
        "matrix": matrix_data["matrix"],
        "discrimination": matrix_data["discrimination"],
        "tier_breakdown": tier_data,
        "pareto_frontier": pareto_data,
        "regression_delta": regression_data
    }
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return output_path


# ==============================================================================
# CLI Entry Point
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="matrix_reporter.py - Multi-Dimensional Matrix & Comparative Analytics Engine"
    )
    parser.add_argument("--db", default=DEFAULT_DB_PATH, help=f"Path to SQLite database file. Default: '{DEFAULT_DB_PATH}'")
    parser.add_argument("--matrix", action="store_true", help="Display the M x N Model x Question pass/fail discrimination matrix.")
    parser.add_argument("--tiers", action="store_true", help="Display the Cognitive Taxonomy Tier breakdown table.")
    parser.add_argument("--pareto", action="store_true", help="Display the Pareto Efficiency Frontier and 2D ASCII plot.")
    parser.add_argument("--diff", nargs=2, type=int, metavar=("RUN_A", "RUN_B"), help="Compare two run IDs for regressions and deltas.")
    parser.add_argument("--regressions", nargs="?", const="all", metavar="MODEL", help="Check regressions across latest two runs of a model (or 'all').")
    parser.add_argument("--min-questions", type=int, default=10, help="Minimum questions in run to qualify for multi-model matrix. Default: 10")
    parser.add_argument("--models", help="Comma-separated list of model names to include in comparison.")
    parser.add_argument("--export-md", nargs="?", const="AUTO", help="Export Markdown report to specified path or auto timestamped file.")
    parser.add_argument("--export-json", nargs="?", const="AUTO", help="Export JSON data to specified path or auto timestamped file.")
    parser.add_argument("--include-archived", action="store_true", help="Include archived historical questions (suite_id IS NULL).")
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI color codes in console output.")
    parser.add_argument("--all", action="store_true", help="Run full analysis suite and export reports.")

    args = parser.parse_args()

    if args.no_color or not sys.stdout.isatty():
        Colors.disable()

    conn = get_db_connection(args.db)

    # Resolve model filter
    model_filter = [m.strip() for m in args.models.split(",") if m.strip()] if args.models else None

    # Default action if no specific action selected
    run_all = args.all or (not args.matrix and not args.tiers and not args.pareto and not args.diff and not args.regressions)

    # 1. Gather Data
    latest_runs = get_latest_qualifying_runs(conn, min_questions=args.min_questions, model_filter=model_filter)
    questions = get_all_active_questions(conn, include_archived=args.include_archived)

    matrix_data = build_model_question_matrix(conn, latest_runs, questions)
    tier_data = build_tier_breakdown_matrix(conn, latest_runs)
    pareto_data = compute_pareto_frontier(latest_runs)

    # Optional regression diff
    regression_report = None
    if args.diff:
        run_a, run_b = args.diff
        regression_report = compare_runs_regression(conn, run_a, run_b)
        print(format_regression_terminal(regression_report, use_color=not args.no_color))
    elif args.regressions:
        target_model = args.regressions
        if target_model.lower() == "all":
            print(f"\n{Colors.BOLD}{Colors.CYAN}--- Multi-Model Regression Sweep ---{Colors.RESET}")
            for m in latest_runs:
                mname = m["model_name"]
                try:
                    ra, rb = find_latest_two_runs_for_model(conn, mname)
                    r_rep = compare_runs_regression(conn, ra, rb)
                    regs = len(r_rep["regressions"])
                    status = f"{Colors.RED}{regs} regression(s){Colors.RESET}" if regs > 0 else f"{Colors.GREEN}0 regressions{Colors.RESET}"
                    print(f"  [{mname:<22}] Runs #{ra} -> #{rb}: {status}")
                except Exception as e:
                    print(f"  [{mname:<22}] Skipped: {e}")
            print()
        else:
            try:
                ra, rb = find_latest_two_runs_for_model(conn, target_model)
                regression_report = compare_runs_regression(conn, ra, rb)
                print(format_regression_terminal(regression_report, use_color=not args.no_color))
            except Exception as e:
                print(f"{Colors.RED}Regression check error for '{target_model}': {e}{Colors.RESET}", file=sys.stderr)

    # 2. Display Views
    if run_all or args.matrix:
        print(format_matrix_terminal(matrix_data, use_color=not args.no_color))

    if run_all or args.tiers:
        print(format_tier_terminal(tier_data, use_color=not args.no_color))

    if run_all or args.pareto:
        print(format_pareto_terminal(pareto_data, use_color=not args.no_color))

    # 3. Export Reports
    timestamp_slug = time.strftime("%Y-%m-%d_%H-%M-%S")
    metrics_dir = "Test metrics"

    if run_all or args.export_md:
        md_path = args.export_md if (args.export_md and args.export_md != "AUTO") else os.path.join(metrics_dir, f"matrix_{timestamp_slug}.md")
        saved_md = export_markdown_report(matrix_data, tier_data, pareto_data, md_path, regression_report)
        print(f"Markdown report generated: {saved_md}")

    if run_all or args.export_json:
        json_path = args.export_json if (args.export_json and args.export_json != "AUTO") else os.path.join(metrics_dir, f"matrix_{timestamp_slug}.json")
        saved_json = export_json_report(matrix_data, tier_data, pareto_data, json_path, regression_report)
        print(f"JSON metrics generated: {saved_json}")


if __name__ == "__main__":
    main()
