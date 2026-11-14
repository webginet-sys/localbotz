"""
LocalBotz — a personal AI assistant that runs on your own computer.

Stack: Python 3.11+, FastAPI, plain HTML/JS UI, no Electron, no cloud.
Cross-platform: Windows, macOS and Linux — pathlib throughout, no OS-only
shell commands (file commands are implemented in Python, see run_command).
Model: any OpenAI-compatible local endpoint (LM Studio default, Ollama also works).
Browser automation: Playwright (sync API, Chromium).

Run:
    python app.py [--mock] [--port 8000]
    # or: uvicorn app:app --port 8000
Open http://localhost:8000

Providers (see .env.example - keys only from env/.env, never in code):
    Local-first default: lmstudio  http://localhost:1234/v1  model qwen3.5
    Also: ollama (local), openai, openrouter, groq, mistral, cerebras,
    anthropic (Claude, native Messages API), gemini (OpenAI-compatible),
    vps — "VPS Premium": premium models served by your own VPS gateway
    (see server/). The client never holds provider API keys for this
    provider, only a user token (VPS_API_TOKEN) issued by the VPS owner.
    Playwright is optional: without it the app still runs and browser
    tools reply with a clear "not installed" message.
    Each bot stores its own provider + model; pick them in the UI.
Env (see .env.example):
    PROVIDER / LLM_PROVIDER  default lmstudio
    LLM_BASE_URL  overrides the LM Studio base URL (default http://localhost:1234/v1)
    MODEL / LLM_MODEL  default qwen3.5 (Thomas's model in LM Studio).
                  If LM Studio shows a fuller identifier for it, e.g.
                  qwen/qwen3.5-..., copy that exact identifier into MODEL
                  (in .env or per bot in the UI) instead.
    ANTHROPIC_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY, OPENROUTER_API_KEY,
    GROQ_API_KEY, MISTRAL_API_KEY, CEREBRAS_API_KEY - all optional, online only.
    MOCK_MODE=1   test without a model
"""
import argparse
import json
import os
import platform
import shutil
import socket
import sys
import re
import shlex
import subprocess
import threading
import time
import uuid
from html.parser import HTMLParser
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CHATS_DIR = DATA_DIR / "chats"
MEMORY_DIR = DATA_DIR / "memory"
SHOTS_DIR = DATA_DIR / "screenshots"
WORKSPACE_DIR = BASE_DIR / "workspace"
BOTS_FILE = DATA_DIR / "bots.json"
STATIC_DIR = BASE_DIR / "static"
APP_VERSION = "0.3.0"
SETTINGS_FILE = DATA_DIR / "settings.json"

def _default_settings():
    return {"default_provider": (os.getenv("PROVIDER") or os.getenv("LLM_PROVIDER") or "lmstudio"),
            "default_model": (os.getenv("MODEL") or os.getenv("LLM_MODEL") or "qwen3.5"),
            "workspace_folder": "workspace", "theme": "light",
            "data_location": str(DATA_DIR), "app_version": APP_VERSION}

def load_settings():
    try:
        saved = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        if isinstance(saved, dict):
            merged = _default_settings(); merged.update(saved); return merged
    except Exception:
        pass
    return _default_settings()

def save_settings(settings):
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    return settings

SETTINGS = load_settings()
# Workspace folder is configurable in Settings > General (relative to the app folder).
_ws = (SETTINGS.get("workspace_folder") or "workspace").strip()
WORKSPACE_DIR = (BASE_DIR / _ws).resolve() if not Path(_ws).is_absolute() else Path(_ws)
if BASE_DIR.resolve() not in WORKSPACE_DIR.parents and WORKSPACE_DIR != BASE_DIR.resolve():
    WORKSPACE_DIR = BASE_DIR / "workspace"

for d in (DATA_DIR, CHATS_DIR, MEMORY_DIR, SHOTS_DIR, WORKSPACE_DIR):
    d.mkdir(parents=True, exist_ok=True)

def _apply_settings():
    # Re-read settings.json and apply live globals (called after a Settings save).
    global SETTINGS, WORKSPACE_DIR
    SETTINGS = load_settings()
    ws = (SETTINGS.get("workspace_folder") or "workspace").strip()
    cand = (BASE_DIR / ws).resolve() if not Path(ws).is_absolute() else Path(ws)
    if BASE_DIR.resolve() in cand.parents or cand == BASE_DIR.resolve():
        WORKSPACE_DIR = cand
        WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    return SETTINGS

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

# ---------- providers (v1, simple) ----------
# Local-first: LM Studio is the default and works fully offline, no key.
# Online providers are optional: they need an API key from env/.env only -
# keys are never hardcoded, never logged, and never sent to the client.
# kind "openai" = OpenAI-compatible /chat/completions; kind "anthropic" =
# Claude's native Messages API (tool calls are translated in llm_chat).
PROVIDERS = {
    # Order shown in the UI: local first, then DeepSeek, Claude,
    # OpenAI / Codex, Gemini, OpenRouter, then the rest, VPS Premium last.
    "lmstudio":  {"label": "LM Studio (local)", "kind": "openai",
                  "base_url": "http://localhost:1234/v1", "default_model": "qwen3.5",
                  "key_env": None, "env_base": "LMSTUDIO_BASE_URL"},
    "ollama":    {"label": "Ollama (local)", "kind": "openai",
                  "base_url": "http://localhost:11434/v1", "default_model": "qwen3.5",
                  "key_env": None, "env_base": "OLLAMA_BASE_URL"},
    "deepseek":  {"label": "DeepSeek", "kind": "openai",
                  "base_url": "https://api.deepseek.com/v1", "default_model": "deepseek-chat",
                  "key_env": "DEEPSEEK_API_KEY", "env_base": "DEEPSEEK_BASE_URL"},
    "anthropic": {"label": "Claude", "kind": "anthropic",
                  "base_url": "https://api.anthropic.com/v1/messages", "default_model": "claude-sonnet-4-5",
                  "key_env": "ANTHROPIC_API_KEY", "env_base": None,
                  "models_url": "https://api.anthropic.com/v1/models"},
    "openai":    {"label": "OpenAI / Codex", "kind": "openai",
                  "base_url": "https://api.openai.com/v1", "default_model": "gpt-4o-mini",
                  "key_env": "OPENAI_API_KEY", "env_base": "OPENAI_BASE_URL"},
    "gemini":    {"label": "Google Gemini (AI Studio)", "kind": "openai",
                  "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
                  "default_model": "gemini-2.5-flash",
                  "key_env": "GEMINI_API_KEY", "env_base": "GEMINI_BASE_URL"},
    "openrouter":{"label": "OpenRouter", "kind": "openai",
                  "base_url": "https://openrouter.ai/api/v1", "default_model": "openrouter/auto",
                  "key_env": "OPENROUTER_API_KEY", "env_base": "OPENROUTER_BASE_URL"},
    "groq":      {"label": "Groq", "kind": "openai",
                  "base_url": "https://api.groq.com/openai/v1", "default_model": "llama-3.3-70b-versatile",
                  "key_env": "GROQ_API_KEY", "env_base": "GROQ_BASE_URL"},
    "mistral":   {"label": "Mistral", "kind": "openai",
                  "base_url": "https://api.mistral.ai/v1", "default_model": "mistral-small-latest",
                  "key_env": "MISTRAL_API_KEY", "env_base": "MISTRAL_BASE_URL"},
    "cerebras":  {"label": "Cerebras", "kind": "openai",
                  "base_url": "https://api.cerebras.ai/v1", "default_model": "llama-3.3-70b",
                  "key_env": "CEREBRAS_API_KEY", "env_base": "CEREBRAS_BASE_URL"},
    # New providers from the reference model list (see models.json /
    # docs/model-reference.md). Reference-only:
    # shown only when their key is set; confirm the exact model ID in the
    # provider's own docs before use. No Git is needed to run any of this.
    "grok":      {"label": "Grok (xAI)", "kind": "openai",
                  "base_url": "https://api.x.ai/v1", "default_model": "grok-4",
                  "key_env": "XAI_API_KEY", "env_base": "XAI_BASE_URL"},
    "kimi":      {"label": "Kimi (Moonshot AI)", "kind": "openai",
                  "base_url": "https://api.moonshot.ai/v1", "default_model": "kimi-k2",
                  "key_env": "MOONSHOT_API_KEY", "env_base": "MOONSHOT_BASE_URL"},
    "glm":       {"label": "GLM (Zhipu AI)", "kind": "openai",
                  "base_url": "https://open.bigmodel.cn/api/paas/v4", "default_model": "glm-4.5",
                  "key_env": "ZHIPU_API_KEY", "env_base": "ZHIPU_BASE_URL"},
    # VPS Premium — premium models from Thomas's own VPS gateway (server/).
    # The gateway holds the real provider keys; this client only sends a
    # user token (VPS_API_TOKEN) that Thomas issues. Base URL + token are
    # set in Settings > Connectors > VPS Premium (or .env: VPS_BASE_URL /
    # VPS_API_TOKEN). Default model is filled in from the gateway's
    # GET /v1/models list when it is reachable.
    "vps":       {"label": "VPS Premium", "kind": "openai",
                  "base_url": "https://api.localbotz.io/v1", "default_model": "",
                  "key_env": "VPS_API_TOKEN", "env_base": "VPS_BASE_URL"},
}
VPS_PLACEHOLDER_URL = "https://api.localbotz.io/v1"

def get_vps_base_url() -> str:
    # VPS base URL: env first, then the value saved in Settings > Connectors
    # (connectors store, key "vps"), then the placeholder.
    url = (os.getenv("VPS_BASE_URL") or "").strip()
    if url:
        return url.rstrip("/")
    try:
        saved = _load_json(CONNECTORS_FILE, {}).get("vps", {})
        url = (saved.get("base_url") or "").strip()
        if url:
            return url.rstrip("/")
    except Exception:
        pass
    return VPS_PLACEHOLDER_URL

def vps_configured() -> bool:
    base = get_vps_base_url()
    return bool(os.getenv("VPS_API_TOKEN")) and base != VPS_PLACEHOLDER_URL \
        and base.startswith(("http://", "https://"))

# ---- VPS heartbeat: where this install is used -------------------------
# On startup, if VPS Premium is configured, the app tells the VPS
# gateway "this install exists": install id, app version, platform/OS.
# That is how the owner's admin panel (GET /admin on the VPS) knows
# where the software is used. No personal data, no chat or file content,
# no provider keys — and it never blocks startup (background thread,
# 10 s timeout, failures ignored). No VPS configured = nothing is sent.
INSTALL_FILE = DATA_DIR / "install.json"

def _get_install_id() -> str:
    try:
        data = _load_json(INSTALL_FILE, {})
        if data.get("install_id"):
            return str(data["install_id"])
    except Exception:
        pass
    install_id = "inst_" + uuid.uuid4().hex[:16]
    try:
        INSTALL_FILE.parent.mkdir(parents=True, exist_ok=True)
        INSTALL_FILE.write_text(json.dumps({"install_id": install_id}), encoding="utf-8")
    except Exception:
        pass
    return install_id

def _send_vps_heartbeat():
    try:
        if MOCK_MODE or not vps_configured():
            return
        base = get_vps_base_url()
        with _http_client(timeout=10, external=not _is_local_url(base)) as c:
            c.post(f"{base}/heartbeat",
                   headers={"Authorization": f"Bearer {os.getenv('VPS_API_TOKEN')}"},
                   json={"install_id": _get_install_id(), "app_version": APP_VERSION,
                         "platform": sys.platform,
                         "os": f"{platform.system()} {platform.release()}"})
    except Exception:
        pass  # Heartbeat must never break the app.

# NOTE: the startup hook that calls _send_vps_heartbeat lives just after
# `app = FastAPI(...)` below — `app` does not exist yet at this point in
# the file, so it cannot be registered here.

def playwright_available() -> bool:
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False
DEFAULT_PROVIDER = (os.getenv("PROVIDER") or os.getenv("LLM_PROVIDER") or SETTINGS.get("default_provider") or "lmstudio").lower()
if DEFAULT_PROVIDER not in PROVIDERS:
    DEFAULT_PROVIDER = "lmstudio"
# Legacy override: LLM_BASE_URL overrides the LM Studio base URL.
LLM_BASE_URL = (os.getenv("LLM_BASE_URL") or PROVIDERS["lmstudio"]["base_url"]).rstrip("/")

def get_provider_config(provider_id: str) -> dict:
    # Public config for a provider - never includes the API key value.
    pid = (provider_id or DEFAULT_PROVIDER).lower()
    spec = PROVIDERS.get(pid, PROVIDERS[DEFAULT_PROVIDER])
    pid = pid if pid in PROVIDERS else DEFAULT_PROVIDER
    base = os.getenv(spec["env_base"]) if spec.get("env_base") else None
    if pid == "lmstudio" and os.getenv("LLM_BASE_URL"):
        base = os.getenv("LLM_BASE_URL")
    if pid == "vps":
        base = get_vps_base_url()
    base = (base or spec["base_url"]).rstrip("/")
    key_env = spec.get("key_env")
    if pid == "vps":
        configured = vps_configured()
    else:
        configured = (not key_env) or bool(os.getenv(key_env))
    return {"id": pid, "label": spec["label"], "kind": spec["kind"],
            "base_url": base, "default_model": spec["default_model"],
            "key_env": key_env, "requires_key": bool(key_env),
            "configured": configured,
            "models_url": spec.get("models_url")}

def _provider_api_key(provider_id: str):
    cfg = get_provider_config(provider_id)
    return os.getenv(cfg["key_env"]) if cfg.get("key_env") else None

def _provider_name(base_url: str) -> str:
    # Kept for log lines: map a base URL back to a provider label.
    for cfg in (get_provider_config(pid) for pid in PROVIDERS):
        if cfg["base_url"] == base_url:
            return cfg["label"]
    return "Local LLM"

# Default model (single place): Thomas's Qwen3.5 in LM Studio.
# Override with MODEL / LLM_MODEL in .env, or per bot in the UI.
# If LM Studio shows a fuller identifier (e.g. qwen/qwen3.5-...), use that
# exact identifier instead - every other code path uses this variable.
DEFAULT_MODEL = (os.getenv("MODEL") or os.getenv("LLM_MODEL") or os.getenv("OLLAMA_MODEL")
                 or SETTINGS.get("default_model")
                 or PROVIDERS[DEFAULT_PROVIDER]["default_model"])
MOCK_MODE = os.getenv("MOCK_MODE", "").lower() in ("1", "true", "yes")

TEMPLATES = {
    "chief_of_staff": {
        "name": "Chief of Staff",
        "instructions": (
            "You are a Chief of Staff personal assistant. Help plan the day, "
            "draft emails and messages, track follow-ups, remember preferences, "
            "and summarise information clearly. Be concise, proactive, and ask "
            "a clarifying question when a request is ambiguous. "
            "Use the browser and files tools when you need current information "
            "or to read/write notes in the workspace."
        ),
    },
    "research_scout": {
        "name": "Research Scout",
        "instructions": (
            "You are a Research Scout. Search the web, open pages, read them, "
            "and produce short cited reports: key facts, sources (URLs), and "
            "what is still uncertain. Prefer primary sources. Save longer "
            "findings to a file in the workspace when asked. Be honest about "
            "what you could not verify."
        ),
    },
}

