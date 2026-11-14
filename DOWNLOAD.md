# Download LocalBotz

![LocalBotz](assets/logo.png)

**Your own personal AI agent, on your own computer.**

LocalBotz is free, private by design, and runs on your own computer. You do not need to know how to use a terminal. Just download it, double-click one file, and it opens in your browser.

**Get it here:** https://github.com/webginet-sys/localbotz

On that page, click the green **Code** button, then **Download ZIP**.

- Direct ZIP link: https://github.com/webginet-sys/localbotz/archive/refs/heads/main.zip
- Ready-made installers, when available: https://github.com/webginet-sys/localbotz/releases

---

## What you need first

- **A computer** — Windows 10 or 11, or a Mac with macOS 13 or newer.
- **Internet for the first setup** — to download LocalBotz and your AI model. After that, it works offline.
- **LM Studio + Qwen3.5 (free)** — this is the AI brain that runs on your computer. See below.

---

## First, get your AI model (5 minutes, once)

You only do this once.

1. **Download LM Studio** — go to https://lmstudio.ai/ and download it for Windows or Mac, then install it like any normal app.
2. **Download the Qwen3.5 model** — open LM Studio, search for **Qwen3.5**, and download it.
3. **Start the local server** — in LM Studio, open the **Developer** tab (the `</>` icon on the left), load Qwen3.5, and press **Start Server**. Leave LM Studio open while you use LocalBotz.

Tip: if LM Studio shows a longer name for the model, for example `qwen/qwen3.5-…`, that is fine — just copy that exact name into LocalBotz later if it asks for it. The normal name is `qwen3.5`.

---

## On Windows — 5 steps

1. **Click “Get LocalBotz for Windows”** on the download page, or go to https://github.com/webginet-sys/localbotz. Click the green **Code** button, then **Download ZIP**.
2. **Open the downloaded ZIP.** Find it in your Downloads folder, open it, and click **Extract All**. Choose a folder you will remember, for example your Desktop.
3. **Double-click `start.bat`.** It is in the folder you just extracted. A small black window will appear — that is normal, it is setting LocalBotz up for you. The first time takes a few minutes.
4. **Wait while it sets itself up.** It installs what it needs and then starts LocalBotz. Please leave the black window open while you use LocalBotz.
5. **LocalBotz opens in your browser.** Your browser should open to `localhost:8000` — that is LocalBotz running on your own computer. If it does not open by itself, type `localhost:8000` into your browser's address bar.

To stop LocalBotz, just close the black window. To start it again, double-click `start.bat` again.

## On Mac — 5 steps

Works on Apple Silicon (M1 / M2 / M3 / M4) and Intel Macs — the same download works for both, you do not need to choose.

1. **Click “Get LocalBotz for Mac”** on the download page, or go to https://github.com/webginet-sys/localbotz. Click the green **Code** button, then **Download ZIP**.
2. **Open the ZIP.** Find it in your Downloads folder and double-click it. It will open into a folder called `localbotz`.
3. **Double-click `start.command`.** It is in the `localbotz` folder. If your Mac says it cannot be opened, right-click it (or hold Control and click), choose **Open**, then click **Open** again. A small window will appear — that is normal.
4. **Wait while it sets itself up.** It installs what it needs and then starts LocalBotz. The first time takes a few minutes. Please leave that window open while you use LocalBotz.
5. **LocalBotz opens in your browser.** Your browser should open to `localhost:8000` — that is LocalBotz running on your own computer. If it does not open by itself, type `localhost:8000` into your browser's address bar.

To stop LocalBotz, just close the Terminal window. To start it again, double-click `start.command` again.

---

## Questions people ask

**Is it free?**
Yes. LocalBotz itself is free, and the Qwen3.5 model in LM Studio is free. You only pay if you choose to use paid online models (like Claude or GPT) — and then only to that provider, if you add your own key.

**Is my data private?**
Yes. With the local model, your chats, files and browsing stay on your own computer. Nothing is sent to a cloud service unless you choose an online provider yourself.

**Do I need to type commands?**
No. You only need to download a ZIP, extract it, and double-click one file. There is a terminal version for developers in the README, but you do not need it.

**What if it doesn't open?**
First, check that the small setup window is still open — LocalBotz stops when you close it. Then open your browser and type `localhost:8000` in the address bar. If you see an error about Python, install Python 3.11 or newer from https://www.python.org/downloads/ (on Windows, tick “Add python.exe to PATH” during install), then double-click the start file again.

**What if LM Studio isn't running?**
LocalBotz will tell you it cannot reach LM Studio. Open LM Studio, make sure Qwen3.5 is loaded, press **Start Server** in the Developer tab, and try again. LocalBotz will reconnect automatically.

**Can I use Claude, GPT or Gemini instead?**
Yes, when you have internet. In LocalBotz, go to Settings → Connectors and add the key for the provider you want. You can use whichever model is available — local or online — and switch per bot.

---

## For developers

If you do use a terminal, the quick version is:

```bash
git clone https://github.com/webginet-sys/localbotz.git
cd localbotz
./start.sh        # Mac / Linux
start.bat         # Windows
```

See [README.md](README.md) for the full guide, and [download.html](download.html) for the same instructions as a web page.

Support: https://github.com/webginet-sys/localbotz/issues
