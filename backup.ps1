# backup.ps1 — 备份（不含 API Key）
$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

Write-Host "== 备份工厂智能体分析平台 ==" -ForegroundColor Cyan

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupDir = Join-Path $PSScriptRoot "backup-$stamp"

New-Item -ItemType Directory -Path $backupDir | Out-Null

# 备份数据库（含行动清单、结论、同义表达）——不含 .env（密钥）
$dataDir = "D:\FactoryAgentData"
if (Test-Path $dataDir) {
    Copy-Item -Path $dataDir -Destination (Join-Path $backupDir "FactoryAgentData") -Recurse -Force
    Write-Host "已备份数据目录 $dataDir"
} else {
    Write-Host "数据目录 $dataDir 不存在，跳过" -ForegroundColor Yellow
}

# 明确：不备份 .env（API Key 不进入备份）
Write-Host "备份完成：$backupDir（不含 API Key）" -ForegroundColor Green