TOOL_DEFS = [
    {"type": "function", "function": {"name": "web_search", "description": "Search the web (DuckDuckGo) and return top results with titles, URLs and snippets.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "browser_search", "description": "Alias of web_search: search the web and return top results.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "browser_open", "description": "Open a URL in the browser.", "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}},
    {"type": "function", "function": {"name": "browser_read", "description": "Get the visible text of the currently open browser page.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "browser_screenshot", "description": "Screenshot the current browser page, save it, and return its path.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "browser_click", "description": "Click an element on the current page, by CSS selector.", "parameters": {"type": "object", "properties": {"selector": {"type": "string"}}, "required": ["selector"]}}},
    {"type": "function", "function": {"name": "browser_type", "description": "Type text into an element on the current page, by CSS selector.", "parameters": {"type": "object", "properties": {"selector": {"type": "string"}, "text": {"type": "string"}}, "required": ["selector", "text"]}}},
    {"type": "function", "function": {"name": "list_files", "description": "List files in the workspace folder (relative path, default '.').", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "read_file", "description": "Read a file in the workspace folder (relative path).", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "write_file", "description": "Write content to a file in the workspace folder (relative path). Creates parent folders.", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}}},
    {"type": "function", "function": {"name": "run_command", "description": "Run a safe allowlisted command in the workspace folder (30s timeout). Works the same on Windows, macOS and Linux: ls/dir, pwd, echo, cat/type, head, tail, wc, grep, find, python, node, git, mkdir, date.", "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}},
]

# ---------- storage helpers ----------
def _load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default

def _save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

def load_bots():
    bots = _load_json(BOTS_FILE, None)
    if bots is None:
        bots = [
            {"id": "chief-of-staff", "name": "Chief of Staff", "template": "chief_of_staff",
             "instructions": TEMPLATES["chief_of_staff"]["instructions"],
             "provider": DEFAULT_PROVIDER, "model": DEFAULT_MODEL,
             "created_at": int(time.time())},
            {"id": "research-scout", "name": "Research Scout", "template": "research_scout",
             "instructions": TEMPLATES["research_scout"]["instructions"],
             "provider": DEFAULT_PROVIDER, "model": DEFAULT_MODEL,
             "created_at": int(time.time())},
        ]
        _save_json(BOTS_FILE, bots)
    # Migration: bots created before providers existed get the default.
    for b in bots:
        b.setdefault("provider", DEFAULT_PROVIDER)
        if b["provider"] not in PROVIDERS:
            b["provider"] = DEFAULT_PROVIDER
        b.setdefault("model", PROVIDERS[b["provider"]]["default_model"])
    return bots

def save_bots(bots):
    _save_json(BOTS_FILE, bots)

def get_bot(bot_id: str):
    for b in load_bots():
        if b["id"] == bot_id:
            return b
    return None

def chat_path(bot_id: str) -> Path:
    return CHATS_DIR / f"{bot_id}.json"

def load_chat(bot_id: str):
    return _load_json(chat_path(bot_id), [])

def save_chat(bot_id: str, messages):
    _save_json(chat_path(bot_id), messages)

def memory_path(bot_id: str) -> Path:
    return MEMORY_DIR / f"{bot_id}.json"

def load_memory(bot_id: str):
    return _load_json(memory_path(bot_id), {"facts": []})

def save_memory(bot_id: str, mem):
    _save_json(memory_path(bot_id), mem)

# ---------- web search (DuckDuckGo HTML, no API key) ----------
class _DDGParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.results, self._cur, self._in_result, self._field = [], None, False, None
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "a" and "result__a" in a.get("class", ""):
            self._cur = {"title": "", "url": a.get("href", ""), "snippet": ""}
            self._in_result, self._field = True, "title"
        elif self._in_result and tag == "a" and "result__snippet" in a.get("class", ""):
            self._field = "snippet"
    def handle_data(self, data):
        if self._in_result and self._cur is not None and self._field:
            self._cur[self._field] += data.strip() + " "
    def handle_endtag(self, tag):
        if tag == "a" and self._in_result and self._field == "snippet":
            self.results.append({k: v.strip() for k, v in self._cur.items()})
            self._cur, self._in_result, self._field = None, False, None

def tool_web_search(query: str) -> str:
    last_error = ""
    try:
        with _http_client(timeout=15, external=True) as _c:
            r = _c.get("https://html.duckduckgo.com/html/",
                       params={"q": query}, headers={"User-Agent": "Mozilla/5.0"},
                       follow_redirects=True)
        r.raise_for_status()
        p = _DDGParser(); p.feed(r.text)
        results = p.results[:5]
        if not results:
            # Fallback: strip links from raw HTML
            links = re.findall(r'result__a[^>]*href="([^"]+)"[^>]*>([^<]+)', r.text)[:5]
            results = [{"title": t.strip(), "url": u, "snippet": ""} for u, t in links]
        if results:
            return "\n".join(f"{i+1}. {x['title']} — {x['url']}\n   {x.get('snippet','')}".strip()
                             for i, x in enumerate(results))
    except Exception as e:
        last_error = str(e)
    # Fallback: DuckDuckGo instant-answer JSON API (no HTML scraping).
    try:
        with _http_client(timeout=15, external=True) as _c:
            r = _c.get("https://api.duckduckgo.com/",
                       params={"q": query, "format": "json", "no_html": "1"})
            data = r.json()
        topics = []
        if data.get("AbstractText"):
            topics.append({"title": data.get("Heading") or query, "url": data.get("AbstractURL") or "",
                           "snippet": data["AbstractText"]})
        for item in (data.get("RelatedTopics") or [])[:5]:
            if isinstance(item, dict) and item.get("Text"):
                topics.append({"title": item.get("Text", "")[:80], "url": item.get("FirstURL", ""),
                               "snippet": item.get("Text", "")})
        if topics:
            return "\n".join(f"{i+1}. {x['title']} — {x['url']}\n   {x.get('snippet','')}".strip()
                             for i, x in enumerate(topics))
    except Exception as e:
        last_error = str(e)
    return (f"No web results for '{query}' from DuckDuckGo - it showed a bot challenge "
            "in this environment. Try browser_search instead, which opens the search "
            "in Chromium. (If this keeps happening on your computer, DuckDuckGo may be "
            "rate-limiting automated searches.)")

def tool_browser_search(query: str) -> str:
    # Real browser search: open DuckDuckGo in Chromium and read the results.
    try:
        from urllib.parse import quote_plus
        page = _get_page()
        page.goto(f"https://duckduckgo.com/?q={quote_plus(query)}", timeout=30000,
                  wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        text = page.inner_text("body")[:6000]
        if "bots use DuckDuckGo" in text or "challenge" in text.lower():
            return ("DuckDuckGo showed a bot challenge in the browser too - no results. "
                    "Try a different query, or wait and try again.")
        return text or "(search page had no visible text)"
    except Exception as e:
        return f"browser_search failed: {e}"

# ---------- browser (Playwright, one shared page) ----------
_browser_lock = threading.Lock()
_pw = _browser = _page = None

def _get_page():
    global _pw, _browser, _page
    with _browser_lock:
        if _page is not None:
            return _page
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:
            raise RuntimeError("Playwright is not installed (lightweight install). "
                               "Install browser support with: pip install -r requirements-browser.txt "
                               "&& playwright install chromium — or re-run the starter with --with-browser. "
                               "Everything else in the app works without it.") from e
        try:
            _pw = sync_playwright().start()
            # If a proxy is configured in the environment (e.g. a sandbox or
            # corporate proxy), pass it to Chromium; otherwise go direct.
            # On a normal home computer there is no proxy env var, so this is a no-op.
            launch_kwargs = {"headless": True}
            _proxy = os.getenv("HTTPS_PROXY") or os.getenv("https_proxy") or os.getenv("HTTP_PROXY")
            if _proxy:
                from urllib.parse import urlparse
                _u = urlparse(_proxy)
                _server = f"{_u.scheme}://{_u.hostname}:{_u.port or 3128}"
                launch_kwargs["proxy"] = {"server": _server}
                if _u.username:
                    from urllib.parse import unquote
                    launch_kwargs["proxy"]["username"] = unquote(_u.username)
                    launch_kwargs["proxy"]["password"] = unquote(_u.password or "")
            _browser = _pw.chromium.launch(**launch_kwargs)
            _page = _browser.new_page()
        except Exception as e:
            raise RuntimeError(f"Could not launch Chromium: {e}. Run: playwright install chromium") from e
        return _page

def tool_browser_open(url: str) -> str:
    try:
        page = _get_page()
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        return f"Opened {url} — title: {page.title()!r}"
    except Exception as e:
        return f"browser_open failed: {e}"

def tool_browser_read() -> str:
    try:
        page = _get_page()
        text = page.inner_text("body")
        return text[:8000] or "(page has no visible text)"
    except Exception as e:
        return f"browser_read failed: {e}"

def tool_browser_screenshot() -> str:
    try:
        page = _get_page()
        name = f"shot-{int(time.time())}.png"
        path = SHOTS_DIR / name
        page.screenshot(path=str(path))
        return f"Screenshot saved to data/screenshots/{name} (open /screenshots/{name})"
    except Exception as e:
        return f"browser_screenshot failed: {e}"

def tool_browser_click(selector: str) -> str:
    try:
        page = _get_page()
        page.click(selector, timeout=10000)
        return f"Clicked {selector!r} — now on {page.url} ({page.title()!r})"
    except Exception as e:
        return f"browser_click failed: {e}"

def tool_browser_type(selector: str, text: str) -> str:
    try:
        page = _get_page()
        page.fill(selector, text, timeout=10000)
        return f"Typed into {selector!r}"
    except Exception as e:
        return f"browser_type failed: {e}"

# ---------- files (restricted to ./workspace) ----------
def _safe_workspace_path(rel: str) -> Path:
    rel = (rel or ".").strip()
    if _is_blocked_path(rel):
        raise ValueError(f"Path {rel!r} is blocked in Settings > Permissions.")
    p = (WORKSPACE_DIR / rel).resolve()
    if p != WORKSPACE_DIR.resolve() and WORKSPACE_DIR.resolve() not in p.parents:
        raise ValueError(f"Path {rel!r} is outside the workspace folder.")
    return p

def tool_list_files(path: str = ".") -> str:
    try:
        p = _safe_workspace_path(path)
        if not p.exists():
            return f"No such path in workspace: {path}"
        if p.is_file():
            return str(p.relative_to(WORKSPACE_DIR))
        items = sorted(x.name + ("/" if x.is_dir() else "") for x in p.iterdir())
        return "\n".join(items) or "(empty)"
    except Exception as e:
        return f"list_files failed: {e}"

def tool_read_file(path: str) -> str:
    try:
        p = _safe_workspace_path(path)
        return p.read_text(encoding="utf-8")[:12000]
    except Exception as e:
        return f"read_file failed: {e}"

def tool_write_file(path: str, content: str) -> str:
    try:
        p = _safe_workspace_path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"Wrote {len(content)} chars to workspace/{path}"
    except Exception as e:
        return f"write_file failed: {e}"

# ---------- shell (cross-platform, allowlist, no shell=True, 30s) ----------
# Cross-platform by design: common file commands (ls/dir, cat/type, pwd,
# echo, head, tail, wc, grep, find, mkdir, date) are implemented in Python
# with pathlib, so they work identically on Windows, macOS and Linux.
# Only real programs (python, node, git, ...) are delegated to subprocess,
# and only if shutil.which() finds them on that OS. No shell=True, no
# OS-only shell builtins, no hardcoded OS paths (all paths are pathlib).
ALLOWED_CMDS = {"ls", "dir", "pwd", "echo", "cat", "type", "head", "tail", "wc",
                "grep", "find", "python3", "python", "node", "git", "mkdir",
                "date", "whoami", "tree"}
BLOCKED_CHARS = (";", "&&", "||", "|", "`", "$", "(", ")", ">", "<", "\n", "\r")
_BUILTIN_CMDS = {"ls", "dir", "pwd", "echo", "cat", "type", "head", "tail",
                 "wc", "grep", "find", "mkdir", "date"}
_EXTERNAL_CMDS = {"python3", "python", "node", "git", "whoami", "tree"}

def _run_builtin(cmd: str, args):
    """Python implementation of common file commands — same on every OS."""
    import shutil as _shutil
    if cmd in ("ls", "dir"):
        target = _safe_workspace_path(args[0] if args else ".")
        if target.is_file():
            return target.name
        return "\n".join(sorted(x.name + ("/" if x.is_dir() else "")
                                 for x in target.iterdir())) or "(empty)"
    if cmd == "pwd":
        return str(WORKSPACE_DIR)
    if cmd == "echo":
        return " ".join(args)
    if cmd in ("cat", "type"):
        if not args:
            return "cat needs a file path."
        return _safe_workspace_path(args[0]).read_text(encoding="utf-8")[:12000]
    if cmd in ("head", "tail"):
        if not args:
            return f"{cmd} needs a file path."
        lines = _safe_workspace_path(args[-1]).read_text(encoding="utf-8").splitlines()
        n = 10
        return "\n".join(lines[:n] if cmd == "head" else lines[-n:])
    if cmd == "wc":
        if not args:
            return "wc needs a file path."
        text = _safe_workspace_path(args[-1]).read_text(encoding="utf-8")
        return f"{len(text.splitlines())} lines, {len(text.split())} words, {len(text)} chars"
    if cmd == "grep":
        if len(args) < 2:
            return "grep needs a pattern and a file path."
        pattern, rel = args[0], args[1]
        hits = [ln for ln in _safe_workspace_path(rel).read_text(encoding="utf-8").splitlines()
                if pattern in ln]
        return "\n".join(hits)[:6000] or "(no matches)"
    if cmd == "find":
        rel = args[0] if args else "."
        root = _safe_workspace_path(rel)
        return "\n".join(str(p.relative_to(WORKSPACE_DIR))
                          for p in sorted(root.rglob("*")) if p != WORKSPACE_DIR) or "(empty)"
    if cmd == "mkdir":
        _safe_workspace_path(args[0] if args else "new-folder").mkdir(parents=True, exist_ok=True)
        return f"Created {args[0] if args else 'new-folder'}"
    if cmd == "date":
        from datetime import datetime
        return datetime.now().isoformat(timespec="seconds")
    raise ValueError(f"no builtin for {cmd}")

def tool_run_command(command: str) -> str:
    try:
        if any(c in command for c in BLOCKED_CHARS):
            return "run_command refused: shell metacharacters ( ; & | ` $ > < ) are not allowed."
        try:
            parts = shlex.split(command)
        except ValueError as e:
            return f"run_command failed to parse: {e}"
        if not parts or parts[0] not in ALLOWED_CMDS:
            return (f"run_command refused: '{parts[0] if parts else ''}' is not in the allowlist "
                    f"({', '.join(sorted(ALLOWED_CMDS))}).")
        cmd, args = parts[0], parts[1:]
        if cmd in _BUILTIN_CMDS:
            return _run_builtin(cmd, args) or "(no output)"
        # External programs only: must exist on this OS (shutil.which).
        import shutil
        if shutil.which(cmd) is None:
            return f"run_command failed: '{cmd}' is not installed on this computer."
        r = subprocess.run(parts, cwd=WORKSPACE_DIR, capture_output=True, text=True, timeout=30)
        out = (r.stdout + r.stderr)[:6000]
        return out or f"(exit {r.returncode}, no output)"
    except subprocess.TimeoutExpired:
        return "run_command timed out after 30s."
    except Exception as e:
        return f"run_command failed: {e}"

TOOLS = {
    "web_search": lambda a: tool_web_search(a.get("query", "")),
    "browser_search": lambda a: tool_browser_search(a.get("query", "")),
    "browser_open": lambda a: tool_browser_open(a.get("url", "")),
    "browser_read": lambda a: tool_browser_read(),
    "browser_screenshot": lambda a: tool_browser_screenshot(),
    "browser_click": lambda a: tool_browser_click(a.get("selector", "")),
    "browser_type": lambda a: tool_browser_type(a.get("selector", ""), a.get("text", "")),
    "list_files": lambda a: tool_list_files(a.get("path", ".")),
    "read_file": lambda a: tool_read_file(a.get("path", "")),
    "write_file": lambda a: tool_write_file(a.get("path", ""), a.get("content", "")),
    "run_command": lambda a: tool_run_command(a.get("command", "")),
}


# ---------- shared stores: Settings, Library and bots use the SAME files ----------
# One store per area, so Settings > Connectors and Library > Connectors (etc.)
# can never disagree. All files live under data/ (gitignored).
AVATARS = ["🤖", "👔", "🔬", "🌅", "📰", "📝", "💬", "👀"]
CONNECTORS_FILE = DATA_DIR / "connectors.json"
MCP_FILE = DATA_DIR / "mcp_servers.json"
SKILLS_FILE = DATA_DIR / "skills.json"
WALLET_FILE = DATA_DIR / "wallet.json"
PERMISSIONS_FILE = DATA_DIR / "permissions.json"
MESSAGING_FILE = DATA_DIR / "messaging.json"
DEVICES_FILE = DATA_DIR / "devices.json"
TEMPLATES_FILE = DATA_DIR / "templates.json"
SHIPPED_TEMPLATES_FILE = BASE_DIR / "templates.json"

SERVICE_CONNECTORS = [
    # Service connectors. "category" groups them in the UI. "token_env"
    # names the env var (saved in Secure store) holding the token/key
    # Test uses; connectors without a token_env need OAuth, so v1 is
    # config + setup instructions only and Test honestly reports
    # not_connected - never faked. "key_env" is a second credential
    # (Trello needs both an API key and a token).
    # --- Email & productivity ---
    {"id": "gmail", "label": "Gmail", "category": "Email & productivity", "auth": "OAuth", "setup": "Connect in the app with your Google account (OAuth). v1: config only - sign-in flow is not built yet."},
    {"id": "drive", "label": "Google Drive", "category": "Email & productivity", "auth": "OAuth", "setup": "Connect in the app with your Google account (OAuth). v1: config only - sign-in flow is not built yet."},
    {"id": "calendar", "label": "Google Calendar", "category": "Email & productivity", "auth": "OAuth", "setup": "Connect in the app with your Google account (OAuth). v1: config only - sign-in flow is not built yet."},
    {"id": "outlook", "label": "Outlook (Microsoft 365)", "category": "Email & productivity", "auth": "OAuth", "setup": "Connect in the app with your Microsoft account (OAuth, Microsoft Graph). v1: config only - sign-in flow is not built yet."},
    {"id": "dropbox", "label": "Dropbox", "category": "Email & productivity", "auth": "Access token", "token_env": "DROPBOX_TOKEN", "setup": "Create an app in the Dropbox App Console, generate an access token, add it in Secure store as DROPBOX_TOKEN, then enable here. Test calls get_current_account."},
    # --- Chat ---
    {"id": "slack", "label": "Slack", "category": "Chat", "auth": "OAuth / token", "token_env": "SLACK_BOT_TOKEN", "setup": "Create a Slack app, add a bot token (xoxb-...) in Secure store as SLACK_BOT_TOKEN, then enable here. Test calls auth.test."},
    {"id": "telegram", "label": "Telegram", "category": "Chat", "auth": "Bot token", "token_env": "TELEGRAM_BOT_TOKEN", "setup": "Talk to @BotFather on Telegram, create a bot to get a token, add it in Secure store as TELEGRAM_BOT_TOKEN, then enable here. Test calls getMe. (Inbound replies are set up under Messaging channels.)"},
    {"id": "discord", "label": "Discord", "category": "Chat", "auth": "Bot token", "token_env": "DISCORD_BOT_TOKEN", "setup": "Create an application in the Discord Developer Portal, add a bot and copy its token, add it in Secure store as DISCORD_BOT_TOKEN, then enable here. Test calls users/@me. (Inbound replies are set up under Messaging channels.)"},
    {"id": "whatsapp", "label": "WhatsApp", "category": "Chat", "auth": "Access token", "token_env": "WHATSAPP_ACCESS_TOKEN", "setup": "Create a WhatsApp Business app, add its access token in Secure store as WHATSAPP_ACCESS_TOKEN, then enable here. v1: config only - Test does not call Meta yet. (Inbound replies are set up under Messaging channels.)"},
    {"id": "teams", "label": "Microsoft Teams", "category": "Chat", "auth": "OAuth", "setup": "Connect in the app with your Microsoft account (OAuth, Microsoft Graph). v1: config only - sign-in flow is not built yet."},
    # --- Work ---
    {"id": "notion", "label": "Notion", "category": "Work", "auth": "Integration token", "token_env": "NOTION_TOKEN", "setup": "Create a Notion integration, add its token in Secure store as NOTION_TOKEN, share a page with it, then enable here. Test calls users/me."},
    {"id": "trello", "label": "Trello", "category": "Work", "auth": "API key + token", "token_env": "TRELLO_TOKEN", "key_env": "TRELLO_API_KEY", "setup": "Get an API key and a token from trello.com/app-key, add them in Secure store as TRELLO_API_KEY and TRELLO_TOKEN, then enable here. Test calls members/me."},
    {"id": "asana", "label": "Asana", "category": "Work", "auth": "OAuth", "setup": "Connect in the app with your Asana account (OAuth). v1: config only - sign-in flow is not built yet."},
    {"id": "jira", "label": "Jira", "category": "Work", "auth": "OAuth", "setup": "Connect in the app with your Atlassian account (OAuth). v1: config only - sign-in flow is not built yet."},
    {"id": "linear", "label": "Linear", "category": "Work", "auth": "OAuth", "setup": "Connect in the app with your Linear account (OAuth). v1: config only - sign-in flow is not built yet."},
    {"id": "airtable", "label": "Airtable", "category": "Work", "auth": "Personal access token", "token_env": "AIRTABLE_PAT", "setup": "Create a personal access token in your Airtable account settings, add it in Secure store as AIRTABLE_PAT, then enable here. Test lists your bases."},
    {"id": "sheets", "label": "Google Sheets", "category": "Work", "auth": "OAuth", "setup": "Connect in the app with your Google account (OAuth). v1: config only - sign-in flow is not built yet."},
    # --- Dev ---
    {"id": "github", "label": "GitHub", "category": "Dev", "auth": "Personal access token", "token_env": "GITHUB_TOKEN", "setup": "Create a fine-grained token on github.com, add it in Secure store as GITHUB_TOKEN, then enable here. Test calls /user."},
    {"id": "gitlab", "label": "GitLab", "category": "Dev", "auth": "Personal access token", "token_env": "GITLAB_TOKEN", "setup": "Create a personal access token on gitlab.com, add it in Secure store as GITLAB_TOKEN, then enable here. Test calls /user."},
    # --- CRM & sales ---
    {"id": "hubspot", "label": "HubSpot", "category": "CRM & sales", "auth": "Private app token", "token_env": "HUBSPOT_TOKEN", "setup": "Create a private app in HubSpot settings and copy its access token, add it in Secure store as HUBSPOT_TOKEN, then enable here. Test checks the token against HubSpot."},
    {"id": "salesforce", "label": "Salesforce", "category": "CRM & sales", "auth": "OAuth", "setup": "Connect in the app with your Salesforce account (OAuth). v1: config only - sign-in flow is not built yet."},
    # --- Payments ---
    {"id": "stripe", "label": "Stripe", "category": "Payments", "auth": "Secret key", "token_env": "STRIPE_SECRET_KEY", "setup": "Copy a secret key (sk_...) from your Stripe dashboard, add it in Secure store as STRIPE_SECRET_KEY, then enable here. Test calls /v1/account. Use a restricted key if you only need reads."},
    # --- Video & meetings ---
    {"id": "zoom", "label": "Zoom", "category": "Video & meetings", "auth": "OAuth access token", "token_env": "ZOOM_ACCESS_TOKEN", "setup": "Create a Server-to-Server OAuth app in the Zoom Marketplace, copy its access token, add it in Secure store as ZOOM_ACCESS_TOKEN, then enable here. Test calls users/me. Without a token it stays Not connected."},
    # --- Social & publishing ---
    {"id": "x", "label": "X (Twitter)", "category": "Social & publishing", "auth": "OAuth", "setup": "Connect in the app with your X account (OAuth 2.0). v1: config only - sign-in flow is not built yet."},
    {"id": "linkedin", "label": "LinkedIn", "category": "Social & publishing", "auth": "OAuth", "setup": "Connect in the app with your LinkedIn account (OAuth 2.0). v1: config only - sign-in flow is not built yet."},
]
BUILTIN_SKILLS = [
    {"id": "research", "name": "Research", "builtin": True, "enabled": True,
     "instructions": "Research skill: search the web, open and read pages, cite sources with URLs, and say what you could not verify."},
    {"id": "file-help", "name": "File help", "builtin": True, "enabled": True,
     "instructions": "File help skill: read, write and organise files in the workspace folder, and summarise files for the user."},
    {"id": "browser-help", "name": "Browser help", "builtin": True, "enabled": True,
     "instructions": "Browser help skill: use the browser tools to open pages, read visible text, click and type, and take screenshots."},
    {"id": "coding-help", "name": "Coding help", "builtin": True, "enabled": True,
     "instructions": "Coding help skill: inspect code, explain it, propose edits as files or diffs, and run safe commands to test."},
    {"id": "email-drafting", "name": "Email drafting", "builtin": True, "enabled": True,
     "instructions": "Email drafting skill: draft clear, polite emails in the user's voice, with a subject line; never claim to have sent anything."},
    {"id": "morning-brief", "name": "Morning Brief", "builtin": True, "enabled": True,
     "instructions": "Morning Brief skill: prepare a short briefing - today, top 3 priorities, and anything new that matters, under 300 words."},
    {"id": "project-graveyard", "name": "Project Graveyard", "builtin": True, "enabled": True,
     "instructions": "Project Graveyard skill: find the user's abandoned side projects in the workspace, work out why each one died, and help them finish the one worth going back to."},
    {"id": "first-reader", "name": "First Reader", "builtin": True, "enabled": True,
     "instructions": "First Reader skill: read a draft the way a real reader would, and report where they lose interest, where they stop reading, and what they remember afterwards — without rewriting a word."},
    {"id": "scope-creep", "name": "Scope Creep Detector", "builtin": True, "enabled": True,
     "instructions": "Scope Creep Detector skill: check whether a change grew beyond its stated intent, and recommend what to keep, split, or justify."},
    {"id": "commit-archaeologist", "name": "Commit Archaeologist", "builtin": True, "enabled": True,
     "instructions": "Commit Archaeologist skill: reconstruct why a file or code region exists from its history — the commit that introduced it, later edits, and co-changes — and explain the intent."},
    {"id": "dependency-doctor", "name": "Dependency Doctor", "builtin": True, "enabled": True,
     "instructions": "Dependency Doctor skill: check a dependency manifest for unpinned entries, obsolete backports, duplicate constraints and yanked releases, and say what to fix first."},
    {"id": "self-improving", "name": "Self-Improving Skill", "builtin": True, "enabled": True,
     "instructions": "Self-Improving skill: after a task, note what worked and what did not, and rewrite your own approach for next time — keep what helped, drop what wasted effort."},
]
MESSAGING_CHANNELS = {
    "whatsapp": {"label": "WhatsApp", "token_env": "WHATSAPP_ACCESS_TOKEN",
                 "setup": "1) Create a WhatsApp Business app / use the WhatsApp Business API. 2) Add its access token in Secure store (WHATSAPP_ACCESS_TOKEN). 3) Set the webhook URL in Meta's app dashboard to this app's /api/messaging/whatsapp/webhook. 4) Enable inbound replies here and add approved senders."},
    "telegram": {"label": "Telegram", "token_env": "TELEGRAM_BOT_TOKEN",
                 "setup": "1) Talk to @BotFather on Telegram and create a bot to get a token. 2) Add it in Secure store (TELEGRAM_BOT_TOKEN). 3) Enable this channel and inbound replies here, add approved senders (Telegram user id or username), and pick which bot answers. LocalBotz polls Telegram every few seconds — no webhook or public URL needed. Only approved senders get replies."},
    "discord": {"label": "Discord", "token_env": "DISCORD_BOT_TOKEN",
                "setup": "1) Create an application in the Discord Developer Portal, add a bot and copy its token. 2) Add it in Secure store (DISCORD_BOT_TOKEN). 3) Invite the bot to your server. 4) Enable inbound replies here and add approved senders."},
}
# Estimated prices, USD per 1M tokens (input, output). Local models cost 0.
PRICE_USD_PER_1M = {
    "gpt-4o-mini": (0.15, 0.60), "gpt-4o": (2.50, 10.00),
    "claude-sonnet-4-5": (3.00, 15.00), "claude-opus-4-1": (15.00, 75.00),
    "gemini-2.5-flash": (0.30, 2.50), "gemini-2.5-pro": (1.25, 10.00),
    "llama-3.3-70b-versatile": (0.59, 0.79), "llama-3.3-70b": (0.59, 0.79),
    "mistral-small-latest": (0.10, 0.30), "openrouter/auto": (0.0, 0.0),
}

def load_templates_list():
    shipped = []
    try:
        data = json.loads(SHIPPED_TEMPLATES_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list) and data:
            shipped = data
    except Exception:
        pass
    # Merge: a stored list from an older install keeps the user's edits,
    # but new shipped templates are added (otherwise an upgrade would
    # never show them).
    try:
        data = json.loads(TEMPLATES_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list) and data:
            have = {x.get("id") for x in data}
            missing = [x for x in shipped if x.get("id") not in have]
            if missing:
                data = data + missing
            return data
    except Exception:
        pass
    if shipped:
        return shipped
    return [{"id": k, "name": v["name"], "category": "personal_assistant",
             "description": "", "instructions": v["instructions"], "icon": "🤖", "avatar": "🤖",
             "provider": DEFAULT_PROVIDER, "model": DEFAULT_MODEL,
             "default_tools": [], "schedule": "on_demand", "featured": False}
            for k, v in TEMPLATES.items()]

def get_template(template_id: str):
    for t in load_templates_list():
        if t["id"] == template_id:
            return t
    return None

def load_connectors_store():
    d = _load_json(CONNECTORS_FILE, {})
    d.setdefault("providers", {})
    d.setdefault("services", {})
    d.setdefault("last_test", {})
    return d

def save_connectors_store(d):
    _save_json(CONNECTORS_FILE, d)
    return d

def provider_enabled(provider_id: str) -> bool:
    return load_connectors_store()["providers"].get(provider_id, {}).get("enabled", True)

def _provider_status(pid: str, store: dict):
    """Exact status vocabulary (Thomas's list), from the saved key + the
    last Test result in data/connectors.json (last_test: status, detail, ts):
      not_connected    — no key saved
      saved_not_checked — key saved, never tested
      connected        — last Test succeeded
      failed           — last Test failed (detail holds the error)
      not_checked      — local provider, never tested
    Returns (status, detail, last_test_dict). Never exposes a key."""
    cfg = get_provider_config(pid)
    last = (store.get("last_test") or {}).get(pid) or {}
    if cfg["requires_key"] and not cfg["configured"]:
        return "not_connected", "No key saved — add it in Settings > Secure store.", last
    if last:
        st = last.get("status", "")
        if st in ("connected", "reachable"):
            return "connected", last.get("detail", ""), last
        if st in ("failed", "offline"):
            return "failed", last.get("detail", ""), last
        return st, last.get("detail", ""), last
    if cfg["requires_key"]:
        return "saved_not_checked", "Key saved — press Test to check it.", last
    return "not_checked", "Not checked yet — press Test.", last

def load_mcp_servers():
    return _load_json(MCP_FILE, [])

def save_mcp_servers(servers):
    _save_json(MCP_FILE, servers)
    return servers

def load_skills():
    skills = _load_json(SKILLS_FILE, None)
    if skills is None:
        skills = [dict(x) for x in BUILTIN_SKILLS]
        _save_json(SKILLS_FILE, skills)
        return skills
    # Merge: new built-in skills from an upgrade are added to a stored
    # list from an older install (custom skills and edits are kept).
    have = {s.get("id") for s in skills}
    missing = [dict(x) for x in BUILTIN_SKILLS if x["id"] not in have]
    if missing:
        skills = skills + missing
        _save_json(SKILLS_FILE, skills)
    return skills

def save_skills(skills):
    _save_json(SKILLS_FILE, skills)
    return skills

def load_wallet():
    d = _load_json(WALLET_FILE, {})
    d.setdefault("monthly_budget_usd", 0.0)
    d.setdefault("alert_enabled", False)
    d.setdefault("usage", [])
    return d

def save_wallet(d):
    _save_json(WALLET_FILE, d)
    return d

def record_usage(provider_id: str, model: str, usage):
    if not usage:
        return
    try:
        inp = int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
        out = int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)
    except Exception:
        return
    price = PRICE_USD_PER_1M.get(model, (0.0, 0.0))
    cost = (inp * price[0] + out * price[1]) / 1_000_000
    w = load_wallet()
    w["usage"].append({"ts": int(time.time()), "provider": provider_id, "model": model,
                       "calls": 1, "input_tokens": inp, "output_tokens": out,
                       "est_cost_usd": round(cost, 6)})
    w["usage"] = w["usage"][-500:]
    save_wallet(w)

def load_permissions():
    d = _load_json(PERMISSIONS_FILE, {})
    d.setdefault("global", {"file_read": True, "file_write": True, "shell": True,
                            "browser": True, "web_search": True, "network": True})
    d.setdefault("tools", {t["function"]["name"]: True for t in TOOL_DEFS})
    d.setdefault("bots", {})
    d.setdefault("blocked_paths", [])
    return d

def save_permissions(d):
    _save_json(PERMISSIONS_FILE, d)
    return d

def load_messaging():
    d = _load_json(MESSAGING_FILE, {})
    for ch in MESSAGING_CHANNELS:
        d.setdefault(ch, {"enabled": False, "inbound_replies": False, "webhook": "",
                          "approved_senders": []})
    return d

def save_messaging(d):
    _save_json(MESSAGING_FILE, d)
    return d

def load_devices_extra():
    return _load_json(DEVICES_FILE, [])

def save_devices_extra(devices):
    _save_json(DEVICES_FILE, devices)
    return devices

def _mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "****"
    return key[:3] + "..." + key[-4:]

def _set_env_key(key_env: str, value: str):
    # Write one KEY=value line into .env (gitignored) and apply it live.
    # The value is never logged or returned.
    env_file = BASE_DIR / ".env"
    lines = env_file.read_text(encoding="utf-8").splitlines() if env_file.exists() else []
    out, found = [], False
    for line in lines:
        if line.strip().startswith(key_env + "="):
            out.append(key_env + "=" + value); found = True
        else:
            out.append(line)
    if not found:
        out.append(key_env + "=" + value)
    env_file.write_text("\n".join(out) + "\n", encoding="utf-8")
    os.environ[key_env] = value

def _delete_env_key(key_env: str):
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        lines = [ln for ln in env_file.read_text(encoding="utf-8").splitlines()
                 if not ln.strip().startswith(key_env + "=")]
        env_file.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    os.environ.pop(key_env, None)

def _check_chromium():
    # Playwright is optional (requirements-browser.txt). Without it the
    # app still runs; browser tools just report "not installed".
    if not playwright_available():
        return False, "Playwright is not installed - install it with: pip install -r requirements-browser.txt && playwright install chromium (or run start with --with-browser)"
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            exe = Path(pw.chromium.executable_path)
            return exe.exists(), str(exe)
    except Exception as e:
        return False, str(e)

def _is_blocked_path(rel: str) -> bool:
    rel = (rel or "").replace("\\", "/").strip("/")
    for blocked in load_permissions().get("blocked_paths", []):
        b = str(blocked).replace("\\", "/").strip("/")
        if b and (rel == b or rel.startswith(b.rstrip("/") + "/")):
            return True
    return False

_MUTATING_TOOLS = {"write_file", "run_command", "browser_click", "browser_type"}

def _tool_allowed(name: str, bot: dict):
    # Returns (allowed, reason). Enforces, in order: template/bot tool list,
    # global + per-bot tool toggles, category permissions, approval mode.
    perms = load_permissions()
    enabled_tools = bot.get("enabled_tools") or []
    if enabled_tools and name not in enabled_tools:
        return False, "tool not enabled for this bot (see its template / Tools)"
    if not perms.get("tools", {}).get(name, True):
        return False, "tool disabled globally (Library > Tools)"
    bot_perms = perms.get("bots", {}).get(bot.get("id", ""), {})
    if bot_perms.get("tools", {}).get(name) is False:
        return False, "tool disabled for this bot (Library > Tools)"
    g = perms.get("global", {})
    if name in ("read_file", "list_files") and not g.get("file_read", True):
        return False, "file reading is off (Settings > Permissions)"
    if name == "write_file" and not g.get("file_write", True):
        return False, "file writing is off (Settings > Permissions)"
    if name == "run_command" and not g.get("shell", True):
        return False, "shell commands are off (Settings > Permissions)"
    if name.startswith("browser_") and not g.get("browser", True):
        return False, "browser automation is off (Settings > Permissions)"
    if name in ("web_search", "browser_search") and not g.get("web_search", True):
        return False, "web search is off (Settings > Permissions)"
    if name in ("web_search", "browser_search", "browser_open", "browser_read") and not g.get("network", True):
        return False, "network access is off (Settings > Permissions)"
    if name in _MUTATING_TOOLS and bot_perms.get("approval_mode", "auto") == "ask":
        return False, "blocked by approval mode Ask - switch this bot to Auto/Full in Settings > Permissions to allow changes"
    return True, ""

def _execute_tool(name: str, args: dict, bot: dict):
    allowed, reason = _tool_allowed(name, bot)
    if not allowed:
        return "Tool blocked by permissions: " + reason, True
    fn = TOOLS.get(name)
    if not fn:
        return "Unknown tool: " + name, True
    return fn(args), False

def _skills_text_for_bot(bot: dict):
    skills = {s["id"]: s for s in load_skills()}
    wanted = bot.get("skills") or ["research", "file-help", "browser-help"]
    parts = [skills[sid]["instructions"] for sid in wanted if sid in skills and skills[sid].get("enabled", True)]
    return "\n".join(parts)

# ---------- model availability (live, not a fixed list) ----------
# Users can use whichever model is available right now:
#  - LM Studio: whatever GET {base}/v1/models returns (any local model)
#  - Ollama: whatever GET /api/tags returns
#  - VPS Premium: whatever the gateway's GET /v1/models returns
#  - Direct online providers: their known defaults, but only when an API
#    key is configured — otherwise "unavailable: missing key".
# A model the user typed (default Qwen3.5) is always the fallback when a
# list cannot be fetched; a list that *is* fetched is the truth.
KNOWN_DEFAULT_MODELS = {
    "deepseek": ["deepseek-chat", "deepseek-reasoner"],
    "anthropic": ["claude-sonnet-4-5", "claude-opus-4-1"],
    "openai": ["gpt-4o-mini", "gpt-4o", "gpt-5-codex", "codex-mini-latest"],
    "gemini": ["gemini-2.5-flash", "gemini-2.5-pro"],
    "openrouter": ["openrouter/auto"],
    "groq": ["llama-3.3-70b-versatile"],
    "mistral": ["mistral-small-latest"],
    "cerebras": ["llama-3.3-70b"],
    # From the reference model list (see models.json). Reference-only models:
    # only listed as usable when their key is set; confirm IDs in the
    # provider's own docs. Marketing names (Grok-4.7, etc.) are
    # NOT API IDs and are never sent to a provider.
    "grok": ["grok-4"],
    "kimi": ["kimi-k2"],
    "glm": ["glm-4.5"],
}

def _live_models_for_provider(provider_id: str, timeout: int = 5):
    """Return (models, source, error). source: live | defaults | fallback | unavailable.
    models is a list of model ids that can actually be used right now.
    Never raises; on failure returns ([], "unavailable", <reason>)."""
    cfg = get_provider_config(provider_id)
    pid = cfg["id"]
    if pid in ("lmstudio", "ollama"):
        # Local: ask the server what it actually has loaded/available.
        err = "local server not reachable"
        try:
            with _http_client(timeout=timeout, external=False) as c:
                r = c.get(f"{cfg['base_url']}/models")
            r.raise_for_status()
            models = [m.get("id") for m in (r.json().get("data") or [])
                      if isinstance(m, dict) and m.get("id")]
            if models:
                return models, "live", ""
        except Exception as e:
            err = str(e)
        if pid == "ollama":
            # Ollama's /v1/models is not always enabled; try /api/tags.
            try:
                with _http_client(timeout=timeout, external=False) as c:
                    r = c.get("http://localhost:11434/api/tags")
                r.raise_for_status()
                models = [m.get("name") for m in (r.json().get("models") or [])
                          if isinstance(m, dict) and m.get("name")]
                if models:
                    return models, "live", ""
            except Exception as e:
                err = str(e)
        # List could not be fetched: fall back to the typed default so the
        # user can still try it (the chat call itself will report if the
        # server is really down). Never block on a failed probe.
        return [cfg["default_model"]], "fallback", err
    if pid == "vps":
        if not vps_configured():
            return [], "unavailable", "VPS Premium is not configured - set the base URL and token in Settings > Connectors > VPS Premium."
        try:
            with _http_client(timeout=timeout, external=not _is_local_url(get_vps_base_url())) as c:
                r = c.get(f"{get_vps_base_url()}/models",
                          headers={"Authorization": f"Bearer {os.getenv('VPS_API_TOKEN')}"})
            if r.status_code == 401:
                return [], "unavailable", "VPS token rejected (HTTP 401) - check the token."
            r.raise_for_status()
            models = [m.get("id") for m in (r.json().get("data") or [])
                      if isinstance(m, dict) and m.get("id")]
            return models, "live", "" if models else "VPS gateway listed no models."
        except Exception as e:
            return [], "unavailable", f"VPS gateway unreachable: {e}"
    # Direct online providers: usable only when a key is configured.
    if cfg["requires_key"] and not cfg["configured"]:
        return [], "unavailable", f"missing key ({cfg['key_env']} is not set)"
    if pid == "anthropic" and cfg.get("configured"):
        try:
            with _http_client(timeout=timeout, external=True) as c:
                r = c.get(cfg.get("models_url") or "https://api.anthropic.com/v1/models",
                          headers={"x-api-key": _provider_api_key("anthropic"),
                                   "anthropic-version": "2023-06-01"})
            r.raise_for_status()
            models = [m.get("id") for m in (r.json().get("data") or [])
                      if isinstance(m, dict) and m.get("id")]
            if models:
                return models, "live", ""
        except Exception:
            pass  # fall through to known defaults below
    return list(KNOWN_DEFAULT_MODELS.get(pid, [cfg["default_model"]])), "defaults", ""

def models_available():
    """Probe every source live. Returns {sources, models} where sources is
    one entry per provider with status + reason, and models is the flat
    list of actually-usable models (provider, model, source label)."""
    sources, flat = [], []
    for pid in PROVIDERS:
        cfg = get_provider_config(pid)
        models, source, error = _live_models_for_provider(pid)
        available = bool(models) and source != "unavailable"
        sources.append({"provider": pid, "label": cfg["label"],
                        "status": "available" if available else "unavailable",
                        "source": source, "reason": "" if available else error,
                        "models": models if available else []})
        for m in (models if available else []):
            flat.append({"provider": pid, "provider_label": cfg["label"],
                         "model": m, "source": source})
    return {"sources": sources, "models": flat}

# ---------- LLM / providers ----------
def _is_local_url(url: str) -> bool:
    u = (url or "").lower()
    return "localhost" in u or "127.0.0.1" in u or "[::1]" in u

def _http_client(timeout=120, external: bool = False):
    # Local URLs go direct (no proxy). External URLs use the proxy from env
    # if one is set, with the system CA store (corporate/sandbox proxies
    # often use a CA that certifi does not know). trust_env is off because
    # httpx mis-parses bracketed IPv6 entries in NO_PROXY.
    if external:
        import ssl
        proxy = os.getenv("HTTPS_PROXY") or os.getenv("https_proxy") or None
        return httpx.Client(timeout=timeout, trust_env=False, proxy=proxy,
                            verify=ssl.create_default_context())
    return httpx.Client(timeout=timeout, trust_env=False, proxy=None)

def check_provider(provider_id: str, real: bool = False):
    # Returns (reachable, detail, configured). Never exposes a key.
    cfg = get_provider_config(provider_id)
    if MOCK_MODE and not real:
        return True, "mock mode - no real model needed", True
    if cfg["id"] == "vps" and not vps_configured():
        return False, ("VPS Premium is not configured - set the VPS base URL and "
                       "your token in Settings > Connectors > VPS Premium "
                       "(or VPS_BASE_URL / VPS_API_TOKEN in .env)."), False
    if cfg["requires_key"] and not cfg["configured"]:
        return False, f"API key not set - add {cfg['key_env']} to .env", False
    try:
        url = cfg.get("models_url") or f"{cfg['base_url']}/models"
        headers = {}
        key = _provider_api_key(cfg["id"])
        if key:
            headers["Authorization"] = f"Bearer {key}"
        if cfg["kind"] == "anthropic":
            headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
        with _http_client(timeout=5, external=not _is_local_url(url)) as _c:
            r = _c.get(url, headers=headers)
        if r.status_code == 401:
            return False, "API key rejected (HTTP 401) - check the key in .env", True
        return r.status_code < 500, f"HTTP {r.status_code}", True
    except Exception as e:
        return False, str(e), True

def check_llm(provider_id: str = None):
    # Backwards-compatible wrapper: (reachable, detail) for a provider.
    reachable, detail, _cfg = check_provider(provider_id or DEFAULT_PROVIDER)
    return reachable, detail

def _lmstudio_fallback_available(provider_id: str) -> bool:
    # Is the local fallback reachable, for a bot on another provider?
    if (provider_id or DEFAULT_PROVIDER) == "lmstudio" or MOCK_MODE:
        return False
    reachable, _d, _c = check_provider("lmstudio")
    return reachable

def _llm_chat_openai(messages, model: str, cfg: dict, api_key=None):
    # api_key: explicit key for this call (master key, or the tenant's BYOK
    # key). None means "use the master key from .env" (existing behaviour).
    headers = {}
    key = api_key if api_key is not None else _provider_api_key(cfg["id"])
    if key:
        headers["Authorization"] = f"Bearer {key}"
    with _http_client(timeout=120, external=not _is_local_url(cfg["base_url"])) as c:
        r = c.post(f"{cfg['base_url']}/chat/completions",
                   headers=headers,
                   json={"model": model, "messages": messages, "tools": TOOL_DEFS,
                         "tool_choice": "auto", "temperature": 0.7})
        r.raise_for_status()
        return r.json()

def _llm_chat_anthropic(messages, model: str, cfg: dict, api_key=None):
    # Translate OpenAI-style messages/tools to Claude's Messages API,
    # then translate the reply back to OpenAI shape so the tool loop
    # in run_agent works identically for every provider.
    key = api_key if api_key is not None else _provider_api_key("anthropic")
    if not key:
        raise ValueError("No Claude key available - Super Admin (master key) or this workspace (BYOK key) needs to add one.")
    system = ""
    anthropic_msgs = []
    tool_results = []  # consecutive tool messages merge into one user turn
    def flush_tools():
        nonlocal tool_results
        if tool_results:
            anthropic_msgs.append({"role": "user", "content": tool_results})
            tool_results = []
    for m in messages:
        role = m.get("role")
        if role == "system":
            system = m.get("content") or ""
        elif role == "tool":
            tool_results.append({"type": "tool_result", "tool_use_id": m.get("tool_call_id", ""),
                                 "content": m.get("content") or ""})
        else:
            flush_tools()
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
    flush_tools()
    tools = [{"name": t["function"]["name"], "description": t["function"]["description"],
              "input_schema": t["function"]["parameters"]} for t in TOOL_DEFS]
    with _http_client(timeout=120, external=True) as c:
        r = c.post(cfg["base_url"], headers={
                       "x-api-key": key, "anthropic-version": "2023-06-01",
                       "content-type": "application/json"},
                   json={"model": model, "max_tokens": 4096, "system": system,
                         "messages": anthropic_msgs, "tools": tools})
        r.raise_for_status()
        data = r.json()
    text, tool_calls = "", []
    for block in data.get("content") or []:
        if block.get("type") == "text":
            text += block.get("text", "")
        elif block.get("type") == "tool_use":
            tool_calls.append({"id": block.get("id", ""), "type": "function",
                               "function": {"name": block.get("name"),
                                            "arguments": json.dumps(block.get("input") or {})}})
    return {"choices": [{"message": {"role": "assistant", "content": text,
                                     "tool_calls": tool_calls}}]}

def llm_chat(messages, model: str, provider_id: str = None, api_key=None):
    # One model call, in OpenAI shape. Raises on missing key / HTTP error.
    # api_key: explicit key for this call (BYOK). None = master key from .env.
    cfg = get_provider_config(provider_id or DEFAULT_PROVIDER)
    if api_key is None and cfg["requires_key"] and not cfg["configured"]:
        raise ValueError(f"{cfg['key_env']} is not set - add it to .env to use {cfg['label']}.")
    if cfg["kind"] == "anthropic":
        return _llm_chat_anthropic(messages, model, cfg, api_key=api_key)
    return _llm_chat_openai(messages, model, cfg, api_key=api_key)

def run_agent(bot: dict, user_text: str, workspace_id: str = "default"):
    # Tool loop, max 8 turns. Returns (reply, tool_trace, extra).
    # extra carries error/fallback info for the UI; the loop itself is
    # identical for every provider (see llm_chat translation).
    # Operating-model enforcement (v0.3): the workspace's effective mode
    # decides which provider/model and which key pays for the chat.
    ws = get_workspace(workspace_id)
    mode, mode_source = effective_mode(ws)
    plat = load_platform()
    low_warn = False
    if mode == "fixed":
        # Master Managed Fixed: every chat uses the Super Admin's fixed model.
        provider_id = (plat.get("fixed_llm") or {}).get("provider") or "lmstudio"
        model = (plat.get("fixed_llm") or {}).get("model") or "qwen3.5"
    else:
        provider_id = bot.get("provider") or DEFAULT_PROVIDER
        model = bot.get("model") or ""
    if provider_id not in PROVIDERS:
        provider_id = DEFAULT_PROVIDER
    cfg = get_provider_config(provider_id)
    if not model:
        model = cfg["default_model"]
    eff_key, key_source = resolve_key(provider_id, ws, mode)
    history = load_chat(bot["id"])
    mem = load_memory(bot["id"])
    mem_text = "\n".join(f"- {f}" for f in mem.get("facts", [])) or "(no memory yet)"
    skills_text = _skills_text_for_bot(bot)
    system = (f"{bot['instructions']}\n\nYour memory about the user:\n{mem_text}\n\n"
              "You have tools for web search, browser automation, workspace files, "
              "and safe shell commands. Use them when needed, then answer in plain text."
              + (f"\n\nEnabled skills:\n{skills_text}" if skills_text else ""))
    messages = [{"role": "system", "content": system}]
    # Keep last 20 history turns as context (only user/assistant text)
    for m in history[-20:]:
        if m.get("role") in ("user", "assistant") and m.get("content"):
            messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": user_text})

    history.append({"role": "user", "content": user_text, "ts": int(time.time())})
    trace = []

    if MOCK_MODE:
        low = user_text.lower()
        if any(k in low for k in ("search", "browse", "open", "look up", "research")):
            q = user_text
            result, _blocked = _execute_tool("web_search", {"query": q}, bot)
            trace.append({"tool": "web_search", "args": {"query": q}, "result": result[:2000]})
            reply = (f"[MOCK MODE — no local model running] I searched for {q!r}:\n\n"
                     f"{result[:1500]}\n\n(This is a mock reply so you can test the UI and tools "
                     f"without a model. In LM Studio, load a model and start its local server, "
                     f"then restart without --mock for real answers.)")
        else:
            reply = (f"[MOCK MODE — no local model running] Got it: {user_text!r}\n\n"
                     f"I'm {bot['name']}, running in mock mode. In LM Studio, load a model, "
                     f"start the local server (Developer tab), set MODEL to that model's exact id, "
                     f"and restart without --mock for real local-model replies. I can still search the web, "
                     f"browse, and read/write files in ./workspace.")
        history.append({"role": "assistant", "content": reply, "tools": trace, "ts": int(time.time())})
        save_chat(bot["id"], history)
        return reply, trace, {"mode": mode, "key_source": key_source,
                              "workspace": ws["id"], "cost_usd": 0.0,
                              "wallet_balance": wallet_balance(ws["id"])}

    # Pre-check: provider disabled in Library/Settings > Connectors.
    if not provider_enabled(provider_id):
        reply = (f"{cfg['label']} is disabled in Library > Connectors. Enable it there, "
                 "or switch this bot to LM Studio (local) in the chat header.")
        history.append({"role": "assistant", "content": reply, "tools": [], "ts": int(time.time())})
        save_chat(bot["id"], history)
        return reply, [], {"error": "provider_disabled", "provider": provider_id,
                           "fallback_available": _lmstudio_fallback_available(provider_id),
                           "fallback_provider": "lmstudio"}
    # Pre-check: network off in Settings > Permissions blocks online providers.
    if provider_id not in ("lmstudio", "ollama") and not load_permissions().get("global", {}).get("network", True):
        reply = ("Network access is off in Settings > Permissions, so online providers are blocked. "
                 "Turn network back on, or switch this bot to LM Studio to work offline.")
        history.append({"role": "assistant", "content": reply, "tools": [], "ts": int(time.time())})
        save_chat(bot["id"], history)
        return reply, [], {"error": "network_off", "provider": provider_id,
                           "fallback_available": _lmstudio_fallback_available(provider_id),
                           "fallback_provider": "lmstudio"}

    # Pre-check: online provider with no key - fail fast with a clear error.
    # The "key" here is the effective one: master key, or the tenant's own
    # BYOK key for this workspace (see resolve_key). Local models need none.
    if cfg["requires_key"] and not eff_key:
        fb = _lmstudio_fallback_available(provider_id)
        if mode == "byok":
            reply = (f"{cfg['label']} needs YOUR key in this workspace (BYOK mode): "
                     "add your own API key for it in this workspace's Secure store. "
                     "The host pays nothing for BYOK chats — your key is used instead. "
                     + ("Local models are free: switch this bot to LM Studio to keep working offline."
                        if fb else ""))
            history.append({"role": "assistant", "content": reply, "tools": [], "ts": int(time.time())})
            save_chat(bot["id"], history)
            return reply, [], {"error": "missing_key", "provider": provider_id,
                               "mode": mode, "key_source": key_source,
                               "fallback_available": fb, "fallback_provider": "lmstudio"}
        if provider_id == "vps":
            reply = ("VPS Premium is not configured: set the VPS base URL and your "
                     "token in Settings > Connectors > VPS Premium (or VPS_BASE_URL / "
                     "VPS_API_TOKEN in .env). Your token is issued by the VPS owner — "
                     "it is not a provider API key, and no provider key ever lives in this app. "
                     + ("Fallback available: LM Studio is reachable - switch this bot to LM Studio."
                        if fb else "LM Studio is not reachable either, so there is no local fallback right now."))
        else:
            reply = (f"{cfg['label']} needs an API key: {cfg['key_env']} is not set. "
                     "Add it to .env (see .env.example) and restart the app. "
                     + (f"Fallback available: LM Studio at {get_provider_config('lmstudio')['base_url']} "
                        "is reachable - switch this bot's provider to LM Studio to keep working offline."
                        if fb else
                        "LM Studio is not reachable either, so there is no local fallback right now."))
        history.append({"role": "assistant", "content": reply, "tools": [], "ts": int(time.time())})
        save_chat(bot["id"], history)
        return reply, [], {"error": "missing_key", "provider": provider_id,
                           "fallback_available": fb, "fallback_provider": "lmstudio"}

    # Selectable mode: the model must be on the Super Admin's roster.
    # Local models are exempt — any local model is always allowed (and free).
    if (mode == "selectable" and provider_id not in ("lmstudio", "ollama")
            and not roster_allows(provider_id, model)):
        allowed = [f"{e['provider']}/{e['model']}" for e in roster_entries("llm")
                   if e.get("enabled")]
        first = next((e for e in roster_entries("llm") if e.get("enabled")), None)
        reply = (f"Model {provider_id}/{model} is not on this workspace's allowed roster. "
                 f"Allowed models: {', '.join(allowed) or '(none — ask the Super Admin)'}")
        history.append({"role": "assistant", "content": reply, "tools": [], "ts": int(time.time())})
        save_chat(bot["id"], history)
        extra_roster = {"error": "model_not_in_roster", "provider": provider_id,
                        "model": model, "allowed_models": allowed,
                        "fallback_available": _lmstudio_fallback_available(provider_id),
                        "fallback_provider": "lmstudio"}
        if first:
            extra_roster["suggested_provider"] = first["provider"]
            extra_roster["suggested_model"] = first["model"]
        return reply, [], extra_roster

    # Wallet check (master-paid modes only; local + BYOK are $0 to the host).
    if key_source == "master" and provider_id not in ("lmstudio", "ollama"):
        _bal = wallet_balance(ws["id"])
        _warn_at = float(load_pricing().get("low_balance_warn_usd", 1.0))
        low_warn = _bal < _warn_at
        if _bal <= 0:
            reply = (f"Workspace wallet is empty ($0.00) — this chat needs a paid model. "
                     f"Ask the Super Admin to top up the '{ws['name']}' workspace wallet, "
                     "or switch this bot to a local model (LM Studio / Ollama), which is always free.")
            history.append({"role": "assistant", "content": reply, "tools": [], "ts": int(time.time())})
            save_chat(bot["id"], history)
            return reply, [], {"error": "wallet_empty", "provider": provider_id,
                               "mode": mode, "key_source": key_source,
                               "wallet_balance": _bal,
                               "fallback_available": _lmstudio_fallback_available(provider_id),
                               "fallback_provider": "lmstudio"}

    # Availability check (local + VPS only): if the bot's saved model is
    # no longer offered by its provider, say so plainly and suggest the
    # nearest available model from the same provider, with a one-click
    # switch in the UI (extra.suggested_*). If the list itself cannot be
    # fetched, do not block — the model call below reports the real error.
    if provider_id in ("lmstudio", "ollama", "vps") and not MOCK_MODE:
        avail_models, avail_source, _avail_err = _live_models_for_provider(provider_id)
        if avail_models and avail_source in ("live", "defaults") and model not in avail_models:
            suggested = avail_models[0]
            fb = _lmstudio_fallback_available(provider_id)
            reply = (f"Model {model!r} is no longer available from {cfg['label']}. "
                     f"The nearest available model is {suggested!r} — switch to it below, "
                     "or pick another model from the Available models list. "
                     + ("LM Studio is also reachable as a local fallback."
                        if fb else ""))
            history.append({"role": "assistant", "content": reply, "tools": [], "ts": int(time.time())})
            save_chat(bot["id"], history)
            return reply, [], {"error": "model_unavailable", "provider": provider_id,
                               "model": model, "available_models": avail_models,
                               "suggested_provider": provider_id, "suggested_model": suggested,
                               "fallback_available": fb, "fallback_provider": "lmstudio"}

    # Real model loop
    reply = ""
    extra = {}
    last_usage = None
    succeeded = False
    prompt_chars = sum(len(str(m.get("content") or "")) for m in messages)
    for _turn in range(8):
        try:
            data = llm_chat(messages, model, provider_id, api_key=eff_key)
        except Exception as e:
            succeeded = False
            fb = _lmstudio_fallback_available(provider_id)
            extra = {"error": "provider_failed", "provider": provider_id,
                     "fallback_available": fb, "fallback_provider": "lmstudio"}
            if provider_id == "lmstudio":
                reply = (f"Could not reach LM Studio at {cfg['base_url']}. "
                         "Load Qwen3.5 (or your model) and press Start Server in the Developer tab, "
                         "and check the model id matches exactly. Or run with --mock to test the UI.")
            elif provider_id == "ollama":
                reply = (f"Could not reach Ollama at {cfg['base_url']}: {e}. "
                         "Run `ollama serve` and `ollama pull <model>`. "
                         + ("Fallback available: LM Studio is reachable - switch this bot to LM Studio."
                            if fb else ""))
            elif provider_id == "vps":
                reply = (f"VPS Premium failed: {e}. Check the VPS base URL and your token "
                         "in Settings > Connectors > VPS Premium, and that the VPS gateway is running. "
                         + ("Fallback available: LM Studio is reachable - switch this bot to LM Studio."
                            if fb else "LM Studio is not reachable either, so there is no local fallback right now."))
            else:
                _key_hint = ("Check the BYOK key saved for this workspace."
                             if key_source == "byok" else
                             f"Check your internet connection and the {cfg['key_env']} key in .env.")
                reply = (f"{cfg['label']} failed: {e}. {_key_hint} "
                         + (f"Fallback available: LM Studio at "
                            f"{get_provider_config('lmstudio')['base_url']} is reachable - "
                            "switch this bot's provider to LM Studio to keep working offline."
                            if fb else
                            "LM Studio is not reachable either, so there is no local fallback right now."))
            break
        record_usage(provider_id, model, data.get("usage"))
        last_usage = data.get("usage")
        succeeded = True
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        tool_calls = msg.get("tool_calls") or []
        if msg.get("content"):
            reply = msg["content"]
        messages.append(msg)
        if not tool_calls:
            break
        for tc in tool_calls:
            fn = tc.get("function", {})
            name, raw_args = fn.get("name"), fn.get("arguments") or "{}"
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            except Exception:
                args = {}
            result, blocked = _execute_tool(name, args, bot)
            trace.append({"tool": name, "args": args, "result": str(result)[:3000],
                          "blocked": blocked})
            messages.append({"role": "tool", "tool_call_id": tc.get("id", ""),
                             "content": str(result)[:8000]})
    else:
        reply = reply or "I used the maximum number of tool steps (8) — here's what I found so far."
    if not reply:
        reply = "(The model returned an empty reply.)"
    metered = {"cost_usd": 0.0, "billed": False, "balance_usd": wallet_balance(ws["id"]),
               "tokens_in": 0, "tokens_out": 0}
    if succeeded:
        metered = meter_usage(ws["id"], bot["id"], provider_id, model, last_usage,
                              prompt_chars, len(reply or ""), key_source, mode)
    extra.update({"mode": mode, "key_source": key_source, "workspace": ws["id"],
                  "cost_usd": metered["cost_usd"], "billed": metered["billed"],
                  "tokens_in": metered["tokens_in"], "tokens_out": metered["tokens_out"],
                  "wallet_balance": metered["balance_usd"],
                  "low_balance_warning": bool(low_warn)})
    history.append({"role": "assistant", "content": reply, "tools": trace, "ts": int(time.time()),
                    "cost_usd": metered["cost_usd"], "wallet_balance": metered["balance_usd"],
                    "mode": mode, "key_source": key_source})
    save_chat(bot["id"], history)
    return reply, trace, extra


# ---------- Operating models: Super Admin / workspaces / wallets ----------
# Three modes (v0.3, no real payments — wallets are manual balances):
#   fixed      — Master Managed Fixed: Super Admin assigns one fixed LLM
#                (+ one fixed Voice model). Tenants see no picker.
#   selectable — Master User-Selectable: tenants pick from the Super
#                Admin's curated roster; master keys pay for it.
#   byok       — Bring Your Own Key: the tenant's own keys pay; the host
#                incurs zero third-party API cost for that workspace.
# Local models (LM Studio / Ollama) are always free, in every mode.
# Key source is logged per chat (master / byok / local) — never the key.
PLATFORM_FILE = DATA_DIR / "platform.json"
PRICING_FILE = DATA_DIR / "pricing.json"
WORKSPACES_FILE = DATA_DIR / "workspaces.json"
WALLETS_DIR = DATA_DIR / "wallets"
BYOK_DIR = DATA_DIR / "byok"
METERING_FILE = DATA_DIR / "metering.jsonl"
MODES = ("fixed", "selectable", "byok")

def _default_roster():
    # LLM entries for every known provider + a few Voice (TTS) entries.
    roster = []
    for pid in PROVIDERS:
        cfg = PROVIDERS[pid]
        model = cfg["default_model"] or ""
        if pid == "vps":
            # VPS roster entries: the gateway's live list refines this at
            # runtime (Available models); seed the known premium set here.
            for m in ("claude-sonnet-4-5", "gpt-4o", "gpt-4o-mini",
                      "gemini-2.5-flash", "gemini-2.5-pro"):
                roster.append({"id": f"vps:{m}", "type": "llm", "provider": "vps",
                               "model": m, "label": f"VPS Premium — {m}", "enabled": True})
            continue
        if model:
            roster.append({"id": f"{pid}:{model}", "type": "llm", "provider": pid,
                           "model": model, "label": f"{cfg['label']} — {model}",
                           "enabled": True})
    for model, label in (("tts-1", "OpenAI TTS (tts-1)"),
                         ("tts-1-hd", "OpenAI TTS HD (tts-1-hd)"),
                         ("gpt-4o-mini-tts", "OpenAI TTS Mini (gpt-4o-mini-tts)")):
        roster.append({"id": f"openai:{model}", "type": "voice", "provider": "openai",
                       "model": model, "label": label, "enabled": True})
    return roster

def _default_platform():
    return {"global_mode": "selectable",
            "fixed_llm": {"provider": "lmstudio", "model": "qwen3.5"},
            "fixed_voice": {"provider": "openai", "model": "tts-1"},
            "roster": _default_roster()}

def load_platform():
    d = _load_json(PLATFORM_FILE, None)
    if not isinstance(d, dict) or "global_mode" not in d:
        d = _default_platform()
        _save_json(PLATFORM_FILE, d)
    d.setdefault("global_mode", "selectable")
    d.setdefault("fixed_llm", {"provider": "lmstudio", "model": "qwen3.5"})
    d.setdefault("fixed_voice", {"provider": "openai", "model": "tts-1"})
    d.setdefault("roster", _default_roster())
    return d

def save_platform(d):
    _save_json(PLATFORM_FILE, d)
    return d

def _default_pricing():
    # Prices in USD per 1,000 tokens (input / output), from PRICE_USD_PER_1M.
    per_model = {}
    for model, (pin, pout) in PRICE_USD_PER_1M.items():
        per_model[model] = {"per_1k_input_usd": round(pin / 1000, 6),
                            "per_1k_output_usd": round(pout / 1000, 6)}
    per_model.setdefault("deepseek-chat", {"per_1k_input_usd": 0.00014, "per_1k_output_usd": 0.00028})
    per_model.setdefault("deepseek-reasoner", {"per_1k_input_usd": 0.00055, "per_1k_output_usd": 0.00219})
    per_model.setdefault("gpt-5-codex", {"per_1k_input_usd": 0.00125, "per_1k_output_usd": 0.01})
    per_model.setdefault("codex-mini-latest", {"per_1k_input_usd": 0.00025, "per_1k_output_usd": 0.002})
    per_model.setdefault("claude-opus-4-1", {"per_1k_input_usd": 0.015, "per_1k_output_usd": 0.075})
    return {"currency": "USD",
            "default_per_1k_input_usd": 0.001, "default_per_1k_output_usd": 0.003,
            "low_balance_warn_usd": 1.0,
            "per_char_usd": {"tts-1": 0.000015, "tts-1-hd": 0.00003,
                             "gpt-4o-mini-tts": 0.000006},
            "per_model": per_model}

def load_pricing():
    d = _load_json(PRICING_FILE, None)
    if not isinstance(d, dict) or "per_model" not in d:
        d = _default_pricing()
        _save_json(PRICING_FILE, d)
    return d

def save_pricing(d):
    _save_json(PRICING_FILE, d)
    return d

def load_workspaces():
    ws = _load_json(WORKSPACES_FILE, None)
    if not isinstance(ws, list) or not ws:
        ws = [{"id": "default", "name": "Personal", "mode": "inherit",
               "members": ["Thomas"], "created_at": int(time.time())}]
        _save_json(WORKSPACES_FILE, ws)
    return ws

def save_workspaces(ws):
    _save_json(WORKSPACES_FILE, ws)
    return ws

def get_workspace(ws_id: str):
    ws_id = (ws_id or "default").strip() or "default"
    for w in load_workspaces():
        if w["id"] == ws_id:
            return w
    return load_workspaces()[0]

def effective_mode(ws: dict):
    """(mode, source): workspace override wins, else the global mode."""
    mode = (ws.get("mode") or "inherit").lower()
    if mode in MODES:
        return mode, "workspace"
    plat = load_platform()
    gmode = (plat.get("global_mode") or "selectable").lower()
    return (gmode if gmode in MODES else "selectable"), "global"

def roster_entries(kind: str = None):
    entries = load_platform().get("roster") or []
    if kind:
        entries = [e for e in entries if e.get("type") == kind]
    return entries

def roster_allows(provider: str, model: str, kind: str = "llm") -> bool:
    for e in roster_entries(kind):
        if e.get("enabled") and e.get("provider") == provider and e.get("model") == model:
            return True
    return False

# ---- per-workspace wallet (manual balance, no real payments) ----
def _wallet_path(ws_id: str) -> Path:
    return WALLETS_DIR / f"{ws_id}.json"

def load_wallet_ws(ws_id: str):
    d = _load_json(_wallet_path(ws_id), {})
    d.setdefault("workspace", ws_id)
    d.setdefault("currency", "USD")
    d.setdefault("balance_usd", 0.0)
    d.setdefault("transactions", [])
    d.setdefault("usage", [])
    return d

def save_wallet_ws(ws_id: str, d):
    _save_json(_wallet_path(ws_id), d)
    return d

def wallet_balance(ws_id: str) -> float:
    try:
        return float(load_wallet_ws(ws_id).get("balance_usd") or 0)
    except Exception:
        return 0.0

# ---- per-workspace BYOK keys (data/byok/<ws>.json, gitignored, masked) ----
def _byok_path(ws_id: str) -> Path:
    return BYOK_DIR / f"{ws_id}.json"

def load_byok_keys(ws_id: str):
    d = _load_json(_byok_path(ws_id), {})
    return d if isinstance(d, dict) else {}

def save_byok_keys(ws_id: str, d):
    _save_json(_byok_path(ws_id), d)
    return d

def byok_key(ws_id: str, provider: str):
    return (load_byok_keys(ws_id).get(provider) or "").strip() or None

def _is_admin(request) -> bool:
    token = (os.getenv("ADMIN_TOKEN") or "").strip()
    if not token:
        return False
    return (request.headers.get("x-admin-token") or "").strip() == token

def _require_admin(request):
    if not (os.getenv("ADMIN_TOKEN") or "").strip():
        raise HTTPException(403, "Super Admin is not enabled — set ADMIN_TOKEN in .env and restart the app.")
    if not _is_admin(request):
        raise HTTPException(401, "Admin token required — log in as Super Admin first.")

def resolve_key(provider_id: str, ws: dict, mode: str):
    """Which key pays for this chat? Returns (key or None, key_source).
    key_source: local (free) | master (Super Admin's key) | byok (tenant's key)."""
    if provider_id in ("lmstudio", "ollama"):
        return None, "local"
    if mode == "byok":
        return byok_key(ws["id"], provider_id), "byok"
    # fixed + selectable: the Super Admin's master key from .env.
    if provider_id == "vps":
        return os.getenv("VPS_API_TOKEN") or None, "master"
    return _provider_api_key(provider_id), "master"

def price_for(model: str, pricing: dict):
    entry = (pricing.get("per_model") or {}).get(model) or {}
    return (float(entry.get("per_1k_input_usd", pricing.get("default_per_1k_input_usd", 0.001))),
            float(entry.get("per_1k_output_usd", pricing.get("default_per_1k_output_usd", 0.003))))

def meter_usage(ws_id: str, bot_id: str, provider: str, model: str, usage,
                prompt_chars: int, reply_chars: int, key_source: str, mode: str):
    """Meter one chat turn and, for master-paid usage, charge the workspace
    wallet. Returns {tokens_in, tokens_out, chars, cost_usd, billed,
    balance_usd}. Local and BYOK usage costs the host $0 (tracked only)."""
    try:
        tin = int((usage or {}).get("input_tokens") or (usage or {}).get("prompt_tokens") or 0)
        tout = int((usage or {}).get("output_tokens") or (usage or {}).get("completion_tokens") or 0)
    except Exception:
        tin = tout = 0
    if tin == 0 and tout == 0:
        # No token counts returned: estimate ~4 chars per token.
        tin = max(1, int(prompt_chars / 4))
        tout = max(1, int(reply_chars / 4))
    pricing = load_pricing()
    per_in, per_out = price_for(model, pricing)
    cost = round((tin / 1000) * per_in + (tout / 1000) * per_out, 6)
    billed = key_source == "master" and provider not in ("lmstudio", "ollama")
    w = load_wallet_ws(ws_id)
    if billed and cost:
        w["balance_usd"] = round(float(w.get("balance_usd") or 0) - cost, 6)
        w.setdefault("transactions", []).append(
            {"ts": int(time.time()), "type": "charge", "amount_usd": -cost,
             "note": f"Chat: {provider}/{model} ({tin}+{tout} tokens)", "bot": bot_id,
             "model": model, "balance_after_usd": w["balance_usd"]})
        w["transactions"] = w["transactions"][-500:]
    entry = {"ts": int(time.time()), "bot": bot_id, "provider": provider, "model": model,
             "mode": mode, "key_source": key_source,
             "input_tokens": tin, "output_tokens": tout,
             "chars": int(prompt_chars) + int(reply_chars),
             "cost_usd": cost if billed else 0.0, "host_cost_usd": cost if billed else 0.0,
             "billed": billed, "balance_after_usd": float(w.get("balance_usd") or 0)}
    w.setdefault("usage", []).append(entry)
    w["usage"] = w["usage"][-500:]
    save_wallet_ws(ws_id, w)
    try:
        with METERING_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps({k: v for k, v in entry.items()
                                if k != "balance_after_usd"} | {"workspace": ws_id}) + "\n")
    except Exception:
        pass
    return {"tokens_in": tin, "tokens_out": tout,
            "chars": int(prompt_chars) + int(reply_chars),
            "cost_usd": cost if billed else 0.0, "billed": billed,
            "balance_usd": float(w.get("balance_usd") or 0)}

# ---------- API ----------
app = FastAPI(title="LocalBotz", version="0.1.0")
app.mount("/screenshots", StaticFiles(directory=SHOTS_DIR), name="screenshots")

@app.on_event("startup")
def _startup_heartbeat():
    # VPS heartbeat (see _send_vps_heartbeat above): tells the VPS gateway
    # this install exists, so the owner's admin panel can show where the
    # software is used. Background thread, never blocks startup.
    threading.Thread(target=_send_vps_heartbeat, daemon=True).start()
    threading.Thread(target=_persistent_worker, daemon=True).start()
    threading.Thread(target=_telegram_listener, daemon=True).start()

class BotCreate(BaseModel):
    name: str
    instructions: str = ""
    job: str = ""
    provider: str = ""
    model: str = ""
    template: str = ""
    avatar: str = ""
    schedule: str = ""
    enabled_tools: list = []
    skills: list = []

class BotUpdate(BaseModel):
    name: str = ""
    instructions: str = ""
    job: str = ""
    provider: str = ""
    model: str = ""
    avatar: str = ""
    schedule: str = ""
    enabled_tools: list = []
    skills: list = []
    persistent: bool = None

class ChatIn(BaseModel):
    message: str = Field(min_length=1)
    workspace: str = "default"

class MemoryIn(BaseModel):
    fact: str = Field(min_length=1)

@app.get("/health")
def health():
    reachable, detail, _c = check_provider(DEFAULT_PROVIDER)
    lm_reachable, _d, _e = check_provider("lmstudio")
    return {"status": "ok", "mock_mode": MOCK_MODE, "version": APP_VERSION,
            "provider": DEFAULT_PROVIDER, "provider_label": get_provider_config(DEFAULT_PROVIDER)["label"],
            "llm_base_url": get_provider_config(DEFAULT_PROVIDER)["base_url"], "model": DEFAULT_MODEL,
            "llm_reachable": reachable, "llm_detail": detail,
            "lm_studio_reachable": lm_reachable}

@app.get("/api/status")
def status(provider: str = ""):
    pid = (provider or DEFAULT_PROVIDER).lower()
    cfg = get_provider_config(pid)
    reachable, detail, configured = check_provider(pid)
    lm_reachable, _d, _e = check_provider("lmstudio")
    out = {"mock_mode": MOCK_MODE, "provider": pid, "provider_label": cfg["label"],
           "llm_base_url": cfg["base_url"], "model": cfg["default_model"],
           "requires_key": cfg["requires_key"], "key_env": cfg["key_env"],
           "configured": configured, "missing_key": cfg["requires_key"] and not configured,
           "llm_reachable": reachable, "llm_detail": detail,
           "lm_studio_reachable": lm_reachable,
           "fallback_available": lm_reachable and pid != "lmstudio"}
    if pid == "vps":
        out["vps_configured"] = vps_configured()
        out["vps_base_url"] = get_vps_base_url()
    return out

@app.get("/api/providers")
def providers():
    out = []
    store = load_connectors_store()
    for pid in PROVIDERS:
        cfg = get_provider_config(pid)
        cfg["enabled"] = store["providers"].get(pid, {}).get("enabled", True)
        status, detail, last = _provider_status(pid, store)
        cfg["status"] = status
        cfg["status_detail"] = detail
        cfg["last_test"] = last or None
        cfg["masked"] = _mask_key(os.getenv(cfg["key_env"]) or "") if cfg.get("key_env") else ""
        out.append(cfg)
    return out

@app.get("/api/vps/config")
def vps_config():
    cfg = get_provider_config("vps")
    token = os.getenv("VPS_API_TOKEN") or ""
    return {"provider": "vps", "label": "VPS Premium",
            "base_url": get_vps_base_url(), "configured": vps_configured(),
            "has_token": bool(token), "masked_token": _mask_key(token),
            "placeholder": VPS_PLACEHOLDER_URL,
            "note": "Your token is issued by the VPS owner. It is not a provider API key; "
                    "provider keys stay on the VPS only."}

@app.post("/api/vps/config")
def set_vps_config(body: dict):
    # Base URL is stored in the connectors store (not a secret);
    # the token goes to .env via the Secure store path (masked, never returned).
    base_url = (body.get("base_url") or "").strip().rstrip("/")
    token = (body.get("token") or body.get("api_token") or "").strip()
    store = load_connectors_store()
    if base_url:
        store.setdefault("vps", {})["base_url"] = base_url
        save_connectors_store(store)
    if token:
        _set_env_key("VPS_API_TOKEN", token)
    return vps_config()

@app.post("/api/vps/register")
def vps_register(body: dict):
    # Register this user on the VPS gateway: POST {base}/register with
    # name + email. The gateway creates their workspace and returns their
    # own token ONCE. We save the base URL + token the same way as the
    # manual VPS setup (URL in the connectors store, token in .env).
    name = (body.get("name") or "").strip()
    email = (body.get("email") or "").strip().lower()
    base_url = (body.get("base_url") or get_vps_base_url() or "").strip().rstrip("/")
    if not name or not email or "@" not in email:
        raise HTTPException(400, "Name and a valid email are required to register.")
    if not base_url or base_url == VPS_PLACEHOLDER_URL:
        raise HTTPException(400, "Set the VPS base URL first (e.g. https://api.localbotz.io/v1).")
    try:
        with _http_client(timeout=20, external=not _is_local_url(base_url)) as c:
            r = c.post(f"{base_url}/register", json={"name": name, "email": email})
        if r.status_code == 409:
            raise HTTPException(409, "This email is already registered on that VPS. If you lost your token, ask the VPS owner for a new one.")
        if r.status_code == 403:
            raise HTTPException(403, "Registration is closed on that VPS. Ask the VPS owner for a premium token.")
        if r.status_code == 429:
            raise HTTPException(429, "Registration limit reached for today on that VPS. Try again tomorrow.")
        r.raise_for_status()
        data = r.json()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"Could not reach the VPS gateway at {base_url}: {e}. Check the base URL and that the gateway is running.")
    token = (data.get("token") or "").strip()
    if not token:
        raise HTTPException(502, "The VPS gateway did not return a token.")
    store = load_connectors_store()
    store.setdefault("vps", {})["base_url"] = base_url
    save_connectors_store(store)
    _set_env_key("VPS_API_TOKEN", token)
    return {"workspace_id": data.get("workspace_id"), "email": data.get("email"),
            "configured": True,
            "note": "Registered. Your token is saved in Secure store — pick provider 'VPS Premium' per bot to use premium models."}

@app.post("/api/vps/signin-code")
def vps_signin_code(body: dict):
    # Sign in with a 6-digit code made on the VPS account panel
    # (/account → Sign in code). The gateway exchanges it for a FRESH token
    # for that workspace — the old token stops working. We save the base
    # URL + new token the same way as the manual VPS setup.
    code = (body.get("code") or "").strip()
    base_url = (body.get("base_url") or get_vps_base_url() or "").strip().rstrip("/")
    if not re.match(r"^\d{6}$", code):
        raise HTTPException(400, "Enter the 6-digit sign-in code from your account page.")
    if not base_url or base_url == VPS_PLACEHOLDER_URL:
        raise HTTPException(400, "Set the VPS base URL first (e.g. https://api.localbotz.io/v1).")
    try:
        with _http_client(timeout=20, external=not _is_local_url(base_url)) as c:
            r = c.post(f"{base_url}/exchange-code", json={"code": code})
        if r.status_code in (400, 401):
            raise HTTPException(401, "Wrong or expired sign-in code. Make a new one on your account page.")
        if r.status_code == 403:
            raise HTTPException(403, "This premium account is disabled. Contact the VPS owner.")
        r.raise_for_status()
        data = r.json()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"Could not reach the VPS gateway at {base_url}: {e}. Check the base URL and that the gateway is running.")
    token = (data.get("token") or "").strip()
    if not token:
        raise HTTPException(502, "The VPS gateway did not return a token.")
    store = load_connectors_store()
    store.setdefault("vps", {})["base_url"] = base_url
    save_connectors_store(store)
    _set_env_key("VPS_API_TOKEN", token)
    return {"workspace_id": data.get("workspace_id"), "email": data.get("email"),
            "configured": True,
            "note": "Signed in. Your new token is saved in Secure store — your old token no longer works."}

