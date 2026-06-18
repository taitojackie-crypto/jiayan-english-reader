@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "PYTHON_DIR=python-portable"
set "PYTHON_EXE=%PYTHON_DIR%\python.exe"

REM 确保便携 Python 环境已就绪。
call setup-portable.bat
if errorlevel 1 (
    echo 环境准备失败。
    pause
    exit /b 1
)

echo Starting Jiayan English Reader (portable)...

REM Check if the server is already running on port 5000.
set "PID="
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5000" ^| findstr "LISTENING"') do (
    set "PID=%%a"
)

if defined PID (
    echo Server already running on port 5000 (PID: %PID%). Restarting...
    taskkill /F /PID %PID% >nul 2>&1
    timeout /t 2 /nobreak >nul
)

REM Start the Flask server in a minimized window.
start /min "Jiayan Server" "%PYTHON_EXE%" app.py

REM Wait until the server is actually accepting connections.
:wait
timeout /t 1 /nobreak >nul
powershell -NoProfile -Command "try { $c = New-Object Net.Sockets.TcpClient('127.0.0.1', 5000); $c.Close(); exit 0 } catch { exit 1 }"
if errorlevel 1 goto wait

REM Open the browser once the server is ready.
start http://127.0.0.1:5000
