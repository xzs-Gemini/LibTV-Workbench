import argparse
import json
import mimetypes
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from .core import DEFAULT_PROJECT, ROOT, Queue, redact


def serve(port=5212, open_browser=False):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def reply(self, value, status=200):
            data = json.dumps(value, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers(); self.wfile.write(data)

        def local(self):
            allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
            if self.headers.get("Host") not in allowed:
                self.reply({"error": "仅允许本机访问"}, 403); return False
            origin = self.headers.get("Origin")
            if origin and origin not in {"http://" + h for h in allowed}:
                self.reply({"error": "拒绝跨站请求"}, 403); return False
            return True

        def do_GET(self):
            if not self.local(): return
            url = urlparse(self.path); query = parse_qs(url.query)
            try:
                if url.path == "/api/state":
                    self.reply({"jobs": queue.jobs(), "defaultProject": DEFAULT_PROJECT, "paused": queue.paused_file.exists()}); return
                if url.path == "/api/projects":
                    data = queue.cli.call("project", "list")
                    self.reply([{"id": p["uuid"], "name": p["name"]} for p in data.get("projectMetaList", [])]); return
                if url.path == "/api/models":
                    kind = query.get("kind", ["image"])[0]
                    if kind not in ("image", "video"): raise ValueError("类型无效")
                    self.reply(queue.cli.call("model", "search", "-t", kind).get("matches", [])); return
                if url.path == "/api/schema":
                    self.reply(queue.cli.call("model", query.get("name", [""])[0])); return
                if url.path.startswith("/outputs/"):
                    root = (queue.directory / "outputs").resolve()
                    path = (root / unquote(url.path[len("/outputs/"):])).resolve()
                else:
                    root = (ROOT / "workbench/web").resolve()
                    path = (root / (unquote(url.path).lstrip("/") or "index.html")).resolve()
                if not path.is_relative_to(root) or not path.is_file():
                    self.reply({"error": "文件不存在"}, 404); return
                self.send_response(200)
                self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
                self.send_header("Content-Length", str(path.stat().st_size))
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; media-src 'self'; style-src 'self'; script-src 'self'; frame-ancestors 'none'")
                self.end_headers()
                with path.open("rb") as file:
                    while chunk := file.read(1024 * 1024): self.wfile.write(chunk)
            except Exception as exc:
                self.reply({"error": redact(exc)}, 400)

        def do_POST(self):
            if not self.local(): return
            try:
                if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    raise ValueError("需要 JSON 请求")
                length = int(self.headers.get("Content-Length", 0))
                if not 0 < length <= 250000: raise ValueError("请求过大或为空")
                body = json.loads(self.rfile.read(length))
                if self.path == "/api/jobs": self.reply(queue.add(body), 201)
                elif self.path == "/api/resume":
                    queue.paused_file.unlink(missing_ok=True)
                    self.reply({"paused": False})
                elif self.path == "/api/cancel": self.reply(queue.cancel(body["id"]))
                elif self.path == "/api/check": self.reply(queue.reconcile(body["id"]))
                else: self.reply({"error": "接口不存在"}, 404)
            except Exception as exc:
                self.reply({"error": redact(exc)}, 400)

    # Bind first: a second app instance must not start a competing worker.
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    queue = Queue()
    threading.Thread(target=queue.run, daemon=True).start()
    print(f"LibTV Workbench: http://127.0.0.1:{port}", flush=True)
    if open_browser: webbrowser.open(f"http://127.0.0.1:{port}")
    try: server.serve_forever()
    finally: queue.stop.set(); server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5212)
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args()
    serve(args.port, args.open)
