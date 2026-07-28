@echo off
setlocal enabledelayedexpansion

echo ===================================================
echo     AgentRouter Proxy Launcher for OpenCode v3.1
echo ===================================================
echo.

:: -------------------------------------------------------
:: 1. Check Python
:: -------------------------------------------------------
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not available in PATH!
    echo Please install Python 3 and add it to your system PATH.
    echo.
    pause
    exit /b 1
)

:: -------------------------------------------------------
:: 2. Load API key from .env (if not already set)
:: -------------------------------------------------------
if "%AGENTROUTER_API_KEY%"=="" (
    if exist "%~dp0.env" (
        for /f "usebackq tokens=1,* delims==" %%a in ("%~dp0.env") do (
            if "%%a"=="AGENTROUTER_API_KEY" (
                set "AGENTROUTER_API_KEY=%%b"
            )
        )
        if defined AGENTROUTER_API_KEY (
            echo [OK] API key loaded from .env
        ) else (
            echo [WARN] .env found but AGENTROUTER_API_KEY not defined in it.
        )
    )
)

:: If still not set, prompt user
if "!AGENTROUTER_API_KEY!"=="" (
    echo [INFO] AGENTROUTER_API_KEY is not set.
    echo        Create a .env file in this folder with:
    echo        AGENTROUTER_API_KEY=sk-your-key-here
    echo.
    set /p "AGENTROUTER_API_KEY=Or enter your API key now (sk-...): "
    if "!AGENTROUTER_API_KEY!"=="" (
        echo [ERROR] API key cannot be empty. Exiting.
        pause
        exit /b 1
    )
    echo.

    :: Offer to save to .env for next time
    set /p "SAVE_KEY=Save this key to .env for next time? (y/n): "
    if /i "!SAVE_KEY!"=="y" (
        echo AGENTROUTER_API_KEY=!AGENTROUTER_API_KEY!> "%~dp0.env"
        echo [OK] Key saved to .env
        echo.
    )
)

:: -------------------------------------------------------
:: 3. Parse arguments
::    %1 = port (default 4182)
::    %2 = format: auto, openai, anthropic (default auto)
::    Or use named args: --port 4182 --format openai
:: -------------------------------------------------------
set "PORT=4182"
set "FORMAT=auto"
set "SCRIPT=agentrouter-proxy.py"

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
if /i "%~1"=="--help" (
    goto :show_help
)
:: Assume first non-flag arg is port
set "PORT=%~1"
shift
goto :parse_args

:args_done

:: Validate format
if /i not "%FORMAT%"=="auto" if /i not "%FORMAT%"=="openai" if /i not "%FORMAT%"=="anthropic" (
    echo [ERROR] Invalid format: %FORMAT%
    echo         Valid options: auto, openai, anthropic
    pause
    exit /b 1
)

:: -------------------------------------------------------
:: 4. Set format env var for combined proxy
:: -------------------------------------------------------
if /i "%FORMAT%"=="openai" (
    set "AGENTROUTER_FORMAT=openai"
) else if /i "%FORMAT%"=="anthropic" (
    set "AGENTROUTER_FORMAT=anthropic"
)

:: -------------------------------------------------------
:: 5. Launch proxy
:: -------------------------------------------------------
echo Starting AgentRouter proxy on port !PORT!...
echo.
echo   Script:     !SCRIPT!
echo   Proxy URL:  http://localhost:!PORT!/v1
echo   Stats:      http://localhost:!PORT!/_stats
echo   Upstream:   https://agentrouter.org
echo   Format:     !FORMAT!
echo.
echo   opencode.json location:
echo     Per-project:  ^<project-root^>\opencode.json
echo     Global:       %%USERPROFILE%%\.config\opencode\opencode.json (or opencode.jsonc / go find it by ur own)
echo.
echo   Set baseURL in your opencode.json (AgentRouter provider only):
echo     With proxy:    "baseURL": "http://localhost:!PORT!/v1"
echo     Without proxy: "baseURL": "https://agentrouter.org/v1"
echo.
echo Press Ctrl+C to stop the proxy.
echo ---------------------------------------------------
echo.

python "%~dp0!SCRIPT!" !PORT!
set "EXIT_CODE=%errorlevel%"

:: Ctrl+C produces exit codes like 3221225786 (0xC000013A) or 9009 — not real errors
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
echo   --port PORT       Specify port number
echo   --format FORMAT   Payload format: auto, openai, anthropic (default: auto)
echo   --openai          Use OpenAI-only proxy (port 4183)
echo   --anthropic       Use Anthropic-only proxy (port 4184)
echo   --help            Show this help
echo.
echo Examples:
echo   start-proxy.bat              ^(combined, auto-detect, port 4182^)
echo   start-proxy.bat 4190         ^(combined, auto-detect, port 4190^)
echo   start-proxy.bat --openai     ^(OpenAI-only, port 4183^)
echo   start-proxy.bat --anthropic  ^(Anthropic-only, port 4184^)
echo   start-proxy.bat --format openai --port 4200
echo.
pause
exit /b 0
