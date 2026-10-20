#!/usr/bin/env python3
"""
testLLM.py - Automated Testing Runner for LLM Models (Ollama / Open-WebUI / OpenAI API)

Evaluates:
  1. Performance Metrics:
     - Response latency / Round-trip time (seconds / ms)
     - Generation speed (tokens per second)
     - Prompt evaluation speed (tokens per second)
     - Token counts (prompt tokens, completion tokens, total tokens)
     - Model load duration

  2. Rule-Based Assertions:
     - contains (substring presence)
     - contains_any (at least one of expected matches, e.g. "two" or "2")
     - contains_all (all expected matches must be present)
     - not_contains (prohibited substrings)
     - regex (pattern matching)
     - exact (exact string equality)
     - max_latency_sec (performance threshold)
     - min_tokens_per_sec (performance threshold)

Zero external dependencies - uses standard Python 3 libraries only.
"""

import sys
import os
import re
import json
import time
import argparse
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from typing import Dict, List, Any, Optional, Tuple

# Terminal color codes for clean CLI reporting
class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
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
        cls.BOLD = ""
        cls.DIM = ""
        cls.RESET = ""

# Automatically disable colors on non-tty terminals or if NO_COLOR is set
if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
    Colors.disable()


from modelAssertion import (
    BaseAssertion,
    AssertionResult,
    AssertionFactory,
    ModelAssertion,
)
import glob


class TestCase:
    """Represents a test question parsed from questions.xml."""
    def __init__(self, test_id: str, name: str, question: str,
                 system_prompt: str = "",
                 temperature: float = 0.0,
                 max_tokens: int = 1200,
                 model_override: Optional[str] = None,
                 assertions: Optional[ModelAssertion] = None,
                 source_file: str = ""):
        self.test_id = test_id
        self.name = name
        self.question = question
        self.system_prompt = system_prompt
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.model_override = model_override
        self.assertions = assertions if assertions is not None else ModelAssertion()
        self.source_file = source_file



def find_xml_files(path_or_pattern: str) -> List[str]:
    """Finds all XML files matching a directory, glob pattern, or single file."""
    if os.path.isdir(path_or_pattern):
        matched = glob.glob(os.path.join(path_or_pattern, "*.xml"))
    elif "*" in path_or_pattern or "?" in path_or_pattern:
        matched = glob.glob(path_or_pattern)
    elif os.path.isfile(path_or_pattern):
        matched = [path_or_pattern]
    else:
        # Check inside Questions/ directory as convenience
        fallback_dir = os.path.join("Questions", path_or_pattern)
        if os.path.isdir(fallback_dir):
            matched = glob.glob(os.path.join(fallback_dir, "*.xml"))
        else:
            matched = glob.glob(path_or_pattern)

    matched = [f for f in matched if f.lower().endswith(".xml")]
    matched.sort()
    return matched


def parse_questions_xml(xml_path: str) -> List[TestCase]:
    """Parses test cases and assertion rules from a single XML file."""
    if not os.path.isfile(xml_path):
        raise FileNotFoundError(f"Questions XML file not found at: {xml_path}")

    tree = ET.parse(xml_path)
    root = tree.getroot()
    base_file = os.path.basename(xml_path)

    test_cases = []
    for tc_elem in root.findall("test_case"):
        test_id = tc_elem.attrib.get("id", f"case-{len(test_cases)+1}")
        name = tc_elem.findtext("name", test_id).strip()
        question = tc_elem.findtext("question", "").strip()
        system_prompt = tc_elem.findtext("system_prompt", "").strip()

        temp_text = tc_elem.findtext("temperature", "0.0").strip()
        temperature = float(temp_text) if temp_text else 0.0

        max_tok_text = tc_elem.findtext("max_tokens", "1200").strip()
        max_tokens = int(max_tok_text) if max_tok_text else 1200

        model_override = tc_elem.findtext("model")
        if model_override:
            model_override = model_override.strip()

        assertions = ModelAssertion()
        assertions_elem = tc_elem.find("assertions")
        if assertions_elem is not None:
            for assert_elem in assertions_elem.findall("assert"):
                rule_type = assert_elem.attrib.get("type", "contains").strip()
                case_sensitive = assert_elem.attrib.get("case_sensitive", "false").lower() == "true"

                # Check for child <expected> tags or direct text
                expected_tags = assert_elem.findall("expected")
                if expected_tags:
                    expected_vals = [e.text.strip() for e in expected_tags if e.text]
                else:
                    text_val = assert_elem.text.strip() if assert_elem.text else ""
                    expected_vals = [text_val] if text_val else []

                assertions.add_from_spec(rule_type, expected_vals, case_sensitive)

        test_cases.append(TestCase(
            test_id=test_id,
            name=name,
            question=question,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            model_override=model_override,
            assertions=assertions,
            source_file=base_file
        ))

    return test_cases


