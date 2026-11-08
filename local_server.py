#!/usr/bin/env python3
"""Optional standard-library local HTTP server and same-origin Ollama bridge."""
from __future__ import annotations
import ipaddress
import json
import urllib.error
import urllib.parse
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HOST, PORT = '127.0.0.1', 8765
MAX_BODY = 36 * 1024 * 1024
ENDPOINTS = {'tags': 'GET', 'show': 'POST', 'chat': 'POST'}


def ollama_endpoint(raw):
    u = urllib.parse.urlsplit(raw)
    if u.scheme != 'http' or not u.hostname or not u.port or u.username or u.password or u.path not in ('', '/') or u.query or u.fragment:
        raise ValueError('Expected a private Ollama host, e.g. http://127.0.0.1:11434')
    host = u.hostname.lower()
    if host == 'localhost':
        return f'http://localhost:{u.port}'
    try:
        ip = ipaddress.ip_address(host)
    except ValueError as exc:
        if host.endswith('.local'):
            return f'http://{host}:{u.port}'
        raise ValueError('Only localhost, private LAN IPs and .local hosts are allowed') from exc
    if not (ip.is_loopback or ip.is_private):
        raise ValueError('Public Ollama hosts are not allowed by the local bridge')
    return f'http://{host}:{u.port}'


class App(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self):
        if self.path.startswith('/bridge/'):
            self.proxy('GET')
        else:
            super().do_GET()

    def do_POST(self):
        if self.path.startswith('/bridge/'):
            self.proxy('POST')
        else:
            self.error_json(404, 'Not found')

    def error_json(self, status, message):
        blob = json.dumps({'error': message}).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(blob)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(blob)

    def proxy(self, method):
        endpoint = urllib.parse.urlsplit(self.path).path.removeprefix('/bridge/')
        if ENDPOINTS.get(endpoint) != method:
            return self.error_json(404, 'Unsupported route')
        try:
            base = ollama_endpoint(self.headers.get('X-Ollama-Endpoint', 'http://127.0.0.1:11434'))
            size = int(self.headers.get('Content-Length', '0')) if method == 'POST' else 0
            if size < 0 or size > MAX_BODY:
                return self.error_json(413, 'Request exceeds size limit')
            body = self.rfile.read(size) if method == 'POST' else None
            request = urllib.request.Request(f'{base}/api/{endpoint}', method=method, data=body, headers={'Content-Type': 'application/json'})
            try:
                with urllib.request.urlopen(request, timeout=360) as response:
                    status, content = response.status, response.read(MAX_BODY)
            except urllib.error.HTTPError as err:
                status, content = err.code, err.read(2048)
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(content)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(content)
        except (ValueError, OSError, TimeoutError, urllib.error.URLError) as exc:
            self.error_json(502, str(exc))


if __name__ == '__main__':
    app = ThreadingHTTPServer((HOST, PORT), App)
    print(f'Bucket Studio v2.0: http://{HOST}:{PORT}/index.html', flush=True)
    print('Press Ctrl+C to stop.', flush=True)
    try:
        import webbrowser
        import threading
        opener = threading.Thread(target=lambda: webbrowser.open(f'http://{HOST}:{PORT}/index.html'), daemon=True)
        opener.start()
        app.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.server_close()
