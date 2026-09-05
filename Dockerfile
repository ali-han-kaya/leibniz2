# syntax=docker/dockerfile:1
# Stoic-Hume V5 — CI dashboard (preview_server.py) container.
#
# Two stages:
#   builder  — installs the chain's Python deps into a clean venv. The only
#              third-party dependency is z3-solver (K8 symbolic proof engine);
#              everything else in the verify chain is stdlib-only, and
#              z3-solver ships manylinux wheels, so no compiler is needed.
#   runtime  — python:3.11-slim + the venv + the repo's runtime file set
#              (exactly the mirror contract in check_mirror_coverage.py:
#              _calisma/CIKTI/*, _calisma/lean_reduct/*, the docs guide
#              files), running as a non-root user with a real HEALTHCHECK.
#
# K9 (Lean reduct-invariance) is deliberately NOT shipped: it needs the Lean
# toolchain (lean/lake via elan, ~1GB). The chain marks optional layers SKIP
# when the tool is absent, so the dashboard stays green without it. To enable
# K9, extend the runtime stage with an elan install and PATH update.
#
# Build / run:
#   docker build -t verify-dashboard .
#   docker run --rm -p 8000:8000 verify-dashboard
#   # browser → http://localhost:8000/preview.html

FROM python:3.11-slim AS builder

RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir z3-solver

FROM python:3.11-slim AS runtime

# The z3 interpreter for K8 + hook_env: copied from the builder, put on PATH.
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    SC_PY=/opt/venv/bin/python

# Non-root app user.
RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home app

WORKDIR /app

# Repo runtime file set (mirror contract). .dockerignore keeps the context to
# the essentials; zips and lean sources stay because the chain audits them.
COPY --chown=app:app . /app/

# Web surface served from --preview-dir (writable: history.jsonl + runs/ land
# here), mirroring the local caches-dir layout (preview.html, sw.js, guide).
RUN mkdir -p /app/state \
    && cp /app/_calisma/CIKTI/preview.html /app/_calisma/CIKTI/sw.js /app/state/ \
    && cp /app/docs/branch-protection-guide/guide.html /app/state/ \
    && cp /app/docs/HOOK_ENV_MATRIX.md /app/state/ \
    && chown -R app:app /app

USER app
EXPOSE 8000

HEALTHCHECK --interval=60s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python3", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"]

# --bind 0.0.0.0 so the container's port mapping can reach the server
# (loopback inside a container is unreachable from the host). The verify loop
# runs every 60s by default; override with `docker run ... --interval=300`.
CMD ["python3", "_calisma/CIKTI/preview_server.py", \
     "--dir", "/app/_calisma/CIKTI", \
     "--preview-dir", "/app/state", \
     "--bind", "0.0.0.0", "--port", "8000", "--interval", "60"]