@app.get("/api/vps/pricing")
def vps_pricing():
    # Public price list from the VPS gateway (GET {base}/pricing, no
    # auth) — what renting premium models costs, before the user
    # registers. Never includes keys or tokens.
    base = get_vps_base_url()
    if not base or base == VPS_PLACEHOLDER_URL:
        return {"models": [], "currency": "USD", "error": "Set the VPS base URL first in Settings > Connectors > VPS Premium."}
    try:
        with _http_client(timeout=15, external=not _is_local_url(base)) as c:
            r = c.get(f"{base}/pricing")
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"models": [], "currency": "USD",
                "error": f"Could not reach the VPS gateway at {base}: {e}."}

@app.get("/api/vps/models")
def vps_models():
    # List the premium models the VPS gateway offers (GET {base}/models
    # with the user token). Never returns any provider key.
    if not vps_configured():
        return {"models": [], "configured": False, "reachable": False,
                "error": "VPS Premium is not configured - set the base URL and token in Settings > Connectors > VPS Premium."}
    base = get_vps_base_url()
    try:
        with _http_client(timeout=15, external=not _is_local_url(base)) as c:
            r = c.get(f"{base}/models",
                      headers={"Authorization": f"Bearer {os.getenv('VPS_API_TOKEN')}"})
        if r.status_code == 401:
            return {"models": [], "configured": True, "reachable": False,
                    "error": "VPS token rejected (HTTP 401) - check the token in Settings > Connectors > VPS Premium."}
        r.raise_for_status()
        data = r.json()
        models = [m.get("id") for m in (data.get("data") or []) if isinstance(m, dict) and m.get("id")]
        return {"models": models, "configured": True, "reachable": True, "error": ""}
    except Exception as e:
        return {"models": [], "configured": True, "reachable": False,
                "error": f"Could not reach the VPS gateway at {base}: {e}. "
                         "Check the base URL and that the gateway is running; "
                         "fall back to LM Studio (local) meanwhile."}

