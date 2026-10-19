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
    [switch]$Verbose
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
if ($Model) { $extraArgs += @("--model", $Model) }
if ($Questions) { $extraArgs += @("--questions", $Questions) }
if ($Endpoint) { $extraArgs += @("--endpoint", $Endpoint) }
if ($HostUrl) { $extraArgs += @("--host", $HostUrl) }
if ($MetricsDir) { $extraArgs += @("--metrics-dir", $MetricsDir) }

Write-Host "[INFO] Running testLLM.py using $pythonExe..." -ForegroundColor Cyan
& $pythonExe testLLM.py @extraArgs
