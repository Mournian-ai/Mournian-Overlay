from datetime import datetime
from typing import List
from models import Store

def _fmt_time(ts: str | None) -> str:
    if not ts:
        return "—"
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ts

def _row(cells: List[str]) -> str:
    tds = "".join(f"<td>{c}</td>" for c in cells)
    return f"<tr>{tds}</tr>"

def build_stats_html(store: Store) -> str:
    s = store.settings
    latest_follow = store.latest.follow or {}
    latest_sub = store.latest.sub or {}
    latest_bits = store.latest.bits or {}

    recent_follows = store.recent.follows[-10:][::-1]
    recent_subs = store.recent.subs[-10:][::-1]
    recent_cheers = store.recent.cheers[-10:][::-1]

    follow_rows = "\n".join(
        _row([f"{f.get('user_name') or f.get('user_login') or '—'}",
              _fmt_time(f.get('followed_at'))])
        for f in recent_follows
    ) or _row(["—", "—"])

    sub_rows = "\n".join(
        _row([f"{x.get('user_name') or '—'}",
              f"T{int(x.get('tier', '1000'))//1000}",
              "Yes" if x.get('is_gift') else "No"])
        for x in recent_subs
    ) or _row(["—", "—", "—"])

    cheer_rows = "\n".join(
        _row([f"{x.get('user_name') or 'Anonymous'}",
              str(x.get('bits', 0)),
              (x.get('message') or "—")[:60]])
        for x in recent_cheers
    ) or _row(["—", "—", "—"])

    html = f"""<!doctype html>
<html data-theme="" lang="en">
<head>
  <meta charset="utf-8" />
  <title>Overlay Stats</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    :root {{
      --bg: #0b1020;
      --bg-soft: #131a2b;
      --text: #e5e7eb;
      --muted: #9aa3b2;
      --card: #0f1629;
      --border: #23304a;
      --primary: #7c3aed;
      --accent: #22d3ee;
      --good: #10b981;
      --warn: #f59e0b;
      --bad: #ef4444;
    }}
    :root.light {{
      --bg: #f6f7fb;
      --bg-soft: #eef1f7;
      --text: #0f172a;
      --muted: #475569;
      --card: #ffffff;
      --border: #e5e7eb;
      --primary: #6d28d9;
      --accent: #0891b2;
      --good: #059669;
      --warn: #b45309;
      --bad: #dc2626;
    }}
    * {{ box-sizing: border-box; }}
    html, body {{ margin:0; padding:0; background: var(--bg); color: var(--text); font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI; }}
    .wrap {{ max-width: 1100px; margin: 24px auto; padding: 0 16px; }}
    header {{ display:flex; align-items:center; justify-content:space-between; gap:16px; margin-bottom: 20px; }}
    .title {{ font-size: 28px; font-weight: 800; letter-spacing: .3px; }}
    .right {{ display:flex; align-items:center; gap:12px; flex-wrap:wrap; }}
    .chip {{ padding:6px 10px; border-radius: 999px; background: var(--bg-soft); border:1px solid var(--border); color: var(--muted); font-size: 12px; }}
    .btn {{ padding:8px 12px; border-radius: 10px; background: var(--primary); color:#fff; border:0; cursor:pointer; font-weight:700; text-decoration:none; display:inline-block; }}
    .btn.secondary {{ background: transparent; color: var(--text); border:1px solid var(--border); }}
    .grid {{ display:grid; grid-template-columns: repeat(3, 1fr); gap:16px; }}
    .card {{ background: var(--card); border:1px solid var(--border); border-radius: 14px; padding:16px; }}
    .card h3 {{ margin: 0 0 8px 0; font-size: 14px; letter-spacing:.5px; text-transform: uppercase; color: var(--muted); }}
    .big {{ font-size: 32px; font-weight: 800; }}
    .sub {{ color: var(--muted); font-size: 12px; }}
    .row {{ display:grid; grid-template-columns: 1fr 1fr; gap:16px; margin-top: 16px; }}
    .table {{ width:100%; border-collapse: collapse; font-size: 14px; }}
    .table th, .table td {{ text-align:left; padding:10px 8px; border-bottom:1px solid var(--border); }}
    .table th {{ color: var(--muted); font-weight:700; text-transform: uppercase; font-size:12px; letter-spacing:.4px; }}
    .mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
    .good {{ color: var(--good); font-weight: 700; }}
    .warn {{ color: var(--warn); font-weight: 700; }}
    .bad {{ color: var(--bad); font-weight: 700; }}
    .dot {{ display:inline-block; width:10px; height:10px; border-radius:6px; margin-right:6px; vertical-align:middle; background: var(--warn); }}
    @media (max-width: 900px) {{
      .grid {{ grid-template-columns: 1fr; }}
      .row {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <div class="title">Overlay Stats</div>
      <div class="right">
        <span class="chip">Channel: <b>{(s.broadcaster_login or '—')}</b></span>
        <span id="wsBadge" class="chip">Status: checking…</span>
        <button id="themeBtn" class="btn secondary" type="button">Toggle dark / light</button>
        <a class="btn" href="/admin">Admin</a>
      </div>
    </header>

    <section class="grid">
      <div class="card">
        <h3>Total Bits</h3>
        <div class="big">{store.stats.total_bits}</div>
        <div class="sub">Cumulative bits since this store was created.</div>
      </div>
      <div class="card">
        <h3>Latest Follow</h3>
        <div class="big">{(latest_follow.get('user_name') or latest_follow.get('user_login') or '—')}</div>
        <div class="sub">{_fmt_time(latest_follow.get('followed_at'))}</div>
      </div>
      <div class="card">
        <h3>Latest Sub</h3>
        <div class="big">{(latest_sub.get('user_name') or '—')}</div>
        <div class="sub">Tier: {('T' + str(int(latest_sub.get('tier','1000'))//1000)) if latest_sub else '—'} | Gift: {('Yes' if latest_sub.get('is_gift') else 'No') if latest_sub else '—'}</div>
      </div>
    </section>

    <section class="row">
      <div class="card">
        <h3>Subscriptions (EventSub)</h3>
        <p class="sub">WebSocket session & topic status, updated live every few seconds.</p>
        <table class="table">
          <tbody>
            <tr><th>Session ID</th><td class="mono" id="st_session">—</td></tr>
            <tr><th>Connected Since</th><td id="st_since">—</td></tr>
            <tr><th>Last Error</th><td id="st_error" class="mono">—</td></tr>
            <tr><th>Backoff</th><td id="st_backoff">—</td></tr>
            <tr><th>channel.follow</th><td id="st_follow"><span class="dot" id="dot_follow"></span><span id="txt_follow">checking…</span></td></tr>
            <tr><th>channel.subscribe</th><td id="st_subscribe"><span class="dot" id="dot_subscribe"></span><span id="txt_subscribe">checking…</span></td></tr>
            <tr><th>channel.cheer</th><td id="st_cheer"><span class="dot" id="dot_cheer"></span><span id="txt_cheer">checking…</span></td></tr>
            <tr><th>channel.raid</th><td id="st_raid"><span class="dot" id="dot_raid"></span><span id="txt_raid">checking…</span></td></tr>
          </tbody>
        </table>
      </div>
      <div class="card">
        <h3>Recent Follows</h3>
        <table class="table">
          <thead><tr><th>User</th><th>When</th></tr></thead>
          <tbody>
            {follow_rows}
          </tbody>
        </table>
      </div>
    </section>

    <section class="row">
      <div class="card">
        <h3>Recent Subs</h3>
        <table class="table">
          <thead><tr><th>User</th><th>Tier</th><th>Gift</th></tr></thead>
          <tbody>
            {sub_rows}
          </tbody>
        </table>
      </div>
      <div class="card">
        <h3>Recent Cheers</h3>
        <table class="table">
          <thead><tr><th>User</th><th>Bits</th><th>Message</th></tr></thead>
          <tbody>
            {cheer_rows}
          </tbody>
        </table>
      </div>
    </section>
  </div>

  <script>
    // Theme toggle
    (function() {{
      const key = "overlay_stats_theme";
      function apply(theme) {{
        if (theme === "light") {{
          document.documentElement.classList.add("light");
        }} else {{
          document.documentElement.classList.remove("light");
        }}
      }}
      const saved = localStorage.getItem(key) || "dark";
      apply(saved);
      document.getElementById("themeBtn").addEventListener("click", function() {{
        const now = document.documentElement.classList.contains("light") ? "dark" : "light";
        apply(now);
        localStorage.setItem(key, now);
      }});
    }})();

    // Live status poller
    (function() {{
      const badge = document.getElementById('wsBadge');
      const stSession = document.getElementById('st_session');
      const stSince = document.getElementById('st_since');
      const stError = document.getElementById('st_error');
      const stBackoff = document.getElementById('st_backoff');
      const dotFollow = document.getElementById('dot_follow');
      const dotSub = document.getElementById('dot_subscribe');
      const dotCheer = document.getElementById('dot_cheer');
      const dotRaid = document.getElementById('dot_raid');
      const txtFollow = document.getElementById('txt_follow');
      const txtSub = document.getElementById('txt_subscribe');
      const txtCheer = document.getElementById('txt_cheer');
      const txtRaid = document.getElementById('txt_raid');

      function setDot(el, ok) {{
        el.style.background = ok ? "var(--good)" : "var(--warn)";
      }}
      function fmtTime(ts) {{
        if (!ts || ts <= 0) return "—";
        try {{
          const d = new Date(ts * 1000);
          return d.toLocaleString();
        }} catch (e) {{ return "—"; }}
      }}

      async function refresh() {{
        try {{
          const r = await fetch('/status', {{ cache: 'no-store' }});
          const s = await r.json();

          if (s.connected) {{
            badge.textContent = 'Status: Connected';
            badge.style.color = 'var(--good)';
          }} else {{
            const b = s.backoff_s ? ` (retry in ~${{s.backoff_s}}s)` : '';
            badge.textContent = 'Status: Reconnecting' + b;
            badge.style.color = 'var(--warn)';
          }}

          stSession.textContent = s.session_id || '—';
          stSince.textContent = fmtTime(s.since);
          stError.textContent = s.last_error || '—';
          stBackoff.textContent = s.backoff_s ? (s.backoff_s + 's') : '—';

          const subs = s.subs || {{}};
          setDot(dotFollow, !!subs.follow); txtFollow.textContent = subs.follow ? 'subscribed' : 'pending';
          setDot(dotSub, !!subs.subscribe); txtSub.textContent = subs.subscribe ? 'subscribed' : 'pending';
          setDot(dotCheer, !!subs.cheer); txtCheer.textContent = subs.cheer ? 'subscribed' : 'pending';
          setDot(dotRaid, !!subs.raid); txtRaid.textContent = subs.raid ? 'subscribed' : 'pending';
        }} catch {{
          badge.textContent = 'Status: Unknown';
          badge.style.color = 'var(--warn)';
        }}
      }}
      refresh();
      setInterval(refresh, 3000);
    }})();
  </script>
</body>
</html>"""
    return html