@app.get("/api/models/available")
def models_available_endpoint():
    # Live availability probe of every source. Slow sources time out in
    # ~5s each; a source that cannot be reached is reported, not hidden.
    return models_available()

@app.get("/api/providers/{pid}/models")
def provider_models(pid: str):
    if pid.lower() not in PROVIDERS:
        raise HTTPException(404, "Provider not found")
    models, source, error = _live_models_for_provider(pid.lower())
    cfg = get_provider_config(pid.lower())
    return {"provider": cfg["id"], "label": cfg["label"], "models": models,
            "source": source, "error": error,
            "available": bool(models) and source != "unavailable"}

@app.get("/api/templates")
def templates(category: str = ""):
    items = load_templates_list()
    if category in ("featured",):
        return [t for t in items if t.get("featured")]
    if category in ("", "more", "all"):
        return items
    if category:
        return [t for t in items if t.get("category") == category]
    return items

@app.get("/api/templates/{template_id}")
def one_template(template_id: str):
    t = get_template(template_id)
    if not t:
        raise HTTPException(404, "Template not found")
    return t

@app.get("/api/tools")
def tools():
    perms = load_permissions()
    bots = load_bots()
    out = []
    for t in TOOL_DEFS:
        name = t["function"]["name"]
        using = [b["name"] for b in bots
                 if not b.get("enabled_tools") or name in (b.get("enabled_tools") or [])]
        out.append({"name": name, "description": t["function"]["description"],
                    "enabled": perms.get("tools", {}).get(name, True),
                    "bots_using": using})
    return out

