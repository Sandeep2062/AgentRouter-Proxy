@echo off
setlocal EnableDelayedExpansion

echo =======================================================
echo   AgentRouter-Proxy - Auto-Start Installer
echo =======================================================
echo.

:: 1. Verify Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in system PATH.
    echo Please install Python 3 and ensure "Add Python to PATH" is checked.
    pause
    exit /b 1
)

:: 2. Check for .env file
if not exist "%~dp0.env" (
    echo [WARNING] No .env file found in:
    echo           %~dp0
    echo.
    echo           Make sure to create a .env file with:
    echo           PROXY_UPSTREAM_API_KEY=your-agentrouter-api-key
    echo           PROXY_AUTH_TOKEN=your-client-token
    echo           PROXY_LISTEN_HOST=tailscale
    echo.
    echo           A template is available in .env.example.
    echo.
)

:: 3. Configure Windows Power Plan (Prevent PC from sleeping)
echo [*] Configuring Windows power settings (prevent system sleep on AC)...
powercfg /change standby-timeout-ac 0 >nul 2>&1
powercfg /change hibernate-timeout-ac 0 >nul 2>&1
echo [OK] Sleep timeout on AC power disabled - always-on server mode.

:: 4. Install into Windows Startup folder (Per-user auto-start on logon)
set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "STARTUP_VBS=%STARTUP_FOLDER%\AgentRouter-Proxy.vbs"

echo [*] Installing startup launcher to:
echo     %STARTUP_VBS%

(
    echo Option Explicit
    echo Dim WshShell
    echo Set WshShell = CreateObject^("WScript.Shell"^)
    echo WshShell.Run "wscript.exe """ ^& "%~dp0run-silent.vbs" ^& """", 0, False
) > "%STARTUP_VBS%"

if exist "%STARTUP_VBS%" (
    echo [OK] Startup launcher created successfully.
) else (
    echo [WARN] Could not write to Startup folder.
)

:: 5. Also register Windows Scheduled Task (Fallback for background logon)
echo [*] Registering Windows Scheduled Task 'AgentRouterProxy'...
schtasks /create /tn "AgentRouterProxy" /tr "wscript.exe \"%~dp0run-silent.vbs\"" /sc onlogon /f >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Scheduled Task registered successfully.
) else (
    echo [INFO] Scheduled Task registration skipped - Startup folder is active.
)

:: 6. Launch proxy in background now
echo [*] Starting AgentRouter-Proxy in background...
wscript.exe "%~dp0run-silent.vbs"
timeout /t 2 /nobreak >nul 2>&1

:: 7. Check if running
powershell -Command "$p = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*agentrouter-proxy.py*' }; if ($p) { Write-Host '[OK] Proxy process is RUNNING (PID: ' $p.ProcessId ')' -ForegroundColor Green } else { Write-Host '[WARN] Process not detected yet. Check proxy.log' -ForegroundColor Yellow }"

echo.
echo =======================================================
echo   Installation Complete!
echo =======================================================
echo - Proxy will start automatically on every system boot / login.
echo - Runs silently in the background (no cmd window).
echo - View live logs anytime:
echo     type "%~dp0proxy.log"
echo     powershell Get-Content "%~dp0proxy.log" -Wait -Tail 20
echo - To uninstall auto-start:
echo     "%~dp0uninstall-autostart.bat"
echo =======================================================
echo.
pause
