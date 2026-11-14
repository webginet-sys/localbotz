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
import datetime
import time
import uuid
from html.parser import HTMLParser
from pathlib import Path

import httpx
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
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
            "onboarding_done": False, "run_mode": "computer", "autostart": False,
            "data_location": str(DATA_DIR), "app_version": APP_VERSION}


def _autostart_path():
    """Where the start-with-computer entry lives on this OS."""
    system = platform.system()
    if system == "Windows":
        start = Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
        return start / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "LocalBotz.bat"
    if system == "Darwin":
        return Path.home() / "Library" / "LaunchAgents" / "io.localbotz.plist"
    return Path.home() / ".config" / "autostart" / "localbotz.desktop"


def _autostart_enabled():
    try:
        return _autostart_path().is_file()
    except Exception:
        return False


def _set_autostart(enabled):
    """Start LocalBotz when the computer starts (so routines, jobs and
    workflows keep running while the computer is on), or stop it.
    Writes one small file in the OS's own startup place — nothing
    else. Returns (ok, message)."""
    path = _autostart_path()
    try:
        if not enabled:
            if path.is_file():
                path.unlink()
            return True, "Start with computer off."
        system = platform.system()
        path.parent.mkdir(parents=True, exist_ok=True)
        if system == "Windows":
            path.write_text(f"@echo off\r\ncd /d \"{BASE_DIR}\"\r\n"
                            f"start \"\" /min \"LocalBotz\" \"{BASE_DIR}\\start.bat\"\r\n",
                            encoding="utf-8")
        elif system == "Darwin":
            path.write_text(f"<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
                            "<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" "
                            "\"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">\n"
                            "<plist version=\"1.0\"><dict>\n"
                            "  <key>Label</key><string>io.localbotz</string>\n"
                            "  <key>ProgramArguments</key><array><string>/bin/sh</string>"
                            "<string>-c</string><string>cd \"" + str(BASE_DIR) +
                            "\" &amp;&amp; ./start.sh</string></array>\n"
                            "  <key>RunAtLoad</key><true/>\n</dict></plist>\n",
                            encoding="utf-8")
        else:
            path.write_text("[Desktop Entry]\nType=Application\nName=LocalBotz\n"
                            f"Exec={BASE_DIR}/start.sh\nX-GNOME-Autostart-enabled=true\n",
                            encoding="utf-8")
        return True, f"LocalBotz will start with the computer ({path})."
    except Exception as e:
        return False, f"Could not change start-with-computer: {e}"

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
        b.setdefault("routing", "off")
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

# Smart model routing (PicoClaw idea): a bot set to Auto answers simple
# questions free on the local model and only sends hard work to its
# configured premium provider, so the wallet lasts longer. A question
# is "simple" when it is short and asks for none of the hard-work
# words below — drafting, research, analysis, quotations, plans.
ROUTING_HARD_WORDS = ("draft", "write", "proposal", "quotation", "quote",
                      "tender", "boq", "contract", "analys", "research",
                      "compare", "plan", "strategy", "review", "audit",
                      "summar", "explain", "design", "build", "code",
                      "calculat", "estimat", "translate", "legal")


def _is_simple_question(text):
    t = (text or "").strip()
    if not t or len(t) > 300:
        return False
    low = t.lower()
    return not any(k in low for k in ROUTING_HARD_WORDS)


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
    # Smart routing: Auto + a paid online provider + a simple question
    # → answer free on the local model instead. Never overrides the
    # Master Fixed model, and never routes a bot that is already local.
    routed_from = None
    if (bot.get("routing") == "auto" and mode != "fixed"
            and provider_id not in ("lmstudio", "ollama")
            and _is_simple_question(user_text)):
        routed_from = {"provider": provider_id, "model": model}
        provider_id = "lmstudio"
        model = ""
    cfg = get_provider_config(provider_id)
    if not model:
        model = cfg["default_model"]
    eff_key, key_source = resolve_key(provider_id, ws, mode)
    history = load_chat(bot["id"])
    mem = load_memory(bot["id"])
    mem_text = "\n".join(f"- {f}" for f in mem.get("facts", [])) or "(no memory yet)"
    skills_text = _skills_text_for_bot(bot)
    learn_text = _learnings_text(bot_id=bot["id"])
    system = (f"{bot['instructions']}\n\nYour memory about the user:\n{mem_text}\n\n"
              "You have tools for web search, browser automation, workspace files, "
              "and safe shell commands. Use them when needed, then answer in plain text."
              + (f"\n\nEnabled skills:\n{skills_text}" if skills_text else "")
              + (f"\n\nWhat the team has learned from this user's daily work — "
                 f"use it when it fits, e.g. how they price a quotation:\n{learn_text}"
                 if learn_text else ""))
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
        history.append({"role": "assistant", "content": reply, "tools": trace, "ts": int(time.time()),
                        "routed_from": routed_from, "routed_to": provider_id})
        save_chat(bot["id"], history)
        return reply, trace, {"mode": mode, "key_source": key_source,
                              "workspace": ws["id"], "cost_usd": 0.0,
                              "routed_from": routed_from,
                              "routed_to": provider_id,
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
                  "routed_from": routed_from, "routed_to": provider_id,
                  "low_balance_warning": bool(low_warn)})
    history.append({"role": "assistant", "content": reply, "tools": trace, "ts": int(time.time()),
                    "cost_usd": metered["cost_usd"], "wallet_balance": metered["balance_usd"],
                    "mode": mode, "key_source": key_source,
                    "routed_from": routed_from, "routed_to": provider_id})
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
    routing: str = "off"
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
    routing: str = ""
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
           "routing": body.routing if body.routing in ("off", "auto") else "off",
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
    if body.routing in ("off", "auto"):
        bot["routing"] = body.routing
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

def _audit_office_job(office, title, brief, steps, boss):
    """Independent Auditor pass on a finished team job. The Auditor is
    NOT a team member and answers only to the user: it re-reads the
    brief and every step's output and checks facts, prices, dates and
    consistency. Returns {verdict, issues, summary, checked_at} with
    verdict one of pass / pass_with_fixes / fail / error.
    In mock mode there is no model to check with, so the audit is
    honest about that: it lists the figures and dates in the outputs
    for the user to check, and flags any step that ran in mock mode."""
    work = "\n\n".join(
        f"--- {s['member']} ({s['role']}):\n{s['output']}" for s in steps)
    if MOCK_MODE:
        figures = sorted({f.rstrip(",").strip() for f in
                          re.findall(r"(?:AED|QAR|USD|SAR|EUR|GBP|\$|£|€)\s?[\d,]+(?:\.\d+)?|\b\d+(?:\.\d+)?\s?(?:%|percent)|\b\d+\s(?:months?|weeks?|days?|years?)\b|\b\d{1,2}\s(?:January|February|March|April|May|June|July|August|September|October|November|December)\s\d{4}\b|\b\d{4}-\d{2}-\d{2}\b",
                                     work)})[:20]
        issues = []
        if any("[MOCK MODE" in s["output"] for s in steps):
            issues.append("One or more steps ran in mock mode — no real model produced or checked this output. Treat the job as a draft until a real model runs it.")
        if figures:
            issues.append("Figures and dates in the outputs still need checking against the source documents: " + ", ".join(figures) + ".")
        return {"verdict": "pass_with_fixes" if issues else "pass",
                "issues": issues,
                "summary": ("[MOCK MODE — no model ran the audit] The Auditor read the brief and "
                            f"{len(steps)} step(s). It could not verify facts without a model, so "
                            "check the figures and dates it listed before you approve this job."),
                "checked_at": int(time.time())}
    boss_bot = get_bot(boss["bot_id"]) if boss else None
    provider = (boss_bot or {}).get("provider") or DEFAULT_PROVIDER
    model = (boss_bot or {}).get("model") or ""
    cfg = get_provider_config(provider)
    if not model:
        model = cfg["default_model"]
    system = ("You are an independent Auditor. You do NOT work for the team that "
              "produced this work — you answer only to the owner. Check the team's "
              "output against the brief: every price, quantity, measurement, date "
              "and name must be backed by the brief or the shared memory. Flag "
              "anything invented, inconsistent between steps, or missing. "
              "Reply in exactly this shape:\n"
              "VERDICT: pass | pass_with_fixes | fail\n"
              "ISSUES:\n- <one issue per line, or the single line 'none'>\n"
              "SUMMARY: <two sentences: what is sound, and what must be fixed before this goes out>")
    user_text = (f"Office: {office['name']}\nJob: {title}\nBrief: {brief}\n\n"
                 f"Team output:\n{work[:6000]}")
    try:
        reply = llm_chat([{"role": "system", "content": system},
                          {"role": "user", "content": user_text}], model, provider)
    except Exception as e:
        return {"verdict": "error",
                "issues": [f"The audit could not run: {e}"],
                "summary": "The audit did not run, so this job is held for your approval with no verdict. Read the steps yourself before approving.",
                "checked_at": int(time.time())}
    verdict = "pass_with_fixes"
    m = re.search(r"VERDICT:\s*(pass_with_fixes|pass|fail)", reply, re.IGNORECASE)
    if m:
        verdict = m.group(1).lower()
    issues = []
    m = re.search(r"ISSUES:\s*(.*?)(?:\nSUMMARY:|\Z)", reply, re.IGNORECASE | re.DOTALL)
    if m:
        issues = [ln.strip("- ").strip() for ln in m.group(1).strip().splitlines()
                  if ln.strip() and ln.strip().lower() != "none"]
    summary = reply.strip()[:1000]
    m = re.search(r"SUMMARY:\s*(.*)", reply, re.IGNORECASE | re.DOTALL)
    if m:
        summary = m.group(1).strip()[:1000]
    return {"verdict": verdict, "issues": issues, "summary": summary,
            "checked_at": int(time.time())}


def _save_office_job(office_id: str, job: dict):
    """Replace one job in the stored office and save. Returns the job."""
    offices = load_offices()
    for o in offices:
        if o["id"] == office_id:
            o["jobs"] = [job if j.get("id") == job.get("id") else j
                         for j in o.get("jobs", [])]
    save_offices(offices)
    return job


def _job_memory_line(job, steps):
    return (f"- Job '{job['title']}' ({time.strftime('%Y-%m-%d')}): "
            f"{job['brief'][:200]} "
            f"Done by: {', '.join(s['member'] for s in steps) or 'nobody (no team yet)'}. "
            f"Audited: {job.get('audit', {}).get('verdict', 'not audited')}.")


@app.post("/api/offices/{office_id}/jobs")
def run_office_job(office_id: str, body: dict):
    office = get_office(office_id)
    if not office:
        raise HTTPException(404, "Office not found")
    title = (body.get("title") or "").strip()
    brief = (body.get("brief") or "").strip()
    if not title or not brief:
        raise HTTPException(400, "Give the job a title and a brief for the team.")
    # Auditor + approval gate (on by default): the finished job is
    # audited by an independent pass and held as a draft until the
    # user approves it. Send {"audit": false} to run a job the old
    # way — done immediately, no audit, no approval.
    audit_requested = body.get("audit", True) not in (False, "false", "no", 0)
    members = [m for m in office.get("members", []) if m["role"] != "boss"]
    members.sort(key=lambda m: ROLE_ORDER.index(m["role"]) if m["role"] in ROLE_ORDER else 99)
    boss = next((m for m in office.get("members", []) if m["role"] == "boss"), None)
    memory = load_office_memory(office_id)
    office_learn = _learnings_text(office_id=office_id)
    steps = []
    previous = ""
    workers = members or ([boss] if boss else [])
    for member in workers:
        bot = get_bot(member["bot_id"])
        if not bot:
            continue
        prompt = (f"Office: {office['name']}\nJob: {title}\nBrief: {brief}\n\n"
                  f"Shared office memory:\n{memory}\n\n"
                  + (f"What the team has learned from this user's daily work:\n{office_learn}\n\n"
                     if office_learn else "")
                  + f"Work done so far by the team:\n{previous or '(nothing yet — you are first)'}\n\n"
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
           "status": "done", "steps": steps, "created_at": int(time.time()),
           "audit_requested": audit_requested}
    if audit_requested:
        job["audit"] = _audit_office_job(office, title, brief, steps, boss)
        job["status"] = "awaiting_approval"
        job["approval"] = {"status": "pending", "decided_at": None, "note": ""}
        append_blackboard(office_id, "Auditor", "Boss",
                          f"Job '{title}' is a draft until you approve it. "
                          f"Audit verdict: {job['audit']['verdict']}.")
    offices = load_offices()
    for o in offices:
        if o["id"] == office_id:
            o.setdefault("jobs", []).append(job)
            o["jobs"] = o["jobs"][-20:]
    save_offices(offices)
    if not audit_requested:
        # No audit, no gate: the job counts as done, as before.
        append_office_memory(office_id, _job_memory_line(job, steps))
    return job

