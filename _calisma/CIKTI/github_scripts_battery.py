#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""github_scripts_battery.py — K16 self-test katmanı (github-script'ler için).

Çıkarılan `github_scripts/*.js` dosyalarını K12/K13 tarzında DENETLER:
her senaryo MOCK girdi (fixture dosyaları + mock REST yanıtları) kurar,
script'i `github_scripts_selftest.js` harness'ıyla gerçek Node'da çalıştırır
ve ÇIKTI EŞLEŞMESİNİ denetler: hangi REST çağrısı yapıldı (create/update/
delete, hangi comment_id), yorum body'si ne içeriyor, hangi etiket eklendi/
kaldırıldı, `core.setFailed` çağrıldı mı.

Fail-closed: beklenen davranıştan sapma (yanlış çağrı, eksik marker,
beklenmeyen setFailed) → senaryo FAIL → exit 1. Script çıkarımında yapılan
bir yeniden düzenleme davranışı değiştirirse bu battery yakalar.

Kullanım:
  python3 github_scripts_battery.py            # tüm senaryolar; exit 0/1
  python3 github_scripts_battery.py --json     # makine-okunur sonuç

verify_delivery.py K16 (`--check-github-scripts`) bunu subprocess'le koşar.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS = os.path.join(HERE, "github_scripts_selftest.js")

MARKER_STATUS = "<!-- stoic-hume-v5-pr-status -->"
MARKER_MANIFEST = "<!-- stoic-hume-v5-reproducibility-manifest -->"
MARKER_CFGDIFF = "<!-- stoic-hume-v5-config-diff -->"
MARKER_DRIFT = "<!-- stoic-hume-v5-config-drift -->"

REPO_URL = "https://github.com/mock-owner/mock-repo"


def _ctx(issue=1, run=42):
    return {
        "issue": {"number": issue},
        "repo": {"owner": "mock-owner", "repo": "mock-repo"},
        "runId": run,
        "payload": {"repository": {"html_url": REPO_URL}},
    }


