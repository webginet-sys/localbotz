"""
LocalBotz VPS Premium gateway — runs on Thomas's VPS.

What it is: a small FastAPI server that exposes an OpenAI-compatible API
(GET /v1/models, POST /v1/chat/completions) to LocalBotz clients, and
forwards each request to the real provider (Anthropic / OpenAI / Google /
OpenRouter) using keys that live ONLY here, in this server's .env.

Security model — read this before deploying:
- Clients NEVER hold provider API keys. They authenticate with a user
  token (PREMIUM_API_TOKEN) that Thomas issues. That token is not a
  provider key and cannot be used anywhere else.
- Provider keys are never returned to clients, never written to logs,
  and never appear in error messages. Errors name the provider and the
  HTTP status only.
- The gateway binds to 127.0.0.1 by default. Put nginx + HTTPS in front
  of it for public access (see README.md), or bind it to the Tailscale
  IP for private tailnet-only access.
- Usage is logged per token (JSON lines in usage.log): timestamp, a
  SHA-256 hash prefix of the token (never the token itself), model,
  provider, input/output tokens. No message content is logged.

Premium models: configured in .env as PREMIUM_MODELS (comma-separated).
Default: Claude Sonnet (claude-sonnet-4-5), GPT (gpt-4o, gpt-4o-mini),
Gemini (gemini-2.5-flash, gemini-2.5-pro). Add newer model ids there —
e.g. PREMIUM_MODELS=claude-sonnet-4-5,gpt-4o,gpt-4o-mini,gpt-5,gemini-2.5-flash,gemini-2.5-pro
— and restart. See models.json / docs/chatllm-model-reference.md for the
ChatLLM model list used as a reference: Grok, Kimi and GLM can be added
the same way (grok-4, kimi-k2, glm-4.5) once their provider keys are set
on the VPS. Routing is by model id prefix:
    claude-* -> Anthropic   gpt-* -> OpenAI   gemini-* -> Google
    deepseek-* -> DeepSeek   grok-* -> xAI   kimi-* -> Moonshot
    glm-* -> Zhipu
    anything else -> OpenRouter (if OPENROUTER_API_KEY is set)

Run:
    cp .env.example .env   # then fill in PREMIUM_API_TOKEN + provider keys
    pip install -r requirements.txt
    python app.py          # or: uvicorn app:app --host 127.0.0.1 --port 8001
"""
import hashlib
import json
import os
import time
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

BASE_DIR = Path(__file__).resolve().parent
USAGE_LOG = BASE_DIR / "usage.log"
APP_VERSION = "0.3.0"

# ---- .env loading (no extra dependency) ----
def _load_dotenv():
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

_load_dotenv()

PREMIUM_API_TOKEN = (os.getenv("PREMIUM_API_TOKEN") or "").strip()
EXTRA_TOKENS = [t.strip() for t in (os.getenv("PREMIUM_API_TOKENS") or "").split(",") if t.strip()]
VALID_TOKENS = {t for t in [PREMIUM_API_TOKEN, *EXTRA_TOKENS] if t}

# Premium models, configurable in .env — never hardcoded as the only list.
# Default: Claude Sonnet, GPT, Gemini.
DEFAULT_PREMIUM_MODELS = "claude-sonnet-4-5,gpt-4o,gpt-4o-mini,gemini-2.5-flash,gemini-2.5-pro"
PREMIUM_MODELS = [m.strip() for m in
                  (os.getenv("PREMIUM_MODELS") or DEFAULT_PREMIUM_MODELS).split(",")
                  if m.strip()]

# Model id -> provider + who owns it (for /v1/models responses).
MODEL_OWNERS = {"claude-": "anthropic", "gpt-": "openai", "gemini-": "google", "deepseek-": "deepseek", "grok-": "xai", "kimi-": "moonshot", "glm-": "zhipu"}

def _owner_of(model: str) -> str:
    for prefix, owner in MODEL_OWNERS.items():
        if model.startswith(prefix):
            return owner
    return "openrouter"

