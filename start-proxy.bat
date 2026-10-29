@echo off
setlocal EnableDelayedExpansion

:: -------------------------------------------------------
:: 1. Check Python installation
:: -------------------------------------------------------
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python 3 and add it to your system PATH.
    echo.
    pause
    exit /b 1
)

:: -------------------------------------------------------
:: 2. Parse arguments
:: -------------------------------------------------------
set "PORT=4182"
set "FORMAT=auto"
set "SCRIPT=agentrouter-proxy.py"
set "USE_TAILSCALE="

:parse_args
if "%~1"=="" goto :args_done
if /i "%~1"=="--port" (
    set "PORT=%~2"
    shift
    shift
    goto :parse_args
)
if /i "%~1"=="--format" (
    set "FORMAT=%~2"
    shift
    shift
    goto :parse_args
)
if /i "%~1"=="--openai" (
    set "SCRIPT=agentrouter-proxy-openai.py"
    set "FORMAT=openai"
    shift
    goto :parse_args
)
if /i "%~1"=="--anthropic" (
    set "SCRIPT=agentrouter-proxy-anthropic.py"
    set "FORMAT=anthropic"
    shift
    goto :parse_args
)
if /i "%~1"=="--tailscale" (
    set "USE_TAILSCALE=1"
    shift
    goto :parse_args
)
if /i "%~1"=="--help" (
    goto :show_help
)
:: Assume first non-flag arg is port
set "PORT=%~1"
shift
goto :parse_args

:args_done

:: -------------------------------------------------------
:: 3. Load configuration from .env (if not already set)
:: -------------------------------------------------------
if "%PROXY_UPSTREAM_API_KEY%"=="" if not "%AGENTROUTER_API_KEY%"=="" set "PROXY_UPSTREAM_API_KEY=%AGENTROUTER_API_KEY%"
if "%PROXY_UPSTREAM%"=="" if not "%AGENTROUTER_UPSTREAM%"=="" set "PROXY_UPSTREAM=%AGENTROUTER_UPSTREAM%"

if exist "%~dp0.env" (
    for /f "usebackq tokens=1,* delims==" %%a in ("%~dp0.env") do (
        if "%%a"=="PROXY_UPSTREAM_API_KEY" if "!PROXY_UPSTREAM_API_KEY!"=="" set "PROXY_UPSTREAM_API_KEY=%%b"
        if "%%a"=="AGENTROUTER_API_KEY" if "!PROXY_UPSTREAM_API_KEY!"=="" set "PROXY_UPSTREAM_API_KEY=%%b"
        if "%%a"=="PROXY_UPSTREAM" if "!PROXY_UPSTREAM!"=="" set "PROXY_UPSTREAM=%%b"
        if "%%a"=="PROXY_LISTEN_HOST" if "!PROXY_LISTEN_HOST!"=="" set "PROXY_LISTEN_HOST=%%b"
        if "%%a"=="PROXY_AUTH_TOKEN" if "!PROXY_AUTH_TOKEN!"=="" set "PROXY_AUTH_TOKEN=%%b"
        if "%%a"=="PROXY_UPSTREAM_AUTH_SCHEME" if "!PROXY_UPSTREAM_AUTH_SCHEME!"=="" set "PROXY_UPSTREAM_AUTH_SCHEME=%%b"
        if "%%a"=="PROXY_UPSTREAM_TIMEOUT" if "!PROXY_UPSTREAM_TIMEOUT!"=="" set "PROXY_UPSTREAM_TIMEOUT=%%b"
        if "%%a"=="PROXY_MAX_BODY_BYTES" if "!PROXY_MAX_BODY_BYTES!"=="" set "PROXY_MAX_BODY_BYTES=%%b"
        if "%%a"=="PROXY_INJECT_PREAMBLE" if "!PROXY_INJECT_PREAMBLE!"=="" set "PROXY_INJECT_PREAMBLE=%%b"
        if "%%a"=="AGENTROUTER_FORMAT" if "!AGENTROUTER_FORMAT!"=="" set "AGENTROUTER_FORMAT=%%b"
    )
    if defined PROXY_UPSTREAM_API_KEY (
        echo [OK] Upstream API key loaded from .env
    )
)

if "!PROXY_UPSTREAM!"=="" set "PROXY_UPSTREAM=https://agentrouter.org"

:: If still not set, prompt user
if "!PROXY_UPSTREAM_API_KEY!"=="" (
    echo [INFO] PROXY_UPSTREAM_API_KEY is not set.
    echo        Create a .env file in this folder with:
    echo        PROXY_UPSTREAM_API_KEY=your-provider-key
    echo.
    set /p "PROXY_UPSTREAM_API_KEY=Or enter your provider key now: "
    if "!PROXY_UPSTREAM_API_KEY!"=="" (
        echo [ERROR] Provider key cannot be empty. Exiting.
        pause
        exit /b 1
    )
    set /p "SAVE_KEY=Save this key to .env for next time? (y/n): "
    if /i "!SAVE_KEY!"=="y" (
        echo PROXY_UPSTREAM_API_KEY=!PROXY_UPSTREAM_API_KEY!> "%~dp0.env"
        echo [OK] Key saved to .env
        echo.
    )
)

