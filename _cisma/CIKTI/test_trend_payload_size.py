#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_trend_payload_size.py — /api/trend payload size guard.

Her /api/trend?limit=N isteği için payload boyutunu (bytes) ölçer ve
belgelendirilmiş byte bütçesini aşarsa commit'i bloke eder.

Kurallar:
  - limit=None (full-list)     → bütçe: 500 KB
  - limit=1..100              → bütçe: 50 KB × limit (lineer büyümelere karşı)
  - limit>100                 → bütçe: 5 KB × limit (katmanlı indirim)

Bu test, verify.yml merge pattern ↔ ARTIFACT_JOBS tutarlılık denetimiyle
uyumlu olması beklenir.
"""

import json
import os
import sys
import tempfile
import shutil
import unittest
import pathlib

# Add CIKTI dir to path (like other tests)
CIKTI = pathlib.Path(__file__).resolve().parent
if str(CIKTI) not in sys.path:
    sys.path.insert(0, str(CIKTI))

# Add api/ to path for _adapter import
API_DIR = os.path.join(str(CIKTI), '..', 'api')
if API_DIR not in sys.path:
    sys.path.insert(0, API_DIR)

import _calisma.CIKTI.preview_server as ps  # noqa: E402
from _adapter import api_trend  # noqa: E402


class TestTrendPayloadSize(unittest.TestCase):
    """/api/trend payload boyutları için byte bütcesi denetimi."""

    def setUp(self):
        # Create a temp history file with realistic records
        self.tmpdir = tempfile.mkdtemp()
        self.history_path = os.path.join(self.tmpdir, 'history.jsonl')

        # Create 50 test records similar to real format
        records = []
        for i in range(50):
            rec = {
                'ts': f'2026-01-15T{(i % 12) + 10:02d}:00:00Z',
                'verdict': 'PASS' if i % 5 != 0 else 'FAIL',
                'p0': i % 2,
                'p1': i % 3,
                'budget_usd': 50 + (i % 20) * 10,
                'budget_limit': 100,
                'duration_s': 10 + (i % 30),
                'z3_passed': i % 2,
                'z3_total': 5,
                'refs_verified': 1,
                'refs_total': 3,
                'workflow': f'test-workflow-{i % 10}',
                'url': f'http://example.com/{i}',
            }
            records.append(json.dumps(rec))

        with open(self.history_path, 'w') as f:
            for rec in records:
                f.write(rec + '\n')

        # Set the history path
        ps.HISTORY_PATH = self.history_path
        ps._history_cache = None

    def tearDown(self):
        ps.HISTORY_PATH = None
        os.environ.clear()
        # Cleanup temp dir
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _get_payload_size(self, limit):
        """/api/trend?limit=N için payload boyutunu (bytes) döndürür."""
        uri = f'/api/trend?limit={limit}' if limit else '/api/trend'
        os.environ['REQUEST_URI'] = uri

        result = api_trend()
        body = json.loads(result['body'])
        return len(result['body']), len(body['history'])

    # ── limit=None (full-list) ──

    def test_full_list_payload_within_budget(self):
        """limit=None (full-list) bütçesi 500 KB olmalı."""
        payload_size, hist_len = self._get_payload_size(None)
        # 500 KB = 512000 bytes
        max_budget = 512000
        self.assertLessEqual(
            payload_size, max_budget,
            f"Full-list payload {payload_size} bytes exceeds 500 KB budget"
        )
        print(f"  full-list: payload={payload_size} bytes, history={hist_len} records")

    # ── limit=1..100 ──

    def test_limit_1_payload_within_budget(self):
        """limit=1 payload bütçesi 50 KB."""
        payload_size, hist_len = self._get_payload_size(1)
        # 50 KB = 51200 bytes
        max_budget = 51200
        self.assertLessEqual(
            payload_size, max_budget,
            f"limit=1 payload {payload_size} bytes exceeds 50 KB budget"
        )
        print(f"  limit=1: payload={payload_size} bytes, history={hist_len} records")

    def test_limit_5_payload_within_budget(self):
        """limit=5 payload bütçesi 250 KB."""
        payload_size, hist_len = self._get_payload_size(5)
        # 250 KB = 256000 bytes
        max_budget = 256000
        self.assertLessEqual(
            payload_size, max_budget,
            f"limit=5 payload {payload_size} bytes exceeds 250 KB budget"
        )
        print(f"  limit=5: payload={payload_size} bytes, history={hist_len} records")

    def test_limit_10_payload_within_budget(self):
        """limit=10 payload bütçesi 500 KB."""
        payload_size, hist_len = self._get_payload_size(10)
        # 500 KB = 512000 bytes
        max_budget = 512000
        self.assertLessEqual(
            payload_size, max_budget,
            f"limit=10 payload {payload_size} bytes exceeds 500 KB budget"
        )
        print(f"  limit=10: payload={payload_size} bytes, history={hist_len} records")

    def test_limit_50_payload_within_budget(self):
        """limit=50 payload bütçesi 2.5 MB."""
        payload_size, hist_len = self._get_payload_size(50)
        # 50 × 50 KB = 2.5 MB = 2621440 bytes
        max_budget = 50 * 51200  # 50 KB × limit
        self.assertLessEqual(
            payload_size, max_budget,
            f"limit=50 payload {payload_size} bytes exceeds 50 KB × 50 = 2.5 MB budget"
        )
        print(f"  limit=50: payload={payload_size} bytes, history={hist_len} records")

    def test_limit_100_payload_within_budget(self):
        """limit=100 payload bütçesi 5 MB."""
        payload_size, hist_len = self._get_payload_size(100)
        # 100 × 50 KB = 5 MB = 5242880 bytes
        max_budget = 100 * 51200  # 50 KB × limit
        self.assertLessEqual(
            payload_size, max_budget,
            f"limit=100 payload {payload_size} bytes exceeds 50 KB × 100 = 5 MB budget"
        )
        print(f"  limit=100: payload={payload_size} bytes, history={hist_len} records")

    # ── limit>100 (katmanlı indirim) ──

    def test_limit_150_payload_within_budget(self):
        """limit=150 payload bütçesi 750 KB (5 KB × limit)."""
        payload_size, hist_len = self._get_payload_size(150)
        # 150 × 5 KB = 750 KB = 786432 bytes
        max_budget = 5 * 150 * 1024
        self.assertLessEqual(
            payload_size, max_budget,
            f"limit=150 payload {payload_size} bytes exceeds 5 KB × 150 = {max_budget} bytes budget"
        )
        print(f"  limit=150: payload={payload_size} bytes, history={hist_len} records")

    def test_limit_200_payload_within_budget(self):
        """limit=200 payload bütçesi 1 MB (5 KB × limit)."""
        payload_size, hist_len = self._get_payload_size(200)
        # 200 × 5 KB = 1 MB = 1048576 bytes
        max_budget = 5 * 200 * 1024
        self.assertLessEqual(
            payload_size, max_budget,
            f"limit=200 payload {payload_size} bytes exceeds 5 KB × 200 = {max_budget} bytes budget"
        )
        print(f"  limit=200: payload={payload_size} bytes, history={hist_len} records")


if __name__ == '__main__':
    unittest.main()