# Security policy

## Reporting a vulnerability

Please do **not** open a public issue for a security problem.
Email the repository owner privately (see the GitHub profile) with
a description and, if possible, steps to reproduce. We will
acknowledge it and fix it before disclosing anything.

## What is protected, and how

- **Provider API keys stay on the machine that owns them.** In the
  client app they live only in `.env` (gitignored), are shown masked
  only (`sk-...abcd`), and are never logged or returned by the API.
- **The VPS Premium gateway** (`server/`) holds the owner's provider
  API keys only in its own `.env` on the VPS. Clients authenticate
  with a separate token (`PREMIUM_API_TOKEN`) that the owner issues;
  that token is *not* a provider key, and provider keys are never
  sent to clients or written to logs.
- **The client binds to `127.0.0.1` by default** — only the local
  computer can reach it. Do not expose it publicly without adding
  authentication in front of it.
- **Super Admin is token-gated.** Set a long random `ADMIN_TOKEN` in
  `.env` to enable the Super Admin panel; without it the admin
  endpoints return 401/403. Rotate it if it leaks. BYOK keys live in
  `data/byok/<workspace>.json` (gitignored) and are shown masked only.
- **Bots are sandboxed:** files are restricted to `./workspace`,
  shell commands are allowlisted with shell metacharacters rejected
  and a 30 s timeout.

## Known limits (v0.3.0)

- WhatsApp / Telegram / Discord live listeners and Gmail / Drive /
  Calendar OAuth flows are configuration only, not live.
- Scheduled routines are stored and shown, but nothing runs them yet.
- The VPS gateway's tool-use translation for Claude is best-effort
  (see `server/README.md`).
