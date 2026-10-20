<#
.SYNOPSIS
    Automated Multi-Model Benchmark Orchestrator for Docker-Llama-LLM.
    Iterates through all curated models in .env, starts each model in an isolated
    Docker container, waits for initialization and warm-up, executes the test suite,
    and shuts down the stack between models.

.DESCRIPTION
    1. Extracts model list from curated commented entries in .env (lines 17-22).
    2. For each model:
       - Overwrites TEST_MODEL in .env.
       - Starts the container stack via `docker compose up -d`.
       - Waits until Ollama starts, configures num_ctx=8192, and completes warm-up.
       - Runs .\run_tests.ps1 against the active model.
       - Shuts down the container via `docker compose down`.
    3. Prints an aggregated summary table of all benchmark runs.

.PARAMETER Models
    Optional list of specific model names to test. Defaults to all models defined in .env.

.PARAMETER Questions
    Optional path or glob pattern for question XML files (e.g. "Questions/*.xml").

.PARAMETER TimeoutSeconds
    Maximum time in seconds to wait for each model to pull/warm up. Default: 600 (10 mins).

.PARAMETER VerboseOutput
    Forward --verbose to testLLM.py to show full model outputs.

.PARAMETER MaxTokens
    Blanket maximum token generation limit across all models. Default: 1200.

.EXAMPLE
    # Run all curated models from .env:
    .\run_all_models.ps1

    # Run only specific models:
    .\run_all_models.ps1 -Models @("llama3.2", "smollm2:latest")

    # Run with verbose output:
    .\run_all_models.ps1 -VerboseOutput
#>

param(
    [string[]]$Models = @(),
    [string]$Questions = "",
    [int]$TimeoutSeconds = 600,
    [switch]$VerboseOutput,
    [int]$MaxTokens = 1200
)

$ErrorActionPreference = "Continue"

# Root workspace path
$scriptRoot = $PSScriptRoot
if (-not $scriptRoot) { $scriptRoot = Get-Location }
$envFile = Join-Path $scriptRoot ".env"

if (-not (Test-Path $envFile)) {
    Write-Host "[ERROR] .env file not found at: $envFile" -ForegroundColor Red
    exit 1
}

# ------------------------------------------------------------------------------
# 1. Discover Models from .env if not explicitly provided
# ------------------------------------------------------------------------------
$envRaw = Get-Content $envFile -Raw
if (-not $Models -or $Models.Count -eq 0) {
    # Match lines like: # TEST_MODEL=llama3.2   # Comment
    $matched = [regex]::Matches($envRaw, '(?m)^\s*#\s*TEST_MODEL=([^\s#]+)')
    $Models = @($matched | ForEach-Object { $_.Groups[1].Value.Trim() } | Where-Object { $_ })
}

if (-not $Models -or $Models.Count -eq 0) {
    Write-Host "[ERROR] No models found in .env (checked lines 17-22). Please pass -Models explicitly." -ForegroundColor Red
    exit 1
}

Write-Host "`n================================================================================" -ForegroundColor Cyan
Write-Host " Docker-Llama-LLM Multi-Model Benchmark Suite" -ForegroundColor Cyan
Write-Host " Total Models to Test: $($Models.Count)" -ForegroundColor Cyan
Write-Host " Queue: $($Models -join ', ')" -ForegroundColor Yellow
Write-Host "================================================================================`n" -ForegroundColor Cyan

# Helper to overwrite TEST_MODEL in .env
function Set-EnvModel {
    param([string]$ModelName)
    $current = Get-Content $envFile -Raw
    if ($current -match '(?m)^TEST_MODEL=.*$') {
        $updated = [regex]::Replace($current, '(?m)^TEST_MODEL=.*$', "TEST_MODEL=$ModelName")
    } else {
        $updated = "TEST_MODEL=$ModelName`r`n" + $current
    }
    [System.IO.File]::WriteAllText($envFile, $updated, [System.Text.Encoding]::UTF8)
    $env:TEST_MODEL = $ModelName
}

