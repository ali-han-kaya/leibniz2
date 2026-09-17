#!/usr/bin/env bash
# docker_security_smoke.sh — Docker güvenlik akışının TEK KOMUTLUK yerel smoke'u.
#
# Akış (CI'daki docker-security workflow'unun birebir yerel karşılığı):
#   1) colima/docker/trivy durumu algılanır; colima kurulu ama kapalıysa
#      BAŞLATILIR (kullanıcı sözleşmesi). Araç hiç yoksa SKIP (exit 0).
#   2) Image CI ile aynı bağlamdan build edilir. arm64 makinelerde
#      linux/amd64 platformu ile build edilir (ölçüldü: z3-solver'ın aarch64
#      wheel'i glibc 2.38 isterken bookworm 2.36'dır → native arm64 build
#      builder'da patlar; CI ubuntu amd64 manylinux wheel kullanır. qemu
#      emülasyonu CI ile birebir artifact üretir).
#   3) Trivy gate CI ile aynı parametrelerle: CRITICAL,HIGH +
#      --ignore-unfixed + --exit-code 1 → bulgu varsa FAIL (fail-closed).
#   4) Sağlık: konteyner -P ile RASTGELE host portunda ayağa kaldırılır
#      (ölçüldü: sabit portlar host süreçleriyle çakışabilir — yanlış kanıt),
#      HEALTHCHECK healthy olana kadar beklenir ve /api/health HTTP 200
#      doğrulanır (host→konteyner erişiminin gerçek kanıtı).
#
# Çıkış sözleşmesi:
#   rc=0 → PASS veya SKIP (araç yok; sebebini yazar)
#   rc=1 → FAIL (build hatası, trivy bulgusu, sağlık ihlali)
# Kanıt: $DOCKER_SMOKE_OUT (varsayılan docs/ci_simulate/docker_security_smoke/)
#
# Stub-test edilebilirlik: tüm dış çağrılar (docker, colima, trivy, curl)
# PATH üzerinden çözülür; test_docker_security_smoke.py stub bin + yerel
# HTTP sunucusuyla offline doğrular. stdlib/ortam bağımlılığı yok.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT="${DOCKER_SMOKE_OUT:-$ROOT/docs/ci_simulate/docker_security_smoke/docker_security_smoke_report.txt}"
IMAGE_TAG="${DOCKER_SMOKE_TAG:-leibniz2/verify-dashboard:smoke-local}"
CID=""

fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
skip() { printf 'SKIP: %s\n' "$*" >&2; exit 0; }

mkdir -p "$(dirname "$OUT")"
: > "$OUT"
log() { printf '%s\n' "$*" | tee -a "$OUT" >&2; }

cleanup() {
  if [[ -n "$CID" ]]; then
    docker rm -f "$CID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

log "docker-security smoke evidence"
log "image=$IMAGE_TAG"

# ── 1) Araç keşfi ────────────────────────────────────────────────────────
command -v docker >/dev/null 2>&1 || skip "docker CLI yok — smoke koşulamaz (SKIP sözleşmesi)"
command -v trivy  >/dev/null 2>&1 || skip "trivy yok — güvenlik gate'i eksik, kısmi kanıt üretilmez"
command -v curl   >/dev/null 2>&1 || fail "curl yok — /api/health doğrulaması imkânsız (fail-closed)"

docker_client="$(docker version --format '{{.Client.Version}}' 2>/dev/null || true)"
if ! docker info >/dev/null 2>&1; then
  # Daemon erişilemiyor: colima kuruluysa başlatmayı DENE (sözleşme),
  # yine de açılmıyorsa SKIP (ortam yok ≠ kod bozuk; fail-closed kanıt yok).
  if command -v colima >/dev/null 2>&1; then
    log "colima=starting (kapalıydı, başlatılıyor)"
    colima start >> "$OUT" 2>&1 || skip "colima start başarısız — daemon sağlanamadı"
  else
    skip "docker daemon erişilemiyor ve colima kurulu değil"
  fi
  docker info >/dev/null 2>&1 || skip "colima start sonrası daemon hâlâ erişilemiyor"
fi
docker_server="$(docker version --format '{{.Server.Version}}' 2>/dev/null || echo unknown)"
log "docker_client=$docker_client"
log "docker_server=$docker_server"
log "colima=$(colima status >/dev/null 2>&1 && echo running || echo unknown)"

# ── 2) Build (CI bağlamı; arm64 → linux/amd64 emülasyon) ─────────────────
PLATFORM="${DOCKER_SMOKE_PLATFORM:-}"
if [[ -z "$PLATFORM" ]]; then
  case "$(uname -m)" in
    x86_64|amd64) PLATFORM="" ;;          # CI runner'ıyla aynı — birebir parity
    *)                PLATFORM="linux/amd64" ;;
  esac