@app.get("/api/offices/{office_id}/jobs")
def list_office_jobs(office_id: str):
    office = get_office(office_id)
    if not office:
        raise HTTPException(404, "Office not found")
    return office.get("jobs", [])


@app.post("/api/offices/{office_id}/jobs/{job_id}/approve")
def approve_office_job(office_id: str, job_id: str, body: dict):
    """Approval gate: only an approved job counts as done. Approving
    writes the job into the shared office memory — until then the job
    is a draft and the memory does not mention it."""
    office = get_office(office_id)
    if not office:
        raise HTTPException(404, "Office not found")
    job = next((j for j in office.get("jobs", []) if j.get("id") == job_id), None)
    if not job:
        raise HTTPException(404, "Job not found")
    if job.get("status") != "awaiting_approval":
        raise HTTPException(400, f"This job is {job.get('status')} — it is not waiting for approval.")
    note = (body.get("note") or "").strip()
    job["status"] = "done"
    job["approval"] = {"status": "approved", "decided_at": int(time.time()), "note": note}
    _save_office_job(office_id, job)
    append_office_memory(office_id, _job_memory_line(job, job.get("steps", [])) + " Approved by you.")
    # Learn from the approved work: record what the user wanted and
    # what passed the audit, so the team brings it back next time.
    _record_learning(
        None, office_id, "office job", job["title"],
        f"Approved job '{job['title']}': {job['brief'][:200]} "
        f"Audit verdict: {job.get('audit', {}).get('verdict', 'not audited')}.")
    append_blackboard(office_id, "You", "Boss",
                      f"Approved '{job['title']}'" + (f" — {note}" if note else "."))
    return job


@app.post("/api/offices/{office_id}/jobs/{job_id}/request-changes")
def request_office_job_changes(office_id: str, job_id: str, body: dict):
    """Send a draft back: the job stays out of the office memory, and
    the note tells the team what to fix. Run the job again with the
    note in the brief."""
    office = get_office(office_id)
    if not office:
        raise HTTPException(404, "Office not found")
    job = next((j for j in office.get("jobs", []) if j.get("id") == job_id), None)
    if not job:
        raise HTTPException(404, "Job not found")
    if job.get("status") != "awaiting_approval":
        raise HTTPException(400, f"This job is {job.get('status')} — it is not waiting for approval.")
    note = (body.get("note") or "").strip()
    if not note:
        raise HTTPException(400, "Say what the team should fix, so they can run it again.")
    job["status"] = "changes_requested"
    job["approval"] = {"status": "changes_requested", "decided_at": int(time.time()), "note": note}
    _save_office_job(office_id, job)
    append_blackboard(office_id, "You", "Boss",
                      f"Changes requested on '{job['title']}': {note}")
    return job


# ---- Office documents: real Word / Excel / PowerPoint exports ----
# A team job is text on a page until it leaves the computer. These
# exporters turn a finished job into a real file — .docx, .xlsx or
# .pptx — built from the job's own text only. Nothing is invented:
# no price, measurement or date is added, and a step with no output
# says so instead of being padded out. Tables the team wrote with
# | pipes | become real tables in Word and real sheets in Excel.
# Files live under data/documents/<office_id>/<job_id>/.
DOCUMENTS_DIR = DATA_DIR / "documents"
DOCUMENT_FORMATS = ("docx", "xlsx", "pptx")


def _document_libs(fmt):
    """Import the library a format needs, lazily, so a missing
    optional library never stops the rest of the app starting."""
    try:
        if fmt == "docx":
            from docx import Document
            return Document
        if fmt == "xlsx":
            import openpyxl
            return openpyxl
        if fmt == "pptx":
            from pptx import Presentation
            return Presentation
    except ImportError:
        raise HTTPException(500, f"The {fmt} library is not installed — run pip install -r requirements.txt and restart LocalBotz.")
    raise HTTPException(400, f"Unknown document format '{fmt}' — use docx, xlsx or pptx.")


def _parse_pipe_blocks(text):
    """Split step text into blocks: {"type": "text", "text": ...} or
    {"type": "table", "rows": [[cell, ...], ...]}. A table is two or
    more consecutive lines made of | cells; separator lines like
    |---|---| are skipped, not shown as data."""
    blocks = []
    buf = []
    table = []

    def flush_text():
        if buf:
            blocks.append({"type": "text", "text": "\n".join(buf).strip()})
            buf.clear()

    def flush_table():
        if len(table) >= 2:
            # Copy: the block must keep its own rows — table is cleared below.
            blocks.append({"type": "table", "rows": [list(r) for r in table]})
        elif table:
            buf.extend(" | ".join(r) for r in table)
        table.clear()

    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2:
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if all(set(c) <= set("-: ") and c for c in cells):
                continue  # separator row: |---|---|---|
            if buf:
                flush_text()
            table.append(cells)
        else:
            if table:
                flush_table()
            buf.append(line)
    if table:
        flush_table()
    flush_text()
    return blocks


def _money_number(cell, header=""):
    """A cell that looks like money (or a number in a money/quantity
    column) as a float, so Excel keeps it a number, not text.
    Returns None when the cell is not numeric — it stays text.
    Currency marks and thousands separators are stripped; bare
    integers stay text unless the column is a quantity/amount one,
    so codes and years (2024, 001) are never mangled."""
    raw = (cell or "").strip()
    if not raw:
        return None
    cleaned = re.sub(r"(AED|QAR|USD|SAR|EUR|GBP|\$|£|€)", "", raw, flags=re.IGNORECASE).strip()
    if not re.fullmatch(r"-?[\d,]+(?:\.\d+)?", cleaned):
        return None
    has_mark = bool(re.search(r"(AED|QAR|USD|SAR|EUR|GBP|\$|£|€)", raw, flags=re.IGNORECASE))
    has_sep = ("," in cleaned) or ("." in cleaned)
    header = (header or "").lower()
    qty_col = any(w in header for w in ("qty", "quantity", "amount", "price", "total", "cost", "value", "unit"))
    if has_mark or has_sep or qty_col:
        try:
            return float(cleaned.replace(",", ""))
        except ValueError:
            return None
    return None


def _job_doc_filename(job, fmt):
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", job.get("title") or "job").strip("-")[:60] or "job"
    return f"{slug}.{fmt}"


def _job_doc_date(job):
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(job.get("created_at") or int(time.time())))


def _step_role_label(step):
    return (OFFICE_ROLES.get(step.get("role") or "") or {}).get("label") or (step.get("role") or "Team member")


def _export_docx(office, job):
    Document = _document_libs("docx")
    doc = Document()
    doc.add_heading(job["title"], level=0)
    doc.add_paragraph(f"Office: {office['name']}  •  Date: {_job_doc_date(job)}  •  Status: {job.get('status')}")
    doc.add_paragraph(f"Brief: {job.get('brief')}")
    audit = job.get("audit") or {}
    if audit:
        doc.add_heading("Auditor", level=1)
        doc.add_paragraph(f"Verdict: {audit.get('verdict')}")
        if audit.get("summary"):
            doc.add_paragraph(audit["summary"])
        for issue in audit.get("issues") or []:
            doc.add_paragraph(issue, style="List Bullet")
    for step in job.get("steps") or []:
        doc.add_heading(f"{step.get('member')} — {_step_role_label(step)}", level=1)
        output = (step.get("output") or "").strip()
        if not output:
            p = doc.add_paragraph("No output from this step.")
            p.runs[0].italic = True
            continue
        for block in _parse_pipe_blocks(output):
            if block["type"] == "text":
                for para in block["text"].split("\n"):
                    para = para.strip()
                    if not para:
                        continue
                    style = "List Bullet" if para.startswith(("- ", "• ")) else None
                    doc.add_paragraph(para[2:].strip() if style else para, style=style)
            else:
                rows = block["rows"]
                table = doc.add_table(rows=1, cols=len(rows[0]))
                table.style = "Table Grid"
                for i, cell in enumerate(rows[0]):
                    run = table.rows[0].cells[i].paragraphs[0].add_run(cell)
                    run.bold = True
                for row in rows[1:]:
                    cells = table.add_row().cells
                    for i, cell in enumerate(row):
                        if i < len(cells):
                            cells[i].text = cell
    path = DOCUMENTS_DIR / office["id"] / job["id"] / _job_doc_filename(job, "docx")
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(path))
    return path


def _export_xlsx(office, job):
    openpyxl = _document_libs("xlsx")
    wb = openpyxl.Workbook()
    summary = wb.active
    summary.title = "Summary"
    audit = job.get("audit") or {}
    summary_rows = [
        ("Job", job["title"]),
        ("Office", office["name"]),
        ("Date", _job_doc_date(job)),
        ("Status", job.get("status")),
        ("Brief", job.get("brief")),
        ("Audit verdict", audit.get("verdict") or "not audited"),
        ("Team members", ", ".join(s.get("member", "") for s in job.get("steps") or [])),
    ]
    for row in summary_rows:
        summary.append(list(row))
    for cell in summary["A"]:
        cell.font = openpyxl.styles.Font(bold=True)
    summary.column_dimensions["A"].width = 18
    summary.column_dimensions["B"].width = 90
    used_names = {"Summary"}
    for step in job.get("steps") or []:
        base = re.sub(r"[\[\]:*?/\\]", "", step.get("member") or "Step")[:28].strip() or "Step"
        name = base
        n = 2
        while name in used_names:
            name = f"{base[:26]} {n}"
            n += 1
        used_names.add(name)
        ws = wb.create_sheet(name)
        ws.append([f"{step.get('member')} — {_step_role_label(step)}"])
        ws["A1"].font = openpyxl.styles.Font(bold=True, size=14)
        output = (step.get("output") or "").strip()
        if not output:
            ws.append(["No output from this step."])
            continue
        row_no = 3
        for block in _parse_pipe_blocks(output):
            if block["type"] == "text":
                for para in block["text"].split("\n"):
                    para = para.strip()
                    if para:
                        ws.cell(row=row_no, column=1, value=para)
                        row_no += 1
                row_no += 1
            else:
                rows = block["rows"]
                header = rows[0]
                for i, cell in enumerate(header, start=1):
                    c = ws.cell(row=row_no, column=i, value=cell)
                    c.font = openpyxl.styles.Font(bold=True)
                row_no += 1
                for row in rows[1:]:
                    for i, cell in enumerate(row, start=1):
                        num = _money_number(cell, header[i - 1] if i - 1 < len(header) else "")
                        c = ws.cell(row=row_no, column=i, value=num if num is not None else cell)
                        if num is not None:
                            c.number_format = "#,##0.00"
                    row_no += 1
                row_no += 1
        for col in range(1, ws.max_column + 1):
            width = 0
            for r in range(1, ws.max_row + 1):
                v = ws.cell(row=r, column=col).value
                if v is not None:
                    width = max(width, len(str(v)))
            ws.column_dimensions[openpyxl.utils.get_column_letter(col)].width = min(max(width + 2, 12), 60)
    path = DOCUMENTS_DIR / office["id"] / job["id"] / _job_doc_filename(job, "xlsx")
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(path))
    return path