# Helper to wait for the container and model to be fully ready
function Wait-For-Stack-Ready {
    param(
        [string]$TargetModel,
        [int]$MaxWaitSec = 600
    )
    Write-Host "[WAIT] Waiting for Ollama container and model '$TargetModel' to start and warm up..." -ForegroundColor Yellow
    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()

    while ($stopwatch.Elapsed.TotalSeconds -lt $MaxWaitSec) {
        # Check container health
        $containerStatus = (docker inspect -f '{{.State.Status}}' ollama 2>$null)
        if ($containerStatus -and $containerStatus -ne "running") {
            throw "Container 'ollama' is in status '$containerStatus' (expected 'running'). Check 'docker logs ollama'."
        }

        # Check if model initialization and multi-token warmup completed in entrypoint.sh logs
        $logs = (docker logs --tail 30 ollama 2>&1)
        if ($logs | Select-String -SimpleMatch "Model initialization complete!") {
            $elapsedSec = [math]::Round($stopwatch.Elapsed.TotalSeconds, 1)
            Write-Host "[READY] Model '$TargetModel' fully initialized and warmed up in ${elapsedSec}s." -ForegroundColor Green
            return $true
        }

        Start-Sleep -Seconds 3
        $elapsedInt = [math]::Round($stopwatch.Elapsed.TotalSeconds, 0)
        Write-Host "       ... waiting for '$TargetModel' (${elapsedInt}s elapsed)" -ForegroundColor DarkGray
    }

    throw "Timed out after $MaxWaitSec seconds waiting for '$TargetModel' to initialize."
}

# ------------------------------------------------------------------------------
# 2. Iterate Over Models
# ------------------------------------------------------------------------------
$benchmarkResults = @()
$totalStartTime = [System.Diagnostics.Stopwatch]::StartNew()

for ($i = 0; $i -lt $Models.Count; $i++) {
    $model = $Models[$i]
    $stepNum = $i + 1
    Write-Host "`n================================================================================" -ForegroundColor Magenta
    Write-Host " [$stepNum/$($Models.Count)] Processing Model: $model" -ForegroundColor Magenta
    Write-Host "================================================================================" -ForegroundColor Magenta

    $modelSw = [System.Diagnostics.Stopwatch]::StartNew()
    $statusText = "Unknown"
    $exitCode = 0

    try {
        # 1. Overwrite TEST_MODEL in .env
        Write-Host "[CONFIG] Setting TEST_MODEL=$model in .env..." -ForegroundColor Cyan
        Set-EnvModel -ModelName $model

        # 2. Start the Docker stack
        Write-Host "[DOCKER] Starting stack via 'docker compose up -d'..." -ForegroundColor Cyan
        docker compose up -d
        if ($LASTEXITCODE -ne 0) {
            throw "docker compose up -d failed with exit code $LASTEXITCODE"
        }

        # 3. Wait until the stack has started and warmed up
        $null = Wait-For-Stack-Ready -TargetModel $model -MaxWaitSec $TimeoutSeconds

        # 4. Execute test suite via .\run_tests.ps1
        Write-Host "[TEST] Executing test suite against model: $model..." -ForegroundColor Cyan
        $testArgs = @{
            Model = $model
        }
        if ($Questions) { $testArgs["Questions"] = $Questions }
        if ($VerboseOutput) { $testArgs["Verbose"] = $true }
        if ($MaxTokens -gt 0) { $testArgs["MaxTokens"] = $MaxTokens }

        & (Join-Path $scriptRoot "run_tests.ps1") @testArgs
        $exitCode = $LASTEXITCODE

        if ($exitCode -eq 0) {
            $statusText = "Passed (100% assertions)"
        } else {
            $statusText = "Completed with assertion failures"
        }
    }
    catch {
        Write-Host "[ERROR] Model '$model' encountered a fatal error: $_" -ForegroundColor Red
        $statusText = "Error: $_"
        $exitCode = -1
    }
    finally {
        # 5. Shutdown the stack to prepare for the next model
        Write-Host "[DOCKER] Shutting down container stack for '$model' via 'docker compose down'..." -ForegroundColor Cyan
        docker compose down
        Start-Sleep -Seconds 2
    }

    $modelElapsedSec = [math]::Round($modelSw.Elapsed.TotalSeconds, 1)

    # Extract metrics from the newly written JSON report
    $safeModel = [regex]::Replace($model, '[\\/:*?"<>|]', '_')
    $modelDir = Join-Path (Join-Path $scriptRoot "Test metrics") $safeModel
    $latestJson = Get-ChildItem -Path $modelDir -Filter "*_out.json" -ErrorAction SilentlyContinue |
                  Sort-Object LastWriteTime -Descending | Select-Object -First 1

    $inferenceLatency = "-"
    $questionsSolved = "-"
    $passRate = "-"
    $assertStr = "-"
    $avgSpeed = "-"

    if ($latestJson) {
        try {
            $metricData = Get-Content $latestJson.FullName -Raw | ConvertFrom-Json
            $inferenceLatency = "$($metricData.total_latency_sec)s"
            $qSolved = if ($metricData.questions_solved -ne $null) { $metricData.questions_solved } elseif ($metricData.passed_cases -ne $null) { $metricData.passed_cases } else { "-" }
            $qTotal = if ($metricData.total_questions -ne $null) { $metricData.total_questions } elseif ($metricData.total_cases -ne $null) { $metricData.total_cases } else { "-" }
            $qRate = if ($metricData.question_pass_rate_pct -ne $null) { "$($metricData.question_pass_rate_pct)%" } else { "-" }
            $questionsSolved = "$qSolved/$qTotal ($qRate)"
            $passRate = "$($metricData.pass_rate_pct)%"
            $assertStr = "$($metricData.passed_assertions)/$($metricData.total_assertions)"
            $avgSpeed = "$($metricData.avg_tokens_per_sec) tok/s"
        } catch {}
    }

    $benchmarkResults += [PSCustomObject]@{
        Model            = $model
        QuestionsSolved  = $questionsSolved
        Assertions       = $assertStr
        AvgSpeed         = $avgSpeed
        InferenceLatency = $inferenceLatency
        TotalCycleTime   = "${modelElapsedSec}s"
        Status           = $statusText
    }
}

