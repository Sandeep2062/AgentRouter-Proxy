#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT=4182
HOST="127.0.0.1"

if [ -f "$SCRIPT_DIR/.env" ]; then
    ENV_PORT=$(grep -E '^PROXY_PORT=' "$SCRIPT_DIR/.env" | cut -d '=' -f2 | tr -d ' "' || true)
    [ -n "$ENV_PORT" ] && PORT="$ENV_PORT"
    ENV_HOST=$(grep -E '^PROXY_LISTEN_HOST=' "$SCRIPT_DIR/.env" | cut -d '=' -f2 | tr -d ' "' || true)
    [ -n "$ENV_HOST" ] && HOST="$ENV_HOST"
fi

echo "================================================================="
echo "   AgentRouter Proxy - Status Check"
echo "   Target: http://$HOST:$PORT"
echo "================================================================="

# Check process
if pgrep -f "agentrouter-proxy.py" >/dev/null 2>&1; then
    echo -e "\033[92m[STATUS] Proxy process is RUNNING\033[0m"
else
    echo -e "\033[91m[STATUS] Proxy process is NOT running\033[0m"
fi

# Check health endpoint
echo -n "Checking healthz endpoint... "
if curl -s -m 2 "http://$HOST:$PORT/healthz" >/dev/null 2>&1; then
    echo -e "\033[92mONLINE (200 OK)\033[0m"
else
    echo -e "\033[93mUNREACHABLE\033[0m"
fi

echo ""
if [ -f "$SCRIPT_DIR/proxy.log" ]; then
    echo "--- Last 10 lines of proxy.log ---"
    tail -n 10 "$SCRIPT_DIR/proxy.log"
fi
