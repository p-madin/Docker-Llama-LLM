<#
.SYNOPSIS
    Convenient PowerShell runner for testLLM.py.
    Reads defaults from .env (TEST_MODEL, OLLAMA_HOST, etc.) or accepts CLI overrides.
.EXAMPLE
    .\run_tests.ps1
    .\run_tests.ps1 -Model "qwen2.5-coder:3b"
    .\run_tests.ps1 -Model "llama3.2,smollm2:latest"
#>
param(
    [string]$Model = "",
    [string]$Questions = "",
    [string]$Endpoint = "",
    [string]$HostUrl = "",
    [string]$MetricsDir = "",
    [switch]$Verbose,
    [switch]$NoWarmup,
    [int]$MaxTokens = 1200,
    [switch]$AppendToSummary
)

$pythonExe = "python"
try {
    $check = & python --version 2>&1
    if ($LASTEXITCODE -ne 0 -or $check -notmatch "Python 3") {
        if (Test-Path "C:\Program Files\Python315\python.exe") {
            $pythonExe = "C:\Program Files\Python315\python.exe"
        }
    }
} catch {
    if (Test-Path "C:\Program Files\Python315\python.exe") {
        $pythonExe = "C:\Program Files\Python315\python.exe"
    }
}

$extraArgs = @()
if ($Verbose) { $extraArgs += "--verbose" }
if ($NoWarmup) { $extraArgs += "--no-warmup" }
if ($MaxTokens -gt 0) { $extraArgs += @("--max-tokens", $MaxTokens) }
if ($Model) { $extraArgs += @("--model", $Model) }
if ($Questions) { $extraArgs += @("--questions", $Questions) }
if ($Endpoint) { $extraArgs += @("--endpoint", $Endpoint) }
if ($HostUrl) { $extraArgs += @("--host", $HostUrl) }
if ($MetricsDir) { $extraArgs += @("--metrics-dir", $MetricsDir) }

Write-Host "[INFO] Running testLLM.py using $pythonExe..." -ForegroundColor Cyan
& $pythonExe testLLM.py @extraArgs
$testExitCode = $LASTEXITCODE

# ------------------------------------------------------------------------------
# Output Summary Row as found in .\Test metrics\Summary.md
# ------------------------------------------------------------------------------
$scriptDir = $PSScriptRoot
if (-not $scriptDir) { $scriptDir = Get-Location }

# Determine the target model(s) tested
$targetModel = $Model
if (-not $targetModel) {
    $envFile = Join-Path $scriptDir ".env"
    if (Test-Path $envFile) {
        $envLines = Get-Content $envFile
        foreach ($line in $envLines) {
            if ($line -match '^\s*TEST_MODEL=([^\s#]+)') {
                $targetModel = $matches[1].Trim()
                break
            }
        }
    }
}
if (-not $targetModel) { $targetModel = "llama3.2" }

$metricsRootDir = if ($MetricsDir) { $MetricsDir } else { "Test metrics" }
$metricsPath = if ([System.IO.Path]::IsPathRooted($metricsRootDir)) { $metricsRootDir } else { Join-Path $scriptDir $metricsRootDir }

$modelsTested = @($targetModel.Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $_ })

Write-Host "`n================================================================================" -ForegroundColor Cyan
Write-Host " SUMMARY ROW (as in Summary.md):" -ForegroundColor Cyan
Write-Host "================================================================================" -ForegroundColor Cyan

foreach ($m in $modelsTested) {
    $safeM = [regex]::Replace($m, '[\\/:*?"<>|]', '_')
    $modelFolder = Join-Path $metricsPath $safeM
    $latestJson = Get-ChildItem -Path $modelFolder -Filter "*_out.json" -ErrorAction SilentlyContinue |
                  Sort-Object LastWriteTime -Descending | Select-Object -First 1

    if ($latestJson) {
        try {
            $jsonContent = Get-Content $latestJson.FullName -Raw | ConvertFrom-Json

            # Extract questions solved & assertions
            $qSolved = if ($jsonContent.questions_solved -ne $null) { $jsonContent.questions_solved } elseif ($jsonContent.passed_cases -ne $null) { $jsonContent.passed_cases } else { "-" }
            $qTotal = if ($jsonContent.total_questions -ne $null) { $jsonContent.total_questions } elseif ($jsonContent.total_cases -ne $null) { $jsonContent.total_cases } else { "-" }
            $qRate = if ($jsonContent.question_pass_rate_pct -ne $null) { "$($jsonContent.question_pass_rate_pct)%" } else { "-" }

            # Summary row matching Summary.md format:
            $summaryRow = "| **$($jsonContent.model)** | $qSolved/$qTotal ($qRate) | $($jsonContent.passed_assertions)/$($jsonContent.total_assertions) | $($jsonContent.avg_tokens_per_sec) tok/s | $($jsonContent.total_latency_sec)s | - |"
            Write-Host $summaryRow -ForegroundColor Yellow

            # Only append to Summary.md if explicitly requested via -AppendToSummary
            if ($AppendToSummary) {
                $summaryFile = Join-Path $metricsPath "Summary.md"
                if (-not (Test-Path $summaryFile)) {
                    $headerLines = @(
                        "## Summary Comparison",
                        "| Model | Questions Solved | Assertions Passed | Avg Generation Speed | Total Latency (Inference) | Total Cycle Time (Docker) |",
                        "| :--- | :--- | :--- | :--- | :--- | :--- |"
                    )
                    [System.IO.File]::WriteAllText($summaryFile, ($headerLines -join "`r`n") + "`r`n", [System.Text.Encoding]::UTF8)
                } else {
                    $raw = [System.IO.File]::ReadAllText($summaryFile)
                    if ($raw.Length -gt 0 -and -not $raw.EndsWith("`n")) {
                        [System.IO.File]::AppendAllText($summaryFile, "`r`n", [System.Text.Encoding]::UTF8)
                    }
                }
                [System.IO.File]::AppendAllText($summaryFile, "$summaryRow`r`n", [System.Text.Encoding]::UTF8)
                Write-Host "(Appended row to $summaryFile)" -ForegroundColor DarkGray
            }
        } catch {
            Write-Host "| **$m** | (could not parse metrics JSON: $_) |" -ForegroundColor Red
        }
    } else {
        Write-Host "| **$m** | (no metrics file found in $modelFolder) |" -ForegroundColor Red
    }
}
Write-Host "================================================================================`n" -ForegroundColor Cyan

exit $testExitCode