def load_all_questions(path_or_pattern: str) -> Tuple[List[TestCase], List[str]]:
    """Loads all test cases from all matching XML files."""
    files = find_xml_files(path_or_pattern)
    if not files:
        raise FileNotFoundError(f"No XML files found matching pattern or path: '{path_or_pattern}'")

    all_cases = []
    for f in files:
        cases = parse_questions_xml(f)
        all_cases.extend(cases)

    return all_cases, files


class LLMClient:
    """Handles communication with Ollama, Open-WebUI, or OpenAI-compatible endpoints."""
    def __init__(self, host: str = "http://localhost:11434", api_type: str = "ollama",
                 api_key: Optional[str] = None, timeout: int = 60):
        self.host = host.rstrip("/")
        self.api_type = api_type.lower()
        self.api_key = api_key
        self.timeout = timeout

    def send_chat(self, model: str, question: str, system_prompt: str = "",
                  temperature: float = 0.0, max_tokens: int = 1200) -> Dict[str, Any]:
        """
        Dispatches request and measures execution time and hardware performance metrics.
        Returns: {
            "content": str,
            "metrics": Dict[str, Any],
            "raw_response": Dict[str, Any]
        }
        """
        messages = []
        # A/B Testing: Disabled system_prompt dispatch to test performance and compliance impact
        # if system_prompt:
        #     messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": question})

        if self.api_type == "ollama":
            url = f"{self.host}/api/chat"
            payload = {
                "model": model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                    "num_ctx": 8192
                }
            }
        else:
            # Open-WebUI or standard OpenAI endpoint
            if "/v1" in self.host or "/api" in self.host:
                url = f"{self.host}/chat/completions"
            elif ":3000" in self.host:
                url = f"{self.host}/api/chat/completions"
            else:
                url = f"{self.host}/v1/chat/completions"

            payload = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": False
            }

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        req_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=req_data, headers=headers)

        start_time = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                resp_bytes = resp.read()
                raw_json = json.loads(resp_bytes.decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {e.code} Error from {url}: {err_body}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"Network error connecting to {url}: {e.reason}") from e

        end_time = time.perf_counter()
        wall_latency_sec = end_time - start_time

        # Extract content and compute metrics
        metrics: Dict[str, Any] = {
            "latency_sec": round(wall_latency_sec, 3),
            "latency_ms": round(wall_latency_sec * 1000, 1),
        }

        if self.api_type == "ollama" and "message" in raw_json:
            msg = raw_json.get("message", {})
            content = msg.get("content", "")
            thinking = msg.get("thinking", "")
            done_reason = raw_json.get("done_reason", "")
            if not content and thinking and done_reason == "length":
                metrics["truncated_in_thinking"] = True
            
            # Nanosecond fields from Ollama
            total_dur_ns = raw_json.get("total_duration", 0)
            load_dur_ns = raw_json.get("load_duration", 0)
            prompt_eval_count = raw_json.get("prompt_eval_count", 0)
            prompt_eval_dur_ns = raw_json.get("prompt_eval_duration", 0)
            eval_count = raw_json.get("eval_count", 0)
            eval_dur_ns = raw_json.get("eval_duration", 0)

            metrics["prompt_tokens"] = prompt_eval_count
            metrics["completion_tokens"] = eval_count
            metrics["total_tokens"] = prompt_eval_count + eval_count
            metrics["load_duration_ms"] = round(load_dur_ns / 1e6, 2)

            if eval_dur_ns > 0:
                metrics["eval_tokens_per_sec"] = round(eval_count / (eval_dur_ns / 1e9), 2)
                metrics["eval_duration_sec"] = round(eval_dur_ns / 1e9, 3)
            else:
                metrics["eval_tokens_per_sec"] = 0.0

            if prompt_eval_dur_ns > 0:
                metrics["prompt_tokens_per_sec"] = round(prompt_eval_count / (prompt_eval_dur_ns / 1e9), 2)
            else:
                metrics["prompt_tokens_per_sec"] = 0.0

        else:
            # OpenAI / Open-WebUI format
            choices = raw_json.get("choices", [])
            content = choices[0].get("message", {}).get("content", "") if choices else ""
            usage = raw_json.get("usage", {})
            p_tok = usage.get("prompt_tokens", 0)
            c_tok = usage.get("completion_tokens", 0)
            metrics["prompt_tokens"] = p_tok
            metrics["completion_tokens"] = c_tok
            metrics["total_tokens"] = usage.get("total_tokens", p_tok + c_tok)
            if wall_latency_sec > 0 and c_tok > 0:
                metrics["eval_tokens_per_sec"] = round(c_tok / wall_latency_sec, 2)
            else:
                metrics["eval_tokens_per_sec"] = 0.0

        return {
            "content": content,
            "metrics": metrics,
            "raw_response": raw_json
        }


