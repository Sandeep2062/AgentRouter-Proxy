@echo off
setlocal EnableDelayedExpansion
title AgentRouter Proxy (Local PC - 127.0.0.1:4182)

:: 1. Verify Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in system PATH.
    echo Please install Python 3 and ensure "Add Python to PATH" is checked.
    pause
    exit /b 1
)

:: 2. Free port 4182 if previously held by an orphaned process
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":4182" ^| findstr "LISTENING"') do (
    taskkill /f /pid %%a >nul 2>&1
)

:: 3. Load API key and upstream from .env
if exist "%~dp0.env" (
    for /f "usebackq tokens=1,* delims==" %%a in ("%~dp0.env") do (
        if "%%a"=="PROXY_UPSTREAM_API_KEY" if "!PROXY_UPSTREAM_API_KEY!"=="" set "PROXY_UPSTREAM_API_KEY=%%b"
        if "%%a"=="AGENTROUTER_API_KEY" if "!PROXY_UPSTREAM_API_KEY!"=="" set "PROXY_UPSTREAM_API_KEY=%%b"
        if "%%a"=="PROXY_UPSTREAM" if "!PROXY_UPSTREAM!"=="" set "PROXY_UPSTREAM=%%b"
    )
)

if "!PROXY_UPSTREAM!"=="" set "PROXY_UPSTREAM=https://agentrouter.org"

if "!PROXY_UPSTREAM_API_KEY!"=="" (
    echo [INFO] No API key found in .env.
    set /p "PROXY_UPSTREAM_API_KEY=Enter your AgentRouter API key (sk-...): "
    if "!PROXY_UPSTREAM_API_KEY!"=="" (
        echo [ERROR] Upstream API key cannot be empty.
        pause
        exit /b 1
    )
    (
        echo PROXY_UPSTREAM=!PROXY_UPSTREAM!
        echo PROXY_UPSTREAM_API_KEY=!PROXY_UPSTREAM_API_KEY!
        echo PROXY_LISTEN_HOST=127.0.0.1
    ) > "%~dp0.env"
    echo [OK] Saved key to .env
)

:: 4. Force local-only settings
set "PROXY_LISTEN_HOST=127.0.0.1"
set "PROXY_AUTH_TOKEN="
set "PORT=4182"

echo.
echo ===============================================================================
echo                AgentRouter Proxy  --  LOCAL ON-DEMAND MODE
echo ===============================================================================
echo.
echo  [STATUS] Proxy is ACTIVE on your local PC
echo  [UPSTREAM] !PROXY_UPSTREAM!
echo.
echo  -----------------------------------------------------------------------------
echo   COPY-PASTE SETTINGS FOR YOUR AI TOOLS (OpenCode, Cursor, Claude Code, Cline):
echo  -----------------------------------------------------------------------------
echo    Base URL:      http://127.0.0.1:4182/v1
echo    API Key:       sk-local  (or any text - local loopback requires no auth)
echo    Format:        Dual format (OpenAI / Anthropic auto-detected)
echo  -----------------------------------------------------------------------------
echo   HEALTH & MONITORING:
echo  -----------------------------------------------------------------------------
echo    Health Endpoint: http://127.0.0.1:4182/healthz
echo    Models List:     http://127.0.0.1:4182/v1/models
echo    Live Usage JSON: http://127.0.0.1:4182/_usage
echo.
echo    [TIP] To see a live real-time token/speed dashboard:
echo          Double-click 'view-usage.bat' in another window!
echo.
echo  -----------------------------------------------------------------------------
echo   Press Ctrl+C in this window or close it anytime to STOP the proxy.
echo ===============================================================================
echo.
echo [LIVE ACTIVITY & PROGRESS LOG]
echo.

python "%~dp0agentrouter-proxy.py" !PORT!

echo.
echo [INFO] Proxy stopped.
pause
