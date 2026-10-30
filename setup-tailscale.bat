@echo off
setlocal EnableDelayedExpansion
title AgentRouter-Proxy - Tailscale Remote Setup

echo.
echo ========================================================
echo   AgentRouter-Proxy  --  TAILSCALE / REMOTE SETUP
echo   Proxy runs on THIS PC and is accessible from your
echo   laptop or desktop over Tailscale VPN.
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
:: 2. Detect Tailscale IP
:: -------------------------------------------------------
echo.
echo [*] Detecting Tailscale IP...
set "TS_IP="
where tailscale >nul 2>&1
if %errorlevel% equ 0 (
    for /f "delims=" %%i in ('tailscale ip -4 2^>nul') do (
        if "!TS_IP!"=="" set "TS_IP=%%i"
    )
)
if defined TS_IP (
    echo [OK] Tailscale IP detected: !TS_IP!
) else (
    echo [WARN] Tailscale not detected or not connected.
    echo.
    set /p "TS_IP=  Enter your Tailscale IP manually (e.g. 100.x.y.z): "
    if "!TS_IP!"=="" (
        echo [ERROR] Tailscale IP is required for remote access.
        pause & exit /b 1
    )
)

:: -------------------------------------------------------
:: 3. Create or update .env
:: -------------------------------------------------------
if not exist "%~dp0.env" (
    echo.
    echo [SETUP] No .env found. Creating one...
    set /p "APIKEY=  Enter your AgentRouter API key (sk-...): "
    if "!APIKEY!"=="" ( echo [ERROR] API key cannot be empty. & pause & exit /b 1 )
    set /p "AUTHTOKEN=  Enter a client auth token (make one up, e.g. mytoken123): "
    if "!AUTHTOKEN!"=="" ( echo [ERROR] Auth token cannot be empty. & pause & exit /b 1 )
    (
        echo PROXY_UPSTREAM=https://agentrouter.org
        echo PROXY_UPSTREAM_API_KEY=!APIKEY!
        echo PROXY_LISTEN_HOST=!TS_IP!
        echo PROXY_AUTH_TOKEN=!AUTHTOKEN!
    ) > "%~dp0.env"
    echo [OK] .env created with Tailscale settings.
) else (
    echo [OK] .env already exists.
    echo [INFO] If PROXY_LISTEN_HOST is wrong, edit .env and set it to !TS_IP!
)

:: -------------------------------------------------------
:: 4. Disable Windows sleep (always-on server mode)
:: -------------------------------------------------------
echo.
echo [*] Disabling Windows sleep on AC power (server mode)...
powercfg /change standby-timeout-ac 0 >nul 2>&1
powercfg /change hibernate-timeout-ac 0 >nul 2>&1
echo [OK] PC will not sleep on AC power.

:: -------------------------------------------------------
:: 5. Run tests
:: -------------------------------------------------------
echo.
echo [*] Running self-tests...
python -m unittest discover -v >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] All tests passed.
) else (
    echo [WARN] Some tests failed - check proxy.log after start.
)

:: -------------------------------------------------------
:: 6. Install auto-start
:: -------------------------------------------------------
echo.
set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "STARTUP_VBS=%STARTUP_FOLDER%\AgentRouter-Proxy.vbs"

echo [*] Installing auto-start launcher for Tailscale proxy...
(
    echo Set WshShell = CreateObject^("WScript.Shell"^)
    echo Set fso = CreateObject^("Scripting.FileSystemObject"^)
    echo scriptDir = fso.GetParentFolderName^(WScript.ScriptFullName^)
    echo WshShell.CurrentDirectory = scriptDir
    echo WshShell.Run "cmd /c """"" ^& scriptDir ^& "\start-tailscale.bat"""""", 0, False
) > "%STARTUP_VBS%"

if exist "%STARTUP_VBS%" (
    echo [OK] Startup launcher installed - proxy auto-starts on every login.
) else (
    echo [WARN] Could not write to Startup folder.
)

schtasks /create /tn "AgentRouterProxy" /tr "wscript.exe \"%STARTUP_VBS%\"" /sc onlogon /f >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Scheduled Task 'AgentRouterProxy' registered.
) else (
    echo [INFO] Startup folder covers auto-start.
)

:: -------------------------------------------------------
:: 7. Launch proxy now
:: -------------------------------------------------------
echo.
echo [*] Starting Tailscale proxy in background (no window)...
wscript.exe "%STARTUP_VBS%"
timeout /t 3 /nobreak >nul

:: -------------------------------------------------------
:: 8. Health check (from this machine)
:: -------------------------------------------------------
if defined TS_IP (
    echo [*] Testing proxy at http://!TS_IP!:4182/healthz ...
    curl.exe -s -m 4 "http://!TS_IP!:4182/healthz" >nul 2>&1
    if %errorlevel% equ 0 (
        echo [OK] Proxy is LIVE at http://!TS_IP!:4182
    ) else (
        echo [INFO] Proxy starting... check proxy.log if it doesn't respond.
    )
)

:: -------------------------------------------------------
:: 9. Read token from .env for display
:: -------------------------------------------------------
set "DISPLAY_TOKEN="
for /f "usebackq tokens=1,* delims==" %%a in ("%~dp0.env") do (
    if "%%a"=="PROXY_AUTH_TOKEN" if "!DISPLAY_TOKEN!"=="" set "DISPLAY_TOKEN=%%b"
)

echo.
echo ========================================================
echo   Tailscale Proxy Setup Complete!
echo ========================================================
echo.
echo   From your LAPTOP or DESKTOP, use in OpenCode:
if defined TS_IP (
    echo     Provider base URL:  http://!TS_IP!:4182/v1
)
if defined DISPLAY_TOKEN (
    echo     API Key / Token:    !DISPLAY_TOKEN!
)
echo.
echo   Add this to ~/.config/opencode/opencode.json:
echo     "agentrouter-proxy-remote": {
echo       "npm": "@ai-sdk/openai-compatible",
echo       "name": "AgentRouter Proxy (Tailscale)",
echo       "options": {
if defined TS_IP (
    echo         "baseURL": "http://!TS_IP!:4182/v1",
)
if defined DISPLAY_TOKEN (
    echo         "apiKey": "!DISPLAY_TOKEN!"
)
echo       }
echo     }
echo.
echo   Logs:        powershell Get-Content "%~dp0proxy.log" -Wait -Tail 20
if defined TS_IP (
    echo   Stats:       curl -H "Authorization: Bearer !DISPLAY_TOKEN!" http://!TS_IP!:4182/_stats
    echo   Token usage: curl -H "Authorization: Bearer !DISPLAY_TOKEN!" http://!TS_IP!:4182/_usage
)
echo   Status:      "%~dp0status-proxy.bat"
echo   Uninstall:   "%~dp0uninstall-autostart.bat"
echo ========================================================
echo.
pause