def warmup_model(client: LLMClient, model: str) -> None:
    """
    Verifies that model weights, CUDA kernels, and SWA / KV-cache buffers
    (num_ctx=8192) are active and warm in GPU VRAM before benchmark timing begins.
    """
    print(f"{Colors.DIM}Verifying model '{model}' readiness in GPU memory...{Colors.RESET}", end="", flush=True)
    t0 = time.perf_counter()
    try:
        client.send_chat(model=model, question="Warmup check: confirm ready.", max_tokens=5)
        dur = time.perf_counter() - t0
        print(f" {Colors.GREEN}[READY in {dur:.2f}s]{Colors.RESET}\n")
    except Exception as e:
        print(f" {Colors.YELLOW}[WARMUP SKIPPED: {e}]{Colors.RESET}\n")


def run_evaluation(client: LLMClient, default_model: str, test_cases: List[TestCase], verbose: bool = False, warmup: bool = True, blanket_max_tokens: int = 1200) -> Dict[str, Any]:
    """Runs test suite against a model and returns aggregate results."""
    results = []
    total_assertions = 0
    passed_assertions = 0
    total_latency = 0.0
    total_tokens_generated = 0

    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN} Running Test Suite on Model: {Colors.YELLOW}{default_model}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN} Endpoint: {Colors.RESET}{client.host} ({client.api_type.upper()})")
    print(f"{Colors.BOLD}{Colors.CYAN} Total Test Cases: {Colors.RESET}{len(test_cases)}")
    print(f"{Colors.BOLD}{Colors.CYAN} Blanket Max Tokens: {Colors.RESET}{blanket_max_tokens}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.RESET}\n")

    if warmup:
        warmup_model(client, default_model)

    for idx, tc in enumerate(test_cases, 1):
        target_model = tc.model_override or default_model
        source_prefix = f"[{tc.source_file}] " if tc.source_file else ""
        print(f"{Colors.BOLD}[Test {idx}/{len(test_cases)}] {source_prefix}{tc.name} ({tc.test_id}){Colors.RESET}")
        print(f"{Colors.DIM}Question:{Colors.RESET} {tc.question}")

        effective_max_tokens = blanket_max_tokens if (blanket_max_tokens and blanket_max_tokens > 0) else tc.max_tokens

        case_start = time.perf_counter()
        try:
            resp = client.send_chat(
                model=target_model,
                question=tc.question,
                system_prompt=tc.system_prompt,
                temperature=tc.temperature,
                max_tokens=effective_max_tokens
            )
            output_text = resp["content"]
            metrics = resp["metrics"]
            error_msg = None
        except Exception as e:
            output_text = ""
            metrics = {"latency_sec": round(time.perf_counter() - case_start, 3), "eval_tokens_per_sec": 0.0}
            error_msg = str(e)

        # Evaluate Assertions using ModelAssertion
        case_passed = True
        assertion_results = []
        if error_msg:
            case_passed = False
            raw_results = [
                AssertionResult(
                    rule_type="request_execution",
                    passed=False,
                    message=f"Execution error: {error_msg}"
                )
            ]
            total_assertions += 1
        else:
            raw_results = tc.assertions.evaluate(output_text, metrics)
            total_assertions += len(raw_results)
            passed_assertions += sum(1 for r in raw_results if r.passed)
            case_passed = tc.assertions.is_all_passed(raw_results)

        assertion_results = [r.to_dict() for r in raw_results]

        # Print Output Snippet
        clean_preview = output_text.strip().replace("\n", " ")
        if len(clean_preview) > 120:
            clean_preview = clean_preview[:117] + "..."
        if not output_text and metrics.get("truncated_in_thinking"):
            clean_preview = f"{Colors.YELLOW}(cut off in <think> phase at {effective_max_tokens} tokens - increase headroom){Colors.RESET}"
        print(f"{Colors.DIM}Answer:{Colors.RESET}   {clean_preview if clean_preview else '(empty/error)'}")

        # Print Metrics
        lat_sec = metrics.get("latency_sec", 0.0)
        tps = metrics.get("eval_tokens_per_sec", 0.0)
        c_tok = metrics.get("completion_tokens", 0)
        p_tok = metrics.get("prompt_tokens", 0)
        total_latency += lat_sec
        total_tokens_generated += c_tok

        perf_str = f"Latency: {Colors.CYAN}{lat_sec:.2f}s{Colors.RESET} | Speed: {Colors.CYAN}{tps:.1f} tok/s{Colors.RESET} | Tokens: {Colors.CYAN}{p_tok}+{c_tok}={p_tok+c_tok}{Colors.RESET}"
        print(f"{Colors.DIM}Metrics:{Colors.RESET}  {perf_str}")

        # Print Assertion Results
        for ar in assertion_results:
            status_tag = f"{Colors.GREEN}[PASS]{Colors.RESET}" if ar["passed"] else f"{Colors.RED}[FAIL]{Colors.RESET}"
            print(f"  {status_tag} {ar['message']}")

        if verbose and output_text:
            print(f"{Colors.DIM}--- Full Output ---{Colors.RESET}\n{output_text}\n{Colors.DIM}-------------------{Colors.RESET}")

        print()

        results.append({
            "test_id": tc.test_id,
            "name": tc.name,
            "model": target_model,
            "question": tc.question,
            "output": output_text,
            "metrics": metrics,
            "case_passed": case_passed,
            "assertions": assertion_results
        })

    passed_cases = sum(1 for r in results if r["case_passed"])
    failed_cases = len(test_cases) - passed_cases
    question_pass_rate = (passed_cases / len(test_cases) * 100) if test_cases else 0.0

    pass_rate = (passed_assertions / total_assertions * 100) if total_assertions > 0 else 0.0
    avg_speed = (total_tokens_generated / total_latency) if total_latency > 0 else 0.0

    # Console summary block
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN} Model Evaluation Complete: {Colors.YELLOW}{default_model}{Colors.RESET}")
    print(f" Questions Solved:  {Colors.BOLD}{passed_cases}/{len(test_cases)} ({question_pass_rate:.1f}%){Colors.RESET}")
    print(f" Assertions Passed: {passed_assertions}/{total_assertions} ({pass_rate:.1f}%)")
    print(f" Generation Speed:  {avg_speed:.2f} tok/s | Total Latency: {total_latency:.2f}s")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.RESET}\n")

    summary = {
        "model": default_model,
        "endpoint": client.host,
        "total_questions": len(test_cases),
        "questions_solved": passed_cases,
        "questions_failed": failed_cases,
        "question_pass_rate_pct": round(question_pass_rate, 1),
        "total_cases": len(test_cases),
        "passed_cases": passed_cases,
        "failed_cases": failed_cases,
        "case_pass_rate_pct": round(question_pass_rate, 1),
        "total_assertions": total_assertions,
        "passed_assertions": passed_assertions,
        "failed_assertions": total_assertions - passed_assertions,
        "pass_rate_pct": round(pass_rate, 1),
        "assertion_pass_rate_pct": round(pass_rate, 1),
        "total_latency_sec": round(total_latency, 2),
        "total_tokens_generated": total_tokens_generated,
        "avg_tokens_per_sec": round(avg_speed, 2),
        "cases": results
    }

    return summary