def _route(model: str):
    """Return (provider, base_url, key_env) for a model id, or raise 400."""
    if model.startswith("claude-"):
        return ("anthropic", "https://api.anthropic.com/v1/messages", "ANTHROPIC_API_KEY")
    if model.startswith("gpt-"):
        return ("openai", "https://api.openai.com/v1", "OPENAI_API_KEY")
    if model.startswith("gemini-"):
        return ("gemini", "https://generativelanguage.googleapis.com/v1beta/openai/", "GEMINI_API_KEY")
    if model.startswith("deepseek-"):
        return ("deepseek", "https://api.deepseek.com/v1", "DEEPSEEK_API_KEY")
    # Anything else goes to OpenRouter, if it is configured.
    return ("openrouter", "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY")

def _provider_key(key_env: str):
    return (os.getenv(key_env) or "").strip()

def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()[:12]

def _log_usage(token: str, model: str, provider: str, usage: dict):
    try:
        entry = {"ts": int(time.time()), "token_hash": _token_hash(token),
                 "model": model, "provider": provider,
                 "input_tokens": int((usage or {}).get("input_tokens")
                                     or (usage or {}).get("prompt_tokens") or 0),
                 "output_tokens": int((usage or {}).get("output_tokens")
                                      or (usage or {}).get("completion_tokens") or 0)}
        with USAGE_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # Usage logging must never break a chat reply.

def _auth(request: Request) -> str:
    """Require Authorization: Bearer <PREMIUM_API_TOKEN>. Returns the token."""
    if not VALID_TOKENS:
        raise HTTPException(503, "Premium gateway is not configured: PREMIUM_API_TOKEN is not set in the server .env.")
    auth = request.headers.get("authorization") or ""
    if not auth.lower().startswith("bearer "):
        raise HTTPException(401, "Missing Authorization: Bearer token. Ask the VPS owner for a premium token.")
    token = auth[7:].strip()
    if token not in VALID_TOKENS:
        raise HTTPException(401, "Invalid premium token.")
    return token

app = FastAPI(title="LocalBotz VPS Premium gateway", version=APP_VERSION)

@app.get("/health")
def health():
    # No auth: only reports that the gateway is up and how many premium
    # models are configured. Never reports keys or tokens.
    return {"status": "ok", "version": APP_VERSION,
            "premium_models": len(PREMIUM_MODELS),
            "configured": bool(VALID_TOKENS)}

@app.get("/v1/models")
def list_models(request: Request):
    _auth(request)
    return {"object": "list",
            "data": [{"id": m, "object": "model", "created": 0,
                      "owned_by": _owner_of(m)} for m in PREMIUM_MODELS]}

# ---------- provider clients ----------
async def _chat_openai_compatible(model: str, messages, tools, base_url: str,
                                  key: str, temperature: float = 0.7):
    payload = {"model": model, "messages": messages, "temperature": temperature}
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(f"{base_url.rstrip('/')}/chat/completions",
                         headers={"Authorization": f"Bearer {key}"},
                         json=payload)
    if r.status_code in (401, 403):
        raise HTTPException(502, "The VPS provider key was rejected by the provider. The VPS owner needs to check the key on the server.")
    if r.status_code >= 400:
        raise HTTPException(502, f"Provider request failed (HTTP {r.status_code}).")
    return r.json()

