@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "PYTHON_DIR=python-portable"
set "PYTHON_EXE=%PYTHON_DIR%\python.exe"

REM Ensure portable Python environment is ready.
call setup-portable.bat
if errorlevel 1 (
    echo Environment setup failed.
    pause
    exit /b 1
)

REM Verify portable Python exists.
if not exist "%PYTHON_EXE%" (
    echo Error: %PYTHON_EXE% not found after setup.
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
    echo Server already running on port 5000 ^(PID: %PID%^). Restarting...
    taskkill /F /PID %PID% >nul 2>&1
    timeout /t 2 /nobreak >nul
)

REM Start the Flask server in a minimized window. Use /k so errors stay visible.
start /min "Jiayan Server" cmd /k "%PYTHON_EXE% app.py"

REM Wait until the server is actually accepting connections (max 30s).
set "TRIES=0"
:wait
timeout /t 1 /nobreak >nul
powershell -NoProfile -Command "try { $c = New-Object Net.Sockets.TcpClient('127.0.0.1', 5000); $c.Close(); exit 0 } catch { exit 1 }"
if errorlevel 1 (
    set /a TRIES+=1
    if !TRIES! GEQ 30 (
        echo Server did not start within 30 seconds.
        echo Please check the minimized "Jiayan Server" window for errors.
        pause
        exit /b 1
    )
    goto wait
)

REM Open the browser once the server is ready.
start http://127.0.0.1:5000
