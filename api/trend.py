"""Vercel /api/trend — yerel serve_trend birebir: {history, refs_trend}.

Handler BaseHTTPRequestHandler (Vercel 2026 dosya-tabanlı sözleşme).
Gövde paylaşımlı adaptörde: api/_adapter.py (tek-kaynak import'lar).
"""
from http.server import BaseHTTPRequestHandler

import os
import sys

# Köprü: api/ sys.path'de değil (handler dosya-yolundan exec edilir); gerçek
# bootstrap api/_adapter.py'de (tek-kaynak — burada çoğaltılmaz).
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from _adapter import jresp, api_trend  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        body = api_trend()["body"].encode("utf-8")
        self.wfile.write(body)

    def do_POST(self):
        self.send_response(405)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(b'{"error":"method not allowed"}')
