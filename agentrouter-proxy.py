#!/usr/bin/env python3
"""
Enhanced AgentRouter Proxy for OpenCode — v3.1
Content-block mitigation + SSE stream fix + request cleanup.
Optimized with buffered SSE, early block detection, anti-loop protection.

This proxy sits between OpenCode and AgentRouter, providing:

  1. SSE stream filtering (data: null, billing.summary)
  2. Request body cleanup (strip null-valued fields)
  3. User-Agent injection for AgentRouter client auth
  4. System prompt injection (educational content preamble)
  5. Auto-retry on content-blocked with trimmed context
  6. Retry statistics endpoint (GET /_stats)
  7. Debug mode via AGENTROUTER_DEBUG=1
  8. OpenAI + Anthropic dual format support (auto-detect or force via env)
  9. Anti-loop protection (stops retrying after N consecutive blocks)
 10. Buffered SSE reading (chunk-based, not byte-by-byte)

Usage:
    set AGENTROUTER_API_KEY=sk-...
    python agentrouter-proxy.py [port]       # default 4182

Environment Variables:
    AGENTROUTER_API_KEY    API key for AgentRouter (required)
    AGENTROUTER_UPSTREAM   Upstream URL (default https://agentrouter.org)
    AGENTROUTER_FORMAT     Payload format: "auto" (detect), "openai", "anthropic"
                          Default: auto
    AGENTROUTER_DEBUG=1    Dump requests and SSE chunks to stderr
"""

import http.server
import urllib.request
import urllib.error
import ssl
import sys
import json
import threading
import os
import datetime
import collections
import hmac
import subprocess

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_LOG_PATH = os.path.join(_SCRIPT_DIR, "proxy.log")

class TeeLogger:
    def __init__(self, filename, original):
        self.filename = filename
        self.original = original
        self.file = None
        try:
            self.file = open(filename, "a", encoding="utf-8", buffering=1)
        except Exception:
            pass

    def write(self, text):
        if self.original:
            try:
                self.original.write(text)
            except Exception:
                pass
        if self.file:
            try:
                self.file.write(text)
            except Exception:
                pass

    def flush(self):
        if self.original and hasattr(self.original, "flush"):
            try:
                self.original.flush()
            except Exception:
                pass
        if self.file and hasattr(self.file, "flush"):
            try:
                self.file.flush()
            except Exception:
                pass

    def isatty(self):
        if self.original and hasattr(self.original, "isatty"):
            try:
                return self.original.isatty()
            except Exception:
                pass
        return False



if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.stdout = TeeLogger(_LOG_PATH, sys.stdout)
sys.stderr = TeeLogger(_LOG_PATH, sys.stderr)


def load_env_file(path: str = None) -> None:
    """Load key-value pairs from a .env file into os.environ without overwriting existing vars."""
    if path is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.isfile(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    if k and k not in os.environ:
                        os.environ[k] = v
    except Exception:
        pass


load_env_file()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

UPSTREAM = os.environ.get(
    "PROXY_UPSTREAM", os.environ.get("AGENTROUTER_UPSTREAM", "https://agentrouter.org")
).rstrip("/")
PORT = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 4182
API_KEY = os.environ.get(
    "PROXY_UPSTREAM_API_KEY", os.environ.get("AGENTROUTER_API_KEY", "")
)
LISTEN_HOST = os.environ.get("PROXY_LISTEN_HOST", "127.0.0.1")
if LISTEN_HOST.strip().lower() == "tailscale":
    try:
        ts_ip = subprocess.check_output(["tailscale", "ip", "-4"], text=True, timeout=3).strip().splitlines()[0]
        if ts_ip:
            LISTEN_HOST = ts_ip
    except Exception:
        LISTEN_HOST = "0.0.0.0"
PROXY_AUTH_TOKEN = os.environ.get("PROXY_AUTH_TOKEN", "")
UPSTREAM_AUTH_SCHEME = os.environ.get("PROXY_UPSTREAM_AUTH_SCHEME", "Bearer")
MAX_BODY_BYTES = int(os.environ.get("PROXY_MAX_BODY_BYTES", str(20 * 1024 * 1024)))
UPSTREAM_TIMEOUT = float(os.environ.get("PROXY_UPSTREAM_TIMEOUT", "300"))
INJECT_PREAMBLE = os.environ.get("PROXY_INJECT_PREAMBLE", "0") == "1"
USER_AGENT = "opencode/2.2.1"
CTX = ssl.create_default_context()

# Format mode: auto (detect), openai, anthropic
FORMAT_MODE = os.environ.get("AGENTROUTER_FORMAT", "auto").strip().lower()

# Anti-loop: max consecutive content-blocked retries per model before giving up
MAX_CONSECUTIVE_BLOCKS = 3

# SSE read chunk size (bytes) — instead of reading byte-by-byte
SSE_CHUNK_SIZE = 8192

SUPPORTED_MODELS = {
    "claude-opus-5",
    "claude-opus-4-8",
    "claude-opus-4-7",
    "claude-opus-4-6",
    "gpt-5.5",
    "gpt-5.6-sol",
    "gpt-6.1-sol",
    "gpt-6-astra",
    "glm-5.2",
    "kimi-k3",
}

MODEL_ALIASES = {
    "claude-opus-4.8": "claude-opus-4-8",
    "claude-opus-4.7": "claude-opus-4-7",
    "claude-opus-4.6": "claude-opus-4-6",
    "claude-opus-5": "claude-opus-5",
}

# ---------------------------------------------------------------------------
# Content-Block Mitigation — Educational Preamble
# ---------------------------------------------------------------------------
# This preamble is injected into every request's system message to signal
# to AgentRouter's content filter that the conversation contains legitimate
# educational material (CJK characters, Pinyin, textbook excerpts, etc.).
# You can customize this text to match your specific use case.

EDUCATION_PREAMBLE = (
    "This conversation is part of an educational language-learning application "
    "for studying Mandarin Chinese. All Chinese characters (Hanzi), Pinyin, "
    "vocabulary lists, and textbook excerpts are standard pedagogical material. "
    "Please process them normally."
)

# ---------------------------------------------------------------------------
# Consecutive-block tracker (anti-loop)
# ---------------------------------------------------------------------------
# Tracks how many times in a row a given model was content-blocked.
# Reset on successful response.

_block_counter_lock = threading.Lock()
_block_counter = collections.Counter()  # model_name -> consecutive block count


def _check_and_increment_block(model: str) -> bool:
    """Returns True if retry should be attempted, False if limit exceeded."""
    with _block_counter_lock:
        _block_counter[model] += 1
        count = _block_counter[model]
        if count > MAX_CONSECUTIVE_BLOCKS:
            return False
        return True


def _reset_block_counter(model: str):
    """Reset the consecutive block counter on success."""
    with _block_counter_lock:
        if model in _block_counter:
            del _block_counter[model]


# ---------------------------------------------------------------------------
# Statistics (thread-safe)
# ---------------------------------------------------------------------------

_stats_lock = threading.Lock()
_stats = {
    "requests": 0,
    "content_blocked": 0,
    "retry_success": 0,
    "retry_failed": 0,
    "anti_loop_triggered": 0,
}


# ---------------------------------------------------------------------------
# Token Usage Tracker  (persisted to usage.json next to proxy script)
# ---------------------------------------------------------------------------

_USAGE_PATH = os.path.join(_SCRIPT_DIR, "usage.json")
_usage_lock = threading.Lock()


def _load_usage() -> dict:
    """Load usage.json, return empty structure on missing/corrupt file."""
    try:
        with open(_USAGE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def _save_usage(data: dict) -> None:
    """Atomically write usage.json."""
    try:
        tmp = _USAGE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, _USAGE_PATH)
    except Exception:
        pass


def record_tokens(model: str, prompt_tokens: int, completion_tokens: int, total_tokens: int) -> None:
    """Record token usage into usage.json keyed by YYYY-MM-DD and YYYY-MM."""
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    month = today[:7]  # YYYY-MM
    with _usage_lock:
        data = _load_usage()
        # Per-day bucket
        day_bucket = data.setdefault("days", {}).setdefault(today, {})
        day_bucket["prompt_tokens"] = day_bucket.get("prompt_tokens", 0) + prompt_tokens
        day_bucket["completion_tokens"] = day_bucket.get("completion_tokens", 0) + completion_tokens
        day_bucket["total_tokens"] = day_bucket.get("total_tokens", 0) + total_tokens
        day_bucket["requests"] = day_bucket.get("requests", 0) + 1
        # Per-model breakdown inside day
        models_day = day_bucket.setdefault("models", {}).setdefault(model, {})
        models_day["total_tokens"] = models_day.get("total_tokens", 0) + total_tokens
        models_day["requests"] = models_day.get("requests", 0) + 1
        # Per-month bucket
        month_bucket = data.setdefault("months", {}).setdefault(month, {})
        month_bucket["prompt_tokens"] = month_bucket.get("prompt_tokens", 0) + prompt_tokens
        month_bucket["completion_tokens"] = month_bucket.get("completion_tokens", 0) + completion_tokens
        month_bucket["total_tokens"] = month_bucket.get("total_tokens", 0) + total_tokens
        month_bucket["requests"] = month_bucket.get("requests", 0) + 1
        _save_usage(data)


def get_usage_summary() -> dict:
    """Return usage summary: today, yesterday, this month, last month, all-time."""
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    this_month = today[:7]
    last_month_dt = datetime.datetime.now().replace(day=1) - datetime.timedelta(days=1)
    last_month = last_month_dt.strftime("%Y-%m")
    with _usage_lock:
        data = _load_usage()
    days = data.get("days", {})
    months = data.get("months", {})
    all_time_tokens = sum(v.get("total_tokens", 0) for v in months.values())
    all_time_requests = sum(v.get("requests", 0) for v in months.values())
    return {
        "today": days.get(today, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "requests": 0}),
        "yesterday": days.get(yesterday, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "requests": 0}),
        "this_month": months.get(this_month, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "requests": 0}),
        "last_month": months.get(last_month, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "requests": 0}),
        "all_time": {"total_tokens": all_time_tokens, "requests": all_time_requests},
    }