:: -------------------------------------------------------
:: 4. Tailscale / Listen Host Setup
:: -------------------------------------------------------
if defined USE_TAILSCALE (
    set "DETECTED_TS_IP="
    where tailscale >nul 2>&1
    if !errorlevel! equ 0 (
        for /f "delims=" %%i in ('tailscale ip -4 2^>nul') do set "DETECTED_TS_IP=%%i"
    )
    if not "!DETECTED_TS_IP!"=="" (
        set "PROXY_LISTEN_HOST=!DETECTED_TS_IP!"
        echo [OK] Detected Tailscale IP: !PROXY_LISTEN_HOST!
    ) else if "!PROXY_LISTEN_HOST!"=="" (
        set /p "PROXY_LISTEN_HOST=Enter your Tailscale IP (100.x.y.z): "
    ) else if "!PROXY_LISTEN_HOST!"=="127.0.0.1" (
        set /p "PROXY_LISTEN_HOST=Enter your Tailscale IP (100.x.y.z): "
    )
    if "!PROXY_AUTH_TOKEN!"=="" (
        echo [INFO] Generating secure random client token for Tailscale...
        for /f "delims=" %%t in ('python -c "import secrets; print(secrets.token_hex(24))"') do set "PROXY_AUTH_TOKEN=%%t"
        echo PROXY_AUTH_TOKEN=!PROXY_AUTH_TOKEN!>> "%~dp0.env"
        echo [OK] Client token generated and saved to .env
    )
)

if "!PROXY_LISTEN_HOST!"=="" set "PROXY_LISTEN_HOST=127.0.0.1"

if not "!PROXY_LISTEN_HOST!"=="127.0.0.1" if not "!PROXY_LISTEN_HOST!"=="localhost" if not "!PROXY_LISTEN_HOST!"=="::1" (
    if "!PROXY_AUTH_TOKEN!"=="" (
        echo [ERROR] PROXY_AUTH_TOKEN is required for network or Tailscale access.
        echo         Set it in .env or run with: start-proxy.bat --tailscale
        pause
        exit /b 1
    )
)

:: -------------------------------------------------------
:: 5. Validate format
:: -------------------------------------------------------
if /i not "%FORMAT%"=="auto" if /i not "%FORMAT%"=="openai" if /i not "%FORMAT%"=="anthropic" (
    echo [ERROR] Invalid format: %FORMAT%
    echo         Valid options: auto, openai, anthropic
    pause
    exit /b 1
)

if /i "%FORMAT%"=="openai" (
    set "AGENTROUTER_FORMAT=openai"
) else if /i "%FORMAT%"=="anthropic" (
    set "AGENTROUTER_FORMAT=anthropic"
)

:: -------------------------------------------------------
:: 6. Launch proxy
:: -------------------------------------------------------
echo.
echo ===================================================
echo   Provider Proxy Launcher
echo ===================================================
echo   Script:     !SCRIPT!
echo   Listen:     !PROXY_LISTEN_HOST!:!PORT!
echo   Proxy URL:  http://!PROXY_LISTEN_HOST!:!PORT!/v1
echo   Upstream:   !PROXY_UPSTREAM!
echo   Format:     !FORMAT!
if not "!PROXY_AUTH_TOKEN!"=="" (
echo   Client Key: !PROXY_AUTH_TOKEN!
echo   Stats URL:  http://!PROXY_LISTEN_HOST!:!PORT!/_stats
echo   Healthz:    http://!PROXY_LISTEN_HOST!:!PORT!/healthz
) else (
echo   Client Key: None (local loopback mode)
echo   Stats URL:  http://localhost:!PORT!/_stats
echo   Healthz:    http://localhost:!PORT!/healthz
)
echo ===================================================
echo.
if not "!PROXY_LISTEN_HOST!"=="127.0.0.1" (
echo [Remote Access Instructions]
echo   Configure your client tool (OpenCode, Claude Code, Cursor, Cline) with:
echo     Base URL: http://!PROXY_LISTEN_HOST!:!PORT!/v1
echo     API Key:  !PROXY_AUTH_TOKEN!
echo.
) else (
echo   Configure your local client tool with:
echo     Base URL: http://127.0.0.1:!PORT!/v1
echo.
)
echo Press Ctrl+C to stop the proxy.
echo ---------------------------------------------------
echo.

set "PROXY_LISTEN_HOST=!PROXY_LISTEN_HOST!"
set "PROXY_UPSTREAM_API_KEY=!PROXY_UPSTREAM_API_KEY!"
set "PROXY_UPSTREAM=!PROXY_UPSTREAM!"
set "PROXY_AUTH_TOKEN=!PROXY_AUTH_TOKEN!"

python "%~dp0!SCRIPT!" !PORT!
set "EXIT_CODE=%errorlevel%"

if !EXIT_CODE! equ 0 goto :end
if !EXIT_CODE! equ 3221225786 goto :end
if !EXIT_CODE! equ 9009 goto :end

echo.
echo [ERROR] Proxy terminated with exit code !EXIT_CODE!.
pause

:end
endlocal
goto :eof

:: -------------------------------------------------------
:: Help
:: -------------------------------------------------------
:show_help
echo Usage: start-proxy.bat [port] [options]
echo.
echo Options:
echo   port              Port number (default: 4182)
echo   --tailscale       Auto-detect Tailscale IP and configure client token
echo   --openai          Use OpenAI-only mode (port 4183)
echo   --anthropic       Use Anthropic-only mode (port 4184)
echo   --format FORMAT   Payload format: auto, openai, anthropic
echo   --help            Show this help
echo.
echo Examples:
echo   start-proxy.bat               (Local loopback, port 4182)
echo   start-proxy.bat --tailscale   (Tailscale remote access)
echo   start-proxy.bat 4190          (Custom port)
echo.