def _export_pptx(office, job):
    Presentation = _document_libs("pptx")
    prs = Presentation()
    title_slide = prs.slides.add_slide(prs.slide_layouts[0])
    title_slide.shapes.title.text = job["title"]
    title_slide.placeholders[1].text = (
        f"{office['name']}  •  {_job_doc_date(job)}  •  Status: {job.get('status')}")
    steps = job.get("steps") or []
    max_content = 11  # title slide + 11 = 12 slides at most
    shown = steps[:max_content]
    for step in shown:
        slide = prs.slides.add_slide(prs.slide_layouts[1])
        slide.shapes.title.text = f"{step.get('member')} — {_step_role_label(step)}"
        tf = slide.placeholders[1].text_frame
        tf.word_wrap = True
        output = (step.get("output") or "").strip()
        if not output:
            tf.paragraphs[0].text = "No output from this step."
            continue
        lines = [ln.strip() for ln in output.splitlines() if ln.strip()]
        # Pipe tables become one line per row; cap the slide so it
        # stays readable — the full text lives in the Word/Excel file.
        bullets = []
        for ln in lines:
            if ln.startswith("|") and ln.endswith("|"):
                bullets.append(" | ".join(c.strip() for c in ln.strip("|").split("|") if c.strip()))
            elif ln.startswith(("- ", "• ")):
                bullets.append(ln[2:].strip())
            else:
                bullets.append(ln)
        bullets = bullets[:8]
        for i, b in enumerate(bullets):
            para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            para.text = b[:220]
            para.level = 0
        if len(lines) > 8:
            para = tf.add_paragraph()
            para.text = f"… {len(lines) - 8} more line(s) — see the Word or Excel export for the full text."
            para.level = 1
    if len(steps) > max_content:
        slide = prs.slides.add_slide(prs.slide_layouts[1])
        slide.shapes.title.text = "More steps"
        slide.placeholders[1].text_frame.paragraphs[0].text = (
            f"{len(steps) - max_content} further step(s) — see the Word or Excel export for the full text.")
    path = DOCUMENTS_DIR / office["id"] / job["id"] / _job_doc_filename(job, "pptx")
    path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(path))
    return path


def _export_office_document(office, job, fmt):
    if fmt == "docx":
        return _export_docx(office, job)
    if fmt == "xlsx":
        return _export_xlsx(office, job)
    if fmt == "pptx":
        return _export_pptx(office, job)
    raise HTTPException(400, f"Unknown document format '{fmt}' — use docx, xlsx or pptx.")


@app.post("/api/offices/{office_id}/jobs/{job_id}/export")
def export_office_job(office_id: str, job_id: str, body: dict):
    """Export a finished job as a real Word, Excel or PowerPoint file.
    Works for any job with steps — approved jobs especially, but a
    draft awaiting approval can be exported too, to read or check
    before you approve it."""
    office = get_office(office_id)
    if not office:
        raise HTTPException(404, "Office not found")
    job = next((j for j in office.get("jobs", []) if j.get("id") == job_id), None)
    if not job:
        raise HTTPException(404, "Job not found")
    fmt = (body.get("format") or "").strip().lower()
    if fmt not in DOCUMENT_FORMATS:
        raise HTTPException(400, "Format must be docx, xlsx or pptx.")
    path = _export_office_document(office, job, fmt)
    return {"format": fmt, "filename": path.name,
            "url": f"/api/documents/{office_id}/{job_id}/{path.name}",
            "size_bytes": path.stat().st_size,
            "created_at": int(path.stat().st_mtime)}


@app.get("/api/documents")
def list_documents(office_id: str = ""):
    """Every generated document, newest first. Filter with
    ?office_id= for one office's files."""
    docs = []
    if not DOCUMENTS_DIR.exists():
        return docs
    offices = {o["id"]: o for o in load_offices()}
    for path in sorted(DOCUMENTS_DIR.rglob("*"), key=lambda p: p.stat().st_mtime, reverse=True):
        if not path.is_file() or path.suffix.lstrip(".") not in DOCUMENT_FORMATS:
            continue
        parts = path.relative_to(DOCUMENTS_DIR).parts
        if len(parts) != 3:
            continue
        oid, jid, filename = parts
        if office_id and oid != office_id:
            continue
        office = offices.get(oid) or {}
        job = next((j for j in office.get("jobs", []) if j.get("id") == jid), None)
        docs.append({"office_id": oid, "office_name": office.get("name"),
                     "job_id": jid, "job_title": (job or {}).get("title"),
                     "format": path.suffix.lstrip("."),
                     "filename": filename,
                     "url": f"/api/documents/{oid}/{jid}/{filename}",
                     "size_bytes": path.stat().st_size,
                     "created_at": int(path.stat().st_mtime)})
    return docs


@app.get("/api/documents/{office_id}/{job_id}/{filename}")
def download_document(office_id: str, job_id: str, filename: str):
    """Download one generated document. The path is resolved inside
    data/documents/ — anything trying to climb out gets a 404."""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", office_id) or not re.fullmatch(r"[A-Za-z0-9_-]+", job_id):
        raise HTTPException(404, "Document not found")
    if not re.fullmatch(r"[A-Za-z0-9_.\-]+\.(docx|xlsx|pptx)", filename):
        raise HTTPException(404, "Document not found")
    path = (DOCUMENTS_DIR / office_id / job_id / filename).resolve()
    if DOCUMENTS_DIR.resolve() not in path.parents or not path.is_file():
        raise HTTPException(404, "Document not found")
    return FileResponse(str(path), filename=filename)


# ---- Document workroom ----
# LocalBotz-native, modelled on the TeamOffice idea of a private AI
# workroom for document-heavy professional teams: one workroom is a
# vault of project documents (BOQs, tenders, contracts, SOWs, SLAs,
# drawings notes, invoices, correspondence) that you can search and
# ask questions about — with receipts, not blind trust.
#   * Vault: documents stay on your computer, under
#     data/workrooms/<id>/docs/. Nothing is uploaded anywhere.
#   * Search: keyword search over the documents, in chunks, so a big
#     document set is searched as the work happens instead of being
#     stuffed into one prompt.
#   * Ask with receipts: the model only gets the matching passages,
#     and every answer comes back with its sources — document name
#     and the exact passage it came from. If it is not in the
#     documents, the answer says so. Prices, measurements and dates
#     are never invented.
#   * Redaction: before anything is sent to an online (non-local)
#     model, emails, IBANs, card-like numbers and the workroom's own
#     private terms are replaced with placeholders like [EMAIL-1].
#     The placeholders are swapped back into the answer locally, so
#     you see the real text. The redaction log records only what kind
#     of thing was hidden and how many — never the values themselves.
#     Local models (LM Studio / Ollama) never leave the computer, so
#     redaction is off for them unless you ask for it.
#   * Handoff: a workroom exports as one JSON package — documents,
#     questions and answers with their sources, redaction log and
#     reviewer notes — so another reviewer can pick the work up.
# Text is extracted for .txt/.md/.csv/.json/.log, .pdf (pypdf) and
# .docx (python-docx); anything else is stored but not searchable,
# and the workroom says so honestly on the document.

WORKROOMS_FILE = DATA_DIR / "workrooms.json"
WORKROOMS_DIR = DATA_DIR / "workrooms"
WORKROOM_ALLOWED_SUFFIXES = {".txt", ".md", ".csv", ".json", ".log", ".tsv", ".pdf", ".docx"}
WORKROOM_MAX_BYTES = 20 * 1024 * 1024
_LOCAL_PROVIDERS = ("lmstudio", "ollama")
_WORKROOM_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "your",
    "you", "are", "was", "were", "have", "has", "what", "when", "which",
    "about", "there", "their", "will", "would", "should", "please",
}
_REDACTION_PATTERNS = [
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("iban", re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")),
    ("card_number", re.compile(r"\b(?:\d[ -]?){13,19}\b")),
    ("phone", re.compile(r"\+\d[\d\s\-()]{7,}\d")),
]


def load_workrooms():
    return _load_json(WORKROOMS_FILE, [])


def save_workrooms(workrooms):
    _save_json(WORKROOMS_FILE, workrooms)


def get_workroom(workroom_id: str):
    return next((w for w in load_workrooms() if w["id"] == workroom_id), None)


def _workroom_dir(workroom_id: str) -> Path:
    d = WORKROOMS_DIR / workroom_id
    (d / "docs").mkdir(parents=True, exist_ok=True)
    (d / "text").mkdir(parents=True, exist_ok=True)
    return d


def _workroom_asks_path(workroom_id: str) -> Path:
    return _workroom_dir(workroom_id) / "asks.json"


def load_workroom_asks(workroom_id: str):
    return _load_json(_workroom_asks_path(workroom_id), [])


def save_workroom_asks(workroom_id: str, asks):
    _save_json(_workroom_asks_path(workroom_id), asks[-50:])


def _safe_doc_filename(name: str) -> str:
    name = Path(name).name.strip() or "document"
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)[:120]


def _extract_text(path: Path, suffix: str):
    """Return (text, note). note explains when text could not be read."""
    try:
        if suffix == ".pdf":
            try:
                from pypdf import PdfReader
            except Exception:
                return "", "PDF text was not extracted: pypdf is not installed. Run pip install pypdf, or add a .txt copy of this document."
            reader = PdfReader(str(path))
            parts = [(p.extract_text() or "") for p in reader.pages]
            return "\n".join(parts), ""
        if suffix == ".docx":
            try:
                from docx import Document
            except Exception:
                return "", "Word text was not extracted: python-docx is not installed. Run pip install python-docx, or add a .txt copy of this document."
            doc = Document(str(path))
            return "\n".join(p.text for p in doc.paragraphs), ""
        return path.read_text(encoding="utf-8", errors="replace"), ""
    except Exception as e:
        return "", f"Could not read this file: {e}"


