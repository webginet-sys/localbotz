# LocalBotz install progress screen.
#
# A small friendly window that shows the install step by step while
# start.bat runs - Python, LM Studio, the Qwen3.5 model download,
# libraries, browser automation, then LocalBotz starting - instead of
# only a black terminal window. It reads two files in the app folder:
#   install_progress.txt - one line per step: "STEP 2", then "DONE"
#   install.log          - the last lines, shown as the detail box
# If either file is missing it just shows step 1. Closing this window
# never stops the install; the install carries on in the terminal.
# Standard library only (tkinter ships with python.org Python).
# Run with pythonw so no extra console window appears.

import os
import sys
import time

STEPS = [
    (1, "Python 3.12 ready", "Checking that Python is installed"),
    (2, "LM Studio installed", "Installing LM Studio"),
    (3, "Qwen3.5 model downloaded", "Downloading the Qwen3.5 model, about 6 GB, and starting its server"),
    (4, "Python libraries installed", "Installing everything LocalBotz needs"),
    (5, "Browser automation ready", "Installing Playwright and Chromium"),
    (6, "LocalBotz starting", "Starting LocalBotz and opening your browser"),
]

PROGRESS_FILE = "install_progress.txt"
LOG_FILE = "install.log"
POLL_MS = 500
DONE_CLOSE_MS = 4000
LOG_TAIL_LINES = 6


def app_dir():
    # This file lives in installer/, the app folder is its parent.
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(here)


def read_status(folder):
    """Read the progress file and the log tail. Pure function, no GUI."""
    current = 1
    done = False
    try:
        with open(os.path.join(folder, PROGRESS_FILE), encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if line == "DONE":
                    done = True
                elif line.startswith("STEP "):
                    try:
                        n = int(line.split(" ", 1)[1])
                    except ValueError:
                        continue
                    if 1 <= n <= len(STEPS):
                        current = n
    except OSError:
        pass
    log_lines = []
    try:
        with open(os.path.join(folder, LOG_FILE), encoding="utf-8", errors="replace") as f:
            lines = [ln.rstrip("\n") for ln in f]
        log_lines = [ln for ln in lines if ln.strip()][-LOG_TAIL_LINES:]
    except OSError:
        pass
    if done:
        current = len(STEPS)
    return {"current": current, "done": done, "log_lines": log_lines}


def step_state(step_no, status):
    """done / current / waiting for one step number."""
    if status["done"] or step_no < status["current"]:
        return "done"
    if step_no == status["current"]:
        return "current"
    return "waiting"


def format_elapsed(started_at, now=None):
    seconds = int((now if now is not None else time.time()) - started_at)
    minutes, seconds = divmod(seconds, 60)
    if minutes:
        return "%d min %02d sec" % (minutes, seconds)
    return "%d sec" % seconds


def main():
    try:
        import tkinter as tk
        from tkinter import ttk
    except Exception:
        return 0
    folder = app_dir()
    started_at = time.time()
    try:
        root = tk.Tk()
    except Exception:
        return 0
    root.title("LocalBotz - Installing...")
    root.geometry("540x600")
    root.resizable(False, False)
    teal = "#4d9d9d"
    dark = "#1f3a3a"

    header = tk.Frame(root, bg=teal)
    header.pack(fill="x")
    tk.Label(header, text="LocalBotz", font=("Segoe UI", 22, "bold"),
             fg="white", bg=teal).pack(anchor="w", padx=20, pady=(14, 0))
    tk.Label(header, text="Installing LocalBotz on your computer",
             font=("Segoe UI", 11), fg="white", bg=teal).pack(anchor="w", padx=20)
    tk.Label(header, text="Please keep this window open. The first install downloads everything it needs.",
             font=("Segoe UI", 9), fg="white", bg=teal, wraplength=500,
             justify="left").pack(anchor="w", padx=20, pady=(0, 12))

    body = tk.Frame(root)
    body.pack(fill="both", expand=True, padx=20, pady=14)

    status_label = tk.Label(body, text="Starting...", font=("Segoe UI", 11, "bold"),
                            fg=dark, anchor="w")
    status_label.pack(fill="x")
    elapsed_label = tk.Label(body, text="", font=("Segoe UI", 9), fg="#666666", anchor="w")
    elapsed_label.pack(fill="x", pady=(0, 8))

    overall = ttk.Progressbar(body, maximum=len(STEPS), length=480)
    overall.pack(fill="x", pady=(0, 4))
    current_bar = ttk.Progressbar(body, mode="indeterminate", length=480)
    current_bar.pack(fill="x", pady=(0, 12))
    current_bar.start(15)

    step_rows = []
    for number, label, detail in STEPS:
        row = tk.Frame(body)
        row.pack(fill="x", pady=3)
        icon = tk.Label(row, text="\u25cb", font=("Segoe UI", 13), width=3, fg="#999999")
        icon.pack(side="left")
        texts = tk.Frame(row)
        texts.pack(side="left", fill="x")
        name = tk.Label(texts, text=label, font=("Segoe UI", 10, "bold"),
                        fg="#333333", anchor="w")
        name.pack(anchor="w")
        sub = tk.Label(texts, text=detail, font=("Segoe UI", 9), fg="#777777", anchor="w")
        sub.pack(anchor="w")
        step_rows.append((icon, name, sub))

    tk.Label(body, text="What is happening now:", font=("Segoe UI", 10, "bold"),
             fg=dark, anchor="w").pack(fill="x", pady=(10, 2))
    log_box = tk.Text(body, height=7, font=("Consolas", 9), fg="#333333",
                      bg="#f4f4f4", wrap="none")
    log_box.pack(fill="x")
    log_box.config(state="disabled")

    footer = tk.Label(body, text="Closing this window does not stop the install - it carries on in the black window.",
                      font=("Segoe UI", 8), fg="#888888", wraplength=480, justify="left")
    footer.pack(fill="x", pady=(10, 0))

    closed = {"at": None}

    def poll():
        status = read_status(folder)
        done_count = sum(1 for n, _l, _d in STEPS if step_state(n, status) == "done")
        overall["value"] = done_count
        for (number, _label, _detail), (icon, name, sub) in zip(STEPS, step_rows):
            state = step_state(number, status)
            if state == "done":
                icon.config(text="\u2713", fg="#2e9e5b")
                name.config(fg="#2e9e5b")
            elif state == "current":
                icon.config(text="\u25b6", fg=teal)
                name.config(fg=dark)
            else:
                icon.config(text="\u25cb", fg="#999999")
                name.config(fg="#999999")
        if status["done"]:
            status_label.config(text="Done - opening LocalBotz...", fg="#2e9e5b")
            current_bar.stop()
            current_bar["value"] = 100
            if closed["at"] is None:
                closed["at"] = time.time()
            elif time.time() - closed["at"] > DONE_CLOSE_MS / 1000:
                root.destroy()
                return
        else:
            current_label = STEPS[status["current"] - 1][1]
            status_label.config(text="Step %d of %d: %s" % (status["current"], len(STEPS), current_label), fg=dark)
        elapsed_label.config(text="Time so far: %s" % format_elapsed(started_at))
        text = "\n".join(status["log_lines"]) if status["log_lines"] else "Waiting for the install to report..."
        log_box.config(state="normal")
        log_box.delete("1.0", "end")
        log_box.insert("end", text)
        log_box.config(state="disabled")
        root.after(POLL_MS, poll)

    poll()
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
