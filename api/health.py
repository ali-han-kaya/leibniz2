"""Vercel /api/health — yerel /api/health birebir: 200 "ok" düz-metin.

2026 dosya-tabanlı Python-handler sözleşmesi (vercel.com/docs/functions/
runtimes/python/api-directory): her api/*.py ayrı fonksiyon; dosya
top-level `handler` adını, BaseHTTPRequestHandler-alt-sınıfı olarak
tanımlar. Method-gating: GET dışı → 405 (yerel _reject_method kardeşi).
"""
from http.server import BaseHTTPRequestHandler


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"ok")

    def _reject(self):
        self.send_response(405)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(b'{"error":"method not allowed"}')

    def do_POST(self):
        self._reject()

    def do_HEAD(self):
        self._reject()