# ---------------------------------------------------------------------------
# Blocked Content Logger
# ---------------------------------------------------------------------------

def log_blocked_content(body: bytes, error_body: bytes = b"", extra_info: str = ""):
    """Log safe metadata only; request bodies and prompts never touch disk."""
    model = "unknown"
    msg_count = 0

    try:
        obj = json.loads(body)
        model = obj.get("model", "unknown")
        messages = obj.get("messages", [])
        msg_count = len(messages)

    except (json.JSONDecodeError, ValueError):
        pass

    # Parse error response
    error_info = ""
    if error_body:
        error_info = error_body.decode(errors="replace")[:200]

    sys.stderr.write(
        f"[ar] blocked content: model={model!r} messages={msg_count} "
        f"request_bytes={len(body)} response_bytes={len(error_body)}\n"
    )
    if extra_info:
        sys.stderr.write(f"[ar]   Extra:    {extra_info}\n")
    if error_info:
        sys.stderr.write(f"[ar]   Server response: {error_info}\n")


# ===================================================================
# Request Processing
# ===================================================================


def clean_request_body(raw: bytes) -> bytes:
    """Remove null-valued fields from JSON request body.

    The AI SDK sends ``response_format: null`` and similar fields;
    AgentRouter rejects these with 400 "expected object, received null".

    Uses iterative stack-based traversal instead of recursion to avoid
    stack overflow on very deep/large payloads (175+ messages).
    """
    try:
        obj = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return raw

    if not isinstance(obj, (dict, list)):
        return raw

    # Iterative cleanup using a stack
    def _clean(value):
        if isinstance(value, dict):
            # Stack of (dict, new_dict) pairs to process
            stack = [(value, {})]
            result_stack = []
            while stack:
                current, new = stack.pop()
                for k, v in current.items():
                    if v is not None:
                        if isinstance(v, (dict, list)):
                            new[k] = v  # will be replaced after processing
                            result_stack.append((v, new, k))
                        else:
                            new[k] = v
            # Process nested structures
            while result_stack:
                v, parent, k = result_stack.pop()
                parent[k] = _clean(v)
            return new
        elif isinstance(value, list):
            return [_clean(item) if isinstance(item, (dict, list)) else item
                    for item in value if item is not None]
        return value

    cleaned = _clean(obj)
    return json.dumps(cleaned, separators=(",", ":")).encode()


def normalize_model_name(model):
    """Normalize a few common model aliases to values AgentRouter accepts."""
    if not isinstance(model, str):
        return model
    trimmed = model.strip()
    if not trimmed:
        return model
    lowered = trimmed.lower()
    return MODEL_ALIASES.get(lowered, trimmed)


