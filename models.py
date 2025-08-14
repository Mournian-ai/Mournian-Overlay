from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

# ------------------------------------------------------------
# Storage location:
# - Packaged exe  -> per-user app data (AppData on Windows, etc.)
# - Running from source -> ./store/ next to the code
# ------------------------------------------------------------
if getattr(sys, "frozen", False):
    # Bundled (PyInstaller)
    if sys.platform.startswith("win"):
        base_dir = Path(os.getenv("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":  # macOS
        base_dir = Path.home() / "Library" / "Application Support"
    else:  # Linux / other
        base_dir = Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    STORE_DIR = base_dir / "TwitchOverlay"
else:
    # Source checkout
    STORE_DIR = Path(__file__).parent / "store"

STORE_DIR.mkdir(parents=True, exist_ok=True)
STORE_FILE = STORE_DIR / "store.json"


# ------------------------------------------------------------
# Models
# ------------------------------------------------------------
class Latest(BaseModel):
    follow: Dict[str, Any] | None = None
    sub: Dict[str, Any] | None = None
    bits: Dict[str, Any] | None = None


class Settings(BaseModel):
    # Overlay/admin visuals
    default_channel: str = ""  # fallback if no ?channel=
    rotation_ms: int = 5000
    chat_max_lines: int = 60
    chat_width: int = 420
    chat_height: int = 420
    latest_font_px: int = 28
    emote_px: int = 28

    # Twitch app + OAuth
    client_id: str = ""
    client_secret: str = ""
    redirect_uri: str = "http://localhost:8000/oauth/callback"

    # Who are we streaming as?
    broadcaster_login: str = ""  # e.g. "yourchannel"
    broadcaster_id: str = ""  # resolved automatically (optional)
    moderator_user_id: str = ""  # resolved automatically from token (optional)

    # User token (from OAuth)
    user_access_token: str = ""
    user_refresh_token: str = ""


class Stats(BaseModel):
    total_bits: int = 0


class Recent(BaseModel):
    follows: List[Dict[str, Any]] = Field(default_factory=list)
    subs: List[Dict[str, Any]] = Field(default_factory=list)
    cheers: List[Dict[str, Any]] = Field(default_factory=list)
    max_items: int = 100  # in-file cap

    def _push(self, bucket: List[Dict[str, Any]], item: Dict[str, Any]):
        bucket.append(item)
        if len(bucket) > self.max_items:
            del bucket[:-self.max_items]

    def push_follow(self, item: Dict[str, Any]):  # noqa: D401
        self._push(self.follows, item)

    def push_sub(self, item: Dict[str, Any]):  # noqa: D401
        self._push(self.subs, item)

    def push_cheer(self, item: Dict[str, Any]):  # noqa: D401
        self._push(self.cheers, item)


class Store(BaseModel):
    settings: Settings = Field(default_factory=Settings)
    latest: Latest = Field(default_factory=Latest)
    stats: Stats = Field(default_factory=Stats)
    recent: Recent = Field(default_factory=Recent)

    @classmethod
    def load(cls) -> "Store":
        if STORE_FILE.exists():
            try:
                return cls(**json.loads(STORE_FILE.read_text(encoding="utf-8")))
            except Exception:
                # Corrupt or incompatible file → start fresh
                return cls()
        return cls()

    def save(self) -> None:
        tmp = STORE_FILE.with_suffix(".json.tmp")
        tmp.write_text(self.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(STORE_FILE)