def _chunk_text(text: str, size: int = 900, overlap: int = 150):
    """Split text into overlapping chunks on paragraph boundaries."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paras:
        return []
    chunks, current = [], ""
    for para in paras:
        if len(current) + len(para) + 2 > size and current:
            chunks.append(current)
            current = current[-overlap:] if len(current) > overlap else current
        current = (current + "\n\n" + para).strip() if current else para
    if current:
        chunks.append(current)
    return chunks


def _load_workroom_chunks(workroom_id: str):
    """{doc_id: {'filename': ..., 'chunks': [...]}} from stored text."""
    out = {}
    workroom = get_workroom(workroom_id)
    if not workroom:
        return out
    text_dir = _workroom_dir(workroom_id) / "text"
    for doc in workroom.get("docs", []):
        p = text_dir / f"{doc['id']}.txt"
        if not p.exists():
            continue
        out[doc["id"]] = {"filename": doc["filename"],
                          "chunks": _chunk_text(p.read_text(encoding="utf-8", errors="replace"))}
    return out


def _search_workroom(workroom_id: str, query: str, top_n: int = 5):
    """Keyword search over the workroom's documents. Returns passages
    with document name + chunk number — the receipts for an answer."""
    words = [w for w in re.findall(r"[a-z0-9]+", query.lower())
             if len(w) > 2 and w not in _WORKROOM_STOPWORDS]
    if not words:
        words = [w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 2]
    if not words:
        return []
    phrase = query.lower().strip()
    scored = []
    for doc_id, doc in _load_workroom_chunks(workroom_id).items():
        for i, chunk in enumerate(doc["chunks"]):
            low = chunk.lower()
            score = sum(low.count(w) for w in words)
            if phrase and phrase in low:
                score += 5
            if score > 0:
                scored.append({"doc_id": doc_id, "filename": doc["filename"],
                               "chunk": i, "excerpt": chunk[:600], "score": score})
    scored.sort(key=lambda s: -s["score"])
    return scored[:top_n]


def _redact_text(text: str, terms):
    """Replace sensitive values with placeholders. Returns
    (redacted_text, counts, mapping). The mapping (placeholder -> real
    value) lives only in memory for this one ask — it is never saved."""
    counts, mapping = {}, {}
    counters = {}

    def _replace(label, pattern, value):
        def _sub(m):
            counters[label] = counters.get(label, 0) + 1
            tag = f"[{label.upper()}-{counters[label]}]"
            mapping[tag] = m.group(0)
            return tag
        return pattern.sub(_sub, value)

    out = text
    for label, pattern in _REDACTION_PATTERNS:
        before = counters.get(label, 0)
        out = _replace(label, pattern, out)
        if counters.get(label, 0) > before:
            counts[label] = counters[label] - before
    for term in sorted((terms or []), key=len, reverse=True):
        term = (term or "").strip()
        if len(term) < 3:
            continue
        pattern = re.compile(re.escape(term), re.IGNORECASE)
        before = counters.get("term", 0)
        out = _replace("term", pattern, out)
        if counters.get("term", 0) > before:
            counts["private_term"] = counts.get("private_term", 0) + (counters["term"] - before)
    return out, counts, mapping


def _unredact_text(text: str, mapping):
    for tag, value in mapping.items():
        text = text.replace(tag, value)
    return text


def _add_workroom_doc(workroom_id: str, filename: str, data: bytes):
    """Store a document's bytes + extracted text, register it, return its record."""
    suffix = Path(filename).suffix.lower()
    if suffix not in WORKROOM_ALLOWED_SUFFIXES:
        raise HTTPException(400, f"That file type ({suffix or 'none'}) is not supported yet. Use: {', '.join(sorted(WORKROOM_ALLOWED_SUFFIXES))}.")
    if len(data) > WORKROOM_MAX_BYTES:
        raise HTTPException(400, "That file is over 20 MB. Split it, or add a shorter extract.")
    doc_id = uuid.uuid4().hex[:8]
    safe = _safe_doc_filename(filename)
    d = _workroom_dir(workroom_id)
    (d / "docs" / f"{doc_id}_{safe}").write_bytes(data)
    text, note = _extract_text(d / "docs" / f"{doc_id}_{safe}", suffix)
    (d / "text" / f"{doc_id}.txt").write_text(text, encoding="utf-8")
    record = {"id": doc_id, "filename": safe, "size_bytes": len(data),
              "chars": len(text), "chunks": len(_chunk_text(text)),
              "added_at": int(time.time()), "note": note}
    workrooms = load_workrooms()
    for w in workrooms:
        if w["id"] == workroom_id:
            w.setdefault("docs", []).append(record)
    save_workrooms(workrooms)
    return record


def _workroom_summary(w):
    asks = load_workroom_asks(w["id"])
    return {"id": w["id"], "name": w["name"], "description": w.get("description", ""),
            "office_id": w.get("office_id") or "", "provider": w.get("provider") or DEFAULT_PROVIDER,
            "model": w.get("model") or "", "docs": len(w.get("docs", [])),
            "asks": len(asks), "created_at": w.get("created_at")}


@app.get("/api/workrooms")
def list_workrooms():
    return [_workroom_summary(w) for w in load_workrooms()]


@app.post("/api/workrooms", status_code=201)
def create_workroom(body: dict):
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "Give the workroom a name, e.g. Marina Tower — Tender 14.")
    office_id = (body.get("office_id") or "").strip()
    if office_id and not get_office(office_id):
        raise HTTPException(400, "That office does not exist.")
    provider = (body.get("provider") or DEFAULT_PROVIDER).lower()
    if provider not in PROVIDERS:
        provider = DEFAULT_PROVIDER
    workroom = {"id": uuid.uuid4().hex[:8], "name": name,
                "description": (body.get("description") or "").strip(),
                "office_id": office_id, "provider": provider,
                "model": (body.get("model") or "").strip(),
                "redact_terms": [str(t).strip() for t in (body.get("redact_terms") or []) if str(t).strip()],
                "docs": [], "notes": [], "created_at": int(time.time())}
    workrooms = load_workrooms()
    workrooms.append(workroom)
    save_workrooms(workrooms)
    _workroom_dir(workroom["id"])
    save_workroom_asks(workroom["id"], [])
    return workroom


@app.get("/api/workrooms/{workroom_id}")
def get_workroom_detail(workroom_id: str):
    workroom = get_workroom(workroom_id)
    if not workroom:
        raise HTTPException(404, "Workroom not found")
    detail = dict(workroom)
    detail["asks"] = load_workroom_asks(workroom_id)[-10:]
    return detail


@app.patch("/api/workrooms/{workroom_id}")
def update_workroom(workroom_id: str, body: dict):
    workroom = get_workroom(workroom_id)
    if not workroom:
        raise HTTPException(404, "Workroom not found")
    workrooms = load_workrooms()
    for w in workrooms:
        if w["id"] != workroom_id:
            continue
        if (body.get("name") or "").strip():
            w["name"] = body["name"].strip()
        if "description" in body:
            w["description"] = (body.get("description") or "").strip()
        if (body.get("provider") or "").lower() in PROVIDERS:
            w["provider"] = body["provider"].lower()
        if "model" in body:
            w["model"] = (body.get("model") or "").strip()
        if isinstance(body.get("redact_terms"), list):
            w["redact_terms"] = [str(t).strip() for t in body["redact_terms"] if str(t).strip()]
    save_workrooms(workrooms)
    return get_workroom(workroom_id)


@app.delete("/api/workrooms/{workroom_id}")
def delete_workroom(workroom_id: str):
    workroom = get_workroom(workroom_id)
    if not workroom:
        raise HTTPException(404, "Workroom not found")
    save_workrooms([w for w in load_workrooms() if w["id"] != workroom_id])
    shutil.rmtree(_workroom_dir(workroom_id), ignore_errors=True)
    return {"deleted": workroom_id}


@app.post("/api/workrooms/{workroom_id}/docs", status_code=201)
async def upload_workroom_doc(workroom_id: str, file: UploadFile = File(...)):
    if not get_workroom(workroom_id):
        raise HTTPException(404, "Workroom not found")
    data = await file.read()
    return _add_workroom_doc(workroom_id, file.filename or "document", data)


@app.post("/api/workrooms/{workroom_id}/docs/from-workspace", status_code=201)
def add_workroom_doc_from_workspace(workroom_id: str, body: dict):
    if not get_workroom(workroom_id):
        raise HTTPException(404, "Workroom not found")
    rel = (body.get("path") or "").strip()
    if not rel:
        raise HTTPException(400, "Give a file path inside the workspace folder, e.g. tender-14.pdf.")
    path = _safe_workspace_path(rel)
    if not path.exists() or not path.is_file():
        raise HTTPException(404, f"No file at {rel} inside the workspace folder.")
    return _add_workroom_doc(workroom_id, path.name, path.read_bytes())


@app.delete("/api/workrooms/{workroom_id}/docs/{doc_id}")
def delete_workroom_doc(workroom_id: str, doc_id: str):
    workroom = get_workroom(workroom_id)
    if not workroom:
        raise HTTPException(404, "Workroom not found")
    before = len(workroom.get("docs", []))
    workrooms = load_workrooms()
    for w in workrooms:
        if w["id"] == workroom_id:
            w["docs"] = [d for d in w.get("docs", []) if d["id"] != doc_id]
    after = len(next(w for w in workrooms if w["id"] == workroom_id).get("docs", []))
    if after == before:
        raise HTTPException(404, "Document not found")
    save_workrooms(workrooms)
    d = _workroom_dir(workroom_id)
    for p in (d / "docs").glob(f"{doc_id}_*"):
        p.unlink(missing_ok=True)
    (d / "text" / f"{doc_id}.txt").unlink(missing_ok=True)
    return {"deleted": doc_id}


@app.get("/api/workrooms/{workroom_id}/search")
def search_workroom(workroom_id: str, q: str = "", top: int = 5):
    if not get_workroom(workroom_id):
        raise HTTPException(404, "Workroom not found")
    if not (q or "").strip():
        raise HTTPException(400, "Type something to search for.")
    return _search_workroom(workroom_id, q.strip(), top_n=max(1, min(int(top), 10)))


@app.post("/api/workrooms/{workroom_id}/ask")
def ask_workroom(workroom_id: str, body: dict):
    workroom = get_workroom(workroom_id)
    if not workroom:
        raise HTTPException(404, "Workroom not found")
    question = (body.get("question") or "").strip()
    if not question:
        raise HTTPException(400, "Ask a question about the documents in this workroom.")
    provider = (body.get("provider") or workroom.get("provider") or DEFAULT_PROVIDER).lower()
    if provider not in PROVIDERS:
        provider = DEFAULT_PROVIDER
    cfg = get_provider_config(provider)
    model = (body.get("model") or workroom.get("model") or "").strip() or cfg["default_model"]
    hits = _search_workroom(workroom_id, question, top_n=5)
    is_local = provider in _LOCAL_PROVIDERS
    force = body.get("redact")
    do_redact = bool(force) if force is not None else (not is_local)
    ask = {"id": uuid.uuid4().hex[:8], "question": question, "provider": provider,
           "model": model, "sources": hits, "ts": int(time.time()),
           "redacted": {"applied": do_redact, "counts": {}}}
    if not hits:
        ask["answer"] = ("I could not find anything about that in this workroom's "
                         "documents. Add the document it is in, or ask it a different way.")
        asks = load_workroom_asks(workroom_id)
        asks.append(ask)
        save_workroom_asks(workroom_id, asks)
        return ask
    # Build the model's context from the matching passages only.
    mapping = {}
    passages = []
    for i, h in enumerate(hits):
        text = h["excerpt"]
        if do_redact:
            text, counts, _map = _redact_text(text, workroom.get("redact_terms") or [])
            mapping.update(_map)
            for k, v in counts.items():
                ask["redacted"]["counts"][k] = ask["redacted"]["counts"].get(k, 0) + v
        passages.append(f"[Source {i + 1}: {h['filename']}, passage {h['chunk'] + 1}]\n{text}")
    context = "\n\n".join(passages)
    if MOCK_MODE:
        lines = [f"{i + 1}. {h['filename']} (passage {h['chunk'] + 1}): {h['excerpt'][:300]}"
                 for i, h in enumerate(hits)]
        ask["answer"] = ("[MOCK MODE — no local model running] Based on the documents in "
                         "this workroom, here is what I found:\n\n" + "\n\n".join(lines) +
                         "\n\nWith a model running, the answer is written from these same "
                         "passages, with each claim tied to its source above. If the answer "
                         "is not in the documents, I say so instead of guessing.")
    else:
        system = ("You answer questions using ONLY the document passages below. "
                  "Every claim in your answer must come from a passage — cite it as "
                  "[Source N]. Never invent a price, measurement, date, name or figure "
                  "that is not in the passages. If the passages do not contain the "
                  "answer, say so plainly and say which document would settle it. "
                  "Answer in plain language, short where possible.")
        try:
            reply = llm_chat([{"role": "system", "content": system},
                              {"role": "user", "content": f"Question: {question}\n\nPassages:\n{context}"}],
                             model, provider)
            ask["answer"] = _unredact_text(reply, mapping) if do_redact else reply
        except Exception as e:
            ask["error"] = str(e)
            ask["answer"] = (f"Could not get an answer from {cfg['label']}: {e}. "
                             "The matching passages are saved with this question below, "
                             "so you can still read them. Switch the workroom to LM Studio "
                             "to work offline, or check the provider key in Settings > Secure store.")
    asks = load_workroom_asks(workroom_id)
    asks.append(ask)
    save_workroom_asks(workroom_id, asks)
    return ask


@app.get("/api/workrooms/{workroom_id}/asks")
def list_workroom_asks(workroom_id: str):
    if not get_workroom(workroom_id):
        raise HTTPException(404, "Workroom not found")
    return load_workroom_asks(workroom_id)


