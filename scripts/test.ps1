# test.ps1 — 依次运行：pytest、样表验收、密钥泄漏扫描、规格指纹检查、本地健康检查
# 退出码 0 = 全部通过；非 0 = 有失败项
$ErrorActionPreference = "Continue"

Set-Location $PSScriptRoot\..

$failures = @()
$PASS = 0
$FAIL = 0

function Report($name, $ok, $detail = "") {
    if ($ok) {
        Write-Host "[通过] $name" -ForegroundColor Green
        $script:PASS++
    } else {
        Write-Host "[失败] $name  $detail" -ForegroundColor Red
        $script:FAIL++
        $script:failures += $name
    }
}

Write-Host "========== 工厂智能体分析平台 · 验收测试 ==========" -ForegroundColor Cyan
Write-Host ""

# ---------------------------------------------------------------------------
# 1. pytest
# ---------------------------------------------------------------------------
Write-Host "--- 1/5 pytest ---"
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Report "pytest" $false "未找到虚拟环境，请先运行 install.ps1"
} else {
    .venv\Scripts\python.exe -m pytest tests/ -q --tb=short
    $pytestCode = $LASTEXITCODE
    if ($pytestCode -eq 0) {
        Report "pytest" $true "零失败零跳过"
    } else {
        Report "pytest" $false "退出码 $pytestCode"
    }
}

# ---------------------------------------------------------------------------
# 2. 样表验收（六实测值）
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "--- 2/5 样表验收 ---"
$sampleScript = Join-Path $PSScriptRoot "verify_samples.py"
if (Test-Path $sampleScript) {
    .venv\Scripts\python.exe $sampleScript
    if ($LASTEXITCODE -eq 0) {
        Report "样表验收" $true
    } else {
        Report "样表验收" $false "样表缺失或数值不符（详见上方输出）"
    }
} else {
    Report "样表验收" $false "缺少 scripts/verify_samples.py"
}

# ---------------------------------------------------------------------------
# 3. 密钥泄漏扫描
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "--- 3/5 密钥泄漏扫描 ---"
$leakScript = Join-Path $PSScriptRoot "scan_secrets.py"
if (Test-Path $leakScript) {
    .venv\Scripts\python.exe $leakScript
    if ($LASTEXITCODE -eq 0) {
        Report "密钥泄漏扫描" $true "零命中"
    } else {
        Report "密钥泄漏扫描" $false "检测到疑似密钥泄漏"
    }
} else {
    Report "密钥泄漏扫描" $false "缺少 scripts/scan_secrets.py"
}

# ---------------------------------------------------------------------------
# 4. 规格指纹检查
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "--- 4/5 规格指纹检查 ---"
$fingerprintScript = Join-Path $PSScriptRoot "check_fingerprint.py"
if (Test-Path $fingerprintScript) {
    .venv\Scripts\python.exe $fingerprintScript
    if ($LASTEXITCODE -eq 0) {
        Report "规格指纹检查" $true
    } else {
        Report "规格指纹检查" $false "指纹不一致（详见上方输出）"
    }
} else {
    Report "规格指纹检查" $false "缺少 scripts/check_fingerprint.py"
}

# ---------------------------------------------------------------------------
# 5. 本地健康检查（127.0.0.1:8000）
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "--- 5/5 本地健康检查 ---"
$healthScript = Join-Path $PSScriptRoot "health_check.py"
if (Test-Path $healthScript) {
    .venv\Scripts\python.exe $healthScript
    if ($LASTEXITCODE -eq 0) {
        Report "本地健康检查" $true "127.0.0.1:8000 可达"
    } else {
        Report "本地健康检查" $false "服务未启动或端口错误（127.0.0.1:8000）"
    }
} else {
    Report "本地健康检查" $false "缺少 scripts/health_check.py"
}

# ---------------------------------------------------------------------------
# 汇总
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "========== 验收结果 ==========" -ForegroundColor Cyan
Write-Host "通过：$PASS  失败：$FAIL"
if ($FAIL -eq 0) {
    Write-Host "全部通过。" -ForegroundColor Green
    exit 0
} else {
    Write-Host "失败项：$($failures -join ', ')" -ForegroundColor Red
    exit 1
}