# ── Senaryo tanımları ────────────────────────────────────────────────────────
# (name, script, fixtures: {rel: str}, context, labels, comments, expect)
# expect anahtarları:
#   ok              bool|None   script throw etmemeli (None = umursama)
#   set_failed      bool|None   core.setFailed beklentisi
#   call_counts     {fn: int}   belirtilen REST çağrı adetleri
#   body_contains   {fn: [str]} her alt dizi body'de olmalı (birleşik)
#   target_ids      {fn: [int]} update/delete hedef comment_id'leri
#   add_labels      [str]|None  issues.addLabels'e geçilen etiketler
#   remove_labels   [str]|None  issues.removeLabel'e geçilen etiket adları
#   console_any     [str]       console çıktısında en az birinde geçmeli
SCENARIOS = [
    # ── pr_status_comment.js ────────────────────────────────────────────────
    (
        "pr_status: bütçe OK + pre-commit temiz + yeni yorum",
        "pr_status_comment.js",
        {
            "budget/index.json": json.dumps({
                "runs": [{"source": "verify", "estimated_usd": 1.2,
                          "limit": 30, "tokens_est": 400000}],
                "method": "weighted"}),
            "precommit_findings/PRECOMMIT_RAPORU.json": json.dumps({
                "findings": [], "counts": {"hooks": 9, "passed": 9}}),
        },
        None, [], [],
        {
            "ok": True, "set_failed": False,
            "call_counts": {"issues.listComments": 1,
                            "issues.createComment": 1},
            "body_contains": {"issues.createComment": [
                "Bütçe: limit içinde", "$1.2 / $30",
                "Pre-commit: bulgu yok", "9/9 hook geçti",
                MARKER_STATUS]},
            "add_labels": [], "remove_labels": [],
        },
    ),
    (
        "pr_status: bütçe aşımı + P0/P1 + mevcut yorum güncelle + etiket senkronu",
        "pr_status_comment.js",
        {
            "budget/index.json": json.dumps({
                "failures": [{"source": "verify", "estimated_usd": 35.0,
                              "limit": 30, "tokens_est": 10000000}],
                "method": "weighted"}),
            "precommit_findings/PRECOMMIT_RAPORU.json": json.dumps({
                "findings": [
                    {"priority": "P0", "message": "bayat zip var"},
                    {"priority": "P1", "message": "hijyen uyarısı"}]}),
        },
        None, [],  # etiket yok → P0/P1 bulguları etiketi EKLEMELİ
        [{"id": 555, "body": "eski " + MARKER_STATUS}],
        {
            "ok": True, "set_failed": False,
            "call_counts": {"issues.updateComment": 1,
                            "issues.createComment": 0},
            "target_ids": {"issues.updateComment": [555]},
            "body_contains": {"issues.updateComment": [
                "Bütçe: limit aşıldı", "+$5.00 aşım",
                "P0 (1)", "bayat zip var", "P1 (1)", MARKER_STATUS]},
            "add_labels": ["precommit-p0", "precommit-p1"],
            "remove_labels": [],
        },
    ),
    (
        "pr_status: bütçe aşımı + CLI override → tek uyarı bloğu",
        "pr_status_comment.js",
        {
            "budget/index.json": json.dumps({
                "failures": [{"source": "verify", "estimated_usd": 35.0,
                              "limit": 30, "tokens_est": 10000000}],
                "method": "weighted",
                "cli_overrides": {
                    "warning": True,
                    "overrides": [{"key": "budget", "file_value": 30.0,
                                   "effective": 25.0}],
                }}),
            "precommit_findings/PRECOMMIT_RAPORU.json": json.dumps({
                "findings": [], "counts": {"hooks": 9, "passed": 9}}),
        },
        None, [], [],
        {
            "ok": True, "set_failed": False,
            "call_counts": {"issues.createComment": 1},
            "body_contains": {"issues.createComment": [
                "Bütçe: limit aşıldı", "+$5.00 aşım",
                "CLI override tespit edildi", "`budget`", "30 → 25",
                "aşımın olası nedeni", MARKER_STATUS]},
            "add_labels": [], "remove_labels": [],
        },
    ),
    (
        "pr_status: CLI override var ama aşım yok → bilgilendirme",
        "pr_status_comment.js",
        {
            "budget/index.json": json.dumps({
                "runs": [{"source": "verify", "estimated_usd": 1.2,
                          "limit": 30, "tokens_est": 400000}],
                "method": "weighted",
                "cli_overrides": {
                    "warning": True,
                    "overrides": [{"key": "budget", "file_value": 30.0,
                                   "effective": 25.0}],
                }}),
            "precommit_findings/PRECOMMIT_RAPORU.json": json.dumps({
                "findings": [], "counts": {"hooks": 9, "passed": 9}}),
        },
        None, [], [],
        {
            "ok": True, "set_failed": False,
            "call_counts": {"issues.createComment": 1},
            "body_contains": {"issues.createComment": [
                "Bütçe: limit içinde", "CLI override aktif",
                "`budget`", "30 → 25", MARKER_STATUS]},
            # Aşım yokken "aşımın olası nedeni" ifadesi OLMAMALI.
            "body_not_contains": {"issues.createComment": ["aşımın olası nedeni"]},
            "add_labels": [], "remove_labels": [],
        },
    ),
    (
        "pr_status: etiket fazlası temizlenir (P0 çözüldü, p1 etiketi kalmasın)",
        "pr_status_comment.js",
        {
            "budget/index.json": json.dumps({
                "runs": [{"source": "verify", "estimated_usd": 1.0,
                          "limit": 30, "tokens_est": 330000}],
                "method": "weighted"}),
            "precommit_findings/PRECOMMIT_RAPORU.json": json.dumps({
                "findings": [], "counts": {"hooks": 9, "passed": 9}}),
        },
        None,
        [{"name": "precommit-p0"}, {"name": "precommit-p1"}],  # bayat etiketler
        [],
        {
            "ok": True, "set_failed": False,
            "call_counts": {"issues.createComment": 1},
            "body_contains": {"issues.createComment": [
                "limit içinde", "bulgu yok", MARKER_STATUS]},
            "add_labels": [],
            "remove_labels": ["precommit-p0", "precommit-p1"],
        },
    ),
    (
        "pr_status: sidecar'lar yok → 'bulunamadı' rozetleri + yorum yine düşer",
        "pr_status_comment.js",
        {},  # budget/precommit fixture yok
        None, [], [],
        {
            "ok": True, "set_failed": False,
            "call_counts": {"issues.createComment": 1},
            "body_contains": {"issues.createComment": [
                "Bütçe: sidecar bulunamadı",
                "Pre-commit: rapor bulunamadı", MARKER_STATUS]},
            "add_labels": [], "remove_labels": [],
        },
    ),

    # ── label_gate.js ───────────────────────────────────────────────────────
    (
        "label_gate: precommit-p0 etiketi yok → PASS (setFailed yok)",
        "label_gate.js",
        {}, None, [], [],
        {"ok": True, "set_failed": False, "call_counts": {
            "issues.listLabelsOnIssue": 1},
         "console_any": ["precommit-p0 etiketi yok — P0 label gate PASS"]},
    ),
    (
        "label_gate: precommit-p0 etiketi var → setFailed (merge bloke)",
        "label_gate.js",
        {}, None, [{"name": "precommit-p0"}], [],
        {
            "ok": True, "set_failed": True,
            "call_counts": {"issues.listLabelsOnIssue": 1},
            "set_failed_contains": ["precommit-p0 etiketi var — P0 bulgusu"],
        },
    ),

    # ── manifest_comment.js ─────────────────────────────────────────────────
    (
        "manifest_comment: K10 PASS + yeni yorum",
        "manifest_comment.js",
        {
            "reproducibility/manifest.txt":
                "github_run_id: 12345\ngithub_sha: abcdef\n\n== FILES ==\n"
                "a.txt 00aa\n",
            "k10_verdict.txt": "PASS",
        },
        None, [], [],
        {
            "ok": True, "set_failed": False,
            "call_counts": {"issues.createComment": 1},
            "body_contains": {"issues.createComment": [
                "K10 manifest digest: PASS", "github_run_id: 12345",
                "== FILES ==", MARKER_MANIFEST,
                "actions/runs/12345"]},
        },
    ),
    (
        "manifest_comment: CLI override uyarısı yoruma girer",
        "manifest_comment.js",
        {
            "reproducibility/manifest.txt": "github_run_id: 999\n",
            "k10_verdict.txt": "PASS",
            "reproducibility/cli_overrides_version.json": json.dumps({
                "tool": "check_cli_overrides.py", "warning": True,
                "override_count": 1,
                "overrides": [{"key": "budget", "file_value": 30.0,
                               "effective": 25.0}],
                "summary": "CLI override TESPİT EDİLDİ (1 parametre)"}),
        },
        None, [], [],
        {
            "ok": True, "set_failed": False,
            "call_counts": {"issues.createComment": 1},
            "body_contains": {"issues.createComment": [
                "CLI override TESPİT EDİLDİ", "`budget`", "30 → 25",
                "tekrarlanabilirlik sapması", MARKER_MANIFEST]},
            # override dosyası YOKSA yorumda uyarı bölümü olmamalı (negatif
            # kontrol ayrı senaryoda; burada yalnızca pozitif kanıt).
        },
    ),
    (
        "manifest_comment: K10 FAIL + mevcut yorum güncelle",
        "manifest_comment.js",
        {
            "reproducibility/manifest.txt": "github_run_id: 777\n",
            "k10_verdict.txt": "FAIL",
        },
        None, [],
        [{"id": 777, "body": "önceki " + MARKER_MANIFEST}],
        {
            "ok": True, "set_failed": False,
            "call_counts": {"issues.updateComment": 1,
                            "issues.createComment": 0},
            "target_ids": {"issues.updateComment": [777]},
            "body_contains": {"issues.updateComment": [
                "K10 manifest digest: FAIL", MARKER_MANIFEST]},
        },
    ),
    (
        "manifest_comment: manifest.txt yok → yorum atlanır (REST çağrısı yok)",
        "manifest_comment.js",
        {}, None, [], [],
        {"ok": True, "set_failed": False,
         "call_counts": {"issues.listComments": 0,
                         "issues.createComment": 0},
         "console_any": ["atlanıyor"]},
    ),

    # ── config_diff_comment.js ──────────────────────────────────────────────
    (
        "config_diff: fark var + yeni yorum",
        "config_diff_comment.js",
        {
            "reproducibility/config/config-diff.json": json.dumps({
                "differences": [{
                    "field": "expected_pages", "raw": 33, "effective": 34,
                    "reason": "paket yeniden üretildi"}]}),
        },
        None, [], [],
        {
            "ok": True, "set_failed": False,
            "call_counts": {"issues.createComment": 1},
            "body_contains": {"issues.createComment": [
                "expected_pages", "33", "34",
                "paket yeniden üretildi",
                "bloke etmez", MARKER_CFGDIFF]},
        },
    ),
    (
        "config_diff: mevcut yorum güncelle",
        "config_diff_comment.js",
        {
            "reproducibility/config/config-diff.json": json.dumps({
                "differences": [{"field": "budget_usd", "raw": 30,
                                 "effective": 35, "reason": "limit artırıldı"}]}),
        },
        None, [],
        [{"id": 888, "body": "eski " + MARKER_CFGDIFF}],
        {
            "ok": True, "set_failed": False,
            "call_counts": {"issues.updateComment": 1},
            "target_ids": {"issues.updateComment": [888]},
            "body_contains": {"issues.updateComment": [MARKER_CFGDIFF]},
        },
    ),
    (
        "config_diff: fark yok + bayat yorum varsa SİLİNİR",
        "config_diff_comment.js",
        {"reproducibility/config/config-diff.json":
            json.dumps({"differences": []})},
        None, [],
        [{"id": 888, "body": "bayat " + MARKER_CFGDIFF}],
        {
            "ok": True, "set_failed": False,
            "call_counts": {"issues.deleteComment": 1,
                            "issues.createComment": 0},
            "target_ids": {"issues.deleteComment": [888]},
            "console_any": ["bayat yorum kaldırıldı"],
        },
    ),
    (
        "config_diff: config-diff.json yok → atlanır (REST çağrısı yok)",
        "config_diff_comment.js",
        {}, None, [], [],
        {"ok": True, "set_failed": False,
         "call_counts": {"issues.listComments": 0},
         "console_any": ["atlanıyor"]},
    ),

    # ── config_drift_comment.js ─────────────────────────────────────────────
    (
        "config_drift: exit 1 + bulgular + yeni yorum",
        "config_drift_comment.js",
        {
            "drift_rc.txt": "1",
            "drift_stderr.txt": "expected_pages: config 33, paket 34",
            "config-drift/cli_overrides_version.json": json.dumps({
                "tool": "check_cli_overrides.py", "warning": False,
                "override_count": 0, "overrides": [],
                "config_read": True, "summary": "CLI override YOK"}),
        },
        None, [], [],
        {
            "ok": True, "set_failed": False,
            "call_counts": {"issues.createComment": 1},
            "body_contains": {"issues.createComment": [
                "Config drift tespit edildi", "exit `1`",
                "expected_pages: config 33, paket 34",
                "CLI override: yok (config değerleriyle tutarlı ✓)",
                "gen_config.py", MARKER_DRIFT]},
        },
    ),
    (
        "config_drift: mevcut yorum güncelle",
        "config_drift_comment.js",
        {
            "drift_rc.txt": "2",
            "drift_stderr.txt": "manifest sayısı uyuşmuyor",
        },
        None, [],
        [{"id": 999, "body": "eski " + MARKER_DRIFT}],
        {
            "ok": True, "set_failed": False,
            "call_counts": {"issues.updateComment": 1},
            "target_ids": {"issues.updateComment": [999]},
            "body_contains": {"issues.updateComment": [
                "exit `2`", MARKER_DRIFT]},
        },
    ),
    (
        "config_drift: CLI override warning + drift ayrı satırlar",
        "config_drift_comment.js",
        {
            "drift_rc.txt": "1",
            "drift_stderr.txt": "expected_pages: config 33, paket 34",
            "config-drift/cli_overrides_version.json": json.dumps({
                "tool": "check_cli_overrides.py", "warning": True,
                "override_count": 1,
                "overrides": [{"key": "budget", "file_value": 30,
                               "effective": 25}],
                "config_read": True,
                "summary": "CLI override VAR (tekrarlanabilirlik sapması)"}),
        },
        None, [], [],
        {
            "ok": True, "set_failed": False,
            "call_counts": {"issues.createComment": 1},
            "body_contains": {"issues.createComment": [
                "Config drift tespit edildi", "exit `1`",
                "CLI override tespit edildi (tekrarlanabilirlik sapması)",
                "`budget`: 30 → 25 (CLI verildi)",
                MARKER_DRIFT]},
        },
    ),
]


