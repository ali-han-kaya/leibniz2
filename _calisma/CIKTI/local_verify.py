#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""local_verify.py — yerel ortamı TEK komuta indirir: taze derleme + kapılar + ağaç envanteri.

Neden var: yerel doğrulama parçalıdır. `make verify` bataryayı koşar ama
dashboard-next derlemesinin TAZE olduğunu söylemez; `pre-commit run --all-files`
tüm kapıları koşar ama hangi dosyaların ağaçta durduğunu ve derlemenin kaynakların
gerisinde kalıp kalmadığını söylemez. Ayrı ayrı koşulduğunda biri sessizce
atlanır ve "yeşil" yanılsaması doğar (aynı gerekçe: `verify_sweep.py`).

Adımlar (sıra nedenseldir; fail-fast KAPALI — tek turda tüm kırıkları gör):

  1. env    `bash _calisma/dev_bootstrap.sh --check` — araç-kümeleri tam mı
            (fail-closed; eksikse sonraki adımların SKIP'leri yanıltıcı olur).
  2. build  dashboard-next `.next` derlemesini TAZELE: `BUILD_ID` kaynaklardan
            eskiyse (ya da derleme yoksa) `npm run build` koşar, sonra TAZELİĞİ
            YENİDEN ÖLÇER. `--rebuild` koşulsuz derler. Tazelik mantığı
            `test_surface_cwv_report`'tan import edilir (tek kaynak; CWV kapısı
            bayat derlemeyi ölçmeyi reddeder).
  3. sweep  `verify_sweep.py --only <build hariç tüm adımlar> --verbose` —
            adım listesi import edilir, kopyalanmaz: süpürmeye yeni bir kapı
            eklendiğinde burası otomatik kapsar.
  4. hooks  `pre-commit run --all-files` — commit zincirinin TAMAMI (63 hook).
            Varsayılan AÇIK; `--fast` atlar ve bunu verdict'te "atlandı" diye
            yazar (sessiz kapsam daralması yok).
  5. tree   çalışma ağacı envanteri: stage'li / işlenmemiş / takipsiz dosyalar,
            dizin dağılımı ve KARMA durum (aynı dosya hem stage hem işlenmemiş →
            commit'i `check-unstaged-delta` bloklar). Kapılar ağacı değiştirirse
            (auto-edit hook'ları) FARK ayrıca raporlanır.

Exit: 0 = tüm seçilen adımlar PASS, 1 = ≥1 adım FAIL, 2 = kullanım hatası.
`--json`: stdout'ta TEK JSON belgesi; teşhis/uyarılar stderr'e (repo kuralı).

Kullanım:
  python3 _calisma/CIKTI/local_verify.py                 # tam koşum
  python3 _calisma/CIKTI/local_verify.py --fast          # hooks adımını atla
  python3 _calisma/CIKTI/local_verify.py --rebuild       # derlemeyi zorla
  python3 _calisma/CIKTI/local_verify.py --only build,tree
  python3 _calisma/CIKTI/local_verify.py --dry-run       # plan + ağaç, koşum yok
  python3 _calisma/CIKTI/local_verify.py --json
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import subprocess
import sys
import time
from typing import Callable, Dict, List, NamedTuple, Optional, Sequence, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import verify_sweep  # noqa: E402  — adım listesi TEK kaynaktan

# Dashboard-next derleme tazeliği: CWV kapısının kendi yardımcıları (tek kural).
import test_surface_cwv_report as cwv  # noqa: E402

# Süpürme adımlarından `build` HARİÇ: derleme burada, tazelik ölçümüyle yapılır.
SWEEP_ONLY = ",".join(step.name for step in verify_sweep.STEPS
                      if step.name != "build")
SWEEP_CMD = ["python3", "_calisma/CIKTI/verify_sweep.py",
             "--only", SWEEP_ONLY, "--verbose"]
HOOKS_CMD = ["pre-commit", "run", "--all-files"]
BOOTSTRAP_CMD = ["bash", "_calisma/dev_bootstrap.sh", "--check"]
NEXT_BUILD_CMD = ["npm", "run", "build", "--prefix", "apps/dashboard-next"]

TAIL_LINES = 15
DEFAULT_MAX_PATHS = 25


class Step(NamedTuple):
    """Bir adım: ad + hedef + (iç adım ise) argv; cmd boşsa fonksiyon koşar."""

    name: str
    label: str
    cmd: List[str]


STEPS: List[Step] = [
    Step("env", "araç-kümeleri (dev_bootstrap --check)", list(BOOTSTRAP_CMD)),
    Step("build", "dashboard-next derlemesini tazele", list(NEXT_BUILD_CMD)),
    Step("sweep", "doğrulama süpürmesi (verify_sweep, build hariç)", list(SWEEP_CMD)),
    Step("hooks", "commit zinciri (pre-commit --all-files)", list(HOOKS_CMD)),
    Step("tree", "çalışma ağacı envanteri", []),
]
STEP_NAMES = tuple(step.name for step in STEPS)


# ─────────────────────────────────────────────────────────── koşucular


def run_command(cmd: Sequence[str], cwd: str, verbose: bool = False
                ) -> Tuple[int, str]:
    """Varsayılan koşucu: (rc, çıktı-kuyruğu).

    Çıktı SATIR SATIR okunur: `verbose` iken anında akar (dakikalarca süren
    batarya/zincir için ilerleme görünür) ve aynı anda son satırlar kuyrukta
    tutulur — FAIL bloğunda boş bir `--- sweep (rc=1) ---` kalmasın (bir kez
    ölçüldü: kırık adımın sebebi yalnız akışta kaldığı için raporda görünmedi).

    `OSError` (komut yok) çağıranda kırık adım sayılır — süpürme çökmez.
    """
    proc = subprocess.Popen(list(cmd), cwd=cwd, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, bufsize=1)
    tail = collections.deque(maxlen=TAIL_LINES * 8)
    try:
        for line in proc.stdout:
            tail.append(line.rstrip("\n"))
            if verbose:
                print(line, end="", flush=True)
    finally:
        proc.stdout.close()
        rc = proc.wait()
    return rc, "\n".join(tail)


def _tail_text(text: str, lines: int = TAIL_LINES) -> str:
    meaningful = [line for line in (text or "").splitlines() if line.strip()]
    return "\n".join(meaningful[-lines:])


# ──────────────────────────────────── dashboard-next tazelik / yenileme


def build_freshness(next_dir: Optional[str] = None,
                    build_id: Optional[str] = None,
                    inputs=None) -> Dict:
    """Disktaki `.next` derlemesinin kaynaklara göre durumu (ölçüm, karar değil).

    `inputs` verilmezse `cwv.build_input_files()` taranır (üretilmiş ağaçlar
    hariç; `public/` ve paylaşılan design-system CSS'i dahil).
    """
    next_dir = cwv.NEXT_DIR if next_dir is None else next_dir
    build_id = cwv.NEXT_BUILD_ID if build_id is None else build_id
    if not os.path.isfile(build_id):
        return {"exists": False, "build_id": None, "stamp": None,
                "sources": 0, "stale": []}
    inputs = cwv.build_input_files(next_dir) if inputs is None else inputs
    stamp, stale = cwv.stale_sources(build_id, inputs)
    with open(build_id, encoding="utf-8") as f:
        build_id_value = f.read().strip()
    return {"exists": True, "build_id": build_id_value, "stamp": stamp,
            "sources": len(inputs), "stale": list(stale)}


def _stale_detail(state: Dict, limit: int = 5) -> str:
    if not state["stale"]:
        return ""
    shown = ", ".join("%s (%s)" % (rel, cwv._age_label(age))
                      for age, rel in state["stale"][:limit])
    more = "" if len(state["stale"]) <= limit else \
        " … +%d dosya" % (len(state["stale"]) - limit)
    return shown + more


def refresh_build(runner: Callable = run_command,
                  next_dir: Optional[str] = None,
                  build_id: Optional[str] = None,
                  inputs=None, force: bool = False,
                  verbose: bool = False) -> Dict:
    """Derlemeyi gerekirse tazeler ve TAZELİĞİ YENİDEN ölçer (fail-closed).

    Dönen kayıt: {"ok", "rebuilt", "detail", "state", "rc"}.
    Kural: taze derlemede npm ÇAĞRILMAZ (idempotent); derleme sonrası hâlâ
    bayatsa FAIL — "build koştu" tek başına yeşil değildir.
    """
    next_dir = cwv.NEXT_DIR if next_dir is None else next_dir
    build_id = cwv.NEXT_BUILD_ID if build_id is None else build_id
    state = build_freshness(next_dir, build_id, inputs)
    if state["exists"] and not force and not state["stale"]:
        return {"ok": True, "rebuilt": False, "rc": 0, "state": state,
                "detail": "derleme taze (build_id=%s, %d kaynak)" % (
                    state["build_id"], state["sources"])}
    if force:
        reason = "--rebuild verildi"
    elif not state["exists"]:
        reason = "derleme yok"
    else:
        reason = "%d kaynak daha yeni: %s" % (
            len(state["stale"]), _stale_detail(state))
    rc, output = runner(list(NEXT_BUILD_CMD), ROOT, verbose)
    if rc != 0:
        return {"ok": False, "rebuilt": True, "rc": rc, "state": state,
                "detail": "derleme BAŞARISIZ (%s):\n%s" % (
                    reason, _tail_text(output))}
    state = build_freshness(next_dir, build_id, inputs)
    if not state["exists"] or state["stale"]:
        detail = ("derleme sonrası hâlâ bayat (%d kaynak daha yeni: %s)"
                  % (len(state["stale"]), _stale_detail(state))
                  if state["exists"] else "derleme sonrası BUILD_ID yok")
        return {"ok": False, "rebuilt": True, "rc": 0, "state": state,
                "detail": detail}
    return {"ok": True, "rebuilt": True, "rc": 0, "state": state,
            "detail": "yeniden derlendi (%s) → taze (build_id=%s, %d kaynak)"
                      % (reason, state["build_id"], state["sources"])}


# ────────────────────────────────────────── çalışma ağacı envanteri


def _parse_name_status(raw: str) -> List[Tuple[str, str]]:
    """`git diff --name-status -z` çıktısı → [(status, yol)].

    `-z` biçiminde rename/copy iki yol taşır (`R100\0eski\0yeni\0`); yeni yol
    raporlanır, aksi halde çıktı tek kayar ve sahte yollar üretirdi.
    """
    parts = [p for p in (raw or "").split("\0")]
    entries: List[Tuple[str, str]] = []
    index = 0
    while index < len(parts):
        status = parts[index].strip()
        index += 1
        if not status:
            continue
        if status[0] in ("R", "C"):
            if index + 1 >= len(parts):
                break
            entries.append((status, parts[index + 1]))
            index += 2
        else:
            if index >= len(parts):
                break
            entries.append((status, parts[index]))
            index += 1
    return entries


def _git_reader(root: str) -> Callable:
    def read(args: Sequence[str]) -> Tuple[int, str]:
        try:
            proc = subprocess.run(["git", *args], cwd=root, capture_output=True,
                                  text=True)
        except OSError as exc:  # git yok
            return 127, str(exc)
        return proc.returncode, proc.stdout or ""
    return read


def working_tree_inventory(root: str, read: Optional[Callable] = None) -> Dict:
    """Stage'li / işlenmemiş / takipsiz dosyalar + KARMA (çakışan) küme.

    Okuma yetmezse (git yok / repo değil) `error` alanı dolar — envanter
    "boş ağaç" diye sessizce yanlış raporlanmaz.
    """
    read = _git_reader(root) if read is None else read
    staged_rc, staged_raw = read(["diff", "--cached", "--name-status", "-z"])
    unstaged_rc, unstaged_raw = read(["diff", "--name-status", "-z"])
    untracked_rc, untracked_raw = read(
        ["ls-files", "--others", "--exclude-standard", "-z"])
    if staged_rc or unstaged_rc or untracked_rc:
        return {"error": "git okunamadı (rc=%s/%s/%s)" % (
            staged_rc, unstaged_rc, untracked_rc),
            "staged": [], "unstaged": [], "untracked": [], "mixed": []}
    staged = _parse_name_status(staged_raw)
    unstaged = _parse_name_status(unstaged_raw)
    untracked = [p for p in (untracked_raw or "").split("\0") if p]
    staged_paths = {path for _status, path in staged}
    unstaged_paths = {path for _status, path in unstaged}
    return {
        "staged": staged,
        "unstaged": unstaged,
        "untracked": sorted(untracked),
        "mixed": sorted(staged_paths & unstaged_paths),
    }


def _status_counts(entries: Sequence[Tuple[str, str]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for status, _path in entries:
        key = status[0]
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _directory_rollup(paths: Sequence[str]) -> List[Tuple[str, int]]:
    """İlk iki yol bileşenine göre sayım (``_calisma/CIKTI`` gibi).

    Kök dosyaları kendi adıyla görünür (``README.md``); daha derin yollar ilk
    iki bileşende toplanır — 300 dosyalık bir envanterde tek tek dizin adları
    okunaksız olurdu.
    """
    counts: Dict[str, int] = {}
    for path in paths:
        parts = path.split("/")
        key = "/".join(parts[:2]) if len(parts) > 2 else "/".join(parts[:1])
        counts[key] = counts.get(key, 0) + 1
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))


def render_inventory(inventory: Dict, max_paths: int = DEFAULT_MAX_PATHS,
                     heading: str = "ÇALIŞMA AĞACI") -> List[str]:
    """İnsan-okunur envanter. `max_paths=0` → tüm yollar (kesme yok)."""
    lines: List[str] = []
    if inventory.get("error"):
        return ["%s: ÖLÇÜLEMEDİ — %s" % (heading, inventory["error"])]
    staged = inventory["staged"]
    unstaged = inventory["unstaged"]
    untracked = inventory["untracked"]
    mixed = inventory["mixed"]
    total = len(staged) + len(unstaged) + len(untracked)
    lines.append("%s — %d dosya (stage %d · işlenmemiş %d · takipsiz %d)" % (
        heading, total, len(staged), len(unstaged), len(untracked)))
    for label, entries in (("stage", staged), ("işlenmemiş", unstaged)):
        counts = _status_counts(entries)
        if counts:
            lines.append("  %-10s %s" % (
                label, " · ".join("%s %d" % (k, v) for k, v in counts.items())))
    if untracked:
        lines.append("  takipsiz   %d (gitignore dışı yeni dosya)"
                     % len(untracked))
    if mixed:
        lines.append(
            "  KARMA      %d dosya hem stage hem işlenmemiş — commit'i "
            "`check-unstaged-delta` bloklar:" % len(mixed))
        for path in mixed[:_shown(max_paths)]:
            lines.append("    %s" % path)
    # Dizin dağılımı BENZERSİZ yollar üzerinden: hem stage hem işlenmemiş
    # olan dosya iki kez sayılırsa "docs (11)" gibi gerçek olmayan bir sayı
    # çıkar (ağaçta 10 dosya var).
    all_paths = sorted({path for _status, path in staged}
                       | {path for _status, path in unstaged}
                       | set(untracked))
    rollup = _directory_rollup(all_paths)
    if rollup:
        lines.append("  dizinler   " + " · ".join(
            "%s (%d)" % (name, count) for name, count in rollup[:8]))
    for label, entries in (("stage", staged), ("işlenmemiş", unstaged)):
        if not entries:
            continue
        shown = _shown(max_paths)
        lines.append("  %s dosyaları%s:" % (
            label, "" if shown >= len(entries) else
            " (ilk %d / %d)" % (shown, len(entries))))
        for status, path in entries[:shown]:
            lines.append("    %-4s %s" % (status, path))
    if untracked:
        shown = _shown(max_paths)
        lines.append("  takipsiz dosyalar%s:" % (
            "" if shown >= len(untracked) else
            " (ilk %d / %d)" % (shown, len(untracked))))
        for path in untracked[:shown]:
            lines.append("    ?    %s" % path)
    return lines


def _shown(max_paths: int) -> int:
    return max_paths if max_paths and max_paths > 0 else 10 ** 9


def inventory_paths(inventory: Dict) -> List[str]:
    """Envanterdeki tüm yollar (kapıların yan etkisini karşılaştırmak için)."""
    paths = [path for _status, path in inventory.get("staged") or []]
    paths += [path for _status, path in inventory.get("unstaged") or []]
    paths += list(inventory.get("untracked") or [])
    return sorted(set(paths))


def tree_signature(inventory: Dict, root: str = ROOT) -> Dict[str, List[int]]:
    """Değişen dosyaların (boyut, mtime_ns) imzası — hook yan etkisi gözcüsü.

    Yalnız YOL kümesini karşılaştırmak yetmez: auto-edit bir hook genellikle
    ZATEN değişmiş bir dosyayı (ör. README changelog satırı) düzenler, o zaman
    `git status` aynı kalır. Content hash yerine boyut+mtime: 800+ dosyalık
    ağaçta okuma maliyeti yok ve hook'un yazımı bu imzayı mutlaka değiştirir.
    """
    signature: Dict[str, List[int]] = {}
    for path in inventory_paths(inventory):
        try:
            stat = os.stat(os.path.join(root, path))
        except OSError:
            continue  # silinmiş dosya: yol farkı zaten yakalar
        signature[path] = [stat.st_size, stat.st_mtime_ns]
    return signature


def inventory_delta(before: Dict, after: Dict,
                    before_sig: Optional[Dict] = None,
                    after_sig: Optional[Dict] = None
                    ) -> Dict[str, List[str]]:
    """Kapılar ağacı değiştirdi mi: eklenen / çıkan / İÇERİĞİ değişen yollar."""
    before_paths = set(inventory_paths(before))
    after_paths = set(inventory_paths(after))
    modified: List[str] = []
    if before_sig is not None and after_sig is not None:
        modified = sorted(path for path in before_paths & after_paths
                          if before_sig.get(path) != after_sig.get(path))
    return {"added": sorted(after_paths - before_paths),
            "removed": sorted(before_paths - after_paths),
            "modified": modified}


# ───────────────────────────────────────────────────────────── adımlar


def _step_env(runner, verbose) -> Dict:
    rc, output = runner(list(BOOTSTRAP_CMD), ROOT, verbose)
    detail = "" if rc == 0 else _tail_text(output)
    return {"rc": rc, "ok": rc == 0, "detail": detail}


def _step_sweep(runner, verbose) -> Dict:
    rc, output = runner(list(SWEEP_CMD), ROOT, verbose)
    detail = "" if rc == 0 else _tail_text(output)
    return {"rc": rc, "ok": rc == 0, "detail": detail}


def _step_hooks(runner, verbose) -> Dict:
    rc, output = runner(list(HOOKS_CMD), ROOT, verbose)
    if rc == 0:
        return {"rc": 0, "ok": True, "detail": ""}
    detail = _tail_text(output)
    if "files were modified" in (output or "").lower():
        detail += ("\nNOT: bir hook dosya düzenledi — değişikliği gözden "
                   "geçirip yeniden koşun (kapsam sessizce daralmaz).")
    return {"rc": rc, "ok": False, "detail": detail}


def select_steps(only: Optional[str]) -> List[str]:
    """`--only a,b`; bilinmeyen ad → [] (çağıran exit 2 verir)."""
    if not only:
        return list(STEP_NAMES)
    wanted = [part.strip() for part in only.split(",") if part.strip()]
    unknown = [name for name in wanted if name not in STEP_NAMES]
    if unknown:
        print("HATA: bilinmeyen adım: %s (geçerli: %s)" % (
            ", ".join(unknown), ", ".join(STEP_NAMES)), file=sys.stderr)
        return []
    keep = set(wanted)
    return [name for name in STEP_NAMES if name in keep]


def run_steps(names: Sequence[str], fast: bool = False, rebuild: bool = False,
              runner: Callable = run_command, reader: Optional[Callable] = None,
              verbose: bool = True, max_paths: int = DEFAULT_MAX_PATHS
              ) -> Tuple[List[Dict], Dict, Dict]:
    """Adımları sırayla koşar → (kayıtlar, ağaç_öncesi, ağaç_sonrası, fark)."""
    records: List[Dict] = []
    before = working_tree_inventory(ROOT, reader)
    before_sig = tree_signature(before)
    for index, name in enumerate(names, 1):
        started = time.monotonic()
        try:
            if name == "env":
                result = _step_env(runner, verbose)
                cmd = list(BOOTSTRAP_CMD)
            elif name == "build":
                result = refresh_build(runner=runner, force=rebuild,
                                       verbose=verbose)
                cmd = list(NEXT_BUILD_CMD)
            elif name == "sweep":
                result = _step_sweep(runner, verbose)
                cmd = list(SWEEP_CMD)
            elif name == "hooks":
                if fast:
                    result = {"rc": 0, "ok": True, "skipped": True,
                              "detail": "--fast: commit zinciri atlandı"}
                else:
                    result = _step_hooks(runner, verbose)
                cmd = list(HOOKS_CMD)
            else:  # tree
                result = {"rc": 0, "ok": True, "detail": "envanter aşağıda"}
                cmd = []
        except OSError as exc:
            # Komut yok/çalıştırılamaz → çökme değil KIRIK ADIM (süpürme
            # sözleşmesiyle aynı): kalan adımlar koşmaya devam eder.
            result = {"rc": 127, "ok": False,
                      "detail": "çalıştırılamadı: %s" % exc}
            cmd = []
        seconds = time.monotonic() - started
        record = {"name": name, "cmd": cmd, "seconds": round(seconds, 2)}
        record.update(result)
        records.append(record)
        if verbose:
            status = ("SKIP" if record.get("skipped")
                      else "PASS" if record["ok"] else "FAIL")
            print("[%d/%d] %-6s %s (%s, %.1fs)  %s" % (
                index, len(names), name, status, "rc=%s" % record["rc"],
                seconds, _label_for(name)), flush=True)
            # Detay yalnız KIRIK adımda (akış zaten geçti) ya da kısa build
            # hükmünde basılır; başarılı batarya kuyruğunu yeniden dökmek
            # rapordaki bilgiyi artırmıyor.
            if record.get("detail") and (not record["ok"] or name == "build"
                                          or record.get("skipped")):
                for line in str(record["detail"]).splitlines():
                    print("        %s" % line, flush=True)
    after = working_tree_inventory(ROOT, reader)
    delta = inventory_delta(before, after, before_sig, tree_signature(after))
    return records, before, after, delta


def _label_for(name: str) -> str:
    for step in STEPS:
        if step.name == name:
            return step.label
    return name


# ───────────────────────────────────────────────────────────────── CLI


def main(argv=None, runner: Callable = run_command,
         reader: Optional[Callable] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Yerel tek komut: taze dashboard-next derlemesi + tüm "
                    "kapılar + çalışma ağacı envanteri.")
    parser.add_argument("--list", action="store_true", help="adımları listele")
    parser.add_argument("--dry-run", action="store_true",
                        help="planı ve ağaç envanterini bas, adım koşma")
    parser.add_argument("--only", default=None,
                        help="yalnız bu adımlar (virgülle; ör. build,tree)")
    parser.add_argument("--fast", action="store_true",
                        help="commit zincirini (hooks) atla — verdict'te yazar")
    parser.add_argument("--rebuild", action="store_true",
                        help="derleme taze olsa da yeniden derle")
    parser.add_argument("--max-paths", type=int, default=DEFAULT_MAX_PATHS,
                        help="kategori başına gösterilecek yol (0 = tümü)")
    parser.add_argument("--json", action="store_true",
                        help="makine-okunur tek JSON belgesi (stdout)")
    args = parser.parse_args(argv)

    if args.list:
        for step in STEPS:
            print("%-6s %s" % (step.name, step.label))
            print("%-6s $ %s" % ("", " ".join(step.cmd) if step.cmd
                                 else "(iç adım)"))
        print("%-6s not: sweep adımı kapsamı = verify_sweep.STEPS - build"
              % "")
        print("%-6s      %s" % ("", SWEEP_ONLY))
        return 0

    names = select_steps(args.only)
    if not names:
        return 2

    if args.dry_run:
        print("LOCAL PLAN — %d adım (kök: %s)" % (len(names), ROOT))
        for index, name in enumerate(names, 1):
            step = next(s for s in STEPS if s.name == name)
            print("[%d/%d] %-6s $ %s" % (
                index, len(names), name,
                " ".join(step.cmd) if step.cmd else "(iç adım)"))
        if "hooks" in names and args.fast:
            print("[--] hooks  ATLANACAK (--fast)")
        for line in render_inventory(working_tree_inventory(ROOT, reader),
                                     args.max_paths):
            print(line)
        return 0

    if args.json:
        # JSON modunda adım günlüğü stderr'e: stdout TEK belge kalmalı.
        verbose, log = False, sys.stderr
    else:
        verbose, log = True, sys.stdout

    def emit(line=""):
        print(line, file=log, flush=True)

    emit("LOCAL DOĞRULAMA — kök: %s" % ROOT)
    if verbose:
        for line in render_inventory(working_tree_inventory(ROOT, reader),
                                     args.max_paths):
            emit(line)

    records, before, after, delta = run_steps(
        names, fast=args.fast, rebuild=args.rebuild, runner=runner,
        reader=reader, verbose=verbose, max_paths=args.max_paths)

    failed = [r for r in records if not r["ok"]]
    skipped = [r["name"] for r in records if r.get("skipped")]
    passed = not failed

    if verbose:
        if delta["added"] or delta["removed"] or delta.get("modified"):
            emit("")
            emit("KAPILAR AĞACI DEĞİŞTİRDİ (auto-edit hook'ları):")
            for path in delta["added"]:
                emit("  + %s" % path)
            for path in delta["removed"]:
                emit("  - %s" % path)
            for path in delta.get("modified") or []:
                emit("  ~ %s (içerik değişti)" % path)
        emit("")
        for line in render_inventory(after, args.max_paths,
                                     heading="ÇALIŞMA AĞACI (koşum sonrası)"):
            emit(line)
        emit("")
        total = round(sum(r["seconds"] for r in records), 1)
        if failed:
            for record in failed:
                emit("--- %s (rc=%s) ---" % (record["name"], record["rc"]))
                for line in str(record.get("detail") or "").splitlines():
                    emit(line)
            emit("LOCAL: FAIL — %d/%d adım başarısız (%s) · kırık: %s" % (
                len(failed), len(records), _seconds(total),
                ", ".join(r["name"] for r in failed)))
        else:
            emit("LOCAL: PASS — %d/%d adım yeşil (%s)%s" % (
                len(records), len(records), _seconds(total),
                " · atlanan: " + ", ".join(skipped) if skipped else ""))
    else:
        payload = {
            "verdict": "PASS" if passed else "FAIL",
            "root": ROOT,
            "steps": [
                {key: r.get(key) for key in ("name", "cmd", "rc", "ok",
                                            "skipped", "seconds", "detail")}
                for r in records
            ],
            "tree": _json_inventory(after),
            "tree_before": _json_inventory(before),
            "tree_changed": delta,
            "skipped": skipped,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if passed else 1


def _seconds(value: float) -> str:
    return "%.1fs" % value if value < 60 else "%.1fdk" % (value / 60.0)


def _json_inventory(inventory: Dict) -> Dict:
    return {
        "staged": [{"status": s, "path": p} for s, p in inventory["staged"]],
        "unstaged": [{"status": s, "path": p} for s, p in inventory["unstaged"]],
        "untracked": list(inventory["untracked"]),
        "mixed": list(inventory["mixed"]),
        "error": inventory.get("error"),
    }


if __name__ == "__main__":
    sys.exit(main())