@app.post("/api/workrooms/{workroom_id}/notes", status_code=201)
def add_workroom_note(workroom_id: str, body: dict):
    workroom = get_workroom(workroom_id)
    if not workroom:
        raise HTTPException(404, "Workroom not found")
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "Write a note first.")
    note = {"id": uuid.uuid4().hex[:8], "text": text,
            "ask_id": (body.get("ask_id") or "").strip(),
            "ts": int(time.time())}
    workrooms = load_workrooms()
    for w in workrooms:
        if w["id"] == workroom_id:
            w.setdefault("notes", []).append(note)
    save_workrooms(workrooms)
    return note


@app.get("/api/workrooms/{workroom_id}/export")
def export_workroom(workroom_id: str):
    """One JSON package: workroom, documents (with text), questions and
    answers with their sources, redaction log and reviewer notes — so
    another reviewer can pick the work up and check it."""
    workroom = get_workroom(workroom_id)
    if not workroom:
        raise HTTPException(404, "Workroom not found")
    text_dir = _workroom_dir(workroom_id) / "text"
    docs = []
    for doc in workroom.get("docs", []):
        p = text_dir / f"{doc['id']}.txt"
        docs.append({"filename": doc["filename"], "added_at": doc.get("added_at"),
                     "note": doc.get("note", ""),
                     "text": p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""})
    package = {"app": "LocalBotz", "version": APP_VERSION, "exported_at": int(time.time()),
               "workroom": {k: v for k, v in workroom.items() if k != "docs"},
               "documents": docs, "asks": load_workroom_asks(workroom_id),
               "notes": workroom.get("notes", [])}
    return Response(content=json.dumps(package, indent=2, ensure_ascii=False),
                    media_type="application/json",
                    headers={"Content-Disposition": f"attachment; filename=workroom-{workroom_id}.json"})

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
    """Background loop: every 30s, run one thing — the oldest pending
    task of a persistent bot, the first routine whose time has
    arrived, or the first workflow chain whose wait has ended. One
    per loop, then re-check. Never crashes the app. A routine whose
    time passed while the app was closed runs once here (catch-up),
    then goes back on its normal schedule. A chain whose wait ended
    while the app was closed resumes once here too."""
    while True:
        try:
            time.sleep(30)
            ran = False
            bots = {b["id"]: b for b in load_bots() if b.get("persistent")}
            if bots:
                for task in load_tasks():
                    if task.get("status") == "pending" and task.get("bot_id") in bots:
                        _run_task(task)
                        ran = True
                        break  # one task per loop, then re-check
            if not ran:
                now = int(time.time())
                for routine in load_routines():
                    if (routine.get("enabled") and routine.get("next_run")
                            and routine["next_run"] <= now):
                        _run_routine(routine)
                        ran = True
                        break  # one routine per loop, then re-check
            if not ran:
                now = int(time.time())
                for run in load_chain_runs():
                    if (run.get("status") == "waiting" and run.get("resume_at")
                            and run["resume_at"] <= now):
                        _resume_chain_run(run)
                        break  # one chain per loop, then re-check
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


# ---------- Scheduled routines that actually run ----------
# A routine is a bot + a task + a clock: daily at HH:MM, weekly on a
# weekday at HH:MM, every N minutes, or once. The background worker
# (same 30s loop as persistent tasks) runs any routine whose next_run
# has arrived. If the app was closed when a routine was due, the next
# start runs it ONCE as a catch-up, then puts it back on its normal
# schedule — it never fires a backlog of missed runs. A routine only
# runs while the app is running; it is not a system service.
ROUTINES_FILE = DATA_DIR / "routines.json"
ROUTINE_KINDS = ("daily", "weekly", "interval", "once")
# A routine that is already running must not be started again.
_RUNNING_ROUTINES = set()


def load_routines():
    routines = _load_json(ROUTINES_FILE, None)
    return routines if isinstance(routines, list) else []


def save_routines(routines):
    _save_json(ROUTINES_FILE, routines)
    return routines


def _parse_hhmm(value):
    """'09:30' -> (9, 30); anything else -> None."""
    if not isinstance(value, str):
        return None
    parts = value.strip().split(":")
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        return None
    h, m = int(parts[0]), int(parts[1])
    if 0 <= h <= 23 and 0 <= m <= 59:
        return h, m
    return None


def _next_run_after(routine, from_ts):
    """Next epoch the routine should run, strictly after from_ts.
    Local time, as the user reads it on their own computer."""
    kind = routine.get("kind")
    if kind == "interval":
        minutes = routine.get("interval_minutes") or 60
        return int(from_ts) + int(minutes) * 60
    hm = _parse_hhmm(routine.get("time") or "")
    if not hm:
        return None
    hour, minute = hm
    base = datetime.datetime.fromtimestamp(from_ts)
    # Next occurrence of HH:MM after from_ts (today if still ahead).
    cand = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if cand <= base:
        cand += datetime.timedelta(days=1)
    if kind == "daily" or kind == "once":
        return int(cand.timestamp())
    if kind == "weekly":
        weekday = routine.get("weekday")
        if not isinstance(weekday, int) or not 0 <= weekday <= 6:
            return None
        # weekday: 0 = Monday .. 6 = Sunday (datetime.weekday()).
        days_ahead = (weekday - cand.weekday()) % 7
        cand += datetime.timedelta(days=days_ahead)
        return int(cand.timestamp())
    return None


def _routine_schedule_text(routine):
    kind = routine.get("kind")
    if kind == "daily":
        return f"Daily at {routine.get('time')}"
    if kind == "weekly":
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        wd = routine.get("weekday")
        day = days[wd] if isinstance(wd, int) and 0 <= wd <= 6 else "?"
        return f"Weekly, {day} at {routine.get('time')}"
    if kind == "interval":
        return f"Every {routine.get('interval_minutes')} min"
    if kind == "once":
        return f"Once at {routine.get('time')}"
    return kind or "?"


def _run_routine(routine: dict, manual: bool = False):
    """Run one routine now: run_agent with the bot, record the run,
    then put the routine back on its schedule (or switch it off if
    it was a one-off). Returns the updated routine, or None."""
    routines = load_routines()
    stored = next((x for x in routines if x["id"] == routine["id"]), None)
    if not stored or stored.get("id") in _RUNNING_ROUTINES:
        return stored
    _RUNNING_ROUTINES.add(stored["id"])
    try:
        bot = get_bot(stored["bot_id"])
        run = {"at": int(time.time()), "status": "failed", "summary": ""}
        if not bot:
            run["summary"] = "Bot was deleted — routine switched off."
            stored["enabled"] = False
            stored["next_run"] = None
        else:
            try:
                reply, trace, extra = run_agent(bot, stored["task"])
                run["status"] = "failed" if (extra or {}).get("error") else "done"
                run["summary"] = (reply or "")[:500].replace("\n", " ").strip()
            except Exception as e:
                run["status"] = "failed"
                run["summary"] = f"Routine failed: {e}"
            # Remember what happened, like a Hermes task does.
            try:
                mem = load_memory(bot["id"])
                mem.setdefault("facts", []).append(
                    f"Routine '{stored['name']}' ran ({run['status']}): {run['summary'][:200]}")
                save_memory(bot["id"], mem)
            except Exception:
                pass
            # Learn from the daily work: record what the user wants
            # this routine to do, so the bot brings it back next time
            # (e.g. how they price a quotation). Only done runs teach.
            if run["status"] == "done":
                _record_learning(
                    bot["id"], None, "routine", stored["name"],
                    f"Daily work — routine '{stored['name']}': the user wants this done regularly: "
                    f"{stored['task'][:200]} Last result: {run['summary'][:200]}")
        stored.setdefault("runs", []).append(run)
        stored["runs"] = stored["runs"][-20:]
        stored["last_run"] = run["at"]
        stored["last_status"] = run["status"]
        stored["last_result"] = run["summary"]
        if stored.get("kind") == "once":
            # One-off: done, switch it off. A manual run counts too.
            stored["enabled"] = False
            stored["next_run"] = None
        elif stored.get("enabled"):
            stored["next_run"] = _next_run_after(stored, int(time.time()))
        save_routines(routines)
        return stored
    finally:
        _RUNNING_ROUTINES.discard(stored["id"])


def _validate_routine_fields(body, routine=None):
    """Validate + normalise the fields a routine is created/patched
    with. Returns (fields, error) — error is a message or None."""
    fields = {}
    if routine is not None:
        fields.update({k: routine.get(k) for k in
                       ("name", "bot_id", "task", "kind", "time", "weekday",
                        "interval_minutes")})
    for key in ("name", "task"):
        if key in body:
            val = (body.get(key) or "").strip()
            if not val:
                return None, f"Give the routine a {key}."
            fields[key] = val
    if "bot_id" in body:
        fields["bot_id"] = (body.get("bot_id") or "").strip()
    if "kind" in body:
        kind = (body.get("kind") or "").strip().lower()
        if kind not in ROUTINE_KINDS:
            return None, "Kind must be daily, weekly, interval or once."
        fields["kind"] = kind
    if "time" in body:
        fields["time"] = (body.get("time") or "").strip()
    if "weekday" in body and body.get("weekday") is not None:
        try:
            fields["weekday"] = int(body.get("weekday"))
        except (TypeError, ValueError):
            return None, "Weekday must be 0 (Monday) to 6 (Sunday)."
    if "interval_minutes" in body and body.get("interval_minutes") is not None:
        try:
            fields["interval_minutes"] = int(body.get("interval_minutes"))
        except (TypeError, ValueError):
            return None, "Interval must be a number of minutes."
    if routine is None:
        for key in ("name", "bot_id", "task", "kind"):
            if not fields.get(key):
                return None, f"Give the routine a {key}."
    kind = fields.get("kind")
    if kind in ("daily", "weekly", "once"):
        if not _parse_hhmm(fields.get("time") or ""):
            return None, "Give a time like 09:00."
    if kind == "weekly":
        wd = fields.get("weekday")
        if not isinstance(wd, int) or not 0 <= wd <= 6:
            return None, "Pick a weekday (0 = Monday … 6 = Sunday)."
    if kind == "interval":
        mins = fields.get("interval_minutes")
        if not isinstance(mins, int) or not 1 <= mins <= 10080:
            return None, "Interval must be between 1 and 10080 minutes."
    if fields.get("bot_id") and not get_bot(fields["bot_id"]):
        return None, "That bot does not exist."
    return fields, None


class RoutineIn(BaseModel):
    name: str = ""
    bot_id: str = ""
    task: str = ""
    kind: str = ""
    time: str = ""
    weekday: int | None = None
    interval_minutes: int | None = None


@app.get("/api/routines")
def list_routines():
    routines = sorted(load_routines(), key=lambda r: (r.get("next_run") is None, r.get("next_run") or 0))
    for r in routines:
        r["schedule_text"] = _routine_schedule_text(r)
    return routines


@app.post("/api/routines", status_code=201)
def create_routine(body: RoutineIn):
    fields, error = _validate_routine_fields(body.model_dump())
    if error:
        raise HTTPException(400, error)
    routine = {"id": uuid.uuid4().hex[:8], **fields, "enabled": True,
               "runs": [], "last_run": None, "last_status": None,
               "last_result": "", "created_at": int(time.time())}
    routine["next_run"] = _next_run_after(routine, int(time.time()))
    routines = load_routines()
    routines.append(routine)
    save_routines(routines)
    routine["schedule_text"] = _routine_schedule_text(routine)
    return routine


@app.get("/api/routines/{routine_id}")
def get_routine(routine_id: str):
    routine = next((x for x in load_routines() if x["id"] == routine_id), None)
    if not routine:
        raise HTTPException(404, "Routine not found")
    routine["schedule_text"] = _routine_schedule_text(routine)
    return routine


