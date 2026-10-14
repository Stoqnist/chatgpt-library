"""Inert Agency BFF staging shell: no authentication or provider capabilities.

This process is intentionally NOT the real Agency login or consent UI.
Until a separately reviewed OIDC implementation exists, every application
endpoint fails closed. Only a process-liveness probe answers successfully.
No secrets, sessions, HTTP clients, redirects, event writes or debug console.
"""
from __future__ import annotations

import json
import os
from wsgiref.simple_server import WSGIRequestHandler, make_server


def application(environ, start_response):
    """Minimal WSGI surface, never interprets caller-supplied auth headers."""
    path = environ.get("PATH_INFO", "")
    method = environ.get("REQUEST_METHOD", "")
    health = path == "/_internal/live" and method in ("GET", "HEAD")

    if health:
        status = "200 OK"
        result = {"status": "process_alive", "authentication_ready": False,
                  "calendar_writes_enabled": False}
    else:
        status = "503 Service Unavailable"
        result = {"status": "unavailable",
                  "reason": "authenticated_bff_not_implemented"}
    body = json.dumps(result, sort_keys=True, separators=(",", ":")).encode("utf-8")
    headers = [
        ("Content-Type", "application/json; charset=utf-8"),
        ("Content-Length", str(len(body) if method != "HEAD" else 0)),
        ("Cache-Control", "no-store, max-age=0"),
        ("Pragma", "no-cache"),
        ("X-Content-Type-Options", "nosniff"),
        ("X-Frame-Options", "DENY"),
        ("Referrer-Policy", "no-referrer"),
        ("Content-Security-Policy",
         "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"),
    ]
    start_response(status, headers)
    return [b"" if method == "HEAD" else body]


class _NoAccessLog(WSGIRequestHandler):
    """Do not record HTTP paths, query strings or potential credentials."""

    def log_message(self, format, *args):
        pass


def main():
    # The Docker namespace uses 0.0.0.0 but only a loopback-host port mapping.
    # Direct host execution defaults to loopback. NEVER use this as public UI.
    bind = os.environ.get("AGENCY_BFF_BIND", "127.0.0.1")
    port = int(os.environ.get("AGENCY_BFF_PORT", "8000"))
    if bind not in ("127.0.0.1", "0.0.0.0") or not 1024 <= port <= 65535:
        raise ValueError("unsupported staging listener")
    from .bff_http import configured_application
    with make_server(bind, port, configured_application(), handler_class=_NoAccessLog) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