def looks_like_anthropic_request(obj: dict) -> bool:
    """Detect Anthropic-style payloads such as /v1/messages requests."""
    if not isinstance(obj, dict):
        return False
    # Anthropic messages endpoint uses "anthropic_version" field
    if "anthropic_version" in obj:
        return True
    # Anthropic uses "max_tokens" (not "max_completion_tokens")
    # AND has messages with content as list of blocks
    if "max_tokens" in obj and "max_completion_tokens" not in obj:
        messages = obj.get("messages", [])
        if isinstance(messages, list) and messages:
            first = messages[0]
            if isinstance(first, dict):
                content = first.get("content")
                # Anthropic content blocks are always lists of typed objects
                if isinstance(content, list) and content:
                    first_block = content[0]
                    if isinstance(first_block, dict) and "type" in first_block and "text" in first_block:
                        return True
    return False


def detect_format(obj: dict) -> str:
    """Detect whether the payload is OpenAI or Anthropic format.

    Returns 'openai' or 'anthropic'.
    """
    if FORMAT_MODE == "openai":
        return "openai"
    if FORMAT_MODE == "anthropic":
        return "anthropic"
    # Auto-detect
    if looks_like_anthropic_request(obj):
        return "anthropic"
    return "openai"


def anthropic_to_openai(obj: dict) -> dict:
    """Translate Anthropic-style payloads into OpenAI-compatible shape.

    Handles:
      - /v1/messages content blocks (text, image, tool_use, tool_result, thinking)
      - system field (string or list of blocks)
      - max_tokens -> max_completion_tokens
      - stop_sequences -> stop
      - Anthropic metadata (user_id, etc.)
    """
    if not isinstance(obj, dict):
        return obj

    messages = []
    system_messages = []

    for msg in obj.get("messages", []):
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        content = msg.get("content")

        # Map Anthropic roles
        if role == "assistant":
            # Check for tool_use content blocks
            if isinstance(content, list):
                text_parts = []
                tool_calls = []
                for block in content:
                    if isinstance(block, dict):
                        block_type = block.get("type")
                        if block_type == "text":
                            text_parts.append(block.get("text", ""))
                        elif block_type == "tool_use":
                            tool_calls.append({
                                "id": block.get("id", ""),
                                "type": "function",
                                "function": {
                                    "name": block.get("name", ""),
                                    "arguments": json.dumps(block.get("input", {}), separators=(",", ":")),
                                }
                            })
                        elif block_type == "thinking":
                            text_parts.append(block.get("thinking", ""))
                        elif block_type == "tool_result":
                            text_parts.append(json.dumps(block.get("content", ""), separators=(",", ":")))
                combined_text = "\n".join([p for p in text_parts if p])
                msg_obj = {"role": "assistant", "content": combined_text}
                if tool_calls:
                    msg_obj["tool_calls"] = tool_calls
                messages.append(msg_obj)
                continue
            else:
                messages.append({"role": "assistant", "content": str(content or "")})
                continue

        if role == "system":
            if isinstance(content, list):
                parts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        parts.append(block.get("text", ""))
                content = "\n".join(parts)
            system_messages.append({"role": "system", "content": str(content or "")})
            continue

        if role == "tool_result":
            # Convert to OpenAI tool result format
            tool_call_id = msg.get("tool_use_id", "")
            if isinstance(content, list):
                text_parts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                content = "\n".join(text_parts)
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": str(content or ""),
            })
            continue

        if role not in {"user", "assistant"}:
            if role == "tool":
                messages.append(msg)
                continue
            continue

        # User role
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        parts.append(block.get("text", ""))
                    elif block.get("type") == "image":
                        parts.append("[image]")
                    elif block.get("type") == "tool_result":
                        parts.append("[tool_result]")
            content = "\n".join([p for p in parts if p])
        elif content is None:
            content = ""

        messages.append({"role": role, "content": str(content)})

    # Handle top-level 'system' field (Anthropic-specific)
    system_value = obj.get("system")
    if isinstance(system_value, str) and system_value:
        system_messages.insert(0, {"role": "system", "content": system_value})
    elif isinstance(system_value, list):
        parts = []
        for block in system_value:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        if parts:
            system_messages.insert(0, {"role": "system", "content": "\n".join(parts)})

    if system_messages:
        messages = system_messages + messages

    normalized = {
        "model": normalize_model_name(obj.get("model")),
        "messages": messages,
        "stream": obj.get("stream", False),
    }

    # Map Anthropic-specific fields to OpenAI equivalents
    if "max_tokens" in obj:
        normalized["max_completion_tokens"] = obj["max_tokens"]
    if "temperature" in obj:
        normalized["temperature"] = obj["temperature"]
    if "top_p" in obj:
        normalized["top_p"] = obj["top_p"]
    if "top_k" in obj:
        normalized["top_k"] = obj["top_k"]
    if "stop_sequences" in obj:
        normalized["stop"] = obj["stop_sequences"]
    if "tools" in obj:
        normalized["tools"] = obj["tools"]
    if "tool_choice" in obj:
        normalized["tool_choice"] = obj["tool_choice"]
    if "metadata" in obj:
        normalized["metadata"] = obj["metadata"]

    return normalized



RESPONSES_MODELS = {"gpt-6.1-sol", "gpt-5.6-sol", "gpt-6-astra"}


def is_responses_model(model: str) -> bool:
    if not isinstance(model, str):
        return False
    m = model.strip().lower()
    return m in RESPONSES_MODELS or m.endswith("-sol") or "astra" in m


