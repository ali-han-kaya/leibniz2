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

# Distro line pinned to bookworm: python:3.11-slim floated to trixie
# (Debian 13) and its younger package set carries unfixed CRITICAL/HIGH
# CVEs — the docker-security Trivy gate fails closed on them. Bookworm's
# package set is the mature, continuously-patched line (upstream rebuilds
# the tag as security fixes land), keeping the scan green without
# weakening the gate.
# PYTHON KATMANI güvenlik-yama ARG'si — apt katmanıyla (SECURITY_PATCH_PACKAGES)
# TEK MEKANİZMADA: floors burada yaşar (tek kopya, global scope — her stage
# bare ARG ile miras alır), stage'ler yeniden beyan eder. CVE-defteri:
#   setuptools: pip/pkg_resources zinciri HIGH CVE'si → floor >=80
#   wheel: CVE-2026-24049 (privesc) → floor >=0.46.2
#   (kanıt: 2026-09-16 trivy docker-security gate bulgusu → yama → 0 bulgu)
# Floor'lar minimumdur (>=): base image daha yenisini taşıyorsa pip onu kullanır.
ARG PYTHON_SECURITY_PATCH_PACKAGES="setuptools>=80 wheel>=0.46.2"

FROM python:3.11-slim-bookworm AS builder

# z3-solver: K8 symbolic proof engine (tek üçüncü-parti bağımlılık).
# Pip yaması: global ARG default'u (üstteki CVE-defteri) — apt katmanıyla
# simetrik guard/kanıt: boş ARG = yama yok (net kanıt), kurulan sürümler
# pip show ile build log'una yazılır (floor eki kırpılır — yalın paket adı).
ARG PYTHON_SECURITY_PATCH_PACKAGES
# Tuzaka-notu (canlı build'de ölçüldü): unquoted $VAR genişlemesi floor'lardaki
# '>' karakterini shell REDIRECT'ine çevirir — floor yutulur, pip bare sürüm
# kurar. Güvenli form: QUOTED genişleme satır başına floor yazıp -r dosyası.
RUN set -eux; \
    python -m venv /opt/venv; \
    if [ "$(printf '%s' "$PYTHON_SECURITY_PATCH_PACKAGES" | tr -d '[:space:]')" = "" ]; then \
      echo "PYTHON_SECURITY_PATCH_PACKAGES empty — no targeted pip patch"; \
    else \
      printf '%s\n' "$PYTHON_SECURITY_PATCH_PACKAGES" | tr ' ' '\n' > /tmp/pip_security_reqs.txt; \
      /opt/venv/bin/pip install --no-cache-dir --upgrade -r /tmp/pip_security_reqs.txt; \
      /opt/venv/bin/pip show \
        $(printf '%s\n' "$PYTHON_SECURITY_PATCH_PACKAGES" | tr ' ' '\n' | sed 's/[><=!~].*//') \
        | grep -E '^(Name|Version):'; \
    fi; \
    /opt/venv/bin/pip install --no-cache-dir z3-solver

FROM python:3.11-slim-bookworm AS runtime

# Sistem setuptools/wheel'i (pip/pkg_resources zinciri) aynı ARG mekanizmasıyla
# yamalanır — gate'in tetiklediği yamalar bu aşamada uygulanır (guard/kanıt
# builder stage'iyle özdeş; bare ARG global default'u miras alır).
ARG PYTHON_SECURITY_PATCH_PACKAGES
RUN set -eux; \
    if [ "$(printf '%s' "$PYTHON_SECURITY_PATCH_PACKAGES" | tr -d '[:space:]')" = "" ]; then \
      echo "PYTHON_SECURITY_PATCH_PACKAGES empty — no targeted pip patch"; \
    else \
      printf '%s\n' "$PYTHON_SECURITY_PATCH_PACKAGES" | tr ' ' '\n' > /tmp/pip_security_reqs.txt; \
      pip install --no-cache-dir --upgrade -r /tmp/pip_security_reqs.txt; \
      pip show \
        $(printf '%s\n' "$PYTHON_SECURITY_PATCH_PACKAGES" | tr ' ' '\n' | sed 's/[><=!~].*//') \
        | grep -E '^(Name|Version):'; \
    fi

# GENELLEŞTİRİLMİŞ güvenlik-yama katmanı — base-image güncellemelerinin
# getirdiği CRITICAL/HIGH Trivy bulgularını kapatan tek nokta. Desen:
#
#   SECURITY_PATCH_PACKAGES (build-arg, boş varsayılan) — yamalanacak paket
#     listesi. Bir base-image güncellemesi Trivy gate'ini (docker-security
#     workflow: CRITICAL,HIGH + ignore-unfixed + exit-code 1) kırdığında,
#     bulgunun paketi floor sürümüyle buraya EKLENİR:
#
#       --build-arg SECURITY_PATCH_PACKAGES="pkg=fixed_version ..."
#
#     build'de yama uygulanır; Dockerfile'a işlenen kalıcı kayıt aşağıdaki
#     CVE-defteridir (her paket için paket, bulan CVE'ler, floor sürüm,
#     kanıt tarihi). Gate yeşil kalınca da satırlar DURUR: kasıtlı, hızlı
#     tekrar-tarama + sürüm-için-dokümantasyon. Floor'lar minimumdur —
#     base image daha yenisini taşıyorsa --only-upgrade asla düşürmez.
#   Uygulama kuralları (dava uyumlu): yalnız etkilenen paket (tüm-upgrade
#     değil — taban sürümü değişmez, diff yüzeyi küçük kalır),
#     --no-install-recommends, apt listeleri temizlenir (katman kalıntısı
#     yok), kurulan sürümler kanıta yazılır (yama doğrulanabilir).
#
# CVE-defteri (artan süre — desen 2026-09-16 pcre2 düzeltmesiyle doğdu):
#   libpcre2-8-0: CVE-2026-86145 (OOB write) + CVE-2026-89161
#     (pcre2_jit_match memory corruption) → floor 10.42-1+deb12u1
#     (kanıt: 2026-09-16, trivy 0.74.0 yerel smoke + CI 35161423659
#     before/after; 2026-09-17 desenle yeniden doğrulandı). Girdi
#     SECURITY_PATCH_PACKAGES default'unda yaşar — pasif kayıt, her
#     build'de taze yama.
ARG SECURITY_PATCH_PACKAGES="libpcre2-8-0=10.42-1+deb12u1"
RUN set -eux; \
    if [ "$(printf '%s' "$SECURITY_PATCH_PACKAGES" | tr -d '[:space:]')" = "" ]; then \
      echo "SECURITY_PATCH_PACKAGES empty — no targeted apt patch"; \
    else \
      apt-get update; \
      apt-get install -y --no-install-recommends --only-upgrade $SECURITY_PATCH_PACKAGES; \
      rm -rf /var/lib/apt/lists/*; \
      dpkg-query -W -f='${Package}\t${Version}\n' \
        $(printf '%s\n' $SECURITY_PATCH_PACKAGES | sed 's/=.*//'); \
    fi
#
# Desen dokümanı: docs/DOCKER_SECURITY_PATCHING.md (kapalı döngü: gate →
# bulgu → yama → tarama; iki katman — bu ARG ve pip floor katmanı; katkı
# sözleşmesi). Yerel kanıt üretimi: _calisma/CIKTI/docker_security_smoke.sh

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
