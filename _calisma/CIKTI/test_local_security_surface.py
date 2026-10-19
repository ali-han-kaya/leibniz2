class TestRunNowTokenlessFailClosed(unittest.TestCase):
    """tokensız-mod: PREVIEW_RUN_NOW_TOKEN yoksa /api/run-now /api/stop
    hiçbir koşulda açma → fail-closed (401). localhost+trusted dışında
    (G1) ve peer dışında (G2) zaten 403; token yoksa da üstüne 401."""
    def _no_token(self):
        old = os.environ.get("PREVIEW_RUN_NOW_TOKEN")
        if old is None:
            os.environ.pop("PREVIEW_RUN_NOW_TOKEN", None)
        else:
            os.environ["PREVIEW_RUN_NOW_TOKEN"] = old
        return old

    def test_run_now_requires_token(self):
        old = self._no_token()
        try:
            h, sent = _handler("/api/run-now",
                               {"Host": "127.0.0.1:8000"},
                               peer=("127.0.0.1", 55555))
            h.trigger_run_now()
            self.assertEqual(sent[0][0], 401)
            self.assertEqual(sent[0][1]["error"], "unauthorized")
        finally:
            if old is None:
                os.environ.pop("PREVIEW_RUN_NOW_TOKEN", None)
            else:
                os.environ["PREVIEW_RUN_NOW_TOKEN"] = old


