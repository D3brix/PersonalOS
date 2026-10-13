"""Local web interface. Standard library only; no external assets; nothing is loaded from the internet.

Security model (loopback is not authentication, so every request is checked):
* binds to 127.0.0.1 only (hard-coded);
* Host header allow-list on every request (defeats DNS rebinding);
* every API call needs the per-launch token in the X-PersonalOS-Token header. Browsers cannot attach a custom
  header cross-origin without a CORS preflight, which this server never approves, so this also blocks CSRF;
* writes additionally require JSON, a same-origin Origin/Sec-Fetch-Site, a size cap, and `confirm: true` in the
  body for settings changes;
* strict CSP, nosniff, no-referrer, no-store; errors never expose internals.
"""
import hmac
import json
import mimetypes
import secrets
import sys
import threading
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .. import __version__, config, health, index, logs, maintain, vault
from ..integrations import all_integrations, get as get_integration
from ..sources import LABEL_HELP

HOST = "127.0.0.1"
STATIC = Path(__file__).resolve().parent / "static"
MAX_BODY = 64 * 1024
CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; "
       "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def _summary(cfg):
    st = index.stats(cfg)
    return {
        "version": __version__, "vault": str(cfg.vault), "data_dir": str(cfg.data_dir),
        "archive_dir": cfg.data.get("archive_dir"), "archive_root": str(cfg.archive_root),
        "mode": "SSD + archive drive" if cfg.data.get("archive_dir") else "single drive",
        "last_index": st["last_index"], "files": sum(g["files"] for g in st["groups"]),
        "groups": st["groups"], "inbox": len(vault.list_notes(cfg, "inbox")),
        "folders": cfg.data["folders"],
    }


def _settings_view(cfg):
    keep = ("vault", "data_dir", "archive_dir", "folders", "search", "maintenance", "privacy", "ui",
            "extra_sources")
    return {"config_file": str(cfg.path), **{k: cfg.data[k] for k in keep}}


