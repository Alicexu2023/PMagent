# stop.ps1 — 停止本项目（只按本项目 PID 停止，不影响其他 Python/浏览器进程）
$ErrorActionPreference = "Continue"

Set-Location $PSScriptRoot

Write-Host "== 停止工厂智能体分析平台 ==" -ForegroundColor Cyan

# 查找监听 127.0.0.1:8000 的进程 PID（用 findstr，兼容各环境）
$lines = netstat -ano 2>$null | findstr ":8000" | findstr "LISTENING"
if (-not $lines) {
    Write-Host "未发现监听 8000 端口的进程，可能未运行。" -ForegroundColor Yellow
    exit 0
}

$seen = @{}
foreach ($line in $lines) {
    $trimmed = $line.Trim()
    $parts = $trimmed -split "\s+"
    $pidStr = $parts[-1]
    if ($pidStr -match "^\d+$" -and -not $seen.ContainsKey($pidStr)) {
        $seen[$pidStr] = $true
        Write-Host "停止进程 PID $pidStr ..."
        taskkill /F /PID $pidStr 2>$null | Out-Null
    }
}

Write-Host "已停止。" -ForegroundColor Green