@app.post("/api/tools/{tool_name}")
def set_tool(tool_name: str, body: dict):
    perms = load_permissions()
    names = [t["function"]["name"] for t in TOOL_DEFS]
    if tool_name not in names:
        raise HTTPException(404, "Tool not found")
    perms.setdefault("tools", {})[tool_name] = bool(body.get("enabled", True))
    save_permissions(perms)
    return {"tool": tool_name, "enabled": perms["tools"][tool_name]}

@app.post("/api/bots/{bot_id}/tools")
def set_bot_tool(bot_id: str, body: dict):
    bot = get_bot(bot_id)
    if not bot:
        raise HTTPException(404, "Bot not found")
    perms = load_permissions()
    perms.setdefault("bots", {}).setdefault(bot_id, {})         .setdefault("tools", {})[body.get("tool", "")] = bool(body.get("enabled", True))
    save_permissions(perms)
    return {"bot": bot_id, "tool": body.get("tool"), "enabled": body.get("enabled")}

@app.get("/api/bots")
def list_bots():
    return load_bots()

@app.post("/api/bots", status_code=201)
def create_bot(body: BotCreate):
    bots = load_bots()
    tpl = get_template(body.template) if body.template else None
    instructions = body.instructions.strip()
    if tpl and not instructions:
        instructions = tpl["instructions"]
    provider = ((body.provider or (tpl["provider"] if tpl else "") or DEFAULT_PROVIDER)).lower()
    if provider not in PROVIDERS:
        provider = DEFAULT_PROVIDER
    model = body.model.strip() or (tpl["model"] if tpl else "") or get_provider_config(provider)["default_model"]
    job = body.job.strip()
    if job and not instructions:
        instructions = f"You are {body.name.strip() or 'a helpful assistant'}. Job: {job}"
    bot = {"id": uuid.uuid4().hex[:8], "name": body.name.strip() or (tpl["name"] if tpl else "Untitled Bot"),
           "template": body.template, "job": job,
           "instructions": instructions or "You are a helpful local assistant.",
           "provider": provider, "model": model,
           "avatar": body.avatar or (tpl["avatar"] if tpl else "🤖"),
           "schedule": body.schedule or (tpl["schedule"] if tpl else "on_demand"),
           "enabled_tools": body.enabled_tools or (tpl["default_tools"] if tpl else []),
           "skills": body.skills or ["research", "file-help", "browser-help"],
           "persistent": False,
           "created_at": int(time.time())}
    bots.append(bot); save_bots(bots)
    return bot

@app.patch("/api/bots/{bot_id}")
def update_bot(bot_id: str, body: BotUpdate):
    bots = load_bots()
    bot = next((b for b in bots if b["id"] == bot_id), None)
    if not bot:
        raise HTTPException(404, "Bot not found")
    for field in ("name", "instructions", "job", "avatar", "schedule"):
        v = getattr(body, field)
        if v:
            bot[field] = v.strip() if isinstance(v, str) else v
    if body.provider and body.provider.lower() in PROVIDERS:
        bot["provider"] = body.provider.lower()
        if not body.model:
            bot["model"] = get_provider_config(bot["provider"])["default_model"]
    if body.model:
        bot["model"] = body.model.strip()
    if body.enabled_tools is not None:
        bot["enabled_tools"] = body.enabled_tools
    if body.skills is not None:
        bot["skills"] = body.skills
    if body.persistent is not None:
        bot["persistent"] = bool(body.persistent)
    save_bots(bots)
    return bot

@app.get("/api/bots/{bot_id}")
def get_one_bot(bot_id: str):
    bot = get_bot(bot_id)
    if not bot:
        raise HTTPException(404, "Bot not found")
    return bot

# ---------- Office: run a team of agents locally -----------------------
# Modelled on Munder Difflin (HarnessMD/munder-difflin, MIT): an office
# of agents on your own machine. A user creates their office locally,
# hires an AI team with roles, and the team works together with a shared
# memory that survives sessions. LocalBotz version, local-first:
# - One office = one folder under data/offices/<id>/ with memory.md
#   (shared office memory, markdown) and blackboard.json (the mailbox:
#   messages passed between team members).
# - One boss agent (the "Michael": the only agent the user briefs) who
#   plans the job and assigns steps to the team.
# - Team members are ordinary LocalBotz bots with a role (Researcher,
#   Writer, Developer, Analyst, Assistant) — hired from a template or
#   blank, each with its own instructions, memory and chats.
# - A team job runs locally (LM Studio default): the boss's plan is the
#   hire order — Researcher first, then Writer/Developer, then Analyst
#   last — each member runs with the brief + shared office memory +
#   the previous members' outputs, and hands its result to the next
#   member on the blackboard. The job summary is written into the
#   office memory, so the team remembers it next time.
OFFICES_FILE = DATA_DIR / "offices.json"
OFFICES_DIR = DATA_DIR / "offices"

OFFICE_ROLES = {
    "boss": {"label": "Office Manager (boss)", "avatar": "👔",
             "instructions": "You are {name}, the Office Manager — the boss of this office and the one agent the user talks to. You plan work, assign it to your team, check their results, and report back in plain text. You never do the team's specialist work yourself when a team member can do it."},
    "researcher": {"label": "Researcher", "avatar": "🔍",
                   "instructions": "You are {name}, the Researcher on this office's AI team. You search the web and the workspace, gather facts with sources, and hand over a clear research brief. You do not write the final piece or the code — you hand your findings to the next team member."},
    "writer": {"label": "Writer", "avatar": "✍️",
              "instructions": "You are {name}, the Writer on this office's AI team. You turn research and briefs into clear, finished writing in plain language. You do not do new research — you work from what the Researcher handed over."},
    "developer": {"label": "Developer", "avatar": "💻",
                 "instructions": "You are {name}, the Developer on this office's AI team. You write and fix code in the workspace, run safe checks, and hand over working code with a short summary of what changed."},
    "analyst": {"label": "Analyst", "avatar": "📊",
               "instructions": "You are {name}, the Analyst on this office's AI team. You check numbers, review the team's work for errors and gaps, and give a clear verdict with what to fix. You are the last step before the work goes back to the boss."},
    "assistant": {"label": "Assistant", "avatar": "🤖",
                 "instructions": "You are {name}, the Assistant on this office's AI team. You handle follow-ups, organise notes, draft replies, and keep the office memory tidy."},
    "sales": {"label": "Sales", "avatar": "💰",
              "instructions": "You are {name}, the Sales member on this office's AI team. You research competitors and customers, and build battle cards: what the other side sells, their weak spots, and how to win. You cite sources and keep it to one page."},
    "finance": {"label": "Finance", "avatar": "💲",
                "instructions": "You are {name}, the Finance member on this office's AI team. You check the numbers: budgets, costs, prices and forecasts. You show your working, never invent figures, and flag what is missing before the team decides."},
    "legal": {"label": "Legal", "avatar": "⚖️",
              "instructions": "You are {name}, the Legal member on this office's AI team. You research a legal question and explain contracts in plain language: what a clause means and what the risks are. You are not a lawyer and this is not legal advice — you say so, and you never present a guess as settled law."},
    "recruiter": {"label": "Recruiter", "avatar": "💼",
                  "instructions": "You are {name}, the Recruiter on this office's AI team. You screen candidates against the job: skills, experience and fit, in a short scorecard, and draft the interview questions that would settle the open doubts. You stay fair and never judge a person on anything but the job."},
    "teacher": {"label": "Teacher", "avatar": "👨‍🏫",
                "instructions": "You are {name}, the Teacher on this office's AI team. You turn what the team learned into a clear lesson: the big ideas in order, a short explanation for each, and a small exercise. You keep it short and check understanding with a question."},
}

