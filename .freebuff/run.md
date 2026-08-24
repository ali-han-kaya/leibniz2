# Stoic-Hume V5 preview — run doc

## What this is
A live SSE-streaming CI dashboard at http://127.0.0.1:8000/preview.html.
`preview_server.py` runs `verify_delivery.py --full` every 60 s, parses the
JSON verdict, and serves:
- `/`            / `/preview.html` — static HTML dashboard (EventSource)
- `/api/latest`  — JSON snapshot of the most recent run
- `/api/run`     — Server-Sent Events stream of successive runs
- `/api/run-stream` — live line stream of the running verify subprocess:
                   stdout/stderr lines (incl. K8 Z3 progress) as they are
                   produced; `end` event with final snapshot on completion
- `/api/run-now` — manual trigger (GET/POST): runs `verify_delivery.py --full`
                   immediately, without waiting for the interval; result is
                   broadcast to SSE clients as soon as it finishes. Returns
                   `{"status":"started"}` or `409 {"status":"already_running"}`
                   if a verify is already in flight (busy-guard, no overlap)
- `/api/history` — last 100 runs as JSON array (trend chart data), read from
                   `history.jsonl` on disk; survives server restarts
- `/api/health`  — `ok`

The dashboard updates in real time without page refresh (HTML5 EventSource).

## How to reproduce the artifacts

Tek komutla beş artefaktı kurar (idempotent, fail-closed):

```bash
_calisma/CIKTI/fresh_clone_setup.sh              # kur/senkron et
_calisma/CIKTI/fresh_clone_setup.sh --check       # beş artefakt hazır mı? (0/1/2)
_calisma/CIKTI/fresh_clone_setup.sh --check-ci    # CI runner: daemon + mirror venv atla
_calisma/CIKTI/fresh_clone_setup.sh --force-venv  # venv'leri her zaman yeniden kur
```

Adımlar (script içinde tek komutta):

| # | Artefakt | Yol | Ne yapar |
|---|---|---|---|
| 1 | Repo venv | `_calisma/.venv_z3` | z3 + pre-commit + yaml + jsonschema |
| 2 | Mirror venv | `~/Library/Caches/com.freebuff/venv_z3` | TCC-safe, aynı paketler |
| 3+4 | Preview + verify mirror | `~/Library/Caches/com.freebuff/preview/` + `verify/` + `lean_reduct/` | `sync_verify_mirror.sh` — tek komutta |
| 5 | HTML + plist | `preview.html` + `LaunchAgents/*.plist` | `update_preview.sh --bootstrap` |

Ek denetimler (`--check` modunda):
- Daemon HTTP rotası: `daemon_http_test.py` mirror kopyasıyla SSE/run-now dahil HTTP smoke
- Agent mirror karşılaştırması: plist'teki `--preview-dir`/`--dir` yolları `--check` ile aynı mı?
- Plist şablonu drift: `preview-template/*.plist.tmpl` kurulu plist'le birebir mi?