# ------------------------------------------------------------------------------
# 3. Final Aggregated Summary
# ------------------------------------------------------------------------------
$totalDurationSec = [math]::Round($totalStartTime.Elapsed.TotalSeconds, 1)

Write-Host "`n================================================================================" -ForegroundColor Green
Write-Host " MULTI-MODEL BENCHMARK COMPLETE" -ForegroundColor Green
Write-Host " Total Time Elapsed: ${totalDurationSec}s" -ForegroundColor Green
Write-Host "================================================================================" -ForegroundColor Green

$benchmarkResults | Format-Table -Property Model, QuestionsSolved, Assertions, AvgSpeed, InferenceLatency, TotalCycleTime, Status -AutoSize

# Append benchmark results to Test metrics\Summary.md without overwriting existing calculations
$summaryMdPath = Join-Path (Join-Path $scriptRoot "Test metrics") "Summary.md"
if (-not (Test-Path $summaryMdPath)) {
    $headerLines = @(
        "## Summary Comparison",
        "| Model | Questions Solved | Assertions Passed | Avg Generation Speed | Total Latency (Inference) | Total Cycle Time (Docker) |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |"
    )
    [System.IO.File]::WriteAllText($summaryMdPath, ($headerLines -join "`r`n") + "`r`n", [System.Text.Encoding]::UTF8)
} else {
    $existingRaw = [System.IO.File]::ReadAllText($summaryMdPath)
    if ($existingRaw.Length -gt 0 -and -not $existingRaw.EndsWith("`n")) {
        [System.IO.File]::AppendAllText($summaryMdPath, "`r`n", [System.Text.Encoding]::UTF8)
    }
}
foreach ($r in $benchmarkResults) {
    $row = "| **$($r.Model)** | $($r.QuestionsSolved) | $($r.Assertions) | $($r.AvgSpeed) | $($r.InferenceLatency) | $($r.TotalCycleTime) |"
    [System.IO.File]::AppendAllText($summaryMdPath, "$row`r`n", [System.Text.Encoding]::UTF8)
}
Write-Host "`nResults appended to: $summaryMdPath" -ForegroundColor Cyan
Write-Host "Individual reports saved to: '.\Test metrics\<model>\<datetime>_out.json' and '.md'`n" -ForegroundColor Cyan
