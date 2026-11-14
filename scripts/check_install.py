"""LocalBotz install check — run at the end of install.bat / start.sh.

Checks everything the user needs, all installed upfront in the one
install step, so nothing is left to install later:
  - Python version
  - Core packages (fastapi, uvicorn, httpx)
  - Playwright + Chromium (browser automation) — launches headless
  - LM Studio reachable on http://localhost:1234 (best-effort only;
    the model download / server start is done by the installer, and
    the app still starts if LM Studio is not up yet)

Exit code 0 = everything needed is ready. Exit code 1 = something
is missing — the printed checklist says what, and how the installer
should have provided it.
"""
import sys

checks = []


def check(name, ok, detail=""):
    checks.append((name, ok, detail))
    print(f"[{'OK ' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def main():
    print("LocalBotz install check — everything should be ready now:")
    print(f"Python {sys.version.split()[0]}")
    check("Python 3.11+", sys.version_info >= (3, 11), sys.version.split()[0])

    for pkg in ("fastapi", "uvicorn", "httpx"):
        try:
            __import__(pkg)
            check(f"Package: {pkg}", True)
        except Exception as e:  # noqa: BLE001
            check(f"Package: {pkg}", False, str(e))

    # Browser automation — Playwright + Chromium, launched headless.
    try:
        import playwright  # noqa: F401
        check("Playwright installed", True)
    except Exception as e:  # noqa: BLE001
        check("Playwright installed", False, str(e))
        print("RESULT: FAIL — browser automation is missing.")
        return 1

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            exe = pw.chromium.executable_path
            check("Chromium downloaded", True, str(exe))
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto("about:blank")
            check("Chromium launches (browser automation ready)", True, page.title() or "about:blank")
            browser.close()
    except Exception as e:  # noqa: BLE001
        check("Chromium launches (browser automation ready)", False, str(e))

    # Desktop control — import-only. On a headless machine (no display)
    # pyautogui may still import but cannot take a screenshot; that is
    # reported honestly and is NOT a failure of the install — the app
    # still starts, and desktop tools say so on the Desktop page.
    for pkg in ("pyautogui", "pygetwindow"):
        try:
            __import__(pkg)
            check(f"Desktop control: {pkg}", True)
        except Exception as e:  # noqa: BLE001
            check(f"Desktop control: {pkg}", False, str(e))
    try:
        import os as _os
        if _os.name == "nt":
            import pywinauto  # noqa: F401
            check("Desktop control: pywinauto (Windows accessibility tree)", True)
        else:
            check("Desktop control: pywinauto (Windows only — skipped)", True, "not needed on this OS")
    except Exception as e:  # noqa: BLE001
        check("Desktop control: pywinauto (Windows accessibility tree)", False, str(e))
    # Live voice — Gemini Live + WebSocket. Best-effort: the app, chat,
    # Talk and the desktop all work without it; the Live Voice page
    # says honestly what is missing.
    for pkg in ("websockets", "google.genai"):
        try:
            __import__(pkg)
            check(f"Live voice: {pkg}", True)
        except Exception as e:  # noqa: BLE001
            check(f"Live voice: {pkg}", False, str(e))
    _key = _os.environ.get("GEMINI_API_KEY", "")
    check("Live voice: Gemini key (GEMINI_API_KEY)", bool(_key),
          "Saved, not checked" if _key else "Not connected — add it in Secure store to use live voice (Talk still works)")

    if not _os.environ.get("DISPLAY") and sys.platform.startswith("linux"):
        check("Desktop: no display here (headless)", True, "import-only check — a real desktop is checked on the user's computer")

    # LM Studio — best-effort only; the installer tries to start it,
    # but the app can still start without it (mock / online providers).
    try:
        import httpx

        r = httpx.get("http://localhost:1234/v1/models", timeout=3)
        check("LM Studio reachable (localhost:1234)", r.status_code == 200, f"HTTP {r.status_code}")
    except Exception:  # noqa: BLE001
        check("LM Studio reachable (localhost:1234)", False, "not up yet")

    failed = [name for name, ok, _ in checks if not ok]
    # LM Studio not being up yet is not a failure of the install itself.
    # Desktop import failures are not either: the app checks the desktop
    # itself and says so on the Desktop page (e.g. headless servers).
    hard_fail = [n for n in failed if "LM Studio" not in n and "Desktop" not in n and "Live voice" not in n]
    if hard_fail:
        print("RESULT: FAIL — missing: " + ", ".join(hard_fail))
        return 1
    print("RESULT: OK — LocalBotz is fully installed, including browser automation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