def chat_messages_to_responses_input(messages: list) -> list:
    """Convert OpenAI/Chat-Completions style `messages` to Responses API `input` items.

    In OpenAI Chat Completions:
    - Assistant tool calls are inside `message.tool_calls`
    - Tool responses are messages with `role: "tool"` and `tool_call_id`
    - Text blocks are {"type": "text", "text": "..."}

    In Responses API:
    - Tool calls are standalone items with `type: "function_call"`, `call_id`, `name`, `arguments`
    - Tool responses are standalone items with `type: "function_call_output"`, `call_id`, `output`
    - Every message item MUST have a non-null `content` field.
    - Content text blocks use `type: "input_text"` instead of `type: "text"`.
    """
    if not isinstance(messages, list):
        return []

    responses_input = []

    for msg in messages:
        if not isinstance(msg, dict):
            continue

        # If already formatted as a Responses API item, preserve it
        if msg.get("type") in ("function_call", "function_call_output"):
            responses_input.append(msg)
            continue

        role = msg.get("role", "")
        content = msg.get("content")

        if isinstance(content, list):
            all_text = all(isinstance(b, dict) and b.get("type") in ("text", "input_text") for b in content)
            if all_text:
                normalized_content = "".join(b.get("text", "") for b in content if isinstance(b, dict))
            else:
                normalized_content = []
                for b in content:
                    if not isinstance(b, dict):
                        continue
                    b_type = b.get("type")
                    if b_type == "text":
                        normalized_content.append({"type": "input_text", "text": b.get("text", "")})
                    elif b_type == "image_url":
                        normalized_content.append({"type": "input_image", "image_url": b.get("image_url")})
                    else:
                        normalized_content.append(b)
        elif content is None:
            normalized_content = ""
        else:
            normalized_content = str(content)

        if role in ("tool", "function"):
            call_id = msg.get("tool_call_id") or msg.get("id") or msg.get("name", "call_default")
            output_val = normalized_content if isinstance(normalized_content, str) else json.dumps(normalized_content, separators=(",", ":"))
            responses_input.append({
                "type": "function_call_output",
                "call_id": call_id,
                "output": output_val,
            })
            continue

        tool_calls = msg.get("tool_calls")
        if role == "assistant" and tool_calls and isinstance(tool_calls, list):
            if normalized_content:
                responses_input.append({
                    "role": "assistant",
                    "content": normalized_content,
                })
            for tc in tool_calls:
                if not isinstance(tc, dict):
                    continue
                call_id = tc.get("id") or "call_default"
                fn = tc.get("function", {}) if isinstance(tc.get("function"), dict) else {}
                name = fn.get("name") or tc.get("name", "")
                args = fn.get("arguments") if "arguments" in fn else tc.get("arguments", "{}")
                if not isinstance(args, str):
                    args = json.dumps(args, separators=(",", ":"))
                responses_input.append({
                    "type": "function_call",
                    "id": f"fc_{call_id}" if not str(call_id).startswith("fc_") else str(call_id),
                    "call_id": call_id,
                    "name": name,
                    "arguments": args,
                })
            continue

        responses_input.append({
            "role": role if role in ("user", "assistant", "system", "developer") else "user",
            "content": normalized_content,
        })

    return responses_input


