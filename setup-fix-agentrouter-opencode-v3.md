# AgentRouter Proxy for OpenCode — Setup Guide

> **v3.1** — July 28, 2026

A local proxy that fixes all AgentRouter issues in OpenCode:
- ✅ Fixes `Type validation failed` crashes (data: null, billing.summary)
- ✅ Fixes `content-blocked` on educational content (CJK/Mandarin)
- ✅ Auto-retry on content blocks with anti-loop protection
- ✅ Supports both OpenAI and Anthropic payload formats
- ✅ Buffered SSE reading (much faster than byte-by-byte)
- ✅ Does not affect other providers (OpenRouter, Anthropic, etc.)

---

## Quick Start (3 Steps)

### 1. Create a `.env` file

Create a `.env` file in the same folder as `agentrouter-proxy.py`:

```
AGENTROUTER_API_KEY=sk-your-key-here
```

### 2. Run the proxy

Double-click `start-proxy.bat` or run manually:

```bash
python agentrouter-proxy.py
```

### 3. Configure `opencode.json`

Add or update the AgentRouter provider in your project's `opencode.json`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "agentrouter": {
      "name": "AgentRouter",
      "npm": "@ai-sdk/openai-compatible",
      "options": {
        "baseURL": "http://localhost:4182/v1",
        "apiKey": "sk-placeholder"
      },
      "models": {
        "claude-opus-5": { "name": "Claude Opus 5" },
        "claude-opus-4-8": { "name": "Claude Opus 4.8" },
        "claude-opus-4-7": { "name": "Claude Opus 4.7" },
        "claude-opus-4-6": { "name": "Claude Opus 4.6" },
        "gpt-5.5": { "name": "GPT 5.5" },
        "gpt-5.6-sol": { "name": "GPT 5.6 Sol" },
        "glm-5.2": { "name": "GLM 5.2" },
        "kimi-k3": { "name": "Kimi K3" }
      }
    }
  }
}
```

> [!WARNING]
> Use `@ai-sdk/openai-compatible`, **not** `@ai-sdk/anthropic`.
> The `apiKey` field can be a placeholder — the proxy handles auth from `.env`.

Restart OpenCode. Done! 🎉

---

## Proxy Variants (3 Options)

The v3.1 release provides **three proxy scripts** for different use cases:

| Script | Port | Format | Best For |
|--------|------|--------|----------|
| `agentrouter-proxy.py` | 4182 | Auto-detect (OpenAI + Anthropic) | Most users, mixed clients |
| `agentrouter-proxy-openai.py` | 4183 | OpenAI only | OpenCode with `@ai-sdk/openai-compatible` |
| `agentrouter-proxy-anthropic.py` | 4184 | Anthropic → OpenAI convert | OpenCode with `@ai-sdk/anthropic` |

### Option A: Combined Proxy (auto-detect) — Port 4182

```bash
python agentrouter-proxy.py
# or
start-proxy.bat
```

Accepts both OpenAI and Anthropic format payloads. Auto-detects format from the request body.

### Option B: OpenAI-Only Proxy — Port 4183

```bash
python agentrouter-proxy-openai.py
# or
start-proxy.bat --openai
```

Lightweight version — no Anthropic conversion overhead. Use with `@ai-sdk/openai-compatible`.

### Option C: Anthropic-Only Proxy — Port 4184

```bash
python agentrouter-proxy-anthropic.py
# or
start-proxy.bat --anthropic
```

Accepts Anthropic-format requests (`/v1/messages`) and converts them to OpenAI for AgentRouter. Handles:
- Content blocks (text, image, tool_use, tool_result, thinking)
- System field (string or list of blocks)
- Tool calls and tool results
- `max_tokens` → `max_completion_tokens` mapping

### Force Format via Environment Variable

```bash
set AGENTROUTER_FORMAT=openai    # Force OpenAI mode
set AGENTROUTER_FORMAT=anthropic # Force Anthropic mode
python agentrouter-proxy.py
```

---

## What's New in v3.1

### 🚀 Performance: Buffered SSE Reading
- **Before**: Read SSE byte-by-byte (`resp.read(1)`) — extremely slow for large responses
- **After**: Reads in 8KB chunks, extracts complete events — **~8000x fewer read calls**

### 🛡️ Anti-Loop Protection
- Tracks consecutive content-blocked failures per model
- After **3 consecutive blocks**, stops retrying and passes the error through
- Prevents infinite retry loops (like the 12+ gpt-5.5 blocks seen in the log)
- Counter resets on successful response

### 🔍 Early Content-Block Detection in SSE
- Buffers the **first SSE event** before sending HTTP response headers
- If the first event is content-blocked, **retries** instead of forwarding the error
- Previously, SSE streams couldn't retry because headers were already sent

### 🔄 Improved Anthropic Support
- Handles `thinking` content blocks
- Handles `tool_result` → `tool` role conversion
- Handles `top_k` parameter
- Better detection of Anthropic vs OpenAI payloads

### 📊 Enhanced Stats Endpoint
- New `anti_loop_triggered` counter in `/_stats`

---

## `start-proxy.bat` Usage

```bash
start-proxy.bat                    # Combined, auto-detect, port 4182
start-proxy.bat 4190               # Combined, auto-detect, port 4190
start-proxy.bat --openai           # OpenAI-only, port 4183
start-proxy.bat --anthropic        # Anthropic-only, port 4184
start-proxy.bat --format openai    # Combined, force OpenAI mode
start-proxy.bat --format anthropic --port 4200
start-proxy.bat --help             # Show help
```

---

## `opencode.json` Location

| Scope | Path |
|---|---|
| Per-project | `<project-root>/opencode.json` |
| Global | `%USERPROFILE%\.config\opencode\config.json` |

---

## Troubleshooting

| Error | Cause | Fix |
|---|---|---|
| Empty output (no response) | Using `@ai-sdk/anthropic` | Switch to `@ai-sdk/openai-compatible` or use `agentrouter-proxy-anthropic.py` |
| `Type validation failed: null` | Proxy not running | Run `start-proxy.bat` first |
| `Type validation failed: billing.summary` | Proxy not running | Run `start-proxy.bat` first |
| `content-blocked` | AgentRouter content filter | Handled automatically (auto-retry + anti-loop) |
| `Connection refused localhost:4182` | Proxy not started | Run `start-proxy.bat` first |
| Infinite retry loop | Same model keeps getting blocked | v3.1 anti-loop stops after 3 retries |

---

## Tips

- **Change API key** → edit `.env` file
- **Check proxy stats** → open `http://localhost:4182/_stats`
- **See blocked content** → check `blocked-requests.log`
- **Debug mode** → `set AGENTROUTER_DEBUG=1` before running the proxy
- **Force format** → `set AGENTROUTER_FORMAT=openai` (or `anthropic`)
- **Use without proxy** → change baseURL back to `https://agentrouter.org/v1`
- **Used the old JS plugin?** → delete `agentrouter-fix.js` from `~/.config/opencode/plugins/`