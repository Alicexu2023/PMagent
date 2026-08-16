# install.ps1 — 安装依赖（首次运行）
$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

Write-Host "== 工厂智能体分析平台 · 依赖安装 ==" -ForegroundColor Cyan

# 检查 Python
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    Write-Host "[错误] 未找到 Python，请先安装 Python 3.12+" -ForegroundColor Red
    exit 1
}

# 创建虚拟环境
if (-not (Test-Path ".venv")) {
    Write-Host "创建虚拟环境..."
    python -m venv .venv
}

# 安装依赖
Write-Host "安装依赖..."
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt

# 复制 .env.example 为 .env（若不存在）
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "已创建 .env（请填入 DEEPSEEK_API_KEY）" -ForegroundColor Yellow
}

Write-Host "安装完成。双击 start.bat 启动平台。" -ForegroundColor Green
