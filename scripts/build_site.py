#!/usr/bin/env python3
"""Build the LocalBotz company website (static HTML, repo root).

Generates the multi-page site (hero -> features -> use-case gallery ->
bundle/cross-sell -> pricing strip -> FAQ -> footer), using LocalBotz's
own content only.

Usage:  python3 scripts/build_site.py
Writes: landing.html (reworked in place), products.html, app.html,
        office.html, workroom.html, deals.html, voice.html,
        whatsapp.html, leads.html, pricing.html, about.html, help.html,
        download.html + docs/download.html (same content, docs/ paths —
        the docs/index.html mirror pattern, NOT byte-identical: a byte
        copy would leave every nav link in docs/download.html broken),
        docs/index.html (mirror of landing.html with docs/ paths).

Shared header/footer/CSS live here, so a nav change is one edit.
No other company's names, text or branding anywhere.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CSS = """
:root {
  --teal: #0d9488;
  --teal-dark: #0f766e;
  --teal-light: #73bbbb;
  --mint: #eafaf7;
  --navy: #0f2a3d;
  --ink: #1f2a30;
  --muted: #5b6b72;
  --line: #dfe9e7;
  --soft: #f6fbfa;
  --green: #15803d;
}
* { box-sizing: border-box; }
body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; color: var(--ink); background: #fff; line-height: 1.6; }
a { color: var(--teal-dark); }
.wrap { max-width: 1080px; margin: 0 auto; padding: 0 20px; }
header.top { border-bottom: 1px solid var(--line); padding: 12px 0; }
header.top .wrap { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
header.top img { height: 40px; width: auto; }
header.top .name { font-weight: 800; font-size: 20px; color: var(--navy); text-decoration: none; }
header.top nav { margin-left: auto; font-size: 14px; display: flex; flex-wrap: wrap; gap: 4px 16px; }
header.top nav a { text-decoration: none; font-weight: 600; color: var(--navy); }
header.top nav a:hover { color: var(--teal-dark); }
.hero { text-align: center; padding: 56px 20px 40px; background: linear-gradient(180deg, var(--mint) 0%, #ffffff 100%); }
.hero h1 { font-size: 38px; line-height: 1.15; margin: 0 0 10px; color: var(--navy); }
.hero p.tagline { font-size: 19px; color: var(--muted); margin: 0 auto 8px; max-width: 700px; }
.hero p.sub { color: var(--muted); max-width: 700px; margin: 12px auto 0; }
.btn { display: inline-block; background: linear-gradient(90deg, var(--teal), var(--teal-dark)); color: #fff !important; text-decoration: none; font-weight: 700; font-size: 17px; padding: 13px 24px; border-radius: 999px; margin-top: 18px; }
.btn:hover { opacity: 0.92; }
.btn.small { font-size: 15px; padding: 10px 18px; }
.btn.ghost { background: #fff; color: var(--teal-dark) !important; border: 2px solid var(--teal-dark); }
h2.section { font-size: 29px; margin: 56px 0 8px; text-align: center; color: var(--navy); }
p.lead { text-align: center; color: var(--muted); max-width: 720px; margin: 0 auto 28px; }
.cards { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 20px; margin-top: 8px; }
@media (max-width: 900px) { .cards { grid-template-columns: 1fr 1fr; } }
@media (max-width: 600px) { .cards { grid-template-columns: 1fr; } }
.card { border: 1px solid var(--line); border-radius: 16px; padding: 24px; background: #fff; }
.card .tag { font-size: 13px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; color: var(--teal-dark); }
.card h3 { font-size: 19px; margin: 8px 0 6px; color: var(--navy); }
.card h3 a { color: var(--navy); text-decoration: none; }
.card h3 a:hover { color: var(--teal-dark); }
.card p { color: var(--muted); margin: 0; font-size: 15px; }
.card .icon { font-size: 30px; }
.features { display: grid; grid-template-columns: 1fr 1fr; gap: 16px 28px; margin-top: 8px; }
@media (max-width: 700px) { .features { grid-template-columns: 1fr; } }
.feature { display: flex; gap: 12px; align-items: flex-start; }
.feature .tick { flex: none; width: 26px; height: 26px; border-radius: 50%; background: var(--mint); color: var(--teal-dark); font-weight: 800; text-align: center; line-height: 26px; }
.feature p { margin: 0; font-size: 16px; }
.feature p strong { color: var(--navy); }
.steps { display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; margin-top: 8px; }
@media (max-width: 800px) { .steps { grid-template-columns: 1fr 1fr; } }
@media (max-width: 520px) { .steps { grid-template-columns: 1fr; } }
.step { border: 1px solid var(--line); border-radius: 16px; padding: 24px 20px; background: #fff; }
.step .num { display: inline-flex; align-items: center; justify-content: center; width: 40px; height: 40px; border-radius: 50%; background: var(--teal); color: #fff; font-weight: 800; font-size: 18px; margin-bottom: 12px; }
.step h3 { font-size: 18px; margin: 0 0 6px; color: var(--navy); }
.step p { color: var(--muted); margin: 0; font-size: 15px; }
.open { text-align: center; background: linear-gradient(180deg, var(--mint) 0%, #ffffff 100%); border: 1px solid var(--line); border-radius: 16px; padding: 32px 24px; margin-top: 8px; }
.open h3 { margin: 0 0 8px; font-size: 22px; color: var(--navy); }
.open p { color: var(--muted); margin: 0 auto; max-width: 680px; }
.fine { font-size: 14px; color: var(--muted); margin-top: 14px; text-align: center; }
table { border-collapse: collapse; width: 100%; margin-top: 8px; font-size: 15px; }
th, td { border: 1px solid var(--line); padding: 10px 12px; text-align: left; }
th { background: var(--mint); color: var(--navy); }
td.num { text-align: right; }
.faq { margin-top: 8px; }
.faq details { border: 1px solid var(--line); border-radius: 12px; padding: 16px 18px; margin: 10px 0; background: #fff; }
.faq summary { font-weight: 700; cursor: pointer; font-size: 17px; color: var(--navy); }
.faq p { margin: 10px 0 0; color: var(--muted); }
footer { margin-top: 60px; border-top: 1px solid var(--line); padding: 32px 0 40px; color: var(--muted); font-size: 15px; }
.foot-cols { display: grid; grid-template-columns: repeat(4, 1fr); gap: 28px; }
@media (max-width: 900px) { .foot-cols { grid-template-columns: 1fr 1fr; } }
@media (max-width: 600px) { .foot-cols { grid-template-columns: 1fr; } }
.nav-group { position: relative; display: inline-block; }
.nav-drop { display: none; position: absolute; top: 100%; left: 0; background: #fff; border: 1px solid var(--line); border-radius: 12px; padding: 8px 0; min-width: 230px; box-shadow: 0 8px 24px rgba(15,42,61,.12); z-index: 10; }
.nav-drop a { display: block; padding: 8px 16px; }
.nav-group:hover .nav-drop, .nav-group:focus-within .nav-drop { display: block; }
@media (max-width: 700px) {
  header.top nav { flex-direction: column; align-items: flex-start; gap: 2px; }
  .nav-group { display: block; }
  .nav-drop { position: static; display: block; box-shadow: none; border: none; padding: 0 0 0 14px; min-width: 0; }
}
.foot-col h4 { margin: 0 0 10px; color: var(--navy); font-size: 15px; }
.foot-col a { display: block; margin: 6px 0; text-decoration: none; }
.foot-col a:hover { text-decoration: underline; }
.foot-bottom { text-align: center; margin-top: 28px; }
.foot-bottom p { margin: 6px 0; }
"""

# Site navigation, exactly as Thomas specified (2026-11-14):
# Products (LocalBotz Chat, LocalBotz for Business), Research
# (Research Areas, Publications), Open-Source AI, Company
# (About Us, Culture, Press, Customers, Jobs). Pricing and Download
# are top-level links too; every nav link is a real page.
NAV_GROUPS = [
    ("Products", "products.html", [
        ("LocalBotz Chat", "chat.html"),
        ("LocalBotz for Business", "business.html"),
    ]),
    ("Research", "research.html", [
        ("Research Areas", "research-areas.html"),
        ("Publications", "publications.html"),
    ]),
    ("Open-Source AI", "open-source.html", []),
    ("Company", "about.html", [
        ("About Us", "about.html"),
        ("Culture", "culture.html"),
        ("Press", "press.html"),
        ("Customers", "customers.html"),
        ("Jobs", "jobs.html"),
    ]),
]
NAV_SINGLE = [
    ("Pricing", "pricing.html"),
    ("Download", "download.html"),
]


def header(prefix=""):
    parts = []
    for label, href, children in NAV_GROUPS:
        if children:
            drop = "".join(
                '<a href="%s%s">%s</a>' % (prefix, h, l) for l, h in children
            )
            parts.append(
                '<span class="nav-group"><a href="%s%s">%s</a>'
                '<span class="nav-drop">%s</span></span>'
                % (prefix, href, label, drop)
            )
        else:
            parts.append('<a href="%s%s">%s</a>' % (prefix, href, label))
    for label, href in NAV_SINGLE:
        parts.append('<a href="%s%s">%s</a>' % (prefix, href, label))
    parts.append('<a href="https://github.com/webginet-sys/localbotz">GitHub</a>')
    return (
        '<header class="top">\n  <div class="wrap">\n'
        '    <a href="%slanding.html"><img src="%sassets/logo.png" alt="LocalBotz logo"></a>\n'
        '    <a class="name" href="%slanding.html">LocalBotz</a>\n'
        "    <nav>\n      %s\n    </nav>\n  </div>\n</header>\n"
        % (prefix, prefix, prefix, "".join(parts))
    )


def footer(prefix=""):
    def l(href):
        return prefix + href

    return (
        '<footer>\n  <div class="wrap">\n    <div class="foot-cols">\n'
        '      <div class="foot-col"><h4>Products</h4>\n'
        '        <a href="%s">LocalBotz Chat</a>\n'
        '        <a href="%s">LocalBotz for Business</a>\n'
        '        <a href="%s">Office — your AI team</a>\n'
        '        <a href="%s">Workroom — documents with proof</a>\n'
        '        <a href="%s">Deals &amp; workflows</a>\n'
        '        <a href="%s">Talk &amp; Live Voice</a>\n'
        '        <a href="%s">WhatsApp sales agent</a>\n'
        '        <a href="%s">Leads &amp; Marketing</a>\n      </div>\n'
        '      <div class="foot-col"><h4>Research</h4>\n'
        '        <a href="%s">Research Areas</a>\n'
        '        <a href="%s">Publications</a>\n'
        '        <a href="%s">Open-Source AI</a>\n      </div>\n'
        '      <div class="foot-col"><h4>Company</h4>\n'
        '        <a href="%s">About Us</a>\n'
        '        <a href="%s">Culture</a>\n'
        '        <a href="%s">Press</a>\n'
        '        <a href="%s">Customers</a>\n'
        '        <a href="%s">Jobs</a>\n'
        '        <a href="%s">Pricing</a>\n'
        '        <a href="%s">Download</a>\n      </div>\n'
        '      <div class="foot-col"><h4>Guides</h4>\n'
        '        <a href="%s">Help &amp; guides</a>\n'
        '        <a href="%s">Full guide (README)</a>\n'
        '        <a href="%s">Download instructions</a>\n'
        '        <a href="%s">How LocalBotz runs</a>\n'
        '        <a href="%s">Office guide</a>\n'
        '        <a href="%s">Workroom guide</a>\n'
        '        <a href="%s">Pricing guide</a>\n      </div>\n'
        "    </div>\n"
        '    <div class="foot-bottom">\n'
        "      <p>LocalBotz — free, open, and yours. Your own personal AI agent, on your own computer.</p>\n"
        "      <p>LocalBotz is a product of WEBGINET ENTERPRISE PRIVATE LIMITED. MIT licensed and built in the open. "
        '<a href="https://github.com/webginet-sys/localbotz">Read the code</a>, run it from source, or '
        '<a href="https://github.com/webginet-sys/localbotz/pulls">send a pull request</a>.</p>\n'
        "    </div>\n  </div>\n</footer>\n"
        % (
            l("chat.html"), l("business.html"), l("office.html"), l("workroom.html"),
            l("deals.html"), l("voice.html"), l("whatsapp.html"), l("leads.html"),
            l("research-areas.html"), l("publications.html"), l("open-source.html"),
            l("about.html"), l("culture.html"), l("press.html"), l("customers.html"),
            l("jobs.html"), l("pricing.html"), l("download.html"),
            l("help.html"), l("README.md"), l("DOWNLOAD.md"), l("docs/how-it-runs.md"),
            l("docs/office.md"), l("docs/workroom.md"), l("docs/pricing.md"),
        )
    )


def page(title, desc, body, prefix=""):
    return (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>%s</title>\n"
        '<meta name="description" content="%s">\n'
        "<style>%s</style>\n</head>\n<body>\n\n%s\n<main>\n%s\n</main>\n\n%s\n</body>\n</html>\n"
        % (title, desc, CSS, header(prefix), body, footer(prefix))
    )


def must_replace(text, old, new, where):
    if old not in text:
        raise SystemExit("ANCHOR NOT FOUND in %s: %r" % (where, old[:80]))
    return text.replace(old, new, 1)

# ---------------------------------------------------------------------------
# Page bodies. Every fact below comes from the repo docs; nothing is
# invented — no fake prices, testimonials, clients, papers or coverage.
# ---------------------------------------------------------------------------

PAGES = {}

PAGES["products.html"] = (
    "Products — LocalBotz",
    "Everything LocalBotz does: chat with bots on your own computer, an AI office team, documents with proof, deals, voice, WhatsApp and marketing.",
    """
  <section class="hero">
    <div class="wrap">
      <h1>Products — everything LocalBotz does</h1>
      <p class="tagline">One app on your computer, built for office, sales and marketing work. Chat with a bot, hire an AI team, or run the whole business side — all local-first, all yours.</p>
      <a class="btn" href="download.html">Get LocalBotz free</a>
    </div>
  </section>

  <div class="wrap">
    <h2 class="section">Two ways in</h2>
    <p class="lead">Start with a chat, or start with a team. Both run on the same app, on your own computer.</p>
    <div class="cards">
      <div class="card"><div class="icon">💬</div><div class="tag">Products</div><h3><a href="chat.html">LocalBotz Chat</a></h3><p>Chat with bots on your own computer. Your local model, plus Claude, GPT, Gemini and DeepSeek — building, researching and automating your work in one conversation.</p></div>
      <div class="card"><div class="icon">🏢</div><div class="tag">Products</div><h3><a href="business.html">LocalBotz for Business</a></h3><p>Office AI teams, a rented computer in the cloud, and premium models on tap. For companies that want the whole office running, not just one chat.</p></div>
      <div class="card"><div class="icon">🧠</div><div class="tag">Research</div><h3><a href="research.html">Research</a></h3><p>How LocalBotz is built — local-first models, availability-driven model lists, smart routing, learnings from daily tasks — published as open guides.</p></div>
    </div>

    <h2 class="section">The products, one by one</h2>
    <p class="lead">Every product below lives in the same app. Install once, use them all.</p>
    <div class="cards">
      <div class="card"><div class="icon">🏢</div><div class="tag">Office</div><h3><a href="office.html">Office — your AI team</a></h3><p>Hire a team, give everyone a role and a face. One boss, shared memory, and an independent Auditor who checks every job before you approve it.</p></div>
      <div class="card"><div class="icon">📁</div><div class="tag">Documents</div><h3><a href="workroom.html">Workroom — documents with proof</a></h3><p>Your BOQs, tenders and contracts in a private vault. Ask questions, get answers with the exact document and passage behind them.</p></div>
      <div class="card"><div class="icon">💼</div><div class="tag">Sales</div><h3><a href="deals.html">Deals &amp; workflows</a></h3><p>A deal pipeline for every department, workflows that act when a deal moves, and always-on monitors that chase what has gone quiet.</p></div>
      <div class="card"><div class="icon">🎙️</div><div class="tag">Voice</div><h3><a href="voice.html">Talk &amp; Live Voice</a></h3><p>Talk to your computer in plain words — no prompting, no tutorials. The bot answers in voice and shows you how, step by step, on your screen.</p></div>
      <div class="card"><div class="icon">💬</div><div class="tag">WhatsApp</div><h3><a href="whatsapp.html">WhatsApp sales agent</a></h3><p>Customers write to your WhatsApp Business number. LocalBotz drafts the reply — nothing is sent until you approve it.</p></div>
      <div class="card"><div class="icon">🎯</div><div class="tag">Growth</div><h3><a href="leads.html">Leads &amp; Marketing</a></h3><p>Hunt for new clients in your area, turn leads into deals, and publish posts — drafted, approved, then sent.</p></div>
    </div>

    <h2 class="section">How they fit together</h2>
    <p class="lead">A lead becomes a deal. A deal becomes an office job. The job's documents live in the workroom, and what the team learns is kept for the next quotation.</p>
    <div class="steps">
      <div class="step"><span class="num">1</span><h3>Find the work</h3><p>Leads hunt for new clients; deals track them through your department's pipeline.</p></div>
      <div class="step"><span class="num">2</span><h3>Do the work</h3><p>Your office team researches, writes and builds — checked by the Auditor, approved by you.</p></div>
      <div class="step"><span class="num">3</span><h3>Prove the work</h3><p>Workroom answers come with their sources. Office jobs export as real Word, Excel and PowerPoint files.</p></div>
      <div class="step"><span class="num">4</span><h3>Keep the learning</h3><p>What the team learns — your pricing, your way of working — is recorded and presented when you need it.</p></div>
    </div>

    <div class="open">
      <h3>Free to start, on your own computer</h3>
      <p>Your computer is free, your subscriptions cost whatever your provider charges, and premium models are pay-as-you-go. <a href="pricing.html">See the full price list</a>.</p>
      <p><a class="btn small" href="download.html">Download LocalBotz</a></p>
    </div>
  </div>
""",
)

PAGES["chat.html"] = (
    "LocalBotz Chat — chat with bots on your own computer",
    "LocalBotz Chat is the app: chat with bots on your own computer, on your local model or Claude, GPT, Gemini and DeepSeek.",
    """
  <section class="hero">
    <div class="wrap">
      <h1>LocalBotz Chat</h1>
      <p class="tagline">Chat with bots on your own computer. Your local model for free, plus Claude, GPT, Gemini and DeepSeek when you have internet — in one conversation.</p>
      <a class="btn" href="download.html">Get LocalBotz free</a>
      <a class="btn ghost" href="business.html">See LocalBotz for Business</a>
    </div>
  </section>

  <div class="wrap">
    <h2 class="section">What you get in the chat</h2>
    <div class="features">
      <div class="feature"><span class="tick">✓</span><p><strong>Bots with a job.</strong> Make a bot, name it, describe the job, pick a template — 47 templates across Personal Assistant, Productivity, Research, Sectors and more.</p></div>
      <div class="feature"><span class="tick">✓</span><p><strong>Your local model first.</strong> LM Studio with Qwen3.5 on your own computer, free and offline. Nothing leaves the computer unless you choose an online model.</p></div>
      <div class="feature"><span class="tick">✓</span><p><strong>Whichever models are available.</strong> The model list shows only what is actually usable right now — your computer, your keys, or premium from us.</p></div>
      <div class="feature"><span class="tick">✓</span><p><strong>It uses the computer.</strong> Browser automation and desktop control: it reads pages, fills forms, opens Excel and the BOQ, and shows you each step.</p></div>
      <div class="feature"><span class="tick">✓</span><p><strong>It remembers.</strong> Every bot has long-term memory, and the team records what it learns from your daily work.</p></div>
      <div class="feature"><span class="tick">✓</span><p><strong>It talks.</strong> Speak in plain words, hear the reply back, and watch it show you how on your own screen. <a href="voice.html">Talk &amp; Live Voice</a>.</p></div>
    </div>

    <h2 class="section">Your bots, your tools</h2>
    <p class="lead">A bot is more than a chat. Give it tools, a schedule, and the apps you use.</p>
    <div class="cards">
      <div class="card"><div class="tag">Library</div><h3>25 connectors, MCP servers, skills</h3><p>Gmail, Drive, Calendar, Slack, Telegram, Notion, Trello, GitHub, Stripe, Zoom and more — plus MCP servers that are really tested, and skills your bots can use.</p></div>
      <div class="card"><div class="tag">Routines</div><h3>Work that runs itself</h3><p>Scheduled routines that really run: every morning at 8, every Monday, every 3 hours. If the app was closed, it catches up once — never a backlog.</p></div>
      <div class="card"><div class="tag">Desktop</div><h3>Use the computer</h3><p>Observe, act, verify: the bot reads the desktop as a list of windows and controls, clicks and types by reference, then checks the result. Permission-gated, always.</p></div>
      <div class="card"><div class="tag">Languages</div><h3>199 countries, 186 languages</h3><p>Every bot speaks the language you pick — per bot, per chat, or for the whole app. Talk follows the language too.</p></div>
      <div class="card"><div class="tag">Routing</div><h3>Simple questions, free answers</h3><p>Smart routing sends simple questions to your free local model and keeps the hard work for the premium one. It never overrides a fixed choice, and never spends money silently.</p></div>
      <div class="card"><div class="tag">Permissions</div><h3>You decide what it may do</h3><p>Ask, Auto or Full — per bot, per tool. A bot on Ask cannot click, type or send anything without your say.</p></div>
    </div>

    <h2 class="section">Also in LocalBotz</h2>
    <p class="lead">The chat is the front door. Behind it, the whole office.</p>
    <div class="cards">
      <div class="card"><div class="icon">🏢</div><div class="tag">Business</div><h3><a href="business.html">LocalBotz for Business</a></h3><p>Office AI teams, a rented computer in the cloud, and premium models on tap.</p></div>
      <div class="card"><div class="icon">📁</div><div class="tag">Documents</div><h3><a href="workroom.html">Workroom</a></h3><p>Documents with proof — every answer shows its source.</p></div>
      <div class="card"><div class="icon">💼</div><div class="tag">Sales</div><h3><a href="deals.html">Deals &amp; workflows</a></h3><p>One pipeline per department, workflows that act when a deal moves.</p></div>
    </div>

    <div class="open">
      <h3>Your computer — $0. Your subscriptions — your provider's price. Premium — pay-as-you-go.</h3>
      <p><a href="pricing.html">See the full price list</a> · <a class="btn small" href="download.html">Download LocalBotz</a></p>
    </div>

    <h2 class="section">Questions people ask</h2>
    <div class="faq">
      <details><summary>Does it work without internet?</summary><p>Yes — with the local model. LM Studio and Qwen3.5 run entirely on your computer, so chat, office jobs and the workroom work offline. Online providers need internet, and the chat says so plainly when they are not reachable.</p></details>
      <details><summary>Does it generate images or videos?</summary><p>No. LocalBotz is for office, sales and marketing work — chat, documents, deals, research, automation. Image and video generation are deliberately out of scope.</p></details>
      <details><summary>Where does my data live?</summary><p>On your computer, in plain files under the data folder — bots, memory, offices, workrooms, documents. You choose the folder at install time (C: drive or D: drive), and you can back it up or delete it yourself.</p></details>
    </div>
  </div>
""",
)

PAGES["business.html"] = (
    "LocalBotz for Business — Office AI teams, Cloud Office and VPS Premium",
    "LocalBotz for Business: hire an AI office team, rent a computer in the cloud, and use premium models — for companies that want the whole office running.",
    """
  <section class="hero">
    <div class="wrap">
      <h1>LocalBotz for Business</h1>
      <p class="tagline">An AI office team on your computers — or rent one from us. The boss, the team, the memory and the premium models, run as a business.</p>
      <a class="btn" href="download.html">Get LocalBotz free</a>
      <a class="btn ghost" href="office.html">See how the Office works</a>
    </div>
  </section>

  <div class="wrap">
    <h2 class="section">Three parts, one business</h2>
    <div class="cards">
      <div class="card"><div class="icon">🏢</div><div class="tag">Teams</div><h3><a href="office.html">Office AI teams</a></h3><p>Hire a team for each department — construction, MEP, electrical, IT services, e-commerce and more. One boss, 143 roles, shared memory, and an Auditor who checks every job before you approve it.</p></div>
      <div class="card"><div class="icon">☁️</div><div class="tag">Cloud</div><h3>Cloud Office</h3><p>Rent a computer from us instead of running one yourself. Your office lives on our server — 2 vCPU, 8 GB RAM, 100 GB disk — and your team works there even when your computer is off. The monthly price is set by the server owner in the admin panel.</p></div>
      <div class="card"><div class="icon">🔑</div><div class="tag">Premium</div><h3>VPS Premium models</h3><p>Claude Sonnet, GPT and Gemini from our server, metered to your workspace wallet. Register on the server, get your own token, pick VPS Premium per bot. <a href="pricing.html">See the prices</a>.</p></div>
    </div>

    <h2 class="section">Three ways to run a business on it</h2>
    <p class="lead">The owner supplies the keys and the rules. The team just works.</p>
    <div class="steps">
      <div class="step"><span class="num">1</span><h3>Master Managed Fixed</h3><p>The owner supplies the master keys and assigns one fixed default model. Tenants do nothing — zero config — and usage is metered to their workspace wallet.</p></div>
      <div class="step"><span class="num">2</span><h3>Master User-Selectable</h3><p>The owner supplies the master keys and curates the allowed model roster. Tenants pick from the roster. No one needs their own keys.</p></div>
      <div class="step"><span class="num">3</span><h3>BYOK</h3><p>Tenants bring their own keys. The host pays nothing for API usage — local models and the tenants' own keys do the work.</p></div>
      <div class="step"><span class="num">✓</span><h3>Local models are always free</h3><p>In every mode, the local model costs the host nothing and is never metered.</p></div>
    </div>

    <h2 class="section">Built for office, sales and marketing</h2>
    <p class="lead">Construction, MEP, electrical engineering, IT services, e-commerce — and every other sector that runs on quotations, tenders and follow-ups.</p>
    <div class="cards">
      <div class="card"><div class="tag">Sales</div><h3><a href="deals.html">Deals &amp; workflows</a></h3><p>One pipeline per department, workflows that act when a deal moves, and monitors that chase what has gone quiet.</p></div>
      <div class="card"><div class="tag">Documents</div><h3><a href="workroom.html">Workroom</a></h3><p>Tenders, BOQs and contracts with proof — every answer cites its document and passage, and never invents a price or a date.</p></div>
      <div class="card"><div class="tag">Growth</div><h3><a href="leads.html">Leads &amp; Marketing</a></h3><p>Hunt for new clients, turn leads into deals, and publish posts — drafted, approved, then sent.</p></div>
      <div class="card"><div class="tag">WhatsApp</div><h3><a href="whatsapp.html">WhatsApp sales agent</a></h3><p>Customers write in, LocalBotz drafts the reply, and nothing is sent until you approve it.</p></div>
      <div class="card"><div class="tag">Voice</div><h3><a href="voice.html">Talk &amp; Live Voice</a></h3><p>Your team talks back — in plain words, in your language, on your screen.</p></div>
      <div class="card"><div class="tag">Sectors</div><h3><a href="customers.html">Who it's built for</a></h3><p>The sectors LocalBotz is built for, and what the office team does in each one.</p></div>
    </div>

    <div class="open">
      <h3>Run it your way</h3>
      <p>Your computers are free. Your subscriptions cost whatever your provider charges. Renting from us is pay-as-you-go, per 1M tokens. <a href="pricing.html">See the full price list</a>.</p>
      <p><a class="btn small" href="download.html">Download LocalBotz</a></p>
    </div>

    <h2 class="section">Questions people ask</h2>
    <div class="faq">
      <details><summary>Do I need my own API keys?</summary><p>No. In the two Master modes the owner supplies the keys and the team just works. In BYOK mode each tenant brings their own. And the local model needs no key at all.</p></details>
      <details><summary>Who sees my team's work?</summary><p>Your office, its memory and its files live on your computer — or on the rented server you registered on. Nothing is shared between workspaces, and usage is logged as counts and costs only, never message content.</p></details>
      <details><summary>What does the Cloud Office cost?</summary><p>The server owner sets the Cloud Office monthly price in the admin panel. Until it is set, the panel shows that the price is not set yet — we don't invent one here.</p></details>
    </div>
  </div>
""",
)

PAGES["research.html"] = (
    "Research — LocalBotz",
    "How LocalBotz is built: local-first models, availability-driven model lists, smart routing, learnings from daily tasks, and privacy — published as open guides.",
    """
  <section class="hero">
    <div class="wrap">
      <h1>Research</h1>
      <p class="tagline">LocalBotz is built in the open, and its work is published as open guides — not locked in papers. Here is what we work on, and where to read it.</p>
    </div>
  </section>

  <div class="wrap">
    <div class="cards">
      <div class="card"><div class="icon">🔬</div><div class="tag">Research</div><h3><a href="research-areas.html">Research Areas</a></h3><p>The five things LocalBotz works on: local-first models, availability-driven model lists, smart routing, learnings from daily tasks, and privacy — data that stays on your computer.</p></div>
      <div class="card"><div class="icon">📚</div><div class="tag">Research</div><h3><a href="publications.html">Publications</a></h3><p>The real technical docs and guides from the repo — how each part of LocalBotz works, its limits stated honestly, and how to run it yourself.</p></div>
      <div class="card"><div class="icon">💻</div><div class="tag">Open source</div><h3><a href="open-source.html">Open-Source AI</a></h3><p>Every line of LocalBotz is MIT licensed and on GitHub. Read the code, run it from source, or send a pull request.</p></div>
    </div>

    <h2 class="section">How we work</h2>
    <div class="features">
      <div class="feature"><span class="tick">✓</span><p><strong>Build first, write it down.</strong> A feature ships in the app, is tested, and then gets a guide that says what it does — and what it does not do yet.</p></div>
      <div class="feature"><span class="tick">✓</span><p><strong>Honest limits, in writing.</strong> Every guide has a limits section: what was only tested in mock mode, what needs a key, what is not built yet.</p></div>
      <div class="feature"><span class="tick">✓</span><p><strong>Learn from others, build our own.</strong> Public projects are read for ideas — never copied. All LocalBotz code is written from scratch, under its own name.</p></div>
      <div class="feature"><span class="tick">✓</span><p><strong>Local first, always.</strong> The research question behind everything: how much can an AI team do on the user's own computer, without a cloud bill and without giving its data away?</p></div>
    </div>

    <div class="open">
      <h3>Read the work</h3>
      <p>Start with the <a href="research-areas.html">research areas</a>, then the <a href="publications.html">publications</a> — or go straight to <a href="https://github.com/webginet-sys/localbotz">the code on GitHub</a>.</p>
    </div>
  </div>
""",
)

PAGES["research-areas.html"] = (
    "Research Areas — LocalBotz",
    "The five things LocalBotz works on: local-first models, availability-driven model lists, smart routing, learnings from daily tasks, and privacy.",
    """
  <section class="hero">
    <div class="wrap">
      <h1>Research Areas</h1>
      <p class="tagline">Five questions, worked on in the open. Each one ships in the app — and each one has a guide that says what it does and what it does not do yet.</p>
    </div>
  </section>

  <div class="wrap">
    <div class="cards">
      <div class="card"><div class="tag">Area 1</div><h3>🖥️ Local-first models</h3><p>How much can an AI team do on the user's own computer? LocalBotz runs on a downloaded local model — LM Studio with Qwen3.5 by default, Ollama as a fallback — free, offline, and private. The question is how far that goes before an online model is needed, and the app answers it honestly: if the local model is not running, it says so instead of pretending.</p><p><a href="docs/how-it-runs.md">How LocalBotz runs →</a></p></div>
      <div class="card"><div class="tag">Area 2</div><h3>📋 Availability-driven model lists</h3><p>Most apps show a fixed list of models. LocalBotz shows only what is actually usable right now: it probes the local model, the VPS, and each provider — a model only appears as usable when its provider is reachable or its key is set. Unavailable models are greyed out, with the reason.</p><p><a href="docs/model-reference.md">Model reference →</a></p></div>
      <div class="card"><div class="tag">Area 3</div><h3>🧭 Smart routing</h3><p>Simple questions should not cost premium money. When routing is on, a short plain question goes to the free local model, and the hard work — drafting, analysis, research — goes to the premium one. Routing never overrides a fixed choice, never routes a bot that is already local, and if the local model is not running when a question is routed to it, the chat fails honestly instead of spending money silently.</p><p><a href="docs/routing.md">Routing guide →</a></p></div>
      <div class="card"><div class="tag">Area 4</div><h3>🧠 Learnings from daily tasks</h3><p>The team learns from your daily work — what you want, how you price a quotation, what you always check — and keeps a record. When you need it, it presents what it learned: your pricing, your way of working, ready when the next quotation comes in. A learning is a record, not fine-tuning: no model is retrained, and nothing is computed automatically from it.</p><p><a href="docs/learnings.md">Learnings guide →</a></p></div>
      <div class="card"><div class="tag">Area 5</div><h3>🔒 Privacy — data stays on your computer</h3><p>Your chats, files and memory live in plain files on your computer. Nothing is sent anywhere unless you choose an online provider. Before anything goes to an online model, the workroom redacts emails, IBANs, card numbers and your own private terms — and the redaction record stores only what kind of thing was hidden, never the values. Keys live in a local file, are never logged, and never reach the repo.</p><p><a href="docs/workroom.md">Workroom &amp; redaction →</a></p></div>
      <div class="card"><div class="tag">How we publish</div><h3>📚 Open guides, not locked papers</h3><p>LocalBotz publishes its work as open guides in the repo, with honest limits in every one. There are no academic papers to list — if that changes, they will be listed here, with links. <a href="publications.html">See the publications →</a></p></div>
    </div>

    <div class="open">
      <h3>Talking is the heart of it</h3>
      <p>Under all five areas sits one mission: everyone should be able to talk to their computer and get things done — no keyboard, no menus, no carefully worded prompt. <a href="culture.html">Read about the mission →</a></p>
    </div>
  </div>
""",
)

PAGES["publications.html"] = (
    "Publications — LocalBotz",
    "The real technical docs and guides from the LocalBotz repo — how each part works, its limits stated honestly, and how to run it yourself.",
    """
  <section class="hero">
    <div class="wrap">
      <h1>Publications</h1>
      <p class="tagline">LocalBotz publishes its work as open guides in the repo — not academic papers. These are the real documents, each one written when the feature shipped, with its limits stated honestly.</p>
    </div>
  </section>

  <div class="wrap">
    <h2 class="section">Models &amp; how it runs</h2>
    <div class="cards">
      <div class="card"><div class="tag">Guide</div><h3><a href="docs/model-reference.md">Model reference</a></h3><p>The model catalogue: 11 families, mapped to real API IDs. Marketing names are reference only and are never sent to an API.</p></div>
      <div class="card"><div class="tag">Guide</div><h3><a href="docs/how-it-runs.md">How LocalBotz runs</a></h3><p>Three ways: your computer, your subscriptions, or rent one from us — and what each one costs and needs.</p></div>
      <div class="card"><div class="tag">Guide</div><h3><a href="docs/routing.md">Smart routing</a></h3><p>Simple questions go to the free local model; hard work goes to the premium one. What it routes, and what it never overrides.</p></div>
      <div class="card"><div class="tag">Guide</div><h3><a href="docs/pricing.md">Pricing</a></h3><p>The premium price table, where the prices live, and how usage is metered to wallets.</p></div>
      <div class="card"><div class="tag">Guide</div><h3><a href="docs/connectors.md">Connectors</a></h3><p>25 popular connectors: what is really tested, and what a Connected result actually means.</p></div>
      <div class="card"><div class="tag">Guide</div><h3><a href="docs/languages.md">Languages</a></h3><p>199 countries and 186 languages — and the honest limits: a language being listed is not equal fluency in every model.</p></div>
    </div>

    <h2 class="section">Products</h2>
    <div class="cards">
      <div class="card"><div class="tag">Guide</div><h3><a href="docs/office.md">Office</a></h3><p>Run a team of agents locally: the boss, 143 roles, shared memory, the Auditor and the approval gate.</p></div>
      <div class="card"><div class="tag">Guide</div><h3><a href="docs/workroom.md">Workroom</a></h3><p>Documents with proof: the vault, keyword search, ask with receipts, and redaction before online models.</p></div>
      <div class="card"><div class="tag">Guide</div><h3><a href="docs/deal-workflows.md">Deal workflows</a></h3><p>One pipeline per department, multi-step chains with IF and Wait, and always-on monitors.</p></div>
      <div class="card"><div class="tag">Guide</div><h3><a href="docs/desktop.md">Desktop control</a></h3><p>Observe, act, verify: how bots use the desktop, and the permission gates that protect it.</p></div>
      <div class="card"><div class="tag">Guide</div><h3><a href="docs/talk.md">Talk &amp; Show-me-how</a></h3><p>Voice in, voice out, and visible steps on your screen — the plain-language rule, and what it is not.</p></div>
      <div class="card"><div class="tag">Guide</div><h3><a href="docs/live-voice.md">Live Voice</a></h3><p>Real-time conversation on Gemini Live: how it works, what it costs, and what is never saved.</p></div>
      <div class="card"><div class="tag">Guide</div><h3><a href="docs/leads.md">Leads</a></h3><p>Hunting for new clients: hot, warm and cold tiers, evidence for every lead, and what is never invented.</p></div>
      <div class="card"><div class="tag">Guide</div><h3><a href="docs/business-profile.md">Business profile</a></h3><p>Your company, once: the single profile every bot, office job and proposal draws on.</p></div>
      <div class="card"><div class="tag">Guide</div><h3><a href="docs/whatsapp-agent.md">WhatsApp sales agent</a></h3><p>Official Business API only, allowlist, draft first — nothing sent until you approve it.</p></div>
      <div class="card"><div class="tag">Guide</div><h3><a href="docs/marketing.md">Marketing publisher</a></h3><p>Write once, approve, then post or schedule — and which platforms really post today.</p></div>
      <div class="card"><div class="tag">Guide</div><h3><a href="docs/panels-whatsapp.md">Panels: WhatsApp &amp; Marketing</a></h3><p>Doing it all from the user and admin panels: hosted WhatsApp approval and per-platform credentials.</p></div>
      <div class="card"><div class="tag">Guide</div><h3><a href="docs/documents.md">Office documents</a></h3><p>Real Word, Excel and PowerPoint output from office jobs — with money kept as numbers, not text.</p></div>
    </div>

    <h2 class="section">Running it &amp; learning</h2>
    <div class="cards">
      <div class="card"><div class="tag">Guide</div><h3><a href="docs/routines.md">Routines</a></h3><p>Scheduled work that really runs — and the one catch-up rule when the app was closed.</p></div>
      <div class="card"><div class="tag">Guide</div><h3><a href="docs/learnings.md">Learnings</a></h3><p>What the team learns from daily tasks, and how it is presented when you need it.</p></div>
      <div class="card"><div class="tag">Guide</div><h3><a href="docs/hermes.md">Persistent agents</a></h3><p>Agents that work while you are away: tasks, memory, and the Telegram listener.</p></div>
      <div class="card"><div class="tag">Guide</div><h3><a href="docs/data-folder.md">Data folder</a></h3><p>Where your memory lives: C: drive or D: drive, chosen once at install, changeable later.</p></div>
      <div class="card"><div class="tag">Guide</div><h3><a href="docs/python-libraries.md">Python libraries</a></h3><p>Every library bundled in the install — pinned, packed as wheels, installed offline first.</p></div>
      <div class="card"><div class="tag">Guide</div><h3><a href="docs/awesome-llm-apps.md">Ideas we took, ideas we left</a></h3><p>What LocalBotz learned from public agent projects — and what it deliberately did not take.</p></div>
    </div>

    <div class="open">
      <h3>All of it is in the repo</h3>
      <p>Every guide above lives in <a href="https://github.com/webginet-sys/localbotz/tree/main/docs">the docs folder on GitHub</a>. If a feature has no guide yet, that is honest too — it is not listed here.</p>
    </div>
  </div>
""",
)

PAGES["open-source.html"] = (
    "Open-Source AI — LocalBotz",
    "LocalBotz is MIT licensed and built in the open. Read the code, run it from source, or send a pull request.",
    """
  <section class="hero">
    <div class="wrap">
      <h1>Open-Source AI</h1>
      <p class="tagline">Every line of LocalBotz is on GitHub, MIT licensed, and built in the open. Your office, your data, your code to read.</p>
      <a class="btn" href="https://github.com/webginet-sys/localbotz">Browse the code on GitHub</a>
    </div>
  </section>

  <div class="wrap">
    <h2 class="section">What's open</h2>
    <p class="lead">Everything. The app, the premium gateway, the installer, the docs — all of it.</p>
    <div class="cards">
      <div class="card"><div class="icon">💬</div><div class="tag">The app</div><h3>LocalBotz itself</h3><p>Python, FastAPI, plain HTML and JavaScript. No build step, no Electron. Bots, office teams, workrooms, deals, voice, WhatsApp, leads — all in one repo.</p></div>
      <div class="card"><div class="icon">☁️</div><div class="tag">The gateway</div><h3>VPS Premium gateway</h3><p>The server that rents premium models: registration, per-user tokens, metering, the admin panel and the user panel. In <code>server/</code>.</p></div>
      <div class="card"><div class="icon">🪟</div><div class="tag">The installer</div><h3>Windows installer &amp; wheels</h3><p>The Inno Setup script, the GitHub Actions build, and the script that packs every Python library as offline wheels.</p></div>
    </div>

    <h2 class="section">How to contribute</h2>
    <div class="steps">
      <div class="step"><span class="num">1</span><h3>Read the guide</h3><p>Start with the <a href="README.md">full guide</a> and <a href="https://github.com/webginet-sys/localbotz/blob/main/CONTRIBUTING.md">CONTRIBUTING.md</a> in the repo.</p></div>
      <div class="step"><span class="num">2</span><h3>Run it</h3><p>Download the ZIP, double-click install, and use it. The best contributions start from using it for real work.</p></div>
      <div class="step"><span class="num">3</span><h3>Pick something</h3><p>An open issue, a missing template, a translation, a guide that needs a clearer limit — all welcome.</p></div>
      <div class="step"><span class="num">4</span><h3>Send a pull request</h3><p>Fork the repo, build from scratch in LocalBotz's own code, and send a pull request. Ideas from other projects are welcome; copied code and names are not.</p></div>
    </div>

    <h2 class="section">The rules that stay in place</h2>
    <div class="features">
      <div class="feature"><span class="tick">✓</span><p><strong>MIT licensed.</strong> Copyright WEBGINET ENTERPRISE PRIVATE LIMITED. Use it, run it, build on it.</p></div>
      <div class="feature"><span class="tick">✓</span><p><strong>Our own code.</strong> Public projects are read for ideas and learned from — then LocalBotz is written from scratch, under its own name.</p></div>
      <div class="feature"><span class="tick">✓</span><p><strong>No secrets in the repo.</strong> Keys live in a local file, never in code, never in chat, never committed.</p></div>
      <div class="feature"><span class="tick">✓</span><p><strong>Honest limits.</strong> A contribution that claims more than it does is not merged. What is mock-tested says so.</p></div>
    </div>

    <div class="open">
      <h3>No open roles — but open code</h3>
      <p>There are no jobs at LocalBotz right now. Contributing on GitHub is how to work with us. <a href="jobs.html">See the Jobs page →</a></p>
      <p><a class="btn small" href="https://github.com/webginet-sys/localbotz">github.com/webginet-sys/localbotz</a></p>
    </div>
  </div>
""",
)

PAGES["about.html"] = (
    "About Us — LocalBotz",
    "LocalBotz is a personal AI assistant that runs on your own computer — a product of WEBGINET ENTERPRISE PRIVATE LIMITED.",
    """
  <section class="hero">
    <div class="wrap">
      <h1>About Us</h1>
      <p class="tagline">LocalBotz gives you a team of AI specialists that think as one — on your own computer, with your own models, and yours to run.</p>
    </div>
  </section>

  <div class="wrap">
    <h2 class="section">What LocalBotz is</h2>
    <p class="lead">A personal AI assistant that lives on your computer. Your local model, plus Claude, GPT, Gemini and DeepSeek — building and automating your work in one agent. Free, private by design, and open source.</p>
    <div class="features">
      <div class="feature"><span class="tick">✓</span><p><strong>Local first.</strong> The default model runs on your computer. Your chats, files and memory stay there unless you choose an online model.</p></div>
      <div class="feature"><span class="tick">✓</span><p><strong>A team, not a chatbot.</strong> Ask the team a question and it pools what every member knows: independent first takes, options backed by evidence, and a decision you can follow line by line.</p></div>
      <div class="feature"><span class="tick">✓</span><p><strong>For office, sales and marketing.</strong> Quotations, tenders, BOQs, deals, follow-ups, posts — the work companies actually do, in every sector.</p></div>
      <div class="feature"><span class="tick">✓</span><p><strong>AI suggests, humans decide.</strong> Every job is checked by an independent Auditor and stays a draft until you approve it. Nothing is sent until you say so.</p></div>
      <div class="feature"><span class="tick">✓</span><p><strong>Open source.</strong> MIT licensed, built in the open, on GitHub. Read the code, run it from source, or send a pull request.</p></div>
      <div class="feature"><span class="tick">✓</span><p><strong>Talking is the heart of it.</strong> Everyone should be able to talk to their computer and get things done — no prompting, no tutorials before you can start. <a href="culture.html">Our culture →</a></p></div>
    </div>

    <h2 class="section">Who makes it</h2>
    <div class="open">
      <h3>LocalBotz is a product of WEBGINET ENTERPRISE PRIVATE LIMITED</h3>
      <p>Built for the companies we work with — construction, MEP, electrical engineering, IT services and e-commerce — and for anyone who wants their AI team on their own computer.</p>
    </div>

    <h2 class="section">What LocalBotz is not</h2>
    <p class="lead">Saying no is part of the product. LocalBotz does not generate images or videos, does not fine-tune models, does not run game bots, and does not wrap other companies' terminal tools as its own.</p>
    <div class="cards">
      <div class="card"><div class="icon">💬</div><div class="tag">Start</div><h3><a href="chat.html">LocalBotz Chat</a></h3><p>Chat with bots on your own computer.</p></div>
      <div class="card"><div class="icon">🏢</div><div class="tag">Business</div><h3><a href="business.html">LocalBotz for Business</a></h3><p>Office teams, Cloud Office and premium models.</p></div>
      <div class="card"><div class="icon">💻</div><div class="tag">Open source</div><h3><a href="open-source.html">Open-Source AI</a></h3><p>MIT licensed, on GitHub, built in the open.</p></div>
    </div>
  </div>
""",
)

PAGES["culture.html"] = (
    "Culture — LocalBotz",
    "Our mission: everyone should be able to talk to their computer and get things done. No prompting, no tutorials before you can start.",
    """
  <section class="hero">
    <div class="wrap">
      <h1>Culture</h1>
      <p class="tagline">Computers were supposed to work for us. Somewhere along the way, we started working for them. LocalBotz exists to turn that back around.</p>
    </div>
  </section>

  <div class="wrap">
    <h2 class="section">Talking is the heart of this mission</h2>
    <p class="lead">AI was supposed to end the drudgery. Instead it added one more thing to learn: how to prompt it. That is backwards. Everyone should be able to talk to their computer and get things done — no keyboard, no menus, no carefully worded prompt. You just say what you want. They ask, and it shows them how — on their own screen, in their own context, in the moment. No prompting. No complicated steps. No tutorials before you can start.</p>
    <p class="lead">Many people are not perfect at typing, and they are used to talking on calls. So the future we are building toward is our own OS and our own mobile app with push-to-talk — so all our AI agents work from them and reply back in a voice, easy to talk to like employer and employee, and feeling like they are in the office. That is the plan for later. Today, Talk and Live Voice in the app are the start of it.</p>

    <h2 class="section">How we work</h2>
    <div class="features">
      <div class="feature"><span class="tick">✓</span><p><strong>Plain words win.</strong> If a feature needs a tutorial to use, it is not finished. The bot answers in short plain sentences, and shows each step on your screen.</p></div>
      <div class="feature"><span class="tick">✓</span><p><strong>AI suggests, humans decide.</strong> The Auditor checks, the draft waits, and nothing is sent until a person says so. A machine that acts without asking is not helpful — it is a liability.</p></div>
      <div class="feature"><span class="tick">✓</span><p><strong>Private by design.</strong> Your work stays on your computer unless you choose otherwise. A product that quietly uploads your business is not a product we would use ourselves.</p></div>
      <div class="feature"><span class="tick">✓</span><p><strong>Honest about limits.</strong> If something was only tested in mock mode, we say so. If a model cannot answer, the app says so instead of pretending. Trust is built by being wrong loudly, not by hiding it.</p></div>
      <div class="feature"><span class="tick">✓</span><p><strong>Build it, then write it down.</strong> A feature ships, is tested, and gets a guide with its limits. Work that is not written down does not exist yet.</p></div>
      <div class="feature"><span class="tick">✓</span><p><strong>Learn from everyone, copy no one.</strong> Public projects are read for ideas — then LocalBotz is written from scratch, under its own name, in its own words.</p></div>
    </div>

    <div class="open">
      <h3>Work with us the open way</h3>
      <p>There are no open roles right now — but the code is open, and so is the work. <a href="jobs.html">Jobs →</a> · <a href="open-source.html">Open-Source AI →</a></p>
    </div>
  </div>
""",
)

PAGES["press.html"] = (
    "Press — LocalBotz",
    "Press kit for LocalBotz: what it is, the logo, key facts, and how to reach us.",
    """
  <section class="hero">
    <div class="wrap">
      <h1>Press</h1>
      <p class="tagline">Everything a journalist needs to write about LocalBotz: what it is, the logo, and the facts — with nothing invented.</p>
    </div>
  </section>

  <div class="wrap">
    <h2 class="section">What LocalBotz is</h2>
    <p class="lead">LocalBotz is a personal AI assistant that runs on your own computer. Your local model (LM Studio with Qwen3.5) for free, plus Claude, GPT, Gemini and DeepSeek when you have internet — in one agent that builds, researches and automates office, sales and marketing work. It hires an AI office team with shared memory, answers document questions with proof, tracks deals, talks back in voice, and drafts WhatsApp replies that are never sent until a human approves them. Free, private by design, open source (MIT), for Windows, Mac and Linux. A product of WEBGINET ENTERPRISE PRIVATE LIMITED.</p>

    <h2 class="section">Logo</h2>
    <p class="lead">The LocalBotz logo — "localbotz" in teal outline, with a robot face in the "o". Use it as-is; don't redraw it, recolour it, or put another name on it.</p>
    <div class="cards">
      <div class="card" style="text-align:center;"><div class="icon"><img src="assets/logo.png" alt="LocalBotz logo" style="max-width:220px;height:auto;"></div><h3>Logo (PNG)</h3><p><a href="assets/logo.png">Download logo.png</a></p></div>
      <div class="card" style="text-align:center;"><div class="icon"><img src="assets/logo-animated.svg" alt="LocalBotz animated logo" style="max-width:220px;height:auto;"></div><h3>Animated logo (SVG)</h3><p><a href="assets/logo-animated.svg">Download logo-animated.svg</a></p></div>
      <div class="card"><div class="tag">Facts</div><h3>Key facts</h3><p>Free &amp; open source (MIT) · Windows, Mac, Linux · Local model free, premium pay-as-you-go · Product of WEBGINET ENTERPRISE PRIVATE LIMITED · <a href="https://github.com/webginet-sys/localbotz">github.com/webginet-sys/localbotz</a></p></div>
    </div>

    <h2 class="section">Press coverage</h2>
    <p class="lead">None to list yet. LocalBotz is new, and we don't invent coverage. If you write about LocalBotz, tell us on <a href="https://github.com/webginet-sys/localbotz/issues">GitHub Issues</a> and we will link your piece here.</p>

    <h2 class="section">Contact</h2>
    <div class="open">
      <h3>Talk to us on GitHub</h3>
      <p>Press questions, corrections, and interview requests: open an issue at <a href="https://github.com/webginet-sys/localbotz/issues">github.com/webginet-sys/localbotz/issues</a>. We don't publish a press email — GitHub is where the project lives and where we answer.</p>
    </div>
  </div>
""",
)

PAGES["customers.html"] = (
    "Customers — LocalBotz",
    "The sectors LocalBotz is built for: construction, MEP, electrical engineering, IT services, e-commerce — and every other office, sales and marketing team.",
    """
  <section class="hero">
    <div class="wrap">
      <h1>Customers</h1>
      <p class="tagline">LocalBotz is only for office, sales and marketing work — in every sector. These are the sectors it is built for, and what the office team does in each one.</p>
    </div>
  </section>

  <div class="wrap">
    <div class="cards">
      <div class="card"><div class="icon">🏗️</div><div class="tag">Sector</div><h3>Construction</h3><p>Tenders, BOQs, submittals and claims. The office team reads the documents, compares tenders, checks the BOQ against the drawings, and drafts the submission — with the Auditor checking every price and date before you approve it.</p></div>
      <div class="card"><div class="icon">🔧</div><div class="tag">Sector</div><h3>MEP</h3><p>Site surveys, HVAC and plumbing BOQs, coordination notes and handover packs. The team tracks the survey-to-submission flow and keeps the shared memory of what was agreed on site.</p></div>
      <div class="card"><div class="icon">⚡</div><div class="tag">Sector</div><h3>Electrical Engineering</h3><p>Design and BOQ, load schedules, submittals and testing records. The team checks the numbers, drafts the design narrative, and keeps the document trail in the workroom.</p></div>
      <div class="card"><div class="icon">💻</div><div class="tag">Sector</div><h3>IT Services</h3><p>Discovery, proposals, SOWs and SLAs. The team writes the proposal from the discovery notes, tracks the deal to Signed, and runs the onboarding routine when it lands.</p></div>
      <div class="card"><div class="icon">🛒</div><div class="tag">Sector</div><h3>E-commerce</h3><p>Briefs, listings, campaigns and rate cards. The team drafts the listings, hunts for new suppliers and customers, and posts — only after you approve it.</p></div>
      <div class="card"><div class="icon">🏠</div><div class="tag">Sector</div><h3>Real Estate</h3><p>Viewings, offers and closings. The team follows the viewing-to-offer flow, drafts the offer, and keeps the client record in one place.</p></div>
      <div class="card"><div class="icon">🏥</div><div class="tag">Sector</div><h3>Clinic &amp; Healthcare</h3><p>Consultations, quotations and bookings. The team drafts the quotation from the consultation, follows up, and books — with nothing sent until approved.</p></div>
      <div class="card"><div class="icon">🚚</div><div class="tag">Sector</div><h3>Logistics</h3><p>Quotations, bookings and deliveries. The team tracks the quote-to-delivery flow and chases what has gone quiet.</p></div>
      <div class="card"><div class="icon">🏭</div><div class="tag">Sector</div><h3>Manufacturing</h3><p>Quotations, samples and orders. The team follows the sample-to-order flow and keeps the specification documents in the workroom.</p></div>
      <div class="card"><div class="icon">🏨</div><div class="tag">Sector</div><h3>Hotel &amp; Hospitality</h3><p>Enquiries, quotations and bookings. The team answers enquiries from the rate card, drafts the quotation, and follows up.</p></div>
    </div>

    <div class="open">
      <h3>We don't publish client names</h3>
      <p>LocalBotz runs on its users' own computers, and their work is theirs. We don't list client names or testimonials we haven't got. If you use LocalBotz in your company and want to be listed here, tell us on <a href="https://github.com/webginet-sys/localbotz/issues">GitHub Issues</a>.</p>
      <p><a class="btn small" href="business.html">See LocalBotz for Business</a></p>
    </div>
  </div>
""",
)

PAGES["jobs.html"] = (
    "Jobs — LocalBotz",
    "No open roles right now. The best way to work with LocalBotz is to contribute on GitHub.",
    """
  <section class="hero">
    <div class="wrap">
      <h1>Jobs</h1>
      <p class="tagline">LocalBotz is a small open-source project. There are no open roles right now — but the work is open, and so is the code.</p>
    </div>
  </section>

  <div class="wrap">
    <h2 class="section">No open roles right now</h2>
    <p class="lead">We are not hiring at the moment. When that changes, the roles will be listed here — with real titles, real descriptions, and a real way to apply. Until then, the honest answer is: nothing open.</p>

    <h2 class="section">Work with us the open way</h2>
    <p class="lead">The best way to work with LocalBotz today is to contribute on GitHub — code, docs, bot templates, translations, or a guide that needs a clearer limit.</p>
    <div class="steps">
      <div class="step"><span class="num">1</span><h3>Use it</h3><p>Download LocalBotz and use it for real work. The best contributions start there.</p></div>
      <div class="step"><span class="num">2</span><h3>Find a gap</h3><p>An open issue, a missing template, a language that needs work — pick something real.</p></div>
      <div class="step"><span class="num">3</span><h3>Build it</h3><p>From scratch, in LocalBotz's own code. Ideas from other projects are welcome; copied code and names are not.</p></div>
      <div class="step"><span class="num">4</span><h3>Send it</h3><p>Open a pull request on GitHub. We review in the open, and say plainly what needs to change.</p></div>
    </div>

    <div class="open">
      <h3>Start here</h3>
      <p><a href="https://github.com/webginet-sys/localbotz">github.com/webginet-sys/localbotz</a> · <a href="https://github.com/webginet-sys/localbotz/blob/main/CONTRIBUTING.md">Contributing guide</a> · <a href="https://github.com/webginet-sys/localbotz/issues">Open issues</a></p>
      <p><a class="btn small" href="open-source.html">About Open-Source AI</a></p>
    </div>
  </div>
""",
)

PAGES["office.html"] = (
    "Office — your AI team — LocalBotz",
    "Hire an AI office team on your own computer: one boss, 143 roles, shared memory, and an independent Auditor who checks every job before you approve it.",
    """
  <section class="hero">
    <div class="wrap">
      <h1>Office — hire a team, give everyone a face</h1>
      <p class="tagline">An office of AI agents on your own computer. You hire the team, give each one a role, a face and a model, and hand them work in plain words. They plan it, do it, and report back.</p>
      <a class="btn" href="download.html">Build your office — get LocalBotz free</a>
    </div>
  </section>

  <div class="wrap">
    <h2 class="section">How a job runs</h2>
    <div class="steps">
      <div class="step"><span class="num">1</span><h3>You brief the boss</h3><p>The Office Manager is the only agent you brief. It plans the work and assigns it to the team.</p></div>
      <div class="step"><span class="num">2</span><h3>The team works in order</h3><p>Research, then write or build, then review — each member seeing the brief, the shared memory, and the work done before it.</p></div>
      <div class="step"><span class="num">3</span><h3>The Auditor checks it</h3><p>An independent Auditor who didn't do the work re-reads the brief and every step, and gives a verdict: pass, pass with fixes, or fail.</p></div>
      <div class="step"><span class="num">4</span><h3>You approve it</h3><p>The finished job is a draft until you approve it. Only then is it written into the office memory. AI suggests, humans decide.</p></div>
    </div>

    <h2 class="section">143 roles to hire from</h2>
    <p class="lead">The core team — Researcher, Writer, Developer, Analyst, Assistant, Sales, Finance, Legal, Recruiter, Teacher — plus 132 sector roles: every job a construction, MEP, electrical engineering, IT services or e-commerce company hires, from Construction Manager down to Steel Fixer, and 42 more office, sales and marketing functions. Physical and frontline jobs the AI cannot do were left out on purpose.</p>
    <div class="cards">
      <div class="card"><div class="tag">Memory</div><h3>One shared memory</h3><p>What one agent learns, the others can find. The whole office shares one memory you can read, search and back up. It survives sessions and grows with every day of work.</p></div>
      <div class="card"><div class="tag">Mailbox</div><h3>The blackboard</h3><p>Messages passed between the team: the boss assigns a part, the member reports back done. Visible on the Office page, on the record.</p></div>
      <div class="card"><div class="tag">Learning</div><h3>It learns your work</h3><p>Approved jobs teach the team — your pricing, your way of working — and the record is presented when the next quotation comes in.</p></div>
      <div class="card"><div class="tag">Any model</div><h3>Each member, its own model</h3><p>A team member is a normal bot. The Researcher can run on your computer, the Writer on your Claude key, the Analyst on premium from us.</p></div>
      <div class="card"><div class="tag">Documents</div><h3>Real documents out</h3><p>Office jobs export as real Word, Excel and PowerPoint files — with money kept as numbers, not text. <a href="docs/documents.md">Documents guide →</a></p></div>
      <div class="card"><div class="tag">Sectors</div><h3>Built for your sector</h3><p>Construction, MEP, electrical, IT services, e-commerce — and more. <a href="customers.html">Who it's built for →</a></p></div>
    </div>

    <h2 class="section">Also in LocalBotz</h2>
    <div class="cards">
      <div class="card"><div class="icon">🏢</div><div class="tag">Business</div><h3><a href="business.html">LocalBotz for Business</a></h3><p>Office teams, Cloud Office and premium models — run as a business.</p></div>
      <div class="card"><div class="icon">📁</div><div class="tag">Documents</div><h3><a href="workroom.html">Workroom</a></h3><p>The documents of one job, with proof behind every answer.</p></div>
      <div class="card"><div class="icon">💼</div><div class="tag">Sales</div><h3><a href="deals.html">Deals &amp; workflows</a></h3><p>Office jobs can start from a deal — and a won deal can start an office job.</p></div>
    </div>

    <div class="open">
      <h3>Your office, on your computer, for free</h3>
      <p><a class="btn small" href="download.html">Download LocalBotz</a></p>
    </div>

    <h2 class="section">Questions people ask</h2>
    <div class="faq">
      <details><summary>Does the team work in parallel?</summary><p>Not yet. The team runs one job at a time, in order — research, then write or build, then review. Parallel jobs are a planned next step.</p></details>
      <details><summary>Is there a 2D office floor with avatars?</summary><p>No. There is no 2D floor and no live terminal per agent. The office is the team, the memory, the blackboard and the job record — the parts that do the work.</p></details>
      <details><summary>What happens if the Auditor fails a job?</summary><p>The job stays a draft. You can ask for changes with a note saying what to fix, and run it again with the fix in the brief. Nothing failed is written into the office memory.</p></details>
    </div>
  </div>
""",
)

PAGES["workroom.html"] = (
    "Workroom — documents with proof — LocalBotz",
    "Your BOQs, tenders and contracts in a private vault. Ask questions and get answers with the exact document and passage behind them.",
    """
  <section class="hero">
    <div class="wrap">
      <h1>Workroom — documents with proof</h1>
      <p class="tagline">A vault of project documents for one job. Ask a question, get the answer — with the exact document and passage it came from. Never a made-up price, measurement or date.</p>
      <a class="btn" href="download.html">Get LocalBotz free</a>
    </div>
  </section>

  <div class="wrap">
    <h2 class="section">How it works</h2>
    <div class="steps">
      <div class="step"><span class="num">1</span><h3>Put the documents in</h3><p>BOQs, tenders, contracts, SOWs, SLAs, invoices, correspondence. Upload them, or add them from the workspace folder. They stay on your computer.</p></div>
      <div class="step"><span class="num">2</span><h3>Search them</h3><p>Keyword search over the documents, in passages. A big document set is searched as the work happens, not stuffed into one prompt.</p></div>
      <div class="step"><span class="num">3</span><h3>Ask with receipts</h3><p>The model only sees the matching passages, and is told to answer only from them. Every answer cites its document and passage.</p></div>
      <div class="step"><span class="num">4</span><h3>Hand it over</h3><p>Export one package — the workroom, all documents, every question and answer with its sources, the redaction log and the reviewer notes — for the next reviewer.</p></div>
    </div>

    <h2 class="section">Private by design</h2>
    <div class="features">
      <div class="feature"><span class="tick">✓</span><p><strong>Redaction before online models.</strong> Emails, IBANs, card numbers and your own private terms are replaced with placeholders before anything leaves the computer — and swapped back into the answer on your computer.</p></div>
      <div class="feature"><span class="tick">✓</span><p><strong>Local models skip redaction.</strong> LM Studio and Ollama never leave the computer, so redaction is off for them unless you ask for it.</p></div>
      <div class="feature"><span class="tick">✓</span><p><strong>The record keeps no secrets.</strong> The redaction log stores only what kind of thing was hidden and how many — never the values themselves.</p></div>
      <div class="feature"><span class="tick">✓</span><p><strong>Honest about what it cannot read.</strong> A file whose text cannot be extracted is still stored, and the workroom says so on the document instead of pretending it searched it.</p></div>
    </div>

    <h2 class="section">Built for document work</h2>
    <div class="cards">
      <div class="card"><div class="tag">Templates</div><h3>Five reviewer bots</h3><p>Document Reviewer, Tender Comparator, Contract Checker, BOQ Reviewer and Evidence Checker — each works only from the documents given, and never invents a figure.</p></div>
      <div class="card"><div class="tag">Formats</div><h3>What it reads</h3><p>.txt, .md, .csv, .json, .log, .tsv, .pdf and .docx — up to 20 MB each. A scanned-image PDF has no text to extract, and the workroom says so.</p></div>
      <div class="card"><div class="tag">Linked</div><h3>Works with your Office</h3><p>A workroom can be linked to an Office — the documents of one job, the team working on it. Or it can stand alone.</p></div>
    </div>

    <div class="open">
      <h3>Answers you can check</h3>
      <p>If the answer is not in the documents, the workroom says so — and says which document would settle it.</p>
      <p><a class="btn small" href="download.html">Download LocalBotz</a></p>
    </div>

    <h2 class="section">Questions people ask</h2>
    <div class="faq">
      <details><summary>Is the search semantic?</summary><p>Not yet — search is keyword-based, so a question in very different words from the document may miss. Use the document's own words (for example "retention" or "payment terms") for the best matches.</p></details>
      <details><summary>Does it upload my documents anywhere?</summary><p>No. Documents stay under the workroom folder on your computer. Only the matching passages are sent to a model — and to a local model, nothing leaves at all.</p></details>
    </div>
  </div>
""",
)

PAGES["deals.html"] = (
    "Deals & workflows — LocalBotz",
    "A deal pipeline for every department, workflows that act when a deal moves, and always-on monitors that chase what has gone quiet.",
    """
  <section class="hero">
    <div class="wrap">
      <h1>Deals &amp; workflows</h1>
      <p class="tagline">A small local CRM for sales work — and workflows that act when a deal moves. One flow per department, in that trade's own words.</p>
      <a class="btn" href="download.html">Get LocalBotz free</a>
    </div>
  </section>

  <div class="wrap">
    <h2 class="section">One flow per department</h2>
    <p class="lead">The same flow, with each trade's own stage names. Moving a deal to another department resets it to the new pipeline's first stage.</p>
    <table>
      <tr><th>Department</th><th>Pipeline</th></tr>
      <tr><td>General</td><td>New → Quoted → Negotiation → Won / Lost</td></tr>
      <tr><td>Construction</td><td>New lead → Tender received → BOQ prepared → Submitted → Negotiation → Awarded / Lost</td></tr>
      <tr><td>MEP</td><td>New lead → Site survey → BOQ prepared → Submitted → Negotiation → Awarded / Lost</td></tr>
      <tr><td>Electrical Engineering</td><td>New lead → Site survey → Design &amp; BOQ → Submitted → Negotiation → Awarded / Lost</td></tr>
      <tr><td>IT Services</td><td>New lead → Discovery → Proposal → Negotiation → Signed / Lost</td></tr>
      <tr><td>E-commerce</td><td>New lead → Brief → Proposal → Negotiation → Order won / Lost</td></tr>
      <tr><td>Real Estate</td><td>New lead → Viewing → Offer made → Negotiation → Closed / Lost</td></tr>
      <tr><td>Clinic &amp; Healthcare</td><td>New lead → Consultation → Quotation → Negotiation → Booked / Lost</td></tr>
      <tr><td>Logistics</td><td>New lead → Quotation → Negotiation → Booked → Delivered / Lost</td></tr>
      <tr><td>Manufacturing</td><td>New lead → Quotation → Sample → Negotiation → Order / Lost</td></tr>
      <tr><td>Hotel &amp; Hospitality</td><td>New lead → Enquiry → Quotation → Negotiation → Booked / Lost</td></tr>
    </table>

    <h2 class="section">Workflows that act when a deal moves</h2>
    <p class="lead">A rule is: when a deal moves to a stage, then a chain of steps, in order. Up to 10 steps: create a task, run an office job, write a draft, add a note, wait, or check a condition first.</p>
    <div class="cards">
      <div class="card"><div class="tag">Example</div><h3>Quoted — chase after 3 days</h3><p>Wait 3 days. If the deal is still Quoted, write a chase draft and add a note. If it moved on, the chain stops and writes nothing.</p></div>
      <div class="card"><div class="tag">Example</div><h3>Won — start the handover</h3><p>When a deal is won, a handover draft is written on the deal — or an office job starts, with the Auditor and the approval gate, like any office job.</p></div>
      <div class="card"><div class="tag">Example</div><h3>Lost — ask why</h3><p>When a deal is lost, a note asks for the reason. The reason stays on the timeline, where the next quotation can learn from it.</p></div>
    </div>

    <h2 class="section">Always-on monitors</h2>
    <p class="lead">Two watchers ship with the app: a deal Quoted for 3 days with no reply gets a chase draft and a task; a deal stuck in Negotiation for 7 days gets a nudge. Each fires once per deal — never a nag loop. Add your own, or pause them.</p>

    <h2 class="section">Nothing is sent by a workflow</h2>
    <div class="features">
      <div class="feature"><span class="tick">✓</span><p><strong>Drafts stay drafts.</strong> A workflow writes a draft on the deal. You send it yourself — by email, WhatsApp, or in person.</p></div>
      <div class="feature"><span class="tick">✓</span><p><strong>Office jobs go through approval.</strong> A workflow that starts an office job still waits for the Auditor and for you.</p></div>
      <div class="feature"><span class="tick">✓</span><p><strong>Every run is on the record.</strong> The Runs page shows what every chain did, step by step — and a finished run can be re-run.</p></div>
      <div class="feature"><span class="tick">✓</span><p><strong>Values stay numbers.</strong> A deal worth 4,850,000 is written as 4,850,000 — never as 4.85e+06.</p></div>
    </div>

    <div class="open">
      <h3>From lead to deal to done</h3>
      <p>A lead becomes a deal in one click, and the deal's timeline records that it came from a lead. <a href="leads.html">Leads &amp; Marketing →</a></p>
      <p><a class="btn small" href="download.html">Download LocalBotz</a></p>
    </div>
  </div>
""",
)

PAGES["voice.html"] = (
    "Talk & Live Voice — LocalBotz",
    "Talk to your computer in plain words — no prompting, no tutorials. The bot answers in voice and shows you how, step by step, on your screen.",
    """
  <section class="hero">
    <div class="wrap">
      <h1>Talk &amp; Live Voice</h1>
      <p class="tagline">Talking is the heart of this mission. Everyone should be able to talk to their computer and get things done — no keyboard, no menus, no carefully worded prompt.</p>
      <a class="btn" href="download.html">Get LocalBotz free</a>
    </div>
  </section>

  <div class="wrap">
    <h2 class="section">Talk — voice in, voice out</h2>
    <p class="lead">Tap the mic in chat and speak in plain words. The browser types what you said and sends it as a normal chat message. Turn the speaker on and the bot's replies are read out loud. No install, no keys, no audio recorded by LocalBotz.</p>
    <div class="features">
      <div class="feature"><span class="tick">✓</span><p><strong>Plain-language rule.</strong> When Talk is on, the bot replies in short plain sentences, no jargon, no menus. If something is unclear, it asks ONE simple question. It never asks you to write a better prompt.</p></div>
      <div class="feature"><span class="tick">✓</span><p><strong>Your language.</strong> Talk follows the language you picked — per bot, per chat, or for the whole app. 199 countries, 186 languages.</p></div>
      <div class="feature"><span class="tick">✓</span><p><strong>Honest when it can't.</strong> A browser with no speech recognition says so when you tap Talk, and never crashes the chat. Talk needs Chrome or Edge; the speaker works in most browsers.</p></div>
      <div class="feature"><span class="tick">✓</span><p><strong>Optional local transcription.</strong> Upload an audio file and LocalBotz transcribes it on your computer — only if you installed the optional transcriber. Without it, you get an honest "not installed" instead of a fake transcript.</p></div>
    </div>

    <h2 class="section">Show-me-how — visible steps on your screen</h2>
    <p class="lead">Flip the toggle and the bot still does the work — it just shows each step: what it is about to click or type and where, in plain words, with a picture after each desktop or browser step. Off, it does it quietly. On, it shows every step. Same bot, same work.</p>

    <h2 class="section">Live Voice — a real conversation</h2>
    <p class="lead">Talk is turn by turn. Live Voice is live: tap Start, talk in plain words, and the bot answers out loud while you speak. Interrupt it any time — just start talking — and it can do things on the desktop when you ask ("look at the BOQ", "click the total").</p>
    <div class="cards">
      <div class="card"><div class="tag">Live</div><h3>Interrupt any time</h3><p>Tap Interrupt, or just start talking while it speaks. Playback stops at once, the model is told to stop, and it waits for what you say next.</p></div>
      <div class="card"><div class="tag">Live</div><h3>It stops itself</h3><p>Say nothing for 2 minutes and the session stops, the mic closes, and the words — text only, no audio — are saved into the bot's chat history.</p></div>
      <div class="card"><div class="tag">Live</div><h3>Powered by Gemini Live</h3><p>Live voice runs on Google Gemini Live, so it needs internet and a Gemini key, and usage is billed to the key owner. Without a key the page says so honestly and refuses to start. The local model is text-only and cannot do live audio.</p></div>
    </div>

    <div class="open">
      <h3>Where this is going</h3>
      <p>The plan for later is our own OS and our own mobile app with push-to-talk — so all our AI agents work from them and reply back in a voice, easy to talk to like employer and employee, feeling like they are in the office. Today, Talk and Live Voice are the start of it. <a href="culture.html">Our culture →</a></p>
      <p><a class="btn small" href="download.html">Download LocalBotz</a></p>
    </div>

    <h2 class="section">Questions people ask</h2>
    <div class="faq">
      <details><summary>Is any audio saved?</summary><p>No. Audio is streamed and discarded. Only the text transcript is kept, in the bot's chat history. Every live session is logged as start/stop, duration, turns and interruptions — no audio.</p></details>
      <details><summary>Can live voice use the desktop?</summary><p>Yes — it can inspect, click and type, through the same permission gate as every other tool. Desktop control off, or a bot on Ask, blocks clicking and typing. Every live desktop action is logged.</p></details>
      <details><summary>How long can a live session run?</summary><p>Gemini caps a live audio session at about 15 minutes. The page ends the session when Gemini does, and the transcript is still saved.</p></details>
    </div>
  </div>
""",
)

PAGES["whatsapp.html"] = (
    "WhatsApp sales agent — LocalBotz",
    "Customers write to your WhatsApp Business number. LocalBotz drafts the reply — and nothing is sent until you approve it.",
    """
  <section class="hero">
    <div class="wrap">
      <h1>WhatsApp sales agent</h1>
      <p class="tagline">Customers message your WhatsApp Business number, LocalBotz drafts a reply, and nothing is sent until you approve it. The same rule as the Auditor: a draft is a draft until a human says send.</p>
      <a class="btn" href="download.html">Get LocalBotz free</a>
    </div>
  </section>

  <div class="wrap">
    <h2 class="section">How it works</h2>
    <div class="steps">
      <div class="step"><span class="num">1</span><h3>Customer writes in</h3><p>A customer writes to your WhatsApp Business number. Meta calls LocalBotz, and the call is checked — the signature must match, or the message is rejected.</p></div>
      <div class="step"><span class="num">2</span><h3>Only approved senders</h3><p>Only senders on your allowlist get a reply. Anyone else is logged as blocked and gets nothing. A do-not-reply blocklist always wins.</p></div>
      <div class="step"><span class="num">3</span><h3>A draft, not a send</h3><p>Your WhatsApp bot drafts a reply, using your business profile and the rule never to invent a price, a date or a delivery. The draft waits in your inbox.</p></div>
      <div class="step"><span class="num">4</span><h3>You approve it</h3><p>Approve it in the panel and only then is it sent, through the official WhatsApp Business API. A failed send is reported honestly, and the message stays waiting.</p></div>
    </div>

    <h2 class="section">Two ways to run it</h2>
    <div class="cards">
      <div class="card"><div class="tag">Hosted</div><h3>On the server</h3><p>The gateway-hosted agent lives on the VPS. Set it up in the user panel — connect form, webhook URL, inbox with Approve &amp; send — and it works even when your computer is off. The admin panel sees every workspace's status.</p></div>
      <div class="card"><div class="tag">Local</div><h3>On your computer</h3><p>The LocalBotz app on your computer has its own WhatsApp agent too, on the Messaging channels page. Same rule: draft first, approve, then send.</p></div>
      <div class="card"><div class="tag">Setup</div><h3>What you need</h3><p>A WhatsApp Business number and a Meta app: access token, phone number ID, verify token, app secret. They live in the Secure store, masked everywhere, never logged.</p></div>
    </div>

    <div class="open">
      <h3>Official API only</h3>
      <p>There is no QR-code pairing: logging in by scanning a code breaks WhatsApp's rules and can get the number banned, so LocalBotz does not do it. Text messages only — voice notes, images and status updates are ignored.</p>
      <p><a class="btn small" href="download.html">Download LocalBotz</a></p>
    </div>
  </div>
""",
)

PAGES["leads.html"] = (
    "Leads & Marketing — LocalBotz",
    "Hunt for new clients in your area, turn leads into deals, and publish posts — drafted, approved, then sent.",
    """
  <section class="hero">
    <div class="wrap">
      <h1>Leads &amp; Marketing</h1>
      <p class="tagline">Find new clients, turn them into deals, and tell the world — with a human approving every step.</p>
      <a class="btn" href="download.html">Get LocalBotz free</a>
    </div>
  </section>

  <div class="wrap">
    <h2 class="section">Lead hunting</h2>
    <p class="lead">Give it an area and a sector — "Doha, Qatar" and "Construction" — and it searches public directories and search results for businesses there, then sorts them into three tiers.</p>
    <div class="cards">
      <div class="card"><div class="icon">🔥</div><div class="tag">Hot</div><h3>Ready to buy</h3><p>They have a website and a way to reach them, and they look ready: a new project, a tender, an expansion.</p></div>
      <div class="card"><div class="icon">🟡</div><div class="tag">Warm</div><h3>Reachable, unclear need</h3><p>They can be reached, but it is not clear yet whether they need anything.</p></div>
      <div class="card"><div class="icon">❄️</div><div class="tag">Cold</div><h3>No usable contact</h3><p>No usable contact was found. The lead still shows what the search did find, so you can judge it yourself.</p></div>
    </div>
    <div class="features">
      <div class="feature"><span class="tick">✓</span><p><strong>Evidence for every lead.</strong> Every lead shows why it got its tier, and a link to the source page. A phone number or a website is only shown when the page actually showed it. LocalBotz never invents contact details.</p></div>
      <div class="feature"><span class="tick">✓</span><p><strong>Lead → deal in one click.</strong> A lead becomes a deal in the General pipeline, at New, with the business as the client. The timeline records that it came from a lead.</p></div>
      <div class="feature"><span class="tick">✓</span><p><strong>Proposal packs.</strong> A lead gets a real .docx proposal and an .xlsx tracker row, using your business profile — company name, services, tone.</p></div>
      <div class="feature"><span class="tick">✓</span><p><strong>Public sources only.</strong> Hunting does not scrape Google Maps — that breaks Google's terms — and it only reads pages a browser can open.</p></div>
    </div>

    <h2 class="section">Marketing publisher</h2>
    <p class="lead">Write a post once, pick the platforms it goes to, and it is only posted after you approve it. Nothing is ever posted without approval.</p>
    <div class="steps">
      <div class="step"><span class="num">1</span><h3>Draft</h3><p>Write the post, tick the platforms — Telegram, Facebook, LinkedIn, X, Instagram — and save it as a draft.</p></div>
      <div class="step"><span class="num">2</span><h3>Approve</h3><p>A draft becomes approved. An unapproved post cannot be posted or scheduled.</p></div>
      <div class="step"><span class="num">3</span><h3>Post or schedule</h3><p>An approved post goes out now, or at a time you pick. Scheduled posts go out while the app is open.</p></div>
      <div class="step"><span class="num">✓</span><h3>Honest results</h3><p>Each post shows, per platform, what actually happened. Telegram posts for real today; the other platforms report honestly that live posting is not wired up yet — never shown as posted when it was not.</p></div>
    </div>

    <div class="open">
      <h3>Growth with a human in the loop</h3>
      <p>Leads are hunted, deals are tracked, posts are drafted — and a person approves before anything reaches a customer. <a href="deals.html">Deals &amp; workflows →</a></p>
      <p><a class="btn small" href="download.html">Download LocalBotz</a></p>
    </div>
  </div>
""",
)

PAGES["pricing.html"] = (
    "Pricing — LocalBotz",
    "Your computer is free, your subscriptions cost whatever your provider charges, and premium models are pay-as-you-go, per 1M tokens.",
    """
  <section class="hero">
    <div class="wrap">
      <h1>Pricing</h1>
      <p class="tagline">Three ways to run. Only one of them costs anything through LocalBotz itself — and that one is pay-as-you-go, nothing else.</p>
    </div>
  </section>

  <div class="wrap">
    <h2 class="section">Three ways to run</h2>
    <div class="cards">
      <div class="card" style="text-align:left;"><div class="tag">Free</div><h3>🖥️ Your computer — $0</h3><p>Local model (LM Studio / Qwen3.5) on your own computer. Unlimited, no bill, nothing leaves your computer.</p></div>
      <div class="card" style="text-align:left;"><div class="tag">You pay your provider</div><h3>🔑 Your subscriptions</h3><p>Claude, ChatGPT, Grok, Gemini, DeepSeek and more — you pay whatever your provider charges for your own API key. LocalBotz adds nothing on top.</p></div>
      <div class="card" style="text-align:left;"><div class="tag">Premium, metered</div><h3>☁️ Rent one from us</h3><p>Claude Sonnet, GPT, Gemini and more from our server — register on the VPS and use them, metered to your wallet. Prices below, per 1M tokens.</p></div>
    </div>

    <h2 class="section">Rent-from-us prices (USD per 1M tokens)</h2>
    <p class="lead">These are the defaults, the providers' public list prices. The server owner can change any of them in the admin panel, and the new price applies to later requests. Grok, Kimi and GLM are starting prices — confirm them in the provider's own docs before relying on them.</p>
    <table>
      <tr><th>Model</th><th class="num">Input / 1M</th><th class="num">Output / 1M</th></tr>
      <tr><td>Claude Sonnet 4.5</td><td class="num">$3.00</td><td class="num">$15.00</td></tr>
      <tr><td>Claude Opus 4.1</td><td class="num">$15.00</td><td class="num">$75.00</td></tr>
      <tr><td>GPT-4o</td><td class="num">$2.50</td><td class="num">$10.00</td></tr>
      <tr><td>GPT-4o mini</td><td class="num">$0.15</td><td class="num">$0.60</td></tr>
      <tr><td>Gemini 2.5 Flash</td><td class="num">$0.30</td><td class="num">$2.50</td></tr>
      <tr><td>Gemini 2.5 Pro</td><td class="num">$1.25</td><td class="num">$10.00</td></tr>
      <tr><td>DeepSeek Chat</td><td class="num">$0.27</td><td class="num">$1.10</td></tr>
      <tr><td>DeepSeek Reasoner</td><td class="num">$0.55</td><td class="num">$2.19</td></tr>
      <tr><td>Grok-4</td><td class="num">$3.00</td><td class="num">$15.00</td></tr>
      <tr><td>Kimi K2</td><td class="num">$0.60</td><td class="num">$2.50</td></tr>
      <tr><td>GLM-4.5</td><td class="num">$0.60</td><td class="num">$2.20</td></tr>
    </table>
    <p class="fine">Local models are always free and never appear in the price list. The public price list is also at the gateway — no sign-in needed to see it before you register.</p>

    <h2 class="section">Cloud Office</h2>
    <p class="lead">Rent a computer from us — 2 vCPU, 8 GB RAM, 100 GB disk — and your office lives there. The monthly price is set by the server owner in the admin panel. Until it is set, the panel shows that the price is not set yet. We don't invent a price here.</p>

    <h2 class="section">Wallets &amp; metering</h2>
    <p class="lead">Every premium request is metered: tokens in and out, and cost, per workspace and per model. Workspaces have wallets, with a low-balance warning. Local and bring-your-own-key usage costs the host $0 and is tracked only.</p>

    <div class="open">
      <h3>Start free</h3>
      <p>Your computer costs nothing. Download LocalBotz, and add premium only if and when you need it.</p>
      <p><a class="btn small" href="download.html">Download LocalBotz</a></p>
    </div>
  </div>
""",
)

PAGES["help.html"] = (
    "Help & guides — LocalBotz",
    "Every LocalBotz guide in one place: getting started, each product, and running the server.",
    """
  <section class="hero">
    <div class="wrap">
      <h1>Help &amp; guides</h1>
      <p class="tagline">Every guide, in one place. Each one says what the feature does — and what it does not do yet.</p>
    </div>
  </section>

  <div class="wrap">
    <h2 class="section">Getting started</h2>
    <div class="cards">
      <div class="card"><div class="tag">Start</div><h3><a href="download.html">Download</a></h3><p>Windows or Mac, step by step, no terminal jargon. Including what to do when Windows Smart App Control blocks the file.</p></div>
      <div class="card"><div class="tag">Start</div><h3><a href="README.md">Full guide (README)</a></h3><p>The whole app in one document: install, bots, settings, providers, office, and everything else.</p></div>
      <div class="card"><div class="tag">Start</div><h3><a href="docs/how-it-runs.md">How LocalBotz runs</a></h3><p>Your computer, your subscriptions, or rent one from us — and what each one needs.</p></div>
      <div class="card"><div class="tag">Start</div><h3><a href="docs/data-folder.md">Data folder</a></h3><p>Where your memory lives: C: drive or D: drive, chosen once at install, changeable later.</p></div>
      <div class="card"><div class="tag">Start</div><h3><a href="docs/python-libraries.md">Python libraries</a></h3><p>Every library bundled in the install — pinned, packed as wheels, installed offline first.</p></div>
      <div class="card"><div class="tag">Start</div><h3><a href="docs/model-reference.md">Model reference</a></h3><p>The model catalogue, mapped to real API IDs. Marketing names are reference only.</p></div>
    </div>

    <h2 class="section">Products</h2>
    <div class="cards">
      <div class="card"><div class="tag">Guide</div><h3><a href="docs/office.md">Office</a></h3><p>Run a team of agents locally.</p></div>
      <div class="card"><div class="tag">Guide</div><h3><a href="docs/workroom.md">Workroom</a></h3><p>Documents with proof.</p></div>
      <div class="card"><div class="tag">Guide</div><h3><a href="docs/deal-workflows.md">Deal workflows</a></h3><p>Pipelines, chains, monitors.</p></div>
      <div class="card"><div class="tag">Guide</div><h3><a href="docs/desktop.md">Desktop control</a></h3><p>Observe, act, verify.</p></div>
      <div class="card"><div class="tag">Guide</div><h3><a href="docs/talk.md">Talk &amp; Show-me-how</a></h3><p>Voice in, voice out, visible steps.</p></div>
      <div class="card"><div class="tag">Guide</div><h3><a href="docs/live-voice.md">Live Voice</a></h3><p>Real-time conversation.</p></div>
      <div class="card"><div class="tag">Guide</div><h3><a href="docs/leads.md">Leads</a></h3><p>Hunting for new clients.</p></div>
      <div class="card"><div class="tag">Guide</div><h3><a href="docs/business-profile.md">Business profile</a></h3><p>Your company, once.</p></div>
      <div class="card"><div class="tag">Guide</div><h3><a href="docs/whatsapp-agent.md">WhatsApp agent</a></h3><p>Draft first, approve, then send.</p></div>
      <div class="card"><div class="tag">Guide</div><h3><a href="docs/marketing.md">Marketing publisher</a></h3><p>Draft, approve, post or schedule.</p></div>
      <div class="card"><div class="tag">Guide</div><h3><a href="docs/panels-whatsapp.md">Panels: WhatsApp &amp; Marketing</a></h3><p>Doing it all from the panels.</p></div>
      <div class="card"><div class="tag">Guide</div><h3><a href="docs/documents.md">Office documents</a></h3><p>Real Word, Excel and PowerPoint output.</p></div>
    </div>

    <h2 class="section">Running it &amp; learning</h2>
    <div class="cards">
      <div class="card"><div class="tag">Guide</div><h3><a href="docs/routines.md">Routines</a></h3><p>Scheduled work that really runs.</p></div>
      <div class="card"><div class="tag">Guide</div><h3><a href="docs/learnings.md">Learnings</a></h3><p>What the team learns from daily tasks.</p></div>
      <div class="card"><div class="tag">Guide</div><h3><a href="docs/hermes.md">Persistent agents</a></h3><p>Agents that work while you are away.</p></div>
      <div class="card"><div class="tag">Guide</div><h3><a href="docs/routing.md">Smart routing</a></h3><p>Simple questions, free answers.</p></div>
      <div class="card"><div class="tag">Guide</div><h3><a href="docs/connectors.md">Connectors</a></h3><p>25 popular connectors, really tested.</p></div>
      <div class="card"><div class="tag">Guide</div><h3><a href="docs/languages.md">Languages</a></h3><p>199 countries, 186 languages.</p></div>
      <div class="card"><div class="tag">Guide</div><h3><a href="docs/pricing.md">Pricing</a></h3><p>The price table and metering.</p></div>
      <div class="card"><div class="tag">Guide</div><h3><a href="docs/awesome-llm-apps.md">Ideas we took, ideas we left</a></h3><p>What LocalBotz learned from public projects.</p></div>
    </div>

    <div class="open">
      <h3>Still stuck?</h3>
      <p>Report a problem or ask a question on <a href="https://github.com/webginet-sys/localbotz/issues">GitHub Issues</a>. That is where the project answers.</p>
    </div>
  </div>
""",
)

# ---------------------------------------------------------------------------
# Surgery on the two existing pages + docs mirror
# ---------------------------------------------------------------------------

OLD_NAV = (
    '    <nav>\n'
    '      <a href="https://github.com/webginet-sys/localbotz">GitHub</a>\n'
    '      <a href="README.md">Guide</a>\n'
    '      <a href="#download">Download</a>\n'
    '    </nav>'
)

# Extra CSS appended to landing.html / download.html so the shared
# header dropdowns and footer columns work with their existing styles.
CHROME_CSS = """
  /* Shared site chrome (scripts/build_site.py) */
  header.top .wrap { flex-wrap: wrap; }
  header.top nav { display: flex; flex-wrap: wrap; gap: 4px 16px; margin-left: auto; }
  header.top nav a { margin-left: 0; }
  .nav-group { position: relative; display: inline-block; }
  .nav-drop { display: none; position: absolute; top: 100%; left: 0; background: #fff; border: 1px solid var(--line); border-radius: 12px; padding: 8px 0; min-width: 230px; box-shadow: 0 8px 24px rgba(15,42,61,.12); z-index: 10; }
  .nav-drop a { display: block; padding: 8px 16px; margin-left: 0; }
  .nav-group:hover .nav-drop, .nav-group:focus-within .nav-drop { display: block; }
  footer { text-align: left; }
  .foot-cols { display: grid; grid-template-columns: repeat(4, 1fr); gap: 28px; }
  @media (max-width: 900px) { .foot-cols { grid-template-columns: 1fr 1fr; } }
  @media (max-width: 600px) { .foot-cols { grid-template-columns: 1fr; } }
  .foot-col h4 { margin: 0 0 10px; color: var(--navy); font-size: 15px; }
  .foot-col a { display: block; margin: 6px 0; text-decoration: none; }
  .foot-bottom { text-align: center; margin-top: 28px; }
  .foot-bottom p { margin: 6px 0; }
  @media (max-width: 700px) {
    header.top nav { flex-direction: column; align-items: flex-start; gap: 2px; }
    .nav-group { display: block; }
    .nav-drop { position: static; display: block; box-shadow: none; border: none; padding: 0 0 0 14px; min-width: 0; }
  }
"""

PRODUCTS_STRIP = """
    <h2 class="section">Products — everything LocalBotz does</h2>
    <p class="lead">One app on your computer, built for office, sales and marketing work. Start with a chat, or start with a team.</p>
    <div class="cards">
      <div class="card"><div class="icon">💬</div><div class="tag">Products</div><h3><a href="chat.html">LocalBotz Chat</a></h3><p>Chat with bots on your own computer — your local model, plus Claude, GPT, Gemini and DeepSeek.</p></div>
      <div class="card"><div class="icon">🏢</div><div class="tag">Products</div><h3><a href="business.html">LocalBotz for Business</a></h3><p>Office AI teams, a rented computer in the cloud, and premium models on tap.</p></div>
      <div class="card"><div class="icon">📁</div><div class="tag">Products</div><h3><a href="workroom.html">Workroom</a></h3><p>Documents with proof — every answer shows its source.</p></div>
      <div class="card"><div class="icon">💼</div><div class="tag">Products</div><h3><a href="deals.html">Deals &amp; workflows</a></h3><p>One pipeline per department, workflows that act when a deal moves.</p></div>
      <div class="card"><div class="icon">🎙️</div><div class="tag">Products</div><h3><a href="voice.html">Talk &amp; Live Voice</a></h3><p>Talk to your computer in plain words — no prompting, no tutorials.</p></div>
      <div class="card"><div class="icon">💬</div><div class="tag">Products</div><h3><a href="whatsapp.html">WhatsApp sales agent</a></h3><p>Customers write in, LocalBotz drafts — nothing sent until you approve it.</p></div>
    </div>
    <p style="text-align:center;"><a class="btn small" href="products.html">See all products</a></p>

"""


def replace_footer(text, where):
    new, n = re.subn(r"<footer>.*?</footer>", lambda _: footer(""), text,
                     count=1, flags=re.S)
    if n != 1:
        raise SystemExit("footer block not found in " + where)
    return new


def build_landing():
    p = ROOT / "landing.html"
    text = p.read_text(encoding="utf-8")
    nav = re.search(r"<nav>.*?</nav>", header(""), re.S).group(0)
    text = must_replace(text, OLD_NAV, nav, "landing.html")
    text = replace_footer(text, "landing.html")
    # Shared chrome CSS.
    text = must_replace(text, "</style>", CHROME_CSS + "</style>", "landing.html")
    # Products strip before "How LocalBotz runs".
    text = must_replace(
        text, '    <h2 class="section">How LocalBotz runs</h2>',
        PRODUCTS_STRIP + '    <h2 class="section">How LocalBotz runs</h2>',
        "landing.html")
    # Factual fix: the template count grew since v0.2.0.
    text = must_replace(
        text, "15 templates, your own instructions",
        "47 templates, your own instructions", "landing.html")
    # Link the pricing section to the full price list.
    text = must_replace(
        text,
        "Renting our computer is pay-as-you-go, per 1M tokens. Local models are always free.</p>",
        "Renting our computer is pay-as-you-go, per 1M tokens. Local models are always free. "
        '<a href="pricing.html">See the full price list →</a></p>',
        "landing.html")
    p.write_text(text, encoding="utf-8")
    return text


def build_download():
    p = ROOT / "download.html"
    text = p.read_text(encoding="utf-8")
    # Teal palette (was the old pink/purple). Variable names stay the same.
    palette = [
        ("--pink: #ec2a8a;", "--pink: #0d9488;"),
        ("--purple: #7c3aed;", "--purple: #0f766e;"),
        ("--violet: #9333ea;", "--violet: #73bbbb;"),
        ("--ink: #1f1b2e;", "--ink: #1f2a30;"),
        ("--muted: #5b5566;", "--muted: #5b6b72;"),
        ("--line: #e9e4f2;", "--line: #dfe9e7;"),
        ("--soft: #faf7ff;", "--soft: #f6fbfa;"),
        ("#fdf2f8 0%, #f5f3ff 100%", "#eafaf7 0%, #ffffff 100%"),
        ("background: #f3f0fa;", "background: #f6fbfa;"),
        ("--green: #15803d;\n  }", "--green: #15803d;\n    --navy: #0f2a3d;\n  }"),
    ]
    for old, new in palette:
        text = must_replace(text, old, new, "download.html")
    nav = re.search(r"<nav>.*?</nav>", header(""), re.S).group(0)
    text = must_replace(text, OLD_NAV, nav, "download.html")
    text = replace_footer(text, "download.html")
    text = must_replace(text, "</style>", CHROME_CSS + "</style>", "download.html")
    text = must_replace(
        text, "localbotz in pink to purple with a robot face",
        "localbotz in teal with a robot face in the o", "download.html")
    # The installer now exists (built by GitHub Actions) — it is unsigned
    # until the company certificate is in place.
    text = must_replace(
        text,
        "A proper signed installer (<code>LocalBotz-Setup.exe</code>) is coming, so Windows will trust it from day one — this unblock step is only needed until then.",
        "A proper installer (<code>LocalBotz-Setup.exe</code>) is built automatically on GitHub — see the "
        '<a href="https://github.com/webginet-sys/localbotz/actions/workflows/build-windows-installer.yml">latest installer build</a>. '
        "It is unsigned until the company certificate is in place, so the unblock step above is still needed for now.",
        "download.html")
    p.write_text(text, encoding="utf-8")
    # docs/download.html is a path-adjusted mirror (same content, docs/
    # paths), like docs/index.html — NOT a byte copy: a byte copy would
    # leave every nav link in docs/download.html pointing at
    # docs/<page>.html, which does not exist.
    mirror = text
    for old, new in DOCS_PATH_PAIRS:
        mirror = mirror.replace(old, new)
    (ROOT / "docs" / "download.html").write_text(mirror, encoding="utf-8")
    return text


# Root-relative links in a root page -> the same link from docs/.
DOCS_PATH_PAIRS = [
    ('href="products.html"', 'href="../products.html"'),
    ('href="chat.html"', 'href="../chat.html"'),
    ('href="business.html"', 'href="../business.html"'),
    ('href="research.html"', 'href="../research.html"'),
    ('href="research-areas.html"', 'href="../research-areas.html"'),
    ('href="publications.html"', 'href="../publications.html"'),
    ('href="open-source.html"', 'href="../open-source.html"'),
    ('href="about.html"', 'href="../about.html"'),
    ('href="culture.html"', 'href="../culture.html"'),
    ('href="press.html"', 'href="../press.html"'),
    ('href="customers.html"', 'href="../customers.html"'),
    ('href="jobs.html"', 'href="../jobs.html"'),
    ('href="office.html"', 'href="../office.html"'),
    ('href="workroom.html"', 'href="../workroom.html"'),
    ('href="deals.html"', 'href="../deals.html"'),
    ('href="voice.html"', 'href="../voice.html"'),
    ('href="whatsapp.html"', 'href="../whatsapp.html"'),
    ('href="leads.html"', 'href="../leads.html"'),
    ('href="pricing.html"', 'href="../pricing.html"'),
    ('href="help.html"', 'href="../help.html"'),
    ('href="landing.html"', 'href="../landing.html"'),
    ('href="download.html"', 'href="../download.html"'),
    ('href="README.md"', 'href="../README.md"'),
    ('href="DOWNLOAD.md"', 'href="../DOWNLOAD.md"'),
    ('href="docs/', 'href="../docs/'),
    ('src="assets/', 'src="../assets/'),
]


def build_docs_index(landing_text):
    # Mirror of landing.html for the docs/ folder: same page, docs/ paths.
    text = landing_text
    for old, new in DOCS_PATH_PAIRS:
        text = text.replace(old, new)
    (ROOT / "docs" / "index.html").write_text(text, encoding="utf-8")


def build():
    for name, (title, desc, body) in sorted(PAGES.items()):
        (ROOT / name).write_text(page(title, desc, body), encoding="utf-8")
    landing_text = build_landing()
    build_download()
    build_docs_index(landing_text)
    print("wrote %d pages + landing.html + download.html + docs/download.html + docs/index.html"
          % len(PAGES))


if __name__ == "__main__":
    build()
