@echo off
setlocal EnableDelayedExpansion
title AgentRouter-Proxy - Local Setup

echo.
echo ========================================================
echo   AgentRouter-Proxy  --  LOCAL SETUP
echo   Proxy runs on THIS PC at http://127.0.0.1:4182
echo ========================================================
echo.

:: -------------------------------------------------------
:: 1. Python check
:: -------------------------------------------------------
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found in PATH.
    echo         Download from https://python.org and tick "Add to PATH".
    pause & exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo [OK] %%v found

:: -------------------------------------------------------
:: 2. Create .env if missing
:: -------------------------------------------------------
if not exist "%~dp0.env" (
    echo.
    echo [SETUP] No .env file found. Let's create one now.
    echo.
    set /p "APIKEY=  Enter your AgentRouter API key (sk-...): "
    if "!APIKEY!"=="" (
        echo [ERROR] API key cannot be empty.
        pause & exit /b 1
    )
    (
        echo PROXY_UPSTREAM=https://agentrouter.org
        echo PROXY_UPSTREAM_API_KEY=!APIKEY!
        echo PROXY_LISTEN_HOST=127.0.0.1
        echo PROXY_AUTH_TOKEN=
    ) > "%~dp0.env"
    echo [OK] .env created for local use.
) else (
    echo [OK] .env already exists.
)

:: -------------------------------------------------------
:: 3. Run tests
:: -------------------------------------------------------
echo.
echo [*] Running self-tests...
python -m unittest discover -v >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] All tests passed.
) else (
    echo [WARN] Some tests failed - proxy may still work.
)

:: -------------------------------------------------------
:: 4. Install auto-start in Windows Startup folder
:: -------------------------------------------------------
echo.
set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "STARTUP_VBS=%STARTUP_FOLDER%\AgentRouter-Proxy-Local.vbs"

echo [*] Installing auto-start launcher for LOCAL proxy...
(
    echo Option Explicit
    echo Dim WshShell
    echo Set WshShell = CreateObject^("WScript.Shell"^)
    echo WshShell.Run "wscript.exe """ ^& "%~dp0run-silent.vbs" ^& """", 0, False
) > "%STARTUP_VBS%"

if exist "%STARTUP_VBS%" (
    echo [OK] Startup launcher installed. Proxy will auto-start on next login.
) else (
    echo [WARN] Could not write to Startup folder.
)

:: -------------------------------------------------------
:: 5. Register Scheduled Task
:: -------------------------------------------------------
schtasks /create /tn "AgentRouterProxy-Local" /tr "wscript.exe \"%~dp0run-silent.vbs\"" /sc onlogon /f >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Scheduled Task 'AgentRouterProxy-Local' registered.
) else (
    echo [INFO] Startup folder covers auto-start.
)

:: -------------------------------------------------------
:: 6. Launch proxy now
:: -------------------------------------------------------
echo.
echo [*] Starting local proxy in background (no window)...
wscript.exe "%~dp0run-silent.vbs"
timeout /t 2 /nobreak >nul

:: -------------------------------------------------------
:: 7. Health check
:: -------------------------------------------------------
echo [*] Waiting for proxy to start...
timeout /t 3 /nobreak >nul
curl.exe -s -m 3 http://127.0.0.1:4182/healthz >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Proxy is LIVE at http://127.0.0.1:4182
) else (
    echo [INFO] Proxy starting... check proxy.log if it doesn't respond.
)

echo.
echo ========================================================
echo   Local Proxy Setup Complete!
echo ========================================================
echo.
echo   Use in OpenCode as provider base URL:
echo     http://127.0.0.1:4182/v1
echo.
echo   No API key needed between OpenCode and proxy
echo   (local loopback is always trusted).
echo.
echo   View logs:   powershell Get-Content "%~dp0proxy.log" -Wait -Tail 20
echo   Stats:       curl http://127.0.0.1:4182/_stats
echo   Token usage: curl http://127.0.0.1:4182/_usage
echo   Stop proxy:  "%~dp0uninstall-autostart.bat"
echo ========================================================
echo.
pause