async def _chat_anthropic(model: str, messages, tools, key: str):
    # Translate OpenAI-style messages/tools to Claude's Messages API and
    # back. Tool use is best-effort: Claude's tool format is translated,
    # but a model that does not support tools returns plain text.
    system = ""
    anthropic_msgs, tool_results = [], []
    for m in messages or []:
        role = m.get("role")
        if role == "system":
            system = m.get("content") or ""
        elif role == "tool":
            tool_results.append({"type": "tool_result",
                                 "tool_use_id": m.get("tool_call_id", ""),
                                 "content": m.get("content") or ""})
        else:
            if tool_results:
                anthropic_msgs.append({"role": "user", "content": tool_results})
                tool_results = []
            blocks = []
            if m.get("content"):
                blocks.append({"type": "text", "text": m["content"]})
            for tc in m.get("tool_calls") or []:
                fn = tc.get("function", {})
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except Exception:
                    args = {}
                blocks.append({"type": "tool_use", "id": tc.get("id", ""),
                               "name": fn.get("name"), "input": args})
            anthropic_msgs.append({"role": role if role in ("user", "assistant") else "user",
                                   "content": blocks})
    if tool_results:
        anthropic_msgs.append({"role": "user", "content": tool_results})
    anthropic_tools = None
    if tools:
        anthropic_tools = [{"name": t["function"]["name"],
                            "description": t["function"]["description"],
                            "input_schema": t["function"]["parameters"]}
                           for t in tools]
    payload = {"model": model, "max_tokens": 4096, "system": system,
               "messages": anthropic_msgs}
    if anthropic_tools:
        payload["tools"] = anthropic_tools
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post("https://api.anthropic.com/v1/messages",
                         headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                                  "content-type": "application/json"},
                         json=payload)
    if r.status_code in (401, 403):
        raise HTTPException(502, "The VPS provider key was rejected by the provider. The VPS owner needs to check the key on the server.")
    if r.status_code >= 400:
        raise HTTPException(502, f"Provider request failed (HTTP {r.status_code}).")
    data = r.json()
    text, tool_calls = "", []
    for block in data.get("content") or []:
        if block.get("type") == "text":
            text += block.get("text", "")
        elif block.get("type") == "tool_use":
            tool_calls.append({"id": block.get("id", ""), "type": "function",
                               "function": {"name": block.get("name"),
                                            "arguments": json.dumps(block.get("input") or {})}})
    return {"id": data.get("id", ""), "object": "chat.completion",
            "created": int(time.time()), "model": model,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": text,
                                                 "tool_calls": tool_calls},
                         "finish_reason": data.get("stop_reason") or "stop"}],
            "usage": {"prompt_tokens": (data.get("usage") or {}).get("input_tokens", 0),
                      "completion_tokens": (data.get("usage") or {}).get("output_tokens", 0),
                      "total_tokens": ((data.get("usage") or {}).get("input_tokens", 0)
                                       + (data.get("usage") or {}).get("output_tokens", 0))}}

@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    token = _auth(request)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Request body must be valid JSON.")
    model = (body.get("model") or "").strip()
    if not model:
        raise HTTPException(400, "No model specified.")
    if body.get("stream"):
        raise HTTPException(400, "Streaming is not supported by the VPS gateway yet — send stream=false.")
    if model not in PREMIUM_MODELS:
        raise HTTPException(400,
                            f"Model '{model}' is not offered by this VPS. "
                            f"Available premium models: {', '.join(PREMIUM_MODELS)}.")
    provider, base_url, key_env = _route(model)
    key = _provider_key(key_env)
    if not key:
        raise HTTPException(502,
                            f"The VPS owner has not configured a key for {provider} "
                            f"({key_env} is not set on the server). "
                            "Ask the VPS owner, or pick another premium model.")
    messages = body.get("messages") or []
    tools = body.get("tools") or []
    temperature = float(body.get("temperature") or 0.7)
    if provider == "anthropic":
        result = await _chat_anthropic(model, messages, tools, key)
    else:
        result = await _chat_openai_compatible(model, messages, tools,
                                               base_url, key, temperature)
    _log_usage(token, model, provider, result.get("usage"))
    return JSONResponse(result)

if __name__ == "__main__":
    import uvicorn
    if not VALID_TOKENS:
        raise SystemExit("PREMIUM_API_TOKEN is not set. Copy server/.env.example to server/.env, "
                         "set PREMIUM_API_TOKEN (a long random token you issue to users), "
                         "add at least one provider key, and restart.")
    port = int(os.getenv("PORT", "8001"))
    host = os.getenv("HOST", "127.0.0.1")
    print(f"LocalBotz VPS Premium gateway on http://{host}:{port}  "
          f"models={len(PREMIUM_MODELS)} ({', '.join(PREMIUM_MODELS)})")
    uvicorn.run(app, host=host, port=port)
