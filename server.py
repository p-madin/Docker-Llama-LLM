#!/usr/bin/env python3
"""
Interactive Web Management Dashboard & CRUD Server for LLM Benchmark Suite.
Phase 6 Implementation (Zero external pip dependencies - Python Standard Library).

Provides REST API endpoints and static file serving for:
  - Interactive Heatmap Matrix Explorer
  - Side-by-Side Model Completion Diff Inspector
  - Bidirectional Question & Assertion CRUD Manager (SQLite <-> XML)
  - Single-Prompt Live Sandbox with Assertion Evaluation
"""

import os
import sys
import json
import time
import glob
import urllib.parse
import urllib.request
import urllib.error
import sqlite3
import argparse
import socketserver
import queue
import threading
import xml.etree.ElementTree as ET
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict, Any, List, Optional, Tuple

def load_env_file(filepath: str = ".env"):
    """Loads environment variables from .env if present."""
    if os.path.isfile(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k and k not in os.environ:
                            os.environ[k] = v
        except Exception:
            pass

load_env_file()

# Framework imports
import benchmark_store
from modelAssertion import ModelAssertion, AssertionFactory, BaseAssertion, AssertionResult
from testLLM import (
    LLMClient,
    load_all_questions,
    export_markdown_report,
    sanitize_filename,
    TestCase
)

DEFAULT_DB_PATH = os.environ.get("DB_PATH", "benchmark.db")
DEFAULT_OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
QUESTIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Questions")
METRICS_DIR = os.environ.get("METRICS_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "Test metrics"))


def get_db(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Returns a SQLite connection with row factory enabled."""
    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn


class BenchmarkJobWorker:
    """
    Asynchronous in-container background execution worker (Phase 7).
    Executes benchmark jobs off the main HTTP thread, manages Ollama VRAM dynamically,
    persists results to SQLite and disk, and broadcasts real-time telemetry over SSE.
    """

    def __init__(self, db_path: str = DEFAULT_DB_PATH, metrics_dir: str = METRICS_DIR):
        self.db_path = db_path
        self.metrics_dir = metrics_dir
        self.job_queue: queue.Queue = queue.Queue()
        self.abort_flags: Dict[int, bool] = {}
        self.subscribers: Dict[int, List[queue.Queue]] = {}
        self.event_backlogs: Dict[int, List[Dict[str, Any]]] = {}
        self.lock = threading.Lock()
        self.active_job_id: Optional[int] = None
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()

    def enqueue_job(self, job_id: int):
        """Enqueues a job ID for background processing."""
        self.abort_flags[job_id] = False
        self.job_queue.put(job_id)

    def request_abort(self, job_id: int) -> bool:
        """Flags an executing or queued job to abort immediately."""
        self.abort_flags[job_id] = True
        self.broadcast(job_id, {
            "type": "log",
            "level": "warn",
            "message": f"Abort requested for Job #{job_id}."
        })
        return True

    def subscribe(self, job_id: int) -> Tuple[queue.Queue, List[Dict[str, Any]]]:
        """Registers an SSE listener for job events and returns (subscriber_queue, backlog)."""
        q = queue.Queue()
        with self.lock:
            if job_id not in self.subscribers:
                self.subscribers[job_id] = []
            self.subscribers[job_id].append(q)
            backlog = list(self.event_backlogs.get(job_id, []))
        return q, backlog

    def unsubscribe(self, job_id: int, q: queue.Queue):
        """Removes an SSE subscriber queue."""
        with self.lock:
            if job_id in self.subscribers and q in self.subscribers[job_id]:
                self.subscribers[job_id].remove(q)

    def broadcast(self, job_id: int, event: Dict[str, Any]):
        """Pushes an event payload to all active SSE subscribers and appends to job backlog."""
        event["timestamp"] = time.strftime("%H:%M:%S")
        with self.lock:
            if job_id not in self.event_backlogs:
                self.event_backlogs[job_id] = []
            self.event_backlogs[job_id].append(event)
            if len(self.event_backlogs[job_id]) > 1000:
                self.event_backlogs[job_id].pop(0)

            subs = list(self.subscribers.get(job_id, []))
        for q in subs:
            try:
                q.put_nowait(event)
            except Exception:
                pass

    def evict_ollama_model(self, client: LLMClient, model_name: str):
        """Evicts model from GPU VRAM immediately using Ollama's keep_alive: 0 parameter."""
        if client.is_gemini(model_name):
            return
        try:
            payload = json.dumps({"model": model_name, "keep_alive": 0, "stream": False}).encode("utf-8")
            req = urllib.request.Request(
                f"{client.host}/api/generate",
                data=payload,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=10) as res:
                res.read()
        except Exception:
            pass

    def _append_summary_md(self, summaries: List[Dict[str, Any]]):
        """Appends finished benchmark run rows to Test metrics/Summary.md."""
        try:
            os.makedirs(self.metrics_dir, exist_ok=True)
            summary_md_path = os.path.join(self.metrics_dir, "Summary.md")
            header = (
                "## Summary Comparison\n"
                "| Model | Questions Solved | Assertions Passed | Avg Generation Speed | Total Latency (Inference) | Total Cycle Time (Docker) |\n"
                "| :--- | :--- | :--- | :--- | :--- | :--- |\n"
            )
            if not os.path.isfile(summary_md_path):
                with open(summary_md_path, "w", encoding="utf-8") as f:
                    f.write(header)

            with open(summary_md_path, "a", encoding="utf-8") as f:
                for s in summaries:
                    q_solved = s.get("questions_solved", s.get("passed_cases", 0))
                    q_total = s.get("total_questions", s.get("total_cases", 0))
                    q_pct = s.get("question_pass_rate_pct", 0.0)
                    a_passed = s.get("passed_assertions", 0)
                    a_total = s.get("total_assertions", 0)
                    a_pct = s.get("assertion_pass_rate_pct", 0.0)
                    speed = s.get("avg_tokens_per_sec", 0.0)
                    lat = s.get("total_latency_sec", 0.0)
                    row = f"| **{s['model']}** | {q_solved}/{q_total} ({q_pct}%) | {a_passed}/{a_total} ({a_pct}%) | {speed} tok/s | {lat}s | In-Container (Worker) |\n"
                    f.write(row)
        except Exception as e:
            print(f"[WORKER] Failed to append to Summary.md: {e}", file=sys.stderr)

    def _worker_loop(self):
        """Continuously pulls and executes benchmark jobs from queue."""
        while True:
            job_id = self.job_queue.get()
            try:
                self.active_job_id = job_id
                self._execute_job(job_id)
            except Exception as e:
                import traceback
                traceback.print_exc()
                conn = get_db(self.db_path)
                with conn:
                    benchmark_store.update_job_status(conn, job_id, "failed", error_message=str(e))
                self.broadcast(job_id, {"type": "job_error", "job_id": job_id, "error": str(e)})
            finally:
                self.active_job_id = None
                self.job_queue.task_done()

    def _execute_job(self, job_id: int):
        """Executes a single benchmark job end-to-end."""
        conn = get_db(self.db_path)
        job = benchmark_store.get_job(conn, job_id)
        if not job:
            return

        if self.abort_flags.get(job_id):
            benchmark_store.update_job_status(conn, job_id, "aborted", error_message="Aborted before starting")
            self.broadcast(job_id, {"type": "aborted", "job_id": job_id})
            return

        # Mark running
        benchmark_store.update_job_status(conn, job_id, "running")
        models = job.get("models", [])
        suites = job.get("suites", [])
        temperature = float(job.get("temperature", 0.0))
        blanket_max_tokens = int(job.get("blanket_max_tokens", 1200))

        self.broadcast(job_id, {
            "type": "job_start",
            "job_id": job_id,
            "job_uuid": job["job_uuid"],
            "models": models,
            "suites": suites,
            "total_models": len(models)
        })

        # Load question bank
        all_cases, _ = load_all_questions(os.path.join(QUESTIONS_DIR, "*.xml"))
        if suites:
            suite_filter = {s.lower() for s in suites}
            test_cases = [
                tc for tc in all_cases
                if any(sf in tc.source_file.lower() or sf in tc.category.lower() for sf in suite_filter)
            ]
        else:
            test_cases = all_cases

        if not test_cases:
            msg = "No test questions matched the requested suites or filters."
            benchmark_store.update_job_status(conn, job_id, "failed", error_message=msg)
            self.broadcast(job_id, {"type": "job_error", "job_id": job_id, "error": msg})
            return

        total_work_units = len(models) * len(test_cases)
        completed_units = 0
        created_run_ids: List[int] = []
        all_summaries: List[Dict[str, Any]] = []
        job_start_time = time.perf_counter()

        client = LLMClient(
            host=DEFAULT_OLLAMA_URL,
            timeout=120,
            gemini_api_key=os.environ.get("GEMINI_API_KEY", "")
        )

        for model_idx, model_name in enumerate(models):
            if self.abort_flags.get(job_id):
                benchmark_store.update_job_status(conn, job_id, "aborted", error_message="Job aborted by user", result_run_ids=created_run_ids)
                self.broadcast(job_id, {"type": "aborted", "job_id": job_id})
                return

            self.broadcast(job_id, {
                "type": "model_start",
                "job_id": job_id,
                "model": model_name,
                "model_index": model_idx + 1,
                "total_models": len(models),
                "total_questions": len(test_cases)
            })

            # Pre-warm / load into VRAM
            if not client.is_gemini(model_name):
                self.broadcast(job_id, {
                    "type": "log",
                    "level": "info",
                    "message": f"Pre-loading '{model_name}' into GPU VRAM (keep_alive: -1)..."
                })
                try:
                    payload = json.dumps({"model": model_name, "keep_alive": -1, "stream": False}).encode("utf-8")
                    req = urllib.request.Request(
                        f"{client.host}/api/generate",
                        data=payload,
                        headers={"Content-Type": "application/json"}
                    )
                    with urllib.request.urlopen(req, timeout=30) as res:
                        res.read()
                except Exception:
                    pass

            # Model evaluation loop
            cases_results = []
            total_assertions = 0
            passed_assertions = 0
            total_latency = 0.0
            total_tokens = 0

            for q_idx, tc in enumerate(test_cases):
                if self.abort_flags.get(job_id):
                    benchmark_store.update_job_status(conn, job_id, "aborted", error_message="Job aborted by user", result_run_ids=created_run_ids)
                    self.broadcast(job_id, {"type": "aborted", "job_id": job_id})
                    return

                q_temp = tc.temperature if tc.temperature is not None else temperature
                q_max_tok = tc.max_tokens if tc.max_tokens else blanket_max_tokens

                try:
                    resp = client.send_chat(
                        model=model_name,
                        question=tc.question,
                        system_prompt=tc.system_prompt,
                        temperature=q_temp,
                        max_tokens=q_max_tok
                    )
                except Exception as e:
                    resp = {
                        "content": "",
                        "thinking": "",
                        "metrics": {"error": str(e), "latency_sec": 0.0, "eval_tokens_per_sec": 0.0}
                    }

                final_content = resp.get("content", "")
                thinking = resp.get("thinking", "")
                metrics = resp.get("metrics", {})
                full_output = f"<think>\n{thinking.strip()}\n</think>\n\n{final_content.strip()}" if thinking else final_content

                # CoT strict evaluation & stall-detection
                if thinking and not final_content.strip():
                    case_passed = False
                    raw_results = [
                        AssertionResult(
                            rule_type="response_delivered",
                            passed=False,
                            message="Model failed to deliver an answer (truncated or halted in <think> phase)"
                        )
                    ]
                    total_assertions += 1
                else:
                    eval_target = final_content if thinking else (final_content if final_content else full_output)
                    raw_results = tc.assertions.evaluate(eval_target, metrics)
                    total_assertions += len(raw_results)
                    passed_assertions += sum(1 for r in raw_results if r.passed)
                    case_passed = tc.assertions.is_all_passed(raw_results)

                assertion_dicts = [r.to_dict() for r in raw_results]

                lat_sec = metrics.get("latency_sec", 0.0)
                tps = metrics.get("eval_tokens_per_sec", 0.0)
                c_tok = metrics.get("completion_tokens", 0)
                p_tok = metrics.get("prompt_tokens", 0)

                total_latency += lat_sec
                total_tokens += c_tok

                completed_units += 1
                progress_pct = (completed_units / total_work_units) * 100.0
                benchmark_store.update_job_progress(conn, job_id, model_name, tc.test_id, progress_pct)

                cases_results.append({
                    "test_id": tc.test_id,
                    "name": tc.name,
                    "tier": tc.tier,
                    "category": tc.category,
                    "difficulty": tc.difficulty,
                    "model": model_name,
                    "question": tc.question,
                    "output": full_output,
                    "metrics": metrics,
                    "case_passed": case_passed,
                    "assertions": assertion_dicts
                })

                self.broadcast(job_id, {
                    "type": "test_result",
                    "job_id": job_id,
                    "model": model_name,
                    "test_id": tc.test_id,
                    "name": tc.name,
                    "tier": tc.tier,
                    "category": tc.category,
                    "passed": case_passed,
                    "latency_sec": lat_sec,
                    "speed_tok_s": tps,
                    "prompt_tokens": p_tok,
                    "completion_tokens": c_tok,
                    "assertions": assertion_dicts,
                    "output_preview": (final_content or full_output).strip()[:100],
                    "progress_pct": round(progress_pct, 1),
                    "completed_units": completed_units,
                    "total_work_units": total_work_units,
                    "question_index": q_idx + 1,
                    "total_questions": len(test_cases)
                })

            # Calculate model summary
            passed_cases = sum(1 for r in cases_results if r["case_passed"])
            q_pass_rate = (passed_cases / len(test_cases) * 100) if test_cases else 0.0
            a_pass_rate = (passed_assertions / total_assertions * 100) if total_assertions > 0 else 0.0
            avg_speed = (total_tokens / total_latency) if total_latency > 0 else 0.0

            summary = {
                "model": model_name,
                "endpoint": "https://generativelanguage.googleapis.com" if client.is_gemini(model_name) else client.host,
                "total_questions": len(test_cases),
                "questions_solved": passed_cases,
                "questions_failed": len(test_cases) - passed_cases,
                "question_pass_rate_pct": round(q_pass_rate, 1),
                "total_cases": len(test_cases),
                "passed_cases": passed_cases,
                "failed_cases": len(test_cases) - passed_cases,
                "case_pass_rate_pct": round(q_pass_rate, 1),
                "total_assertions": total_assertions,
                "passed_assertions": passed_assertions,
                "failed_assertions": total_assertions - passed_assertions,
                "pass_rate_pct": round(a_pass_rate, 1),
                "assertion_pass_rate_pct": round(a_pass_rate, 1),
                "total_latency_sec": round(total_latency, 2),
                "total_tokens_generated": total_tokens,
                "avg_tokens_per_sec": round(avg_speed, 2),
                "cases": cases_results
            }
            all_summaries.append(summary)

            # Persist model run to SQLite
            run_id = benchmark_store.record_full_summary(conn, summary)
            created_run_ids.append(run_id)

            # Save report files to Test metrics/<model>/<timestamp>
            ts = time.strftime("%Y-%m-%d_%H-%M-%S")
            safe_model = sanitize_filename(model_name)
            model_out_dir = os.path.join(self.metrics_dir, safe_model)
            os.makedirs(model_out_dir, exist_ok=True)

            try:
                with open(os.path.join(model_out_dir, f"{ts}_out.json"), "w", encoding="utf-8") as f:
                    json.dump(summary, f, indent=2)
                export_markdown_report([summary], os.path.join(model_out_dir, f"{ts}_out.md"))
            except Exception as e:
                print(f"[WORKER] Failed to write report files: {e}", file=sys.stderr)

            # Evict model from GPU memory to free VRAM for next model
            self.broadcast(job_id, {
                "type": "log",
                "level": "info",
                "message": f"Evicting '{model_name}' from GPU VRAM (keep_alive: 0)..."
            })
            self.evict_ollama_model(client, model_name)

            self.broadcast(job_id, {
                "type": "model_done",
                "job_id": job_id,
                "model": model_name,
                "run_id": run_id,
                "questions_solved": passed_cases,
                "total_questions": len(test_cases),
                "pass_rate_pct": round(q_pass_rate, 1),
                "avg_speed": round(avg_speed, 1),
                "total_latency_sec": round(total_latency, 2)
            })

        # Append to Test metrics/Summary.md
        self._append_summary_md(all_summaries)

        # Update job to completed
        benchmark_store.update_job_status(conn, job_id, "completed", result_run_ids=created_run_ids)

        elapsed = round(time.perf_counter() - job_start_time, 2)
        self.broadcast(job_id, {
            "type": "job_done",
            "job_id": job_id,
            "run_ids": created_run_ids,
            "total_models": len(models),
            "total_questions": len(test_cases),
            "elapsed_sec": elapsed
        })


WORKER_INSTANCE = BenchmarkJobWorker()


class ThreadedHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    """Threaded HTTP server to handle concurrent API requests without blocking."""
    daemon_threads = True


class BenchmarkWebHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler providing REST API and static UI serving."""

    def log_message(self, format, *args):
        # Override to keep server stdout clean, logging errors and API calls concisely
        if self.path.startswith("/api/"):
            print(f"[{self.command}] {self.path} -> {args[1] if len(args) > 1 else ''}")

    # ==========================================================================
    # HTTP Headers & Response Helpers
    # ==========================================================================

    def send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_cors_headers()
        self.end_headers()

    def send_json(self, data: Any, status_code: int = 200):
        body = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, message: str, status_code: int = 400):
        self.send_json({"error": message, "status": status_code}, status_code=status_code)

    def read_json_body(self) -> Dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length <= 0:
            return {}
        raw = self.rfile.read(content_length).decode("utf-8")
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON request body: {e}")

    # ==========================================================================
    # Static File Serving
    # ==========================================================================

    def serve_static(self, rel_path: str):
        if rel_path in ("", "/", "index.html"):
            file_path = os.path.join(WEB_DIR, "index.html")
        else:
            clean_path = rel_path.lstrip("/").replace("\\", "/")
            file_path = os.path.abspath(os.path.join(WEB_DIR, clean_path))
            # Directory traversal prevention
            if not file_path.startswith(os.path.abspath(WEB_DIR)):
                self.send_error_json("Access denied", 403)
                return

        if not os.path.isfile(file_path):
            self.send_error_json("Resource not found", 404)
            return

        ext = os.path.splitext(file_path)[1].lower()
        mime_types = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".svg": "image/svg+xml",
            ".png": "image/png",
            ".ico": "image/x-icon",
        }
        content_type = mime_types.get(ext, "application/octet-stream")

        try:
            with open(file_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self.send_error_json(f"Error serving file: {e}", 500)

    # ==========================================================================
    # Route Dispatchers
    # ==========================================================================

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        try:
            if path == "/api/health":
                self.handle_health()
            elif path == "/api/matrix":
                self.handle_matrix(query)
            elif path == "/api/models":
                self.handle_models()
            elif path == "/api/suites":
                self.handle_suites()
            elif path == "/api/questions":
                self.handle_questions(query)
            elif path.startswith("/api/question/"):
                qid = path.split("/api/question/")[1]
                self.handle_get_question(qid)
            elif path.startswith("/api/result/"):
                rid = int(path.split("/api/result/")[1])
                self.handle_get_result(rid)
            elif path == "/api/diff":
                self.handle_diff(query)
            elif path == "/api/stats":
                self.handle_stats()
            elif path == "/api/jobs":
                self.handle_list_jobs()
            elif path.startswith("/api/jobs/") and path.endswith("/stream"):
                jid = path.split("/api/jobs/")[1].split("/stream")[0]
                self.handle_job_stream(jid)
            elif path.startswith("/api/jobs/"):
                jid = path.split("/api/jobs/")[1]
                self.handle_get_job(jid)
            else:
                self.serve_static(path)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.send_error_json(str(e), 500)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        try:
            if path == "/api/question":
                self.handle_create_question()
            elif path == "/api/sandbox/run":
                self.handle_sandbox_run()
            elif path == "/api/sandbox/stream":
                self.handle_sandbox_stream()
            elif path == "/api/sync":
                self.handle_sync_questions()
            elif path == "/api/benchmark/run":
                self.handle_launch_benchmark()
            elif path.startswith("/api/jobs/") and path.endswith("/abort"):
                jid = path.split("/api/jobs/")[1].split("/abort")[0]
                self.handle_abort_job(jid)
            else:
                self.send_error_json(f"Unknown POST endpoint: {path}", 404)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.send_error_json(str(e), 500)

    def do_PUT(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        try:
            if path.startswith("/api/question/"):
                qid = path.split("/api/question/")[1]
                self.handle_update_question(qid)
            else:
                self.send_error_json(f"Unknown PUT endpoint: {path}", 404)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.send_error_json(str(e), 500)

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        try:
            if path.startswith("/api/question/"):
                qid = path.split("/api/question/")[1]
                self.handle_delete_question(qid)
            else:
                self.send_error_json(f"Unknown DELETE endpoint: {path}", 404)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.send_error_json(str(e), 500)

    # ==========================================================================
    # API Handlers
    # ==========================================================================

    def handle_health(self):
        """Returns environment status, DB metrics, and connectivity to Ollama & Gemini."""
        ollama_ok = False
        ollama_models = []
        try:
            req = urllib.request.Request(f"{DEFAULT_OLLAMA_URL}/api/tags")
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                if resp.status == 200:
                    ollama_ok = True
                    data = json.loads(resp.read().decode("utf-8"))
                    ollama_models = [m.get("name") for m in data.get("models", [])]
        except Exception:
            ollama_ok = False

        gemini_key = os.environ.get("GEMINI_API_KEY", "")
        gemini_ok = bool(gemini_key and len(gemini_key) > 5)

        db_ok = False
        stats = {}
        try:
            conn = get_db()
            with conn:
                stats = benchmark_store.get_stats(conn)
                db_ok = True
        except Exception as e:
            stats = {"error": str(e)}

        self.send_json({
            "status": "healthy" if db_ok else "degraded",
            "db_connected": db_ok,
            "ollama_connected": ollama_ok,
            "ollama_url": DEFAULT_OLLAMA_URL,
            "ollama_models": ollama_models,
            "gemini_configured": gemini_ok,
            "stats": stats
        })

    def handle_stats(self):
        """Returns relational database row counts."""
        conn = get_db()
        with conn:
            stats = benchmark_store.get_stats(conn)
        self.send_json(stats)

    def handle_models(self):
        """Returns all models evaluated in the database along with available Ollama models."""
        conn = get_db()
        with conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT m.id, m.name, m.family, m.parameter_size, m.quantization,
                       COUNT(DISTINCT r.id) as total_runs,
                       MAX(r.timestamp) as latest_run_time
                FROM models m
                LEFT JOIN test_results tr ON m.id = tr.model_id
                LEFT JOIN benchmark_runs r ON tr.run_id = r.id
                GROUP BY m.id
                ORDER BY total_runs DESC, m.name ASC
            """)
            models = [dict(r) for r in cursor.fetchall()]

        self.send_json({"models": models})

    def handle_suites(self):
        """Returns all test suites with question counts."""
        conn = get_db()
        with conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT ts.id, ts.name, ts.file_path, ts.description, COUNT(q.id) as question_count
                FROM test_suites ts
                LEFT JOIN questions q ON ts.id = q.suite_id
                GROUP BY ts.id
                ORDER BY ts.name ASC
            """)
            suites = [dict(r) for r in cursor.fetchall()]
        self.send_json({"suites": suites})

    def handle_questions(self, query: Dict[str, List[str]]):
        """Returns questions list with assertions."""
        include_archived = query.get("include_archived", ["false"])[0].lower() == "true"
        conn = get_db()
        with conn:
            cursor = conn.cursor()
            filter_sql = "" if include_archived else "WHERE q.suite_id IS NOT NULL"
            cursor.execute(f"""
                SELECT q.id, q.test_id, q.tier, q.category, q.difficulty, q.question_text,
                       q.system_prompt, q.temperature, q.max_tokens, ts.name as suite_name,
                       ts.file_path as suite_file
                FROM questions q
                LEFT JOIN test_suites ts ON q.suite_id = ts.id
                {filter_sql}
                ORDER BY q.tier ASC, q.test_id ASC
            """)
            q_rows = [dict(r) for r in cursor.fetchall()]

            # Fetch assertions for all questions
            cursor.execute("SELECT question_id, assertion_type as rule_type, expected_value as expected_values, case_sensitive FROM assertions")
            assertions_by_q: Dict[int, List[Dict[str, Any]]] = {}
            for row in cursor.fetchall():
                qid = row["question_id"]
                if qid not in assertions_by_q:
                    assertions_by_q[qid] = []
                try:
                    exp = json.loads(row["expected_values"])
                except Exception:
                    exp = [row["expected_values"]]
                assertions_by_q[qid].append({
                    "rule_type": row["rule_type"],
                    "expected_values": exp,
                    "case_sensitive": bool(row["case_sensitive"])
                })

            for q in q_rows:
                q["assertions"] = assertions_by_q.get(q["id"], [])

        self.send_json({"questions": q_rows, "total": len(q_rows)})

    def handle_get_question(self, qid_or_test_id: str):
        """Returns single question details and its historical results across models."""
        conn = get_db()
        with conn:
            cursor = conn.cursor()
            if qid_or_test_id.isdigit():
                cursor.execute("SELECT q.*, ts.name as suite_name, ts.file_path FROM questions q LEFT JOIN test_suites ts ON q.suite_id = ts.id WHERE q.id = ?", (int(qid_or_test_id),))
            else:
                cursor.execute("SELECT q.*, ts.name as suite_name, ts.file_path FROM questions q LEFT JOIN test_suites ts ON q.suite_id = ts.id WHERE q.test_id = ?", (qid_or_test_id,))
            q_row = cursor.fetchone()
            if not q_row:
                self.send_error_json(f"Question '{qid_or_test_id}' not found", 404)
                return

            q = dict(q_row)

            # Get assertions
            cursor.execute("SELECT assertion_type as rule_type, expected_value as expected_values, case_sensitive FROM assertions WHERE question_id = ?", (q["id"],))
            q["assertions"] = []
            for r in cursor.fetchall():
                try:
                    exp = json.loads(r["expected_values"])
                except Exception:
                    exp = [r["expected_values"]]
                q["assertions"].append({
                    "rule_type": r["rule_type"],
                    "expected_values": exp,
                    "case_sensitive": bool(r["case_sensitive"])
                })

            # Get recent model completions for this question
            cursor.execute("""
                SELECT tr.id as result_id, tr.run_id, m.name as model_name, tr.passed,
                       tr.raw_output, tr.latency_sec, tr.eval_tokens_per_sec,
                       tr.prompt_tokens, tr.completion_tokens, r.timestamp
                FROM test_results tr
                JOIN models m ON tr.model_id = m.id
                JOIN benchmark_runs r ON tr.run_id = r.id
                WHERE tr.question_id = ?
                ORDER BY tr.run_id DESC
                LIMIT 20
            """, (q["id"],))
            completions = [dict(r) for r in cursor.fetchall()]

            for c in completions:
                cursor.execute("SELECT passed, message FROM assertion_results WHERE test_result_id = ?", (c["result_id"],))
                c["assertion_evaluations"] = [dict(ar) for ar in cursor.fetchall()]

            q["recent_results"] = completions

        self.send_json(q)

    def handle_get_result(self, result_id: int):
        """Returns details and assertion breakdown for a single test result cell."""
        conn = get_db()
        with conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT tr.id as result_id, tr.run_id, m.name as model_name, q.test_id,
                       q.question_text, q.tier, q.category, tr.passed, tr.raw_output,
                       tr.latency_sec, tr.eval_tokens_per_sec, tr.prompt_tokens,
                       tr.completion_tokens, r.timestamp
                FROM test_results tr
                JOIN models m ON tr.model_id = m.id
                JOIN questions q ON tr.question_id = q.id
                JOIN benchmark_runs r ON tr.run_id = r.id
                WHERE tr.id = ?
            """, (result_id,))
            res = cursor.fetchone()
            if not res:
                self.send_error_json("Test result not found", 404)
                return

            data = dict(res)
            cursor.execute("SELECT passed, message FROM assertion_results WHERE test_result_id = ?", (result_id,))
            data["assertions"] = [dict(r) for r in cursor.fetchall()]

        self.send_json(data)

    def handle_matrix(self, query: Dict[str, List[str]]):
        """Builds and returns the full M x N Model x Question Pass/Fail Matrix."""
        min_q = int(query.get("min_questions", ["10"])[0])
        include_archived = query.get("include_archived", ["false"])[0].lower() == "true"

        conn = get_db()
        with conn:
            cursor = conn.cursor()

            # 1. Get latest qualifying run per model
            qualifying_query = """
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
            cursor.execute(qualifying_query, (min_q,))
            models = [dict(r) for r in cursor.fetchall()]

            # 2. Get active questions
            filter_sql = "" if include_archived else "WHERE q.suite_id IS NOT NULL"
            cursor.execute(f"""
                SELECT q.id, q.test_id, q.tier, q.category, q.difficulty, q.question_text, ts.name AS suite_name
                FROM questions q
                LEFT JOIN test_suites ts ON q.suite_id = ts.id
                {filter_sql}
                ORDER BY q.tier ASC, q.test_id ASC;
            """)
            questions = [dict(r) for r in cursor.fetchall()]

            if not models or not questions:
                self.send_json({"models": [], "questions": [], "matrix": {}, "tiers": {}})
                return

            # 3. Pull all test results for latest runs
            run_ids = [m["run_id"] for m in models]
            placeholders = ",".join("?" for _ in run_ids)
            cursor.execute(f"""
                SELECT tr.id as result_id, tr.run_id, m.name AS model_name, q.test_id,
                       tr.passed, tr.eval_tokens_per_sec, tr.latency_sec
                FROM test_results tr
                JOIN models m ON tr.model_id = m.id
                JOIN questions q ON tr.question_id = q.id
                WHERE tr.run_id IN ({placeholders})
            """, run_ids)

            matrix: Dict[str, Dict[str, Any]] = {}
            for r in cursor.fetchall():
                tid = r["test_id"]
                mname = r["model_name"]
                if tid not in matrix:
                    matrix[tid] = {}
                matrix[tid][mname] = {
                    "result_id": r["result_id"],
                    "passed": bool(r["passed"]),
                    "speed_tps": round(r["eval_tokens_per_sec"] or 0.0, 1),
                    "latency_sec": round(r["latency_sec"] or 0.0, 2)
                }

            # 4. Calculate Cognitive Tier performance per model
            tiers = {}
            for m in models:
                mname = m["model_name"]
                tiers[mname] = {1: {"solved": 0, "total": 0},
                                2: {"solved": 0, "total": 0},
                                3: {"solved": 0, "total": 0},
                                4: {"solved": 0, "total": 0}}

            for q in questions:
                tid = q["test_id"]
                tier = q["tier"]
                q_res = matrix.get(tid, {})
                for m in models:
                    mname = m["model_name"]
                    if mname in q_res:
                        tiers[mname][tier]["total"] += 1
                        if q_res[mname]["passed"]:
                            tiers[mname][tier]["solved"] += 1

        self.send_json({
            "models": models,
            "questions": questions,
            "matrix": matrix,
            "tiers": tiers
        })

    def handle_diff(self, query: Dict[str, List[str]]):
        """Returns side-by-side completions across specified models for a question."""
        qid = query.get("question_id", query.get("test_id", [""]))[0]
        model_names = [m.strip() for m in query.get("models", [""])[0].split(",") if m.strip()]

        if not qid:
            self.send_error_json("Missing required parameter: question_id or test_id", 400)
            return

        conn = get_db()
        with conn:
            cursor = conn.cursor()
            # Fetch question info
            if qid.isdigit():
                cursor.execute("SELECT q.*, ts.name as suite_name FROM questions q LEFT JOIN test_suites ts ON q.suite_id = ts.id WHERE q.id = ?", (int(qid),))
            else:
                cursor.execute("SELECT q.*, ts.name as suite_name FROM questions q LEFT JOIN test_suites ts ON q.suite_id = ts.id WHERE q.test_id = ?", (qid,))
            q_row = cursor.fetchone()
            if not q_row:
                self.send_error_json(f"Question '{qid}' not found", 404)
                return
            question = dict(q_row)

            # Build query to get latest completion for each model
            diff_results = []
            filter_sql = ""
            params = [question["id"]]
            if model_names:
                placeholders = ",".join("?" for _ in model_names)
                filter_sql = f"AND m.name IN ({placeholders})"
                params.extend(model_names)

            cursor.execute(f"""
                WITH ranked_results AS (
                    SELECT tr.*, m.name as model_name, r.timestamp,
                           ROW_NUMBER() OVER(PARTITION BY tr.model_id ORDER BY tr.run_id DESC) as rn
                    FROM test_results tr
                    JOIN models m ON tr.model_id = m.id
                    JOIN benchmark_runs r ON tr.run_id = r.id
                    WHERE tr.question_id = ? {filter_sql}
                )
                SELECT * FROM ranked_results WHERE rn = 1
                ORDER BY passed DESC, model_name ASC
            """, params)

            for r in cursor.fetchall():
                row_dict = dict(r)
                # Pull assertions
                cursor.execute("SELECT passed, message FROM assertion_results WHERE test_result_id = ?", (row_dict["id"],))
                row_dict["assertions"] = [dict(ar) for ar in cursor.fetchall()]

                # Extract <think> tokens if present
                raw = row_dict.get("raw_output", "")
                think_content = ""
                final_content = raw
                if "<think>" in raw and "</think>" in raw:
                    parts = raw.split("</think>", 1)
                    think_content = parts[0].replace("<think>", "").strip()
                    final_content = parts[1].strip()

                row_dict["think_content"] = think_content
                row_dict["final_content"] = final_content
                diff_results.append(row_dict)

        self.send_json({
            "question": question,
            "models": diff_results
        })

    def handle_create_question(self):
        """Creates a new question in benchmark.db and appends to the corresponding XML file."""
        body = self.read_json_body()
        test_id = body.get("test_id", "").strip()
        name = body.get("name", test_id).strip()
        suite_name = body.get("suite_name", "LLM Evaluation Suite").strip()
        suite_file = body.get("suite_file", "questions_basic.xml").strip()
        question_text = body.get("question_text", "").strip()
        system_prompt = body.get("system_prompt", "").strip()
        tier = int(body.get("tier", 1))
        category = body.get("category", "general").strip()
        difficulty = body.get("difficulty", "medium").strip()
        temperature = float(body.get("temperature", 0.0))
        max_tokens = int(body.get("max_tokens", 1200))
        assertions = body.get("assertions", [])

        if not test_id or not question_text:
            self.send_error_json("test_id and question_text are required fields", 400)
            return

        conn = get_db()
        with conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM questions WHERE test_id = ?", (test_id,))
            if cursor.fetchone():
                self.send_error_json(f"Question with test_id '{test_id}' already exists", 409)
                return

            suite_id = benchmark_store.get_or_create_suite(conn, suite_name, file_path=os.path.join(QUESTIONS_DIR, suite_file))

            cursor.execute("""
                INSERT INTO questions (suite_id, test_id, category, difficulty, tier, question_text, system_prompt, temperature, max_tokens)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (suite_id, test_id, category, difficulty, tier, question_text, system_prompt, temperature, max_tokens))
            new_qid = cursor.lastrowid

            for a in assertions:
                rtype = a.get("rule_type", "contains")
                exp = a.get("expected_values", [])
                cs = 1 if a.get("case_sensitive", False) else 0
                is_neg = 1 if rtype.startswith("not_") else 0
                cursor.execute("""
                    INSERT INTO assertions (question_id, assertion_type, expected_value, is_negative, case_sensitive)
                    VALUES (?, ?, ?, ?, ?)
                """, (new_qid, rtype, json.dumps(exp) if isinstance(exp, list) else str(exp), is_neg, cs))

        # Commit to XML file
        self._write_question_to_xml(suite_file, {
            "test_id": test_id,
            "name": name,
            "tier": tier,
            "category": category,
            "difficulty": difficulty,
            "question_text": question_text,
            "system_prompt": system_prompt,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "assertions": assertions
        }, is_new=True)

        self.send_json({"success": True, "question_id": new_qid, "test_id": test_id})

    def handle_update_question(self, qid_or_test_id: str):
        """Updates an existing question in SQLite and syncs to its XML suite."""
        body = self.read_json_body()
        conn = get_db()
        with conn:
            cursor = conn.cursor()
            if qid_or_test_id.isdigit():
                cursor.execute("SELECT q.*, ts.name as suite_name, ts.file_path FROM questions q LEFT JOIN test_suites ts ON q.suite_id = ts.id WHERE q.id = ?", (int(qid_or_test_id),))
            else:
                cursor.execute("SELECT q.*, ts.name as suite_name, ts.file_path FROM questions q LEFT JOIN test_suites ts ON q.suite_id = ts.id WHERE q.test_id = ?", (qid_or_test_id,))
            q_row = cursor.fetchone()
            if not q_row:
                self.send_error_json(f"Question '{qid_or_test_id}' not found", 404)
                return

            q = dict(q_row)
            qid = q["id"]
            test_id = q["test_id"]
            suite_file = os.path.basename(q.get("file_path") or "questions_basic.xml")

            name = body.get("name", test_id).strip()
            question_text = body.get("question_text", q["question_text"]).strip()
            system_prompt = body.get("system_prompt", q["system_prompt"]).strip()
            tier = int(body.get("tier", q["tier"]))
            category = body.get("category", q["category"]).strip()
            difficulty = body.get("difficulty", q["difficulty"]).strip()
            temperature = float(body.get("temperature", q["temperature"]))
            max_tokens = int(body.get("max_tokens", q["max_tokens"]))
            assertions = body.get("assertions", [])

            cursor.execute("""
                UPDATE questions
                SET category = ?, difficulty = ?, tier = ?, question_text = ?,
                    system_prompt = ?, temperature = ?, max_tokens = ?
                WHERE id = ?
            """, (category, difficulty, tier, question_text, system_prompt, temperature, max_tokens, qid))

            if assertions:
                cursor.execute("DELETE FROM assertions WHERE question_id = ?", (qid,))
                for a in assertions:
                    rtype = a.get("rule_type", "contains")
                    exp = a.get("expected_values", [])
                    cs = 1 if a.get("case_sensitive", False) else 0
                    is_neg = 1 if rtype.startswith("not_") else 0
                    cursor.execute("""
                        INSERT INTO assertions (question_id, assertion_type, expected_value, is_negative, case_sensitive)
                        VALUES (?, ?, ?, ?, ?)
                    """, (qid, rtype, json.dumps(exp) if isinstance(exp, list) else str(exp), is_neg, cs))

        # Update XML
        self._write_question_to_xml(suite_file, {
            "test_id": test_id,
            "name": name,
            "tier": tier,
            "category": category,
            "difficulty": difficulty,
            "question_text": question_text,
            "system_prompt": system_prompt,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "assertions": assertions
        }, is_new=False)

        self.send_json({"success": True, "question_id": qid, "test_id": test_id})

    def handle_delete_question(self, qid_or_test_id: str):
        """Archives or removes a question from SQLite and the XML file."""
        conn = get_db()
        with conn:
            cursor = conn.cursor()
            if qid_or_test_id.isdigit():
                cursor.execute("SELECT q.*, ts.file_path FROM questions q LEFT JOIN test_suites ts ON q.suite_id = ts.id WHERE q.id = ?", (int(qid_or_test_id),))
            else:
                cursor.execute("SELECT q.*, ts.file_path FROM questions q LEFT JOIN test_suites ts ON q.suite_id = ts.id WHERE q.test_id = ?", (qid_or_test_id,))
            q_row = cursor.fetchone()
            if not q_row:
                self.send_error_json(f"Question '{qid_or_test_id}' not found", 404)
                return

            q = dict(q_row)
            test_id = q["test_id"]
            suite_file = os.path.basename(q.get("file_path") or "questions_basic.xml")

            # Soft-delete by unlinking suite_id
            cursor.execute("UPDATE questions SET suite_id = NULL WHERE id = ?", (q["id"],))

        # Remove from XML
        self._remove_question_from_xml(suite_file, test_id)
        self.send_json({"success": True, "archived_test_id": test_id})

    def handle_sandbox_run(self):
        """Executes a live single prompt and evaluates assertion rules directly."""
        body = self.read_json_body()
        model = body.get("model", "llama3.2").strip()
        question = body.get("question", "").strip()
        system_prompt = body.get("system_prompt", "").strip()
        temperature = float(body.get("temperature", 0.0))
        max_tokens = int(body.get("max_tokens", 800))
        assertions_spec = body.get("assertions", [])

        if not question:
            self.send_error_json("Question prompt is required", 400)
            return

        client = LLMClient(host=DEFAULT_OLLAMA_URL, timeout=90)
        try:
            resp = client.send_chat(
                model=model,
                question=question,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens
            )
        except Exception as e:
            self.send_error_json(f"Inference error ({model}): {str(e)}", 502)
            return

        final_content = resp.get("content", "")
        thinking = resp.get("thinking", "")
        if thinking:
            full_output = f"<think>\n{thinking.strip()}\n</think>\n\n{final_content.strip()}"
        else:
            full_output = final_content

        metrics = resp.get("metrics", {})

        # Evaluate assertions against clean final_content to prevent CoT false negatives
        model_assertion = ModelAssertion()
        for a in assertions_spec:
            rtype = a.get("rule_type", "contains")
            exp = a.get("expected_values", [])
            cs = a.get("case_sensitive", False)
            model_assertion.add_from_spec(rtype, exp, cs)

        if thinking and not final_content.strip():
            eval_summary = {
                "all_passed": False,
                "results": [{
                    "rule": "response_delivered",
                    "passed": False,
                    "message": "Model failed to deliver an answer (truncated or halted in <think> phase)"
                }]
            }
        else:
            eval_target = final_content if thinking else (final_content if final_content else full_output)
            eval_summary = model_assertion.evaluate_all(eval_target, metrics)

        self.send_json({
            "model": model,
            "output": full_output,
            "metrics": metrics,
            "all_passed": eval_summary["all_passed"],
            "assertions": eval_summary["results"]
        })

    def handle_sandbox_stream(self):
        """Streams live completion tokens over SSE and returns assertion evaluation on completion."""
        body = self.read_json_body()
        model = body.get("model", "llama3.2").strip()
        question = body.get("question", "").strip()
        system_prompt = body.get("system_prompt", "").strip()
        temperature = float(body.get("temperature", 0.0))
        max_tokens = int(body.get("max_tokens", 800))
        assertions_spec = body.get("assertions", [])

        if not question:
            self.send_error_json("Question prompt is required", 400)
            return

        # Initialize SSE headers
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.send_cors_headers()
        self.end_headers()

        def send_sse(data_dict: Dict[str, Any]):
            payload = f"data: {json.dumps(data_dict)}\n\n".encode("utf-8")
            self.wfile.write(payload)
            self.wfile.flush()

        client = LLMClient(host=DEFAULT_OLLAMA_URL, timeout=120)
        start_time = time.perf_counter()

        try:
            if client.is_gemini(model):
                # Cloud Gemini fallback (chunked streaming / single execution streamed)
                resp = client.send_chat(
                    model=model,
                    question=question,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                final_content = resp.get("content", "")
                thinking = resp.get("thinking", "")
                metrics = resp.get("metrics", {})

                if thinking:
                    send_sse({"type": "token", "channel": "thinking", "text": thinking})
                if final_content:
                    send_sse({"type": "token", "channel": "content", "text": final_content})

                model_assertion = ModelAssertion()
                for a in assertions_spec:
                    rtype = a.get("rule_type", "contains")
                    exp = a.get("expected_values", [])
                    cs = a.get("case_sensitive", False)
                    model_assertion.add_from_spec(rtype, exp, cs)

                if thinking and not final_content.strip():
                    eval_summary = {
                        "all_passed": False,
                        "results": [{
                            "rule": "response_delivered",
                            "passed": False,
                            "message": "Model failed to deliver an answer (truncated or halted in <think> phase)"
                        }]
                    }
                else:
                    eval_target = final_content if thinking else (final_content if final_content else full_output)
                    eval_summary = model_assertion.evaluate_all(eval_target, metrics)
                full_output = f"<think>\n{thinking.strip()}\n</think>\n\n{final_content.strip()}" if thinking else final_content

                send_sse({
                    "type": "done",
                    "all_passed": eval_summary["all_passed"],
                    "assertions": eval_summary["results"],
                    "metrics": metrics,
                    "output": full_output,
                    "content": final_content,
                    "thinking": thinking
                })
            else:
                # Direct Ollama streaming over /api/chat with stream=True
                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                messages.append({"role": "user", "content": question})

                url = f"{DEFAULT_OLLAMA_URL}/api/chat"
                ollama_payload = {
                    "model": model,
                    "messages": messages,
                    "stream": True,
                    "options": {
                        "temperature": temperature,
                        "num_predict": max_tokens,
                        "num_ctx": 8192
                    }
                }

                req = urllib.request.Request(
                    url,
                    data=json.dumps(ollama_payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"}
                )

                full_thinking = []
                full_content = []
                final_chunk = {}

                with urllib.request.urlopen(req, timeout=120) as res:
                    for raw_line in res:
                        line = raw_line.decode("utf-8").strip()
                        if not line:
                            continue
                        chunk = json.loads(line)
                        msg = chunk.get("message", {})
                        t_token = msg.get("thinking", "")
                        c_token = msg.get("content", "")

                        if t_token:
                            full_thinking.append(t_token)
                            send_sse({"type": "token", "channel": "thinking", "text": t_token})
                        if c_token:
                            full_content.append(c_token)
                            send_sse({"type": "token", "channel": "content", "text": c_token})

                        if chunk.get("done"):
                            final_chunk = chunk

                wall_latency = round(time.perf_counter() - start_time, 2)
                thinking_str = "".join(full_thinking)
                content_str = "".join(full_content)

                prompt_tokens = final_chunk.get("prompt_eval_count", 0)
                eval_tokens = final_chunk.get("eval_count", len(content_str.split()))
                eval_dur_ns = final_chunk.get("eval_duration", 0)
                speed = round(eval_tokens / (eval_dur_ns / 1e9), 1) if eval_dur_ns > 0 else (round(eval_tokens / wall_latency, 1) if wall_latency > 0 else 0.0)

                metrics = {
                    "latency_sec": wall_latency,
                    "eval_tokens_per_sec": speed,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": eval_tokens,
                    "total_tokens": prompt_tokens + eval_tokens
                }

                model_assertion = ModelAssertion()
                for a in assertions_spec:
                    rtype = a.get("rule_type", "contains")
                    exp = a.get("expected_values", [])
                    cs = a.get("case_sensitive", False)
                    model_assertion.add_from_spec(rtype, exp, cs)

                if thinking_str and not content_str.strip():
                    eval_summary = {
                        "all_passed": False,
                        "results": [{
                            "rule": "response_delivered",
                            "passed": False,
                            "message": "Model failed to deliver an answer (truncated or halted in <think> phase)"
                        }]
                    }
                else:
                    eval_target = content_str if thinking_str else (content_str if content_str else full_output)
                    eval_summary = model_assertion.evaluate_all(eval_target, metrics)
                full_output = f"<think>\n{thinking_str.strip()}\n</think>\n\n{content_str.strip()}" if thinking_str else content_str

                send_sse({
                    "type": "done",
                    "all_passed": eval_summary["all_passed"],
                    "assertions": eval_summary["results"],
                    "metrics": metrics,
                    "output": full_output,
                    "content": content_str,
                    "thinking": thinking_str
                })

        except (BrokenPipeError, ConnectionResetError):
            # Client closed browser connection / aborted stream
            pass
        except Exception as e:
            try:
                send_sse({"type": "error", "error": str(e)})
            except Exception:
                pass
        finally:
            self.close_connection = True

    def handle_sync_questions(self):
        """Forces bidirectional re-synchronization between Questions/*.xml and SQLite."""
        conn = get_db()
        with conn:
            qmap = benchmark_store.sync_questions_from_xml(conn, xml_path_or_pattern=os.path.join(QUESTIONS_DIR, "*.xml"))
        self.send_json({"success": True, "synced_questions": len(qmap)})

    # ==========================================================================
    # Asynchronous Job Queue Handlers (Phase 7)
    # ==========================================================================

    def handle_launch_benchmark(self):
        """
        POST /api/benchmark/run
        Registers a multi-model benchmark job, enqueues it with the background worker,
        and immediately returns HTTP 202 Accepted in <20ms with job metadata and SSE stream URL.
        """
        body = self.read_json_body()
        models = body.get("models", [])
        if not models or not isinstance(models, list):
            self.send_error_json("Payload must contain a non-empty 'models' array.", 400)
            return

        suites = body.get("suites")
        if suites is not None and not isinstance(suites, list):
            suites = [suites]

        temperature = float(body.get("temperature", 0.0))
        max_tokens = int(body.get("max_tokens", 1200))
        concurrency = int(body.get("concurrency", 1))

        conn = get_db()
        with conn:
            job_id = benchmark_store.create_job(
                conn=conn,
                models=models,
                suites=suites,
                temperature=temperature,
                blanket_max_tokens=max_tokens,
                concurrency=concurrency
            )
            job = benchmark_store.get_job(conn, job_id)

        WORKER_INSTANCE.enqueue_job(job_id)

        self.send_json({
            "job_id": job_id,
            "job_uuid": job["job_uuid"],
            "status": "queued",
            "models": models,
            "suites": suites,
            "stream_url": f"/api/jobs/{job_id}/stream",
            "message": "Benchmark job accepted and queued for in-container execution."
        }, status_code=202)

    def handle_list_jobs(self):
        """GET /api/jobs - Returns historical and queued benchmark jobs."""
        conn = get_db()
        with conn:
            jobs = benchmark_store.list_jobs(conn, limit=50)
        self.send_json({
            "jobs": jobs,
            "total": len(jobs),
            "active_job_id": WORKER_INSTANCE.active_job_id
        })

    def handle_get_job(self, job_id_or_uuid: str):
        """GET /api/jobs/{id} - Returns metadata and status for a single job."""
        conn = get_db()
        with conn:
            job = benchmark_store.get_job(conn, job_id_or_uuid)
        if not job:
            self.send_error_json(f"Job '{job_id_or_uuid}' not found", 404)
            return
        job["is_active"] = (WORKER_INSTANCE.active_job_id == job["id"])
        self.send_json(job)

    def handle_abort_job(self, job_id_or_uuid: str):
        """POST /api/jobs/{id}/abort - Signals cancellation to an executing or queued job."""
        conn = get_db()
        with conn:
            job = benchmark_store.get_job(conn, job_id_or_uuid)
        if not job:
            self.send_error_json(f"Job '{job_id_or_uuid}' not found", 404)
            return
        WORKER_INSTANCE.request_abort(job["id"])
        self.send_json({
            "success": True,
            "job_id": job["id"],
            "message": f"Cancellation signal dispatched for Job #{job['id']}."
        })

    def handle_job_stream(self, job_id_or_uuid: str):
        """
        GET /api/jobs/{id}/stream
        Real-time telemetry stream using Server-Sent Events (SSE).
        Streams test progress, assertion evaluations, hardware latency, and model swapping.
        """
        conn = get_db()
        with conn:
            job = benchmark_store.get_job(conn, job_id_or_uuid)
        if not job:
            self.send_error_json(f"Job '{job_id_or_uuid}' not found", 404)
            return

        job_id = job["id"]

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_cors_headers()
        self.end_headers()

        def send_sse(event_data: Dict[str, Any]):
            msg = f"data: {json.dumps(event_data)}\n\n".encode("utf-8")
            self.wfile.write(msg)
            self.wfile.flush()

        sub_queue, backlog = WORKER_INSTANCE.subscribe(job_id)

        try:
            # Replay historical event backlog for late-joining or refreshed browser tabs
            for ev in backlog:
                send_sse(ev)

            # If job is already in a terminal state, end stream
            if job["status"] in ("completed", "failed", "aborted"):
                send_sse({"type": "job_status", "job_id": job_id, "status": job["status"]})
                return

            while True:
                try:
                    ev = sub_queue.get(timeout=2.0)
                    send_sse(ev)
                    if ev.get("type") in ("job_done", "job_error", "aborted"):
                        break
                except queue.Empty:
                    # Heartbeat comment to keep HTTP connection alive through proxies
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            WORKER_INSTANCE.unsubscribe(job_id, sub_queue)
            self.close_connection = True

    # ==========================================================================
    # XML Manipulation Helpers
    # ==========================================================================

    def _write_question_to_xml(self, suite_filename: str, q_data: Dict[str, Any], is_new: bool = True):
        xml_path = os.path.join(QUESTIONS_DIR, suite_filename)
        if not os.path.isfile(xml_path):
            # Create a new suite XML if not found
            root = ET.Element("test_suite", attrib={"name": suite_filename.replace(".xml", "").replace("questions_", "").replace("_", " ").title()})
            tree = ET.ElementTree(root)
        else:
            tree = ET.parse(xml_path)
            root = tree.getroot()

        target_tc = None
        for tc in root.findall("test_case"):
            if tc.attrib.get("id") == q_data["test_id"]:
                target_tc = tc
                break

        if target_tc is None:
            target_tc = ET.SubElement(root, "test_case")

        # Set attributes
        target_tc.attrib["id"] = q_data["test_id"]
        target_tc.attrib["tier"] = str(q_data["tier"])
        target_tc.attrib["category"] = q_data["category"]
        target_tc.attrib["difficulty"] = q_data["difficulty"]

        # Clear existing children for clean update
        target_tc.clear()
        target_tc.attrib["id"] = q_data["test_id"]
        target_tc.attrib["tier"] = str(q_data["tier"])
        target_tc.attrib["category"] = q_data["category"]
        target_tc.attrib["difficulty"] = q_data["difficulty"]

        name_el = ET.SubElement(target_tc, "name")
        name_el.text = q_data["name"]

        q_el = ET.SubElement(target_tc, "question")
        q_el.text = q_data["question_text"]

        if q_data.get("system_prompt"):
            sp_el = ET.SubElement(target_tc, "system_prompt")
            sp_el.text = q_data["system_prompt"]

        temp_el = ET.SubElement(target_tc, "temperature")
        temp_el.text = str(q_data["temperature"])

        if q_data.get("max_tokens"):
            mt_el = ET.SubElement(target_tc, "max_tokens")
            mt_el.text = str(q_data["max_tokens"])

        assertions_el = ET.SubElement(target_tc, "assertions")
        for a in q_data.get("assertions", []):
            assert_el = ET.SubElement(assertions_el, "assert")
            assert_el.attrib["type"] = a.get("rule_type", "contains")
            if a.get("case_sensitive"):
                assert_el.attrib["case_sensitive"] = "true"
            exp_vals = a.get("expected_values", [])
            if len(exp_vals) == 1 and not isinstance(exp_vals[0], list):
                assert_el.text = str(exp_vals[0])
            else:
                for ev in exp_vals:
                    e_el = ET.SubElement(assert_el, "expected")
                    e_el.text = str(ev)

        # Indent and save
        ET.indent(tree, space="    ", level=0)
        tree.write(xml_path, encoding="utf-8", xml_declaration=True)

    def _remove_question_from_xml(self, suite_filename: str, test_id: str):
        xml_path = os.path.join(QUESTIONS_DIR, suite_filename)
        if not os.path.isfile(xml_path):
            return
        tree = ET.parse(xml_path)
        root = tree.getroot()
        for tc in root.findall("test_case"):
            if tc.attrib.get("id") == test_id:
                root.remove(tc)
                break
        ET.indent(tree, space="    ", level=0)
        tree.write(xml_path, encoding="utf-8", xml_declaration=True)


def main():
    parser = argparse.ArgumentParser(description="LLM Benchmark Interactive Management Server")
    parser.add_argument("--host", default="0.0.0.0", help="Binding host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8080")), help="Port number (default: 8080)")
    parser.add_argument("--db", default=DEFAULT_DB_PATH, help="Path to benchmark.db")
    args = parser.parse_args()

    # Ensure DB exists
    if not os.path.exists(args.db):
        print(f"[INIT] Database not found at '{args.db}'. Initializing blank benchmark database...")
        conn = benchmark_store.get_connection(args.db)
        benchmark_store.init_database(conn)
        benchmark_store.sync_questions_from_xml(conn)
        conn.close()

    server_address = (args.host, args.port)
    httpd = ThreadedHTTPServer(server_address, BenchmarkWebHandler)

    print("=" * 70)
    print("  LLM Benchmark Web Management Dashboard & CRUD Server")
    print("=" * 70)
    print(f"  Web Dashboard UI : http://localhost:{args.port}")
    print(f"  REST API Endpoint: http://localhost:{args.port}/api/")
    print(f"  Database Storage : {os.path.abspath(args.db)}")
    print(f"  Ollama Inference : {DEFAULT_OLLAMA_URL}")
    print(f"  Google Gemini API: {'Configured' if os.environ.get('GEMINI_API_KEY') else 'Not Set'}")
    print("=" * 70)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[STOP] Shutting down web server gracefully...")
        httpd.server_close()


if __name__ == "__main__":
    main()
