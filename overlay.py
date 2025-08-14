from models import Settings

def build_overlay_html(settings: Settings, override_channel: str = "") -> str:
    channel = (override_channel or settings.default_channel or "").lower().strip()

    prefix = f'<!DOCTYPE html>\n<html data-channel="{channel}">\n'
    rest = f"""<head>
  <meta charset="utf-8" />
  <title>Twitch Overlay</title>
  <!-- Local tmi.js served by FastAPI /static -->
  <script src="/static/tmi.min.js"></script>
  <style>
    :root {{ --text-color: white; --font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI; }}
    html, body {{ margin:0; padding:0; background:transparent; font-family: var(--font-family); }}
    .container {{ position: relative; width: 100vw; height: 100vh; overflow: hidden; }}

    /* Rotating latest bar (bottom-left) */
    .latestBar {{
      position: absolute; bottom: 20px; left: 20px;
      min-width: 360px; max-width: 560px;
      padding: 14px 18px; border-radius: 14px;
      background: rgba(0,0,0,0.55); backdrop-filter: blur(6px);
      color: var(--text-color); line-height: 1.4;
      box-shadow: 0 10px 30px rgba(0,0,0,0.35);
    }}
    .label {{ opacity: 0.7; font-size: 16px; text-transform: uppercase; letter-spacing: 1px; }}
    .value {{ font-weight: 700; font-size: {settings.latest_font_px}px; }}
    .fade {{ animation: fadein 350ms ease-out; }}
    @keyframes fadein {{ from {{opacity:0; transform: translateY(8px);}} to {{opacity:1; transform: translateY(0);}} }}

    /* Alert pop (center-top) */
    .alert {{
      position: absolute; top: 15%; left: 50%; transform: translateX(-50%);
      background: rgba(255,255,255,0.06); color: var(--text-color); padding: 12px 18px; border-radius: 12px;
      font-size: 26px; font-weight: 800; border: 1px solid rgba(255,255,255,0.15);
      opacity: 0; pointer-events: none;
    }}
    .alert.show {{ animation: pop 2.8s ease-out; }}
    @keyframes pop {{
      0% {{ opacity: 0; transform: translate(-50%, -6px) scale(0.95); }}
      8% {{ opacity:  1; transform: translate(-50%, 0)  scale(1.0); }}
      85% {{ opacity:  1; }}
      100% {{ opacity: 0; transform: translate(-50%, 6px)  scale(0.98); }}
    }}

    /* Chat box (bottom-right) */
    .chatBox {{
      position: absolute; right: 20px; bottom: 20px;
      width: {settings.chat_width}px; height: {settings.chat_height}px;
      display: flex; flex-direction: column;
      background: rgba(0,0,0,0.55); backdrop-filter: blur(6px);
      border-radius: 14px; box-shadow: 0 10px 30px rgba(0,0,0,0.35);
      color: var(--text-color); overflow: hidden;
    }}
    .chatHeader {{
      padding: 8px 12px; font-size: 14px; letter-spacing: .5px; text-transform: uppercase;
      color: #adadb8; border-bottom: 1px solid rgba(255,255,255,0.08);
      display:flex; justify-content:space-between; align-items:center;
    }}
    .chatStatus {{ font-size: 12px; color:#8a8a96; }}
    .chatScroll {{
      flex: 1; overflow-y: hidden; padding: 10px 12px; display: flex; flex-direction: column; gap: 6px;
    }}
    .line {{ display: flex; align-items: flex-start; gap: 6px; font-size: 16px; line-height: 1.35; }}
    .name {{ font-weight: 700; margin-right: 6px; white-space: nowrap; }}
    .message {{ word-wrap: break-word; overflow-wrap: anywhere; }}
    .emote {{ vertical-align: middle; height: {settings.emote_px}px; }}
    .fader {{ animation: lineIn 200ms ease-out; }}
    @keyframes lineIn {{ from {{opacity:0; transform: translateY(4px);}} to {{opacity:1; transform: translateY(0);}} }}
    .chatScroll::-webkit-scrollbar {{ width: 0; height: 0; }}
  </style>
</head>
<body>
  <div class="container">
    <div id="alert" class="alert"></div>

    <!-- Bottom-left rotating bar -->
    <div class="latestBar fade">
      <div class="label" id="rotLabel">Latest Follow</div>
      <div class="value" id="rotValue">—</div>
    </div>

    <!-- Bottom-right chat -->
    <div class="chatBox">
      <div class="chatHeader">
        <span>Chat</span>
        <span id="chatStatus" class="chatStatus">loading…</span>
      </div>
      <div id="chatScroll" class="chatScroll"></div>
    </div>
  </div>

  <script>
    // --- on-screen logger ---
    const chatStatusEl = document.getElementById('chatStatus');
    function setStatus(s){{ chatStatusEl.textContent = s; }}
    window.addEventListener('error', (e)=> setStatus('error: ' + (e.message || 'unknown')));
    window.addEventListener('unhandledrejection', ()=> setStatus('promise error'));

    // --- Rotating latest ---
    const rotLabel = document.getElementById('rotLabel');
    const rotValue = document.getElementById('rotValue');
      const alertBox = document.getElementById('alert');
      const custom = JSON.parse(localStorage.getItem('overlayCustom') || "{{}}" );
      const latest = {{ follow:null, sub:null, bits:null }};
      const rotation = ["follow","sub","bits"];
      let idx = 0;

      function applyCustom(){{
        if (custom.fontFamily) document.documentElement.style.setProperty('--font-family', custom.fontFamily);
        if (custom.textColor) document.documentElement.style.setProperty('--text-color', custom.textColor);
        if (custom.show && custom.show.rotator === false) document.querySelector('.latestBar').style.display='none';
        if (custom.show && custom.show.chat === false) document.querySelector('.chatBox').style.display='none';
        if (custom.show && custom.show.alert === false) alertBox.style.display='none';
        if (custom.positions){{
          const p = custom.positions.rotator; if(p){{ const el=document.querySelector('.latestBar'); el.style.left=p.x+'px'; el.style.top=p.y+'px'; el.style.bottom=''; }}
          const c = custom.positions.chat; if(c){{ const el=document.querySelector('.chatBox'); el.style.left=c.x+'px'; el.style.top=c.y+'px'; el.style.right=''; el.style.bottom=''; }}
          const a = custom.positions.alert; if(a){{ alertBox.style.left=a.x+'px'; alertBox.style.top=a.y+'px'; alertBox.style.transform=''; }}
        }}
      }}
      applyCustom();

      function renderRotation(){{
      const kind = rotation[idx % rotation.length]; idx++;
      let label = "Latest " + (kind === "bits" ? "Bits" : (kind === "sub" ? "Sub" : "Follow"));
      let val = "—"; const d = latest[kind];
      if (d) {{
        if (kind === "follow") val = d.user_name || d.user_login || "Someone";
        if (kind === "sub") {{
          const tier = d.tier ? ("T" + (parseInt(d.tier,10)/1000)) : "";
          val = `${{d.user_name || "Someone"}} ${{tier}}${{d.is_gift ? " (gift)" : ""}}`;
        }}
        if (kind === "bits") val = `${{d.user_name || "Anonymous"}} — ${{d.bits || 0}} bits`;
      }}
      rotLabel.textContent = label; rotValue.textContent = val;
    }}

      function playSound(kind){{
        const url = custom.sounds && custom.sounds[kind];
        if (url){{ try {{ new Audio(url).play(); }} catch(e){{}} }}
      }}

      function showAlert(kind, data){{
        let text = "";
        if (kind === "follow") text = `💜 ${{data.user_name || "Someone"}} followed!`;
        if (kind === "sub") {{
          const tier = data.tier ? ("T" + (parseInt(data.tier,10)/1000)) : "";
          text = `⭐ ${{data.user_name || "Someone"}} subscribed ${{tier}}${{data.is_gift ? " (gift)" : ""}}!`;
        }}
        if (kind === "bits") text = `💎 ${{data.user_name || "Anonymous"}} cheered ${{data.bits}} bits!`;
        if (kind === "raid") text = `🚀 ${{data.from_broadcaster_user_name || "Someone"}} raided with ${{data.viewers || 0}} viewers!`;
        alertBox.textContent = text;
        alertBox.classList.remove('show'); void alertBox.offsetWidth; alertBox.classList.add('show');
        playSound(kind);
      }}

    setInterval(renderRotation, {settings.rotation_ms});
    renderRotation();

    // --- WS bridge to backend for latest/alerts ---
    const wsProtocol = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${{wsProtocol}}://${{location.host}}/ws`);
    ws.addEventListener('message', (ev) => {{
      try {{
        const msg = JSON.parse(ev.data);
        if (msg.op === "bootstrap" && msg.latest) {{
          latest.follow = msg.latest.follow; latest.sub = msg.latest.sub; latest.bits = msg.latest.bits;
          renderRotation();
        }} else if (msg.op === "latest_update") {{
          latest[msg.kind] = msg.data; renderRotation();
        }} else if (msg.op === "alert") {{
          showAlert(msg.kind, msg.data);
        }}
      }} catch(e) {{ setStatus('ws parse error'); }}
    }});

    // --- Twitch chat (bottom-right) ---
    const chatEl = document.getElementById('chatScroll');

    function getChannelName(){{
      const p = new URLSearchParams(location.search);
      const qp = (p.get('channel') || "").toLowerCase().trim();
      if (qp) return qp.replace(/^#/, "");
      const fromData = (document.documentElement.dataset.channel || "").toLowerCase().trim();
      return fromData.replace(/^#/, "");
    }}

    const channelName = getChannelName();
    if (!channelName) {{
      setStatus("no channel");
    }} else if (typeof tmi === 'undefined') {{
      setStatus("tmi.js failed to load");
    }} else {{
      setStatus("connecting…");
      const client = new tmi.Client({{
        options: {{ debug: false }},
        connection: {{ secure: true, reconnect: true }},
        channels: [channelName]   // no hash
      }});

      client.on('connected', () => setStatus(`connected`));
      client.on('join', (chan, username, self) => {{ if (self) setStatus(`joined #${{channelName}}`); }});
      client.on('disconnected', () => setStatus('disconnected'));
      client.on('reconnect', () => setStatus('reconnecting…'));
      client.on('notice', (_, __, msgid) => setStatus(`notice: ${{msgid||''}}`));

      client.connect().catch(() => setStatus('connect error'));

      client.on('message', (channel, tags, message, self) => {{
        if (self) return;
        const line = document.createElement('div'); line.className = 'line fader';

        const name = document.createElement('span');
        name.className = 'name';
        name.textContent = tags['display-name'] || tags.username || 'User';
        const color = tags.color || '#b9a3e3'; name.style.color = color;

        const msgSpan = document.createElement('span'); msgSpan.className = 'message';
        msgSpan.innerHTML = renderWithTwitchEmotes(message, tags.emotes);

        line.appendChild(name); const colon = document.createElement('span'); colon.textContent = ': ';
        line.appendChild(colon); line.appendChild(msgSpan);

        chatEl.appendChild(line); trimChat(); scrollToBottom();
      }});
    }}

    function scrollToBottom(){{ chatEl.scrollTop = chatEl.scrollHeight; }}
    function trimChat(maxLines = {settings.chat_max_lines}){{
      while (chatEl.children.length > maxLines) {{ chatEl.removeChild(chatEl.firstChild); }}
    }}

    // ---- Emote renderer: escape text, keep <img> intact ----
    function escapeHtml(s) {{
      return String(s)
        .replace(/&/g,'&amp;')
        .replace(/</g,'&lt;')
        .replace(/>/g,'&gt;')
        .replace(/"/g,'&quot;')
        .replace(/'/g,'&#39;');
    }}
    function escapeAttr(s) {{ return escapeHtml(s); }}

    function renderWithTwitchEmotes(text, emotesMap) {{
      if (!emotesMap) return escapeHtml(text);

      const ranges = [];
      for (const id in emotesMap) {{
        for (const r of emotesMap[id]) {{
          const [s, e] = r.split('-').map(n => parseInt(n, 10));
          ranges.push([s, e, id]);
        }}
      }}
      ranges.sort((a, b) => a[0] - b[0]);

      let html = ''; let cursor = 0;
      for (const [start, end, id] of ranges) {{
        if (cursor < start) {{ html += escapeHtml(text.slice(cursor, start)); }}
        const token = text.slice(start, end + 1);
        html += `<img class="emote" src="https://static-cdn.jtvnw.net/emoticons/v2/${{id}}/default/dark/2.0" alt="${{escapeAttr(token)}}"/>`;
        cursor = end + 1;
      }}
      if (cursor < text.length) {{ html += escapeHtml(text.slice(cursor)); }}
      return html;
    }}
  </script>
</body>
</html>"""
    return prefix + rest
