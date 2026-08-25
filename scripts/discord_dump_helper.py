"""本机收 Discord 页推过来的职位批次，并提供 scrape.js / 心跳。不删已有 dump。"""

from __future__ import annotations

import json
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path("/Users/cuijian/opc-x/Scraper")
DUMP = Path("/tmp/discord_thread_dump.jsonl")
HEART = Path("/tmp/discord_scrape_heartbeat.json")
JS = ROOT / "scripts" / "discord_unattended_scrape.js"
DUMP.parent.mkdir(parents=True, exist_ok=True)
if not DUMP.exists():
    DUMP.touch()

_offset_hint = 0


def _count_offset() -> int:
    ids: set[str] = set()
    try:
        for line in DUMP.read_text().splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict) or row.get("type") != "jobs":
                continue
            for item in row.get("batch") or []:
                tid = str((item or {}).get("threadId") or "")
                if tid:
                    ids.add(tid)
    except OSError:
        return 0
    return len(ids)


_offset_hint = _count_offset()


class H(SimpleHTTPRequestHandler):
    def log_message(self, *args):  # noqa: ARG002
        pass

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        global _offset_hint
        if self.path.startswith("/health"):
            body = b"ok"
        elif self.path.startswith("/status"):
            body = json.dumps({"offsetHint": _offset_hint, "ok": True}).encode()
        elif self.path.startswith("/heartbeat"):
            body = HEART.read_bytes() if HEART.exists() else b"{}"
        elif self.path.startswith("/scrape.js"):
            body = JS.read_bytes()
        else:
            self.send_response(404)
            self._cors()
            self.end_headers()
            return
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "application/json" if not self.path.startswith("/scrape") else "text/javascript")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        global _offset_hint
        n = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(n)
        if self.path.startswith("/heartbeat"):
            HEART.write_bytes(raw)
        else:
            DUMP.open("ab").write(raw + b"\n")
            try:
                row = json.loads(raw)
                batch = row.get("batch") if isinstance(row, dict) else None
                if isinstance(batch, list):
                    _offset_hint += len(batch)
            except json.JSONDecodeError:
                pass
        self.send_response(200)
        self._cors()
        self.end_headers()
        self.wfile.write(b"ok")


if __name__ == "__main__":
    httpd = ThreadingHTTPServer(("127.0.0.1", 8766), H)
    print(f"helper offset={_offset_hint}", flush=True)
    httpd.serve_forever()