def _run_scenario(node, script, fixture_dir, timeout=30):
    """Harness'ı koş; (returncode, parsed JSON record) döndür."""
    r = subprocess.run(
        [node, HARNESS, script, fixture_dir],
        capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        return r, None
    try:
        return r, json.loads(r.stdout)
    except json.JSONDecodeError:
        return r, None


def _check_expect(rec, expect):
    """Kaydı beklenen davranışla eşleştir; (ok, problems[]) döndür."""
    problems = []
    if expect.get("ok") and not rec.get("ok"):
        problems.append(f"script throw: {rec.get('error')}")
    exp_failed = expect.get("set_failed")
    if exp_failed is not None and exp_failed != bool(rec.get("setFailed")):
        problems.append(
            f"setFailed: beklenen {exp_failed}, gerçek {bool(rec.get('setFailed'))}")
    for sub in (expect.get("set_failed_contains") or []):
        if not any(sub in msg for msg in rec.get("setFailed") or []):
            problems.append(f"setFailed mesajı '{sub}' yok")

    calls = rec.get("calls") or []
    counts = {}
    bodies = {}
    targets = {}
    added, removed = [], []
    for c in calls:
        fn = c.get("fn")
        counts[fn] = counts.get(fn, 0) + 1
        args = c.get("args") or {}
        if "body" in args:
            bodies.setdefault(fn, []).append(args["body"])
        if "comment_id" in args:
            targets.setdefault(fn, []).append(args["comment_id"])
        if fn == "issues.addLabels":
            added.extend(args.get("labels") or [])
        if fn == "issues.removeLabel":
            removed.append(args.get("name"))

    for fn, n in (expect.get("call_counts") or {}).items():
        if counts.get(fn, 0) != n:
            problems.append(
                f"{fn}: {counts.get(fn, 0)} çağrı, beklenen {n}")

    for fn, subs in (expect.get("body_contains") or {}).items():
        joined = "".join(bodies.get(fn, []))
        for s in subs:
            if s not in joined:
                problems.append(f"{fn} body '{s}' yok")

    for fn, subs in (expect.get("body_not_contains") or {}).items():
        joined = "".join(bodies.get(fn, []))
        for s in subs:
            if s in joined:
                problems.append(f"{fn} body '{s}' OLMAMALI ama var")

    for fn, ids in (expect.get("target_ids") or {}).items():
        for tid in targets.get(fn, []):
            if tid not in ids:
                problems.append(
                    f"{fn} comment_id {tid}, beklenen {ids}")

    exp_add = expect.get("add_labels")
    if exp_add is not None and sorted(added) != sorted(exp_add):
        problems.append(f"addLabels: gerçek {sorted(added)}, beklenen {sorted(exp_add)}")
    exp_rm = expect.get("remove_labels")
    if exp_rm is not None and sorted(removed) != sorted(exp_rm):
        problems.append(f"removeLabel: gerçek {sorted(removed)}, beklenen {sorted(exp_rm)}")

    for sub in (expect.get("console_any") or []):
        if not any(sub in line for line in rec.get("console") or []):
            problems.append(f"console '{sub}' yok")

    return not problems, problems


def run_battery(node=None, scripts_dir=None, timeout=30):
    """Tüm senaryoları koş; [(name, ok, detail)] döndür.

    node yoksa her senaryo (False, 'node bulunamadı') ile raporlanır —
    çağıran (verify_delivery.py K16 / test) fail-closed kararı verir.
    """
    node = node or shutil.which("node")
    if not node:
        # launchd GUI agent PATH'i minimal; Homebrew node bilinen
        # konumlardan (verify_delivery.py K16 fallback'iyle aynı).
        for cand in ("/opt/homebrew/bin/node", "/usr/local/bin/node",
                     "/home/linuxbrew/.linuxbrew/bin/node"):
            if os.path.isfile(cand) and os.access(cand, os.X_OK):
                node = cand
                break
    scripts_dir = scripts_dir or os.path.join(HERE, "github_scripts")
    results = []
    for name, script, fixtures, ctx, labels, comments, expect in SCENARIOS:
        script_path = os.path.join(scripts_dir, script)
        if node is None:
            results.append((name, False, "node bulunamadı"))
            continue
        with tempfile.TemporaryDirectory(prefix="gscripts_") as tmp:
            for rel, data in fixtures.items():
                fp = os.path.join(tmp, rel)
                os.makedirs(os.path.dirname(fp), exist_ok=True)
                with open(fp, "w", encoding="utf-8") as f:
                    f.write(data)
            if ctx is not None:
                with open(os.path.join(tmp, "mock_context.json"), "w",
                          encoding="utf-8") as f:
                    json.dump(ctx, f)
            if labels is not None:
                with open(os.path.join(tmp, "mock_labels.json"), "w",
                          encoding="utf-8") as f:
                    json.dump(labels, f)
            if comments is not None:
                with open(os.path.join(tmp, "mock_comments.json"), "w",
                          encoding="utf-8") as f:
                    json.dump(comments, f)
            try:
                r, rec = _run_scenario(node, script_path, tmp, timeout=timeout)
            except (OSError, subprocess.TimeoutExpired) as e:
                results.append((name, False, f"harness çalışmadı: {e}"))
                continue
            if rec is None:
                results.append(
                    (name, False,
                     f"harness exit={r.returncode}: "
                     f"{(r.stderr or r.stdout or '').strip()[:200]}"))
                continue
            ok, problems = _check_expect(rec, expect)
            detail = "; ".join(problems) if problems else (
                f"{sum(1 for c in rec['calls'] if c['fn'].startswith('issues.'))}"
                f" REST çağrısı eşleşti")
            results.append((name, ok, detail))
    return results


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true",
                    help="makine-okunur sonuç (JSON)")
    args = ap.parse_args(argv)

    results = run_battery()
    n_ok = sum(1 for _, ok, _ in results if ok)
    n_total = len(results)
    if args.json:
        print(json.dumps({
            "layer": "K16",
            "scenarios": n_total,
            "passed": n_ok,
            "failed": n_total - n_ok,
            "results": [
                {"name": n, "ok": o, "detail": d} for n, o, d in results],
        }, ensure_ascii=False, indent=2))
    else:
        for name, ok, detail in results:
            print(f"  [{'PASS' if ok else 'FAIL'}] {name} — {detail}")
        print(f"SONUÇ: {'PASS' if n_ok == n_total else 'FAIL'} — "
              f"{n_ok}/{n_total} senaryo")
    return 0 if n_ok == n_total else 1


if __name__ == "__main__":
    sys.exit(main())