@app.patch("/api/routines/{routine_id}")
def update_routine(routine_id: str, body: dict):
    routines = load_routines()
    routine = next((x for x in routines if x["id"] == routine_id), None)
    if not routine:
        raise HTTPException(404, "Routine not found")
    fields, error = _validate_routine_fields(body, routine)
    if error:
        raise HTTPException(400, error)
    schedule_changed = any(fields.get(k) != routine.get(k) for k in
                           ("kind", "time", "weekday", "interval_minutes"))
    routine.update(fields)
    if "enabled" in body:
        routine["enabled"] = bool(body.get("enabled"))
    # A changed schedule, or an enabled routine with no next run, gets
    # a fresh next run. A disabled routine keeps its next_run, so
    # switching it back on catches up once, like a missed run.
    if schedule_changed or (routine.get("enabled") and not routine.get("next_run")):
        if routine.get("enabled"):
            routine["next_run"] = _next_run_after(routine, int(time.time()))
    save_routines(routines)
    routine["schedule_text"] = _routine_schedule_text(routine)
    return routine


@app.delete("/api/routines/{routine_id}")
def delete_routine(routine_id: str):
    routines = [x for x in load_routines() if x["id"] != routine_id]
    save_routines(routines)
    return {"deleted": routine_id}


@app.post("/api/routines/{routine_id}/run")
def run_routine_now(routine_id: str):
    routine = next((x for x in load_routines() if x["id"] == routine_id), None)
    if not routine:
        raise HTTPException(404, "Routine not found")
    if routine.get("id") in _RUNNING_ROUTINES:
        raise HTTPException(409, "Routine is already running")
    result = _run_routine(routine, manual=True)
    if not result:
        raise HTTPException(404, "Routine not found")
    result["schedule_text"] = _routine_schedule_text(result)
    return result


# ---------- Learnings — what the team learns from daily work ----------
# A learning is a durable record of what the user wants, learned from
# work that actually happened (a routine that ran, an office job the
# user approved) or added by hand (e.g. "Always add 12% margin to
# Cisco quotes"). Learnings are shown back to the bot in its prompt
# (run_agent) and to the team in an office job prompt, so the team
# presents what it learned when the user needs it — e.g. the pricing
# it learned when drafting the next quotation. They are a record, not
# a model: with a real model the bot applies them; in mock mode they
# are recorded and shown, never invented.
LEARNINGS_FILE = DATA_DIR / "learnings.json"


def load_learnings():
    learnings = _load_json(LEARNINGS_FILE, None)
    return learnings if isinstance(learnings, list) else []


def save_learnings(learnings):
    _save_json(LEARNINGS_FILE, learnings)
    return learnings


def _record_learning(bot_id, office_id, source, source_name, text):
    """Add one learning, unless the same text is already recorded for
    the same bot/office. Keeps the last 200."""
    text = (text or "").strip()
    if not text:
        return None
    learnings = load_learnings()
    for x in learnings:
        if (x.get("text") == text and x.get("bot_id") == bot_id
                and x.get("office_id") == office_id):
            return x
    entry = {"id": uuid.uuid4().hex[:8], "text": text, "bot_id": bot_id,
             "office_id": office_id, "source": source,
             "source_name": source_name, "created_at": int(time.time())}
    learnings.append(entry)
    learnings = learnings[-200:]
    save_learnings(learnings)
    return entry


def _learnings_text(bot_id=None, office_id=None):
    """Latest 10 learnings for a bot or an office, as prompt lines.
    Empty string when there is nothing to show."""
    items = [x for x in load_learnings()
             if (bot_id and x.get("bot_id") == bot_id)
             or (office_id and x.get("office_id") == office_id)]
    if not items:
        return ""
    return "\n".join(f"- {x['text']}" for x in items[-10:])


@app.get("/api/learnings")
def list_learnings(bot_id: str = "", office_id: str = ""):
    items = load_learnings()
    if bot_id:
        items = [x for x in items if x.get("bot_id") == bot_id]
    if office_id:
        items = [x for x in items if x.get("office_id") == office_id]
    return items


@app.post("/api/learnings", status_code=201)
def add_learning(body: dict):
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "Write what the team should remember.")
    bot_id = (body.get("bot_id") or "").strip() or None
    office_id = (body.get("office_id") or "").strip() or None
    if not bot_id and not office_id:
        raise HTTPException(400, "Pick a bot or an office for this learning.")
    if bot_id and not get_bot(bot_id):
        raise HTTPException(400, "That bot does not exist.")
    if office_id and not get_office(office_id):
        raise HTTPException(400, "That office does not exist.")
    entry = _record_learning(bot_id, office_id, "manual", "", text)
    return entry


@app.delete("/api/learnings/{learning_id}")
def delete_learning(learning_id: str):
    learnings = [x for x in load_learnings() if x["id"] != learning_id]
    save_learnings(learnings)
    return {"deleted": learning_id}


# ---------- Clients & Deals + deal workflows ----------
# A small local CRM, just enough for sales work: a deal is a client,
# a value and a pipeline stage (New -> Quoted -> Negotiation -> Won /
# Lost), with one activity timeline (stage moves, notes, drafts,
# workflow runs). A workflow rule fires when a deal moves TO a stage:
# it can create a task for a bot, run an office job with the team
# (which goes through the Auditor + approval gate, like any job),
# write a draft for the user to send themselves, or add a note.
# Nothing is sent out by a workflow on its own: drafts stay drafts
# until the user sends them, and office jobs wait for approval.
# (Twenty's idea, LocalBotz-sized: plain local JSON, no new stack.)
DEALS_FILE = DATA_DIR / "deals.json"
DEAL_WORKFLOWS_FILE = DATA_DIR / "deal_workflows.json"
# One pipeline per department: the same flow (deal -> stages ->
# workflows), with each trade's own stage names. The 10 sectors are
# the ones LocalBotz already ships as bot templates, plus General.
DEPARTMENT_PIPELINES = {
    "general": {"label": "General", "stages": [("new", "New"), ("quoted", "Quoted"), ("negotiation", "Negotiation"), ("won", "Won"), ("lost", "Lost")]},
    "construction": {"label": "Construction", "stages": [("new", "New lead"), ("tender", "Tender received"), ("boq", "BOQ prepared"), ("submitted", "Submitted"), ("negotiation", "Negotiation"), ("awarded", "Awarded"), ("lost", "Lost")]},
    "mep": {"label": "MEP", "stages": [("new", "New lead"), ("survey", "Site survey"), ("boq", "BOQ prepared"), ("submitted", "Submitted"), ("negotiation", "Negotiation"), ("awarded", "Awarded"), ("lost", "Lost")]},
    "electrical": {"label": "Electrical Engineering", "stages": [("new", "New lead"), ("survey", "Site survey"), ("design", "Design & BOQ"), ("submitted", "Submitted"), ("negotiation", "Negotiation"), ("awarded", "Awarded"), ("lost", "Lost")]},
    "it": {"label": "IT Services", "stages": [("new", "New lead"), ("discovery", "Discovery"), ("proposal", "Proposal"), ("negotiation", "Negotiation"), ("signed", "Signed"), ("lost", "Lost")]},
    "ecommerce": {"label": "E-commerce", "stages": [("new", "New lead"), ("brief", "Brief"), ("proposal", "Proposal"), ("negotiation", "Negotiation"), ("won", "Order won"), ("lost", "Lost")]},
    "realestate": {"label": "Real Estate", "stages": [("new", "New lead"), ("viewing", "Viewing"), ("offer", "Offer made"), ("negotiation", "Negotiation"), ("closed", "Closed"), ("lost", "Lost")]},
    "clinic": {"label": "Clinic & Healthcare", "stages": [("new", "New lead"), ("consultation", "Consultation"), ("quotation", "Quotation"), ("negotiation", "Negotiation"), ("booked", "Booked"), ("lost", "Lost")]},
    "logistics": {"label": "Logistics", "stages": [("new", "New lead"), ("quotation", "Quotation"), ("negotiation", "Negotiation"), ("booked", "Booked"), ("delivered", "Delivered"), ("lost", "Lost")]},
    "manufacturing": {"label": "Manufacturing", "stages": [("new", "New lead"), ("quotation", "Quotation"), ("sample", "Sample"), ("negotiation", "Negotiation"), ("order", "Order"), ("lost", "Lost")]},
    "hotel": {"label": "Hotel & Hospitality", "stages": [("new", "New lead"), ("enquiry", "Enquiry"), ("quotation", "Quotation"), ("negotiation", "Negotiation"), ("booked", "Booked"), ("lost", "Lost")]},
}
# The stage that means "won" in each pipeline, for the starter rules.
DEPARTMENT_WON_STAGE = {"general": "won", "construction": "awarded",
                        "mep": "awarded", "electrical": "awarded",
                        "it": "signed", "ecommerce": "won",
                        "realestate": "closed", "clinic": "booked",
                        "logistics": "delivered", "manufacturing": "order",
                        "hotel": "booked"}
WORKFLOW_ACTIONS = ("create_task", "office_job", "draft", "note")


def _pipeline(department):
    return DEPARTMENT_PIPELINES.get(department or "general",
                                     DEPARTMENT_PIPELINES["general"])


def _deal_department(deal):
    return deal.get("department") or "general"


def _stage_label(department, stage):
    return dict(_pipeline(department)["stages"]).get(stage, stage)


def load_deals():
    deals = _load_json(DEALS_FILE, None)
    return deals if isinstance(deals, list) else []


def save_deals(deals):
    _save_json(DEALS_FILE, deals)
    return deals


def _seed_deal_workflows():
    """Starter flow for every department: a won-stage draft and a
    lost-stage note, ready to use and to edit. No bot or office
    needed, so they work on a fresh install."""
    rules = []
    now = int(time.time())
    for dept, pipe in DEPARTMENT_PIPELINES.items():
        won = DEPARTMENT_WON_STAGE[dept]
        rules.append({"id": uuid.uuid4().hex[:8],
                      "name": f"{pipe['label']} — {_stage_label(dept, won)}: prepare handover",
                      "department": dept, "stage": won, "action": "draft",
                      "bot_id": None, "office_id": None,
                      "text": "Prepare the handover for {client} — {deal} ({value} {currency}). Confirm the delivery dates, the first invoice and who the client calls.",
                      "enabled": True, "created_at": now})
        rules.append({"id": uuid.uuid4().hex[:8],
                      "name": f"{pipe['label']} — Lost: record the reason",
                      "department": dept, "stage": "lost", "action": "note",
                      "bot_id": None, "office_id": None,
                      "text": "Lost {deal} ({value} {currency}) — record the reason.",
                      "enabled": True, "created_at": now})
    # One ready-made chain, so the idea is visible from day one:
    # Quoted → wait 3 days → if still Quoted, write a chase draft.
    rules.append({"id": uuid.uuid4().hex[:8],
                  "name": "General — Quoted: chase after 3 days",
                  "department": "general", "stage": "quoted",
                  "action": "chain", "bot_id": None, "office_id": None,
                  "text": "",
                  "steps": [{"type": "wait", "minutes": 4320},
                            {"type": "if", "condition": "stage_is", "value": "quoted"},
                            {"type": "draft", "text": "Hi {client}, following up on the {deal} quotation ({value} {currency}) — have you had a chance to look at it? Happy to walk through it or adjust anything."},
                            {"type": "note", "text": "Chase draft written for {deal} — still Quoted after 3 days."}],
                  "enabled": True, "created_at": now})
    save_deal_workflows(rules)
    return rules


def load_deal_workflows():
    if not DEAL_WORKFLOWS_FILE.exists():
        return _seed_deal_workflows()
    rules = _load_json(DEAL_WORKFLOWS_FILE, None)
    rules = rules if isinstance(rules, list) else []
    return [_normalize_workflow_rule(r) for r in rules]


def save_deal_workflows(rules):
    _save_json(DEAL_WORKFLOWS_FILE, rules)
    return rules


