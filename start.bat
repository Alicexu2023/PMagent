@echo off
REM ASCII-only launcher. Do not put Chinese here: cmd.exe uses GBK and will garbled UTF-8.
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
chcp 65001 >nul

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] .venv not found.
    echo Run: powershell -ExecutionPolicy Bypass -File install.ps1
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"
set ERR=%ERRORLEVEL%
if not "%ERR%"=="0" (
    echo.
    echo Start failed. See messages above.
    pause
)
exit /b %ERR%
