@echo off
setlocal EnableDelayedExpansion

echo =======================================================
echo   AgentRouter-Proxy - Auto-Start Uninstaller
echo =======================================================
echo.

set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "STARTUP_VBS=%STARTUP_FOLDER%\AgentRouter-Proxy.vbs"

:: 1. Remove from Startup folder
if exist "%STARTUP_VBS%" (
    del /f /q "%STARTUP_VBS%" >nul 2>&1
    echo [OK] Removed startup launcher from Startup folder.
) else (
    echo [INFO] Startup launcher was not present in Startup folder.
)

:: 2. Remove Scheduled Task
schtasks /query /tn "AgentRouterProxy" >nul 2>&1
if %errorlevel% equ 0 (
    schtasks /delete /tn "AgentRouterProxy" /f >nul 2>&1
    echo [OK] Removed scheduled task 'AgentRouterProxy'.
) else (
    echo [INFO] Scheduled task 'AgentRouterProxy' was not registered.
)

:: 3. Stop running proxy processes
echo [*] Stopping running AgentRouter-Proxy processes...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*agentrouter-proxy.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Host ('[OK] Terminated PID ' + $_.ProcessId) -ForegroundColor Green }"

echo.
echo =======================================================
echo   AgentRouter-Proxy Auto-Start Uninstalled!
echo =======================================================
echo.
pause
