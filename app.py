# app.py — with system tray (Open Admin / Open Stats / Restart EventSub / Restart Server / Quit)

import asyncio
import json
import secrets
import sys
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, Any, Set

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

# --- our modules
from models import Latest, Store, STORE_DIR
from overlay import build_overlay_html
from stats_view import build_stats_html
from twitch_ws import (
    connect_eventsub_ws,
    ensure_tokens_ready,
    register_broadcaster,
    register_store,
    get_worker_status,
)

# ---------------- In-memory app state ----------------
store = Store.load()
latest = store.latest
ws_clients: Set[WebSocket] = set()
eventsub_task: asyncio.Task | None = None

_pending_oauth_states: Set[str] = set()

# flags controlled by tray
_restart_server_flag = threading.Event()
_quit_flag = threading.Event()
_current_server = None  # type: ignore

# ---------------- Lifespan (startup/shutdown) ----------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global eventsub_task
    register_store(store)
    register_broadcaster(lambda msg: broadcast(msg))
    await ensure_tokens_ready()
    eventsub_task = asyncio.create_task(connect_eventsub_ws(latest), name="eventsub_ws")

    # auto-open admin on first run
    def _open():
        time.sleep(0.8)
        import webbrowser
        webbrowser.open("http://localhost:8000/admin")
    threading.Thread(target=_open, daemon=True).start()

    try:
        yield
    finally:
        if eventsub_task and not eventsub_task.done():
            eventsub_task.cancel()
            try:
                await eventsub_task
            except asyncio.CancelledError:
                pass

# ---------------- App + Static ----------------
def get_static_root() -> Path:
    base = getattr(sys, "_MEIPASS", None)  # PyInstaller onefile extraction dir
    return Path(base) if base else Path(__file__).parent

app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(get_static_root())), name="static")

# ---------------- Broadcast helper ----------------
async def broadcast(msg: Dict[str, Any]):
    stale = []
    for w in list(ws_clients):
        try:
            await w.send_text(json.dumps(msg))
        except Exception:
            stale.append(w)
    for w in stale:
        ws_clients.discard(w)

# ---------------- Health / WS / Status ----------------
@app.get("/health")
def health():
    return {
        "ok": True,
        "latest": store.latest.model_dump(),
        "settings": store.settings.model_dump(),
        "stats": store.stats.model_dump(),
    }

@app.get("/status")
def status_json():
    return get_worker_status()

@app.websocket("/ws")
async def websocket_ws(ws: WebSocket):
    await ws.accept()
    ws_clients.add(ws)
    await ws.send_text(json.dumps({"op": "bootstrap", "latest": store.latest.model_dump()}))
    try:
        while True:
            _ = await ws.receive_text()
    except WebSocketDisconnect:
        ws_clients.discard(ws)

# ---------------- Overlay / Stats pages ----------------
@app.get("/overlay")
def overlay(request: Request, channel: str | None = None):
    html = build_overlay_html(
        settings=store.settings,
        override_channel=(channel or "").lower().strip()
    )
    return HTMLResponse(html)

@app.get("/stats")
def stats_page():
    return HTMLResponse(build_stats_html(store))

@app.get("/customizer")
def customizer_page():
    return HTMLResponse(CUSTOMIZER_HTML)