def print_comparison_table(summaries: List[Dict[str, Any]]):
    """Prints a comparative table if multiple models were tested."""
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*96}{Colors.RESET}")
    print(f"{Colors.BOLD}{'MODEL COMPARISON & BENCHMARK SUMMARY':^96}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*96}{Colors.RESET}")
    header = f"{'Model':<20} | {'Questions Solved':<18} | {'Q Pass %':<10} | {'Assertions':<14} | {'Avg Speed':<14} | {'Total Time':<10}"
    print(header)
    print("-" * 96)

    for s in summaries:
        q_pct = s.get("question_pass_rate_pct", s.get("case_pass_rate_pct", 0.0))
        color = Colors.GREEN if q_pct == 100.0 else (Colors.YELLOW if q_pct >= 70.0 else Colors.RED)
        q_str = f"{s.get('questions_solved', s.get('passed_cases', 0))}/{s.get('total_cases', 0)}"
        q_pct_str = f"{color}{q_pct:.1f}%{Colors.RESET}"
        assert_str = f"{s['passed_assertions']}/{s['total_assertions']}"
        speed_str = f"{s['avg_tokens_per_sec']} tok/s"
        time_str = f"{s['total_latency_sec']}s"
        print(f"{s['model']:<20} | {q_str:<18} | {q_pct_str:<19} | {assert_str:<14} | {speed_str:<14} | {time_str:<10}")

    print(f"{Colors.BOLD}{Colors.CYAN}{'='*96}{Colors.RESET}\n")


