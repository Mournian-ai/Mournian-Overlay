import asyncio
import json
import time
from typing import Dict, Any, Awaitable, Callable, Optional

import httpx
from pydantic import BaseModel

from models import Latest, Store

TWITCH_API = "https://api.twitch.tv/helix"
OAUTH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"

# ---- Worker status (for /status & /stats live badge) ----
_worker_status = {
    "connected": False,
    "session_id": None,
    "since": 0.0,
    "last_error": "",
    "backoff_s": 0,
    "subs": {"follow": False, "subscribe": False, "cheer": False},
}

def get_worker_status():
    return {
        "connected": _worker_status["connected"],
        "session_id": _worker_status["session_id"],
        "since": _worker_status["since"],
        "last_error": _worker_status["last_error"],
        "backoff_s": _worker_status["backoff_s"],
        "subs": dict(_worker_status["subs"]),
    }

# ---- Injected hooks/objects ----
_broadcast: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None
_store: Optional[Store] = None

def register_broadcaster(fn: Callable[[Dict[str, Any]], Awaitable[None]]):
    global _broadcast
    _broadcast = fn

def register_store(store: Store):
    global _store
    _store = store

def HEADERS(token: str, client_id: str) -> Dict[str, str]:
    return {"Client-Id": client_id, "Authorization": f"Bearer {token}"}

# ---- Token state ----
class TokenState(BaseModel):
    access_token: str = ""
    refresh_token: Optional[str] = None

token_state = TokenState()

async def refresh_user_token_if_needed() -> None:
    if _store is None: return
    s = _store.settings
    if not token_state.refresh_token:
        return
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(
            OAUTH_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": token_state.refresh_token,
                "client_id": s.client_id,
                "client_secret": s.client_secret,
                "redirect_uri": s.redirect_uri,
            },
        )
        r.raise_for_status()
        data = r.json()
        token_state.access_token = data.get("access_token", token_state.access_token)
        if data.get("refresh_token"):
            token_state.refresh_token = data["refresh_token"]
        # persist back
        s.user_access_token = token_state.access_token
        s.user_refresh_token = token_state.refresh_token or ""
        _store.save()

# ---- ID resolution ----
async def ensure_broadcaster_id(token: str) -> str:
    assert _store is not None
    s = _store.settings
    if s.broadcaster_id:
        return s.broadcaster_id
    if not s.broadcaster_login:
        raise RuntimeError("Set the 'Broadcaster Login' in /admin")
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(f"{TWITCH_API}/users?login={s.broadcaster_login}", headers=HEADERS(token, s.client_id))
        r.raise_for_status()
        data = r.json().get("data", [])
        if not data:
            raise RuntimeError(f"Broadcaster not found for login '{s.broadcaster_login}'")
        s.broadcaster_id = data[0]["id"]
        _store.save()
        return s.broadcaster_id

async def ensure_moderator_user_id(token: str) -> str:
    assert _store is not None
    s = _store.settings
    if s.moderator_user_id:
        return s.moderator_user_id
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(f"{TWITCH_API}/users", headers=HEADERS(token, s.client_id))
        r.raise_for_status()
        data = r.json().get("data", [])
        if not data:
            raise RuntimeError("Failed to resolve user for the provided USER access token.")
        s.moderator_user_id = data[0]["id"]
        _store.save()
        return s.moderator_user_id

# ---- Subscriptions ----
SUB_VERSIONS = {
    "channel.follow": "2",   # requires moderator_user_id condition + scope
    "channel.subscribe": "1",
    "channel.cheer": "1",
}

async def subscribe(token: str, session_id: str, sub_type: str, condition: Dict[str, str]):
    assert _store is not None
    s = _store.settings
    payload = {
        "type": sub_type,
        "version": SUB_VERSIONS.get(sub_type, "1"),
        "condition": condition,
        "transport": {"method": "websocket", "session_id": session_id},
    }
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(
            f"{TWITCH_API}/eventsub/subscriptions",
            headers=HEADERS(token, s.client_id) | {"Content-Type": "application/json"},
            json=payload,
        )
        if r.status_code == 401:
            await refresh_user_token_if_needed()
            r = await client.post(
                f"{TWITCH_API}/eventsub/subscriptions",
                headers=HEADERS(token_state.access_token, s.client_id) | {"Content-Type": "application/json"},
                json=payload,
            )
        if r.status_code >= 400:
            try:
                print("[EventSub] subscribe error", sub_type, r.status_code, r.text)
            except Exception:
                pass
        r.raise_for_status()

# ---- Public: ensure tokens/ids ready on boot ----
async def ensure_tokens_ready():
    if _store is None: return
    s = _store.settings
    token_state.access_token = s.user_access_token or ""
    token_state.refresh_token = s.user_refresh_token or None
    try:
        await refresh_user_token_if_needed()
    except Exception as e:
        print(f"[Token] Optional refresh failed/skipped: {e}")