def _render_deal_text(template, deal):
    """Fill {deal} {client} {value} {currency} {stage} in a template.
    Values read like money (4,850,000), never like 4.85e+06."""
    value = deal.get("value")
    if value is None:
        value_text = ""
    elif float(value) == int(float(value)):
        value_text = f"{int(float(value)):,}"
    else:
        value_text = f"{float(value):,.2f}"
    return (template or "").replace("{deal}", deal.get("title", "")) \
        .replace("{client}", deal.get("client", "")) \
        .replace("{value}", value_text) \
        .replace("{currency}", deal.get("currency", "")) \
        .replace("{stage}", _stage_label(_deal_department(deal), deal.get("stage", "")))


CHAIN_RUNS_FILE = DATA_DIR / "chain_runs.json"
WORKFLOW_STEP_TYPES = ("create_task", "office_job", "draft", "note", "wait", "if")
WORKFLOW_IF_CONDITIONS = ("value_over", "value_under", "stage_is", "stage_is_not")


def load_chain_runs():
    runs = _load_json(CHAIN_RUNS_FILE, None)
    return runs if isinstance(runs, list) else []


def save_chain_runs(runs):
    _save_json(CHAIN_RUNS_FILE, runs)
    return runs


def _normalize_workflow_rule(rule):
    """Old rules have one action + text; new rules have a steps list.
    Old ones are read as a one-step chain, so nothing breaks."""
    if rule.get("steps"):
        return rule
    rule["steps"] = [{"type": rule.get("action") or "note",
                      "text": rule.get("text") or "",
                      "bot_id": rule.get("bot_id"),
                      "office_id": rule.get("office_id")}]
    return rule


def _wait_label(minutes):
    if minutes >= 1440 and minutes % 1440 == 0:
        days = minutes // 1440
        return f"{days} day{'s' if days != 1 else ''}"
    if minutes >= 60 and minutes % 60 == 0:
        hours = minutes // 60
        return f"{hours} hour{'s' if hours != 1 else ''}"
    return f"{minutes} minute{'s' if minutes != 1 else ''}"


def _validate_workflow_steps(steps):
    if not isinstance(steps, list) or not steps:
        raise HTTPException(400, "A workflow needs at least one step.")
    if len(steps) > 10:
        raise HTTPException(400, "A workflow can have at most 10 steps.")
    for step in steps:
        if not isinstance(step, dict):
            raise HTTPException(400, "Each step must be an object.")
        stype = step.get("type")
        if stype not in WORKFLOW_STEP_TYPES:
            raise HTTPException(400, f"Unknown step type '{stype}'.")
        if stype in ("create_task", "office_job", "draft", "note"):
            if not (step.get("text") or "").strip():
                raise HTTPException(400, f"A {stype} step needs text.")
            if stype == "create_task" and (not step.get("bot_id") or not get_bot(step.get("bot_id"))):
                raise HTTPException(400, "Pick a bot for the task step.")
            if stype == "office_job" and (not step.get("office_id") or not get_office(step.get("office_id"))):
                raise HTTPException(400, "Pick an office for the job step.")
        elif stype == "wait":
            try:
                minutes = int(step.get("minutes"))
            except (TypeError, ValueError):
                raise HTTPException(400, "A wait step needs minutes (a number).")
            if minutes < 1 or minutes > 43200:
                raise HTTPException(400, "Wait must be between 1 minute and 30 days.")
        elif stype == "if":
            cond = step.get("condition")
            if cond not in WORKFLOW_IF_CONDITIONS:
                raise HTTPException(400, "An IF step needs a condition (value over/under, or stage is/is not).")
            if cond in ("value_over", "value_under"):
                try:
                    float(step.get("value"))
                except (TypeError, ValueError):
                    raise HTTPException(400, "An IF value condition needs a number.")
            elif not any((step.get("value") or "") in dict(p["stages"]) for p in DEPARTMENT_PIPELINES.values()):
                raise HTTPException(400, "An IF stage condition needs a stage from a department's pipeline.")
    return steps


def _eval_workflow_condition(step, deal):
    cond = step.get("condition")
    value = step.get("value")
    if cond == "value_over":
        return (deal.get("value") or 0) > float(value)
    if cond == "value_under":
        return (deal.get("value") or 0) < float(value)
    if cond == "stage_is":
        return deal.get("stage") == value
    if cond == "stage_is_not":
        return deal.get("stage") != value
    return False


def _run_workflow_step(rule, step, deal):
    """One action step. Returns a one-line result. May raise."""
    stype = step.get("type")
    text = _render_deal_text(step.get("text") or "", deal)
    if stype == "create_task":
        tasks = load_tasks()
        task = {"id": uuid.uuid4().hex[:8], "bot_id": step["bot_id"],
                "goal": text, "status": "pending",
                "steps": [], "result": "", "created_at": int(time.time()),
                "finished_at": None}
        tasks.append(task)
        save_tasks(tasks)
        return f"Task created for the bot ({task['id']}). It runs on its own if the bot is persistent, or from the bot's tasks."
    if stype == "office_job":
        job = run_office_job(step["office_id"],
                             {"title": f"Deal: {deal.get('title')}",
                              "brief": text})
        return (f"Office job started ({job['id']}) — {job.get('status')}"
                + (" — waiting for your approval." if job.get("status") == "awaiting_approval" else "."))
    if stype == "draft":
        deal.setdefault("drafts", []).append(
            {"id": uuid.uuid4().hex[:8], "text": text,
             "status": "draft", "created_at": int(time.time())})
        return "Draft written on the deal — send it yourself when ready."
    if stype == "note":
        return text
    raise ValueError(f"Unknown step type '{stype}'")


def _run_workflow_chain(rule, deal, start_index=0, run=None):
    """Run a rule's steps in order from start_index. A wait step
    pauses the chain (a run record is kept and the background worker
    resumes it); an IF step whose condition fails stops the chain
    there; a step that fails stops the chain with that step marked
    failed. Returns {"status": "done"|"waiting"|"stopped"|"failed",
    "results": [{step, result}], "next_index": int,
    "resume_at": epoch or None, "run": run or None}."""
    steps = rule.get("steps") or []
    results = []
    i = start_index
    while i < len(steps):
        step = steps[i]
        stype = step.get("type")
        if stype == "wait":
            minutes = int(step.get("minutes", 60))
            resume_at = int(time.time()) + minutes * 60
            results.append({"step": "wait",
                            "result": f"Waiting {_wait_label(minutes)} — resumes automatically."})
            if run is None:
                run = {"id": uuid.uuid4().hex[:8], "rule_id": rule["id"],
                       "rule_name": rule.get("name"), "deal_id": deal["id"],
                       "deal_title": deal.get("title"),
                       "step_index": i + 1, "status": "waiting",
                       "resume_at": resume_at,
                       "created_at": int(time.time()), "finished_at": None,
                       "history": list(results)}
                runs = load_chain_runs()
                runs.append(run)
                save_chain_runs(runs)
            else:
                run["step_index"] = i + 1
                run["status"] = "waiting"
                run["resume_at"] = resume_at
                run["history"] = run.get("history", []) + results
            return {"status": "waiting", "results": results, "next_index": i + 1,
                    "resume_at": resume_at, "run": run}
        if stype == "if":
            if not _eval_workflow_condition(step, deal):
                results.append({"step": "if", "result": "Condition not met — chain stopped here."})
                return {"status": "stopped", "results": results, "next_index": i,
                        "resume_at": None, "run": run}
            results.append({"step": "if", "result": "Condition met — chain continues."})
            i += 1
            continue
        try:
            results.append({"step": stype, "result": _run_workflow_step(rule, step, deal)})
        except Exception as e:
            results.append({"step": stype, "result": f"Step failed: {e}"})
            return {"status": "failed", "results": results, "next_index": i,
                    "resume_at": None, "run": run}
        i += 1
    return {"status": "done", "results": results, "next_index": len(steps),
            "resume_at": None, "run": run}


def _resume_chain_run(run):
    """Continue a waiting chain from where it paused. The deal is
    re-read fresh, so an IF step sees the deal as it is now — a
    chase only happens if the deal is still in that stage."""
    runs = load_chain_runs()
    stored = next((x for x in runs if x["id"] == run["id"]), None)
    if not stored or stored.get("status") != "waiting":
        return
    rules = {r["id"]: r for r in load_deal_workflows()}
    rule = rules.get(run.get("rule_id"))
    deals = load_deals()
    deal = next((x for x in deals if x["id"] == run.get("deal_id")), None)
    if not rule or not deal:
        stored["status"] = "failed"
        stored["finished_at"] = int(time.time())
        stored.setdefault("history", []).append(
            {"step": "resume", "result": "The deal or the workflow no longer exists — chain stopped."})
        save_chain_runs(runs)
        return
    out = _run_workflow_chain(rule, deal, stored.get("step_index", 0), stored)
    stored["history"] = stored.get("history", []) + out["results"]
    stored["status"] = out["status"]
    stored["step_index"] = out["next_index"]
    if out["status"] == "waiting":
        stored["resume_at"] = out["resume_at"]
    else:
        stored["finished_at"] = int(time.time())
        stored["resume_at"] = None
    deal.setdefault("events", []).append(
        {"at": int(time.time()), "kind": "workflow",
         "text": f"Workflow '{rule.get('name')}' resumed ({out['status']}): "
                 + " | ".join(r["result"] for r in out["results"])})
    save_deals(deals)
    save_chain_runs(runs)


def _record_chain_run(rule, deal, out):
    """Record a finished chain (done / stopped / failed) in the
    executions log. A chain that hit a wait step already has its run
    record (created by _run_workflow_chain); this only covers chains
    that finished without waiting."""
    if out.get("run") is not None:
        return out["run"]
    run = {"id": uuid.uuid4().hex[:8], "rule_id": rule["id"],
           "rule_name": rule.get("name"), "deal_id": deal["id"],
           "deal_title": deal.get("title"),
           "step_index": len(rule.get("steps") or []), "status": out["status"],
           "resume_at": None, "created_at": int(time.time()),
           "finished_at": int(time.time()), "history": list(out["results"])}
    runs = load_chain_runs()
    runs.append(run)
    save_chain_runs(runs)
    return run


def _fire_deal_workflows(deal, old_stage, new_stage):
    """Run every enabled rule that fires on a move TO new_stage in
    this deal's department. Each rule is now a chain of steps.
    Returns [{rule, action, result, status, steps, resume_at,
    run_id}]. One rule failing never stops the others, and never
    stops the stage change itself."""
    fired = []
    for rule in load_deal_workflows():
        if not rule.get("enabled") or rule.get("stage") != new_stage:
            continue
        rule_dept = rule.get("department")
        if rule_dept and rule_dept != _deal_department(deal):
            continue
        try:
            out = _run_workflow_chain(rule, deal)
        except Exception as e:
            out = {"status": "failed",
                   "results": [{"step": "chain", "result": f"Chain failed: {e}"}],
                   "next_index": 0, "resume_at": None, "run": None}
        summary = " | ".join(r["result"] for r in out["results"])
        _record_chain_run(rule, deal, out)
        deal.setdefault("events", []).append(
            {"at": int(time.time()), "kind": "workflow",
             "text": f"Workflow '{rule.get('name')}' ran ({out['status']}): {summary}"})
        fired.append({"rule": rule.get("name"), "action": "chain",
                      "result": summary, "status": out["status"],
                      "steps": out["results"],
                      "resume_at": out.get("resume_at"),
                      "run_id": (out.get("run") or {}).get("id")})
    return fired


@app.get("/api/deals/pipelines")
def list_deal_pipelines():
    return DEPARTMENT_PIPELINES


@app.get("/api/deals")
def list_deals():
    deals = sorted(load_deals(), key=lambda d: d.get("updated_at", 0), reverse=True)
    for d in deals:
        d["department"] = _deal_department(d)
        d["department_label"] = _pipeline(d["department"])["label"]
        d["stage_label"] = _stage_label(d["department"], d.get("stage"))
    return deals


