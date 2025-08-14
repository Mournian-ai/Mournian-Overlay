# TwitchOverlay (OBS/Twitch overlay + EventSub + Tray App)

A self-contained Twitch overlay server for OBS:
- **Overlay** with rotating “latest follow/sub/bits” and a **Twitch-like chat box** (emotes supported).
- **EventSub (WebSocket)** listener for `channel.follow`, `channel.subscribe`, and `channel.cheer`.
- **Pretty stats dashboard** with dark/light mode and live connection/subscription status.
- **Admin UI** to configure credentials, appearance, and OAuth.
- **Windows tray app** (exe) with Open Admin/Stats, Restart EventSub/Server, and Quit.
- **Persistent data** stored per-user (e.g., `%APPDATA%\TwitchOverlay\store.json`) when packaged.

---

## Contents

- `app.py` — FastAPI app + tray menu + server control.
- `twitch_ws.py` — EventSub worker (connects to `wss://eventsub.wss.twitch.tv/ws`).
- `overlay.py` — HTML/JS overlay page (for OBS).
- `stats_view.py` — HTML/JS live stats page.
- `models.py` — Pydantic models + **store location logic** (per-user app data when packaged).
- `tmi.min.js` — Local copy of tmi.js (served via `/static`).

---

## Requirements

- Python 3.11+ recommended
- Windows (packaged EXE target). Source works on macOS/Linux, but EventSub scopes & packaging steps are written for Windows.
- Pip packages:
  ```bash
  pip install fastapi uvicorn[standard] httpx websockets python-dotenv pydantic pystray pillow
