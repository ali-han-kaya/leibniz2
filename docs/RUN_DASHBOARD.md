# Run Doc: Preview Server + Dashboard from Fresh Checkout

> **Goal:** Stand up the Python preview server and its static dashboard from a
> clean `git clone`, verify the API + SSE surface, and optionally run the
> React prototype against it.

## Prerequisites

| Requirement | Version | Check |
|---|---|---|
| Python | 3.11+ (3.9 works without z3) | `python3 --version` |
| Git | any recent | `git --version` |
| Docker (optional) | any | `docker --version` |
| Node.js (optional, React prototype) | 18+ | `node --version` |

No npm, pip install, or system packages are required for the core server —
`preview_server.py` is stdlib-only. The only third-party dependency is
`z3-solver` for K8 symbolic proofs, which degrades honestly (SKIP) if absent.

---

## 1. Clone

```bash
git clone git@github.com:ali-han-kaya/leibniz2.git
cd leibniz2
```

## 2. Start the preview server

### Option A: Bare Python (fastest)

```bash
python3 _calisma/CIKTI/preview_server.py \
  --dir _calisma/CIKTI \
  --preview-dir _calisma/CIKTI \
  --port 8000 \
  --bind 127.0.0.1 \
  --interval 60
```

| Flag | Purpose | Default |
|---|---|---|
| `--dir` | Directory containing `verify_delivery.py` | `_calisma/CIKTI` (ROOT) |
| `--preview-dir` | Where `preview.html`, `history.jsonl`, `runs/` live | `~/Library/Caches/com.freebuff/preview` |
| `--port` | HTTP port | 8000 |
| `--bind` | Bind address | `127.0.0.1` |
| `--interval` | Seconds between verify runs | 60 |
| `--replay-runs` | Number of past runs to persist + replay | 10 |

**Important:** `--preview-dir` must point to a writable directory containing
`preview.html` and `sw.js`. For a fresh checkout, point it at `_calisma/CIKTI`
where those files already live.

### Option B: Docker

```bash
docker compose up --build
```

This builds the two-stage Dockerfile (python:3.11-slim + z3-solver venv),
publishes on `127.0.0.1:8000` (loopback-only), and persists state to a named
volume. The healthcheck polls `/api/health` every 30s.

### Option C: Full TCC-safe setup (macOS launchd path)

```bash
bash _calisma/CIKTI/fresh_clone_setup.sh
```

This one command sets up the repo venv, TCC-safe mirror venv, preview+verify
mirrors, HTML build, and LaunchAgent plists. Use this if you plan to run the
launchd daemon, not just a foreground server.

## 3. Verify the API surface

```bash
# Health check
curl -s http://127.0.0.1:8000/api/health
# → ok

# Latest snapshot
curl -s http://127.0.0.1:8000/api/latest | python3 -m json.tool

# Run history (last 15 runs, compact JSON)
curl -s http://127.0.0.1:8000/api/run-history | python3 -m json.tool

# Trend history (JSONL-backed)
curl -s http://127.0.0.1:8000/api/history | python3 -m json.tool

# Refs trend (CI artifact, if present)
curl -s http://127.0.0.1:8000/api/refs-trend | python3 -m json.tool
```

## 4. Open the dashboard

Open `http://127.0.0.1:8000/preview.html` in a browser.

The dashboard provides:
- **SSE live stream** (`/api/run`) — real-time verify snapshots
- **Run stdout stream** (`/api/run-stream`) — live stdout lines during a run
- **Trend charts** — history + refs-trend + budget overlay
- **Run history list** — last 15 runs with verdict/P0/P1/budget/duration
- **Mirror sync + pattern drift** indicators

The first verify run starts after `--interval` seconds (default 60). To trigger
one immediately:

```bash
# If PREVIEW_RUN_NOW_TOKEN is not set, no auth is required locally:
curl -X POST http://127.0.0.1:8000/api/run-now
# → {"status":"started","ts":"...","note":"verify başladı..."}

# To enable bearer-token auth:
export PREVIEW_RUN_NOW_TOKEN=my-secret
python3 _calisma/CIKTI/preview_server.py --dir _calisma/CIKTI --preview-dir _calisma/CIKTI
curl -X POST -H "Authorization: Bearer my-secret" http://127.0.0.1:8000/api/run-now
```

## 5. (Optional) Run the React prototype

The repo includes a minimal React/Vite dashboard at `apps/dashboard-shadcn/`
that consumes the same `/api/latest` and `/api/run-history` endpoints.

```bash
# From the repo root, with the preview server already running on :8000:
cd apps/dashboard-shadcn
npm install
npm run dev
```

The Vite dev server proxies `/api/*` to `http://127.0.0.1:8000` (configured in
`vite.config.ts`). Open the URL Vite prints (typically `http://localhost:5173`).

### Comparison: static dashboard vs React prototype

| Feature | `preview.html` (static) | `apps/dashboard-shadcn` (React) |
|---|---|---|
| SSE live updates | ✅ EventSource + service worker | ❌ One-shot fetch on mount |
| Trend charts | ✅ SVG, history + budget | ❌ Not implemented |
| Run-stdout stream | ✅ Live SSE | ❌ Not implemented |
| Run-now trigger | ✅ POST with auth | ❌ Not implemented |
| Build step | None (static file) | `npm install` + Vite |
| Bundle | 0 (served by Python) | ~195 KB JS + 4 KB CSS |

The static dashboard is the production surface; the React prototype is a
design exploration for a potential component-based rewrite.

## 6. Run the test suite

```bash
# Preview server unit tests (stdlib, no deps):
python3 -m unittest _calisma.CIKTI.test_preview_server -v

# Dashboard contract tests (colorize rules, DOM structure):
python3 -m unittest _calisma.CIKTI.test_colorize_rules -v

# Full unit-test gate (all test_*.py files):
bash _calisma/CIKTI/check_unit_tests_hook.sh
```

## 7. Clean shutdown

The server handles `SIGINT`/`SIGTERM` with ordered shutdown:
1. `stop_event.set()` — signals the verify loop to exit
2. `t.join(timeout=30)` — waits for the verify thread
3. `srv.shutdown()` — stops accepting connections
4. `srv.server_close()` — closes the socket

Press `Ctrl+C` in the foreground terminal, or `docker compose down` for the
container path.

---

## API reference (read-only endpoints)

| Endpoint | Method | Returns |
|---|---|---|
| `/api/health` | GET | `ok` (plain text) |
| `/api/latest` | GET | Compact JSON: latest verify snapshot (verdict, P0/P1, layers, budget, stdout_short, hook_env_matrix) |
| `/api/history` | GET | JSON array of trend rows (JSONL-backed) |
| `/api/run-history` | GET | JSON array of last 15 run summaries |
| `/api/refs-trend` | GET | JSON: duration/budget trend (CI artifact) |
| `/api/run-stdout?ts=<timestamp>` | GET | JSON: full stdout+stderr for a specific run |
| `/api/run` | GET (SSE) | `snapshot` / `update` events (real-time) |
| `/api/run-stream` | GET (SSE) | `line` / `info` / `end` events (stdout stream) |
| `/api/run-now` | POST | JSON: starts a verify run (auth-gated) |

All `/api/*` unknown paths return `404` with a JSON error envelope; static-file
404s return plain text.

## Security notes

- `/api/run-now` validates `Host` (loopback only) and optional `Origin` headers
- Bearer-token auth is optional (enabled when `PREVIEW_RUN_NOW_TOKEN` is set)
- Token comparison uses `hmac.compare_digest` (timing-safe)
- Docker Compose binds to `127.0.0.1:8000` (loopback-only, not exposed publicly)
- All verification tools are read-only; the server never writes JSONL or
  sidecars except through the normal verify loop
