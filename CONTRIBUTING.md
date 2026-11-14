# Contributing to LocalBotz

Thanks for helping! This is a small, local-first project — keep changes
simple, cross-platform (Windows / macOS / Linux) and offline-first.

## Quick start

```bash
git clone https://github.com/<username>/<repo>.git
cd <repo>
./start.sh --light --mock   # macOS / Linux — core only, no browser, mock model
# or: start.bat --light --mock   (Windows)
```

Then open http://localhost:8000.

## Rules

- **No secrets in commits.** API keys and tokens live only in `.env`
  (gitignored). If you add a new provider, add its key name to
  `.env.example` as a commented blank line — never a real value.
- **Local first.** The app must run fully offline with LM Studio
  (or Ollama). Online providers are optional and must fail with a clear
  error + a fallback to the local model when they are unreachable.
- **Cross-platform.** Use `pathlib`, no hardcoded OS paths, no
  OS-only shell commands. File/shell commands in `app.py` are
  implemented in Python for this reason — keep it that way.
- **Playwright is optional.** Browser tools must degrade gracefully
  when Playwright/Chromium is not installed (clear message, no crash).
- **Don't fake status.** A connector, channel or server is `not_connected`
  until a real check proves otherwise. Never report a fake "reachable".
- **Small PRs.** One feature per PR, with a short note in the PR
  description about what you tested (`--mock` at minimum).

## Tests

There is no test suite yet in v0.3.0. Before opening a PR, at least run:

```bash
python app.py --mock --port 8002
curl http://127.0.0.1:8002/health
curl http://127.0.0.1:8002/api/templates
```

and check the UI loads at http://localhost:8002.