# ---- EventSub worker with persistence + status ----
async def connect_eventsub_ws(latest: Latest):
    import websockets
    assert _store is not None and _broadcast is not None

    backoff = 1
    last_session_id = None
    try:
        while True:
            try:
                _worker_status["backoff_s"] = backoff
                _worker_status["connected"] = False

                if not token_state.access_token:
                    raise RuntimeError("Please connect your Twitch account in /admin (OAuth)")

                broadcaster_id = await ensure_broadcaster_id(token_state.access_token)
                moderator_id = await ensure_moderator_user_id(token_state.access_token)

                uri = "wss://eventsub.wss.twitch.tv/ws"
                print("[EventSub] Connecting to", uri)
                async with websockets.connect(uri, ping_interval=15, ping_timeout=20) as ws:
                    welcome_raw = await ws.recv()
                    welcome = json.loads(welcome_raw)
                    session = (
                        welcome.get("session")
                        or welcome.get("payload", {}).get("session")
                        or welcome.get("metadata", {}).get("session")
                    )
                    if not session:
                        print("[EventSub] No session in welcome:", welcome)
                        await asyncio.sleep(3)
                        continue

                    session_id = session["id"]
                    changed = "(new)" if session_id != last_session_id else ""
                    last_session_id = session_id
                    print(f"[EventSub] session_id: {session_id} {changed}")

                    _worker_status["session_id"] = session_id
                    _worker_status["subs"] = {"follow": False, "subscribe": False, "cheer": False}

                    await subscribe(token_state.access_token, session_id, "channel.follow",
                                    {"broadcaster_user_id": broadcaster_id, "moderator_user_id": moderator_id})
                    _worker_status["subs"]["follow"] = True

                    await subscribe(token_state.access_token, session_id, "channel.subscribe",
                                    {"broadcaster_user_id": broadcaster_id})
                    _worker_status["subs"]["subscribe"] = True

                    await subscribe(token_state.access_token, session_id, "channel.cheer",
                                    {"broadcaster_user_id": broadcaster_id})
                    _worker_status["subs"]["cheer"] = True

                    print("[EventSub] Subscriptions created")

                    backoff = 1
                    _worker_status["backoff_s"] = backoff
                    _worker_status["connected"] = True
                    _worker_status["since"] = time.time()
                    _worker_status["last_error"] = ""

                    async for message in ws:
                        try:
                            data = json.loads(message)
                        except Exception:
                            continue

                        sub = data.get("subscription") or data.get("payload", {}).get("subscription")
                        event = data.get("event") or data.get("payload", {}).get("event")
                        if not sub or not event:
                            continue  # keepalive/session

                        etype = sub.get("type")
                        if etype == "channel.follow":
                            latest.follow = {
                                "user_name": event.get("user_name") or event.get("user_login"),
                                "user_id": event.get("user_id"),
                                "followed_at": event.get("followed_at"),
                            }
                            _store.latest.follow = latest.follow
                            _store.recent.push_follow(latest.follow)
                            _store.save()
                            await _broadcast({"op": "latest_update", "kind": "follow", "data": latest.follow})
                            await _broadcast({"op": "alert", "kind": "follow", "data": latest.follow})

                        elif etype == "channel.subscribe":
                            latest.sub = {
                                "user_name": event.get("user_name"),
                                "tier": event.get("tier"),
                                "is_gift": event.get("is_gift", False),
                            }
                            _store.latest.sub = latest.sub
                            _store.recent.push_sub(latest.sub)
                            _store.save()
                            await _broadcast({"op": "latest_update", "kind": "sub", "data": latest.sub})
                            await _broadcast({"op": "alert", "kind": "sub", "data": latest.sub})

                        elif etype == "channel.cheer":
                            latest.bits = {
                                "user_name": event.get("user_name", "Anonymous"),
                                "bits": event.get("bits", 0),
                                "message": event.get("message", ""),
                            }
                            _store.latest.bits = latest.bits
                            _store.stats.total_bits += int(latest.bits.get("bits") or 0)
                            _store.recent.push_cheer(latest.bits)
                            _store.save()
                            await _broadcast({"op": "latest_update", "kind": "bits", "data": latest.bits})
                            await _broadcast({"op": "alert", "kind": "bits", "data": latest.bits})

            except Exception as e:
                print(f"[EventSub] Error: {e}")
                _worker_status["connected"] = False
                _worker_status["last_error"] = str(e)
                _worker_status["backoff_s"] = backoff
                try:
                    await refresh_user_token_if_needed()
                except Exception as rerr:
                    print(f"[EventSub] Token refresh failed: {rerr}")
                print(f"[EventSub] Reconnecting in {backoff}s…")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)
    except asyncio.CancelledError:
        _worker_status["connected"] = False
        print("[EventSub] Cancelled, closing…")
        raise
