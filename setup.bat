@echo off
setlocal
title AgentRouter Proxy - Setup Wizard
cd /d "%~dp0"

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python 3 from https://python.org and tick "Add Python to PATH".
    pause
    exit /b 1
)

python "%~dp0setup.py" %*
if %errorlevel% neq 0 (
    echo.
    echo Setup exited with code %errorlevel%.
)
pause
