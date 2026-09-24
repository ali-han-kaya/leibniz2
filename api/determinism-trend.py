"""Vercel /api/determinism-trend — git'te yaşayan GERÇEK trend-verisi.

Yerel serve_determinism_trend birebir: determinism_trend_badge ile aynı
badge-yardımcıları; dosya docs/determinism_trend/determinism_trend.jsonl
repo'da yaşadığı için Vercel-checkout'unda gerçek-değerli çalışır
(bot'un haftalık-commitlediği tek canlı-veri kaynağı).
"""
from http.server import BaseHTTPRequestHandler

import os
import sys

# Köprü: api/ sys.path'de değil (handler dosya-yolundan exec edilir); gerçek
# bootstrap api/_adapter.py'de (tek-kaynak — burada çoğaltılmaz).
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from _adapter import api_determinism_trend  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        resp = api_determinism_trend()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(resp["body"].encode("utf-8"))

    def do_POST(self):
        self.send_response(405)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(b'{"error":"method not allowed"}')