def responses_to_chat_completion(res_json: dict, model: str) -> dict:
    output_text = ""
    tool_calls = []
    for item in res_json.get("output", []):
        itype = item.get("type")
        if itype == "message":
            for c in item.get("content", []):
                if c.get("text"):
                    output_text += c.get("text")
        elif itype == "function_call":
            tool_calls.append({
                "id": item.get("call_id") or item.get("id", "call_default"),
                "type": "function",
                "function": {
                    "name": item.get("name", ""),
                    "arguments": item.get("arguments", "{}"),
                },
            })

    usage_raw = res_json.get("usage")
    usage = usage_raw if isinstance(usage_raw, dict) else {}
    finish_reason = "tool_calls" if tool_calls else "stop"

    msg = {
        "role": "assistant",
        "content": output_text or None,
    }
    if tool_calls:
        msg["tool_calls"] = tool_calls

    return {
        "id": res_json.get("id", "chatcmpl-responses"),
        "object": "chat.completion",
        "created": res_json.get("created_at", int(datetime.datetime.now().timestamp())),
        "model": res_json.get("model", model),
        "choices": [
            {
                "index": 0,
                "message": msg,
                "finish_reason": finish_reason,
            }
        ],
        "usage": {
            "prompt_tokens": usage.get("input_tokens", 0),
            "completion_tokens": usage.get("output_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
        },
    }


def translate_responses_sse_line(line: bytes, resp_id: str = "chatcmpl-stream") -> list[bytes]:
    if not line.startswith(b"data: "):
        return []
    raw = line[6:].strip()
    if not raw or raw == b"[DONE]":
        return [b"data: [DONE]\n\n"]
    try:
        data = json.loads(raw)
    except Exception:
        return []

    event_type = data.get("type")
    if event_type == "response.output_text.delta":
        delta = data.get("delta", "")
        chunk = {
            "id": resp_id,
            "object": "chat.completion.chunk",
            "choices": [{"index": 0, "delta": {"content": delta}}],
        }
        return [b"data: " + json.dumps(chunk, separators=(",", ":")).encode() + b"\n\n"]
    elif event_type == "response.output_item.added":
        item = data.get("item", {})
        if item.get("type") == "function_call":
            chunk = {
                "id": resp_id,
                "object": "chat.completion.chunk",
                "choices": [{
                    "index": 0,
                    "delta": {
                        "tool_calls": [{
                            "index": 0,
                            "id": item.get("call_id") or item.get("id", ""),
                            "type": "function",
                            "function": {
                                "name": item.get("name", ""),
                                "arguments": "",
                            },
                        }]
                    },
                }],
            }
            return [b"data: " + json.dumps(chunk, separators=(",", ":")).encode() + b"\n\n"]
    elif event_type == "response.function_call_arguments.delta":
        delta = data.get("delta", "")
        chunk = {
            "id": resp_id,
            "object": "chat.completion.chunk",
            "choices": [{
                "index": 0,
                "delta": {
                    "tool_calls": [{
                        "index": 0,
                        "function": {"arguments": delta},
                    }]
                },
            }],
        }
        return [b"data: " + json.dumps(chunk, separators=(",", ":")).encode() + b"\n\n"]
    elif event_type in ("response.completed", "response.done"):
        resp_obj = data.get("response") if isinstance(data.get("response"), dict) else data
        has_tool_call = any(
            isinstance(it, dict) and it.get("type") == "function_call"
            for it in resp_obj.get("output", [])
        )
        finish_reason = "tool_calls" if has_tool_call else "stop"
        stop_chunk = {
            "id": resp_id,
            "object": "chat.completion.chunk",
            "choices": [{"index": 0, "delta": {}, "finish_reason": finish_reason}],
        }
        return [
            b"data: " + json.dumps(stop_chunk, separators=(",", ":")).encode() + b"\n\n",
            b"data: [DONE]\n\n",
        ]
    return []

def normalize_upstream_path(path: str, obj: dict | None = None) -> tuple[str, dict]:
    """Map Anthropic-style requests to an OpenAI-compatible upstream path.

    Only converts if the payload is Anthropic format (auto-detected or forced).
    """
    if not isinstance(obj, dict):
        return path, obj

    fmt = detect_format(obj)

    if fmt == "anthropic":
        # Map /v1/messages, /v1, / to /v1/chat/completions
        if path in {"/v1", "/v1/", ""} or path.endswith("/messages"):
            path, obj = "/v1/chat/completions", anthropic_to_openai(obj)
        else:
            obj = anthropic_to_openai(obj)

    model = obj.get("model", "")
    if path in ("/v1/chat/completions", "/chat/completions") and is_responses_model(model):
        resp_payload = {
            "model": model,
            "input": chat_messages_to_responses_input(obj.get("messages", [])),
            "_converted_from_chat": True,
        }
        if "stream" in obj:
            resp_payload["stream"] = obj["stream"]
        if "temperature" in obj:
            resp_payload["temperature"] = obj["temperature"]
        if "max_tokens" in obj or "max_completion_tokens" in obj:
            resp_payload["max_output_tokens"] = obj.get("max_tokens") or obj.get("max_completion_tokens")

        # Convert tools to Responses API format
        if "tools" in obj and isinstance(obj["tools"], list):
            r_tools = []
            for t in obj["tools"]:
                if not isinstance(t, dict):
                    continue
                if "function" in t and isinstance(t["function"], dict):
                    fn = t["function"]
                    r_tools.append({
                        "type": "function",
                        "name": fn.get("name", ""),
                        "description": fn.get("description", ""),
                        "parameters": fn.get("parameters", {}),
                    })
                else:
                    r_tools.append(t)
            resp_payload["tools"] = r_tools

        if "tool_choice" in obj:
            resp_payload["tool_choice"] = obj["tool_choice"]

        return "/v1/responses", resp_payload

    return path, obj


def normalize_request_body(raw: bytes, path: str):
    """Clean, inject preamble, and normalize payloads for AgentRouter."""
    body = clean_request_body(raw)
    if not body:
        return path, body

    try:
        obj = json.loads(body)
    except (json.JSONDecodeError, ValueError):
        return path, body

    if not isinstance(obj, dict):
        return path, body

    if INJECT_PREAMBLE:
        obj = inject_system_preamble(obj)
    path, obj = normalize_upstream_path(path, obj)
    if obj is None:
        return path, body

    if isinstance(obj, dict):
        if "model" in obj and isinstance(obj["model"], str):
            obj["model"] = normalize_model_name(obj["model"])
        body = json.dumps(obj, separators=(",", ":")).encode()
    return path, body


def sanitize_system_reminders(obj: dict) -> dict:
    """Strip code-heavy system reminders from user messages.

    AI coding assistants inject <system-reminder> blocks containing file
    paths and code snippets into user messages. AgentRouter's content
    filter often flags these as blocked content.

    This function replaces the code content inside system reminders with
    a neutral placeholder to avoid false-positive blocks.
    """
    if not isinstance(obj, dict) or "messages" not in obj:
        return obj

    import re

    for msg in obj.get("messages", []):
        if not isinstance(msg, dict) or msg.get("role") != "user":
            continue
        content = msg.get("content", "")
        if not isinstance(content, str):
            continue

        # Replace <system-reminder> blocks that contain code/file references
        # Pattern matches: <system-reminder>...</system-reminder> with content
        # that includes "Line Content" or "file" or "code" indicators
        original = content
        content = re.sub(
            r'<system-reminder>\s*The user opened the file in the IDE\..*?</system-reminder>',
            '<system-reminder>The user is working on a coding task.</system-reminder>',
            content,
            flags=re.DOTALL,
        )
        # Also strip terminal/available_terminal blocks
        content = re.sub(
            r'<system-reminder>\s*The maximum number of terminals.*?</system-reminder>',
            '<system-reminder>Terminal status check.</system-reminder>',
            content,
            flags=re.DOTALL,
        )
        # Strip Response Language Settings blocks
        content = re.sub(
            r'<system-reminder>\s*# Response Language Settings.*?</system-reminder>',
            '<system-reminder>Language settings applied.</system-reminder>',
            content,
            flags=re.DOTALL,
        )
        if content != original:
            msg["content"] = content

    return obj


def inject_system_preamble(obj: dict) -> dict:
    """Inject educational preamble into the system message.

    This helps prevent false-positive content blocking on CJK
    educational content by explicitly declaring the context.
    Also sanitizes system reminders in user messages.
    """
    if not isinstance(obj, dict) or "messages" not in obj:
        return obj

    # First, sanitize system reminders in user messages
    obj = sanitize_system_reminders(obj)

    messages = obj.get("messages", [])
    if not messages:
        return obj

    # Find first system message and prepend preamble
    for msg in messages:
        if msg.get("role") == "system":
            content = msg.get("content", "")
            if isinstance(content, str) and EDUCATION_PREAMBLE not in content:
                msg["content"] = EDUCATION_PREAMBLE + "\n\n" + content
            return obj

    # No system message found — insert one at the beginning
    messages.insert(0, {"role": "system", "content": EDUCATION_PREAMBLE})
    return obj


def trim_context_for_retry(body: bytes) -> bytes:
    """Trim conversation context to system message(s) + last user message.

    Used when content-blocked is detected to retry without the
    contaminated history.  The trade-off is loss of conversation
    context, but it is better than being stuck entirely.
    """
    try:
        obj = json.loads(body)
    except (json.JSONDecodeError, ValueError):
        return body

    if not isinstance(obj, dict) or "messages" not in obj:
        return body

    messages = obj.get("messages", [])
    trimmed = []

    # Keep all system messages (including injected preamble)
    for msg in messages:
        if msg.get("role") == "system":
            trimmed.append(msg)

    # Keep only the last user message
    for msg in reversed(messages):
        if msg.get("role") == "user":
            trimmed.append(msg)
            break

    obj["messages"] = trimmed
    return json.dumps(obj, separators=(",", ":")).encode()


# ===================================================================
# Response Processing
# ===================================================================


def _looks_like_billing_summary(obj) -> bool:
    """Detect the ``billing.summary`` object AgentRouter injects."""
    return isinstance(obj, dict) and obj.get("object") == "billing.summary"


def is_content_blocked(data: bytes) -> bool:
    """Check if a response indicates *content-blocked* from AgentRouter.

    Handles both JSON error structures and raw-text responses.
    Avoids false positives by checking specific structures rather than
    doing a naive substring search on model output.
    """
    if not data:
        return False

    # --- JSON structure (most reliable) ---
    try:
        obj = json.loads(data)
        if isinstance(obj, dict):
            # Check error.type / error.message
            error = obj.get("error", {})
            if isinstance(error, dict):
                etype = str(error.get("type", "")).lower()
                emsg = str(error.get("message", "")).lower()
                if "content_blocked" in etype or "content-blocked" in etype:
                    return True
                if "content-blocked" in emsg or "content_blocked" in emsg:
                    return True
            # Top-level type
            if "content_blocked" in str(obj.get("type", "")).lower():
                return True
    except (json.JSONDecodeError, ValueError):
        pass

    # --- Raw text fallback (matches the format seen in the screenshot:
    #     "content-blocked (request id: ...)")  ---
    text = data.decode(errors="replace").strip().lower()
    if text.startswith("content-blocked"):
        return True

    return False


def clean_sse_line(line: bytes):
    """Filter problematic SSE lines from the stream.

    Returns ``None`` if the line should be discarded.
    """
    stripped = line.strip()
    if not stripped:
        return line  # SSE separator — keep

    if stripped.startswith(b"data:"):
        payload = stripped[len(b"data:"):].strip()
        if payload == b"null" or payload == b"":
            return None
        try:
            obj = json.loads(payload)
        except (json.JSONDecodeError, ValueError):
            return line  # e.g. "[DONE]"
        if _looks_like_billing_summary(obj):
            return None
        return line

    # Raw JSON without ``data:`` prefix (e.g. injected billing.summary)
    if stripped.startswith(b"{") or stripped.startswith(b"["):
        try:
            obj = json.loads(stripped)
        except (json.JSONDecodeError, ValueError):
            return line
        if _looks_like_billing_summary(obj):
            return None

    return line


def clean_nonstream_body(raw: bytes) -> bytes:
    """For non-stream responses, replace billing.summary with an error."""
    if not raw:
        return raw
    try:
        obj = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return raw
    if _looks_like_billing_summary(obj):
        sys.stderr.write("[ar] filtered billing.summary in non-stream response\n")
        return json.dumps({
            "error": {
                "message": "agentrouter billing.summary is not a chat response",
                "type": "proxy_filtered",
            }
        }).encode()
    return raw


# ===================================================================
# Buffered SSE reader — reads in chunks instead of byte-by-byte
# ===================================================================


class BufferedSSEReader:
    """Reads an SSE stream in chunks and yields complete events.

    Much faster than the previous byte-by-byte approach, while still
    allowing early content-block detection before forwarding data.
    """

    def __init__(self, response, debug=False):
        self.resp = response
        self.debug = debug
        self._buf = b""

    def read_events(self):
        """Generator that yields complete SSE events (bytes).

        Each yielded value is a single SSE event ending with \n\n or \r\n\r\n.
        """
        while True:
            chunk = self.resp.read(SSE_CHUNK_SIZE)
            if not chunk:
                # End of stream — flush remaining buffer
                if self._buf:
                    yield self._buf
                return

            self._buf += chunk

            # Extract complete events from buffer
            while True:
                idx_dos = self._buf.find(b"\n\n")
                idx_crlf = self._buf.find(b"\r\n\r\n")
                delim_len = 2
                delim_idx = -1

                if idx_dos >= 0 and idx_crlf >= 0:
                    delim_idx = min(idx_dos, idx_crlf)
                elif idx_dos >= 0:
                    delim_idx = idx_dos
                elif idx_crlf >= 0:
                    delim_idx = idx_crlf
                    delim_len = 4

                if delim_idx < 0:
                    break  # need more data

                event = self._buf[:delim_idx + delim_len]
                self._buf = self._buf[delim_idx + delim_len:]
                yield event


# ===================================================================
# HTTP Proxy Handler
# ===================================================================


class ProxyHandler(http.server.BaseHTTPRequestHandler):
    """Reverse-proxy handler that intercepts AgentRouter traffic."""

    # ------ HTTP verbs ------

    def do_POST(self):
        self._proxy()

    def do_GET(self):
        if self.path == "/healthz":
            if not self._authorized():
                return
            body = b'{"status":"ok"}\n'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            self.wfile.flush()
            return
        if self.path == "/_usage":
            if not self._authorized():
                return
            self._serve_usage()
            return

        if self.path == "/_stats":
            if not self._authorized():
                return
            self._serve_stats()
            return
        self._proxy()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Content-Length", "0")
        self.end_headers()

    # ------ Stats endpoint ------

    def _serve_usage(self):
        """``GET /_usage`` — return token usage by day/month as JSON."""
        summary = get_usage_summary()
        data = json.dumps(summary, indent=2).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
        self.wfile.flush()

    def _serve_stats(self):
        """``GET /_stats`` — return proxy statistics as JSON."""
        with _stats_lock:
            data = json.dumps(_stats, indent=2).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _authorized(self):
        """Authorize clients when a token is configured."""
        if not PROXY_AUTH_TOKEN:
            return True
        supplied = self.headers.get("Authorization", "")
        expected = f"Bearer {PROXY_AUTH_TOKEN}"
        if hmac.compare_digest(supplied, expected):
            return True
        err = b'{"error":{"message":"proxy authentication required"}}\n'
        self.send_response(401)
        self.send_header("WWW-Authenticate", "Bearer")
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(err)))
        self.end_headers()
        self.wfile.write(err)
        self.wfile.flush()
        return False

    # ------ Main proxy logic ------

    def _proxy(self):
        if not self._authorized():
            return
        content_len = int(self.headers.get("Content-Length", 0))
        if content_len > MAX_BODY_BYTES:
            err = b'{"error":{"message":"request body too large"}}\n'
            self.send_response(413)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(err)))
            self.end_headers()
            self.wfile.write(err)
            self.wfile.flush()
            return
        raw_body = self.rfile.read(content_len) if content_len > 0 else None

        with _stats_lock:
            _stats["requests"] += 1

        debug = os.environ.get("AGENTROUTER_DEBUG", "") == "1"

        # --- Prepare request body ---
        target_path = self.path
        body = None
        if raw_body:
            target_path, body = normalize_request_body(raw_body, self.path)

        if debug and body:
            try:
                obj = json.loads(body)
                sys.stderr.write(
                    f"[ar-dbg] req: path={target_path} model={obj.get('model')} "
                    f"stream={obj.get('stream')} "
                    f"msgs={len(obj.get('messages', []))} "
                    f"body={len(body)}b\n"
                )
            except Exception:
                sys.stderr.write(f"[ar-dbg] req {len(body)}b body (not JSON)\n")

        # --- Attempt request (with retry on content-blocked) ---
        self._attempt_request(
            body,
            is_retry=False,
            debug=debug,
            target_path=target_path,
        )

    # ------ Build upstream headers ------

    def _build_headers(self, body):
        """Construct headers for the upstream AgentRouter request."""
        hdrs = {}
        for k, v in self.headers.items():
            kl = k.lower()
            if kl not in ("host", "connection", "transfer-encoding",
                          "accept-encoding", "authorization"):
                hdrs[k] = v
        hdrs["Authorization"] = f"{UPSTREAM_AUTH_SCHEME} {API_KEY}"
        hdrs["User-Agent"] = USER_AGENT
        # Force uncompressed responses so we can filter SSE line-by-line.
        hdrs["Accept-Encoding"] = "identity"
        if body is not None:
            hdrs["Content-Length"] = str(len(body))
        return hdrs

    # ------ Upstream request + retry logic ------

    def _attempt_request(self, body, *, is_retry, debug=False, target_path=None):
        """Send request to AgentRouter.  Retries **once** on content-blocked
        with a trimmed context (system message + last user message only).

        For streaming requests, buffers the first SSE event before sending
        HTTP response headers to allow early content-block detection.
        """
        hdrs = self._build_headers(body)
        url = f"{UPSTREAM}{target_path or self.path}"
        req = urllib.request.Request(
            url, data=body, headers=hdrs, method=self.command
        )
        is_stream = (
            body is not None
            and b'"stream":true' in body.replace(b" ", b"")
        )

        # Extract model for anti-loop tracking
        model = "unknown"
        if body:
            try:
                model = json.loads(body).get("model", "unknown")
            except (json.JSONDecodeError, ValueError):
                pass

        try:
            resp = urllib.request.urlopen(req, context=CTX, timeout=UPSTREAM_TIMEOUT)

            if is_stream:
                self._handle_stream_response(resp, body, model, is_retry, debug, target_path)
            else:
                self._handle_nonstream_response(resp, body, model, is_retry, debug, target_path)

        except urllib.error.HTTPError as e:
            err_body = e.read()
            self._handle_http_error(e, err_body, body, model, is_retry, debug, target_path)

        except Exception as e:
            sys.stderr.write(f"[ar] EXCEPTION: {e}\n")
            err_data = json.dumps({"error": str(e)}).encode() + b"\n"
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(err_data)))
            self.end_headers()
            self.wfile.write(err_data)
            self.wfile.flush()

    # ------ Streaming response handler (with buffered early detection) ------

    def _handle_stream_response(self, resp, body, model, is_retry, debug, target_path):
        """Handle a streaming response.

        Buffers the first SSE event to detect content-blocked before
        sending HTTP response headers, allowing retry.
        """
        reader = BufferedSSEReader(resp, debug)

        # Buffer first event to check for content-blocked before sending headers
        first_event = None
        for event in reader.read_events():
            first_event = event
            break

        # Check if first event is content-blocked
        if first_event is not None and is_content_blocked(first_event) and body and not is_retry:
            sys.stderr.write(
                "[ar] [WARN] content-blocked in SSE stream (early detect), "
                "retrying with trimmed context...\n"
            )
            log_blocked_content(body, first_event, extra_info="SSE early-detect block")
            with _stats_lock:
                _stats["content_blocked"] += 1
            _check_and_increment_block(model)
            retry_body = trim_context_for_retry(body)
            self._attempt_request(
                retry_body,
                is_retry=True,
                debug=debug,
                target_path=target_path,
            )
            return

        # Now send response headers (we know the first event is OK)
        self.send_response(resp.status)
        for k, v in resp.headers.items():
            if k.lower() not in ("transfer-encoding", "connection"):
                self.send_header(k, v)
        self.end_headers()

        is_converted_chat = False
        if target_path == "/v1/responses" and body:
            try:
                req_obj = json.loads(body)
                is_converted_chat = req_obj.get("_converted_from_chat", False)
            except Exception:
                pass

        if is_converted_chat:
            resp_id = f"chatcmpl-{model}"
            if first_event is not None:
                for line in first_event.splitlines():
                    for tl in translate_responses_sse_line(line, resp_id):
                        try:
                            self.wfile.write(tl)
                            self.wfile.flush()
                        except (BrokenPipeError, ConnectionResetError):
                            return
            for event in reader.read_events():
                for line in event.splitlines():
                    for tl in translate_responses_sse_line(line, resp_id):
                        try:
                            self.wfile.write(tl)
                            self.wfile.flush()
                        except (BrokenPipeError, ConnectionResetError):
                            return
            return

        # Forward the first event (already read)
        if first_event is not None:
            cleaned = clean_sse_line(first_event)
            if cleaned is not None:
                try:
                    self.wfile.write(cleaned)
                    self.wfile.flush()
                except (ConnectionResetError, BrokenPipeError):
                    return

        # Forward remaining events
        for event in reader.read_events():
            if debug:
                sys.stderr.write(
                    f"[ar-dbg] evt ({len(event)}b): {event[:400]!r}\n"
                )

            # Log content-blocked if it appears mid-stream (can't retry)
            if is_content_blocked(event):
                sys.stderr.write(
                    "[ar] [WARN] content-blocked detected in SSE "
                    "stream (cannot retry mid-stream)\n"
                )
                with _stats_lock:
                    _stats["content_blocked"] += 1

            cleaned = clean_sse_line(event)
            if cleaned is None:
                if debug:
                    sys.stderr.write(
                        "[ar-dbg] -> DISCARDED by filter\n"
                    )
                continue

            try:
                self.wfile.write(cleaned)
                self.wfile.flush()
            except (ConnectionResetError, BrokenPipeError):
                return

        # All events streamed successfully — reset block counter
        _reset_block_counter(model)
        if is_retry:
            sys.stderr.write("[ar] [OK] retry succeeded\n")
            with _stats_lock:
                _stats["retry_success"] += 1

    # ------ Non-streaming response handler ------

    def _handle_nonstream_response(self, resp, body, model, is_retry, debug, target_path):
        """Handle a non-streaming (buffered) response."""
        buf = resp.read()

        # Content-blocked in a 200 response
        if not is_retry and is_content_blocked(buf) and body:
            sys.stderr.write(
                "[ar] [WARN] content-blocked in 200 response, "
                "retrying with trimmed context...\n"
            )
            log_blocked_content(body, buf)
            with _stats_lock:
                _stats["content_blocked"] += 1
            if not _check_and_increment_block(model):
                # Anti-loop triggered
                sys.stderr.write(
                    f"[ar] [FAIL] anti-loop: {model} blocked "
                    f"{MAX_CONSECUTIVE_BLOCKS}+ times, giving up\n"
                )
                with _stats_lock:
                    _stats["anti_loop_triggered"] += 1
                # Fall through to send the error response
            else:
                retry_body = trim_context_for_retry(body)
                self._attempt_request(
                    retry_body,
                    is_retry=True,
                    debug=debug,
                    target_path=target_path,
                )
                return

        # Retry outcome logging
        if is_retry and is_content_blocked(buf):
            sys.stderr.write("[ar] [FAIL] retry also blocked\n")
            with _stats_lock:
                _stats["retry_failed"] += 1
        elif is_retry:
            sys.stderr.write("[ar] [OK] retry succeeded\n")
            with _stats_lock:
                _stats["retry_success"] += 1
            _reset_block_counter(model)

        is_converted_chat = False
        if target_path == "/v1/responses" and body:
            try:
                req_obj = json.loads(body)
                is_converted_chat = req_obj.get("_converted_from_chat", False)
            except Exception:
                pass

        if is_converted_chat and not is_content_blocked(buf):
            try:
                res_obj = json.loads(buf)
                chat_comp = responses_to_chat_completion(res_obj, model)
                cleaned = json.dumps(chat_comp, separators=(",", ":")).encode("utf-8")
            except Exception:
                cleaned = clean_nonstream_body(buf)
        else:
            cleaned = clean_nonstream_body(buf)
        self.send_response(resp.status)
        for k, v in resp.headers.items():
            if k.lower() not in ("transfer-encoding", "connection", "content-length"):
                self.send_header(k, v)
        self.send_header("Content-Length", str(len(cleaned)))
        self.end_headers()
        self.wfile.write(cleaned)
        self.wfile.flush()

        # Record token usage from response body
        if not is_content_blocked(buf):
            _reset_block_counter(model)
            try:
                resp_obj = json.loads(cleaned)
                usage_data = resp_obj.get("usage") or {}
                record_tokens(
                    model=model,
                    prompt_tokens=int(usage_data.get("prompt_tokens", 0)),
                    completion_tokens=int(usage_data.get("completion_tokens", 0)),
                    total_tokens=int(usage_data.get("total_tokens", 0)),
                )
            except Exception:
                pass

    # ------ HTTP error handler ------

    def _handle_http_error(self, e, err_body, body, model, is_retry, debug, target_path):
        """Handle HTTP errors, with retry logic for content-blocked."""
        # Content-blocked retry (HTTP error)
        if not is_retry and is_content_blocked(err_body) and body:
            sys.stderr.write(
                f"[ar] [WARN] content-blocked (HTTP {e.code}), "
                f"retrying with trimmed context...\n"
            )
            log_blocked_content(body, err_body)
            with _stats_lock:
                _stats["content_blocked"] += 1

            if not _check_and_increment_block(model):
                # Anti-loop triggered
                sys.stderr.write(
                    f"[ar] [FAIL] anti-loop: {model} blocked "
                    f"{MAX_CONSECUTIVE_BLOCKS}+ times, giving up\n"
                )
                with _stats_lock:
                    _stats["anti_loop_triggered"] += 1
                # Fall through to send the error response
            else:
                retry_body = trim_context_for_retry(body)
                self._attempt_request(
                    retry_body,
                    is_retry=True,
                    debug=debug,
                    target_path=target_path,
                )
                return

        # Retry outcome logging
        if is_retry and is_content_blocked(err_body):
            sys.stderr.write("[ar] [FAIL] retry also blocked\n")
            with _stats_lock:
                _stats["retry_failed"] += 1
        elif is_retry:
            sys.stderr.write("[ar] [OK] retry succeeded (error cleared)\n")
            with _stats_lock:
                _stats["retry_success"] += 1
            _reset_block_counter(model)

        sys.stderr.write(
            f"[ar] ERROR {e.code}: "
            f"{err_body.decode(errors='replace')[:500]}\n"
        )
        self.send_response(e.code)
        for k, v in e.headers.items():
            if k.lower() not in ("transfer-encoding", "connection"):
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(err_body)

    # ------ Logging ------

    def log_message(self, format, *args):
        sys.stderr.write(f"[ar] {args[0]} -> {args[1]}\n")