class App:
    def __init__(self, cfg_path, token):
        self.cfg_path = cfg_path
        self.token = token
        self.lock = threading.Lock()  # one indexing/maintenance operation at a time from the UI

    def cfg(self):
        return config.load(self.cfg_path)

    # ---- GET
    def get(self, route, q):
        cfg = self.cfg()
        one = lambda k, d="": (q.get(k) or [d])[0]  # noqa: E731
        if route == "/api/status":
            return _summary(cfg)
        if route == "/api/search":
            text = one("q").strip()
            if not text:
                return {"tier1": [], "tier2": [], "tier2_searched": False, "mode": "AND"}
            kinds = [k for k in one("kind").split(",") if k] or None
            res = index.search(cfg, text[:500], int(one("n", "10")), one("all") == "1", kinds)
            logs.usage(cfg, {"q": text, "hits": [h["path"] for h in (res["tier1"] + res["tier2"])[:3]]})
            for h in res["tier1"] + res["tier2"]:
                h["rel"] = self._rel(cfg, h["path"])
            return {**res, "labels": LABEL_HELP}
        if route == "/api/show":
            try:
                r = index.show(cfg, one("path"), one("loc") or None, 40000)
            except index.NotIndexed as e:
                raise ApiError(404, str(e)) from None
            logs.usage(cfg, {"show": r["path"], "loc": one("loc")})
            return {**r, "rel": self._rel(cfg, r["path"])}
        if route == "/api/tree":
            return vault.tree(cfg, one("rel"))
        if route == "/api/note":
            return vault.read_note(cfg, one("rel"))
        if route == "/api/resolve":
            return {"rel": vault.find_note(cfg, one("name"))}
        if route == "/api/inbox":
            return {"notes": vault.list_notes(cfg, "inbox"), "folder": cfg.data["folders"]["inbox"]}
        if route == "/api/projects":
            return {"groups": vault.projects(cfg)}
        if route == "/api/goals":
            rel = f"{cfg.data['folders']['system']}/Goals.md"
            try:
                return vault.read_note(cfg, rel)
            except vault.VaultError:
                return {"rel": rel, "text": "", "missing": True}
        if route == "/api/archive":
            out = {"notes": vault.list_notes(cfg, "archive"), "archive_root": str(cfg.archive_root),
                   "extra_sources": cfg.data["extra_sources"]}
            con, _ = index.open_db(cfg)
            out["tier2"] = [dict(r) for r in con.execute(
                "select kind, origin, count(*) files, sum(size) bytes from files where tier=2 group by kind, origin")]
            con.close()
            return out
        if route == "/api/reports":
            reps = maintain.list_reports(cfg)
            latest = reps[0].read_text(encoding="utf-8") if reps else ""
            return {"reports": [p.name for p in reps[:20]], "latest": latest, "ops": logs.recent_ops(cfg, 15)}
        if route == "/api/health":
            results, _ = health.checks(one("deep") == "1")
            return {"checks": results}
        if route == "/api/settings":
            return _settings_view(cfg)
        if route == "/api/integrations":
            out = []
            for integ in all_integrations():
                on = bool(cfg.integration(integ.NAME).get("enabled"))
                st = integ.status(cfg) if on else {}
                out.append({"name": integ.NAME, "description": integ.DESCRIPTION, "enabled": on, "status": st})
            return {"integrations": out}
        raise ApiError(404, "not found")

    # ---- POST
    def post(self, route, body):
        cfg = self.cfg()
        if route == "/api/capture":
            try:
                p = vault.capture(cfg, str(body.get("text", "")), body.get("title") or None, source="ui")
            except vault.VaultError as e:
                raise ApiError(400, str(e)) from None
            self._run_locked(lambda: index.run_index(cfg))
            return {"created": self._rel(cfg, str(p))}
        if route == "/api/index":
            rebuild = bool(body.get("rebuild"))
            if rebuild and body.get("confirm") is not True:
                raise ApiError(400, "rebuilding needs confirm: true")
            st, changed, errors = self._run_locked(lambda: index.run_index(cfg, rebuild))
            return {"stats": st, "changed": changed[:50], "errors": errors[:20]}
        if route == "/api/maintain":
            text, out = self._run_locked(lambda: maintain.run_maintain(cfg, bool(body.get("no_archive"))))
            return {"report": text, "file": out.name}
        if route == "/api/integrations":
            if body.get("confirm") is not True:
                raise ApiError(400, "changing an integration needs confirm: true")
            try:
                integ = get_integration(str(body.get("name")))
                msgs = integ.enable(cfg) if body.get("enabled") else integ.disable(cfg)
            except (KeyError, RuntimeError) as e:
                raise ApiError(400, str(e).strip("'\"")) from None
            return {"messages": msgs}
        if route == "/api/settings":
            if body.get("confirm") is not True:
                raise ApiError(400, "changing settings needs confirm: true")
            allowed = {("search", "limit"), ("maintenance", "stale_days"), ("maintenance", "promote_min_hits"),
                       ("privacy", "log_queries")}
            data = json.loads(json.dumps(cfg.data))
            for item in body.get("changes", []):
                key = tuple(str(item.get("key", "")).split("."))
                if key not in allowed:
                    raise ApiError(400, f"setting {'.'.join(key)} cannot be changed here")
                data[key[0]][key[1]] = item.get("value")
            if not isinstance(data["search"]["limit"], int) or not 1 <= data["search"]["limit"] <= 50:
                raise ApiError(400, "search.limit must be 1-50")
            for k in ("stale_days", "promote_min_hits"):
                if not isinstance(data["maintenance"][k], int) or data["maintenance"][k] < 1:
                    raise ApiError(400, f"maintenance.{k} must be a positive integer")
            if not isinstance(data["privacy"]["log_queries"], bool):
                raise ApiError(400, "privacy.log_queries must be true or false")
            cfg.data = data
            cfg.save()
            return _settings_view(cfg)
        raise ApiError(404, "not found")

    def _run_locked(self, fn):
        if not self.lock.acquire(blocking=False):
            raise ApiError(409, "another operation is running; try again in a moment")
        try:
            return fn()
        except index.IndexBusy as e:
            raise ApiError(409, str(e)) from None
        finally:
            self.lock.release()

    @staticmethod
    def _rel(cfg, path):
        try:
            return Path(path).resolve().relative_to(cfg.vault.resolve()).as_posix()
        except ValueError:
            return None