# Sector roles for the Office, from the user's own list: every job title a
# construction, MEP, electrical, IT services or e-commerce company hires —
# senior management down to technicians and trades. Each entry is
# (sector, group, avatar, [(role_id, title, one-line job)]).
SECTOR_ROLES = [
 ("Construction", "Project & Site Management", "👔", [
  ("construction-manager", "Construction Manager", "Runs the whole site: schedule, people, budget and safety, and reports progress to the client."),
  ("project-manager", "Project Manager", "Plans the project, tracks progress against the programme, and keeps the client and the team informed."),
  ("site-engineer", "Site Engineer", "Runs the technical work on site: setting out, drawings, inspections, and solving problems as they come up."),
  ("civil-engineer", "Civil Engineer", "Designs and checks the civil works — structures, earthworks and drainage — and answers site queries."),
  ("structural-engineer", "Structural Engineer", "Designs and checks the structure, reviews steel and concrete, and signs off what is safe to build."),
  ("project-coordinator", "Project Coordinator", "Keeps the project organised: schedules, meetings, documents and follow-ups, so nothing slips."),
 ]),
 ("Construction", "Planning & Commercial", "📋", [
  ("quantity-surveyor", "Quantity Surveyor (QS)", "Measures the work, prepares BOQs and valuations, and keeps the cost of the project under control."),
  ("estimation-engineer", "Estimation Engineer", "Prices the work from drawings and specs: quantities, rates and a clear, checkable estimate."),
  ("tendering-engineer", "Tendering Engineer", "Prepares tender submissions: the price, the programme and the documents the client asked for."),
  ("planning-engineer", "Planning Engineer", "Builds and updates the project programme, flags delays early, and shows what to do about them."),
  ("procurement-officer", "Procurement Officer", "Buys materials and services at the right price and time, and keeps supplier records tidy."),
  ("contract-administrator", "Contract Administrator", "Runs the contract: variations, claims, payments and notices, in writing and on time."),
 ]),
 ("Construction", "Quality, Safety & Drafting", "🛡️", [
  ("qa-qc-engineer", "QA/QC Engineer", "Checks the work against the spec: inspections, test reports and snag lists, until it passes."),
  ("hse-officer", "HSE Officer", "Keeps the site safe: risk assessments, toolbox talks, permits and incident reports."),
  ("document-controller", "Document Controller", "Keeps every drawing, submittal and letter in the right place, with the right revision, and finds it fast."),
  ("autocad-draftsman", "AutoCAD Draftsman", "Draws and updates plans, sections and details in AutoCAD from the engineer's mark-ups."),
  ("bim-specialist", "BIM Specialist", "Builds and coordinates the BIM model, finds clashes before they reach site, and keeps the model current."),
 ]),
 ("Construction", "Field & Trade Roles", "👷", [
  ("site-supervisor", "Site Supervisor", "Runs the site day to day: gangs, materials and safety, and reports progress to the site engineer."),
  ("general-foreman", "General Foreman", "Leads the trades on site, reads the drawings, and makes sure the work is done right the first time."),
  ("land-surveyor", "Land Surveyor", "Measures and sets out the site: levels, boundaries and as-built surveys, with accurate records."),
  ("mason", "Mason", "Builds blockwork, brickwork and plaster to the drawings, and flags bad materials before they are used."),
  ("carpenter", "Carpenter", "Builds formwork, doors and joinery to the drawings, and keeps the work neat and to size."),
  ("steel-fixer", "Steel Fixer", "Fixes reinforcement steel to the drawings and bar bending schedule, and checks it before the pour."),
 ]),
 ("MEP", "Engineering & Design", "🔧", [
  ("mep-manager", "MEP Manager", "Runs all the MEP works: design, installation and commissioning, and coordinates with the civil team."),
  ("mep-project-engineer", "MEP Project Engineer", "Runs the MEP scope on a project: drawings, materials, installation and testing, on schedule."),
  ("mep-coordinator", "MEP Coordinator", "Coordinates the MEP services with each other and with the structure, so nothing clashes on site."),
  ("hvac-engineer", "HVAC Engineer", "Designs and checks heating, ventilation and air conditioning: loads, ductwork and equipment."),
  ("plumbing-drainage-engineer", "Plumbing & Drainage Engineer", "Designs water supply, drainage and plumbing: pipe sizes, routes and fixtures that work."),
  ("firefighting-engineer", "Firefighting / Fire Protection Engineer", "Designs fire protection: sprinklers, hydrants, alarms and pumps, to the code and the authority's rules."),
 ]),
 ("MEP", "Technical & Drafting", "📐", [
  ("mep-draftsman", "MEP Draftsman", "Draws MEP layouts, sections and details in CAD from the engineer's design."),
  ("bim-mep-modeler", "BIM MEP Modeler", "Builds the MEP BIM model, coordinates it with the other trades, and finds clashes early."),
  ("mep-estimation-engineer", "MEP Estimation Engineer", "Prices the MEP works from drawings and specs: quantities, rates and a clear estimate."),
  ("mep-qa-qc-inspector", "MEP QA/QC Inspector", "Inspects MEP installation against the spec: checklists, test records and snag lists until it passes."),
 ]),
 ("MEP", "Technicians & Supervisors", "🧰", [
  ("mep-supervisor", "MEP Supervisor", "Runs the MEP installation on site: gangs, materials, safety and progress reports."),
  ("mep-technician", "MEP Technician", "Installs, tests and maintains MEP systems to the drawings, and reports faults clearly."),
  ("hvac-technician", "HVAC Technician", "Installs and services air conditioning and ventilation: ducts, units and controls that work."),
  ("plumber", "Plumber", "Installs and repairs water and drainage pipework to the drawings, and tests it before handover."),
  ("pipe-fitter", "Pipe Fitter", "Fits and joins pipework — chilled water, plumbing and fire — to the drawings and the spec."),
  ("ductman", "Ductman", "Fabricates and installs ductwork to the drawings, sealed and insulated as specified."),
 ]),
 ("Electrical Engineering", "Design & Power Systems", "⚡", [
  ("electrical-design-engineer", "Electrical Design Engineer", "Designs the electrical system: loads, cable sizing, panels and layouts, to the code."),
  ("power-systems-engineer", "Power Systems Engineer", "Studies the power system: load flow, short circuit and protection, and says what is safe."),
  ("hv-lv-engineer", "HV / LV Engineer", "Designs high and low voltage systems: substations, distribution and earthing, to the code."),
  ("substation-engineer", "Substation Engineer", "Designs and checks substations: transformers, switchgear and protection, ready to build."),
  ("protection-control-engineer", "Protection & Control Engineer", "Designs protection and control: relays, settings and schemes that keep the system safe."),
 ]),
 ("Electrical Engineering", "Testing & Commissioning", "🔌", [
  ("testing-commissioning-engineer", "Testing & Commissioning (T&C) Engineer", "Tests and commissions the electrical installation, and records the results for handover."),
  ("switchgear-commissioning-engineer", "Switchgear Commissioning Engineer", "Commissions switchgear: tests, settings and energisation, step by step and safely."),
  ("maintenance-engineer", "Maintenance Engineer", "Plans and carries out electrical maintenance: inspections, repairs and records, before things fail."),
 ]),
 ("Electrical Engineering", "Specialized Systems & Technicians", "🔬", [
  ("elv-engineer", "ELV Engineer", "Designs extra-low voltage systems: CCTV, access control, fire alarm and data, to the spec."),
  ("instrumentation-controls-engineer", "Instrumentation & Controls Engineer", "Designs instruments and controls: sensors, loops and panels that measure and control the plant."),
  ("earthing-lightning-engineer", "Earthing & Lightning Protection Engineer", "Designs earthing and lightning protection: calculations, layouts and test records."),
  ("electrical-supervisor", "Electrical Supervisor", "Runs the electrical work on site: gangs, materials, safety and progress reports."),
  ("industrial-electrician", "Industrial Electrician", "Installs, tests and repairs industrial electrical systems to the drawings, safely and neatly."),
 ]),
 ("IT Services", "Software Development", "💻", [
  ("software-engineer", "Software Engineer", "Designs and builds software: clean code, tests and clear notes on what changed."),
  ("full-stack-developer", "Full-Stack Developer", "Builds the whole web app: front end, back end and database, working end to end."),
  ("front-end-developer", "Front-End Developer", "Builds the user interface: fast, clear and working on every screen size."),
  ("back-end-developer", "Back-End Developer", "Builds the server side: APIs, databases and logic that the front end relies on."),
  ("mobile-app-developer", "Mobile App Developer", "Builds the mobile app: screens, features and fixes, for iOS and Android."),
 ]),
 ("IT Services", "Infrastructure, Cloud & Security", "☁️", [
  ("devops-engineer", "DevOps Engineer", "Automates builds, deploys and monitoring, so releases go out safely and often."),
  ("cloud-architect", "Cloud Architect", "Designs the cloud setup: the right services, the right size, and the cost kept under control."),
  ("system-administrator", "System Administrator", "Runs the servers and systems: users, backups, updates and uptime."),
  ("network-engineer", "Network Engineer", "Designs and runs the network: switches, firewalls and links that stay up."),
  ("cybersecurity-analyst", "Cybersecurity Analyst", "Watches for threats, checks for weaknesses, and writes down what to fix first."),
 ]),
 ("IT Services", "Data & Testing", "📊", [
  ("data-engineer", "Data Engineer", "Builds the data pipelines: clean, reliable data, ready for reports and models."),
  ("data-analyst", "Data Analyst", "Answers questions from the data: clear numbers, charts and what they mean."),
  ("database-administrator", "Database Administrator (DBA)", "Runs the databases: backups, performance and access, so data is there when needed."),
  ("qa-tester", "QA Automation / Manual Tester", "Tests the software like a user would: finds the bugs, writes them down clearly, and checks the fixes."),
 ]),
 ("IT Services", "Support & Delivery", "🎧", [
  ("it-support-specialist", "IT Support Specialist", "Solves users' IT problems fast and politely, and records what was fixed."),
  ("help-desk-technician", "Help Desk Technician", "Takes support tickets, fixes what can be fixed, and escalates the rest with a clear note."),
  ("technical-project-manager", "Technical Project Manager", "Runs IT projects: scope, schedule and team, and keeps the client informed."),
  ("scrum-master", "Scrum Master", "Runs the agile process: sprints, stand-ups and blockers removed, so the team ships."),
  ("business-analyst", "Business Analyst", "Turns business needs into clear requirements the developers can build from."),
  ("erp-consultant", "ERP Consultant", "Sets up and supports the ERP system: config, training and fixes that fit how the company works."),
 ]),
 ("E-Commerce", "Store & Merchandising", "🛒", [
  ("ecommerce-manager", "E-Commerce Manager", "Runs the online store: sales, listings, offers and the numbers, and grows the business."),
  ("merchandising-manager", "Merchandising Manager", "Plans what to sell and how to show it: ranges, pricing and promotions that move stock."),
  ("category-manager", "Category Manager", "Owns a product category: range, prices and suppliers, and grows its sales."),
  ("catalog-specialist", "Catalog Specialist", "Keeps the product catalog clean: correct titles, specs, images and prices, everywhere."),
  ("product-listing-coordinator", "Product Listing Coordinator", "Writes and publishes product listings: clear titles, honest descriptions and the right attributes."),
 ]),
 ("E-Commerce", "Digital Marketing & Growth", "📣", [
  ("digital-marketing-specialist", "Digital Marketing Specialist", "Runs the marketing: campaigns, social and content that bring customers in."),
  ("performance-marketer", "Performance Marketer (PPC/Paid Ads)", "Runs paid ads: budgets, targeting and landing pages, and reports what each sale cost."),
  ("seo-specialist", "SEO Specialist", "Gets the store found on search: keywords, pages and links that rank and bring buyers."),
  ("content-strategist", "Content Strategist", "Plans the content: what to publish, for whom, and how it brings customers back."),
  ("crm-email-marketing-manager", "CRM / Email Marketing Manager", "Runs customer emails and CRM: campaigns, segments and follow-ups that bring repeat orders."),
 ]),
 ("E-Commerce", "Operations & Supply Chain", "📦", [
  ("supply-chain-manager", "Supply Chain Manager", "Runs the supply chain: suppliers, stock and delivery, so orders go out on time."),
  ("inventory-planner", "Inventory Planner", "Plans stock levels: what to order, when, and how much, so nothing runs out or sits still."),
  ("warehouse-operations-manager", "Warehouse Operations Manager", "Runs the warehouse: receiving, picking, packing and dispatch, safely and on time."),
  ("order-fulfillment-specialist", "Order Fulfillment Specialist", "Gets orders out the door: pick, pack, ship and track, and fix problems fast."),
  ("logistics-coordinator", "Logistics Coordinator", "Coordinates deliveries and couriers: bookings, tracking and proof of delivery."),
 ]),
 ("E-Commerce", "Customer Experience & Design", "🎨", [
  ("ui-ux-designer", "UI/UX Designer", "Designs the store and the app: clear, easy and pleasant to buy from."),
  ("cro-specialist", "Conversion Rate Optimization (CRO) Specialist", "Improves the store so more visitors buy: tests, measures and changes what works."),
  ("customer-support-representative", "Customer Support Representative", "Answers customers politely and fast: orders, returns and complaints, solved or escalated clearly."),
 ]),
 # NaukriGulf jobs-by-category (naukrigulf.com/jobs-by-category, 102
 # categories, read 2026-11-14): every category an AI office agent can
 # actually do — office, sales and marketing work. Left out on purpose:
 # purely physical / frontline jobs (Chef, Guard, Housekeeping, Nurse,
 # Doctor, Equipment Operator, Marine, Installation, Repair), jobs
 # already covered by the core or sector roles above (Sales, Finance,
 # Legal, Teacher, Project Manager, Logistics Coordinator, QA/QC,
 # Network Engineer, UI/UX Designer), and levels, not functions
 # (Fresh Graduate, Management Trainee, Top Management). Near-duplicates
 # are merged into one role (Front Desk into Front Office, Import +
 # Export into one role, Ticketing into Travel Agent).
 ("Finance & Accounts", "Accounts, Audit & Tax", "💲", [
  ("accountant", "Accountant", "Keeps the books tidy: invoices, expenses, reconciliations and monthly reports, and flags anything that does not add up."),
  ("internal-auditor", "Internal Auditor", "Checks the company's own records and processes: what is missing, what breaks the rules, and what to fix first."),
  ("tax-consultant", "Tax Consultant", "Prepares tax workings and filings from the company's numbers, checks deadlines, and explains what is owed in plain language."),
 ]),
 ("Finance & Accounts", "Banking & Insurance", "🏦", [
  ("banking-officer", "Banking Officer", "Prepares loan and account paperwork, follows up with the bank, and keeps the company's banking records in order."),
  ("broker", "Broker", "Prepares quotes and client documents, compares cover and prices, and follows up so nothing is left waiting."),
  ("insurance-advisor", "Insurance Advisor", "Explains policies in plain language, prepares claims paperwork, and chases renewals before they lapse."),
 ]),
 ("Admin & Office Support", "Office & Data", "🗂️", [
  ("office-administrator", "Office Administrator", "Runs the office day to day: letters, records, schedules and suppliers, so the office keeps working."),
  ("back-office-executive", "Back Office Executive", "Handles the paperwork behind the business: forms, records, data checks and follow-ups, accurately and on time."),
  ("data-entry-clerk", "Data Entry Clerk", "Enters data cleanly and checks it twice: lists, records and reports the team can trust."),
  ("executive-secretary", "Executive Secretary", "Supports the manager: diary, meetings, letters and travel plans, kept in order and on time."),
  ("front-office-executive", "Front Office Executive", "Runs the front desk: visitors, calls and messages answered politely, logged, and passed to the right person."),
 ]),
 ("Sales & Marketing", "Marketing & Media", "📣", [
  ("advertising-executive", "Advertising Executive", "Plans and writes adverts: the message, the audience and the budget, and reports what worked."),
  ("marketing-manager", "Marketing Manager", "Runs the marketing plan: campaigns, channels and budget, and reports what brought customers in."),
  ("media-planner", "Media Planner", "Plans where adverts run: channels, timing and budget, so the money reaches the right audience."),
  ("pr-executive", "PR Executive", "Writes press notes and handles media enquiries, and keeps the company's public story straight."),
  ("content-writer", "Content Writer", "Writes the content that brings customers in: web pages, posts and articles, clear and on brand."),
  ("telecalling-executive", "Telecalling Executive", "Prepares call lists, scripts and follow-up notes for the sales team, and logs every outcome."),
 ]),
 ("Sales & Marketing", "Customer & Retail", "🛍️", [
  ("customer-service-executive", "Customer Service Executive", "Answers customers politely and fast: orders, complaints and questions, solved or escalated with a clear note."),
  ("retail-executive", "Retail Executive", "Runs the shop's office side: promotions, stock reports and supplier follow-ups, so the shelves and the numbers match."),
 ]),
 ("People & Operations", "HR & Operations", "👥", [
  ("hr-executive", "HR Executive", "Runs HR paperwork: leave, attendance, onboarding and staff records, kept fair and up to date."),
  ("operations-manager", "Operations Manager", "Runs day-to-day operations: plans, people and suppliers, and reports what is on track and what is stuck."),
 ]),
 ("People & Operations", "Business & Planning", "📈", [
  ("business-consultant", "Business Consultant", "Studies the business and says what to fix: costs, sales and processes, with a clear plan and the numbers behind it."),
  ("corporate-planning-executive", "Corporate Planning Executive", "Prepares plans and strategy documents: targets, budgets and the steps to reach them."),
 ]),
 ("Healthcare & Education", "Care & Learning", "🏥", [
  ("healthcare-administrator", "Healthcare Administrator", "Runs the clinic's office side: appointments, patient records and billing follow-ups, kept accurate and private."),
  ("education-coordinator", "Education Coordinator", "Runs the school or training centre's office side: admissions, timetables and parent messages, kept in order."),
  ("translator", "Translator", "Translates documents and messages accurately, keeping the meaning, the tone and the numbers right."),
  ("editor", "Editor", "Edits the team's writing: fixes errors, tightens the language, and makes sure it reads clearly."),
  ("journalist", "Journalist", "Researches a story and writes it up: facts checked, sources named, and the story told straight."),
 ]),
 ("Engineering & Industry", "Design & Production", "🏭", [
  ("architect", "Architect", "Prepares design briefs, specifications and coordination notes for a building project, and checks drawings against the brief."),
  ("industrial-engineer", "Industrial Engineer", "Studies how the work flows and finds the waste: better layouts, better schedules, and the numbers to prove it."),
  ("production-planner", "Production Planner", "Plans production: what to make, when, and what materials are needed, so orders ship on time."),
 ]),
 ("IT & Design", "Hardware & Creative", "🖥️", [
  ("it-hardware-engineer", "IT Hardware Engineer", "Specifies hardware, compares suppliers and prices, and keeps asset and warranty records in order."),
  ("graphic-designer", "Graphic Designer", "Prepares design briefs, checks artwork against the brand, and keeps the asset list and supplier notes in order."),
 ]),
 ("Trade & Logistics", "Import, Export & Shipping", "🚢", [
  ("import-export-executive", "Import & Export Executive", "Prepares import and export paperwork: invoices, packing lists and customs documents, checked and on time."),
  ("shipping-coordinator", "Shipping Coordinator", "Books shipments, tracks them, and keeps the delivery documents and proof of delivery in order."),
  ("general-trading-executive", "General Trading Executive", "Runs the trading desk: supplier and customer quotes, orders and follow-ups, so deals close on time."),
 ]),
 ("Property & Hospitality", "Property", "🏠", [
  ("real-estate-agent", "Real Estate Agent", "Handles listings and buyers: property details, viewings and follow-ups, with honest descriptions and prices."),
  ("interior-designer", "Interior Designer", "Prepares interior design briefs, material lists and supplier notes for a fit-out, and checks them against the budget."),
 ]),
 ("Property & Hospitality", "Hospitality & Travel", "✈️", [
  ("hotel-manager", "Hotel Manager", "Runs the hotel's office side: bookings, guest messages, rosters and reports, so the hotel runs smoothly."),
  ("restaurant-manager", "Restaurant Manager", "Runs the restaurant's office side: rosters, supplier orders and cost checks, so service runs smoothly."),
  ("event-manager", "Event Manager", "Plans events: venue, vendors, schedule and budget, and keeps every booking and payment on track."),
  ("travel-agent", "Travel Agent", "Plans trips and books travel: itineraries, tickets and hotels, with the costs and documents checked."),
 ]),
]

# Build the sector roles into OFFICE_ROLES: each one gets the same shape
# as a core role (label, avatar, sector, group, instructions).
for _sector, _group, _avatar, _roles in SECTOR_ROLES:
    for _rid, _title, _job in _roles:
        OFFICE_ROLES[_rid] = {
            "label": _title, "avatar": _avatar, "sector": _sector, "group": _group,
            "instructions": ("You are {name}, the " + _title + " on this office's AI team. "
                             + _job + " You work from the brief, the shared office memory and the "
                             "previous team members' outputs, and report back in plain text so the "
                             "next team member can use it.")}

# The order a team job runs in: research first, build/write second,
# review last. Roles not listed here run in hire order after these.
ROLE_ORDER = ["researcher", "developer", "writer", "sales", "finance", "legal", "recruiter", "teacher", "assistant", "analyst"]
ROLE_ORDER += [r[0] for _s, _g, _a, _roles in SECTOR_ROLES for r in _roles]

def load_offices():
    return _load_json(OFFICES_FILE, [])

def save_offices(offices):
    _save_json(OFFICES_FILE, offices)

def get_office(office_id: str):
    return next((o for o in load_offices() if o["id"] == office_id), None)

def _office_dir(office_id: str) -> Path:
    d = OFFICES_DIR / office_id
    d.mkdir(parents=True, exist_ok=True)
    return d

def load_office_memory(office_id: str) -> str:
    p = _office_dir(office_id) / "memory.md"
    return p.read_text(encoding="utf-8") if p.exists() else ""

def append_office_memory(office_id: str, text: str):
    p = _office_dir(office_id) / "memory.md"
    with p.open("a", encoding="utf-8") as f:
        f.write("\n" + text.strip() + "\n")

def load_blackboard(office_id: str):
    return _load_json(_office_dir(office_id) / "blackboard.json", [])

def append_blackboard(office_id: str, sender: str, recipient: str, text: str):
    board = load_blackboard(office_id)
    board.append({"ts": int(time.time()), "from": sender, "to": recipient,
                  "text": text})
    _save_json(_office_dir(office_id) / "blackboard.json", board[-200:])
    return board

@app.get("/api/office/roles")
def office_roles():
    # Every hireable role, grouped by sector — the Office UI builds its
    # hire dropdown from this. Core roles have sector "General".
    jobs = {rid: job for _s, _g, _a, roles in SECTOR_ROLES for rid, _t, job in roles}
    out = []
    for rid, r in OFFICE_ROLES.items():
        if rid == "boss":
            continue
        out.append({"id": rid, "label": r["label"], "avatar": r["avatar"],
                    "sector": r.get("sector", "General"), "group": r.get("group", "Core team"),
                    "job": jobs.get(rid, "")})
    return out

@app.get("/api/offices")
def list_offices():
    return [{"id": o["id"], "name": o["name"], "description": o.get("description", ""),
             "members": len(o.get("members", [])), "jobs": len(o.get("jobs", [])),
             "created_at": o.get("created_at")} for o in load_offices()]

@app.post("/api/offices")
def create_office(body: dict):
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "Give the office a name, e.g. Acme Paper Co.")
    offices = load_offices()
    office_id = uuid.uuid4().hex[:8]
    boss_name = (body.get("boss_name") or "Boss").strip()
    boss_bot = create_bot(BotCreate(
        name=boss_name, avatar="👔",
        instructions=OFFICE_ROLES["boss"]["instructions"].format(name=boss_name),
        job=f"Office Manager (boss) of the {name} office. Plan work, assign it to the team, check results, report back.",
        provider=(body.get("provider") or DEFAULT_PROVIDER),
        model=(body.get("model") or "")))
    office = {"id": office_id, "name": name,
              "description": (body.get("description") or "").strip(),
              "boss_bot_id": boss_bot["id"],
              "members": [{"id": uuid.uuid4().hex[:8], "name": boss_name,
                           "role": "boss", "bot_id": boss_bot["id"],
                           "avatar": "👔", "hired_at": int(time.time())}],
              "jobs": [], "created_at": int(time.time())}
    offices.append(office); save_offices(offices)
    d = _office_dir(office_id)
    (d / "memory.md").write_text(
        f"# {name} — office memory\n\nShared memory for this office's AI team. "
        "Everything the team learns goes here, so it survives sessions.\n\n## Facts\n",
        encoding="utf-8")
    _save_json(d / "blackboard.json", [])
    return office

@app.get("/api/offices/{office_id}")
def get_office_detail(office_id: str):
    office = get_office(office_id)
    if not office:
        raise HTTPException(404, "Office not found")
    detail = dict(office)
    detail["memory"] = load_office_memory(office_id)
    detail["blackboard"] = load_blackboard(office_id)[-50:]
    return detail

@app.delete("/api/offices/{office_id}")
def delete_office(office_id: str):
    offices = load_offices()
    office = next((o for o in offices if o["id"] == office_id), None)
    if not office:
        raise HTTPException(404, "Office not found")
    offices = [o for o in offices if o["id"] != office_id]
    save_offices(offices)
    shutil.rmtree(_office_dir(office_id), ignore_errors=True)
    return {"deleted": office_id,
            "note": "The office is gone. Its team bots stay in Bots — delete them there if you don't need them."}

@app.post("/api/offices/{office_id}/members")
def hire_member(office_id: str, body: dict):
    office = get_office(office_id)
    if not office:
        raise HTTPException(404, "Office not found")
    role = (body.get("role") or "assistant").lower()
    if role not in OFFICE_ROLES or role == "boss":
        raise HTTPException(400, "Role must be one of the office roles (see GET /api/office/roles). The office has one boss already.")
    name = (body.get("name") or "").strip() or OFFICE_ROLES[role]["label"]
    bot = create_bot(BotCreate(
        name=name, avatar=OFFICE_ROLES[role]["avatar"],
        instructions=OFFICE_ROLES[role]["instructions"].format(name=name),
        job=f"{OFFICE_ROLES[role]['label']} on the {office['name']} office AI team.",
        template=(body.get("template") or ""),
        provider=(body.get("provider") or DEFAULT_PROVIDER),
        model=(body.get("model") or "")))
    member = {"id": uuid.uuid4().hex[:8], "name": name, "role": role,
              "bot_id": bot["id"], "avatar": OFFICE_ROLES[role]["avatar"],
              "hired_at": int(time.time())}
    offices = load_offices()
    for o in offices:
        if o["id"] == office_id:
            o.setdefault("members", []).append(member)
    save_offices(offices)
    append_blackboard(office_id, "Boss", name, f"{name} joined the office as {OFFICE_ROLES[role]['label']}.")
    return member

@app.delete("/api/offices/{office_id}/members/{member_id}")
def fire_member(office_id: str, member_id: str):
    offices = load_offices()
    for o in offices:
        if o["id"] == office_id:
            before = len(o.get("members", []))
            o["members"] = [m for m in o.get("members", []) if m["id"] != member_id]
            if len(o["members"]) == before:
                raise HTTPException(404, "Team member not found")
            save_offices(offices)
            return {"removed": member_id}
    raise HTTPException(404, "Office not found")

@app.post("/api/offices/{office_id}/memory")
def add_office_memory(office_id: str, body: dict):
    office = get_office(office_id)
    if not office:
        raise HTTPException(404, "Office not found")
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "Write something to remember.")
    append_office_memory(office_id, f"- {text}")
    return {"memory": load_office_memory(office_id)}

@app.post("/api/offices/{office_id}/jobs")
def run_office_job(office_id: str, body: dict):
    office = get_office(office_id)
    if not office:
        raise HTTPException(404, "Office not found")
    title = (body.get("title") or "").strip()
    brief = (body.get("brief") or "").strip()
    if not title or not brief:
        raise HTTPException(400, "Give the job a title and a brief for the team.")
    members = [m for m in office.get("members", []) if m["role"] != "boss"]
    members.sort(key=lambda m: ROLE_ORDER.index(m["role"]) if m["role"] in ROLE_ORDER else 99)
    boss = next((m for m in office.get("members", []) if m["role"] == "boss"), None)
    memory = load_office_memory(office_id)
    steps = []
    previous = ""
    workers = members or ([boss] if boss else [])
    for member in workers:
        bot = get_bot(member["bot_id"])
        if not bot:
            continue
        prompt = (f"Office: {office['name']}\nJob: {title}\nBrief: {brief}\n\n"
                  f"Shared office memory:\n{memory}\n\n"
                  f"Work done so far by the team:\n{previous or '(nothing yet — you are first)'}\n\n"
                  f"Your role: {OFFICE_ROLES[member['role']]['label']}. Do your part now and report back in plain text, so the next team member can use it.")
        append_blackboard(office_id, "Boss", member["name"],
                          f"Your part of '{title}': {brief[:300]}")
        reply, trace, _extra = run_agent(bot, prompt)
        steps.append({"member": member["name"], "role": member["role"],
                      "output": reply, "tools": [t.get("tool") for t in trace]})
        previous += f"\n\n--- {member['name']} ({OFFICE_ROLES[member['role']]['label']}):\n{reply}"
        append_blackboard(office_id, member["name"], "Boss",
                          f"Done with my part of '{title}'.")
    job = {"id": uuid.uuid4().hex[:8], "title": title, "brief": brief,
           "status": "done", "steps": steps, "created_at": int(time.time())}
    offices = load_offices()
    for o in offices:
        if o["id"] == office_id:
            o.setdefault("jobs", []).append(job)
            o["jobs"] = o["jobs"][-20:]
    save_offices(offices)
    append_office_memory(
        office_id,
        f"- Job '{title}' ({time.strftime('%Y-%m-%d')}): {brief[:200]} "
        f"Done by: {', '.join(s['member'] for s in steps) or 'nobody (no team yet)'}.")
    return job

@app.get("/api/offices/{office_id}/jobs")
def list_office_jobs(office_id: str):
    office = get_office(office_id)
    if not office:
        raise HTTPException(404, "Office not found")
    return office.get("jobs", [])

@app.delete("/api/bots/{bot_id}")
def delete_bot(bot_id: str):
    bots = [b for b in load_bots() if b["id"] != bot_id]
    save_bots(bots)
    for p in (chat_path(bot_id), memory_path(bot_id)):
        p.unlink(missing_ok=True)
    return {"deleted": bot_id}

@app.get("/api/bots/{bot_id}/chat")
def get_chat(bot_id: str):
    if not get_bot(bot_id):
        raise HTTPException(404, "Bot not found")
    return load_chat(bot_id)

@app.post("/api/bots/{bot_id}/chat")
def post_chat(bot_id: str, body: ChatIn):
    bot = get_bot(bot_id)
    if not bot:
        raise HTTPException(404, "Bot not found")
    ws_id = (body.workspace or "default").strip() or "default"
    reply, trace, extra = run_agent(bot, body.message.strip(), workspace_id=ws_id)
    out = {"reply": reply, "tools": trace, "bot": bot["id"], "workspace": ws_id}
    out.update(extra or {})
    return out

@app.post("/api/bots/{bot_id}/chat/reset")
def reset_chat(bot_id: str):
    if not get_bot(bot_id):
        raise HTTPException(404, "Bot not found")
    save_chat(bot_id, [])
    return {"reset": bot_id}