def sanitize_filename(name: str) -> str:
    """Replaces characters that are illegal in Windows folder and file names."""
    return re.sub(r'[\\/:*?"<>|]', '_', name)


def export_markdown_report(summaries: Any, output_path: str):
    """Exports test results to a formatted Markdown file."""
    if not isinstance(summaries, list):
        summaries = [summaries]
    lines = [
        "# LLM Evaluation & Benchmark Report",
        f"Generated at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n",
        "## Summary Comparison",
        "| Model | Questions Solved | Question Pass Rate | Assertions Passed | Avg Generation Speed | Total Latency |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |"
    ]
    for s in summaries:
        q_solved = s.get('questions_solved', s.get('passed_cases', 0))
        q_total = s.get('total_cases', 0)
        q_pct = s.get('question_pass_rate_pct', s.get('case_pass_rate_pct', 0.0))
        lines.append(f"| **{s['model']}** | {q_solved}/{q_total} | {q_pct}% | {s['passed_assertions']}/{s['total_assertions']} | {s['avg_tokens_per_sec']} tok/s | {s['total_latency_sec']}s |")

    lines.append("\n## Detailed Test Results\n")
    for s in summaries:
        lines.append(f"### Model: `{s['model']}`\n")
        for c in s["cases"]:
            status_icon = "✅ PASS" if c["case_passed"] else "❌ FAIL"
            lines.append(f"#### {status_icon} [{c['test_id']}] {c['name']}")
            lines.append(f"- **Question**: {c['question']}")
            lines.append(f"- **Answer**: `{c['output'].strip()}`")
            m = c["metrics"]
            lines.append(f"- **Performance**: Latency: `{m.get('latency_sec')}s` | Speed: `{m.get('eval_tokens_per_sec')} tok/s` | Tokens: `{m.get('prompt_tokens',0)}+{m.get('completion_tokens',0)}`")
            lines.append("- **Rule Assertions**:")
            for a in c["assertions"]:
                a_icon = "✓" if a["passed"] else "✗"
                lines.append(f"  - [{a_icon}] {a['message']}")
            lines.append("")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Markdown report saved to: {output_path}")


