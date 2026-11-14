"""Download every Python library LocalBotz needs, as Windows wheels,
into vendor/wheels/ — the bundled pack shipped inside LocalBotz-Setup.exe.

Run:  python scripts/fetch_wheels.py [--dir vendor/wheels]

Requires pip + internet. Downloads for Windows (win_amd64, CPython 3.12),
the same Python the installer sets up, so the installer can put the
libraries on the user's computer without downloading them from PyPI.
The full dependency closure is downloaded (pip resolves it), so an
offline install from the pack works with `pip install --no-index`.

The wheels are NOT committed to the repo (they are large binaries):
.gitignore excludes vendor/. The Windows installer workflow runs this
script before staging, so LocalBotz-Setup.exe carries the pack.
To refresh the pack after changing a requirements file, run this again.

Two quirks, both handled here:
1. pip evaluates environment markers (e.g. `pywinauto; sys_platform ==
   'win32'`) against THIS machine, not the --platform target, so a
   Linux build machine would skip the Windows-only libraries. The
   markers are stripped before downloading (the download is already
   targeted at Windows).
2. PyAutoGUI ships NO wheel at all, only an sdist — and pip refuses
   sdists when --platform is set. So it is built into a wheel here
   (`pip wheel`, pure Python, builds anywhere) and its runtime deps
   are fetched explicitly. If another library ever ships no wheel,
   add it to SDIST_ONLY and its deps to SDIST_DEPS.

Deliberately NOT bundled: faster-whisper (used only by the optional
/api/talk/transcribe endpoint when installed; it is large and Talk
works through the browser's speech recognition without it).
"""

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
REQUIREMENTS = [
    BASE_DIR / "requirements.txt",
    BASE_DIR / "requirements-browser.txt",
    BASE_DIR / "requirements-desktop.txt",
    BASE_DIR / "requirements-live.txt",
]

# Libraries with no wheel on PyPI (sdist only) — built into wheels here.
# The whole PyAutoGUI family ships sdist-only; all of them are pure
# Python, so `pip wheel` builds them on any machine.
SDIST_ONLY = {
    "pyautogui": "0.9.54",
    "pygetwindow": "0.0.9",
    "pyrect": "0.2.0",
    "pyscreeze": "1.0.1",
    "mouseinfo": "0.1.3",
    "pytweening": "1.2.0",
}
# Runtime deps of the sdist-only libraries that DO have wheels, fetched
# explicitly because the main loop skips the sdist-only packages (so pip
# never sees their deps). Pillow (pyscreeze's dep) is already in the pack
# via python-pptx. python3-Xlib is deliberately left out: Linux-only.
SDIST_DEPS = ["pymsgbox", "pyperclip"]

PLATFORM_ARGS = [
    "--platform", "win_amd64",
    "--python-version", "3.12",
    "--implementation", "cp",
    "--abi", "cp312",
]


def _run(cmd):
    print("[fetch_wheels]", " ".join(cmd[3:]))
    subprocess.run(cmd, check=True)


def _strip_markers(req: Path, tmp: Path) -> Path:
    """Copy a requirements file without environment markers and without
    the sdist-only packages (handled separately below)."""
    lines = []
    for line in req.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name = line.split(";")[0].strip().split("=")[0].split(">")[0].split("<")[0].strip()
        if name.lower() in SDIST_ONLY:
            continue
        lines.append(line.split(";")[0].strip())
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return tmp


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dir", default=str(BASE_DIR / "vendor" / "wheels"))
    args = ap.parse_args()
    out = Path(args.dir)
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        for req in REQUIREMENTS:
            print(f"[fetch_wheels] {req.name} -> {out}")
            stripped = _strip_markers(req, tmpdir / req.name)
            _run([sys.executable, "-m", "pip", "download",
                  *PLATFORM_ARGS, "--only-binary", ":all:",
                  "-r", str(stripped), "-d", str(out)])
        # Sdist-only libraries: build a universal wheel from the sdist
        # (pure Python, builds on any machine), then fetch their deps.
        for name, version in SDIST_ONLY.items():
            print(f"[fetch_wheels] {name} {version} (sdist only) -> build wheel")
            _run([sys.executable, "-m", "pip", "wheel",
                  f"{name}=={version}", "--no-deps", "-w", str(out)])
        if SDIST_DEPS:
            print(f"[fetch_wheels] deps of sdist-only libs: {', '.join(SDIST_DEPS)}")
            _run([sys.executable, "-m", "pip", "download",
                  *PLATFORM_ARGS, "--only-binary", ":all:",
                  *SDIST_DEPS, "-d", str(out)])
        # Build tools, so an sdist that ever sneaks into the pack can
        # still be built offline on the user's computer.
        print("[fetch_wheels] setuptools + wheel (offline sdist builds)")
        _run([sys.executable, "-m", "pip", "download",
              *PLATFORM_ARGS, "--only-binary", ":all:",
              "setuptools", "wheel", "-d", str(out)])
    # python3-Xlib is a Linux-only dep of PyAutoGUI/mouseinfo. pip
    # evaluates its marker against THIS machine, so a Linux build
    # machine pulls it into the Windows pack — drop it: Windows pip
    # would skip it at install time anyway, it is just dead weight.
    for xlib in out.glob("python_xlib-*.whl"):
        print(f"[fetch_wheels] dropping Linux-only {xlib.name}")
        xlib.unlink()
    wheels = sorted(p.name for p in out.glob("*.whl"))
    total = sum(p.stat().st_size for p in out.glob("*.whl"))
    (out / "MANIFEST.txt").write_text(
        "LocalBotz bundled Python libraries (Windows, CPython 3.12)\n"
        f"{len(wheels)} wheels, {total / 1048576:.1f} MB\n\n" + "\n".join(wheels) + "\n",
        encoding="utf-8",
    )
    print(f"[fetch_wheels] {len(wheels)} wheels, {total / 1048576:.1f} MB in {out}")


if __name__ == "__main__":
    main()