# ===================================================================
# Threaded HTTP Server
# ===================================================================


class ThreadedHTTPServer(http.server.HTTPServer):
    """Handle each request in a separate daemon thread."""

    def process_request(self, request, client_address):
        t = threading.Thread(
            target=self.process_request_thread,
            args=(request, client_address),
        )
        t.daemon = True
        t.start()

    def process_request_thread(self, request, client_address):
        try:
            self.finish_request(request, client_address)
        except Exception:
            self.handle_error(request, client_address)
        finally:
            self.shutdown_request(request)


# ===================================================================
# Entry point
# ===================================================================

if __name__ == "__main__":
    if not API_KEY:
        print(
            "ERROR: PROXY_UPSTREAM_API_KEY (or AGENTROUTER_API_KEY) is required.\n"
            "  Create a .env file next to this script with:\n"
            "    PROXY_UPSTREAM_API_KEY=your-api-key\n"
            "  Or set it in your environment:\n"
            "    Windows:  $env:PROXY_UPSTREAM_API_KEY=\"your-key\"\n"
            "    Linux:    export PROXY_UPSTREAM_API_KEY=\"your-key\"",
            file=sys.stderr,
        )
        sys.exit(1)

    if not UPSTREAM.startswith("https://") and os.environ.get("PROXY_ALLOW_INSECURE_UPSTREAM") != "1":
        print("ERROR: upstream must use HTTPS (set PROXY_ALLOW_INSECURE_UPSTREAM=1 only for local testing)", file=sys.stderr)
        sys.exit(1)

    if LISTEN_HOST not in {"127.0.0.1", "localhost", "::1"} and not PROXY_AUTH_TOKEN:
        print("ERROR: PROXY_AUTH_TOKEN is required when PROXY_LISTEN_HOST is not loopback", file=sys.stderr)
        sys.exit(1)

    fmt_str = FORMAT_MODE if FORMAT_MODE in ("openai", "anthropic") else "auto-detect"
    server = ThreadedHTTPServer((LISTEN_HOST, PORT), ProxyHandler)
    print(f"* provider proxy ::{LISTEN_HOST}:{PORT} -> {UPSTREAM}")
    print(f"  Content-block retry:      ENABLED")
    print(f"  System prompt injection:  {'ENABLED' if INJECT_PREAMBLE else 'DISABLED'}")
    print(f"  Payload format:           {fmt_str} (OpenAI + Anthropic)")
    print(f"  Anti-loop protection:     {MAX_CONSECUTIVE_BLOCKS} max retries")
    print(f"  SSE buffered reading:     {SSE_CHUNK_SIZE}b chunks")
    print(f"  Incoming auth:            {'ENABLED' if PROXY_AUTH_TOKEN else 'local-only'}")
    print(f"  Stats endpoint:           http://localhost:{PORT}/_stats")
    print(f"  Usage endpoint:           http://localhost:{PORT}/_usage")
    print(f"  Debug mode:               {'ON' if os.environ.get('AGENTROUTER_DEBUG') == '1' else 'OFF'}")
    print()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n*  Proxy stopped.")
        server.server_close()