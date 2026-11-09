#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_CMD="python"
else
    echo "[ERROR] Python 3 is not installed or not in PATH."
    exit 1
fi

PORT=4182
if [ -f "$SCRIPT_DIR/.env" ]; then
    ENV_PORT=$(grep -E '^PROXY_PORT=' "$SCRIPT_DIR/.env" | cut -d '=' -f2 | tr -d ' "' || true)
    if [ -n "$ENV_PORT" ]; then
        PORT="$ENV_PORT"
    fi
fi

echo "================================================================="
echo "   AgentRouter Proxy - Cross-Platform Runner (Linux/macOS)"
echo "   Port: $PORT"
echo "================================================================="
echo "Press Ctrl+C to stop the proxy."
echo ""

exec "$PYTHON_CMD" "$SCRIPT_DIR/agentrouter-proxy.py" "$PORT"
