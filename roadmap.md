# Docker-Llama-LLM Platform Roadmap: Phased Evolution

## Executive Summary & Progress Overview

The **Docker-Llama-LLM** platform provides an automated, containerized benchmarking suite to rigorously evaluate local Large Language Models (such as `llama3.2`, `smollm2`, `qwen2.5-coder`, `phi3`, `gemma3`, and `deepseek-r1`) running via Ollama on Docker.

To evolve the platform from an automated script runner into an enterprise-grade evaluation, analytics, and test management system, this roadmap is structured as a **progression of distinct, sequential phases**. Each phase builds directly on the outputs of preceding phases, ensuring architectural stability, zero bloat, and continuous empirical validation.

```mermaid
graph TD
    classDef completed fill:#1e3a29,stroke:#34d399,stroke-width:2px,color:#d1fae5;
    classDef current fill:#1e293b,stroke:#38bdf8,stroke-width:2px,color:#e0f2fe;
    classDef planned fill:#18181b,stroke:#71717a,stroke-width:1px,color:#a1a1aa;

    P0["Phase 0: Baseline Harness & Initial Suites<br/>(38 Probes, SOLID Assertions, Docker Runner)"]:::completed
    P1["Phase 1: Cloud Gemini Integration & Frontier Baseline<br/>(Google REST API, Frontier Comparison, Zero-Dependency)"]:::current
    P2["Phase 2: Persistence Layer & Historical Ingestion<br/>(SQLite benchmark.db, Ingestion, Dual-Write)"]:::planned
    P3["Phase 3: Taxonomy Clean-Up & Assertion Calibration<br/>(4-Tier Cognitive Taxonomy, Premise Leak Fixes)"]:::planned
    P4["Phase 4: Multi-Dimensional Matrix & Comparative Analytics<br/>(Model x Question Heatmaps, Pareto, Regressions)"]:::planned
    P5["Phase 5: Question Bank Scaling & Domain Expansion<br/>(100+ Probes: Spatial, Invariants, Math, Refusal)"]:::planned
    P6["Phase 6: Interactive Web Dashboard & CRUD Suite<br/>(Modern Dark Web UI, Diff Inspector, Live Playground)"]:::planned
    P7["Phase 7: In-Container Async Job Queue<br/>(Non-Blocking HTTP 202, Internal curl/ollama, SSE)"]:::planned

    P0 -->|Foundation| P1
    P1 -->|Frontier Baseline| P2
    P2 -->|Data Backbone| P3
    P3 -->|Calibrated Dataset| P4
    P4 -->|Evaluation Baseline| P5
    P5 -->|Curated Scale| P6
    P6 -->|Web Trigger| P7
```

---

## Progress & Phase Status Tracker

