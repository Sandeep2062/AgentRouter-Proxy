@echo off
setlocal EnableDelayedExpansion

echo =======================================================
echo   AgentRouter-Proxy - Status Check
echo =======================================================
echo.

:: 1. Check process
powershell -NoProfile -Command "$procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*agentrouter-proxy.py*' }; if ($procs) { Write-Host '[STATUS] Proxy process is RUNNING:' -ForegroundColor Green; foreach ($p in $procs) { Write-Host ('  - PID: ' + $p.ProcessId) } } else { Write-Host '[STATUS] Proxy process is NOT running.' -ForegroundColor Red }"
echo.

:: 2. Check health endpoint locally
echo [*] Checking local health endpoint (http://127.0.0.1:4182/healthz)...
curl.exe -s -m 2 http://127.0.0.1:4182/healthz 2>nul
if %errorlevel% equ 0 (
    echo.
    echo [OK] Local health endpoint responded!
) else (
    echo [INFO] Local port 4182 did not respond (proxy may be stopped or listening on Tailscale IP only).
)
echo.

:: 3. Show recent log lines
if exist "%~dp0proxy.log" (
    echo --- Last 15 lines of proxy.log ---
    powershell -NoProfile -Command "Get-Content '%~dp0proxy.log' -Tail 15"
) else (
    echo [INFO] No proxy.log file found yet.
)
echo.
pause