@app.get("/api/bots/{bot_id}/memory")
def get_memory(bot_id: str):
    if not get_bot(bot_id):
        raise HTTPException(404, "Bot not found")
    return load_memory(bot_id)

@app.post("/api/bots/{bot_id}/memory")
def add_memory(bot_id: str, body: MemoryIn):
    if not get_bot(bot_id):
        raise HTTPException(404, "Bot not found")
    mem = load_memory(bot_id)
    mem.setdefault("facts", []).append(body.fact.strip())
    save_memory(bot_id, mem)
    return mem


# ---------- Hermes-style persistent agents + autonomous tasks ----------
# A persistent agent keeps working in the background: give it a goal and
# it works through the task on its own (multi-step tool loop, up to 8
# turns per run, like Hermes Agent), remembers what it did in its
# long-term memory, and moves on to the next task. A non-persistent bot
# only works when you chat with it. Tasks are stored in
# data/agent_tasks.json; the worker thread below picks up pending tasks
# for persistent bots every 30 seconds.
TASKS_FILE = DATA_DIR / "agent_tasks.json"

def load_tasks():
    tasks = _load_json(TASKS_FILE, None)
    return tasks if isinstance(tasks, list) else []

def save_tasks(tasks):
    _save_json(TASKS_FILE, tasks)
    return tasks

def _run_task(task: dict):
    """Run one autonomous task: goal -> run_agent -> steps + result.
    Appends a one-line summary to the bot's long-term memory, so the
    agent remembers what it did between sessions (Hermes-style)."""
    tasks = load_tasks()
    stored = next((x for x in tasks if x["id"] == task["id"]), None)
    if not stored:
        return None
    bot = get_bot(task["bot_id"])
    if not bot:
        stored["status"] = "failed"
        stored["result"] = "Bot was deleted before the task ran."
        stored["finished_at"] = int(time.time())
        save_tasks(tasks)
        return stored
    stored["status"] = "running"
    save_tasks(tasks)
    try:
        reply, trace, extra = run_agent(bot, task["goal"])
        stored["steps"] = trace or []
        stored["result"] = reply
        stored["status"] = "failed" if (extra or {}).get("error") else "done"
    except Exception as e:
        stored["status"] = "failed"
        stored["result"] = f"Task failed: {e}"
    stored["finished_at"] = int(time.time())
    save_tasks(tasks)
    # Remember what happened, in the bot's own words, for next time.
    try:
        mem = load_memory(bot["id"])
        summary = (stored.get("result") or "")[:200].replace("\n", " ").strip()
        mem.setdefault("facts", []).append(
            f"Completed task '{task['goal'][:80]}' ({stored['status']}): {summary}")
        save_memory(bot["id"], mem)
    except Exception:
        pass
    return stored

def _persistent_worker():
    """Background loop: every 30s, run the oldest pending task of each
    persistent bot, one at a time. Never crashes the app."""
    while True:
        try:
            time.sleep(30)
            bots = {b["id"]: b for b in load_bots() if b.get("persistent")}
            if not bots:
                continue
            for task in load_tasks():
                if task.get("status") == "pending" and task.get("bot_id") in bots:
                    _run_task(task)
                    break  # one task per loop, then re-check
        except Exception:
            time.sleep(30)

class TaskIn(BaseModel):
    goal: str = Field(min_length=1)

@app.get("/api/bots/{bot_id}/tasks")
def list_tasks(bot_id: str):
    if not get_bot(bot_id):
        raise HTTPException(404, "Bot not found")
    return [x for x in load_tasks() if x["bot_id"] == bot_id]

@app.post("/api/bots/{bot_id}/tasks", status_code=201)
def add_task(bot_id: str, body: TaskIn):
    bot = get_bot(bot_id)
    if not bot:
        raise HTTPException(404, "Bot not found")
    tasks = load_tasks()
    task = {"id": uuid.uuid4().hex[:8], "bot_id": bot_id,
            "goal": body.goal.strip(), "status": "pending",
            "steps": [], "result": "", "created_at": int(time.time()),
            "finished_at": None}
    tasks.append(task)
    save_tasks(tasks)
    return task

@app.post("/api/bots/{bot_id}/tasks/{task_id}/run")
def run_task_now(bot_id: str, task_id: str):
    if not get_bot(bot_id):
        raise HTTPException(404, "Bot not found")
    task = next((x for x in load_tasks() if x["id"] == task_id and x["bot_id"] == bot_id), None)
    if not task:
        raise HTTPException(404, "Task not found")
    if task.get("status") == "running":
        raise HTTPException(409, "Task is already running")
    return _run_task(task)

@app.delete("/api/bots/{bot_id}/tasks/{task_id}")
def delete_task(bot_id: str, task_id: str):
    tasks = [x for x in load_tasks() if not (x["id"] == task_id and x["bot_id"] == bot_id)]
    save_tasks(tasks)
    return {"deleted": task_id}


# ---------- Settings + Library endpoints (one store each, shared by both) ----------
@app.get("/api/settings")
def get_settings():
    st = load_settings()
    st["data_location"] = str(DATA_DIR)
    st["app_version"] = APP_VERSION
    st["workspace_absolute"] = str(WORKSPACE_DIR)
    return st

@app.post("/api/settings")
def update_settings(body: dict):
    st = load_settings()
    for k in ("default_provider", "default_model", "workspace_folder", "theme"):
        if body.get(k):
            st[k] = str(body[k]).strip()
    if st.get("default_provider", "").lower() not in PROVIDERS:
        st["default_provider"] = "lmstudio"
    if st.get("theme") not in ("light", "dark"):
        st["theme"] = "light"
    save_settings(st)
    _apply_settings()
    globals()["DEFAULT_PROVIDER"] = st["default_provider"]
    globals()["DEFAULT_MODEL"] = st["default_model"]
    return get_settings()

@app.post("/api/settings/reset")
def reset_settings():
    try:
        SETTINGS_FILE.unlink(missing_ok=True)
    except Exception:
        pass
    _apply_settings()
    globals()["DEFAULT_PROVIDER"] = _default_settings()["default_provider"]
    globals()["DEFAULT_MODEL"] = _default_settings()["default_model"]
    return get_settings()

@app.get("/api/connectors")
def list_connectors():
    store = load_connectors_store()
    providers = []
    for pid in PROVIDERS:
        cfg = get_provider_config(pid)
        status, detail, last = _provider_status(pid, store)
        providers.append({**cfg, "enabled": store["providers"].get(pid, {}).get("enabled", True),
                          "status": status, "status_detail": detail, "last_test": last or None,
                          "masked": _mask_key(os.getenv(cfg["key_env"]) or "") if cfg.get("key_env") else ""})
    services = []
    for svc in SERVICE_CONNECTORS:
        saved = store["services"].get(svc["id"], {})
        last = store["last_test"].get(svc["id"]) or {}
        # Honest status from the last real Test; never "connected" without one.
        status = last.get("status") if last.get("status") in ("connected", "failed") else "not_connected"
        services.append({**svc, "enabled": saved.get("enabled", False),
                         "status": status,
                         "status_detail": last.get("detail", "") if last else "",
                         "last_test": last or None})
    return {"providers": providers, "services": services}

@app.post("/api/connectors/{kind}/{cid}/toggle")
def toggle_connector(kind: str, cid: str, body: dict):
    store = load_connectors_store()
    if kind == "provider" and cid in PROVIDERS:
        store["providers"].setdefault(cid, {})["enabled"] = bool(body.get("enabled", True))
    elif kind == "service" and any(x["id"] == cid for x in SERVICE_CONNECTORS):
        store["services"].setdefault(cid, {})["enabled"] = bool(body.get("enabled", True))
    else:
        raise HTTPException(404, "Connector not found")
    save_connectors_store(store)
    return {"kind": kind, "id": cid, "enabled": body.get("enabled")}

def _test_service_connector(svc: dict):
    """Real Test for a service connector. Returns (status, detail).
    Token-based connectors call the service's own "who am I" endpoint
    with the saved token; OAuth-only connectors (no token_env) stay
    config-only and honestly report not_connected with the setup text.
    Tokens are never logged or returned."""
    token_env = svc.get("token_env")
    if not token_env:
        return "not_connected", svc["setup"]
    token = (os.getenv(token_env) or "").strip()
    if not token:
        return "not_connected", f"No token saved - add {token_env} in Settings > Secure store. " + svc["setup"]
    cid = svc["id"]
    try:
        with _http_client(timeout=15, external=True) as c:
            if cid == "github":
                r = c.get("https://api.github.com/user",
                          headers={"Authorization": f"Bearer {token}",
                                   "Accept": "application/vnd.github+json"})
                if r.status_code == 200:
                    return "connected", f"Connected as {r.json().get('login', '?')}."
            elif cid == "slack":
                r = c.post("https://slack.com/api/auth.test",
                           headers={"Authorization": f"Bearer {token}"})
                d = r.json()
                if d.get("ok"):
                    return "connected", f"Connected as {d.get('user', '?')} on {d.get('team', '?')}."
            elif cid == "telegram":
                r = c.get(f"https://api.telegram.org/bot{token}/getMe")
                d = r.json()
                if d.get("ok") and d.get("result"):
                    res = d["result"]
                    return "connected", f"Connected as @{res.get('username', '?')} ({res.get('first_name', '')})."
            elif cid == "discord":
                r = c.get("https://discord.com/api/users/@me",
                          headers={"Authorization": f"Bot {token}"})
                if r.status_code == 200:
                    d = r.json()
                    return "connected", f"Connected as {d.get('username', '?')}."
            elif cid == "notion":
                r = c.get("https://api.notion.com/v1/users/me",
                          headers={"Authorization": f"Bearer {token}",
                                   "Notion-Version": "2022-06-28"})
                if r.status_code == 200:
                    d = r.json()
                    return "connected", f"Connected as {d.get('name', '?')} ({d.get('type', 'bot')})."
            elif cid == "trello":
                key = (os.getenv(svc.get("key_env", "TRELLO_API_KEY")) or "").strip()
                if not key:
                    return "not_connected", "No API key saved - add TRELLO_API_KEY in Settings > Secure store. " + svc["setup"]
                r = c.get("https://api.trello.com/1/members/me",
                          params={"key": key, "token": token})
                if r.status_code == 200:
                    d = r.json()
                    return "connected", f"Connected as {d.get('username', '?')} ({d.get('fullName', '')})."
            elif cid == "airtable":
                r = c.get("https://api.airtable.com/v0/meta/bases",
                          headers={"Authorization": f"Bearer {token}"})
                if r.status_code == 200:
                    n = len((r.json() or {}).get("bases") or [])
                    return "connected", f"Connected - {n} base(s) visible to this token."
            elif cid == "stripe":
                r = c.get("https://api.stripe.com/v1/account",
                          headers={"Authorization": f"Bearer {token}"})
                if r.status_code == 200:
                    d = r.json()
                    return "connected", f"Connected to Stripe account {d.get('display_name') or d.get('email') or d.get('id', '?')}."
            elif cid == "gitlab":
                r = c.get("https://gitlab.com/api/v4/user",
                          headers={"Authorization": f"Bearer {token}"})
                if r.status_code == 200:
                    return "connected", f"Connected as {r.json().get('username', '?')}."
            elif cid == "dropbox":
                r = c.post("https://api.dropboxapi.com/2/users/get_current_account",
                           headers={"Authorization": f"Bearer {token}",
                                    "Content-Type": "application/json"}, content=b"null")
                if r.status_code == 200:
                    d = r.json()
                    return "connected", f"Connected as {(d.get('name') or {}).get('display_name', '?')}."
            elif cid == "zoom":
                r = c.get("https://api.zoom.us/v2/users/me",
                          headers={"Authorization": f"Bearer {token}"})
                if r.status_code == 200:
                    d = r.json()
                    return "connected", f"Connected as {d.get('email', '?')}."
            elif cid == "hubspot":
                r = c.get(f"https://api.hubapi.com/oauth/v1/access-tokens/{token}")
                if r.status_code == 200:
                    d = r.json()
                    return "connected", f"Connected - HubSpot token for user {d.get('user', '?')}."
            else:
                return "not_connected", svc["setup"]
        if r.status_code == 401:
            return "failed", "Token rejected (HTTP 401) - check the token in Secure store."
        if r.status_code == 403:
            return "failed", "Token rejected (HTTP 403) - it may lack the permission this check needs."
        return "failed", f"Service answered HTTP {r.status_code} - the token may be wrong or expired."
    except Exception as e:
        return "failed", f"Could not reach the service: {e}"

@app.post("/api/connectors/{kind}/{cid}/test")
def test_connector(kind: str, cid: str):
    store = load_connectors_store()
    if kind == "provider" and cid in PROVIDERS:
        reachable, detail, configured = check_provider(cid, real=True)
        cfg = get_provider_config(cid)
        if cfg["requires_key"] and not configured:
            status = "not_connected"
        elif reachable:
            status = "connected"
        else:
            status = "failed"
        from datetime import datetime as _dt
        result = {"id": cid, "status": status, "detail": detail, "configured": configured,
                  "ts": int(time.time()),
                  "checked_at": _dt.now().isoformat(timespec="seconds")}
        store["last_test"][cid] = result
        save_connectors_store(store)
        return result
    if kind == "service" and any(x["id"] == cid for x in SERVICE_CONNECTORS):
        svc = next(x for x in SERVICE_CONNECTORS if x["id"] == cid)
        from datetime import datetime as _dt
        status, detail = _test_service_connector(svc)
        result = {"id": cid, "status": status, "detail": detail, "ts": int(time.time()),
                  "checked_at": _dt.now().isoformat(timespec="seconds")}
        store["last_test"][cid] = result
        save_connectors_store(store)
        return result
    raise HTTPException(404, "Connector not found")

def _test_mcp_server(server: dict):
    target = (server.get("command_or_url") or "").strip()
    if not target:
        return {"status": "error", "detail": "No command or URL set for this server.", "tools": []}
    if target.startswith("http://") or target.startswith("https://"):
        try:
            with _http_client(timeout=10, external=not _is_local_url(target)) as _c:
                r = _c.post(target, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
            data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            tools = (data.get("result") or {}).get("tools") or []
            if tools:
                return {"status": "reachable", "detail": f"HTTP {r.status_code}", "tools": [t.get("name") for t in tools]}
            return {"status": "reachable", "detail": f"Server responded HTTP {r.status_code} but did not return a tools list.", "tools": []}
        except Exception as e:
            return {"status": "error", "detail": str(e), "tools": []}
    parts = target.split()
    if not parts or shutil.which(parts[0]) is None:
        return {"status": "error", "detail": f"Command not found on this computer: {parts[0] if parts else ''}", "tools": []}
    try:
        proc = subprocess.Popen(parts, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, cwd=WORKSPACE_DIR)
        lines = [
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                        "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "localbotz", "version": APP_VERSION}}}),
            json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}),
        ]
        out, _err = proc.communicate(input="\n".join(lines) + "\n", timeout=10)
        tools = []
        for line in (out or "").splitlines():
            try:
                msg = json.loads(line)
                found = (msg.get("result") or {}).get("tools") or []
                tools += [t.get("name") for t in found if isinstance(t, dict)]
            except Exception:
                continue
        return {"status": "reachable" if tools else "error",
                "detail": "MCP server answered." if tools else "Server started but did not return a tools list.",
                "tools": tools}
    except subprocess.TimeoutExpired:
        return {"status": "error", "detail": "Timed out waiting for the MCP server (10s).", "tools": []}
    except Exception as e:
        return {"status": "error", "detail": str(e), "tools": []}

@app.get("/api/mcp-servers")
def list_mcp():
    return load_mcp_servers()

@app.post("/api/mcp-servers", status_code=201)
def add_mcp(body: dict):
    servers = load_mcp_servers()
    srv = {"id": uuid.uuid4().hex[:8], "name": (body.get("name") or "MCP server").strip(),
           "command_or_url": (body.get("command_or_url") or "").strip(),
           "env": body.get("env") or {}, "enabled": True,
           "status": "unknown", "tools": [], "last_test": None}
    servers.append(srv); save_mcp_servers(servers)
    return srv

@app.delete("/api/mcp-servers/{sid}")
def delete_mcp(sid: str):
    save_mcp_servers([x for x in load_mcp_servers() if x["id"] != sid])
    return {"deleted": sid}

@app.post("/api/mcp-servers/{sid}/toggle")
def toggle_mcp(sid: str, body: dict):
    servers = load_mcp_servers()
    srv = next((x for x in servers if x["id"] == sid), None)
    if not srv:
        raise HTTPException(404, "MCP server not found")
    srv["enabled"] = bool(body.get("enabled", True))
    save_mcp_servers(servers)
    return srv

@app.post("/api/mcp-servers/{sid}/test")
def test_mcp(sid: str):
    servers = load_mcp_servers()
    srv = next((x for x in servers if x["id"] == sid), None)
    if not srv:
        raise HTTPException(404, "MCP server not found")
    result = _test_mcp_server(srv)
    srv["status"] = result["status"]; srv["tools"] = result["tools"]
    srv["last_test"] = {"detail": result["detail"], "ts": int(time.time())}
    save_mcp_servers(servers)
    return {**srv, "detail": result["detail"]}

@app.get("/api/skills")
def list_skills():
    return load_skills()

@app.post("/api/skills", status_code=201)
def add_skill(body: dict):
    skills = load_skills()
    skill = {"id": uuid.uuid4().hex[:8], "name": (body.get("name") or "Custom skill").strip(),
             "instructions": (body.get("instructions") or "").strip(),
             "source": (body.get("source") or "").strip(), "builtin": False, "enabled": True}
    skills.append(skill); save_skills(skills)
    return skill

@app.delete("/api/skills/{sid}")
def delete_skill(sid: str):
    skills = load_skills()
    target = next((x for x in skills if x["id"] == sid), None)
    if not target:
        raise HTTPException(404, "Skill not found")
    if target.get("builtin"):
        raise HTTPException(400, "Built-in skills cannot be deleted (disable them instead)")
    save_skills([x for x in skills if x["id"] != sid])
    return {"deleted": sid}

@app.post("/api/bots/{bot_id}/skills")
def set_bot_skill(bot_id: str, body: dict):
    bot = get_bot(bot_id)
    if not bot:
        raise HTTPException(404, "Bot not found")
    skill_id = body.get("skill_id", "")
    if skill_id not in [x["id"] for x in load_skills()]:
        raise HTTPException(404, "Skill not found")
    skills = list(bot.get("skills") or [])
    if body.get("enabled", True) and skill_id not in skills:
        skills.append(skill_id)
    if not body.get("enabled", True) and skill_id in skills:
        skills.remove(skill_id)
    bots = load_bots()
    for b in bots:
        if b["id"] == bot_id:
            b["skills"] = skills
    save_bots(bots)
    return {"bot": bot_id, "skills": skills}

@app.get("/api/wallet")
def get_wallet():
    w = load_wallet()
    usage = w.get("usage", [])
    total_cost = round(sum(x.get("est_cost_usd", 0) for x in usage), 4)
    total_calls = sum(x.get("calls", 0) for x in usage)
    by_provider = {}
    for x in usage:
        key = f"{x.get('provider')}/{x.get('model')}"
        by_provider.setdefault(key, {"calls": 0, "est_cost_usd": 0.0})
        by_provider[key]["calls"] += x.get("calls", 0)
        by_provider[key]["est_cost_usd"] = round(by_provider[key]["est_cost_usd"] + x.get("est_cost_usd", 0), 4)
    budget = float(w.get("monthly_budget_usd") or 0)
    over = budget > 0 and total_cost > budget
    return {"monthly_budget_usd": budget, "alert_enabled": bool(w.get("alert_enabled")),
            "total_calls": total_calls, "total_est_cost_usd": total_cost,
            "over_budget": over, "alert": over and bool(w.get("alert_enabled")),
            "by_provider_model": by_provider, "usage": usage[-50:]}

@app.post("/api/wallet/budget")
def set_budget(body: dict):
    w = load_wallet()
    w["monthly_budget_usd"] = float(body.get("monthly_budget_usd") or 0)
    w["alert_enabled"] = bool(body.get("alert_enabled", False))
    save_wallet(w)
    return get_wallet()

@app.post("/api/wallet/reset")
def reset_wallet():
    save_wallet({"monthly_budget_usd": 0.0, "alert_enabled": False, "usage": []})
    return get_wallet()

def _secure_store_entries():
    entries = []
    for pid, spec in PROVIDERS.items():
        if spec.get("key_env"):
            key = os.getenv(spec["key_env"])
            entries.append({"id": pid, "label": spec["label"], "key_env": spec["key_env"],
                            "has_key": bool(key), "masked": _mask_key(key or "")})
    for ch, info in MESSAGING_CHANNELS.items():
        key = os.getenv(info["token_env"])
        entries.append({"id": ch, "label": info["label"] + " token", "key_env": info["token_env"],
                        "has_key": bool(key), "masked": _mask_key(key or "")})
    for key_env, label in (("SLACK_BOT_TOKEN", "Slack bot token"), ("GITHUB_TOKEN", "GitHub token"),
                           ("NOTION_TOKEN", "Notion token")):
        key = os.getenv(key_env)
        entries.append({"id": key_env.lower(), "label": label, "key_env": key_env,
                        "has_key": bool(key), "masked": _mask_key(key or "")})
    return entries

@app.get("/api/secure-store")
def list_secure_store():
    return _secure_store_entries()

@app.post("/api/secure-store")
def set_secure_key(body: dict):
    # Accept a provider/channel id or a key_env name; never return or log the key.
    ident = (body.get("provider") or body.get("id") or body.get("key_env") or "").strip()
    value = (body.get("api_key") or body.get("value") or "").strip()
    if not value:
        raise HTTPException(400, "No key provided")
    key_env = ""
    if ident in PROVIDERS and PROVIDERS[ident].get("key_env"):
        key_env = PROVIDERS[ident]["key_env"]
    elif ident in MESSAGING_CHANNELS:
        key_env = MESSAGING_CHANNELS[ident]["token_env"]
    elif ident in ("slack_bot_token", "github_token", "notion_token"):
        key_env = ident.upper()
    elif ident.endswith("_TOKEN") or ident.endswith("_KEY"):
        key_env = ident.upper()
    if not key_env:
        raise HTTPException(400, "Unknown provider/key for Secure store")
    _set_env_key(key_env, value)
    return {"key_env": key_env, "has_key": True, "masked": _mask_key(value)}

@app.delete("/api/secure-store/{ident}")
def delete_secure_key(ident: str):
    entries = {e["id"]: e for e in _secure_store_entries()}
    if ident in entries:
        _delete_env_key(entries[ident]["key_env"])
        return {"deleted": ident}
    if ident.endswith("_TOKEN") or ident.endswith("_KEY"):
        _delete_env_key(ident.upper())
        return {"deleted": ident}
    raise HTTPException(404, "Key not found")

@app.get("/api/permissions")
def get_permissions():
    return load_permissions()

@app.post("/api/permissions")
def update_permissions(body: dict):
    perms = load_permissions()
    if isinstance(body.get("global"), dict):
        perms["global"].update({k: bool(v) for k, v in body["global"].items()
                               if k in perms["global"]})
    if isinstance(body.get("blocked_paths"), list):
        perms["blocked_paths"] = [str(x).strip() for x in body["blocked_paths"] if str(x).strip()]
    save_permissions(perms)
    return perms

