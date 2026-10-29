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

## Deployment Option 1: Local Setup (Single PC)

Use this when you want to run the proxy on the same PC where you run your coding tools.

### 1. Requirements
- Python 3.10 or newer (no extra packages needed; standard library only).
- An API key from [AgentRouter](https://agentrouter.org/register?aff=M69e) or your upstream provider.

### 2. Configure `.env`
Copy `.env.example` to `.env` in the project root:

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

### 3. Start the Proxy
Double-click `start-proxy.bat` or run in terminal:

```powershell
.\start-proxy.bat
# Or manually with Python:
python .\agentrouter-proxy.py 4182
```

The proxy starts on `http://127.0.0.1:4182`. Your local tools use base URL `http://127.0.0.1:4182/v1`.

---

## Deployment Option 2: Remote Server / Wyse PC via Tailscale (Two PCs)

Use this when you want to run the proxy 24/7 on a secondary PC (like a Dell Wyse, home lab mini-PC, Raspberry Pi, or VPS) and connect to it securely from your main laptop or desktop.

### 1. Tailscale Setup
1. Install [Tailscale](https://tailscale.com) on both machines.
2. Sign in to the **same** Tailscale account on both machines.
3. Note down the Tailscale IP of your server PC (e.g. `100.97.230.23`). You can find it by running:
   ```cmd
   tailscale ip -4
   ```

### 2. Configure the Proxy on the Server PC
On the server PC (e.g. `wyse`), create `.env`:

```ini
PROXY_UPSTREAM=https://agentrouter.org
PROXY_UPSTREAM_API_KEY=your-upstream-provider-key
PROXY_LISTEN_HOST=100.97.230.23
PROXY_AUTH_TOKEN=choose-a-strong-client-secret-token
```

> [!IMPORTANT]
> - `PROXY_LISTEN_HOST` should be the server's **Tailscale IP** (never bind to `0.0.0.0` unless protected by a firewall).
> - `PROXY_AUTH_TOKEN` is a secret token you invent for your clients to authenticate to the proxy. The proxy **refuses to start** on a non-loopback IP without this token!

### 3. Launch on the Server PC
You can start it using any of these methods:

- **Method A (Easiest - 1 click):** Double-click `start-tailscale.bat`. It will auto-detect your Tailscale IP and start.
- **Method B (Batch):** Run `.\start-proxy.bat --tailscale`.
- **Method C (Command line):**
  ```powershell
  python .\agentrouter-proxy.py 4182
  ```
- **Method D (From your laptop via SSH):**
  ```powershell
  ssh wyse "cd C:\Users\GCLC\AgentRouter-Proxy && python agentrouter-proxy.py 4182"
  ```

### 4. Verify Connection from Your Laptop
From your laptop, test that the remote proxy is reachable over Tailscale:

```powershell
# 1. Test unauthenticated request (should return HTTP 401 Unauthorized)
curl.exe -i http://100.97.230.23:4182/healthz

# 2. Test authenticated request (should return HTTP 200 {"status":"ok"})
curl.exe -i -H "Authorization: Bearer choose-a-strong-client-secret-token" http://100.97.230.23:4182/healthz

# 3. Check proxy stats
curl.exe -i -H "Authorization: Bearer choose-a-strong-client-secret-token" http://100.97.230.23:4182/_stats
```

---

## Client Integration Examples

Once your proxy is running (either locally at `127.0.0.1:4182` or remotely at `100.x.y.z:4182`), configure your tools:

### OpenCode

In your `opencode.json` (per-project or in `~/.config/opencode/opencode.json`):

```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "agentrouter-proxy": {
      "name": "AgentRouter Proxy",
      "npm": "@ai-sdk/openai-compatible",
      "options": {
        "baseURL": "http://100.97.230.23:4182/v1",
        "apiKey": "choose-a-strong-client-secret-token"
      },
      "models": {
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
*(If running locally on the same PC, change `baseURL` to `http://127.0.0.1:4182/v1` and leave `apiKey` as any dummy string if `PROXY_AUTH_TOKEN` is unset).*

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

## Running Continuously in Background on Windows (Wyse)

If you want the proxy to run automatically in the background on your remote PC even after reboots:

### Option A: Windows Scheduled Task
On the remote machine (e.g. via SSH):

```cmd
schtasks /create /tn "AgentRouterProxy" /tr "python C:\Users\GCLC\AgentRouter-Proxy\agentrouter-proxy.py 4182" /sc onstart /ru SYSTEM
```

### Option B: PowerShell Detached Process
```powershell
Start-Process python -ArgumentList "C:\Users\GCLC\AgentRouter-Proxy\agentrouter-proxy.py 4182" -WindowStyle Hidden
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

## Testing & Quality Assurance

Run the test suite:

```powershell
python -m py_compile agentrouter-proxy.py agentrouter-proxy-openai.py agentrouter-proxy-anthropic.py
python -m unittest discover -v
```

The test suite includes:
- Unit tests for JSON null stripping.
- Anthropic-to-OpenAI payload normalization.
- SSE billing/null stream filtering.
- Structured content-block error detection.
- End-to-end authentication isolation and token verification against an in-process mock server.

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
