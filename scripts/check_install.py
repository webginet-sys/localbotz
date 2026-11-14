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
    hard_fail = [n for n in failed if "LM Studio" not in n]
    if hard_fail:
        print("RESULT: FAIL — missing: " + ", ".join(hard_fail))
        return 1
    print("RESULT: OK — LocalBotz is fully installed, including browser automation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
