@echo off
REM start.bat — 启动工厂智能体分析平台（只绑定 127.0.0.1:8000）
setlocal

cd /d "%~dp0"

REM 检查虚拟环境
if not exist ".venv\Scripts\python.exe" (
    echo [错误] 未找到虚拟环境，请先运行 install.ps1
    pause
    exit /b 1
)

REM 确保数据目录存在
if not exist "D:\FactoryAgentData" mkdir "D:\FactoryAgentData"

echo 正在启动工厂智能体分析平台...
echo 地址：http://127.0.0.1:8000
echo 按 Ctrl+C 停止

REM 启动 Streamlit，只绑定本机 127.0.0.1:8000
start "" http://127.0.0.1:8000
.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1 --server.port 8000 --server.headless false

endlocal
