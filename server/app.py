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
import re
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

BASE_DIR = Path(__file__).resolve().parent
USAGE_LOG = BASE_DIR / "usage.log"

# ---- Pricing (the "rent one from us" price list) -----------------------
# USD per 1M tokens (input, output), same defaults as the LocalBotz app's
# data/pricing.json so the client and the server agree. These are the
# providers' public list prices at the time of writing; the VPS owner
# can change any of them in the admin panel (Pricing) and the new price
# applies to later requests. Grok / Kimi / GLM are starting prices —
# confirm them in the provider's own docs before relying on them.
# Local models are always free and never appear here.
DEFAULT_PRICING_USD_PER_1M = {
    "claude-sonnet-4-5": (3.00, 15.00), "claude-opus-4-1": (15.00, 75.00),
    "gpt-4o": (2.50, 10.00), "gpt-4o-mini": (0.15, 0.60),
    "gemini-2.5-flash": (0.30, 2.50), "gemini-2.5-pro": (1.25, 10.00),
    "deepseek-chat": (0.27, 1.10), "deepseek-reasoner": (0.55, 2.19),
    "grok-4": (3.00, 15.00), "kimi-k2": (0.60, 2.50), "glm-4.5": (0.60, 2.20),
}
PRICING_FILE = BASE_DIR / "data" / "pricing.json"

def _load_pricing():
    """{currency, per_model: {model: {per_1m_input_usd, per_1m_output_usd}}}"""
    try:
        d = json.loads(PRICING_FILE.read_text(encoding="utf-8"))
        if isinstance(d, dict) and isinstance(d.get("per_model"), dict):
            return d
    except Exception:
        pass
    return {"currency": "USD",
            "per_model": {m: {"per_1m_input_usd": pin, "per_1m_output_usd": pout}
                          for m, (pin, pout) in DEFAULT_PRICING_USD_PER_1M.items()}}

def _save_pricing(d):
    PRICING_FILE.parent.mkdir(parents=True, exist_ok=True)
    PRICING_FILE.write_text(json.dumps(d, indent=2), encoding="utf-8")
    return d

def _price_for_model(model: str, pricing=None):
    pricing = pricing or _load_pricing()
    entry = (pricing.get("per_model") or {}).get(model) or {}
    return (float(entry.get("per_1m_input_usd", 0.0)),
            float(entry.get("per_1m_output_usd", 0.0)))

def _cost_usd(model: str, in_tokens: int, out_tokens: int, pricing=None):
    pin, pout = _price_for_model(model, pricing)
    return round(in_tokens * pin / 1_000_000 + out_tokens * pout / 1_000_000, 6)
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

# ---- User registration -------------------------------------------------
# Where users register: on this gateway, at POST /register (and the
# sign-up page GET /register). A user gives a name + email, the gateway
# creates their workspace and issues them their own token (returned once,
# shown on the page and saved by the LocalBotz app). Only the token's
# SHA-256 hash is stored, never the token itself.
# REGISTRATION_OPEN=true (default) lets anyone sign up; set it to false
# and only tokens you issue by hand (PREMIUM_API_TOKEN / PREMIUM_API_TOKENS)
# work. ADMIN_TOKEN guards the admin list/disable endpoints below.
REGISTRATION_OPEN = (os.getenv("REGISTRATION_OPEN", "true") or "true").strip().lower() in ("1", "true", "yes", "on")
REGISTRATION_DAILY_LIMIT = int(os.getenv("REGISTRATION_DAILY_LIMIT", "100") or 100)
ADMIN_TOKEN = (os.getenv("ADMIN_TOKEN") or "").strip()
USERS_FILE = BASE_DIR / "data" / "users.json"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

