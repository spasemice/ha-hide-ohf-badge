"""Read-only status through authenticated Home Assistant ingress."""
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from urllib.parse import quote

TRUSTED_HOSTS = frozenset({"172.30.32.2", "127.0.0.1", "::1"})


def render(report, settings):
    success = report["state"] == "ok"
    title = "Logos removed" if success else (
        "Attention needed" if report["state"] == "error" else "Waiting for Home Assistant")
    message = ("Completed successfully. Both SVG images are verified blank." if success else
               report.get("error", report.get("reason", "The startup check is in progress.")))
    mode = ("Sleeping · waiting for the next Core start" if report.get("listener") == "connected"
            else "Reconnecting to start notifications")
    if report.get("listener_error"):
        mode += ": " + report["listener_error"]
    trigger = {"core_start": "Home Assistant Core started", "app_start": "App started",
               "listener_connected": "Startup / event connection restored"}.get(report.get("trigger"), "Waiting")
    def setting(key, expected):
        value = settings.get(key)
        if value is None:
            return "Unknown · check the Info tab"
        current = "On" if value in (True, "auto") else "Off"
        return current + (" ✓" if value == expected else " · change in Info")
    values = {"color": "good" if success else "bad", "symbol": "✓" if success else "!",
              "title": title, "message": message, "mode": mode, "trigger": trigger,
              "checked": report.get("checked_at", "Not checked yet"),
              "count": str(report.get("check_count", 0)), "boot": setting("boot", "auto"),
              "watchdog": setting("watchdog", True), "protection": setting("protected", False),
              "image": report.get("image", "Waiting for a check"),
              "back_href": ("/config/app/" + quote(settings["slug"], safe="") + "/info"
                            if settings.get("slug") else "/config/apps")}
    template = '''<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hide OHF Badge — status</title><style>
:root{color-scheme:light dark;--paper:#f6f9fb;--surface:#fff;--ink:#163243;--muted:#536b7b;--line:#dbe5eb;--accent:#007f98;--good:#166749;--bad:#a63d24}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.55 "Segoe UI",Roboto,Arial,sans-serif}
main{max-width:850px;margin:auto;padding:40px 24px}header{display:flex;align-items:center;justify-content:space-between;gap:20px;margin-bottom:30px}
header p{margin:0;color:var(--muted)}h1{font-size:21px;font-weight:600;margin:0}h2{font-size:29px;line-height:1.2;margin:12px 0}h3{font-size:19px;margin:28px 0 12px}
a{color:var(--accent)}a.back{display:inline-block;margin-bottom:20px;text-decoration:none}a.refresh{display:inline-block;padding:9px 16px;border:1px solid var(--accent);border-radius:24px;text-decoration:none;white-space:nowrap}
a:focus-visible{outline:3px solid var(--accent);outline-offset:4px}.result{background:var(--surface);border:1px solid var(--line);border-left:5px solid var(--result);border-radius:8px;padding:22px 26px}
.check{color:var(--result);font-size:26px}.result p{margin:8px 0;color:var(--muted)}.mode{display:block;margin-top:20px;color:var(--ink);font-weight:600}
dl{display:grid;grid-template-columns:minmax(160px,1fr) 2fr;gap:0;margin:0}dt,dd{padding:12px 0;border-bottom:1px solid var(--line)}dt{color:var(--muted)}dd{margin:0;overflow-wrap:anywhere}
.note{color:var(--muted);font-size:14px;margin:24px 0 0}details{margin-top:22px}summary{cursor:pointer;color:var(--accent)}code{font-size:13px;overflow-wrap:anywhere}
@media(prefers-color-scheme:dark){:root{--paper:#111f29;--surface:#1c2c37;--ink:#e1edf3;--muted:#b3c5d0;--line:#354956;--accent:#79d4e4;--good:#8ad7af;--bad:#ffb199}}
@media(max-width:520px){main{padding:24px 16px}header{align-items:flex-start;gap:10px}h1{font-size:18px}h2{font-size:25px}.result{padding:18px}dl{grid-template-columns:1fr}dt{border-bottom:0;padding-bottom:0}dd{padding-top:3px}}
</style><main><a class="back" href="{{back_href}}" target="_top">← Back to app</a><header><div><h1>Hide OHF Badge</h1><p>Status and settings · 1.1.2</p></div><a class="refresh" href="./">Refresh status</a></header>
<section class="result" style="--result:var(--{{color}})"><span class="check" aria-hidden="true">{{symbol}}</span><h2>{{title}}</h2><p>{{message}}</p><span class="mode">{{mode}}</span></section>
<h3>Last check</h3><dl><dt>Time</dt><dd><time datetime="{{checked}}">{{checked}}</time></dd>
<dt>Trigger</dt><dd>{{trigger}}</dd><dt>Checks since app start</dt><dd>{{count}}</dd><dt>Periodic SVG checks</dt><dd>Disabled · no timer</dd></dl>
<h3>Settings in Info</h3><dl><dt>Start on boot</dt><dd>{{boot}}</dd><dt>Watchdog</dt><dd>{{watchdog}}</dd><dt>Protection mode</dt><dd>{{protection}}</dd></dl>
<p class="note">Watchdog checks app availability. It never checks or rewrites SVG files. This page updates only when you select Refresh status.</p>
<details><summary>Restore default logos</summary><p>Stop this app and disable Start on boot, or uninstall it. The next Home Assistant Core update will automatically restore the original logos. Stopping or uninstalling does not restore them immediately.</p></details>
<details><summary>Backups and Core version</summary><p>Original images are saved in your Home Assistant configuration folder:<br><code>branding-backups/automatic/</code></p><p><code>{{image}}</code></p></details>
<script>for(const t of document.querySelectorAll('time[datetime]')){const d=new Date(t.dateTime);if(!isNaN(d))t.textContent=d.toLocaleString('en-GB');}</script>
</main></html>'''
    # One-pass substitution: values cannot introduce other template tokens.
    import re
    return re.sub(r"\{\{(\w+)\}\}", lambda match: escape(values[match[1]]), template)


class StatusServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, app, supervisor, worker, address=("0.0.0.0", 8099)):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_GET(self):
                if self.client_address[0] not in TRUSTED_HOSTS:
                    self.send_error(403)
                    return
                path = self.path.split("?", 1)[0]
                if path == "/health":
                    # No Docker/Core/SVG calls on health requests.
                    healthy = worker.is_alive() and not app.stop.is_set()
                    self.reply(200 if healthy else 503, b"ok" if healthy else b"listener stopped", "text/plain")
                elif path in ("/", "/status.json"):
                    report = app.snapshot()
                    if path == "/status.json":
                        self.reply(200, json.dumps(report).encode(), "application/json")
                    else:
                        try:
                            settings = supervisor.request("GET")
                        except Exception:
                            settings = {}
                        self.reply(200, render(report, settings).encode("utf-8"), "text/html; charset=utf-8")
                else:
                    self.send_error(404)

            def reply(self, code, body, content_type):
                self.send_response(code)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)

        super().__init__(address, Handler)

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(10)
        return connection, address
