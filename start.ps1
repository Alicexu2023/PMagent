# start.ps1 -- ASCII-only so Windows PowerShell 5.1 never mojibakes this file.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
try {
    chcp 65001 | Out-Null
    [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
} catch {}

$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "[ERROR] .venv not found."
    Write-Host "Run: powershell -ExecutionPolicy Bypass -File install.ps1"
    exit 1
}

$dataDir = "D:\FactoryAgentData"
if (-not (Test-Path $dataDir)) {
    New-Item -ItemType Directory -Path $dataDir | Out-Null
}

function Test-Ready {
    foreach ($url in @("http://127.0.0.1:8000/_stcore/health", "http://127.0.0.1:8000")) {
        try {
            $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2
            if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500) { return $true }
        } catch {}
    }
    return $false
}

if (Test-Ready) {
    Write-Host "Already running: http://127.0.0.1:8000"
    Start-Process "http://127.0.0.1:8000"
    exit 0
}

Write-Host "Starting Factory Agent Analytics..."
Write-Host "URL: http://127.0.0.1:8000"
Write-Host "Keep this window open. Ctrl+C to stop."

$stArgs = @(
    "-m", "streamlit", "run", "app.py",
    "--server.address", "127.0.0.1",
    "--server.port", "8000",
    "--server.headless", "true",
    "--browser.gatherUsageStats", "false"
)

$proc = Start-Process -FilePath $py -ArgumentList $stArgs -WorkingDirectory $PSScriptRoot -PassThru -NoNewWindow
$ready = $false
for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Seconds 1
    if ($proc.HasExited) {
        Write-Host "[ERROR] Streamlit exited early. ExitCode=$($proc.ExitCode)"
        exit 1
    }
    if (Test-Ready) { $ready = $true; break }
}

if (-not $ready) {
    Write-Host "[ERROR] Server did not become ready in 60 seconds."
    if (-not $proc.HasExited) { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue }
    exit 1
}

Write-Host "Ready. Opening browser..."
Start-Process "http://127.0.0.1:8000"

try {
    Wait-Process -Id $proc.Id
} finally {
    if (-not $proc.HasExited) {
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    }
}
