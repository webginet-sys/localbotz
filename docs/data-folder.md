# Data folder — where LocalBotz keeps its memory

Everything LocalBotz remembers lives in **one folder**:

- your bots (`bots.json`)
- memory, learnings and chat history (`memory/`, `chats/`)
- offices, workrooms and their documents (`offices/`, `workrooms/`, `documents/`)
- leads, deals, routines, posts and settings

By default that folder is `data/` inside the LocalBotz folder (on the C:
drive, for a normal install). As the office grows — documents, BOQs,
workroom files — that folder grows, and the C: drive (the system drive)
fills up. So you can move it.

## Choose at install time

- **Windows installer (`LocalBotz-Setup.exe`)** — the installer asks:
  *In the LocalBotz folder (C: drive)*, *On the D: drive —
  `D:\LocalBotzData`*, or *Decide later*.
- **`install.bat` / `start.bat`** — on first install it asks the same:
  press `1` for the C: drive folder, `2` for `D:\LocalBotzData`, `3` to
  type another folder.
- **First-run wizard** — step 1 asks where the data should live.
- **Mac/Linux (`start.sh`)** — on first run it asks for a folder path
  (there are no C:/D: drives there); press Enter to keep the app folder.

The choice is saved as `LOCALBOTZ_DATA_DIR` in `.env` (gitignored, never
in the repo), so it survives restarts. If no choice is saved, the app
folder is used.

## Change it later

**Settings → General → Data folder**: see the current folder and how big
it is, type a new folder (or use the *Use D: drive* / *Use the LocalBotz
folder* buttons), tick *Move my data* to copy everything there, save,
then restart LocalBotz (close the window, double-click `start.bat`).

- With *Move my data* ticked, your data is **copied** to the new folder;
  the old folder stays on disk as a backup. Delete it by hand when you
  are sure the new one works.
- Without it, the new folder starts empty and your old data stays where
  it was.
- The app must be restarted to use the new folder — the setting only
  takes effect on the next start.

API (for the curious): `GET /api/settings/data-folder` returns the
current path, size in bytes, the default path, and the drives that exist
on this computer. `POST /api/settings/data-folder` with
`{"path": "D:\\LocalBotzData", "move": true}` validates the folder
(full path only, drive must exist, folder must be writable) and saves it.

## What does NOT move

- The app itself stays in the install folder.
- Python, LM Studio and the Qwen3.5 model stay where the installer put
  them (LM Studio keeps the model in its own folder). The data folder
  is about *your* memory and documents, not the model.

## Honest limits

- If the drive you pick is a USB stick or a network drive that is not
  plugged in when LocalBotz starts, the app cannot use it — pick a
  folder on a drive that is always there.
- Moving the data while the app is running only copies files; the app
  keeps using the old folder until you restart it.