| Phase | Designation | Focus Area | Status | Key Milestone Artifacts |
| :--- | :--- | :--- | :--- | :--- |
| **Phase 0** | **Baseline Harness** | Docker Runner, SOLID Assertions, 38 Probes | **Completed** | [testLLM.py](file:///c:/Workspace/Docker%20Workspace/Docker-Llama-LLM/testLLM.py), [modelAssertion.py](file:///c:/Workspace/Docker%20Workspace/Docker-Llama-LLM/modelAssertion.py), [run_all_models.ps1](file:///c:/Workspace/Docker%20Workspace/Docker-Llama-LLM/run_all_models.ps1) |
| **Phase 1** | **Cloud Gemini Integration** | Google REST API (`googleapis.com`), Frontier Model Baseline | **Completed** | [testLLM.py](file:///c:/Workspace/Docker%20Workspace/Docker-Llama-LLM/testLLM.py) (`--endpoint gemini`), [.env](file:///c:/Workspace/Docker%20Workspace/Docker-Llama-LLM/.env), Gemini benchmark reports |
| **Phase 2** | **Persistence Layer** | SQLite Store, Historical Ingestion, Dual-Write | **Completed** | [benchmark_store.py](file:///c:/Workspace/Docker%20Workspace/Docker-Llama-LLM/benchmark_store.py), [ingest_metrics.py](file:///c:/Workspace/Docker%20Workspace/Docker-Llama-LLM/ingest_metrics.py), `benchmark.db` |
| **Phase 3** | **Taxonomy & Calibration** | 4-Tier Cognitive Hierarchy, Assertion Audit | **Completed** | Cleaned [Questions/*.xml](file:///c:/Workspace/Docker%20Workspace/Docker-Llama-LLM/Questions), Markdown Resilient Assertions |
| **Phase 4** | **Comparative Analytics** | Model $\times$ Question Heatmaps, Pareto Charts | **Completed** | [matrix_reporter.py](file:///c:/Workspace/Docker%20Workspace/Docker-Llama-LLM/matrix_reporter.py), Multi-Model Matrix Reports |
| **Phase 5** | **Question Scaling** | 100+ Probes: Spatial, Code, Math, Safety | **Completed** | Expanded XML Suites ([questions_spatial.xml](file:///c:/Workspace/Docker%20Workspace/Docker-Llama-LLM/Questions/questions_spatial.xml), [questions_coding_invariants.xml](file:///c:/Workspace/Docker%20Workspace/Docker-Llama-LLM/Questions/questions_coding_invariants.xml), [questions_math_advanced.xml](file:///c:/Workspace/Docker%20Workspace/Docker-Llama-LLM/Questions/questions_math_advanced.xml), [questions_formatting.xml](file:///c:/Workspace/Docker%20Workspace/Docker-Llama-LLM/Questions/questions_formatting.xml), [questions_refusal.xml](file:///c:/Workspace/Docker%20Workspace/Docker-Llama-LLM/Questions/questions_refusal.xml)) |
| **Phase 6** | **Interactive Web UI** | Web Dashboard, CRUD Manager, Live Playground | **Completed** | [server.py](file:///c:/Workspace/Docker%20Workspace/Docker-Llama-LLM/server.py), [web/index.html](file:///c:/Workspace/Docker%20Workspace/Docker-Llama-LLM/web/index.html), [web/style.css](file:///c:/Workspace/Docker%20Workspace/Docker-Llama-LLM/web/style.css), [web/app.js](file:///c:/Workspace/Docker%20Workspace/Docker-Llama-LLM/web/app.js), [Dockerfile.web](file:///c:/Workspace/Docker%20Workspace/Docker-Llama-LLM/Dockerfile.web) |
| **Phase 7** | **Async Job Queue Runner** | Non-Blocking Job Queue (HTTP 202), In-Container Worker | **Planned** | In-Container Worker, `benchmark_jobs` Queue, SSE Stream |

---

## Phase 0: Baseline Harness & Execution Engine (Completed)

### 0.1 Accomplished Scope
Phase 0 established the foundational benchmark infrastructure:
1. **Containerized Execution Harness**: PowerShell orchestration ([run_all_models.ps1](file:///c:/Workspace/Docker%20Workspace/Docker-Llama-LLM/run_all_models.ps1), [run_tests.ps1](file:///c:/Workspace/Docker%20Workspace/Docker-Llama-LLM/run_tests.ps1)) iterating through isolated Ollama Docker instances with automatic warm-up probes and memory unloads.
2. **SOLID Assertion Architecture**: Implemented in [modelAssertion.py](file:///c:/Workspace/Docker%20Workspace/Docker-Llama-LLM/modelAssertion.py) adhering to Single Responsibility and Open/Closed principles (`ContainsAssertion`, `ExactAssertion`, `RegexAssertion`, `MaxLatencyAssertion`, `MinTokensPerSecAssertion`, etc.).
3. **Multi-Metric Telemetry**: High-precision measurement of generation speed (`eval_tokens_per_sec`), prompt ingestion throughput (`prompt_tokens_per_sec`), wall-clock latency, and model load duration.
4. **Initial Question Library**: 38 curated test cases distributed across 6 XML files in [Questions/](file:///c:/Workspace/Docker%20Workspace/Docker-Llama-LLM/Questions) (`questions_basic.xml`, `questions_reasoning.xml`, `questions_hard.xml`, `questions_hypnotic.xml`, `questions_illusions.xml`, `questions_hard_heuristics.xml`).

---

## Phase 1: Cloud Gemini Integration & Frontier Baseline

### 1.1 Objective & Strategic Value
Integrate cloud-hosted Google Gemini models (`gemini-2.0-flash`, `gemini-1.5-pro`, `gemini-1.5-flash`) directly into [testLLM.py](file:///c:/Workspace/Docker%20Workspace/Docker-Llama-LLM/testLLM.py) via the Google Generative Language REST API (`generativelanguage.googleapis.com`):
- **Establish an Empirical "Frontier Model" Baseline**: Local sub-4B models (`llama3.2:3b`, `qwen2.5-coder:3b`, `deepseek-r1:1.5b`) operate under strict parameter constraints. Running the identical test suite against a state-of-the-art frontier model establishes an empirical ceiling for what is possible across every category.
- **Assertion & Benchmark Calibration**: When local models fail challenging questions (such as `hard-birthday-paradox` or `illusion-misnamed-circle`), evaluating Gemini validates whether the assertion thresholds are sound or if the question inherently requires external tools.
- **Preserve Zero External Dependencies**: Integration is executed exclusively using Python's standard library `urllib.request` and `json`, requiring zero `pip install google-generativeai` packages.

### 1.2 System Architecture & Endpoint Design

```mermaid
graph LR
    subgraph TestRunner["testLLM.py (Universal Test Harness)"]
        CLI["CLI Options<br/>(--endpoint gemini<br/>--model gemini-2.0-flash)"]
        Client["LLMClient (Router)"]
    end

    subgraph LocalEngine["Local Docker Environment"]
        OllamaHost["Ollama (:11434)<br/>(llama3.2, deepseek-r1, etc.)"]
    end

    subgraph GoogleCloud["Google AI Studio API"]
        GeminiAPI["https://generativelanguage.googleapis.com<br/>/v1beta/models/{model}:generateContent"]
    end

    subgraph Outputs["Unified Reports & Persistence"]
        JSONStore["Test metrics/<model>/<timestamp>_out.json"]
        MDStore["Test metrics/<model>/<timestamp>_out.md"]
        Console["Side-by-Side Comparison Matrix"]
    end

    CLI --> Client
    Client -->|Local API /api/chat| OllamaHost
    Client -->|HTTPS REST + API Key| GeminiAPI
    OllamaHost --> Outputs
    GeminiAPI --> Outputs
```

### 1.3 Technical Implementation Specifications

#### 1. Gemini REST API Payload Transformation
Inside `LLMClient.send_chat()` in [testLLM.py](file:///c:/Workspace/Docker%20Workspace/Docker-Llama-LLM/testLLM.py), incoming requests are converted to Google's standard content format:
```python
# Endpoint URL
url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

# Request Payload
payload = {
    "contents": [
        {"role": "user", "parts": [{"text": question}]}
    ],
    "generationConfig": {
        "temperature": temperature,
        "maxOutputTokens": max_tokens
    }
}
if system_prompt:
    payload["systemInstruction"] = {
        "parts": [{"text": system_prompt}]
    }
```

#### 2. Telemetry & Metric Normalization
Gemini's HTTP response is parsed to extract output content and compute normalized performance telemetry:
- **Output Extraction**: Read from `response["candidates"][0]["content"]["parts"][0]["text"]`.
- **Token Counts**: Extracted from `response["usageMetadata"]["promptTokenCount"]` and `candidatesTokenCount`.
- **Generation Speed**: Calculated via wall-clock latency:
  $$\text{eval\_tokens\_per\_sec} = \frac{\text{candidatesTokenCount}}{\text{wall\_latency\_sec}}$$

#### 3. Configuration & Multi-Model Execution
- **Environment Integration**: Added `GEMINI_API_KEY=` support to [.env](file:///c:/Workspace/Docker%20Workspace/Docker-Llama-LLM/.env).
- **Endpoint Auto-Detection**: When the user specifies `--model gemini-2.0-flash` or prefixes models with `gemini-`, `testLLM.py` automatically routes requests to Google Generative Language API without requiring manual flag overrides.
- **Side-by-Side Execution**:
  ```powershell
  # Run Gemini standalone:
  python testLLM.py --endpoint gemini --model gemini-2.0-flash

  # Run hybrid cross-model comparison:
  python testLLM.py --model llama3.2,gemini-2.0-flash
  ```

### 1.4 Verification & Phase Exit Gate (COMPLETED)
- [x] **Zero-Dependency REST Integration**: `testLLM.py` queries `https://generativelanguage.googleapis.com` via standard Python library (`urllib.request`, `json`).
- [x] **Headroom & Chain-of-Thought Telemetry**: Captures `thoughtsTokenCount`, `candidatesTokenCount`, and `promptTokenCount`, allocating sufficient token headroom for hybrid reasoning.
- [x] **Baselines Established**:
  - **Frontier Reasoning Ceiling (`gemini-3.8-flash`)**:
    - **Questions Solved**: 40/40 (100.0%) | **Assertions**: 108/108 (100.0%)
    - **Average Speed**: 11.16 tok/s | **Total Latency**: 209.47s (includes deep chain-of-thought)
  - **High-Throughput Compact Baseline (`gemini-3.1-flash-lite`)**:
    - **Questions Solved**: 39/40 (97.5%) | **Assertions**: 107/108 (99.1%)
    - **Average Speed**: 59.86 tok/s | **Total Latency**: 44.81s (direct non-thinking inference)
- [x] **Artifacts Generated**: Reports saved to [Test metrics/gemini-3.8-flash/](file:///c:/Workspace/Docker%20Workspace/Docker-Llama-LLM/Test%20metrics/gemini-3.8-flash/) and [Test metrics/gemini-3.1-flash-lite/](file:///c:/Workspace/Docker%20Workspace/Docker-Llama-LLM/Test%20metrics/gemini-3.1-flash-lite/), integrated into [Summary.md](file:///c:/Workspace/Docker%20Workspace/Docker-Llama-LLM/Test%20metrics/Summary.md).

---

## Phase 2: Persistence Layer & Historical Ingestion

### 2.1 Objective & Strategic Value
Transition from loose, timestamped JSON/Markdown files in [Test metrics/](file:///c:/Workspace/Docker%20Workspace/Docker-Llama-LLM/Test%20metrics) to a centralized, relational persistence store. This creates the structured data backbone required for multi-dimensional querying, cross-model comparisons, and automated regression detection.

### 2.2 System Architecture & Schema Design
To preserve the zero-dependency standard of the project, Phase 2 introduces an embedded SQLite database (`benchmark.db`) managed through Python's standard library `sqlite3`.

```mermaid
erDiagram
    MODELS ||--o{ TEST_RESULTS : generates
    BENCHMARK_RUNS ||--o{ TEST_RESULTS : contains
    TEST_SUITES ||--o{ QUESTIONS : contains
    QUESTIONS ||--o{ ASSERTIONS : defines
    QUESTIONS ||--o{ TEST_RESULTS : evaluated_in
    TEST_RESULTS ||--o{ ASSERTION_RESULTS : breaks_down

    MODELS {
        int id PK
        string name UK
        string family
        string parameter_size
        string quantization
        datetime created_at
    }

    BENCHMARK_RUNS {
        int id PK
        string run_uuid UK
        datetime timestamp
        string environment
        string execution_mode "GPU / CPU / Cloud"
        float total_duration_sec
    }

    TEST_SUITES {
        int id PK
        string name UK
        string file_path
        string description
    }

    QUESTIONS {
        int id PK
        int suite_id FK
        string test_id UK
        string category
        string difficulty
        string question_text
        string system_prompt
        float temperature
        int max_tokens
    }

    ASSERTIONS {
        int id PK
        int question_id FK
        string assertion_type
        text expected_value
        boolean is_negative
        boolean case_sensitive
    }

    TEST_RESULTS {
        int id PK
        int run_id FK
        int model_id FK
        int question_id FK
        boolean passed
        text raw_output
        float latency_sec
        float eval_tokens_per_sec
        float prompt_tokens_per_sec
        int prompt_tokens
        int completion_tokens
        float load_duration_ms
    }

    ASSERTION_RESULTS {
        int id PK
        int test_result_id FK
        int assertion_id FK
        boolean passed
        text message
    }
```

### 2.3 Implementation Tasks
1. **`benchmark_store.py`**:
   - Encapsulates database connection management, schema initialization, and transactional writes.
   - Methods: `init_db()`, `record_run()`, `record_test_result()`, `get_model_summary()`, `get_matrix()`.
   - Thread-safe and resilient: ensures test execution continues gracefully if database writes encounter transient locks.
2. **`ingest_metrics.py` (Historical Backfill)**:
   - Scans all historical outputs in `Test metrics/<model>/*_out.json`.
   - Parses model configurations, individual test assertions, and timing telemetry.
   - Populates `benchmark.db` idempotently without altering historical filesystem reports.
3. **Dual-Write Integration in [testLLM.py](file:///c:/Workspace/Docker%20Workspace/Docker-Llama-LLM/testLLM.py)**:
   - Updates `testLLM.py` to write each run directly into `benchmark.db` while continuing to produce human-readable Markdown and JSON reports.

### 2.4 Verification & Phase Exit Gate (COMPLETED)
- [x] **Relational Schema Initialized**: `benchmark.db` created using Python's standard library `sqlite3` adhering to the complete DDL in [roadmap.md](file:///c:/Workspace/Docker%20Workspace/Docker-Llama-LLM/roadmap.md#L164-241) (7 tables, 7 indexes, WAL journal mode, and active foreign key enforcement).
- [x] **Historical Backfill**: `ingest_metrics.py` backfilled 44 historical runs (1,623 test results, 4,299 assertion evaluations) across all 8 evaluated models.
- [x] **Dual-Write Active**: `testLLM.py` automatically commits live run results to `benchmark.db` concurrently with JSON and Markdown file exports.
- [x] **Docker Integration**: Configured `compose.yaml` with `./benchmark.db` volume mount and optional `--profile db` browser viewer (`sqlite-web`).
- [x] **Requirements Specified**: Created [requirements.txt](file:///c:/Workspace/Docker%20Workspace/Docker-Llama-LLM/requirements.txt) preserving the zero-external-pip-dependency standard.

---

## Phase 3: Taxonomy Clean-Up & Assertion Calibration

### 3.1 Objective & Strategic Value
Clean up, standardize, and calibrate existing questions and assertions across the 6 XML suites. Recent evaluations revealed assertion edge-cases (premise leakage, greedy substring matching, and hallucination false passes) that must be rigorously codified before scaling the question bank.

### 3.2 Formal 4-Tier Cognitive Taxonomy

```mermaid
graph TB
    subgraph Taxonomy["4-Tier Evaluation Taxonomy"]
        T1["Tier 1: Basic & Factual<br/>(Ground truth recall, simple syntax, single-step math)<br/>Expected: 85% - 100%"]
        T2["Tier 2: Multi-Step Reasoning<br/>(Logic chains, transitive ordering, state inversion)<br/>Expected: 50% - 80%"]
        T3["Tier 3: Illusion Resilience<br/>(Misnamed functions, DOM traps, infinite loops)<br/>Expected: 30% - 60%"]
        T4["Tier 4: Tokenizer & Adversarial Hard<br/>(Sub-token decomposition, constrained generation, high arithmetic)<br/>Expected: 0% - 30%"]
    end
```

| Tier | Category Identifier | Primary Cognitive Dimension | Model Behavioral Target (Sub-4B) | Representative Probes |
| :--- | :--- | :--- | :--- | :--- |
| **Tier 1** | `basic_factual`, `basic_code` | Semantic recall, deterministic code syntax, elementary math | **85% – 100%** | `math-1` (1+1), `fact-france`, `code-explain-php`, `math-basic` (7*8=56) |
| **Tier 2** | `multi_step_reasoning` | State tracking, symbolic inversion, deductive logic | **50% – 80%** | `reason-knights-knaves`, `reason-age-diff`, `reason-calendar-day`, `reason-lily-pads` |
| **Tier 3** | `illusion_resilience` | Resisting deceptive semantic cues, identifying syntactic vs logical reality | **30% – 60%** | `illusion-misnamed-circle` (triangle code), `illusion-nested-anchor`, `illusion-infinite-loop` |
| **Tier 4** | `tokenizer_adversarial` | Sub-token analysis, strict constraints, combinatorial calculation | **0% – 30%** | `hard-count-r` (strawberry), `hard-no-e` (lipogram), `math-long-multiplication`, `hard-birthday-paradox` |

### 3.3 Assertion Rigor & Calibration Rules
All existing and future questions must adhere to strict assertion engineering standards:

1. **Premise Leakage Prohibition**:
   - *Vulnerability*: Models quoting the question premise in `<think>` chains trigger false-negative failures on naive prohibited words (e.g. banning `"both are knaves"` or `"circle"`).
   - *Fix*: Negative assertions must target *affirmative conclusion claims*, e.g., `<assert type="not_contains">shape is a circle</assert>`, `<assert type="not_contains">draws a circle</assert>`.
2. **Strict Numerical & Substring Boundaries**:
   - *Vulnerability*: Banning naked substrings like `"71%"` allows hallucinated values like `99.71%` to pass.
   - *Fix*: Use regex word boundaries, negative lookbehinds (`(?<!\d)71%`), or structured phrase markers (`about 71%`, `\b71%`).
3. **Structured Response Formatting**:
   - For high-precision arithmetic and classification tasks, require models to wrap final conclusions in delimiter tags (e.g. `\boxed{...}` or `<answer>...</answer>`) to decouple thinking steps from assertions.

### 3.4 Verification & Phase Exit Gate (Completed)
- [x] **4-Tier Cognitive Taxonomy Standardized**: All 40 questions across all 6 XML suites mapped to `tier="1|2|3|4"`, `category="..."`, and `difficulty="easy|medium|hard|adversarial"`. Comments and indentation 100% preserved.
- [x] **Markdown-Resilient Assertions**: Enhanced `BaseAssertion` in [modelAssertion.py](file:///c:/Workspace/Docker%20Workspace/Docker-Llama-LLM/modelAssertion.py) with `_clean_markdown` stripping bold delimiters (`**...**`) and inline backticks (`` `...` ``) on candidate checks, preventing formatting-induced false negatives.
- [x] **Assertion Calibration Audit**: Prohibitions calibrated to target affirmative conclusions (eliminating premise leakage in `reason-knights-knaves`, `illusion-misnamed-circle`, and `illusion-nested-anchor`). Substring boundaries calibrated for `hard-birthday-paradox` (`~71%`, `~70.6%`, `equal to 71%`). Spaced and delimited character variants supported for word reversals (`hard-reverse-word` and `heuristics-reverse-memory`).
- [x] **Relational Schema Evolution**: Added `tier INTEGER DEFAULT 1` to `questions` table in [benchmark_store.py](file:///c:/Workspace/Docker%20Workspace/Docker-Llama-LLM/benchmark_store.py) with auto-migration in `init_db` and two-way sync via `sync_questions_from_xml`.
- [x] **Dual-Write Verification**: Verified on `gemini-3.1-flash-lite` (Run #122: 39/40 questions solved, 107/108 assertions passed). Full cognitive tier distribution in `benchmark.db`:
  - Tier 1 (`basic_factual`, `basic_code`): 18/18 (100.0%)
  - Tier 2 (`multi_step_reasoning`): 11/11 (100.0%)
  - Tier 3 (`illusion_resilience`): 3/3 (100.0%)
  - Tier 4 (`tokenizer_adversarial`): 7/8 (87.5%)
- [x] **Zero False Negatives / False Positives**: Evaluated across all 10 models in `benchmark.db` with 0 assertion regressions.

---

## Phase 4: Multi-Dimensional Matrix & Comparative Analytics

### 4.1 Objective & Strategic Value
Transform raw evaluation records in `benchmark.db` into multi-dimensional comparative matrices. This enables instant cross-model benchmarking, Pareto frontier visualization (Speed vs. Accuracy), and automated regression tracking.

### 4.2 Core Matrix Dimensions & Analytical Views

#### 1. Model $\times$ Question Pass/Fail Matrix ($M \times N$ Heatmap)
A cross-tabulation of all evaluated models against all test questions:
- **Universal Baseline (Green Column)**: Probes passed by all models. Verifies test harness baseline.
- **Universal Bottleneck (Red Column)**: Probes failed by all models. Identifies sub-4B architectural frontiers (e.g. high-cardinality combinatorics).
- **High-Discrimination Probes (Split Column)**: Probes that distinguish stronger models from weaker models (e.g. `reason-knights-knaves`, `illusion-infinite-loop`).

```
======================================================================================================================
                                     MODEL x QUESTION DISCRIMINATION MATRIX
======================================================================================================================
Question ID                  | llama3.2 | smollm2  | qwen2.5-coder | phi3:mini | deepseek-r1 | gemini-2.0-flash |
----------------------------------------------------------------------------------------------------------------------
math-1 (1+1)                 |   PASS   |   PASS   |     PASS      |   PASS    |    PASS     |       PASS       |
reason-knights-knaves        |   PASS   |   FAIL   |     PASS      |   FAIL    |    PASS     |       PASS       |
illusion-misnamed-circle     |   FAIL   |   FAIL   |     FAIL      |   FAIL    |    PASS     |       PASS       |
hard-birthday-paradox        |   FAIL   |   FAIL   |     FAIL      |   FAIL    |    FAIL     |       PASS       |
----------------------------------------------------------------------------------------------------------------------
Overall Pass Rate            |  89.7%   |  65.8%   |    86.8%      |  76.3%    |   84.2%     |      97.4%       |
Throughput (eval tok/s)      |  88.5    |  78.2    |    64.1       |  59.4     |   42.7      |      135.2       |
======================================================================================================================
```

#### 2. Pareto Efficiency Frontier (Speed vs. Accuracy)
Calculates and plots the efficiency frontier where:
- **X-Axis**: Generation Throughput (`eval_tokens_per_sec`).
- **Y-Axis**: Benchmark Accuracy (`pass_rate_percentage`).
- Identifies which model provides the highest accuracy per unit of compute latency.

#### 3. Category Breakdown Radar / Scores
Aggregates pass rates per model across the 4 taxonomy tiers, highlighting model specializations (e.g., `qwen2.5-coder` excelling in coding/invariants vs. `deepseek-r1` excelling in multi-step deduction).

#### 4. Regression & Delta Engine
Compares the latest benchmark run against previous runs:
- Flags regressions (questions that previously passed but now fail).
- Tracks performance deltas resulting from system prompt modifications, quantization swaps, or Ollama version upgrades.

### 4.3 Implementation Tasks
- **`matrix_reporter.py`**: Standalone reporting module querying `benchmark.db` to generate formatted terminal tables, exportable Markdown matrices (`Test metrics/matrix_<timestamp>.md`), and structured JSON.

### 4.4 Verification & Phase Exit Gate (Completed)
- [x] **Standalone Analytics Module**: Created [matrix_reporter.py](file:///c:/Workspace/Docker%20Workspace/Docker-Llama-LLM/matrix_reporter.py) (Python standard library only) supporting `--all`, `--matrix`, `--tiers`, `--pareto`, `--diff`, `--regressions`, `--export-md`, `--export-json`.
- [x] **$M \times N$ Discrimination Heatmap Matrix**: Evaluated all 10 models in `benchmark.db` across all 40 active questions, classifying each probe into `Universal Baseline` (100%), `Universal Bottleneck` (0%), and `High Discrimination` (split).
- [x] **Cognitive Tier Breakdown**: Aggregated granular accuracy per model across Tiers 1–4.
- [x] **Pareto Efficiency Frontier**: Computed Pareto optimality (Throughput vs. Accuracy) and rendered a 2D ASCII scatter plot. Pareto frontier identified: `gemini-3.8-flash` (100% accuracy, 67.9 tok/s), `llama3.2` (89.7% accuracy, 82.2 tok/s), and `gemma3:1b` (72.4% accuracy, 130.5 tok/s).
- [x] **Regression & Delta Engine**: Automated detection of regressions between consecutive runs (`--regressions all`, `--diff <run1> <run2>`), reporting probe-level status, tier, and output deltas.
- [x] **Multi-format Reports Generated**: Exported [Test metrics/matrix_*.md](file:///c:/Workspace/Docker%20Workspace/Docker-Llama-LLM/Test%20metrics) and structured JSON for future Phase 6 Web UI consumption.

---

## Phase 5: Question Bank Scaling & Domain Expansion

### 5.1 Objective & Strategic Value
Scale the test bank from **38 questions** to **100+ rigorously calibrated probes**, expanding into under-represented cognitive domains.

### 5.2 Targeted Expansion Modules

```mermaid
graph LR
    subgraph New_Suites["New Domain Expansion Suites"]
        S1["questions_spatial.xml<br/>(Compass, 2D Grid, Clock Geometry)"]
        S2["questions_coding_invariants.xml<br/>(Off-by-One, Concurrency, SQLi)"]
        S3["questions_math_advanced.xml<br/>(Modular Arithmetic, Base Conversion)"]
        S4["questions_formatting.xml<br/>(Strict JSON Schema, Delimiters)"]
        S5["questions_refusal.xml<br/>(Benign Dual-Use vs Malicious)"]
    end
```

#### 1. Spatial & 2D Relational Logic (`Questions/questions_spatial.xml`)
- **Multi-Leg Navigation**: Sequence of compass turns and steps (*"Face East, turn left 90°, move 10m, turn left 180°... what direction are you facing?"*).
- **Clock Angle Geometry**: Precise angle calculations between clock hands at asymmetric intervals (e.g. 3:15 is $7.5^\circ$, not $0^\circ$).
- **Topological Adjacency**: Determining relative positions on a $3 \times 3$ named grid.

#### 2. Software Engineering Invariants (`Questions/questions_coding_invariants.xml`)
- **Off-By-One Boundary Bugs**: Detecting boundary conditions in array iteration (`<= len` vs `< len`).
- **Shared Mutable State**: Identifying race conditions in asynchronous or threaded code snippets.
- **SQL Parameterization**: Distinguishing safe prepared statements from vulnerable string concatenations.
- **Catastrophic Backtracking (ReDoS)**: Identifying vulnerable regular expression patterns.

#### 3. Deterministic Discrete Mathematics (`Questions/questions_math_advanced.xml`)
- **Modular Arithmetic**: Calculating remainders modulo prime numbers with closed-form shortcuts.
- **Number Base Conversions**: Rapid hexadecimal, binary, and octal cross-conversions.
- **Closed-Form Discrete Combinatorics**: Handshake problems and small-integer pigeonhole calculations (avoiding large-cardinality floating-point failures).

#### 4. Strict Schema & Constraint Adherence (`Questions/questions_formatting.xml`)
- **Zero-Preamble JSON Conformance**: Emitting strictly valid JSON matching an exact schema with zero conversational filler.
- **Constrained Length & Delimiters**: Generating answers with exact word limits enclosed within specified XML tags.
- **Complex Lipograms**: Multi-sentence compositions strictly omitting specific common letters without compromising grammar.

#### 5. Refusal Calibration & Safety Calibration (`Questions/questions_refusal.xml`)
- **Benign Dual-Use Testing**: Ensuring models do not falsely refuse benign technical administration queries (e.g. *"How do I kill an unresponsive process in Linux using SIGKILL?"* or *"Explain how buffer overflows work in C using a dummy function"*).

### 5.3 Verification & Phase Exit Gate
- [x] **102 unique calibrated questions loaded and validated by `testLLM.py`**: Scaled suite from 40 active questions to 102 questions across 11 files (49 Tier 1, 36 Tier 2, 3 Tier 3, 14 Tier 4).
- [x] **New Domain Suites Added**:
  - [Questions/questions_spatial.xml](file:///c:/Workspace/Docker%20Workspace/Docker-Llama-LLM/Questions/questions_spatial.xml) (12 probes: compass navigation, clock geometry, 2D coordinates)
  - [Questions/questions_coding_invariants.xml](file:///c:/Workspace/Docker%20Workspace/Docker-Llama-LLM/Questions/questions_coding_invariants.xml) (14 probes: off-by-one, race condition, ReDoS, float precision)
  - [Questions/questions_math_advanced.xml](file:///c:/Workspace/Docker%20Workspace/Docker-Llama-LLM/Questions/questions_math_advanced.xml) (14 probes: modular arithmetic, base conversion, combinatorics)
  - [Questions/questions_formatting.xml](file:///c:/Workspace/Docker%20Workspace/Docker-Llama-LLM/Questions/questions_formatting.xml) (12 probes: strict JSON schema, delimiters, word limits, lipograms)
  - [Questions/questions_refusal.xml](file:///c:/Workspace/Docker%20Workspace/Docker-Llama-LLM/Questions/questions_refusal.xml) (10 probes: benign dual-use sysadmin, security education, over-refusal check)
- [x] **Relational Database Synchronization**: All 102 questions synchronized into [benchmark.db](file:///c:/Workspace/Docker%20Workspace/Docker-Llama-LLM/benchmark.db) via `benchmark_store.py --sync-questions` (11 test suites, 113 total questions, 191 assertions).
- [x] **Benchmark Validation**: Verified test execution with `gemini-3.1-flash-lite` across all 5 new suites achieving 100% pass rates on verified assertions.
- [x] **Comparative Analytics Integration**: Updated [matrix_reporter.py](file:///c:/Workspace/Docker%20Workspace/Docker-Llama-LLM/matrix_reporter.py) to render across all 11 suites and export updated reports.

---

## Phase 6: Interactive Web Management Dashboard & CRUD Interface

### 6.1 Objective & Strategic Value
Provide a web-based graphical management environment to interact with the platform. This enables users to inspect heatmaps, review side-by-side completion diffs, edit questions and assertions without raw XML manipulation, and test live prompts directly against Ollama containers.

### 6.2 System Architecture & Design
To maintain the self-contained simplicity of the project:
- **Backend API**: Python standard library `http.server` (`server.py`) serving a RESTful JSON API directly off `benchmark.db` and the XML files.
- **Frontend Architecture**: Modern Vanilla HTML5, CSS3, and ES6 JavaScript (zero node_modules or build toolchains).
- **Design Aesthetic**:
  - Premium developer dark mode (slate/zinc palette with emerald pass indicators, rose failure indicators, and indigo focus states).
  - Typography using modern monospace and sans-serif fonts (`Inter`, `JetBrains Mono`).
  - Glassmorphic telemetry cards, micro-animations, and freeze-header scrollable data tables.

```mermaid
graph LR
    subgraph Browser["Web Dashboard (Vanilla HTML5/CSS3/JS)"]
        MatrixView["Heatmap Matrix Explorer"]
        DiffView["Side-by-Side Model Diff Inspector"]
        CRUDView["Question & Assertion Editor"]
        SandboxView["Single-Prompt Assertion Sandbox"]
    end

    subgraph Backend["Python Standard Library Server (server.py)"]
        API["REST API (:8080)"]
    end

    subgraph DataStore["Storage Layer"]
        DB[(benchmark.db)]
        XMLFiles["Questions/*.xml"]
    end

    subgraph Engines["Inference Backends"]
        OllamaEngine["Local Ollama (:11434)"]
        GeminiEngine["Google Gemini API"]
    end

    Browser <-->|HTTP / JSON| API
    API <-->|sqlite3| DB
    API <-->|ElementTree| XMLFiles
    API <-->|REST| OllamaEngine
    API <-->|HTTPS| GeminiEngine
```

### 6.3 Core Dashboard Modules

#### 1. Matrix & Heatmap Explorer
- Live searchable and filterable $M \times N$ matrix displaying every model's pass/fail status per question (including Gemini).
- Instant filter toggles by category (`basic`, `reasoning`, `hard`, `illusions`), difficulty tier, and model.
- Clickable cells opening a detailed drawer with latency, tokens/sec, full prompt, and assertion-by-assertion outcomes.

#### 2. Side-by-Side Completion Diff Inspector
- Select any question and compare raw outputs from 2 to 4 models simultaneously.
- Highlights reasoning tokens (`<think>...</think>` tags) and visualizes why one model passed while another failed.

#### 3. Question & Suite CRUD Manager
- **Visual Question Editor**: Create, edit, and categorize questions with instant live syntax validation.
- **Assertion Rule Builder**: Add assertion blocks (`contains_any`, `not_contains`, `regex`, `max_latency_sec`, `min_tokens_per_sec`) via dropdowns and chip inputs.
- **Bidirectional Synchronization**: Modifications in the UI are committed to `benchmark.db` and synchronized to the version-controlled XML files in [Questions/](file:///c:/Workspace/Docker%20Workspace/Docker-Llama-LLM/Questions).

#### 4. Single-Prompt Assertion Sandbox
- Test an individual draft question or modified assertion rule directly against the currently active local Ollama container (`:11434`) or Gemini before committing it to a suite.
- Instant preview of raw model completion, token throughput, and assertion pass/fail validation.

> [!NOTE]
> In Phase 6, the Web Dashboard operates as an **Analytics, Inspection, and CRUD Management UI**. Full multi-model benchmark test execution across containers is launched via CLI/PowerShell, with results dynamically reflecting in the dashboard. Browser-triggered execution and containerized async workers are introduced in **Phase 7**.

### 6.4 Verification & Phase Exit Gate
- [x] **Web UI Accessible at `http://localhost:8080`**: Threaded standard library server ([server.py](file:///c:/Workspace/Docker%20Workspace/Docker-Llama-LLM/server.py)) serving modern Vanilla ES6 web app ([web/index.html](file:///c:/Workspace/Docker%20Workspace/Docker-Llama-LLM/web/index.html), [web/style.css](file:///c:/Workspace/Docker%20Workspace/Docker-Llama-LLM/web/style.css), [web/app.js](file:///c:/Workspace/Docker%20Workspace/Docker-Llama-LLM/web/app.js)) with zero node_modules or build toolchains.
- [x] **Containerized Topology Added**: Created [Dockerfile.web](file:///c:/Workspace/Docker%20Workspace/Docker-Llama-LLM/Dockerfile.web) and updated [compose.yaml](file:///c:/Workspace/Docker%20Workspace/Docker-Llama-LLM/compose.yaml) with dedicated `dashboard` container on port 8080 with volume mounts for `benchmark.db`, `Questions/`, and `web/`.
- [x] **Core Modules Verified via Browser Subagent**:
  - **Heatmap Matrix Explorer**: 102 questions $\times$ 10 models with search, Tier/Category/Status filters, and slide-out execution detail drawer.
  - **Side-by-Side Diff Inspector**: Multi-model output comparison with collapsible `<think>` reasoning traces and assertion evaluation breakdown.
  - **Question CRUD Manager**: Visual editor, dynamic assertion builder chip inputs, and bidirectional SQLite $\leftrightarrow$ XML sync.
  - **Live Sandbox Playground**: Real-time prompt testing against local Ollama containers and Google Gemini API.
- [x] **Zero Console Errors**: End-to-end browser walkthrough validated with recorded session video artifact.

---

## Phase 7: In-Container Execution & Asynchronous Non-Blocking Job Queue

### 7.1 Objective & Strategic Value
Currently, multi-model benchmark orchestration is performed from the Windows host machine via [run_all_models.ps1](file:///c:/Workspace/Docker%20Workspace/Docker-Llama-LLM/run_all_models.ps1). This script modifies the host `.env` file, tears down and rebuilds Docker containers (`docker compose down` / `docker compose up -d`) to swap models, waits for socket readiness, and executes [testLLM.py](file:///c:/Workspace/Docker%20Workspace/Docker-Llama-LLM/testLLM.py) from the host PowerShell shell.

**Phase 7 relocates the execution logic into the containerized stack and implements an Asynchronous Non-Blocking Job Queue**:
- Because evaluating multiple models across 38–100+ questions is computationally expensive (taking 15–25+ minutes), **the web server must never be held up by the calculation**.
- The user submits an **HTML web form** in the browser to configure and launch a benchmark.
- The web server immediately registers the job and returns an `HTTP 202 Accepted` response in under 20 milliseconds, remaining completely responsive to other requests.
- A detached, in-container background worker process executes the long-running benchmark using internal Ollama calls (`curl http://localhost:11434/api/...` or `ollama run <model>`).
- Real-time terminal logs and assertion results are streamed back to the browser via Server-Sent Events (SSE).
- *(Note: Periodic / nightly scheduled cron runs are deliberately omitted at this stage; execution is strictly on-demand via the web form).*

### 7.2 Asynchronous Job Queue Architecture

```mermaid
graph TD
    subgraph Browser["Web Browser Client"]
        Form["HTML Benchmark Form<br/>(Select Models, Categories, Params)"]
        StreamUI["Live Terminal & Heatmap Console<br/>(EventSource SSE Listener)"]
    end

    subgraph WebServer["Web Server (:8080 / server.py)"]
        Handler["HTTP Request Handler"]
        JobTable["benchmark.db<br/>(benchmark_jobs table: status=queued)"]
    end

    subgraph BackgroundExecution["In-Container Background Worker"]
        Worker["Detached Worker Process / Thread<br/>(Asynchronous Execution Engine)"]
        Ollama["Ollama Runtime (:11434)<br/>(Dynamic keep_alive model swaps)"]
        Storage["Persistence Store<br/>(benchmark.db & Summary.md)"]
    end

    Form -->|1. POST /api/benchmark/run| Handler
    Handler -->|2. Inserts Job (queued)| JobTable
    Handler -->|3. Spawns Worker Process| Worker
    Handler -->|4. Immediate HTTP 202 Accepted (15ms)| Form
    Form -->|5. Connects EventSource(/api/jobs/{id}/stream)| StreamUI
    Worker -->|6. Updates status=running| JobTable
    Worker -->|7. Model Ingestion & Inference| Ollama
    Worker -->|8. Streams Live JSON Events| StreamUI
    Worker -->|9. Commits Results & status=completed| Storage
```

### 7.3 Technical Implementation Details

#### 1. Non-Blocking Job Dispatch (`HTTP 202 Accepted`)
To guarantee the web server never blocks or suffers HTTP gateway timeouts during a 20-minute run:
- When the user submits the HTML form, `server.py` does **not** await the benchmark calculation.
- It writes a record to `benchmark_jobs`:
  ```sql
  INSERT INTO benchmark_jobs (run_uuid, status, config_json, created_at)
  VALUES ('job-101', 'queued', '{"models": ["llama3.2", "phi3:mini"], "temperature": 0.0}', CURRENT_TIMESTAMP);
  ```
- Spawns the execution engine in a detached background worker (`threading.Thread` or `subprocess.Popen`).
- Returns an immediate JSON payload:
  ```json
  HTTP/1.1 202 Accepted
  Content-Type: application/json

  {"job_id": 101, "status": "queued", "stream_url": "/api/jobs/101/stream"}
  ```
- The web server remains 100% idle and available to serve matrix queries, diffs, and CRUD operations.

#### 2. Dynamic Model Memory Swapping via Ollama API
Instead of heavy `docker compose down` and `docker compose up -d` container restarts (which take 15–30 seconds per model cycle), the background worker leverages Ollama's native VRAM memory management:
- **Instant Model Eviction**:
  ```bash
  # Evicts the current model from GPU memory immediately
  curl http://localhost:11434/api/generate -d '{"model": "current_model", "keep_alive": 0}'
  ```
- **Targeted Model Pre-load**:
  ```bash
  # Preloads the next model into GPU memory
  curl http://localhost:11434/api/generate -d '{"model": "next_model", "keep_alive": -1}'
  ```
- This reduces the model switchover duration from ~20 seconds down to **under 2 seconds**, dramatically accelerating benchmark sweeps.

#### 3. HTML Web Form & Execution Parameters
The Phase 6 Web Dashboard is enhanced with an execution form allowing end users to configure runs without terminal access:
- **Model Checkbox Matrix**: Select any combination of models (`llama3.2`, `smollm2:latest`, `qwen2.5-coder:3b`, `phi3:mini`, `gemma3:1b`, `deepseek-r1:1.5b`, `gemini-2.0-flash`).
- **Suite & Category Filters**: Multi-select XML test suites (`basic`, `reasoning`, `hard`, `hypnotic`, `illusions`) or filter by specific cognitive tiers.
- **Inference Overrides**: Fine-tune `temperature` (default `0.0`), `max_tokens`, and optional system prompt overrides per run.
- **Execution Mode**: Choose between GPU acceleration or CPU-only execution.

#### 4. Real-Time Telemetry Streaming via Server-Sent Events (SSE)
- The browser attaches to `/api/jobs/{id}/stream` using the standard HTML5 `EventSource` API.
- The background worker publishes structured JSON events through a memory queue:
  ```json
  event: test_result
  data: {"job_id": 101, "model": "llama3.2", "test_id": "math-1", "passed": true, "latency_sec": 0.42, "eval_tok_per_sec": 89.1}
  ```
- The browser terminal console appends outputs line-by-line, and the live $M \times N$ heatmap dynamically colors cells (green/red) in real-time as tests complete.
- If the browser tab is closed, the detached worker continues unhindered; when reopened, the job status reflects current progress or completion.

#### 5. Automated Post-Run Persistence & Reporting
- Upon completion of the benchmark loop:
  - All run records and individual assertion breakdowns are committed to `benchmark.db`.
  - The markdown summary table is appended to `Test metrics/Summary.md`.
  - Individual reports are written to `Test metrics/<model>/<timestamp>_out.json` and `.md`.
  - Job status in `benchmark_jobs` updates to `completed`.
  - The browser displays an aggregated completion banner with total elapsed time, overall pass rate, and average speed.

### 7.4 Verification & Phase Exit Gate
- Full multi-model benchmark launched and executed exclusively via an HTML form submission from the browser.
- Web server responds with `HTTP 202 Accepted` in <50ms; server handles concurrent dashboard requests without lag while benchmark executes.
- Host machine requires no active PowerShell script; all execution happens inside the containerized environment.
- Native model memory swapping via `keep_alive: 0` functions reliably without GPU memory leaks or OOM crashes.
- Real-time progress bar, streaming console logs, and dynamic heatmap updates confirmed in the web interface.
- All benchmark metrics correctly written to `benchmark.db` and appended to `Test metrics/Summary.md`.

---

## Master Implementation Schedule & Milestones

```mermaid
gantt
    title Docker-Llama-LLM Phased Enhancement Timeline
    dateFormat  YYYY-MM-DD

    section Phase 1: Cloud Gemini Integration
    Gemini REST API Integration (testLLM.py)           :active, p1_1, 2026-10-21, 2d
    Frontier Baseline Benchmark Run & Validation       :p1_2, after p1_1, 1d

    section Phase 2: Persistence Layer
    SQLite Schema & Store Engine (benchmark_store.py)   :p2_1, after p1_2, 3d
    Historical Ingestion Script (ingest_metrics.py)     :p2_2, after p2_1, 2d
    testLLM.py Dual-Write Integration                   :p2_3, after p2_2, 2d

    section Phase 3: Taxonomy & Calibration
    Assertion Rigor Audit & Negative Assertion Fixes   :p3_1, 2026-10-31, 3d
    Formal 4-Tier Categorization Implementation        :p3_2, after p3_1, 2d
    Full Model Suite Re-Validation                     :p3_3, after p3_2, 3d

    section Phase 4: Comparative Analytics
    Multi-Dimensional Matrix Engine (matrix_reporter)  :p4_1, 2026-11-08, 3d
    Pareto Frontier & Regression Delta Detection       :p4_2, after p4_1, 3d

    section Phase 5: Question Bank Scaling
    Spatial Logic & Code Invariants Suites             :p5_1, 2026-11-15, 4d
    Advanced Math, Formatting & Refusal Suites         :p5_2, after p5_1, 4d
    100+ Question Calibration Benchmark                :p5_3, after p5_2, 3d

    section Phase 6: Web UI Dashboard
    Lightweight REST API Server (server.py)            :p6_1, 2026-11-26, 3d
    Modern Dashboard UI & Matrix Heatmap               :p6_2, after p6_1, 5d
    Question CRUD Editor & Live Ollama Playground      :p6_3, after p6_2, 5d

    section Phase 7: In-Container Async Job Queue
    Non-Blocking Job Queue Engine & Worker Dispatch    :p7_1, 2026-12-09, 4d
    HTML Benchmark Form & SSE Telemetry Stream         :p7_2, after p7_1, 4d
    Dynamic VRAM keep_alive Swapping Validation        :p7_3, after p7_2, 3d
```

### Summary of Major Deliverables

| Target Milestone | Phase | Deliverable Files | Operational Capability |
| :--- | :--- | :--- | :--- |
| **Milestone 1** | Phase 1 | [testLLM.py](file:///c:/Workspace/Docker%20Workspace/Docker-Llama-LLM/testLLM.py)<br/>[.env](file:///c:/Workspace/Docker%20Workspace/Docker-Llama-LLM/.env)<br/>`Test metrics/gemini-*` | Cloud Gemini models benchmarked via zero-dependency REST API as an empirical frontier baseline. |
| **Milestone 2** | Phase 2 | `benchmark_store.py`<br/>`ingest_metrics.py`<br/>`benchmark.db` | All historical and live runs persisted to a relational SQLite database. |
| **Milestone 3** | Phase 3 | Cleaned [Questions/*.xml](file:///c:/Workspace/Docker%20Workspace/Docker-Llama-LLM/Questions) | 4-tier taxonomy active; zero premise leakage false negatives or collision false passes. |
| **Milestone 4** | Phase 4 | `matrix_reporter.py`<br/>`Test metrics/matrix_*.md` | Instant Model $\times$ Question heatmaps, category radar scores, and Pareto efficiency plots. |
| **Milestone 5** | Phase 5 | 5 New XML Test Suites | Comprehensive 100+ question evaluation covering spatial logic, code invariants, and safety. |
| **Milestone 6** | Phase 6 | `server.py`<br/>`web/index.html`<br/>`web/app.js` | Interactive web dashboard with heatmap inspection, side-by-side diffs, CRUD question editor, and single-prompt sandbox. |
| **Milestone 7** | Phase 7 | In-Container Worker<br/>`benchmark_jobs` Queue<br/>SSE Telemetry Stream | Non-blocking browser benchmark execution (`HTTP 202 Accepted`); in-container async execution without web server stalls. |
