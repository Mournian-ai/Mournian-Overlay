# TwitchOverlay (OBS/Twitch overlay + EventSub + Tray App)

A self-contained Twitch overlay server for OBS:

* **Overlay** with rotating “latest follow/sub/bits” and a **Twitch-like chat box** (emotes supported).
* **EventSub (WebSocket)** listener for `channel.follow`, `channel.subscribe`, and `channel.cheer`.
* **Pretty stats dashboard** with dark/light mode and live connection/subscription status.
* **Admin UI** to configure credentials, appearance, and OAuth.
* **Windows tray app** (exe) with Open Admin/Stats, Restart EventSub/Server, and Quit.
* **Persistent data** stored per-user (e.g., `%APPDATA%\TwitchOverlay\store.json`) when packaged.

---

## 📂 Contents

* `app.py` — FastAPI app + tray menu + server control.
* `twitch_ws.py` — EventSub worker (connects to `wss://eventsub.wss.twitch.tv/ws`).
* `overlay.py` — HTML/JS overlay page (for OBS).
* `stats_view.py` — HTML/JS live stats page.
* `models.py` — Pydantic models + **store location logic** (per-user app data when packaged).
* `tmi.min.js` — Local copy of tmi.js (served via `/static`).

---

## 🛠 Requirements

* Python **3.11+** recommended
* Windows (packaged EXE target). Source works on macOS/Linux, but EventSub scopes & packaging steps are written for Windows.
* Pip packages:

  ```bash
  pip install fastapi uvicorn[standard] httpx websockets python-dotenv pydantic pystray pillow
  ```

---

## 🚀 Quick Start (from source)

### 1️⃣ Clone & install dependencies

```bash
git clone https://github.com/Mournian-ai/Mournian-Overlay.git
cd Mournian-Overlay
python -m venv venv
```

**Windows PowerShell:**

```powershell
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt  # if you have one
# OR manually:
pip install fastapi uvicorn[standard] httpx websockets python-dotenv pydantic pystray pillow
```

---

### 2️⃣ Run the app

```bash
python app.py
```

Your browser should open: [http://localhost:8000/admin](http://localhost:8000/admin)

---

### 3️⃣ Configure in Admin

* **Client ID** / **Client Secret** from your [Twitch Developer Console](https://dev.twitch.tv/console/apps).
* **Redirect URI**: `http://localhost:8000/oauth/callback` *(must match exactly in Twitch console)*.
* **Broadcaster Login**: your channel name (lowercase).
* Click **Connect with Twitch (OAuth)** and approve scopes:

  * `moderator:read:followers`
  * `channel:read:subscriptions`
  * `bits:read`

---

### 4️⃣ Use in OBS

* Add a **Browser Source**:

  * **URL**: `http://localhost:8000/overlay`
  * Or override channel: `http://localhost:8000/overlay?channel=yourname`
* Set size to match your canvas (overlay positions are absolute).

---

### 5️⃣ Stats Dashboard

* Visit: [http://localhost:8000/stats](http://localhost:8000/stats)
  Live status, session ID, subscription status, recent events, and total bits.

---

## 📦 Build a Windows EXE (PyInstaller)

> No personal tokens/settings are shipped — the packaged app stores its data in `%APPDATA%\TwitchOverlay\store.json`.

**PowerShell:**

```powershell
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
pyinstaller app.py --onefile --noconsole --name "TwitchOverlay" `
  --add-data "tmi.min.js;." `
  --hidden-import websockets --hidden-import anyio --hidden-import h11
```

The exe will be at `dist\TwitchOverlay.exe`.
Double-click → tray icon appears → right-click for menu.

---

## 📁 Data & Logs

* **From source**: stored in `./store/store.json` (relative to repo).
* **From exe**:

  * Windows: `%APPDATA%\TwitchOverlay\store.json`
  * macOS: `~/Library/Application Support/TwitchOverlay/store.json`
  * Linux: `~/.local/share/TwitchOverlay/store.json`

---

## ⚠ Troubleshooting

* **403 when creating EventSub subscriptions**

  * Re-run OAuth; ensure correct scopes.
  * OAuth user must be broadcaster (or mod for channel.follow v2).
* **EXE “does nothing”**

  * It runs in background — open `http://localhost:8000/admin`.
  * For logs, build without `--noconsole` or enable file logging.
* **Quit from tray doesn’t fully exit**

  * This repo uses clean shutdown (`server.should_exit = True`).
    If processes linger, add a timed hard-exit fallback.

---

## 🔒 Security

* Tokens are stored locally in `store.json`.
  **Never commit this file** to GitHub.
* `.gitignore` excludes it by default.

---

## 📜 License

MIT (or your choice).

---

## 👌 Credits

* [FastAPI](https://fastapi.tiangolo.com/)
* [Uvicorn](https://www.uvicorn.org/)
* [tmi.js](https://tmijs.com/)
* [pystray](https://github.com/moses-palmer/pystray)
* [Pillow](https://python-pillow.org/)
* Twitch EventSub docs: [https://dev.twitch.tv/docs/eventsub/](https://dev.twitch.tv/docs/eventsub/)
