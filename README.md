# Provider-Neutral AI Proxy (AgentRouter & OpenAI / Anthropic Compatible)

A lightweight, zero-dependency Python proxy for AI coding assistants (OpenCode, Claude Code, Cursor, Cline, Roo Code) that routes requests through [AgentRouter](https://agentrouter.org/register?aff=M69e) or any OpenAI-compatible provider.

It automatically handles:
- **Dual protocol support:** Accepts both OpenAI (`/v1/chat/completions`) and Anthropic (`/v1/messages`) formats and translates seamlessly.
- **Request sanitation:** Strips `null`-valued fields (`response_format: null`, etc.) that cause AI SDK type-validation crashes.
- **SSE stream cleaning:** Filters out non-standard events like `data: null` and `billing.summary`.
- **Content-block mitigation:** Automatically trims context and retries once when upstream filters trigger a content block.
- **Tailscale & remote access ready:** Built-in support for running on a remote PC (e.g. Dell Wyse, mini-PC, VPS) and accessing securely from your laptop or desktop over Tailscale.
- **Security by default:** Strictly loopback-only (`127.0.0.1`) unless configured, refuses network binds without authentication tokens, and never writes prompts or API keys to disk.

---

## Architecture Overview

```
[ Your Laptop / Desktop ]
   └── OpenCode / Claude Code / Cursor / Cline
           │
           │  (HTTP / Tailscale)
           ▼
[ Proxy Server ] (Local PC or Remote Wyse / Server)
   ├── Normalizes Anthropic & OpenAI payloads
   ├── Strips null JSON fields & SSE streaming noise
   ├── Injects upstream API key & enforces client auth token
   └── Retries content-blocked responses with trimmed context
           │
           │  (HTTPS)
           ▼
[ Upstream Provider ] (AgentRouter, OpenRouter, etc.)
```

---

## Local Proxy vs. Tailscale Proxy: Which One Do You Need?

| Feature | Local Proxy (Single PC) | Tailscale Proxy (Two PCs / Server) |
| --- | --- | --- |
| **Where it runs** | On the same PC/laptop where you code | On a secondary PC (e.g. Dell Wyse thin client, mini PC, home server) |
| **Best for** | Quick setup, single machine coding | Always-on 24/7 access from your laptop anywhere in the world |
| **Network setup** | None — loopback only (`127.0.0.1`) | [Tailscale](https://tailscale.com) installed on both machines |
| **Security** | Loopback only (no external traffic allowed) | Encrypted WireGuard mesh VPN + Bearer auth token |
| **PC Sleep Impact** | If your laptop sleeps, proxy pauses | Server sleep disabled (`powercfg`); stays online 24/7 |
| **One-Click Setup** | Double-click `setup-local.bat` | Double-click `setup-tailscale.bat` on the server PC |

---

## Deployment Option 1: Local Setup (Single PC)

Use this when you want to run the proxy on the same PC where you run OpenCode, Claude Code, or Cursor.

### Quickstart (1-Click Automated Setup)

1. Double-click `setup-local.bat`.
2. Enter your AgentRouter API key when prompted (`sk-...`).
3. That's it! The script will:
   - Create your `.env` configured for `127.0.0.1`.
   - Run self-tests to ensure everything works.
   - Install auto-start so the proxy automatically launches on Windows startup/reboot.
   - Start the proxy immediately in the background (no black command window).
   - Test connectivity at `http://127.0.0.1:4182/healthz`.

### Manual Setup (Alternative)

<details>
<summary>Click to view manual step-by-step instructions</summary>

1. **Requirements:** Python 3.10 or newer.
2. **Configure `.env`:** Copy `.env.example` to `.env`:
   ```powershell
   Copy-Item .env.example .env
   ```
   Edit `.env`:
   ```ini
   PROXY_UPSTREAM=https://agentrouter.org
   PROXY_UPSTREAM_API_KEY=your-provider-api-key-here
   PROXY_LISTEN_HOST=127.0.0.1
   PROXY_AUTH_TOKEN=
   ```
3. **Start the Proxy:**
   ```powershell
   .\start-proxy.bat
   # Or directly with Python:
   python .\agentrouter-proxy.py 4182
   ```

The proxy starts on `http://127.0.0.1:4182`. Your local tools use base URL `http://127.0.0.1:4182/v1`.
</details>

---

## Deployment Option 2: Remote Server / Wyse PC via Tailscale (Two PCs)

Use this when you want to run the proxy 24/7 on a secondary PC (like a Dell Wyse, home lab mini-PC, Raspberry Pi, or VPS) and connect to it securely from your main laptop or desktop.

### Quickstart (1-Click Automated Setup)

1. Ensure **Tailscale** is installed and signed in on both your server PC and your laptop.
2. On your **server PC** (e.g. Dell Wyse), double-click:
   ```cmd
   setup-tailscale.bat
   ```
3. The script will:
   - Auto-detect your server's Tailscale IP (e.g. `100.97.230.23`).
   - Prompt for your AgentRouter API key (`sk-...`) and client secret token (or auto-generate one).
   - Permanently disable Windows sleep on AC power (`powercfg /change standby-timeout-ac 0`) so the server stays reachable 24/7 headless.
   - Install auto-start into Windows Startup and Scheduled Tasks.
   - Launch the proxy immediately in the background.
   - Display a copy-paste ready OpenCode configuration block for your laptop!

### Manual Setup (Alternative)

<details>
<summary>Click to view manual step-by-step instructions</summary>

1. **Tailscale Setup:**
   Install Tailscale on both machines and note the server's IP via `tailscale ip -4`.
2. **Configure `.env` on Server PC:**
   ```ini
   PROXY_UPSTREAM=https://agentrouter.org
   PROXY_UPSTREAM_API_KEY=your-upstream-provider-key
   PROXY_LISTEN_HOST=100.97.230.23
   PROXY_AUTH_TOKEN=choose-a-strong-client-secret-token
   ```
3. **Launch on Server PC:**
   Double-click `start-tailscale.bat` or run:
   ```powershell
   .\start-proxy.bat --tailscale
   ```
</details>

### 4. Verify Connection from Your Laptop
From your laptop, test that the remote proxy is reachable over Tailscale:

```powershell
# 1. Test unauthenticated request (should return HTTP 401 Unauthorized)
curl.exe -i http://100.97.230.23:4182/healthz

# 2. Test authenticated request (should return HTTP 200 {"status":"ok"})
curl.exe -i -H "Authorization: Bearer choose-a-strong-client-secret-token" http://100.97.230.23:4182/healthz

# 3. Check proxy stats
curl.exe -i -H "Authorization: Bearer choose-a-strong-client-secret-token" http://100.97.230.23:4182/_stats

# 4. Check token usage (today, yesterday, monthly, all-time)
curl.exe -H "Authorization: Bearer choose-a-strong-client-secret-token" http://100.97.230.23:4182/_usage
```

---

## Client Integration Examples

Once your proxy is running (either locally at `127.0.0.1:4182` or remotely at `100.x.y.z:4182`), configure your tools:

### OpenCode

In your `opencode.json` (per-project or in `~/.config/opencode/opencode.json`):

#### When Connecting over Tailscale (Wyse / Server PC):
```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "agentrouter-proxy-wyse": {
      "name": "AgentRouter (Wyse Tailscale Proxy)",
      "npm": "@ai-sdk/openai-compatible",
      "options": {
        "baseURL": "http://100.97.230.23:4182/v1",
        "apiKey": "your-client-auth-token"
      },
      "models": {
        "gpt-6.1-sol": { "name": "GPT 6.1 Sol" },
        "claude-opus-5": { "name": "Claude Opus 5" },
        "claude-opus-4-8": { "name": "Claude Opus 4.8" },
        "claude-opus-4-7": { "name": "Claude Opus 4.7" },
        "claude-opus-4-6": { "name": "Claude Opus 4.6" },
        "gpt-5.5": { "name": "GPT 5.5" },
        "glm-5.2": { "name": "GLM 5.2" }
      }
    }
  }
}
```

#### When Running Locally (Same PC):
```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "agentrouter-proxy-local": {
      "name": "AgentRouter (Local Proxy)",
      "npm": "@ai-sdk/openai-compatible",
      "options": {
        "baseURL": "http://127.0.0.1:4182/v1",
        "apiKey": "local-proxy-token"
      },
      "models": {
        "gpt-6.1-sol": { "name": "GPT 6.1 Sol" },
        "claude-opus-5": { "name": "Claude Opus 5" },
        "claude-opus-4-8": { "name": "Claude Opus 4.8" },
        "claude-opus-4-7": { "name": "Claude Opus 4.7" },
        "claude-opus-4-6": { "name": "Claude Opus 4.6" },
        "gpt-5.5": { "name": "GPT 5.5" }
      }
    }
  }
}
```

> [!TIP]
> **Why use this provider instead of `AgentRouter (Direct Responses API)`?**
> When OpenCode uses direct Responses API (`/v1/responses`), multi-turn tool calling (e.g., `planning-with-files` in the `Build` agent) sends stateful item references. Because AgentRouter load balances across distinct Azure OpenAI clusters, subsequent turns often hit a different cluster, throwing:
> `Error: The requested item was created under a different Azure OpenAI resource.`
> 
> By selecting **AgentRouter (Wyse Tailscale Proxy)** or **AgentRouter (Local Proxy)** with `npm: "@ai-sdk/openai-compatible"`, the proxy normalizes requests into standard stateless Chat Completions with self-contained context on every turn, completely eliminating this error!

### Claude Code

Point Claude Code to the proxy using environment variables:

```powershell
$env:ANTHROPIC_BASE_URL = "http://100.97.230.23:4182"
$env:ANTHROPIC_AUTH_TOKEN = "choose-a-strong-client-secret-token"
claude
```

### Cursor / Cline / Roo Code

- **Provider:** OpenAI Compatible
- **Base URL:** `http://100.97.230.23:4182/v1`
- **API Key:** Your `PROXY_AUTH_TOKEN` (or dummy string if local loopback)
- **Model:** Enter any model supported by your upstream provider (e.g. `claude-opus-5`, `claude-opus-4-8`, `gpt-5.5`)

### Python (`openai` SDK)

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://100.97.230.23:4182/v1",
    api_key="choose-a-strong-client-secret-token",
)

response = client.chat.completions.create(
    model="claude-opus-5",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(response.choices[0].message.content)
```

---

## Auto-Start on System Boot (Windows & Wyse PC)

To keep the proxy running 24/7 as a background service on your server PC (e.g. Dell Wyse thin client or home server):

### 1. One-Click Automated Setup

**Option A — Tailscale/server PC (run once on the machine that will serve the proxy):**

Double-click `setup-tailscale.bat` on your server/Wyse PC. It will:
1. Auto-detect your Tailscale IP and write `.env` with sensible defaults.
2. Create `start-tailscale.bat` configured to your Tailscale IP.
3. Install the silent auto-start launcher + Scheduled Task.
4. Disable sleep on AC power.
5. Launch the proxy immediately in the background.
6. Print an OpenCode configuration snippet to paste into `opencode.json`.

**Option B — Local setup (run on the same PC you code on):**

Double-click `setup-local.bat`. It will:
1. Create `.env` bound to `127.0.0.1` with a local auth token.
2. Install auto-start into `%APPDATA%\Startup`.
3. Start the proxy in the background.

**Option C — Manual installer (legacy):**

On the server PC, double-click:
```cmd
install-autostart.bat
```
This automated installer:
1. **Installs a silent auto-start launcher** into `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\AgentRouter-Proxy.vbs`.
2. **Registers a Windows Scheduled Task** (`AgentRouterProxy`) for logon triggers.
3. **Disables Windows sleep on AC power** (`powercfg /change standby-timeout-ac 0`), preventing the Wyse PC from going into sleep mode while running headless.
4. **Starts the proxy immediately in the background** without opening any black command window.
5. **Appends all logs** to `proxy.log` in real time.

### 2. Check Proxy Status & Logs
Run `status-proxy.bat` or run in terminal:
```powershell
# Check if proxy is running
.\status-proxy.bat

# Or view real-time logs
powershell Get-Content .\proxy.log -Wait -Tail 20
```

### 3. Uninstall Auto-Start
To completely remove auto-start and terminate background proxy processes:
```cmd
uninstall-autostart.bat
```

---

## Environment Variables Reference

All settings can be configured via `.env` file or environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `PROXY_UPSTREAM` | `https://agentrouter.org` | Upstream provider base URL (e.g. `https://openrouter.ai/api` or custom) |
| `PROXY_UPSTREAM_API_KEY` | *(required)* | Your provider API key |
| `PROXY_LISTEN_HOST` | `127.0.0.1` | IP address to bind to (`127.0.0.1` for local, or Tailscale IP `100.x.y.z`) |
| `PROXY_AUTH_TOKEN` | *(empty)* | Client Bearer token. **Mandatory** when listening on a non-loopback address |
| `PROXY_UPSTREAM_AUTH_SCHEME` | `Bearer` | Upstream auth header scheme (`Bearer`, `Basic`, etc.) |
| `PROXY_UPSTREAM_TIMEOUT` | `300` | Upstream request timeout in seconds |
| `PROXY_MAX_BODY_BYTES` | `20971520` (20MB) | Maximum allowed incoming request body size |
| `AGENTROUTER_FORMAT` | `auto` | Payload format mode: `auto`, `openai`, or `anthropic` |
| `PROXY_INJECT_PREAMBLE` | `0` | Set `1` to inject educational Mandarin preamble for strict CJK filters |
| `AGENTROUTER_DEBUG` | `0` | Set `1` for verbose metadata diagnostics |

*Legacy variable names `AGENTROUTER_API_KEY` and `AGENTROUTER_UPSTREAM` continue to work for backwards compatibility.*

---

## Token Usage Tracking

The proxy tracks token consumption (prompt tokens, completion tokens, total) for every non-streaming request and persists them to `usage.json` (never committed to git).

### `GET /_usage`

Returns a live JSON breakdown of token usage:

```powershell
# Local proxy (PowerShell)
curl.exe http://127.0.0.1:4182/_usage

# Wyse / Tailscale proxy (PowerShell)
curl.exe -H "Authorization: Bearer your-auth-token" http://100.97.230.23:4182/_usage

# Or format as pretty table in PowerShell:
(Invoke-RestMethod -Headers @{ Authorization = "Bearer your-auth-token" } -Uri "http://100.97.230.23:4182/_usage").today
```

Example response:
```json
{
  "today": { "prompt_tokens": 1200, "completion_tokens": 480, "total_tokens": 1680 },
  "yesterday": { "prompt_tokens": 4300, "completion_tokens": 1700, "total_tokens": 6000 },
  "this_month": { "prompt_tokens": 22000, "completion_tokens": 9100, "total_tokens": 31100 },
  "last_month": { "prompt_tokens": 95000, "completion_tokens": 38000, "total_tokens": 133000 },
  "all_time": { "prompt_tokens": 117000, "completion_tokens": 47100, "total_tokens": 164100 },
  "by_model": {
    "gpt-6.1-sol": { "prompt_tokens": 117000, "completion_tokens": 47100, "total_tokens": 164100 }
  }
}
```

> **Note:** Streaming responses (`stream: true`) do not include per-chunk token counts from AgentRouter, so those requests are not counted. Non-streaming requests are fully counted.

---

## Testing & Quality Assurance

Run the test suite:

```powershell
pip install pytest
python -m pytest test_proxy.py -v
```

The test suite includes:
- Unit tests for JSON null stripping.
- Anthropic-to-OpenAI payload normalization.
- SSE billing/null stream filtering.
- Structured content-block error detection.
- End-to-end authentication isolation and token verification against an in-process mock server.

---

## Troubleshooting & FAQ

### 1. "The requested item was created under a different Azure OpenAI resource"
- **Why this happens:** When OpenCode connects directly to AgentRouter's native `/v1/responses` endpoint (e.g. `AgentRouter (Direct Responses API)`), multi-turn sessions (such as the `Build` agent executing tools like `planning-with-files`) send stateful item or response IDs. AgentRouter load-balances incoming requests across multiple regional Azure OpenAI clusters. When Turn 2 lands on a different Azure cluster than Turn 1, Azure rejects the request with this error.
- **Solution:** Route through `AgentRouter-Proxy`. In OpenCode's model selector, select `AgentRouter (Wyse Tailscale Proxy)` or `AgentRouter (Local Proxy)`. The proxy converts requests into standard stateless OpenAI Chat Completions payloads, sending self-contained inputs on every turn so cross-cluster Azure routing never conflicts.

### 2. "Connection timed out on Wyse / Remote PC"
- **Why this happens:** Windows automatically enters sleep or standby mode after 15 to 30 minutes of keyboard/mouse inactivity. Since a headless server PC has no physical user input, Windows puts the machine to sleep, dropping SSH and Tailscale connections.
- **Solution:** Run `install-autostart.bat` on the server PC. It runs `powercfg /change standby-timeout-ac 0` to permanently disable sleep on AC power, keeping the server reachable 24/7.

### 3. "The following users have been banned due to long-term use that does not support the client"
- **Why this happens:** AgentRouter blocks or bans accounts making high volumes of API requests with generic or unauthorized user-agent headers.
- **Solution:** `AgentRouter-Proxy` automatically injects `User-Agent: opencode/2.2.1` into all upstream requests to ensure full compatibility with provider policies.

---

## Security Best Practices

1. **Never commit `.env` or real API keys:** This repository is public. `.gitignore` is pre-configured to ignore `.env`, `*.env`, log files, and caches.
2. **Revoke compromised keys immediately:** If an API key was ever accidentally pasted in public issues, chat logs, or commits, revoke it right away in your provider dashboard.
3. **Use different keys:** Your incoming `PROXY_AUTH_TOKEN` (used between your laptop and proxy) should be different from your upstream provider API key.
4. **Tailscale encryption:** Tailscale traffic is encrypted peer-to-peer with WireGuard, keeping your remote traffic safe across networks without port forwarding.

---

## Provider Referral

If you need an AgentRouter account, support this project by signing up through the official link:
👉 [Register at AgentRouter](https://agentrouter.org/register?aff=M69e)

---

## License

MIT License. See [LICENSE](LICENSE) for details.