@app.post("/api/permissions/bots/{bot_id}")
def set_bot_permissions(bot_id: str, body: dict):
    if not get_bot(bot_id):
        raise HTTPException(404, "Bot not found")
    perms = load_permissions()
    entry = perms.setdefault("bots", {}).setdefault(bot_id, {})
    if body.get("approval_mode") in ("ask", "auto", "full"):
        entry["approval_mode"] = body["approval_mode"]
    if isinstance(body.get("tools"), dict):
        entry.setdefault("tools", {}).update({k: bool(v) for k, v in body["tools"].items()})
    save_permissions(perms)
    return {"bot": bot_id, **entry}

@app.get("/api/messaging")
def get_messaging():
    d = load_messaging()
    out = {}
    for ch, info in MESSAGING_CHANNELS.items():
        cfg = d.get(ch, {})
        out[ch] = {**cfg, "label": info["label"], "token_env": info["token_env"],
                   "has_token": bool(os.getenv(info["token_env"])),
                   "status": "not_connected", "setup": info["setup"]}
    return out

# ---------- Hermes-style Telegram listener (real, polling) -------------
# Hermes Agent connects to Telegram; LocalBotz does the same, with
# polling instead of a webhook so nothing needs to be exposed to the
# internet. When TELEGRAM_BOT_TOKEN is saved and Telegram is enabled
# with inbound replies, this thread polls getUpdates every 5 seconds.
# Only approved senders get a reply, and only from the bot chosen in
# the Telegram settings (or the first bot). Discord and WhatsApp stay
# config-only: Discord needs a websocket gateway, WhatsApp needs a
# public webhook URL — both are honest "not built yet" in v1.
TELEGRAM_STATE = {"listening": False, "last_poll": None, "last_error": "",
                  "messages_handled": 0}

def _telegram_api(token: str, method: str, payload: dict = None, timeout: int = 15):
    with _http_client(timeout=timeout, external=True) as c:
        r = c.post(f"https://api.telegram.org/bot{token}/{method}",
                   json=payload or {})
    r.raise_for_status()
    return r.json()

def _telegram_listener():
    offset = 0
    state_file = DATA_DIR / "telegram_offset.json"
    try:
        offset = int((_load_json(state_file, {}) or {}).get("offset") or 0)
    except Exception:
        offset = 0
    while True:
        try:
            time.sleep(5)
            token = os.getenv("TELEGRAM_BOT_TOKEN") or ""
            cfg = load_messaging().get("telegram", {})
            if not token or not cfg.get("enabled") or not cfg.get("inbound_replies"):
                TELEGRAM_STATE["listening"] = False
                continue
            TELEGRAM_STATE["listening"] = True
            data = _telegram_api(token, "getUpdates",
                                 {"offset": offset, "timeout": 5}, timeout=15)
            TELEGRAM_STATE["last_poll"] = int(time.time())
            TELEGRAM_STATE["last_error"] = ""
            approved = [str(x) for x in (cfg.get("approved_senders") or [])]
            bot = get_bot(cfg.get("bot_id") or "") or (load_bots() or [None])[0]
            for upd in (data or {}).get("result") or []:
                offset = int(upd.get("update_id") or 0) + 1
                msg = upd.get("message") or {}
                text = (msg.get("text") or "").strip()
                sender = msg.get("from") or {}
                chat = msg.get("chat") or {}
                sender_id = str(sender.get("id") or chat.get("id") or "")
                sender_name = str(sender.get("username") or sender.get("first_name") or "")
                if not text or not bot:
                    continue
                if approved and sender_id not in approved and sender_name not in approved:
                    continue  # not an approved sender: ignore silently
                try:
                    reply, _trace, _extra = run_agent(bot, text)
                except Exception as e:
                    reply = f"Sorry — I hit an error: {e}"
                _telegram_api(token, "sendMessage",
                              {"chat_id": chat.get("id"), "text": reply[:4000]})
                TELEGRAM_STATE["messages_handled"] += 1
            _save_json(state_file, {"offset": offset})
        except Exception as e:
            TELEGRAM_STATE["listening"] = False
            TELEGRAM_STATE["last_error"] = str(e)[:200]
            time.sleep(5)

@app.get("/api/messaging/telegram/status")
def telegram_status():
    token = os.getenv("TELEGRAM_BOT_TOKEN") or ""
    cfg = load_messaging().get("telegram", {})
    return {"listening": TELEGRAM_STATE["listening"],
            "has_token": bool(token),
            "enabled": bool(cfg.get("enabled")),
            "inbound_replies": bool(cfg.get("inbound_replies")),
            "bot_id": cfg.get("bot_id") or "",
            "approved_senders": cfg.get("approved_senders") or [],
            "last_poll": TELEGRAM_STATE["last_poll"],
            "last_error": TELEGRAM_STATE["last_error"],
            "messages_handled": TELEGRAM_STATE["messages_handled"]}

@app.post("/api/messaging/{channel}")
def update_messaging(channel: str, body: dict):
    if channel not in MESSAGING_CHANNELS:
        raise HTTPException(404, "Channel not found")
    d = load_messaging()
    cfg = d.setdefault(channel, {})
    for k in ("enabled", "inbound_replies"):
        if k in body:
            cfg[k] = bool(body[k])
    if body.get("webhook") is not None:
        cfg["webhook"] = str(body["webhook"])
    if isinstance(body.get("approved_senders"), list):
        cfg["approved_senders"] = [str(x).strip() for x in body["approved_senders"] if str(x).strip()]
    if body.get("token"):
        _set_env_key(MESSAGING_CHANNELS[channel]["token_env"], str(body["token"]).strip())
    if body.get("bot_id") is not None:
        cfg["bot_id"] = str(body["bot_id"]).strip()
    save_messaging(d)
    return get_messaging()[channel]

@app.get("/api/devices")
def list_devices():
    try:
        chromium_ok, chromium_path = _check_chromium()
    except Exception as e:
        chromium_ok, chromium_path = False, str(e)
    lm_reachable, _d, _e = check_provider("lmstudio", real=True)
    this_computer = {"id": "this-computer", "name": socket.gethostname(),
                     "kind": "computer", "os": f"{platform.system()} {platform.release()}",
                     "python_version": sys.version.split()[0],
                     "playwright_chromium": chromium_ok, "chromium_path": chromium_path,
                     "lm_studio_reachable": lm_reachable,
                     "browser_status": "ready" if chromium_ok else "chromium not installed - run: playwright install chromium"}
    return {"this_computer": this_computer,
            "browser": {"id": "browser-chromium", "name": "Chromium (Playwright)",
                        "installed": chromium_ok, "status": "ready" if chromium_ok else "not installed"},
            "extra": load_devices_extra()}

@app.post("/api/devices", status_code=201)
def add_device(body: dict):
    devices = load_devices_extra()
    dev = {"id": uuid.uuid4().hex[:8], "name": (body.get("name") or "Device").strip(),
           "kind": (body.get("kind") or "computer").strip()}
    devices.append(dev); save_devices_extra(devices)
    return dev

@app.delete("/api/devices/{did}")
def delete_device(did: str):
    if did in ("this-computer", "browser-chromium"):
        raise HTTPException(400, "This device cannot be removed from here")
    save_devices_extra([x for x in load_devices_extra() if x["id"] != did])
    return {"deleted": did}


# ---------- Operating models: platform / admin / workspaces / voice ----------
@app.get("/api/platform")
def get_platform():
    # Public summary (no keys, no pricing): global mode, fixed models, roster.
    plat = load_platform()
    return {"global_mode": plat.get("global_mode"),
            "fixed_llm": plat.get("fixed_llm"),
            "fixed_voice": plat.get("fixed_voice"),
            "roster": plat.get("roster") or [],
            "modes": list(MODES),
            "admin_enabled": bool((os.getenv("ADMIN_TOKEN") or "").strip())}

@app.get("/api/platform/effective")
def platform_effective(workspace: str = "default"):
    # What the model picker and the agent must enforce for this workspace.
    ws = get_workspace(workspace)
    mode, mode_source = effective_mode(ws)
    plat = load_platform()
    roster = [e for e in (plat.get("roster") or []) if e.get("enabled")]
    byok = load_byok_keys(ws["id"])
    if mode == "fixed":
        allowed_providers = [plat["fixed_llm"]["provider"]]
        allowed_models = [{"provider": plat["fixed_llm"]["provider"],
                           "model": plat["fixed_llm"]["model"]}]
    elif mode == "selectable":
        allowed_providers = sorted({e["provider"] for e in roster
                                    if e.get("type") == "llm"} | {"lmstudio", "ollama"})
        allowed_models = [{"provider": e["provider"], "model": e["model"]}
                          for e in roster if e.get("type") == "llm"]
    else:  # byok: local + providers this workspace has its own key for
        allowed_providers = sorted({"lmstudio", "ollama"}
                                   | {pid for pid, k in byok.items() if k})
        allowed_models = [{"provider": pid, "model": get_provider_config(pid)["default_model"]}
                          for pid in allowed_providers]
    return {"workspace": {"id": ws["id"], "name": ws.get("name"), "mode": ws.get("mode")},
            "mode": mode, "mode_source": mode_source,
            "fixed_llm": plat.get("fixed_llm"), "fixed_voice": plat.get("fixed_voice"),
            "allowed_providers": allowed_providers,
            "allowed_models": allowed_models,
            "roster": roster,
            "byok_providers": sorted([pid for pid, k in byok.items() if k]),
            "wallet_balance": wallet_balance(ws["id"]),
            "low_balance_warn_usd": float(load_pricing().get("low_balance_warn_usd", 1.0))}

# --- Super Admin (token login, v1) ---
@app.post("/api/admin/login")
def admin_login(body: dict):
    token = (os.getenv("ADMIN_TOKEN") or "").strip()
    if not token:
        return {"ok": False, "admin_enabled": False,
                "error": "Super Admin is not enabled — set ADMIN_TOKEN in .env and restart."}
    ok = (body.get("token") or "").strip() == token
    return {"ok": ok, "admin_enabled": True,
            "error": "" if ok else "Wrong admin token."}

@app.get("/api/admin/platform")
def admin_get_platform(request: Request):
    _require_admin(request)
    return load_platform()

@app.post("/api/admin/platform")
def admin_set_platform(request: Request, body: dict):
    _require_admin(request)
    plat = load_platform()
    if body.get("global_mode") in MODES:
        plat["global_mode"] = body["global_mode"]
    for key in ("fixed_llm", "fixed_voice"):
        val = body.get(key)
        if isinstance(val, dict) and val.get("provider") in PROVIDERS and val.get("model"):
            plat[key] = {"provider": val["provider"], "model": str(val["model"]).strip()}
    if isinstance(body.get("roster"), list):
        clean = []
        for e in body["roster"]:
            if not isinstance(e, dict):
                continue
            if e.get("type") not in ("llm", "voice"):
                continue
            if e.get("provider") not in PROVIDERS or not str(e.get("model") or "").strip():
                continue
            clean.append({"id": str(e.get("id") or f"{e['provider']}:{e['model']}"),
                          "type": e["type"], "provider": e["provider"],
                          "model": str(e["model"]).strip(),
                          "label": str(e.get("label") or f"{e['provider']} — {e['model']}"),
                          "enabled": bool(e.get("enabled", True))})
        plat["roster"] = clean
    save_platform(plat)
    return plat

@app.get("/api/admin/pricing")
def admin_get_pricing(request: Request):
    _require_admin(request)
    return load_pricing()

@app.post("/api/admin/pricing")
def admin_set_pricing(request: Request, body: dict):
    _require_admin(request)
    if not isinstance(body, dict) or "per_model" not in body:
        raise HTTPException(400, "Pricing must be an object with a per_model map.")
    pricing = load_pricing()
    for k in ("default_per_1k_input_usd", "default_per_1k_output_usd",
              "low_balance_warn_usd"):
        if body.get(k) is not None:
            pricing[k] = float(body[k])
    if isinstance(body.get("per_model"), dict):
        pricing["per_model"] = body["per_model"]
    if isinstance(body.get("per_char_usd"), dict):
        pricing["per_char_usd"] = body["per_char_usd"]
    save_pricing(pricing)
    return pricing

@app.get("/api/admin/master-keys")
def admin_master_keys(request: Request):
    _require_admin(request)
    return _secure_store_entries()

@app.post("/api/admin/master-keys")
def admin_set_master_key(request: Request, body: dict):
    # Master platform keys go to .env via the Secure store (masked, never returned).
    _require_admin(request)
    return set_secure_key(body)

# --- Workspaces / tenants ---
@app.get("/api/workspaces")
def list_workspaces():
    out = []
    for w in load_workspaces():
        out.append({**w, "wallet_balance": wallet_balance(w["id"]),
                    "byok_providers": sorted([pid for pid, k in load_byok_keys(w["id"]).items() if k])})
    return out

@app.post("/api/workspaces", status_code=201)
def create_workspace(body: dict):
    ws = load_workspaces()
    name = (body.get("name") or "Workspace").strip()
    mode = (body.get("mode") or "inherit").lower()
    if mode not in ("inherit", *MODES):
        mode = "inherit"
    w = {"id": uuid.uuid4().hex[:8], "name": name, "mode": mode,
         "members": [str(m).strip() for m in (body.get("members") or []) if str(m).strip()],
         "created_at": int(time.time())}
    ws.append(w)
    save_workspaces(ws)
    return {**w, "wallet_balance": 0.0}

@app.get("/api/workspaces/{wid}")
def get_one_workspace(wid: str):
    w = get_workspace(wid)
    return {**w, "wallet_balance": wallet_balance(w["id"])}

@app.patch("/api/workspaces/{wid}")
def update_workspace(wid: str, body: dict):
    ws = load_workspaces()
    w = next((x for x in ws if x["id"] == wid), None)
    if not w:
        raise HTTPException(404, "Workspace not found")
    if body.get("name"):
        w["name"] = str(body["name"]).strip()
    if body.get("mode") in ("inherit", *MODES):
        w["mode"] = body["mode"]
    if isinstance(body.get("members"), list):
        w["members"] = [str(m).strip() for m in body["members"] if str(m).strip()]
    save_workspaces(ws)
    return {**w, "wallet_balance": wallet_balance(w["id"])}

@app.delete("/api/workspaces/{wid}")
def delete_workspace(wid: str):
    if wid == "default":
        raise HTTPException(400, "The default workspace cannot be deleted")
    ws = [w for w in load_workspaces() if w["id"] != wid]
    save_workspaces(ws)
    for p in (_wallet_path(wid), _byok_path(wid)):
        try:
            p.unlink(missing_ok=True)
        except Exception:
            pass
    return {"deleted": wid}

@app.get("/api/workspaces/{wid}/wallet")
def workspace_wallet(wid: str):
    w = get_workspace(wid)
    d = load_wallet_ws(w["id"])
    return {"workspace": w["id"], "name": w.get("name"), "currency": "USD",
            "balance_usd": float(d.get("balance_usd") or 0),
            "transactions": d.get("transactions", [])[-50:],
            "usage": d.get("usage", [])[-50:]}

@app.post("/api/workspaces/{wid}/wallet/topup")
def workspace_topup(wid: str, request: Request, body: dict):
    # Manual top-up by the Super Admin only. No real payments in v0.3.
    _require_admin(request)
    w = get_workspace(wid)
    try:
        amount = float(body.get("amount_usd") or 0)
    except Exception:
        raise HTTPException(400, "amount_usd must be a number")
    if amount <= 0:
        raise HTTPException(400, "Top-up amount must be greater than 0")
    d = load_wallet_ws(w["id"])
    d["balance_usd"] = round(float(d.get("balance_usd") or 0) + amount, 6)
    d.setdefault("transactions", []).append(
        {"ts": int(time.time()), "type": "topup", "amount_usd": amount,
         "note": (body.get("note") or "Manual top-up by Super Admin").strip(),
         "balance_after_usd": d["balance_usd"]})
    d["transactions"] = d["transactions"][-500:]
    save_wallet_ws(w["id"], d)
    return {"workspace": w["id"], "balance_usd": d["balance_usd"]}

@app.get("/api/workspaces/{wid}/usage")
def workspace_usage(wid: str):
    w = get_workspace(wid)
    d = load_wallet_ws(w["id"])
    usage = d.get("usage", [])
    total = round(sum(x.get("cost_usd", 0) for x in usage), 6)
    by_model = {}
    for x in usage:
        key = f"{x.get('provider')}/{x.get('model')}"
        by_model.setdefault(key, {"calls": 0, "cost_usd": 0.0, "tokens": 0})
        by_model[key]["calls"] += 1
        by_model[key]["cost_usd"] = round(by_model[key]["cost_usd"] + x.get("cost_usd", 0), 6)
        by_model[key]["tokens"] += int(x.get("input_tokens", 0)) + int(x.get("output_tokens", 0))
    return {"workspace": w["id"], "total_cost_usd": total, "calls": len(usage),
            "by_model": by_model, "usage": usage[-100:]}

# --- BYOK keys (per workspace; masked, never returned in full) ---
@app.get("/api/workspaces/{wid}/byok-keys")
def list_byok_keys(wid: str):
    w = get_workspace(wid)
    keys = load_byok_keys(w["id"])
    out = []
    for pid in PROVIDERS:
        cfg = get_provider_config(pid)
        if not cfg.get("key_env"):
            continue
        k = keys.get(pid) or ""
        out.append({"provider": pid, "label": cfg["label"], "key_env": cfg["key_env"],
                    "has_key": bool(k), "masked": _mask_key(k)})
    return out

@app.post("/api/workspaces/{wid}/byok-keys")
def set_byok_key(wid: str, body: dict):
    w = get_workspace(wid)
    pid = (body.get("provider") or "").strip().lower()
    value = (body.get("api_key") or body.get("value") or "").strip()
    if pid not in PROVIDERS or not get_provider_config(pid).get("key_env"):
        raise HTTPException(400, "Unknown provider for BYOK keys")
    if not value:
        raise HTTPException(400, "No key provided")
    keys = load_byok_keys(w["id"])
    keys[pid] = value
    save_byok_keys(w["id"], keys)
    return {"provider": pid, "has_key": True, "masked": _mask_key(value)}

@app.delete("/api/workspaces/{wid}/byok-keys/{pid}")
def delete_byok_key(wid: str, pid: str):
    w = get_workspace(wid)
    keys = load_byok_keys(w["id"])
    keys.pop(pid.lower(), None)
    save_byok_keys(w["id"], keys)
    return {"deleted": pid}

# --- Voice (TTS): real call when a key is present, honest "not configured" otherwise ---
@app.post("/api/voice/tts")
def voice_tts(body: dict):
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "No text provided")
    if len(text) > 4000:
        raise HTTPException(400, "Text is too long for TTS in v1 (max 4000 characters)")
    ws = get_workspace((body.get("workspace") or "default"))
    mode, _src = effective_mode(ws)
    plat = load_platform()
    model = (body.get("model") or "").strip()
    provider = (body.get("provider") or "").strip().lower()
    if mode == "fixed":
        provider = plat["fixed_voice"]["provider"]
        model = plat["fixed_voice"]["model"]
    if not model:
        voice_entries = [e for e in roster_entries("voice") if e.get("enabled")]
        if voice_entries:
            provider = provider or voice_entries[0]["provider"]
            model = voice_entries[0]["model"]
    entry = next((e for e in roster_entries("voice")
                  if e.get("model") == model and e.get("enabled")), None)
    if not entry:
        raise HTTPException(400, f"Voice model '{model}' is not on the enabled roster.")
    provider = entry["provider"]
    cfg = get_provider_config(provider)
    if cfg["kind"] != "openai" or provider in ("lmstudio", "ollama"):
        raise HTTPException(400, "Voice (TTS) is only supported via OpenAI-compatible providers in v1.")
    key, key_source = resolve_key(provider, ws, mode)
    if not key:
        if mode == "byok":
            raise HTTPException(400, f"Voice model '{model}' is not configured: add your own {cfg['label']} key in this workspace's Secure store (BYOK mode).")
        raise HTTPException(400, f"Voice model '{model}' is not configured: the Super Admin has not added a {cfg['label']} key (master keys).")
    per_char = float((load_pricing().get("per_char_usd") or {}).get(model, 0.000015))
    cost = round(len(text) * per_char, 6)
    try:
        with _http_client(timeout=60, external=True) as c:
            r = c.post(f"{cfg['base_url']}/audio/speech",
                       headers={"Authorization": f"Bearer {key}"},
                       json={"model": model, "input": text,
                             "voice": (body.get("voice") or "alloy"),
                             "response_format": "mp3"})
            r.raise_for_status()
            audio = r.content
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"Voice provider failed: {e}")
    if key_source == "master":
        w = load_wallet_ws(ws["id"])
        w["balance_usd"] = round(float(w.get("balance_usd") or 0) - cost, 6)
        w.setdefault("transactions", []).append(
            {"ts": int(time.time()), "type": "charge", "amount_usd": -cost,
             "note": f"Voice: {provider}/{model} ({len(text)} chars)", "model": model,
             "balance_after_usd": w["balance_usd"]})
        save_wallet_ws(ws["id"], w)
    return Response(content=audio, media_type="audio/mpeg",
                    headers={"X-Voice-Cost-USD": str(cost if key_source == "master" else 0.0),
                             "X-Voice-Key-Source": key_source})


@app.get("/logo.png")
def logo():
    # LocalBotz brand logo (also in assets/logo.png for the GitHub repo).
    return FileResponse(STATIC_DIR / "logo.png", media_type="image/png")


@app.get("/logo-animated.svg")
def logo_animated_svg():
    # Animated LocalBotz wordmark (blinking robot, rising letters, shimmer).
    return FileResponse(STATIC_DIR / "logo-animated.svg", media_type="image/svg+xml")


@app.get("/logo-animated.gif")
def logo_animated_gif():
    # Animated LocalBotz logo as a GIF (pulse, shimmer, dot bounce, blink).
    return FileResponse(STATIC_DIR / "logo-animated.gif", media_type="image/gif")


@app.get("/logo-animated.mp4")
def logo_animated_mp4():
    # Animated LocalBotz logo as a 4 s video (also assets/logo-animated.webm).
    return FileResponse(STATIC_DIR / "logo-animated.mp4", media_type="video/mp4")


@app.get("/logo-animated.webm")
def logo_animated_webm():
    return FileResponse(STATIC_DIR / "logo-animated.webm", media_type="video/webm")

@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")

if __name__ == "__main__":
    import uvicorn
    p = argparse.ArgumentParser()
    p.add_argument("--mock", action="store_true", help="Mock mode: no local model needed")
    p.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")))
    p.add_argument("--host", default=os.getenv("HOST", "127.0.0.1"))
    a = p.parse_args()
    if a.mock:
        globals()["MOCK_MODE"] = True
        os.environ["MOCK_MODE"] = "1"
    print(f"LocalBotz on http://{a.host}:{a.port}  provider={_provider_name(LLM_BASE_URL)}  "
          f"model={DEFAULT_MODEL}  llm={LLM_BASE_URL}  mock={MOCK_MODE}")
    if not (os.getenv("MODEL") or os.getenv("LLM_MODEL") or os.getenv("OLLAMA_MODEL")):
        print("NOTE: MODEL not set in .env — using default qwen3.5. If LM Studio shows a fuller")
        print("      identifier for it (e.g. qwen/qwen3.5-...), set MODEL to that exact id.")
    uvicorn.run(app, host=a.host, port=a.port)