# ---------------- Admin UI ----------------
ADMIN_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>Overlay Admin</title>
  <style>
    body { font-family: ui-sans-serif, system-ui, -apple-system; margin: 24px; max-width: 920px; }
    form { display:grid; gap:12px; max-width:640px; margin-bottom: 24px; }
    label { display:flex; flex-direction:column; gap:6px; font-weight:600; }
    input, select { padding:8px 10px; border:1px solid #ccc; border-radius:8px; }
    .row { display:grid; grid-template-columns: 1fr 1fr; gap:12px; }
    button { padding:10px 14px; border-radius:10px; border:0; background:#6d28d9; color:white; font-weight:700; cursor:pointer; }
    .note { color:#444; }
    .code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; background:#f4f4f5; padding:2px 6px; border-radius:6px; }
    .section { margin: 28px 0; }
    .muted { color:#777; font-size: 12px; }
    .ok { color: #047857; font-weight: 700; }
    .warn { color: #b45309; font-weight: 700; }
    a.btnlink { display:inline-block; padding:8px 12px; border-radius:10px; background:#374151; color:#fff; text-decoration:none; }
  </style>
</head>
<body>
  <h1>Overlay Admin</h1>

  <p><a class="btnlink" href="/stats">Open the Stats page →</a></p>
  <p><a class="btnlink" href="/customizer">Open the Customizer →</a></p>

  <div class="section">
    <h2>1) Twitch App Setup</h2>
    <ol>
      <li>Go the <a href="https://dev.twitch.tv/console/apps" target="_blank">Twitch Developer Console</a> and click <b>Register Your Application</b>.</li>
      <li>Set <b>Name</b> (anything), <b>OAuth Redirect URL</b> to <span class="code">{{redirect_uri}}</span>, and <b>Category</b> to Website Integration.</li>
      <li>Copy your <b>Client ID</b> and generate a <b>Client Secret</b>.</li>
    </ol>
  </div>

  <div class="section">
    <h2>2) Save App Credentials</h2>
    <form method="post" action="/admin/save-app">
      <div class="row">
        <label>Client ID
          <input type="text" name="client_id" value="{{client_id}}" placeholder="xxxxxxxxxxxxxxxxxxxxxx"/>
        </label>
        <label>Client Secret
          <input type="password" name="client_secret" value="{{client_secret}}" placeholder="•••••••••••••••••••"/>
        </label>
      </div>
      <label>Redirect URI (must match Twitch app)
        <input type="text" name="redirect_uri" value="{{redirect_uri}}" />
      </label>
      <div class="row">
        <label>Broadcaster Login (your channel)
          <input type="text" name="broadcaster_login" value="{{broadcaster_login}}" placeholder="yourchannel"/>
        </label>
        <label>Default Overlay Channel (fallback)
          <input type="text" name="default_channel" value="{{default_channel}}" placeholder="yourchannel"/>
        </label>
      </div>
      <button type="submit">Save Credentials</button>
      <div class="muted">Tip: For testing tokens, a third-party site like <a href="https://twitchtokengenerator.com" target="_blank">twitchtokengenerator.com</a> can help.</div>
    </form>
    <p>Status:
      {%token_status%}
    </p>
    <form method="get" action="/oauth/start">
      <button type="submit" {%oauth_disabled%}>Connect with Twitch (OAuth)</button>
      <span class="muted">This will ask for the scopes needed for follows/subs/bits.</span>
    </form>
  </div>

  <div class="section">
    <h2>3) Overlay Appearance</h2>
    <form method="post" action="/admin/save-appearance">
      <div class="row">
        <label>Rotation (ms)
          <input type="number" name="rotation_ms" min="1000" step="100" value="{{rotation_ms}}"/>
        </label>
        <label>Max Chat Lines
          <input type="number" name="chat_max_lines" min="20" step="5" value="{{chat_max_lines}}"/>
        </label>
      </div>
      <div class="row">
        <label>Chat Width (px)
          <input type="number" name="chat_width" min="280" step="10" value="{{chat_width}}"/>
        </label>
        <label>Chat Height (px)
          <input type="number" name="chat_height" min="240" step="10" value="{{chat_height}}"/>
        </label>
      </div>
      <div class="row">
        <label>Latest Box Font Size (px)
          <input type="number" name="latest_font_px" min="14" step="1" value="{{latest_font_px}}"/>
        </label>
        <label>Emote Size (px)
          <input type="number" name="emote_px" min="18" step="1" value="{{emote_px}}"/>
        </label>
      </div>
      <button type="submit">Save Appearance</button>
    </form>
  </div>

  <div class="section">
    <h2>4) Use It in OBS</h2>
    <p>Add a <b>Browser Source</b> in OBS → URL: <span class="code">http://localhost:8000/overlay</span>. Override channel with <span class="code">?channel=yourname</span> if needed.</p>
</body>
</html>
"""

CUSTOMIZER_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>Overlay Customizer</title>
  <style>
    body { margin:0; display:flex; height:100vh; font-family: ui-sans-serif, system-ui, -apple-system; }
    .canvas { flex:1; background:#222; position:relative; overflow:hidden; }
    .draggable { position:absolute; cursor:move; user-select:none; padding:8px 12px; border:1px dashed #888; color:#fff; }
    .sidebar { width:260px; background:#f3f4f6; padding:12px; box-sizing:border-box; overflow-y:auto; }
    label { display:block; margin-top:8px; }
    input[type="text"], input[type="color"] { width:100%; padding:4px; box-sizing:border-box; }
    button { margin-top:12px; padding:8px 12px; border-radius:8px; border:0; background:#6d28d9; color:white; font-weight:700; cursor:pointer; }
  </style>
</head>
<body>
  <div class="canvas" id="canvas">
    <div id="alert" class="draggable">Alert</div>
    <div id="rotator" class="draggable">Rotator</div>
    <div id="chat" class="draggable">Chat</div>
  </div>
  <div class="sidebar">
    <h3>Options</h3>
    <label><input type="checkbox" id="showAlert" checked/> Show Alert</label>
    <label><input type="checkbox" id="showRotator" checked/> Show Rotator</label>
    <label><input type="checkbox" id="showChat" checked/> Show Chat</label>
    <label>Text Color <input type="color" id="textColor" value="#ffffff"/></label>
    <label>Font Family <input type="text" id="fontFamily" placeholder="e.g. Arial"/></label>
    <h4>Alert Sounds</h4>
    <label>Follow <input type="text" id="soundFollow" placeholder="URL"/></label>
    <label>Sub <input type="text" id="soundSub" placeholder="URL"/></label>
    <label>Bits <input type="text" id="soundBits" placeholder="URL"/></label>
    <label>Raid <input type="text" id="soundRaid" placeholder="URL"/></label>
    <button id="saveBtn" type="button">Save</button>
  </div>

<script>
  function makeDrag(id){
    const el=document.getElementById(id);
    let drag=false,offX=0,offY=0;
    el.addEventListener('mousedown',e=>{drag=true;offX=e.offsetX;offY=e.offsetY;});
    window.addEventListener('mousemove',e=>{ if(!drag) return; el.style.left=(e.pageX-offX)+'px'; el.style.top=(e.pageY-offY)+'px'; });
    window.addEventListener('mouseup',()=>{drag=false;});
  }
  ['alert','rotator','chat'].forEach(makeDrag);

  function load(){
    const data=JSON.parse(localStorage.getItem('overlayCustom')||'{}');
    if(data.positions){
      for (const k in data.positions){ const p=data.positions[k]; const el=document.getElementById(k); if(p && el){ el.style.left=p.x+'px'; el.style.top=p.y+'px'; }}
    }
    if(data.show){
      showAlert.checked = data.show.alert !== false;
      showRotator.checked = data.show.rotator !== false;
      showChat.checked = data.show.chat !== false;
    }
    if(data.textColor) textColor.value = data.textColor;
    if(data.fontFamily) fontFamily.value = data.fontFamily;
    if(data.sounds){
      soundFollow.value = data.sounds.follow || '';
      soundSub.value = data.sounds.sub || '';
      soundBits.value = data.sounds.bits || '';
      soundRaid.value = data.sounds.raid || '';
    }
  }

  function save(){
    const data={
      positions:{
        alert:{ x:parseInt(document.getElementById('alert').style.left)||0, y:parseInt(document.getElementById('alert').style.top)||0 },
        rotator:{ x:parseInt(document.getElementById('rotator').style.left)||0, y:parseInt(document.getElementById('rotator').style.top)||0 },
        chat:{ x:parseInt(document.getElementById('chat').style.left)||0, y:parseInt(document.getElementById('chat').style.top)||0 }
      },
      show:{ alert:showAlert.checked, rotator:showRotator.checked, chat:showChat.checked },
      textColor:textColor.value,
      fontFamily:fontFamily.value,
      sounds:{ follow:soundFollow.value, sub:soundSub.value, bits:soundBits.value, raid:soundRaid.value }
    };
    localStorage.setItem('overlayCustom', JSON.stringify(data));
    alert('Saved');
  }
  document.getElementById('saveBtn').addEventListener('click', save);
  load();
</script>
</body>
</html>
"""

def _token_status_html() -> str:
    s = store.settings
    if s.user_access_token:
        tail = s.user_access_token[-6:] if len(s.user_access_token) >= 6 else "…"
        return f'<span class="ok">Connected</span> <span class="muted">(…{tail})</span>'
    return '<span class="warn">Not connected</span>'

def render_admin_html() -> str:
    s = store.settings
    html = ADMIN_HTML
    repl = {
        "client_id": s.client_id,
        "client_secret": s.client_secret,
        "redirect_uri": s.redirect_uri,
        "broadcaster_login": s.broadcaster_login,
        "default_channel": s.default_channel,
        "rotation_ms": s.rotation_ms,
        "chat_max_lines": s.chat_max_lines,
        "chat_width": s.chat_width,
        "chat_height": s.chat_height,
        "latest_font_px": s.latest_font_px,
        "emote_px": s.emote_px,
    }
    for k, v in repl.items():
        html = html.replace(f"{{{{{k}}}}}", str(v))
    html = html.replace("{%token_status%}", _token_status_html())
    html = html.replace("{%oauth_disabled%}", "" if (s.client_id and s.client_secret and s.redirect_uri) else "disabled")
    return html

@app.get("/admin")
def admin_form():
    return HTMLResponse(render_admin_html())

@app.post("/admin/save-app")
async def admin_save_app(
    client_id: str = Form(""),
    client_secret: str = Form(""),
    redirect_uri: str = Form("http://localhost:8000/oauth/callback"),
    broadcaster_login: str = Form(""),
    default_channel: str = Form(""),
):
    s = store.settings
    s.client_id = client_id.strip()
    s.client_secret = client_secret.strip()
    s.redirect_uri = redirect_uri.strip()
    s.broadcaster_login = broadcaster_login.lower().strip()
    s.default_channel = default_channel.lower().strip()
    store.save()
    # optional: don't auto-restart here; user will OAuth next
    return RedirectResponse(url="/admin", status_code=303)

@app.post("/admin/save-appearance")
async def admin_save_appearance(
    rotation_ms: int = Form(5000),
    chat_max_lines: int = Form(60),
    chat_width: int = Form(420),
    chat_height: int = Form(420),
    latest_font_px: int = Form(28),
    emote_px: int = Form(28),
):
    s = store.settings
    s.rotation_ms = max(1000, int(rotation_ms))
    s.chat_max_lines = max(10, int(chat_max_lines))
    s.chat_width = max(280, int(chat_width))
    s.chat_height = max(240, int(chat_height))
    s.latest_font_px = max(14, int(latest_font_px))
    s.emote_px = max(18, int(emote_px))
    store.save()
    return RedirectResponse(url="/admin", status_code=303)

# ---------------- OAuth flow ----------------
@app.get("/oauth/start")
async def oauth_start():
    s = store.settings
    if not (s.client_id and s.client_secret and s.redirect_uri):
        return RedirectResponse(url="/admin", status_code=303)

    state = secrets.token_urlsafe(16)
    _pending_oauth_states.add(state)

    scopes = [
        "moderator:read:followers",
        "channel:read:subscriptions",
        "bits:read",
    ]
    scope = "%20".join(scopes)

    qs = (
        f"?client_id={s.client_id}"
        f"&redirect_uri={s.redirect_uri}"
        f"&response_type=code"
        f"&state={state}"
        f"&scope={scope}"
        f"&force_verify=true"
    )
    return RedirectResponse(url="https://id.twitch.tv/oauth2/authorize" + qs, status_code=303)

@app.get("/oauth/callback")
async def oauth_callback(code: str | None = None, state: str | None = None, error: str | None = None):
    s = store.settings
    if error:
        return HTMLResponse(f"<h1>OAuth Error</h1><p>{error}</p><a href='/admin'>Back</a>", status_code=400)
    if not code or not state or state not in _pending_oauth_states:
        return HTMLResponse("<h1>Invalid OAuth state</h1><a href='/admin'>Back</a>", status_code=400)
    _pending_oauth_states.discard(state)

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(
            "https://id.twitch.tv/oauth2/token",
            data={
                "client_id": s.client_id,
                "client_secret": s.client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": s.redirect_uri,
            },
        )
        r.raise_for_status()
        data = r.json()
        s.user_access_token = data.get("access_token", "")
        s.user_refresh_token = data.get("refresh_token", "")
        store.save()

    # hot-restart EventSub after successful OAuth
    await internal_restart_eventsub()
    return RedirectResponse(url="/admin", status_code=303)

# ---------------- Internal control endpoints (for tray) ----------------
@app.post("/internal/restart-eventsub")
async def internal_restart_eventsub():
    # cancel and restart the worker
    global eventsub_task
    if eventsub_task and not eventsub_task.done():
        eventsub_task.cancel()
        try:
            await eventsub_task
        except asyncio.CancelledError:
            pass
    await ensure_tokens_ready()
    eventsub_task = asyncio.create_task(connect_eventsub_ws(latest), name="eventsub_ws")
    return {"ok": True}

@app.post("/internal/restart-server")
def internal_restart_server():
    _restart_server_flag.set()
    return {"ok": True}

@app.post("/internal/quit")
async def internal_quit():
    _quit_flag.set()
    # ask uvicorn to shut down
    try:
        if _current_server is not None:
            _current_server.should_exit = True
    except Exception:
        pass
    # also stop the EventSub task now (lifespan would do this too, but be proactive)
    global eventsub_task
    if eventsub_task and not eventsub_task.done():
        eventsub_task.cancel()
        try:
            await eventsub_task
        except asyncio.CancelledError:
            pass
    return {"ok": True}


# ---------------- System tray (pystray) ----------------
def _make_tray_image():
    # create a simple purple badge with white bolt (no external file needed)
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((4, 4, 60, 60), fill=(124, 58, 237, 255))  # purple
    # bolt
    d.polygon([(32,12),(26,30),(36,30),(28,52),(50,28),(38,28)], fill=(255,255,255,255))
    return img

def start_tray():
    import pystray
    import webbrowser

    def _open_admin(icon, item):
        webbrowser.open("http://localhost:8000/admin")

    def _open_stats(icon, item):
        webbrowser.open("http://localhost:8000/stats")

    def _restart_eventsub(icon, item):
        try:
            httpx.post("http://127.0.0.1:8000/internal/restart-eventsub", timeout=5.0)
        except Exception:
            pass

    def _restart_server(icon, item):
        try:
            httpx.post("http://127.0.0.1:8000/internal/restart-server", timeout=5.0)
        except Exception:
            pass

    def _quit(icon, item):
        try:
            httpx.post("http://127.0.0.1:8000/internal/quit", timeout=3.0)
        except Exception:
            pass
        try:
            icon.stop()
        finally:
            # as a final fallback
            sys.exit(0)

    menu = pystray.Menu(
        pystray.MenuItem("Open Admin", _open_admin),
        pystray.MenuItem("Open Stats", _open_stats),
        pystray.MenuItem("Restart EventSub", _restart_eventsub),
        pystray.MenuItem("Restart Server", _restart_server),
        pystray.MenuItem("Quit", _quit)
    )
    icon = pystray.Icon("TwitchOverlay", _make_tray_image(), "Twitch Overlay", menu)
    icon.run()  # blocking in its own thread

# ---------------- Programmatic Uvicorn server with restart loop ----------------
def run_server_loop():
    import uvicorn
    global _current_server

    while True:
        _restart_server_flag.clear()
        config_kwargs = dict(host="0.0.0.0", port=8000, reload=False)
        if getattr(sys, "frozen", False) or sys.stderr is None:
            config_kwargs["log_config"] = None

        config = uvicorn.Config(app, **config_kwargs)
        server = uvicorn.Server(config)
        _current_server = server  # <-- add this

        server.run()

        _current_server = None  # clear after it returns

        if _quit_flag.is_set():
            break
        if _restart_server_flag.is_set():
            continue
        break


# ---------------- Entrypoint ----------------
if __name__ == "__main__":
    # optional log file so silent crashes are visible
    try:
        STORE_DIR.mkdir(parents=True, exist_ok=True)
        import logging
        logging.basicConfig(filename=str(STORE_DIR / "app.log"),
                            level=logging.INFO,
                            format="%(asctime)s %(levelname)s %(message)s")
    except Exception:
        pass

    # Tray runs in a thread so main thread can run the server
    t = threading.Thread(target=start_tray, daemon=True)
    t.start()

    # Start server loop (supports Restart Server / Quit from tray)
    run_server_loop()