def load_dotenv(env_path: str = ".env"):
    """Loads key-value pairs from .env file into os.environ if not already set."""
    if not os.path.isfile(env_path):
        return
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("'\"")
                    if key and key not in os.environ:
                        os.environ[key] = val
    except Exception as e:
        print(f"Warning: Could not read .env file: {e}", file=sys.stderr)


def main():
    load_dotenv(".env")

    # Read defaults from .env / environment variables
    env_model = os.environ.get("TEST_MODEL") or os.environ.get("LLM_MODEL") or "llama3.2"
    env_questions = os.environ.get("QUESTIONS_PATH") or os.environ.get("QUESTIONS_FILE") or "Questions/*.xml"
    env_endpoint = os.environ.get("LLM_ENDPOINT", "ollama")
    env_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

    env_metrics_dir = os.environ.get("METRICS_DIR", "Test metrics")

    parser = argparse.ArgumentParser(
        description="testLLM.py - Automated Runner for Testing LLM Models with Rule Assertions & Performance Metrics"
    )
    parser.add_argument(
        "--model", "-m", default=env_model,
        help=f"Model name(s) to test. Default (from .env): '{env_model}'"
    )
    parser.add_argument(
        "--questions", "-q", default=env_questions,
        help=f"Path, directory, or glob pattern for questions XML files. Default (from .env): '{env_questions}'"
    )
    parser.add_argument(
        "--endpoint", choices=["ollama", "openai", "openwebui"], default=env_endpoint,
        help=f"API backend type: 'ollama' or 'openai'/'openwebui'. Default (from .env): '{env_endpoint}'"
    )
    parser.add_argument(
        "--host", default=env_host,
        help=f"Host URL (e.g. 'http://localhost:11434'). Default (from .env): '{env_host}'"
    )
    parser.add_argument(
        "--api-key", default=os.environ.get("OPENAI_API_KEY", ""),
        help="API key or Bearer token (optional, for Open-WebUI or protected OpenAI endpoints)."
    )
    parser.add_argument(
        "--timeout", type=int, default=60,
        help="Request timeout in seconds. Default: 60"
    )
    parser.add_argument(
        "--metrics-dir", default=env_metrics_dir,
        help=f"Directory to store timestamped test metrics per model. Default: '{env_metrics_dir}'"
    )
    parser.add_argument(
        "--output-json", default=None,
        help="Optional custom path to save consolidated JSON results. Default: None"
    )
    parser.add_argument(
        "--output-md", default=None,
        help="Optional custom path to save consolidated Markdown report. Default: None"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Print full model output responses in console."
    )
    parser.add_argument(
        "--no-warmup", action="store_true",
        help="Skip pre-warming request before test execution."
    )
    parser.add_argument(
        "--max-tokens", type=int, default=1200,
        help="Blanket max generation tokens per request across all questions. Default: 1200"
    )

    args = parser.parse_args()

    # Determine default host
    host = args.host
    if not host:
        if args.endpoint in ["openai", "openwebui"]:
            host = "http://localhost:3000"
        else:
            host = "http://localhost:11434"

    # Parse all questions XML files matching path/pattern
    try:
        test_cases, loaded_files = load_all_questions(args.questions)
        print(f"{Colors.DIM}[INFO] Loaded {len(test_cases)} question(s) from {len(loaded_files)} file(s): {', '.join(loaded_files)}{Colors.RESET}")
    except Exception as e:
        print(f"{Colors.RED}Error loading XML questions from '{args.questions}': {e}{Colors.RESET}", file=sys.stderr)
        sys.exit(1)

    client = LLMClient(
        host=host,
        api_type=args.endpoint,
        api_key=args.api_key,
        timeout=args.timeout
    )

    # Split multiple models if comma-separated
    models = [m.strip() for m in args.model.split(",") if m.strip()]

    all_summaries = []
    for model_name in models:
        summary = run_evaluation(client, model_name, test_cases, verbose=args.verbose, warmup=not args.no_warmup, blanket_max_tokens=args.max_tokens)
        all_summaries.append(summary)

    # Print comparison table if multiple models were tested
    if len(all_summaries) > 1:
        print_comparison_table(all_summaries)

    # Export results: .\Test metrics\<model name>\<date time>_out.json & .md
    timestamp_str = time.strftime("%Y-%m-%d_%H-%M-%S")
    metrics_root = args.metrics_dir or "Test metrics"

    for summary in all_summaries:
        model_name = summary["model"]
        safe_model_name = sanitize_filename(model_name)
        model_dir = os.path.join(metrics_root, safe_model_name)
        os.makedirs(model_dir, exist_ok=True)

        model_json_path = os.path.join(model_dir, f"{timestamp_str}_out.json")
        model_md_path = os.path.join(model_dir, f"{timestamp_str}_out.md")

        try:
            with open(model_json_path, "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2)
            print(f"JSON metrics saved to: {model_json_path}")
        except Exception as e:
            print(f"Warning: Failed to save JSON report to {model_json_path}: {e}")

        try:
            export_markdown_report([summary], model_md_path)
        except Exception as e:
            print(f"Warning: Failed to save Markdown report to {model_md_path}: {e}")

    # If multiple models were tested, also save comparison report
    if len(all_summaries) > 1:
        comp_dir = os.path.join(metrics_root, "comparison")
        os.makedirs(comp_dir, exist_ok=True)
        comp_json_path = os.path.join(comp_dir, f"{timestamp_str}_comparison.json")
        comp_md_path = os.path.join(comp_dir, f"{timestamp_str}_comparison.md")
        try:
            with open(comp_json_path, "w", encoding="utf-8") as f:
                json.dump(all_summaries, f, indent=2)
            print(f"Comparison JSON saved to: {comp_json_path}")
        except Exception as e:
            print(f"Warning: Failed to save comparison JSON: {e}")

        try:
            export_markdown_report(all_summaries, comp_md_path)
        except Exception as e:
            print(f"Warning: Failed to save comparison Markdown: {e}")

    # Save optional custom output files if explicitly specified via CLI
    if args.output_json:
        try:
            with open(args.output_json, "w", encoding="utf-8") as f:
                json.dump(all_summaries, f, indent=2)
            print(f"Custom JSON saved to: {args.output_json}")
        except Exception as e:
            print(f"Warning: Failed to save custom JSON to {args.output_json}: {e}")

    if args.output_md:
        try:
            export_markdown_report(all_summaries, args.output_md)
        except Exception as e:
            print(f"Warning: Failed to save custom Markdown to {args.output_md}: {e}")

    # Return non-zero exit code if any model had failing assertions
    overall_q_failures = sum(s.get("questions_failed", s.get("failed_cases", 0)) for s in all_summaries)
    overall_failures = sum(s["failed_assertions"] for s in all_summaries)
    if overall_failures > 0 or overall_q_failures > 0:
        print(f"\n{Colors.YELLOW}Completed with {overall_q_failures} unsolved question(s) ({overall_failures} assertion failure(s)).{Colors.RESET}")
        sys.exit(1)
    else:
        print(f"\n{Colors.GREEN}All questions and assertions passed successfully!{Colors.RESET}")
        sys.exit(0)


if __name__ == "__main__":
    main()