@app.post("/api/deals", status_code=201)
def create_deal(body: dict):
    title = (body.get("title") or "").strip()
    client = (body.get("client") or "").strip()
    if not title or not client:
        raise HTTPException(400, "Give the deal a title and a client.")
    department = (body.get("department") or "general").strip().lower()
    if department not in DEPARTMENT_PIPELINES:
        raise HTTPException(400, "Unknown department.")
    value = body.get("value")
    if value in ("", None):
        value = None
    else:
        try:
            value = float(value)
        except (TypeError, ValueError):
            raise HTTPException(400, "Value must be a number.")
    deal = {"id": uuid.uuid4().hex[:8], "title": title, "client": client,
            "contact": (body.get("contact") or "").strip(),
            "value": value,
            "currency": (body.get("currency") or "QAR").strip() or "QAR",
            "department": department, "stage": "new", "events": [], "drafts": [],
            "created_at": int(time.time()), "updated_at": int(time.time())}
    deal["events"].append({"at": int(time.time()), "kind": "stage",
                           "text": f"Deal created ({_stage_label(department, 'new')})."})
    deals = load_deals()
    deals.append(deal)
    save_deals(deals)
    deal["department_label"] = _pipeline(department)["label"]
    deal["stage_label"] = _stage_label(department, "new")
    return deal


@app.get("/api/deals/{deal_id}")
def get_deal(deal_id: str):
    deal = next((x for x in load_deals() if x["id"] == deal_id), None)
    if not deal:
        raise HTTPException(404, "Deal not found")
    deal["department"] = _deal_department(deal)
    deal["department_label"] = _pipeline(deal["department"])["label"]
    deal["stage_label"] = _stage_label(deal["department"], deal.get("stage"))
    return deal


@app.patch("/api/deals/{deal_id}")
def update_deal(deal_id: str, body: dict):
    deals = load_deals()
    deal = next((x for x in deals if x["id"] == deal_id), None)
    if not deal:
        raise HTTPException(404, "Deal not found")
    fired = []
    old_stage = deal.get("stage")
    for key in ("title", "client", "contact", "currency"):
        if key in body and (body.get(key) or "").strip():
            deal[key] = (body.get(key) or "").strip()
    if "value" in body:
        if body.get("value") in ("", None):
            deal["value"] = None
        else:
            try:
                deal["value"] = float(body.get("value"))
            except (TypeError, ValueError):
                raise HTTPException(400, "Value must be a number.")
    if "note" in body and (body.get("note") or "").strip():
        deal.setdefault("events", []).append(
            {"at": int(time.time()), "kind": "note",
             "text": (body.get("note") or "").strip()})
    if "department" in body:
        new_dept = (body.get("department") or "").strip().lower()
        if new_dept not in DEPARTMENT_PIPELINES:
            raise HTTPException(400, "Unknown department.")
        if new_dept != _deal_department(deal):
            deal["department"] = new_dept
            if deal.get("stage") not in dict(_pipeline(new_dept)["stages"]):
                deal["stage"] = "new"
                old_stage = "new"
                deal.setdefault("events", []).append(
                    {"at": int(time.time()), "kind": "stage",
                     "text": f"Moved to the {_pipeline(new_dept)['label']} pipeline — stage reset to {_stage_label(new_dept, 'new')}."})
    if "stage" in body:
        new_stage = (body.get("stage") or "").strip().lower()
        dept = _deal_department(deal)
        if new_stage not in dict(_pipeline(dept)["stages"]):
            raise HTTPException(400, f"'{new_stage}' is not a stage in the {_pipeline(dept)['label']} pipeline.")
        if new_stage != old_stage:
            deal["stage"] = new_stage
            deal.setdefault("events", []).append(
                {"at": int(time.time()), "kind": "stage",
                 "text": f"Moved {_stage_label(dept, old_stage)} → {_stage_label(dept, new_stage)}."})
            fired = _fire_deal_workflows(deal, old_stage, new_stage)
    deal["updated_at"] = int(time.time())
    save_deals(deals)
    deal["department"] = _deal_department(deal)
    deal["department_label"] = _pipeline(deal["department"])["label"]
    deal["stage_label"] = _stage_label(deal["department"], deal.get("stage"))
    deal["workflows_fired"] = fired
    return deal


@app.delete("/api/deals/{deal_id}")
def delete_deal(deal_id: str):
    deals = [x for x in load_deals() if x["id"] != deal_id]
    save_deals(deals)
    return {"deleted": deal_id}


@app.delete("/api/deals/{deal_id}/drafts/{draft_id}")
def delete_deal_draft(deal_id: str, draft_id: str):
    deals = load_deals()
    deal = next((x for x in deals if x["id"] == deal_id), None)
    if not deal:
        raise HTTPException(404, "Deal not found")
    deal["drafts"] = [d for d in deal.get("drafts", []) if d["id"] != draft_id]
    save_deals(deals)
    return {"deleted": draft_id}


@app.get("/api/deal-workflows")
def list_deal_workflows():
    return load_deal_workflows()


@app.get("/api/chain-runs")
def list_chain_runs():
    return sorted(load_chain_runs(), key=lambda r: r.get("created_at", 0), reverse=True)


@app.post("/api/chain-runs/{run_id}/cancel")
def cancel_chain_run(run_id: str):
    runs = load_chain_runs()
    run = next((x for x in runs if x["id"] == run_id), None)
    if not run:
        raise HTTPException(404, "Chain run not found")
    if run.get("status") != "waiting":
        raise HTTPException(400, "Only a waiting chain can be cancelled.")
    run["status"] = "cancelled"
    run["finished_at"] = int(time.time())
    save_chain_runs(runs)
    return run


@app.post("/api/chain-runs/{run_id}/rerun")
def rerun_chain_run(run_id: str):
    """Re-run a finished chain from its first step, on the same deal,
    with the deal's current values. A waiting chain cannot be re-run
    — cancel it first, or let it resume. The re-run is recorded as a
    new run in the executions log."""
    runs = load_chain_runs()
    run = next((x for x in runs if x["id"] == run_id), None)
    if not run:
        raise HTTPException(404, "Chain run not found")
    if run.get("status") == "waiting":
        raise HTTPException(400, "This chain is still waiting — cancel it first, or let it resume.")
    rule = next((r for r in load_deal_workflows() if r["id"] == run["rule_id"]), None)
    deals = load_deals()
    deal = next((d for d in deals if d["id"] == run["deal_id"]), None)
    if not rule or not deal:
        raise HTTPException(400, "The deal or the workflow no longer exists — this chain cannot re-run.")
    try:
        out = _run_workflow_chain(rule, deal)
    except Exception as e:
        out = {"status": "failed",
               "results": [{"step": "chain", "result": f"Chain failed: {e}"}],
               "next_index": 0, "resume_at": None, "run": None}
    summary = " | ".join(r["result"] for r in out["results"])
    deal.setdefault("events", []).append(
        {"at": int(time.time()), "kind": "workflow",
         "text": f"Workflow '{rule.get('name')}' re-ran ({out['status']}): {summary}"})
    save_deals(deals)
    new_run = _record_chain_run(rule, deal, out)
    return {"status": out["status"], "results": out["results"],
            "resume_at": out.get("resume_at"), "run_id": new_run["id"]}


@app.post("/api/deal-workflows", status_code=201)
def create_deal_workflow(body: dict):
    name = (body.get("name") or "").strip()
    stage = (body.get("stage") or "").strip().lower()
    department = (body.get("department") or "").strip().lower() or None
    if not name:
        raise HTTPException(400, "Give the workflow a name.")
    if department and department not in DEPARTMENT_PIPELINES:
        raise HTTPException(400, "Unknown department.")
    if department:
        if stage not in dict(_pipeline(department)["stages"]):
            raise HTTPException(400, f"'{stage}' is not a stage in the {_pipeline(department)['label']} pipeline.")
    elif not any(stage in dict(p["stages"]) for p in DEPARTMENT_PIPELINES.values()):
        raise HTTPException(400, "Unknown stage — pick one from a department's pipeline.")
    steps = body.get("steps")
    if steps is not None:
        steps = _validate_workflow_steps(steps)
        action = "chain" if len(steps) > 1 else steps[0]["type"]
        text = steps[0].get("text", "") if len(steps) == 1 else ""
        bot_id = steps[0].get("bot_id") if len(steps) == 1 else None
        office_id = steps[0].get("office_id") if len(steps) == 1 else None
    else:
        # Legacy single-action form: one step.
        action = (body.get("action") or "").strip()
        text = (body.get("text") or "").strip()
        if action not in WORKFLOW_ACTIONS:
            raise HTTPException(400, "Action must be create_task, office_job, draft or note.")
        if not text:
            raise HTTPException(400, "Write what the workflow should do (the task, brief, draft or note).")
        bot_id = (body.get("bot_id") or "").strip() or None
        office_id = (body.get("office_id") or "").strip() or None
        if action == "create_task":
            if not bot_id or not get_bot(bot_id):
                raise HTTPException(400, "Pick a bot for the task.")
        if action == "office_job":
            if not office_id or not get_office(office_id):
                raise HTTPException(400, "Pick an office for the job.")
        steps = [{"type": action, "text": text, "bot_id": bot_id, "office_id": office_id}]
    rule = {"id": uuid.uuid4().hex[:8], "name": name, "stage": stage,
            "department": department,
            "action": action, "bot_id": bot_id, "office_id": office_id,
            "text": text, "steps": steps,
            "enabled": True, "created_at": int(time.time())}
    rules = load_deal_workflows()
    rules.append(rule)
    save_deal_workflows(rules)
    return rule


@app.patch("/api/deal-workflows/{rule_id}")
def update_deal_workflow(rule_id: str, body: dict):
    rules = load_deal_workflows()
    rule = next((x for x in rules if x["id"] == rule_id), None)
    if not rule:
        raise HTTPException(404, "Workflow not found")
    if "enabled" in body:
        rule["enabled"] = bool(body.get("enabled"))
    if "name" in body and (body.get("name") or "").strip():
        rule["name"] = (body.get("name") or "").strip()
    if "text" in body and (body.get("text") or "").strip():
        rule["text"] = (body.get("text") or "").strip()
    if "steps" in body:
        steps = _validate_workflow_steps(body.get("steps"))
        rule["steps"] = steps
        rule["action"] = "chain" if len(steps) > 1 else steps[0]["type"]
        rule["text"] = steps[0].get("text", "") if len(steps) == 1 else ""
    save_deal_workflows(rules)
    return rule


@app.delete("/api/deal-workflows/{rule_id}")
def delete_deal_workflow(rule_id: str):
    rules = [x for x in load_deal_workflows() if x["id"] != rule_id]
    save_deal_workflows(rules)
    return {"deleted": rule_id}


# ---------- Settings + Library endpoints (one store each, shared by both) ----------
@app.get("/api/settings")
def get_settings():
    st = load_settings()
    st["data_location"] = str(DATA_DIR)
    st["app_version"] = APP_VERSION
    st["workspace_absolute"] = str(WORKSPACE_DIR)
    st["autostart"] = _autostart_enabled()
    st["autostart_path"] = str(_autostart_path())
    return st

@app.post("/api/settings")
def update_settings(body: dict):
    st = load_settings()
    for k in ("default_provider", "default_model", "workspace_folder", "theme"):
        if body.get(k):
            st[k] = str(body[k]).strip()
    if body.get("onboarding_done") is True:
        st["onboarding_done"] = True
    if body.get("run_mode") in ("computer", "subscriptions", "rent"):
        st["run_mode"] = body["run_mode"]
    if body.get("autostart") is not None:
        ok, msg = _set_autostart(bool(body["autostart"]))
        if not ok:
            raise HTTPException(500, msg)
        st["autostart"] = bool(body["autostart"])
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