TCC nedeniyle launchd GUI agent'ı repo dizinini **okuyamaz** — tüm runtime
`~/Library/Caches/com.freebuff/` altındaki TCC-safe mirror'da tutulur.
`--check-ci` modu daemon smoke'u (canlı sunucu gerektirir) ve mirror venv'i
(CI'da farklı yolda) atlar; yalnızca 5 artefaktın kurulumunu doğrular.

## LaunchAgent plist — Homebrew-style, per-profile şablon (TEK plist)

`update_preview.sh --plist` TEK komutla plist'i yönetir:

| Profil | KeepAlive | interval | Amaç |
|---|---|---|---|
| `com.freebuff.preview-leibniz2` | true | 30 | birincil (durable, auto-restart) |

Legacy `com.freebuff.preview-server` profili kaldırıldı; `--remove-legacy`
bir kerelik taşımayı yapar (launchd'den bootout + kurulu plist/şablon/log
silme) — yalnızca birincil leibniz2 canlı kalır.

Kurulu tam yollar korunur: `~/Library/LaunchAgents/<label>.plist`. İçerikleri
şablondan üretilir: `~/Library/Caches/com.freebuff/preview-template/<label>.plist.tmpl`.
Aynı TCC-safe mirror `--dir`'ini kullanır
(`~/Library/Caches/com.freebuff/verify`); launchd GUI agent'ı repo dizinini
TCC nedeniyle okuyamaz.

Şablonda `{{HOME}}` / `{{LABEL}}` / `{{LOGNAME}}` / `{{PORT}}` / `{{INTERVAL}}` /
`{{KEEPALIVE}}` placeholder'ları vardır; profiller script içindeki
`PLIST_PROFILES` dizisinde tanımlıdır (`label|logname|port|interval|keepalive`).

```bash
_calisma/CIKTI/update_preview.sh --plist [HOME]        # plist'i üret (vars. $HOME)
_calisma/CIKTI/update_preview.sh --plist-check [HOME]  # güncel mi? (0 güncel / 1 bayat / 2 şablon yok)
_calisma/CIKTI/update_preview.sh --plist-watch [N]     # şablonlar değişince yeniden üret
_calisma/CIKTI/update_preview.sh --plist-force [HOME]  # plist'i her zaman yeniden üret
_calisma/CIKTI/update_preview.sh --plist-reset         # şablonu yerleşik varsayılandan geri yaz
_calisma/CIKTI/update_preview.sh --start [LABEL]       # plist'i üret + launchctl bootstrap (vars. birincil)
_calisma/CIKTI/update_preview.sh --stop [LABEL|all]    # launchctl bootout
_calisma/CIKTI/update_preview.sh --remove-legacy [HOME] # legacy preview-server'ı kaldır (bootout + sil)
```

Çıktı `plutil -lint` (yoksa plistlib) ile doğrulanır; geçersiz çıktı yazılmaz.
`verify_delivery.py --check-plist` (K12) aynı `--plist-check`'i çağırır.
`--plist-out JSON` bayrağı K12 çıktısını + sidecar'ı tek dosyaya yazar (CI artifact için).

### plist_report.json sidecar biçimi (K12)

```json
{
  "layer": "K12",
  "ok": true,
  "exit": 0,
  "detail": "GÜNCEL (2/2 profil şablonla birebir + plutil geçerli)",
  "output": "GÜNCEL: .../com.freebuff.preview-leibniz2.plist  (şablonla aynı, ...)",
  "profiles": [
    {
      "label": "com.freebuff.preview-leibniz2",
      "status": "GÜNCEL",
      "path": "/Users/.../com.freebuff.preview-leibniz2.plist"
    },
    {
      "label": "com.freebuff.preview-server",
      "status": "GÜNCEL",
      "path": "/Users/.../com.freebuff.preview-server.plist"
    }
  ]
}
```

Her profil için `label` (launchctl label), `status` (GÜNCEL/BAYAT/şablon yok), `path` (plist yolu).
`ok`: tüm profiller GÜNCEL ise true; `exit`: `update_preview.sh --plist-check` çıkış kodu (0=GÜNCEL, 1=BAYAT, 2=şablon yok).
Reproducibility manifest'te `plist_check.combined_sha256` ile sabitlenir.

> Not: bu plist launchd GUI agent'ı içindir ve TCC kısıtı nedeniyle proje
> dosyalarını Okuyamaz — `--dir` TCC-safe kopyayı (`~/Library/Caches/com.freebuff/verify`)
> işaret eder. Tam TCC erişimli canlı dashboard için aşağıdaki setsid
> yöntemi (user shell) kullanılır; plist yedek/otomatik-başlatma yoludur.


## Pre-commit hooks (16 kapı)

```bash
pre-commit run --all-files        # 16 hook: 15 push'ta + 1 commit-msg
```

| # | Hook | Kapsam | Mod |
|---|---|---|---|
| 1 | update-config | gen_config.py --dry-run ile config senkronu | pass-through |
| 2 | verify-delivery | K0-K7 çekirdek (CI: --full ile K8/K9/K11/K13/K14/K16 eklenir) | **fail-closed** |
| 3 | check-action-pins | action major version downgrade kontrolü | fail-closed |
| 4 | check-python3-shell | shell: python3 {0} kabuk-komutu taraması | fail-closed |
| 5 | check-absolute-paths | /Users/... veya /home/... mutlak yol taraması | fail-closed |
| 6 | actionlint | workflow YAML lint (shellcheck info/hints) | advisory |
| 7 | verify-delivery-symbolic | Z3 sembolik ispat (core_section.tex) | **fail-closed** |
| 8 | verify-delivery-lean | Lean 4 reduct-invariance derleme | **fail-closed** |
| 9 | check-plist-drift | K12 plist şablon birim testleri (18 test) | pass-through |
| 10 | check-repro-manifest | K13 repro manifest + pattern coverage (58 test) | fail-closed |
| 11 | verify-delivery-github-scripts | K16 github-scripts self-test (49 senaryo) | fail-closed |
| 12 | verify-delivery-repro-manifest | K13 gen_repro_manifest.py self-test (7 mock dosya) | fail-closed |
| 13 | shellcheck-hooks | shell hook betik POSIX lint | pass-through |
| 14 | check-changelog-sync | git log ↔ docs changelog senkronu | pass-through |
| 15 | check-dryrun-summary | --dry-run-summary markdown üretimi regresyon kapısı | pass-through |
| 16 | commit-msg-style | başlık uzunluğu + noise/marker yasağı (yalnızca commit) | fail-closed |

> Not: 16 hooktan 6-sı **fail-closed** (P0/P1 üretebilir); kalanı pass-through veya advisory.

## How to run the server

The server must run in the **user shell session** (not under launchd GUI
agent) because:
- launchd GUI agents inherit a TCC context that prevents reading project
  files even via `launchctl asuser`.
- `verify_delivery.py --full` (K1-K9 + CrossRef + SEP + OpenLibrary + Z3
  + Lean) takes ~60 s and needs full TCC access.

The trick: `POSIX::setsid()` (Perl one-liner) puts the process in a new
session and process group, so the parent shell's exit doesn't reach it
via group signals (no `nohup` + `&` here is enough — `setsid` is the
real fix).

**Artık elle başlatmak gerekmez.** `_calisma/CIKTI/update_preview.sh --start`
tek komutta plist'i üretir, mirror'ı senkronlar, launchctl bootstrap yapar
ve health check ile HTTP 200'ü doğrular. Detay: `update_preview.sh --help`.

### Launchd plist route (durable, recommended)

With the mirror synced, the `com.freebuff.preview-leibniz2`
plist works end-to-end from launchd: `KeepAlive=true`, port 8000,
`--dir $HOME/Library/Caches/com.freebuff/verify`, log
`~/Library/Logs/com.freebuff/preview-leibniz2.log`. No TCC issues — all
paths stay under Caches/Logs.

```bash
# Tek komut: plist üret + mirror senkron + bootstrap + health check
_calisma/CIKTI/update_preview.sh --start
```

`--start` internally: (1) mirror sync → (2) plist generate → (3) `launchctl
bootout` (temiz durdur) → (4) `launchctl bootstrap` → (5) `curl` health
check. `--stop` tersini yapar: bootout + durdur.

Note: the interval is 30 s in that plist. Verify runs are guarded by the
busy lock, so a slow network refs check (~4 min) never overlaps.
First full run takes ~1-5 min depending on network; `/api/latest` may show
`UNKNOWN` until the first verify cycle completes.

Fallback if the plist is missing: `_calisma/CIKTI/update_preview.sh --plist`
recreates it from the template. (Do NOT use `launchctl submit` with a log
path under the project Desktop dir — TCC blocks the redirect and the job
exits 1 silently.)

## How to register the preview

After the server is verified up, the Freebuff client can register it:

```python
register_preview(
    url="http://127.0.0.1:8000/preview.html",
    pid=<pid from ps above>,
)
```

The dashboard tab will then show live updates.

## Tear-down

```bash
pkill -f preview_server.py
# Don't delete the venv mirror — it's ~117 MB and cheap to keep.
# Re-`cp -R` only when .venv_z3 itself changes.
rm -rf $HOME/Library/Caches/com.freebuff/preview/preview_server.py \
       $HOME/Library/Caches/com.freebuff/preview/preview.html
rm -f $HOME/Library/Logs/com.freebuff/preview-server.log
```

## Port
8000 (free at session start; Python `http.server` default).

## Directory layout (TCC-safe)

| Resource | Path | Why |
|---|---|---|
| HTML artefacts | `~/Library/Caches/com.freebuff/preview/preview.html` | user cache; HTTP server reads freely |
| Server script | `~/Library/Caches/com.freebuff/preview/preview_server.py` | mirror of project source |
| venv z3 python | `~/Library/Caches/com.freebuff/venv_z3/` | mirror of project's `.venv_z3` (z3-solver) |
| Server logs | `~/Library/Logs/com.freebuff/preview-server.log` | standard log dir |
| Run history | `~/Library/Caches/com.freebuff/preview/history.jsonl` | JSONL, last 100 runs; written atomically per run (P0/P1 trend) |
| Project source | `/Users/alikaya/Desktop/leibniz2/_calisma/CIKTI/` | authoring only; verifier reads the MIRROR below in the launchd route |
| Verify mirror | `~/Library/Caches/com.freebuff/verify/` | TCC-safe `--dir` for launchd: verify_delivery.py + config + schema + symbolic_proof_z3.py + zips + lineage + lean_reduct/ |

## Known pitfalls (this session's lessons)

1. **launchd GUI agents can't read project files** — even via
   `launchctl asuser`. The agent's process tree inherits a TCC context
   that the asuser call doesn't fully bypass. The agent can read
   `~/Library/Caches/com.freebuff/` and `~/Library/Logs/com.freebuff/`
   but NOT `/Users/alikaya/Desktop/leibniz2/...`.

2. **`nohup <cmd> > log 2>&1 &` from run_terminal_command is reaped**
   when the parent shell exits. `nohup` ignores SIGHUP, but the
   process group still receives SIGTERM through the shell's exit
   handshake.

3. **`POSIX::setsid()` (Perl) is the working detach idiom** under
   macOS Sequoia. It creates a new session + process group, so the
   parent shell's group signals don't reach the detached process.

4. **TCC-safe venv python works** — `~/Library/Caches/com.freebuff/venv_z3/`
   is a mirror of the project's `.venv_z3`. The venv's `pyvenv.cfg` is
   readable from the user shell context.

5. **JSON parsing of verify_delivery.py output** — the script outputs
   ONLY JSON (no human-readable text) in `--json` mode. The
   `json.loads(stdout)` approach works; `rfind("{")` alone is buggy
   because it finds the innermost nested object.

6. **HTTP server may be killed by run_terminal_command's cleanup**
   even after `nohup` + `disown` if it stays in the same process
   group. `POSIX::setsid()` fixes this definitively.

7. **Time of first verify run** — the loop runs immediately on startup
   (`for line in stdout: ...` style busy-spin replaced with explicit
   first-run). Expect ~60 s for the dashboard to show first valid
   data (K1-K9 + CrossRef + SEP + OpenLibrary + Z3 + Lean).
   With the network refs check the full run takes 1-5 min (or times out
   at 300 s); `/api/latest` stays `UNKNOWN` until it finishes.

8. **launchd `submit` log path must stay out of TCC-protected dirs** —
   a redirect to `/Users/alikaya/Desktop/leibniz2/.freebuff/...` fails
   with EPERM and the job exits 1 with an EMPTY log. Use
   `~/Library/Logs/com.freebuff/` or `/tmp` for launchd-spawned output.

9. **PREVIEW_DAEMON=1 used to close fds 0/1/2** — fixed: now it
   `dup2`-redirects them to /dev/null (never closes), and `log_message`
   swallows OSError — so the daemon flag serves HTTP 200 instead of
   EBADF connection-reset. Prefer the launchd plist route for durability;
   the Perl setsid route still works for the user-shell detach.

10. **Mirror staleness shows as FAIL/old data** — if the mirror's
    verify_delivery.py / zips drift from the repo (e.g. a repack),
    the dashboard runs stale checks. Re-run step 4
    (`sync_verify_mirror.sh` / `update_preview.sh --mirror`) after CIKTI
    changes; `--mirror-check` proves the mirror is current.
    The refs check verdicts are network-dependent: `verified/total`
    (e.g. 46/54) and P1s from UNVERIFIED refs vary per run — the
    dashboard reflects the latest completed run honestly.
