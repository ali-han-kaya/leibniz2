#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""precommit_doctor.py — her KIRMIZI hook'un sahibini işlenmemiş değişikliklere bağlar (read-only).

Neden
-----
"Commit her seferinde aynı kapılarla düşüyor; hangi işlenmemiş değişiklik
hangi kapıyı kırmızıya boyadı?" sorusunun elle izlenmesi uzun bir detour
doğurdu (mutlak-yol bulgusu, PUBLISH_SCENARIO diyagram bayatlığı, test
listesi drift'i tek tek elle eşleştirildi). Doctor bu kök-neden atfını
sistematikleştirir ve tekrarını önler.

Sözleşme
--------
* READ-ONLY: doctor hiçbir dosyayı stage/stash/edit ETMEZ; yalnız `git`
  okur ve `pre-commit run <id> --files …` çağırır (pre-commit kendi
  stash'ini kendisi yapar/geri koyar — normal koşumdaki gibi).
* Evren COMMIT-EŞDEĞER: `git diff --cached` = stage'li dosyalar. Unstaged
  ve takipsiz dosyalar SAHİPLİK etiketi olarak izlenir ama koşuma girmez;
  `--all-changes` ile ("bunu stage etsem kırmızıya döner mi") girer.
* Sahiplik iki kanıt derecesiyle raporlanır:
    - `cikti` : hook'un kendi kırmızı çıktısındaki dosya adı (güçlü).
      Çıkıntıda remedy/çözüm satırları hariç tutulur — çözüm satırındaki
      araç dosyası (ör. sync_check_unit_tests.py) SAHİP sayılmaz.
    - `desen` : hook'un AÇIK `files` deseniyle eşleşen adaylar (statik).
  Çıkıntıda kanıt yok ve daraltan `files` deseni yoksa kapı `sahipsiz`
  raporlanır — sahiplik asla uydurulmaz.
* Yan-etki gözcüsü: koşum öncesi/sonrası `git status` farkı alınır; bir
  hook koşum sırasında dosya değiştirdiyse bu BULGU olarak yazılır
  (doctor read-only'dir ama hook'lar değildir — sessiz yan etki yok).
* `--json`: stdout'ta TEK JSON doküman; tüm uyarılar stderr'e.
* Exit: 0 = hiçbir hook kırmızı değil (veya hiç stage'li dosya yok),
  1 = ≥1 kırmızı hook, 2 = ölçüm/kullanım hatası (pre-commit yok,
  config okunamadı, git hatası, bilinmeyen `--hook` id'si).

Sınırlar ( dürüstlük )
----------------------
* `types`/`types_or` filtreleri uygulanmaz — `desen` aday kümesi
  `files`+`exclude` ile yaklaşıklandırılır; `cikti` kanıtı bundan
  bağımsızdır.
* Kapsam pre-commit STAGE'edir (commit anı); pre-push kapıları koşmaz.
* Temiz/stage'siz ağaçta HEAD'de olası kırmızılar ölçülmez — o durum
  `pre-commit run --all-files` işidir (çıkıntıda bu not yazılır).
* Bazı kapılar dosya düzenler (commit anındaki gibi). Doctor bunu
  yakalar ve `yan_etkiler` bölümünde raporlar; kendisi yazmaz.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]  # _calisma/CIKTI -> repo kökü

# Rapor sınırları (çıktıyı sınırlı tut — bilgi kaybı değil, okunabilirlik).
OWNER_DISPLAY = 5      # metinde ilk kaç sahip gösterilir
CAND_DISPLAY = 8       # metinde ilk kaç aday gösterilir
TAIL_LINES = 30        # metinde kaç satır çıktı sonu
REMEDY_MAX = 2
REMEDY_WIDTH = 240
DEFAULT_TIMEOUT = 900  # hook başına saniye (pil süresi ~345s + pay)

# ── git okumaları ────────────────────────────────────────────────────────────


class GitError(RuntimeError):
    pass


def _git(args, root):
    proc = subprocess.run(["git", *args], cwd=str(root), capture_output=True,
                          text=True)
    if proc.returncode != 0:
        raise GitError(
            "git %s başarısız: %s" % (" ".join(args),
                                       (proc.stderr or "").strip() or proc.returncode))
    return proc.stdout


def _parse_name_status(blob):
    """`git … --name-status -z` -> [(harf, yol)]. R/C için yeni yol alınır."""
    tokens = [t for t in blob.split("\0")]
    while tokens and tokens[-1] == "":
        tokens.pop()
    out = []
    i = 0
    while i < len(tokens):
        letter = tokens[i][:1] or "?"
        if letter in ("R", "C"):
            if i + 2 >= len(tokens):
                break
            out.append((letter, tokens[i + 2]))
            i += 3
        else:
            if i + 1 >= len(tokens):
                break
            out.append((letter, tokens[i + 1]))
            i += 2
    return out


def git_states(root):
    """yol -> {staged: harf, unstaged: harf, untracked: True} (yalnız varolanlar)."""
    staged = _parse_name_status(
        _git(["diff", "--cached", "--name-status", "-z"], root))
    unstaged = _parse_name_status(
        _git(["diff", "--name-status", "-z"], root))
    untracked = [p for p in
                 _git(["ls-files", "--others", "--exclude-standard", "-z"],
                      root).split("\0") if p]
    states = {}
    for letter, path in staged:
        states.setdefault(path, {})["staged"] = letter
    for letter, path in unstaged:
        states.setdefault(path, {})["unstaged"] = letter
    for path in untracked:
        states.setdefault(path, {})["untracked"] = True
    return states


_STAGED_VERB = {
    "M": "değişiklik", "A": "ekleme", "D": "silme",
    "T": "tip-değişikliği", "R": "yeniden-adlandırma", "C": "kopya",
}


def state_label(entry):
    parts = []
    st = entry.get("staged")
    if st:
        verb = _STAGED_VERB.get(st, st)
        parts.append("stage'li(%s %s)" % (st, verb))
    us = entry.get("unstaged")
    if us:
        parts.append("unstaged(%s)" % us)
    if entry.get("untracked"):
        parts.append("takipsiz(??)")
    return " + ".join(parts) or "?"


# ── config ayrıştırma (stdlib — hook ortamında PyYAML olmayabilir) ───────────

_ID_RE = re.compile(r"^\s*-\s*id:\s*([A-Za-z0-9][A-Za-z0-9_.-]*)\s*$")
_REPO_RE = re.compile(r"^\s*-\s*repo:")
_FIELD_RE = {
    "name": re.compile(r"^\s*name:\s*(.*)$"),
    "files": re.compile(r"^\s*files:\s*(.*)$"),
    "exclude": re.compile(r"^\s*exclude:\s*(.*)$"),
    "pass_filenames": re.compile(r"^\s*pass_filenames:\s*(.*)$"),
    "always_run": re.compile(r"^\s*always_run:\s*(.*)$"),
}


def _yaml_scalar(raw):
    """YAML skalerini ham metne çevir (tek/tırnak kaçışları minimal)."""
    v = raw.strip()
    if not v or v.startswith("#"):
        return ""
    if len(v) >= 2 and v[0] == "'" and v[-1] == "'":
        return v[1:-1].replace("''", "'")
    if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
        return re.sub(r"\\(.)", r"\1", v[1:-1])
    if " #" in v:
        v = v.split(" #", 1)[0].rstrip()
    return v


def _as_bool(raw, default):
    v = _yaml_scalar(raw).lower()
    if v in ("true", "yes", "on"):
        return True
    if v in ("false", "no", "off"):
        return False
    return default


def _compile_patterns(value):
    """`files`/`exclude` değeri -> (desen-listesi | None). None = hepsini eşler."""
    if value is None:
        return None
    if isinstance(value, str):
        value = [value]
    compiled = []
    for pat in value:
        if pat == "":
            return None  # boş desen her şeyi eşler
        try:
            compiled.append(re.compile(pat))
        except re.error:
            return _PATTERN_ERROR  # ölçülemedi — çağıran dürüst raporlar
    return compiled


class _PatternErrorType:
    pass


_PATTERN_ERROR = _PatternErrorType()


def parse_hooks(text):
    """Config metninden hook kümesini sıra korunarak çıkarır.

    Her hook: {id, name, files(None|str|list), exclude, pass_filenames, always_run}.
    Ham skaler değerler korunur; derleme `hook_matches` içinde yapılır ki
    bozuk desen sessizce "eşleşmiyor"a çevrilmesin (ölçüm-notu olarak taşınır).
    """
    lines = text.splitlines()
    hooks = []
    for idx, start in enumerate([i for i, ln in enumerate(lines)
                                 if _ID_RE.match(ln)]):
        # blok: bu id satırından bir sonraki id/repo satırına kadar
        end = len(lines)
        for j in range(start + 1, len(lines)):
            if _ID_RE.match(lines[j]) or _REPO_RE.match(lines[j]):
                end = j
                break
        block = lines[start:end]
        hook = {"id": _ID_RE.match(lines[start]).group(1),
                "name": None, "files": None, "exclude": None,
                "pass_filenames": True, "always_run": False}
        for ln in block:
            for key, rx in _FIELD_RE.items():
                m = rx.match(ln)
                if m and hook.get("_%s_seen" % key) is None:
                    hook["_%s_seen" % key] = True
                    raw = m.group(1)
                    if key in ("pass_filenames", "always_run"):
                        hook[key] = _as_bool(raw, hook[key])
                    elif key == "name":
                        hook[key] = _yaml_scalar(raw) or None
                    else:
                        hook[key] = _yaml_scalar(raw) if raw.strip() else None
                    break
        for k in [k for k in hook if k.startswith("_")]:
            del hook[k]
        hooks.append(hook)
    return hooks


def hook_patterns(hook):
    """(files_compiled, exclude_compiled, files_error: bool).

    files=None (config'te yok) -> (None, …) = hepsini eşler.
    Desen bozuksa (_PATTERN_ERROR) -> files_error=True (kör eşleşme YOK).
    """
    files = hook.get("files")
    exclude = hook.get("exclude")
    if files is None:
        f_c, f_err = None, False
    else:
        fc = _compile_patterns(files)
        if fc is _PATTERN_ERROR:
            f_c, f_err = None, True
        else:
            f_c, f_err = fc, False
    ex_c = _compile_patterns(exclude) if exclude is not None else None
    if ex_c is _PATTERN_ERROR:
        ex_c = None
    return f_c, ex_c, f_err


def hook_matches(hook, path):
    f_c, ex_c, _ = hook_patterns(hook)
    if f_c is not None and not any(f.search(path) for f in f_c):
        return False
    if ex_c is not None and any(e.search(path) for e in ex_c):
        return False
    return True


# ── pre-commit yürütücüsü ────────────────────────────────────────────────────


def resolve_runner(root):
    """En az bir pre-commit kurulumu bul -> komut öneki; yoksa None."""
    candidates = [[sys.executable, "-m", "pre_commit"]]
    which = shutil.which("pre-commit")
    if which:
        candidates.append([which])
    venv_py = Path(root) / "_calisma" / ".venv_z3" / "bin" / "python"
    if venv_py.is_file():
        candidates.append([str(venv_py), "-m", "pre_commit"])
    for cmd in candidates:
        try:
            probe = subprocess.run(cmd + ["--version"], capture_output=True)
        except OSError:
            continue
        if probe.returncode == 0:
            return cmd
    return None


def make_runner(cmd, root, timeout=DEFAULT_TIMEOUT):
    """runner(hook_id, files) -> (rc, output). Süre aşımı rc=124 + not."""

    def runner(hook_id, files):
        args = list(cmd) + ["run", hook_id, "--color", "never"]
        # Evren daima stage'li dosyalardan gelir (run_doctor erken-çıkışı
        # boş evrende hiç hook koşturmaz) — --files her koşumda verilir ki
        # pre-commit hiçlikte sürpriz bir --all-files davranışı yapmasın.
        args += ["--files", *files]
        try:
            proc = subprocess.run(args, cwd=str(root), capture_output=True,
                                  text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return 124, "SÜRE AŞIMI: %s hook %ss içinde bitmedi\n" % (
                hook_id, timeout)
        return proc.returncode, proc.stdout + proc.stderr

    return runner


# ── atf (attribution) ────────────────────────────────────────────────────────

_REMEDY_RE = re.compile(r"çözüm|cozum|remedy", re.I)
_PATHISH_RE = re.compile(
    r"\S+\.(?:py|js|mjs|ts|tsx|yml|yaml|md|sh|json|list|excalidraw|html|"
    r"css|svg|lean|tex|zip|plist)\b")


def extract_remedies(output, limit=REMEDY_MAX):
    """Çözüm satırını (gerekirse girintili adım bloğuyla birlikte) çıkarır.

    Başlık biçimi `Çözüm:` ise altındaki girintili adımlar da alınır —
    tek başına bir BAŞLIK çözüm değildir. `Çözüm:`/`remedy:` öneki kırpılır
    ki rapor etiketi aynı öneki ikinci kez yazmasın.
    """
    out = []
    lines = output.splitlines()
    i = 0
    while i < len(lines) and len(out) < limit:
        s = lines[i].strip()
        if _REMEDY_RE.search(s):
            block = [re.sub(r"^(?:çözüm|cozum|remedy)\s*:\s*", "", s,
                            flags=re.I).strip()]
            if s.rstrip().endswith(":"):
                j = i + 1
                while j < len(lines) and len(block) < 4:
                    nxt = lines[j]
                    if nxt.strip() and nxt[:1] in (" ", "\t"):
                        block.append(nxt.strip())
                        j += 1
                    else:
                        break
            joined = " ".join(b for b in block if b)[:REMEDY_WIDTH]
            if joined and joined not in out:
                out.append(joined)
        i += 1
    return out


def _causal_output(output):
    """Remedy/çözüm satırlarını boşaltır (çözüm satırındaki Araç SAHİP sayılmaz)."""
    keep = []
    for line in output.splitlines():
        if _REMEDY_RE.search(line):
            keep.append("")
        else:
            keep.append(line)
    return "\n".join(keep)


def _boundary_ok(output, pos, length):
    """Eşleşme sınırı: öncesi `[\w/]` ya da sonrası `[\w]` ise bu bir
    alt-süzülmedir (`other/docs/x.md` içindeki `docs/x.md` sahip DEĞİL)."""
    before = output[pos - 1] if pos > 0 else ""
    after = output[pos + length] if pos + length < len(output) else ""
    if before and re.match(r"[\w/]", before):
        return False
    if after and re.match(r"[\w]", after):
        return False
    return True


def extract_owners(output, states):
    """Çıkıntıda geçen İŞLENMEMİŞ dosyaları ilk geçiş sırasıyla döndürür.

    İki tur: (1) tam repo-yolu alt_dizesi (sınır-kontrollü), (2) yalnız
    dosya adı (token, `(?<![\w/])…(?![\w])` ile). Remedy satırları hariç
    (`_causal_output` ile çağrılmadan kullanılmamalı).
    """
    hits = []  # (pos, path)
    for path in states:
        pos = output.find(path)
        if pos >= 0 and _boundary_ok(output, pos, len(path)):
            hits.append((pos, path))
    found = {p for _, p in hits}
    by_base = {}
    for path in states:
        if path in found:
            continue
        by_base.setdefault(path.rsplit("/", 1)[-1], []).append(path)
    for base, paths in by_base.items():
        for m in re.finditer(r"(?<![\w/])%s(?![\w])" % re.escape(base),
                             output):
            for path in paths:
                hits.append((m.start(), path))
            break  # aynı ad ilk geçtiğinde yeterli (sıra korunur)
    best = {}
    for pos, path in hits:
        if path not in best or pos < best[path]:
            best[path] = pos
    return [p for p, _ in sorted(best.items(), key=lambda kv: kv[1])]


def attribute(hook, output, states, run_paths):
    """Bir kırmızı hook için sahip/aday/kanıt kararı (dürüst hiyerarşi)."""
    causal = _causal_output(output)
    owner_paths = extract_owners(causal, states)
    owners = [{"path": p, "state": state_label(states[p]), "proof": "cikti"}
              for p in owner_paths]

    f_c, _ex, f_err = hook_patterns(hook)
    has_explicit = f_c is not None
    candidates = []
    if has_explicit:
        for p in run_paths:
            if p in states and hook_matches(hook, p):
                candidates.append({"path": p,
                                   "state": state_label(states[p])})

    if owners:
        verdict = "sahipli"
    elif has_explicit and candidates:
        verdict = "aday"
    else:
        verdict = "sahipsiz"

    notes = []
    if f_err:
        notes.append("hook'un `files` deseni DERLENEMEDİ — aday atfı "
                     "yapılmadı (kör eşleşme yok)")
    if not owners:
        mentioned = [t for t in _PATHISH_RE.findall(causal)
                     if t not in states]
        if mentioned:
            notes.append("çıktıda dosya ad(lar)ı geçti ama hiçbiri "
                         "işlenmemiş değil (COMMITTED olabilir): "
                         + ", ".join(sorted(set(mentioned))[:5]))
    return {
        "verdict": verdict,
        "owners": owners,
        "candidates": candidates[:CAND_DISPLAY * 4],
        "candidates_total": len(candidates),
        "notes": notes,
        "remedy": extract_remedies(output),
        "output_tail": output.splitlines()[-TAIL_LINES:],
    }


# ── orkestrasyon ─────────────────────────────────────────────────────────────


def _snapshot(states, keys):
    return {p: {k: states[p].get(k) for k in keys}
            for p in states if any(states[p].get(k) is not None
                                   for k in keys)}


def run_doctor(root, config_path, runner, include_unstaged=False,
               only=None, skip=None):
    """Ölçüm. Döner (rc, report). rc 0/1/2 — modül sözleşmesinde."""
    report = {
        "ok": False, "rc": 0, "root": str(root),
        "config": str(config_path), "runner": None,
        "universe": {}, "hooks_run": 0, "red": [], "clean": [],
        "yan_etkiler": [], "note": None, "error": None,
    }
    try:
        states = git_states(root)
    except GitError as exc:
        report["error"] = "git okunamadı: %s" % exc
        return 2, report
    report["states_count"] = len(states)
    try:
        text = Path(config_path).read_text(encoding="utf-8")
    except OSError as exc:
        report["error"] = "config okunamadı: %s" % exc
        return 2, report
    hooks = parse_hooks(text)
    if not hooks:
        report["error"] = "config'te hook id'si bulunamadı: %s" % config_path
        return 2, report
    by_id = {h["id"]: h for h in hooks}
    order = [h["id"] for h in hooks]
    if only:
        unknown = [i for i in only if i not in by_id]
        if unknown:
            report["error"] = "bilinmeyen hook id: %s" % ", ".join(unknown)
            return 2, report
        ids = [i for i in order if i in set(only)]
    else:
        ids = list(order)
    if skip:
        ids = [i for i in ids if i not in set(skip)]

    staged = sorted(p for p, e in states.items() if e.get("staged"))
    unstaged_only = sorted(p for p, e in states.items()
                           if e.get("unstaged") and not e.get("staged"))
    untracked_only = sorted(p for p, e in states.items()
                            if e.get("untracked") and not e.get("staged"))
    universe = list(staged)
    if include_unstaged:
        universe += [p for p in unstaged_only + untracked_only]
    report["universe"] = {
        "stage'li": len(staged),
        "unstaged-only": len(unstaged_only),
        "takipsiz-only": len(untracked_only),
        "kosum": len(universe),
        "include_unstaged": bool(include_unstaged),
    }
    if not universe:
        report["note"] = (
            "stage'li dosya yok — commit hiçbir kapıya dosya taşımaz; "
            "HEAD'de olası kırmızılar için `pre-commit run --all-files` "
            "kullanın (doctor kapsamı dışı).")
        report["ok"] = True
        return 0, report

    before = _snapshot(states, ("staged", "unstaged", "untracked"))
    for hid in ids:
        t0 = time.monotonic()
        rc, out = runner(hid, universe)
        dur = round(time.monotonic() - t0, 2)
        if rc == 0:
            report["clean"].append(hid)
            continue
        item = {"id": hid, "name": by_id[hid].get("name"), "exit": rc,
                "duration": dur}
        item.update(attribute(by_id[hid], out, states, universe))
        if rc not in (1, 124):
            item["notes"] = item.get("notes", []) + [
                "beklenmeyen çıkış kodu: %s" % rc]
        report["red"].append(item)
    report["hooks_run"] = len(ids)

    try:
        after_states = git_states(root)
        after = _snapshot(after_states, ("staged", "unstaged", "untracked"))
    except GitError as exc:
        report["yan_etkiler"] = [{"path": "?", "note": "son-okuma başarısız: %s" % exc}]
    else:
        touched = [p for p in sorted(set(before) | set(after))
                   if before.get(p) != after.get(p)]
        report["yan_etkiler"] = [
            {"path": p,
             "once": state_label(before[p]) if p in before else "yok",
             "sonra": state_label(after[p]) if p in after else "kayboldu"}
            for p in touched]

    report["ok"] = not report["red"]
    report["rc"] = 0 if report["ok"] else 1
    return report["rc"], report


# ── rapor ────────────────────────────────────────────────────────────────────


def _owner_line(o):
    return "%s  [%s]" % (o["path"], o["state"])


def render(report):
    lines = ["PRE-COMMIT DOKTOR (read-only) — kırmızı hook → sahip atfı"]
    u = report.get("universe") or {}
    if u:
        extra = ""
        if not u.get("include_unstaged"):
            extra = (" · unstaged-only %d + takipsiz-only %d koşuma girmez "
                     "(--all-changes ile girer)"
                     % (u.get("unstaged-only", 0), u.get("takipsiz-only", 0)))
        lines.append("  evren  : stage'li %d = koşum yüzeyi%s"
                     % (u.get("kosum", 0), extra))
    if report.get("runner"):
        lines.append("  runner : %s" % report["runner"])
    if report.get("error"):
        lines.append("  HATA   : %s" % report["error"])
        return lines
    if report.get("note"):
        lines.append("  NOT    : %s" % report["note"])
    red = report.get("red", [])
    lines.append("  koşulan: %d hook · kırmızı %d · yeşil %d"
                 % (report.get("hooks_run", 0), len(red),
                    len(report.get("clean", []))))
    for i, item in enumerate(red, 1):
        head = "RED %d/%d: %s" % (i, len(red), item["id"])
        if item.get("name"):
            head += " — %s" % item["name"]
        lines.append(head)
        verdict = item["verdict"]
        if verdict == "sahipli":
            owners = item["owners"]
            lines.append("  SAHİP (kanıt: hook çıktısı) — %d dosya:"
                         % len(owners))
            for o in owners[:OWNER_DISPLAY]:
                lines.append("    %s" % _owner_line(o))
            if len(owners) > OWNER_DISPLAY:
                lines.append("    … +%d daha (--json ile tam liste)"
                             % (len(owners) - OWNER_DISPLAY))
        elif verdict == "aday":
            lines.append("  ADAY (kanıt: files deseni) — %d eşleşen "
                         "işlenmemiş değişiklik:" % item["candidates_total"])
            for c in item["candidates"][:CAND_DISPLAY]:
                lines.append("    %s  [%s]" % (c["path"], c["state"]))
            if item["candidates_total"] > CAND_DISPLAY:
                lines.append("    … +%d daha" %
                             (item["candidates_total"] - CAND_DISPLAY))
        else:
            lines.append("  SAHİPSIZ — çıkıntıda dosya kanıtı yok ve "
                         "daraltan `files` deseni yok (ağaç-durumu/ölçüm "
                         "kapısı olabilir; çıktı sonuna bakın)")
        for note in item.get("notes", []):
            lines.append("  NOT    : %s" % note)
        for r in item.get("remedy", []):
            lines.append("  ÇÖZÜM  : %s" % r)
        lines.append("  (çıktı sonu — %d satır):" % len(item["output_tail"]))
        lines.extend("    %s" % ln for ln in item["output_tail"][-8:])
    if red:
        lines.append("ÖZET — hook → sahip:")
        for item in red:
            if item["verdict"] == "sahipli":
                first = item["owners"][0]["path"]
                more = "" if len(item["owners"]) == 1 else \
                    " (+%d dosya)" % (len(item["owners"]) - 1)
                lines.append("  %s → %s  [%s]%s"
                             % (item["id"], first,
                                item["owners"][0]["state"], more))
            elif item["verdict"] == "aday":
                lines.append("  %s → %d aday (desen kanıtı; "
                             "çıktıda dosya yok)" % (item["id"],
                                                    item["candidates_total"]))
            else:
                lines.append("  %s → SAHİPSIZ (kanıt yok — çıktıyı okuyun)"
                             % item["id"])
    if report.get("yan_etkiler"):
        lines.append("YAN ETKİ — koşum sırasında değişen dosyalar "
                     "(doctor yazmadı, hook yazdı):")
        for t in report["yan_etkiler"][:10]:
            lines.append("  %s: %s → %s" % (t["path"], t["once"], t["sonra"]))
        lines.append("  → değişen dosyaları gözden geçirip `git add` edin.")
    else:
        lines.append("YAN ETKİ: yok (koşum öncesi/sonrası git durumu aynı).")
    if report.get("error"):
        return lines
    if report.get("ok"):
        lines.append("SONUÇ: TEMİZ — kırmızı hook yok.")
    else:
        counts = {"sahipli": 0, "aday": 0, "sahipsiz": 0}
        for item in red:
            counts[item["verdict"]] = counts.get(item["verdict"], 0) + 1
        lines.append("SONUÇ: KIRMIZI — %d hook (sahipli %d, aday %d, "
                     "sahipsiz %d)" % (len(red), counts["sahipli"],
                                       counts["aday"], counts["sahipsiz"]))
    return lines


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Kırmızı pre-commit hook'larını işlenmemiş "
                    "değişikliklere bağlar (read-only; "
                    "stage/stash/edit YOK).")
    ap.add_argument("--root", default=str(ROOT), help="repo kökü")
    ap.add_argument("--config", default=None,
                    help="pre-commit config (varsayılan: <root>/.pre-commit-config.yaml)")
    ap.add_argument("--hook", action="append", default=None,
                    metavar="ID", help="yalnız bu hook'u koş (tekrarlanabilir)")
    ap.add_argument("--skip", action="append", default=None,
                    metavar="ID", help="bu hook'u atla (tekrarlanabilir)")
    ap.add_argument("--all-changes", action="store_true",
                    help="unstaged-only ve takipsiz dosyaları da koşuma kat")
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT,
                    help="hook başına saniye (varsayılan %d)" % DEFAULT_TIMEOUT)
    ap.add_argument("--json", action="store_true",
                    help="stdout'ta TEK JSON doküman (uyarılar stderr)")
    args = ap.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        print("HATA: --root dizin değil: %s" % root, file=sys.stderr)
        return 2
    config = Path(args.config) if args.config else root / ".pre-commit-config.yaml"
    cmd = resolve_runner(root)
    if cmd is None:
        msg = ("pre-commit bulunamadı (sys.executable modülü, PATH ve "
               "_calisma/.venv_z3 denendi) — pip install pre-commit")
        if args.json:
            print(json.dumps({"ok": False, "rc": 2, "error": msg},
                             ensure_ascii=False, indent=2))
        else:
            print("HATA: %s" % msg, file=sys.stderr)
        return 2
    runner = make_runner(cmd, root, timeout=args.timeout)

    rc, report = run_doctor(root, config, runner,
                            include_unstaged=args.all_changes,
                            only=args.hook, skip=args.skip)
    report["runner"] = " ".join(cmd)

    if args.json:
        report["rc"] = rc
        report["ok"] = rc == 0
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return rc
    for line in render(report):
        print(line)
    return rc


if __name__ == "__main__":
    sys.exit(main())
