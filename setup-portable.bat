@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "PYTHON_DIR=python-portable"
set "PYTHON_EXE=%PYTHON_DIR%\python.exe"
set "PYTHON_VERSION=3.12.4"
set "PYTHON_ZIP=%PYTHON_DIR%\python-embed.zip"

if exist "%PYTHON_EXE%" (
    echo 便携 Python 已存在：%PYTHON_EXE%
    if exist "%PYTHON_DIR%\.deps-installed" (
        echo 依赖已安装，跳过安装步骤。
        goto :end
    )
    goto :install_deps
)

echo 正在准备便携 Python %PYTHON_VERSION% ...

if not exist "%PYTHON_DIR%" mkdir "%PYTHON_DIR%"

echo 正在下载 python-%PYTHON_VERSION%-embed-amd64.zip ...
powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/%PYTHON_VERSION%/python-%PYTHON_VERSION%-embed-amd64.zip' -OutFile '%PYTHON_ZIP%' -UseBasicParsing"
if errorlevel 1 (
    echo 下载失败，请检查网络连接。
    pause
    exit /b 1
)

echo 正在解压 ...
powershell -NoProfile -Command "Expand-Archive -Path '%PYTHON_ZIP%' -DestinationPath '%PYTHON_DIR%' -Force"
if errorlevel 1 (
    echo 解压失败。
    pause
    exit /b 1
)

del "%PYTHON_ZIP%" >nul 2>&1

echo 正在启用 pip/site-packages ...
set "PTH_FILE=%PYTHON_DIR%\python312._pth"
if not exist "%PTH_FILE%" (
    echo 找不到 %PTH_FILE%，解压可能失败。
    pause
    exit /b 1
)

powershell -NoProfile -Command "(Get-Content '%PTH_FILE%') -replace '^#import site', 'import site' | Set-Content '%PTH_FILE%'"
>>"%PTH_FILE%" echo Lib\site-packages

echo 正在下载 get-pip.py ...
powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile '%PYTHON_DIR%\get-pip.py' -UseBasicParsing"
if errorlevel 1 (
    echo get-pip.py 下载失败。
    pause
    exit /b 1
)

echo 正在安装 pip ...
"%PYTHON_EXE%" "%PYTHON_DIR%\get-pip.py"
if errorlevel 1 (
    echo pip 安装失败。
    pause
    exit /b 1
)

:install_deps
REM Ensure pip is installed before installing dependencies.
"%PYTHON_EXE%" -m pip --version >nul 2>&1
if errorlevel 1 (
    echo 正在安装 pip ...
    powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile '%PYTHON_DIR%\get-pip.py' -UseBasicParsing"
    if errorlevel 1 (
        echo get-pip.py 下载失败。
        pause
        exit /b 1
    )
    "%PYTHON_EXE%" "%PYTHON_DIR%\get-pip.py"
    if errorlevel 1 (
        echo pip 安装失败。
        pause
        exit /b 1
    )
)

echo 正在安装/更新依赖（requirements.txt）...
"%PYTHON_EXE%" -m pip install -r requirements.txt --no-cache-dir
if errorlevel 1 (
    echo 依赖安装失败。
    pause
    exit /b 1
)

if exist "%PYTHON_DIR%\get-pip.py" del "%PYTHON_DIR%\get-pip.py" >nul 2>&1

echo. > "%PYTHON_DIR%\.deps-installed"
echo 便携环境准备完成。

:end
