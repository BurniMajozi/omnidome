"""Tiny authenticated admin sidecar. Asterisk's ARI has no config reload, and AMI must never be exposed,
so the call-center service calls this instead. It can do exactly two things:

  POST /reload         reload PJSIP + dialplan from the shared generated/ directory
  GET  /registrations  `pjsip list registrations` output (no secrets in it)
  GET  /health         unauthenticated liveness

Auth: `Authorization: Bearer $ASTERISK_ADMIN_TOKEN` (constant-time compare). Fails closed: refuses to
start without a token. No arbitrary command execution: argv lists are fixed here, no shell.
Listens on the container network only (never publish port 8099).
"""
import hmac
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOKEN = os.environ.get("ASTERISK_ADMIN_TOKEN", "")
if len(TOKEN) < 32:
    sys.stderr.write("admin sidecar: ASTERISK_ADMIN_TOKEN missing or too short; not starting\n")
    sys.exit(78)

RELOAD_CMDS = (
    "module reload res_pjsip.so",
    "module reload res_pjsip_outbound_registration.so",
    "module reload res_pjsip_endpoint_identifier_ip.so",
    "dialplan reload",
)
_lock = threading.Lock()


def cli(command):
    out = subprocess.run(["asterisk", "-rx", command], capture_output=True, text=True, timeout=20, check=False)
    return out.stdout


class Handler(BaseHTTPRequestHandler):
    server_version = "omni-admin"

    def log_message(self, fmt, *args):  # never log request lines (no tokens/paths of interest)
        return

    def _send(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authed(self):
        got = self.headers.get("Authorization", "")
        return got.startswith("Bearer ") and hmac.compare_digest(got[7:].encode(), TOKEN.encode())

    def do_GET(self):
        if self.path == "/health":
            return self._send(200, {"ok": True})
        if not self._authed():
            return self._send(401, {"error": "unauthorized"})
        if self.path == "/registrations":
            lines = [ln[:300] for ln in cli("pjsip list registrations").splitlines() if ln.strip()][:200]
            return self._send(200, {"lines": lines})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self._authed():
            return self._send(401, {"error": "unauthorized"})
        if self.path == "/reload":
            with _lock:
                for cmd in RELOAD_CMDS:
                    cli(cmd)
            return self._send(200, {"ok": True})
        self._send(404, {"error": "not found"})


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8099), Handler).serve_forever()