def _load_users():
    try:
        data = json.loads(USERS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []

def _save_users(users):
    USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
    USERS_FILE.write_text(json.dumps(users, indent=2), encoding="utf-8")

def _find_user_by_token(token: str):
    h = hashlib.sha256(token.encode()).hexdigest()
    for u in _load_users():
        if u.get("token_hash") == h:
            return u
    return None

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

def _log_usage(token: str, model: str, provider: str, usage: dict, workspace_id: str = "", ip: str = ""):
    try:
        in_tok = int((usage or {}).get("input_tokens")
                     or (usage or {}).get("prompt_tokens") or 0)
        out_tok = int((usage or {}).get("output_tokens")
                      or (usage or {}).get("completion_tokens") or 0)
        entry = {"ts": int(time.time()), "token_hash": _token_hash(token),
                 "workspace_id": workspace_id or "",
                 "ip": ip or "",
                 "model": model, "provider": provider,
                 "cost_usd": _cost_usd(model, in_tok, out_tok),
                 "input_tokens": in_tok, "output_tokens": out_tok}
        with USAGE_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # Usage logging must never break a chat reply.

def _auth(request: Request):
    """Require Authorization: Bearer <token>. Accepts the master token(s)
    from .env AND any per-user token issued by /register. Returns
    (token, workspace_id) — workspace_id is "master" for master tokens,
    or the user's workspace id for registered users."""
    auth = request.headers.get("authorization") or ""
    if not auth.lower().startswith("bearer "):
        raise HTTPException(401, "Missing Authorization: Bearer token. Register at /register or ask the VPS owner for a premium token.")
    token = auth[7:].strip()
    if token in VALID_TOKENS:
        return token, "master"
    user = _find_user_by_token(token)
    if user and user.get("status") == "active":
        return token, user.get("workspace_id", "")
    if user:
        raise HTTPException(403, "This premium account is disabled. Contact the VPS owner.")
    if not VALID_TOKENS:
        raise HTTPException(503, "Premium gateway is not configured: PREMIUM_API_TOKEN is not set in the server .env.")
    raise HTTPException(401, "Invalid premium token. Register at /register or ask the VPS owner for a premium token.")

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
    _auth(request)  # token, workspace_id

@app.get("/v1/pricing")
def public_pricing():
    # No auth: the price list is public, so users can see what renting
    # costs before they register. Never includes keys or tokens.
    pricing = _load_pricing()
    return {"currency": pricing.get("currency", "USD"),
            "models": [{"id": m, "object": "model", "owned_by": _owner_of(m),
                        "per_1m_input_usd": (pricing["per_model"].get(m) or {}).get("per_1m_input_usd", 0.0),
                        "per_1m_output_usd": (pricing["per_model"].get(m) or {}).get("per_1m_output_usd", 0.0)}
                       for m in PREMIUM_MODELS],
            "note": "Prices are USD per 1M tokens. Local models are always free."}
    return {"object": "list",
            "data": [{"id": m, "object": "model", "created": 0,
                      "owned_by": _owner_of(m)} for m in PREMIUM_MODELS]}


# ---------- registration ----------
# Where users register: POST /register (JSON) or the sign-up page
# GET /register. Both also work under /v1/ for clients whose base URL
# already ends in /v1.
REGISTER_PAGE = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Register — LocalBotz Premium</title>
<style>body{font-family:system-ui,sans-serif;max-width:520px;margin:60px auto;padding:0 20px;color:#1f1b2e;line-height:1.6}
h1{font-size:28px}label{display:block;font-weight:700;margin:14px 0 4px}
input{width:100%;padding:12px;border:1px solid #ccc;border-radius:10px;font-size:16px}
button{margin-top:18px;background:linear-gradient(90deg,#ec2a8a,#7c3aed);color:#fff;border:0;border-radius:999px;padding:14px 26px;font-size:17px;font-weight:700;cursor:pointer}
#out{margin-top:20px;padding:16px;border-radius:12px;background:#f0fdf4;border:1px solid #bbf7d0;display:none;word-break:break-all}
code{background:#f3f0fa;padding:2px 6px;border-radius:6px}</style></head><body>
<h1>Register for LocalBotz Premium</h1>
<p>Sign up to use premium models (Claude, GPT, Gemini) from this server.
Your provider keys stay on the server — you only get a token, which you
paste into the LocalBotz app under Settings &gt; Connectors &gt; VPS Premium.</p>
<form id="f"><label>Your name</label><input id="name" required>
<label>Email</label><input id="email" type="email" required>
<button type="submit">Register</button></form>
<div id="out"></div>
<script>document.getElementById('f').onsubmit=async(e)=>{e.preventDefault();
const r=await fetch('/register',{method:'POST',headers:{'content-type':'application/json'},
body:JSON.stringify({name:document.getElementById('name').value,email:document.getElementById('email').value})});
const d=await r.json();const o=document.getElementById('out');o.style.display='block';
if(!r.ok){o.style.background='#fef2f2';o.style.borderColor='#fecaca';o.textContent=d.detail||'Registration failed.';return;}
o.innerHTML='Registered! Your workspace is <code>'+d.workspace_id+'</code>.<br>Your token (shown once — copy it now):<br><code>'+d.token+'</code><br><br>In the LocalBotz app, go to Settings &gt; Connectors &gt; VPS Premium, paste this token, and save.';};</script>
</body></html>"""

@app.get("/register")
@app.get("/v1/register")
def register_page():
    from fastapi.responses import HTMLResponse
    if not REGISTRATION_OPEN:
        return HTMLResponse("<h1>Registration is closed</h1><p>Ask the VPS owner for a premium token.</p>", status_code=403)
    return HTMLResponse(REGISTER_PAGE)

@app.post("/register")
@app.post("/v1/register")
async def register(request: Request):
    if not REGISTRATION_OPEN:
        raise HTTPException(403, "Registration is closed. Ask the VPS owner for a premium token.")
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Request body must be valid JSON.")
    name = (body.get("name") or "").strip()
    email = (body.get("email") or "").strip().lower()
    if not name:
        raise HTTPException(400, "Name is required.")
    if not EMAIL_RE.match(email):
        raise HTTPException(400, "A valid email address is required.")
    users = _load_users()
    if any(u.get("email") == email for u in users):
        raise HTTPException(409, "This email is already registered. If you lost your token, ask the VPS owner for a new one.")
    today = datetime.now(timezone.utc).date().isoformat()
    if sum(1 for u in users if (u.get("created") or "")[:10] == today) >= REGISTRATION_DAILY_LIMIT:
        raise HTTPException(429, "Registration limit reached for today. Try again tomorrow.")
    token = "lbx_" + secrets.token_urlsafe(32)
    workspace_id = "ws_" + secrets.token_hex(4)
    users.append({"workspace_id": workspace_id, "name": name, "email": email,
                  "token_hash": hashlib.sha256(token.encode()).hexdigest(),
                  "status": "active", "created": datetime.now(timezone.utc).isoformat()})
    _save_users(users)
    # The token is returned ONCE here and never stored in plain text.
    return {"workspace_id": workspace_id, "email": email,
            "token": token,
            "note": "Save this token now — it is shown once. Paste it in the LocalBotz app under Settings > Connectors > VPS Premium."}

def _require_admin(request: Request):
    if not ADMIN_TOKEN:
        raise HTTPException(503, "ADMIN_TOKEN is not set in the server .env.")
    if (request.headers.get("x-admin-token") or "") != ADMIN_TOKEN:
        raise HTTPException(401, "Admin token required (X-Admin-Token header).")

@app.get("/admin/users")
def admin_list_users(request: Request):
    _require_admin(request)
    return [{"workspace_id": u.get("workspace_id"), "name": u.get("name"),
             "email": u.get("email"), "status": u.get("status"),
             "created": u.get("created")} for u in _load_users()]

@app.post("/admin/users/{workspace_id}/disable")
def admin_disable_user(workspace_id: str, request: Request):
    _require_admin(request)
    users = _load_users()
    for u in users:
        if u.get("workspace_id") == workspace_id:
            u["status"] = "disabled"
            _save_users(users)
            return {"workspace_id": workspace_id, "status": "disabled"}
    raise HTTPException(404, "No such workspace.")

@app.post("/admin/users/{workspace_id}/enable")
def admin_enable_user(workspace_id: str, request: Request):
    _require_admin(request)
    users = _load_users()
    for u in users:
        if u.get("workspace_id") == workspace_id:
            u["status"] = "active"
            _save_users(users)
            return {"workspace_id": workspace_id, "status": "active"}
    raise HTTPException(404, "No such workspace.")


# ---------- installs, usage, admin panel ----------
# The admin panel (GET /admin, file server/admin.html) is where the VPS
# owner manages where the software is used and what it logs — like the
# admin side of abacus.ai. It shows: registered users/workspaces, every
# install that has phoned home (heartbeat), and the usage log.
# What is logged: per chat request — time, workspace, model, provider,
# input/output tokens, client IP. Message content is NEVER logged.
# Heartbeat (POST /v1/heartbeat, needs a valid token): install id, app
# version, platform/OS, first/last seen. No personal data, no file or
# chat content. Only sent when the client has VPS Premium configured.
INSTALLS_FILE = BASE_DIR / "data" / "installs.json"

def _load_installs():
    try:
        data = json.loads(INSTALLS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []

def _save_installs(installs):
    INSTALLS_FILE.parent.mkdir(parents=True, exist_ok=True)
    INSTALLS_FILE.write_text(json.dumps(installs, indent=2), encoding="utf-8")

def _load_usage():
    try:
        lines = USAGE_LOG.read_text(encoding="utf-8").splitlines()
        return [json.loads(x) for x in lines if x.strip()]
    except Exception:
        return []

@app.post("/v1/heartbeat")
async def heartbeat(request: Request):
    token, workspace_id = _auth(request)
    try:
        body = await request.json()
    except Exception:
        body = {}
    install_id = (body.get("install_id") or "").strip()
    if not install_id:
        raise HTTPException(400, "install_id is required.")
    now = datetime.now(timezone.utc).isoformat()
    installs = _load_installs()
    for inst in installs:
        if inst.get("install_id") == install_id:
            inst["last_seen"] = now
            inst["workspace_id"] = workspace_id
            inst["app_version"] = (body.get("app_version") or inst.get("app_version") or "")
            inst["platform"] = (body.get("platform") or inst.get("platform") or "")
            inst["os"] = (body.get("os") or inst.get("os") or "")
            inst["ip"] = (request.client.host if request.client else "") or inst.get("ip", "")
            _save_installs(installs)
            return {"install_id": install_id, "workspace_id": workspace_id, "status": "ok"}
    installs.append({"install_id": install_id, "workspace_id": workspace_id,
                     "app_version": (body.get("app_version") or ""),
                     "platform": (body.get("platform") or ""),
                     "os": (body.get("os") or ""),
                     "ip": (request.client.host if request.client else ""),
                     "first_seen": now, "last_seen": now})
    _save_installs(installs)
    return {"install_id": install_id, "workspace_id": workspace_id, "status": "ok"}

@app.get("/admin")
def admin_panel():
    from fastapi.responses import HTMLResponse, FileResponse
    page = BASE_DIR / "admin.html"
    if page.exists():
        return FileResponse(page, media_type="text/html")
    return HTMLResponse("<h1>Admin panel</h1><p>admin.html is missing on this server.</p>", status_code=404)

@app.get("/admin/stats")
def admin_stats(request: Request):
    _require_admin(request)
    users = _load_users()
    installs = _load_installs()
    usage = _load_usage()
    now = int(time.time())
    day_ago = now - 86400
    per_model, per_workspace = {}, {}
    in_tok = out_tok = 0
    for u in usage:
        per_model[u.get("model", "?")] = per_model.get(u.get("model", "?"), 0) + 1
        ws = u.get("workspace_id") or "master"
        per_workspace[ws] = per_workspace.get(ws, 0) + 1
        in_tok += int(u.get("input_tokens") or 0)
        out_tok += int(u.get("output_tokens") or 0)
    return {"users_total": len(users),
            "users_active": sum(1 for u in users if u.get("status") == "active"),
            "users_disabled": sum(1 for u in users if u.get("status") != "active"),
            "installs_total": len(installs),
            "installs_last_24h": sum(1 for i in installs
                                     if i.get("last_seen", "") >= datetime.fromtimestamp(day_ago, timezone.utc).isoformat()),
            "requests_total": len(usage),
            "requests_last_24h": sum(1 for u in usage if int(u.get("ts") or 0) >= day_ago),
            "input_tokens_total": in_tok, "output_tokens_total": out_tok,
            "per_model": per_model, "per_workspace": per_workspace,
            "registration_open": REGISTRATION_OPEN,
            "premium_models": PREMIUM_MODELS}

@app.get("/admin/installs")
def admin_installs(request: Request):
    _require_admin(request)
    return sorted(_load_installs(), key=lambda i: i.get("last_seen", ""), reverse=True)

@app.get("/admin/usage")
def admin_usage(request: Request, limit: int = 100):
    _require_admin(request)
    entries = _load_usage()
    entries.sort(key=lambda u: int(u.get("ts") or 0), reverse=True)
    return entries[:max(1, min(int(limit or 100), 500))]

@app.get("/admin/pricing")
def admin_get_pricing(request: Request):
    _require_admin(request)
    return _load_pricing()

@app.post("/admin/pricing")
async def admin_set_pricing(request: Request):
    _require_admin(request)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Request body must be valid JSON.")
    pricing = _load_pricing()
    per_model = body.get("per_model") or {}
    if not isinstance(per_model, dict):
        raise HTTPException(400, "per_model must be an object of model -> prices.")
    for model, entry in per_model.items():
        if not isinstance(entry, dict):
            continue
        pricing.setdefault("per_model", {})[model] = {
            "per_1m_input_usd": float(entry.get("per_1m_input_usd", 0.0)),
            "per_1m_output_usd": float(entry.get("per_1m_output_usd", 0.0))}
    if body.get("currency"):
        pricing["currency"] = str(body["currency"])[:8]
    return _save_pricing(pricing)

@app.get("/admin/revenue")
def admin_revenue(request: Request):
    _require_admin(request)
    users = {u.get("workspace_id"): u for u in _load_users()}
    usage = _load_usage()
    total_cost = 0.0
    per_workspace, per_model, per_day = {}, {}, {}
    for u in usage:
        cost = float(u.get("cost_usd") or 0.0)
        total_cost += cost
        ws = u.get("workspace_id") or "master"
        w = per_workspace.setdefault(ws, {"requests": 0, "input_tokens": 0,
                                          "output_tokens": 0, "cost_usd": 0.0})
        w["requests"] += 1
        w["input_tokens"] += int(u.get("input_tokens") or 0)
        w["output_tokens"] += int(u.get("output_tokens") or 0)
        w["cost_usd"] = round(w["cost_usd"] + cost, 6)
        m = per_model.setdefault(u.get("model", "?"), {"requests": 0, "cost_usd": 0.0})
        m["requests"] += 1
        m["cost_usd"] = round(m["cost_usd"] + cost, 6)
        day = datetime.fromtimestamp(int(u.get("ts") or 0), timezone.utc).date().isoformat()
        d = per_day.setdefault(day, {"requests": 0, "cost_usd": 0.0})
        d["requests"] += 1
        d["cost_usd"] = round(d["cost_usd"] + cost, 6)
    ws_list = []
    for ws_id, w in sorted(per_workspace.items(), key=lambda kv: -kv[1]["cost_usd"]):
        u = users.get(ws_id) or {}
        ws_list.append({"workspace_id": ws_id, "name": u.get("name", ""),
                        "email": u.get("email", ""), **w})
    return {"total_cost_usd": round(total_cost, 6),
            "requests_total": len(usage),
            "per_workspace": ws_list,
            "per_model": per_model,
            "per_day": dict(sorted(per_day.items(), reverse=True)[:14])}

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
    token, workspace_id = _auth(request)
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
    _log_usage(token, model, provider, result.get("usage"), workspace_id,
               ip=(request.client.host if request.client else ""))
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