elif [[ "$PLATFORM" == "native" ]]; then
  PLATFORM=""
fi
build_args=(build -t "$IMAGE_TAG" "$ROOT")
[[ -n "$PLATFORM" ]] && build_args=(build --platform "$PLATFORM" -t "$IMAGE_TAG" "$ROOT")
log "platform=${PLATFORM:-native}"
if ! docker "${build_args[@]}" >> "$OUT" 2>&1; then
  fail "docker build başarısız (ayrıntı kanıt dosyasında: $OUT)"
fi
image_id="$(docker image inspect --format '{{.Id}}' "$IMAGE_TAG" 2>/dev/null || echo unknown)"
log "image_id=$image_id"

# ── 3) Trivy gate (CI parametreleri, fail-closed) ────────────────────────
# || true: sürüm önizlemesi asla script'i öldürmemeli (set -o pipefail altında
# aracın --version'dan bile sıfır-dışı çıkışı diziyi durdurur — stub testte ölçüldü).
trivy_version="$(trivy --version 2>/dev/null | head -1 | awk '{print $2}' || true)"
log "trivy=$trivy_version"
trivy_out="$(mktemp)"
if ! trivy image --severity CRITICAL,HIGH --ignore-unfixed \
      --exit-code 1 --format table "$IMAGE_TAG" > "$trivy_out" 2>&1; then
  tail -30 "$trivy_out" >> "$OUT"
  log "verdict=FAIL"
  fail "Trivy gate bulgu üretti (CRITICAL/HIGH) — fail-closed"
fi
log "trivy_findings=0"
log "trivy_clean=Clean"

# ── 4) Canlı sağlık (rastgele host port + HEALTHCHECK + HTTP) ────────────
CID="$(docker run -d -P "$IMAGE_TAG")" || fail "konteyner başlatılamadı"
host_port=""
for _ in $(seq 1 10); do
  host_port="$(docker port "$CID" 8000 2>/dev/null | tail -1 | sed 's/.*://')"
  [[ -n "$host_port" ]] && break
  sleep 1
done
[[ -n "$host_port" ]] || fail "docker port eşlemesi okunamadı"
log "host_port=$host_port"

http_ok=""
for _ in $(seq 1 40); do
  body="$(curl -fsS -m 5 "http://127.0.0.1:${host_port}/api/health" 2>/dev/null || true)"
  if [[ -n "$body" ]]; then
    http_ok="$body"
    break
  fi
  sleep 3
done
[[ -n "$http_ok" ]] || fail "/api/health yanıt vermedi (${host_port})"
log "health_http=200"
log "health_body=$http_ok"

health_status="unknown"
for _ in $(seq 1 100); do
  health_status="$(docker inspect --format '{{.State.Health.Status}}' "$CID" 2>/dev/null || echo unknown)"
  [[ "$health_status" == "healthy" ]] && break
  sleep 3
done
log "container_health=$health_status"
[[ "$health_status" == "healthy" ]] || fail "HEALTHCHECK healthy olmadı (son durum: $health_status)"

log "verdict=PASS"
printf 'PASS: build + trivy(CRITICAL,HIGH=0) + health(200, healthy) — kanıt: %s\n' "$OUT"