def make_handler(app, port):
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    allowed_origins = {f"http://{h}" for h in allowed_hosts}

    class Handler(BaseHTTPRequestHandler):
        server_version = "PersonalOS"
        sys_version = ""

        def log_message(self, fmt, *args):  # keep the console quiet; no request logging to disk
            pass

        def _headers(self, status, ctype, length):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(length))
            self.send_header("Content-Security-Policy", CSP)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()

        def _json(self, status, obj):
            data = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
            self._headers(status, "application/json; charset=utf-8", len(data))
            self.wfile.write(data)

        def _err(self, status, msg):
            self._json(status, {"error": msg})

        def _host_ok(self):
            return self.headers.get("Host", "") in allowed_hosts

        def _token_ok(self):
            return hmac.compare_digest(self.headers.get("X-PersonalOS-Token", ""), app.token)

        def _dispatch(self, method):
            if not self._host_ok():
                return self._err(403, "forbidden host")
            url = urlparse(self.path)
            route = url.path
            if not route.startswith("/api/"):
                if method != "GET":
                    return self._err(405, "method not allowed")
                return self._static(route)
            if not self._token_ok():
                return self._err(401, "missing or wrong session token; reopen the link printed by `personalos ui`")
            try:
                if method == "GET":
                    return self._json(200, app.get(route, parse_qs(url.query)))
                origin = self.headers.get("Origin")
                if origin is not None and origin not in allowed_origins:
                    return self._err(403, "cross-origin request refused")
                if self.headers.get("Sec-Fetch-Site", "same-origin") not in ("same-origin", "none"):
                    return self._err(403, "cross-site request refused")
                if not self.headers.get("Content-Type", "").startswith("application/json"):
                    return self._err(415, "JSON required")
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    return self._err(400, "bad Content-Length")
                if length > MAX_BODY:
                    self.rfile.read(min(length, MAX_BODY * 4))  # drain a little so Windows does not reset
                    return self._err(413, "request too large")
                try:
                    body = json.loads(self.rfile.read(length) or b"{}")
                except ValueError:
                    return self._err(400, "invalid JSON")
                if not isinstance(body, dict):
                    return self._err(400, "JSON object required")
                return self._json(200, app.post(route, body))
            except ApiError as e:
                return self._err(e.status, str(e))
            except vault.VaultError as e:
                return self._err(400, str(e))
            except config.ConfigError as e:
                return self._err(500, f"configuration problem: {e}")
            except Exception:
                traceback.print_exc(file=sys.stderr)
                return self._err(500, "internal error (details are in the terminal running `personalos ui`)")

        def _static(self, route):
            rel = "index.html" if route in ("/", "") else route.lstrip("/")
            p = (STATIC / rel).resolve()
            if STATIC not in p.parents or not p.is_file():
                return self._err(404, "not found")
            data = p.read_bytes()
            ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype in ("application/javascript", "image/svg+xml"):
                ctype += "; charset=utf-8"
            self._headers(200, ctype, len(data))
            self.wfile.write(data)

        def do_GET(self):
            self._dispatch("GET")

        def do_POST(self):
            self._dispatch("POST")

        def do_PUT(self):
            self._err(405, "method not allowed")

        do_DELETE = do_PATCH = do_PUT

        def do_OPTIONS(self):  # no CORS, ever
            self._err(405, "method not allowed")

    return Handler


def create_server(cfg, port=None, token=None):
    """Create (but do not start) the server. Tries up to 10 ports from the configured one; 0 = any free port."""
    token = token or secrets.token_urlsafe(32)
    app = App(cfg.path, token)
    start = cfg.data["ui"]["port"] if port is None else port
    last = None
    for p in ([0] if start == 0 else range(start, start + 10)):
        try:
            srv = ThreadingHTTPServer((HOST, p), None)
        except OSError as e:
            last = e
            continue
        actual = srv.server_address[1]
        srv.RequestHandlerClass = make_handler(app, actual)
        srv.daemon_threads = True
        return srv, actual, token
    raise OSError(f"no free port from {start} to {start + 9}: {last}")


def serve(cfg, port=None, open_browser=True):
    srv, actual, token = create_server(cfg, port)
    url = f"http://127.0.0.1:{actual}/#t={token}"
    print(f"PersonalOS is running at {url}", flush=True)
    print("This link contains a one-time session key; do not share it. Press Ctrl+C to stop.", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        srv.server_close()
