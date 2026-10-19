#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_scope_contract_drift.py — HEAD ↔ worktree kapsam sözleşmesi meta-kapısı.

Kapsam sözleşmesi üç dosyada yaşar:

  1. `test_coverage_report.py` → `HOOK_COVERAGE`  (hook → koştuğu test dosyaları)
  2. `test_coverage_report.py` → `CHECK_EXEMPT`   (bilinçli olarak hooksuz testler)
  3. `check_unit_tests.list`    → commit'te koşan batarya manifesti

Bu modül, HEAD revizyonundaki sözleşme ile worktree'deki sözleşmeyi karşılaştırır
ve farkları **liste halinde** yazar. Amaç, tek tek dosyaların kendi içinde
tutarlı olduğu (`sync_check_unit_tests.py --check` yeşil) ama kapsamın sessizce
DARALDIĞI durumu yakalamaktır: bir test manifestten çıkarılıp EXCLUDE'a alınır,
bir hook kaydı silinir ya da bir dosya CHECK_EXEMPT'e taşınır — üçü de iç
tutarlılık kontrollerinden geçer, yalnızca **geçmişe bakınca** kapsam kaybı
olduğu görülür.

KAPI KURALI (asimetrik — bu yüzden meşru eklemeler commit'i bloklamaz):

  * EKLEMELER raporlanır, commit'i bloklamaz (yeni test dosyası, yeni hook kaydı).
  * KAPSAM KAYBI bloklar: HEAD'de bir hook/manifest tarafından kapsanan ve
    worktree'de hâlâ DİSKTE DURAN bir dosya, worktree'de hiçbir hook/manifest
    tarafından kapsanmıyorsa (CHECK_EXEMPT'e taşınmış olması dahil) FAIL.
  * Dosya silinmiş/yeniden adlandırılmışsa kayıp sayılmaz — kapsam nesnesi
    ortadan kalkmıştır, kapı bunu "silinmiş" diye raporlar.
  * Başka bir hook'a taşınan dosya kayıp sayılmaz (`HOOK_COVERAGE` toplamı
    üzerinden ölçülür); yine de iki hook'un satırlarında görünür.

FAIL-CLOSED (ölçülemeyen durum "tam" sayılmaz):
  * git deposu değil / HEAD yok / `HEAD:<yol>` okunamıyor,
  * worktree sözleşme dosyası yok,
  * `HOOK_COVERAGE` tanımı yok ya da sözlük değil, girdiler sabit değil
    (`*LIST` / değişken adı → gizli kapsam ölçülemez),
  * sözdizimi hatası.

ÇALIŞMA MODU
  * unittest: `check_unit_tests.list` bataryasında koşar (dosya başına ayrı
    süreç). Pre-commit staged-ağacı çalıştırdığı için "worktree" = commit'in
    kendisi, "HEAD" = ebeveyn commit olur; kapı tam olarak commit'in kapsam
    delta'sını denetler. CI'da ağaç HEAD olduğundan fark boştur (PASS).
  * `python3 test_scope_contract_drift.py --check`  → fark listesini stdout'a
    yazdırır, kapsam kaybında exit 1 (ölçüm hatasında exit 2). Verdict stderr'e
    gider; stdout saf listedir (rapordan verdict ayıklamak gerekmez).
  * `python3 test_scope_contract_drift.py` (argümansız) → sözleşme testleri
    (`unittest.main()`); bu dosyanın tetiklediği scratch-repo testleri de koşar.

stdlib only; ağ yok. Gerçek ağaç testleri `compare()` ile canlı sözleşmeyi
ölçer; geri kalan testler izole scratch repo'larda koşar (kirli geliştirici
ağacı testi etkilemez).
"""

import argparse
import ast
import dataclasses
import contextlib
import io
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
CIKTI_REL = "_calisma/CIKTI"
COVERAGE_REL = f"{CIKTI_REL}/test_coverage_report.py"
MANIFEST_REL = f"{CIKTI_REL}/check_unit_tests.list"


class ContractError(RuntimeError):
    """Kapsam sözleşmesi ölçülemedi — kapı fail-closed davranır."""


# ────────────────────────────────────────────────────────────────────────────
# Sözleşme anlık görüntüsü
# ────────────────────────────────────────────────────────────────────────────


@dataclasses.dataclass(frozen=True)
class Snapshot:
    hooks: dict          # hook id → test dosyaları (sıra korunur)
    exempt: frozenset    # CHECK_EXEMPT
    manifest: tuple      # check_unit_tests.list girdileri (yorumlar hariç)


@dataclasses.dataclass(frozen=True)
class HookChange:
    hook: str
    added: tuple
    removed: tuple


@dataclasses.dataclass(frozen=True)
class CoverageLoss:
    file: str
    head_hooks: tuple    # HEAD'de kapsayan hook'lar (yoksa yalnız manifest)
    exempt_now: bool     # worktree'de CHECK_EXEMPT'e alınmış mı?


@dataclasses.dataclass
class Report:
    head_sha: str
    head: Snapshot
    worktree: Snapshot
    hooks_added: list
    hooks_removed: list
    hook_changes: list
    exempt_added: list
    exempt_removed: list
    manifest_added: list
    manifest_removed: list
    losses: list

    @property
    def has_changes(self):
        """Sözleşmenin herhangi bir yüzeyi HEAD'den farklı mı?"""
        return bool(
            self.hooks_added or self.hooks_removed or self.hook_changes
            or self.exempt_added or self.exempt_removed
            or self.manifest_added or self.manifest_removed
        )

    def lines(self):
        """Raporu satır listesi olarak döndürür (tek biçim: liste, serbest metin değil)."""
        if not self.has_changes:
            return ["KAPSAM SÖZLEŞMESİ: HEAD ile worktree aynı "
                    "(HOOK_COVERAGE, CHECK_EXEMPT, manifest)."]

        sha = (self.head_sha or "?")[:7]
        out = [f"KAPSAM SÖZLEŞMESİ — HEAD ({sha}) → worktree"]
        out.append(f"  HOOK_COVERAGE: {len(self.head.hooks)} → "
                   f"{len(self.worktree.hooks)} hook kaydı")
        for hook in self.hooks_added:
            out.append(f"    + hook: {hook}")
        for hook in self.hooks_removed:
            files = self.head.hooks.get(hook, ())
            suffix = f" (dosyaları: {', '.join(files)})" if files else ""
            out.append(f"    - hook: {hook}{suffix}")
        for change in self.hook_changes:
            out.append(f"    ~ {change.hook}: +{len(change.added)} / -{len(change.removed)}")
            for name in change.added:
                out.append(f"      + {name}")
            for name in change.removed:
                out.append(f"      - {name}")

        out.append(f"  CHECK_EXEMPT: {len(self.head.exempt)} → "
                   f"{len(self.worktree.exempt)} dosya")
        for name in self.exempt_added:
            out.append(f"    + {name}  (muafiyete alındı)")
        for name in self.exempt_removed:
            out.append(f"    - {name}  (muafiyetten çıkarıldı)")

        out.append(f"  MANIFEST: {len(self.head.manifest)} → "
                   f"{len(self.worktree.manifest)} girdi")
        for name in self.manifest_added:
            out.append(f"    + {name}")
        for name in self.manifest_removed:
            out.append(f"    - {name}")

        if self.losses:
            out.append(f"  KAPSAM KAYBI (FAIL): {len(self.losses)} dosya artık "
                       "hiçbir hook/manifest tarafından kapsanmıyor")
            for loss in self.losses:
                where = ", ".join(loss.head_hooks) or "(yalnız manifest)"
                now = "CHECK_EXEMPT" if loss.exempt_now else "hiçbiri"
                out.append(f"    ! {loss.file} — HEAD'te: {where}; "
                           f"worktree'de: {now}; dosya duruyor")
        return out


# ────────────────────────────────────────────────────────────────────────────
# Ayrıştırma — AST, import DEĞİL: HEAD içeriği import edilemez, ayrıca sabit
# olmayan girdi (gizli kapsam) burada fail-closed yakalanır.
# ────────────────────────────────────────────────────────────────────────────


def _module_value(tree, name):
    """Modül düzeyindeki son `<name> = ...` atamasını döndürür (yoksa None).

    Yalnız `tree.body` taranır: bir fonksiyonun içindeki yerel/örnek sözlük
    (test fixture'ı) sözleşme sanılmamalı.
    """
    value = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
                value = node.value
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == name:
                value = node.value
    return value


def _all_values(tree, name):
    """Modül düzeyi DAHİL tüm `<name> = ...` atamalarının değerleri.

    HEAD'in eski revizyonlarında `CHECK_EXEMPT` `main()` içinde yereldi; o
    tanım da etkin muafiyet sözleşmesidir, yok sayılırsa taban yanlış
    okunur (ölçüldü: HEAD'de 10 muafiyet "0" görünüyordu).
    """
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == name for t in node.targets):
            found.append(node.value)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == name:
                found.append(node.value)
    return found


def _const_str(node, label):
    if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
        raise ContractError(
            f"{label}: sabit olmayan girdi ({type(node).__name__}) — "
            "gizli kapsam ölçülemez (fail-closed)")
    return node.value


def _string_sequence(node, label, name):
    if not isinstance(node, (ast.List, ast.Tuple)):
        raise ContractError(f"{label}: {name} liste değil "
                            f"({type(node).__name__}) — kapsam ölçülemedi")
    return tuple(_const_str(el, label) for el in node.elts)


def parse_contract(coverage_src, manifest_src, label="sözleşme"):
    """İki metinden Snapshot üretir; ölçülemeyen her durum ContractError'dır."""
    try:
        tree = ast.parse(coverage_src, filename=label)
    except SyntaxError as exc:
        raise ContractError(
            f"{label}: sözdizimi hatası (satır {exc.lineno}: {exc.msg}) — "
            "kapsam sözleşmesi ölçülemedi")

    node = _module_value(tree, "HOOK_COVERAGE")
    if node is None:
        raise ContractError(f"{label}: HOOK_COVERAGE tanımı yok — "
                            "kapsam tabanı ölçülemedi")
    if not isinstance(node, ast.Dict):
        raise ContractError(f"{label}: HOOK_COVERAGE sözlük değil "
                            f"({type(node).__name__}) — ölçülemedi")
    hooks = {}
    for key, value in zip(node.keys, node.values):
        if key is None:
            raise ContractError(f"{label}: HOOK_COVERAGE içinde ** unpacking var — "
                                "girdiler ölçülemez")
        hook = _const_str(key, label)
        hooks[hook] = _string_sequence(value, label, f"HOOK_COVERAGE[{hook!r}]")

    exempt_node = _module_value(tree, "CHECK_EXEMPT")
    if exempt_node is None:
        # Bu ağaçta CHECK_EXEMPT henüz modül düzeyine taşınmamış olabilir
        # (HEAD'de `main()` içindeydi). Etkin tanımı bul; birden çok FARKLI
        # tanım varsa hangisinin sözleşme olduğu belirsizdir → fail-closed.
        candidates = _all_values(tree, "CHECK_EXEMPT")
        distinct = {ast.dump(c) for c in candidates}
        if len(distinct) > 1:
            raise ContractError(
                f"{label}: birden çok farklı CHECK_EXEMPT tanımı — "
                "hangisinin sözleşme olduğu ölçülemedi (fail-closed)")
        exempt_node = candidates[0] if candidates else None
    if exempt_node is None:
        # Eski revizyon: muafiyet sözleşmesi henüz yok → boş küme. (Fark
        # raporu yine görünür; fail-closed yalnız BOZUK tanım içindir.)
        exempt = frozenset()
    else:
        if isinstance(exempt_node, ast.Call):
            if not exempt_node.args:
                exempt_node = ast.Set(elts=[])
            elif len(exempt_node.args) == 1:
                exempt_node = exempt_node.args[0]
            else:
                raise ContractError(f"{label}: CHECK_EXEMPT çağrısı birden çok "
                                    "argüman alıyor — ölçülemedi")
        # `frozenset({})` boş bir SÖZLÜK literal'idir; boş küme semantiği
        # beklenir (Python'da `{}` set literal'i yoktur).
        if isinstance(exempt_node, ast.Dict) and not exempt_node.keys:
            exempt_node = ast.Set(elts=[])
        if not isinstance(exempt_node, (ast.Set, ast.List, ast.Tuple)):
            raise ContractError(f"{label}: CHECK_EXEMPT küme/liste değil "
                                f"({type(exempt_node).__name__}) — ölçülemedi")
        exempt = frozenset(_const_str(el, label) for el in exempt_node.elts)

    manifest = tuple(
        line.strip() for line in manifest_src.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )
    return Snapshot(hooks=hooks, exempt=exempt, manifest=manifest)


# ────────────────────────────────────────────────────────────────────────────
# Fark + kayıp ölçümü
# ────────────────────────────────────────────────────────────────────────────


def _covered(snapshot, subtract_exempt):
    files = set(snapshot.manifest)
    for entries in snapshot.hooks.values():
        files.update(entries)
    if subtract_exempt:
        files -= set(snapshot.exempt)
    return files


def diff_contracts(head, worktree, exists=None):
    """İki Snapshot'ı karşılaştırır; sıralı, deterministik bir Report döndürür.

    `exists(name)` worktree'de dosyanın hâlâ durup durmadığını söyler.
    Varsayılan (None) "duruyor" kabul eder — yani kayıp yönünde fail-closed.
    """
    head_hooks = set(head.hooks)
    wt_hooks = set(worktree.hooks)

    changes = []
    for hook in sorted(head_hooks & wt_hooks):
        added = tuple(sorted(set(worktree.hooks[hook]) - set(head.hooks[hook])))
        removed = tuple(sorted(set(head.hooks[hook]) - set(worktree.hooks[hook])))
        if added or removed:
            changes.append(HookChange(hook=hook, added=added, removed=removed))

    # HEAD tabanı: muafiyet düşülür (muaf dosya zaten "kapsanmıyor" sayılır).
    # worktree tarafında muafiyet DÜŞÜLMEZ: kapsanan bir dosyayı CHECK_EXEMPT'e
    # taşımak kapsam kaybıdır, muafiyet onu gizlemez.
    covered_head = _covered(head, subtract_exempt=True)
    covered_wt = _covered(worktree, subtract_exempt=False)

    losses = []
    for name in sorted(covered_head - covered_wt):
        if exists is not None and not exists(name):
            continue  # dosya silinmiş/yeniden adlandırılmış: kapsam nesnesi yok
        losses.append(CoverageLoss(
            file=name,
            head_hooks=tuple(h for h in sorted(head.hooks) if name in head.hooks[h]),
            exempt_now=name in worktree.exempt,
        ))

    return Report(
        head_sha="",
        head=head,
        worktree=worktree,
        hooks_added=sorted(wt_hooks - head_hooks),
        hooks_removed=sorted(head_hooks - wt_hooks),
        hook_changes=changes,
        exempt_added=sorted(worktree.exempt - head.exempt),
        exempt_removed=sorted(head.exempt - worktree.exempt),
        manifest_added=sorted(set(worktree.manifest) - set(head.manifest)),
        manifest_removed=sorted(set(head.manifest) - set(worktree.manifest)),
        losses=losses,
    )


# ────────────────────────────────────────────────────────────────────────────
# Git: HEAD tabanı ve worktree
# ────────────────────────────────────────────────────────────────────────────


def _git(root, *args, timeout=120):
    try:
        return subprocess.run(
            ["git", *args], cwd=str(root), capture_output=True, text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ContractError(f"git çalıştırılamadı ({exc}) — "
                            "kapsam sözleşmesi ölçülemedi")


def repo_root(start=None):
    root = pathlib.Path(start or HERE)
    res = _git(root, "rev-parse", "--show-toplevel")
    if res.returncode != 0 or not res.stdout.strip():
        raise ContractError(f"{root}: git deposu değil — "
                            "kapsam sözleşmesi ölçülemedi")
    return pathlib.Path(res.stdout.strip())


def head_text(root, rel):
    """`HEAD:<rel>` içeriği; dosya HEAD'de yoksa None. Ölçüm hatası → hata."""
    if _git(root, "rev-parse", "--verify", "--quiet", "HEAD").returncode != 0:
        raise ContractError("HEAD yok (henüz commit edilmemiş depo) — "
                            "kapsam tabanı ölçülemedi")
    if _git(root, "cat-file", "-e", f"HEAD:{rel}").returncode != 0:
        return None
    res = _git(root, "show", f"HEAD:{rel}")
    if res.returncode != 0:
        raise ContractError(f"HEAD:{rel} okunamadı — kapsam tabanı ölçülemedi: "
                            f"{res.stderr.strip()}")
    return res.stdout


def worktree_text(root, rel):
    path = pathlib.Path(root) / rel
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ContractError(f"{path} okunamadı ({exc}) — "
                            "kapsam sözleşmesi ölçülemedi")


def compare(root=None, coverage_rel=COVERAGE_REL, manifest_rel=MANIFEST_REL,
            exists=None):
    """HEAD ↔ worktree sözleşme farkını ölçer (tek giriş noktası).

    `root` verilmezse içinde bulunulan dosyanın deposu kullanılır; worktree
    kökü git'ten alınır (ayrık worktree'lerde doğru kök).
    """
    root = repo_root(root)  # verilen yol depo değilse fail-closed

    head_cov = head_text(root, coverage_rel)
    if head_cov is None:
        raise ContractError(f"HEAD:{coverage_rel} yok — kapsam tabanı ölçülemedi")
    head_manifest = head_text(root, manifest_rel) or ""
    head = parse_contract(head_cov, head_manifest, f"HEAD:{coverage_rel}")

    worktree = parse_contract(
        worktree_text(root, coverage_rel),
        worktree_text(root, manifest_rel),
        f"worktree:{coverage_rel}",
    )

    if exists is None:
        test_dir = pathlib.Path(root) / pathlib.Path(coverage_rel).parent

        def exists(name):
            return (test_dir / name).exists()

    report = diff_contracts(head, worktree, exists=exists)
    report.head_sha = _git(root, "rev-parse", "HEAD").stdout.strip()
    return report


# ────────────────────────────────────────────────────────────────────────────
# Testler — saf ayrıştırma/fark
# ────────────────────────────────────────────────────────────────────────────


def _cov(hooks, exempt=()):
    """Test için geçerli bir sözleşme kaynağı üretir."""
    lines = ["HOOK_COVERAGE = {"]
    for hook, entries in hooks.items():
        body = "".join(f'\n        "{name}",' for name in entries)
        lines.append(f'    "{hook}": [{body}\n    ],')
    lines.append("}")
    if exempt is not None:
        items = ", ".join(f'"{name}"' for name in sorted(exempt))
        lines.append(f"CHECK_EXEMPT = frozenset({{{items}}})" if items
                     else "CHECK_EXEMPT = frozenset()")
    return "\n".join(lines) + "\n"


def _manifest(*names):
    return "".join(f"{name}\n" for name in names)


def _snap(hooks, exempt=(), manifest=()):
    return parse_contract(_cov(hooks, exempt), _manifest(*manifest))


class TestParseContract(unittest.TestCase):
    """Sözleşme ayrıştırması ve fail-closed sınırları."""

    def test_parses_all_three_surfaces(self):
        snap = _snap({"check-unit-tests": ["test_a.py", "test_b.py"],
                      "other": ["test_c.py"]},
                     exempt=("test_c.py",),
                     manifest=("test_a.py", "test_b.py"))
        self.assertEqual(snap.hooks["check-unit-tests"], ("test_a.py", "test_b.py"))
        self.assertEqual(snap.exempt, frozenset({"test_c.py"}))
        self.assertEqual(snap.manifest, ("test_a.py", "test_b.py"))

    def test_manifest_skips_comments_and_blanks(self):
        src = "# başlık\n\ntest_a.py\n  # iç yorum\n test_b.py \n"
        snap = parse_contract(_cov({}), src, "test")
        self.assertEqual(snap.manifest, ("test_a.py", "test_b.py"))

    def test_missing_check_exempt_is_empty_not_error(self):
        snap = parse_contract(_cov({}, exempt=None), "", "test")
        self.assertEqual(snap.exempt, frozenset())

    def test_empty_check_exempt_call_is_empty(self):
        src = "HOOK_COVERAGE = {}\nCHECK_EXEMPT = frozenset()\n"
        self.assertEqual(parse_contract(src, "", "test").exempt, frozenset())

    def test_function_local_check_exempt_is_the_effective_contract(self):
        # HEAD'de (modül düzeyine taşınmadan önce) CHECK_EXEMPT `main()`
        # içindeydi. Taban 10 muafiyeti "0" okumamalı.
        src = ('HOOK_COVERAGE = {}\n'
               'def main():\n'
               '    CHECK_EXEMPT = frozenset({"test_a.py"})\n'
               '    return CHECK_EXEMPT\n')
        snap = parse_contract(src, "", "test")
        self.assertEqual(snap.exempt, frozenset({"test_a.py"}))

    def test_conflicting_check_exempt_definitions_fail_closed(self):
        src = ('HOOK_COVERAGE = {}\n'
               'def a():\n    CHECK_EXEMPT = frozenset({"test_a.py"})\n'
               'def b():\n    CHECK_EXEMPT = frozenset({"test_b.py"})\n')
        with self.assertRaises(ContractError) as ctx:
            parse_contract(src, "", "test")
        self.assertIn("birden çok farklı CHECK_EXEMPT", str(ctx.exception))

    def test_missing_hook_coverage_fails_closed(self):
        with self.assertRaises(ContractError) as ctx:
            parse_contract("CHECK_EXEMPT = frozenset()\n", "", "test")
        self.assertIn("HOOK_COVERAGE", str(ctx.exception))

    def test_variable_entry_fails_closed(self):
        # `*EXTRA` / değişken adı: metinden görülemeyen kapsam sessizce
        # eksik okunmamalı — ölçülemedi.
        src = ('HOOK_COVERAGE = {\n'
               '    "check-unit-tests": [*EXTRA],\n'
               '}\n'
               'CHECK_EXEMPT = frozenset()\n')
        with self.assertRaises(ContractError) as ctx:
            parse_contract(src, "", "test")
        self.assertIn("gizli kapsam", str(ctx.exception))

    def test_unpacked_hook_mapping_fails_closed(self):
        src = ('HOOK_COVERAGE = {\n'
               '    **EXTRA,\n'
               '}\n'
               'CHECK_EXEMPT = frozenset()\n')
        with self.assertRaises(ContractError) as ctx:
            parse_contract(src, "", "test")
        self.assertIn("unpacking", str(ctx.exception))

    def test_syntax_error_fails_closed(self):
        with self.assertRaises(ContractError) as ctx:
            parse_contract("HOOK_COVERAGE = {\n", "", "test")
        self.assertIn("sözdizimi", str(ctx.exception))

    def test_function_local_map_is_not_the_contract(self):
        # Modül düzeyinde sözleşme yoksa, fonksiyon içindeki yerel sözlük
        # sözleşme yerine geçmemeli (aksi halde kapı yanlış şeyi ölçer).
        src = ('def fixture():\n'
               '    HOOK_COVERAGE = {"x": ["test_a.py"]}\n'
               '    return HOOK_COVERAGE\n')
        with self.assertRaises(ContractError):
            parse_contract(src, "", "test")


class TestDiffContracts(unittest.TestCase):
    """Fark listesi ve kayıp kuralı (asimetrik kapı)."""

    def _exists(self, *present):
        present = set(present)
        return lambda name: name in present

    def test_identical_contracts_are_empty(self):
        snap = _snap({"check-unit-tests": ["test_a.py"]}, manifest=("test_a.py",))
        report = diff_contracts(snap, snap)
        self.assertFalse(report.has_changes)
        self.assertEqual(report.losses, [])
        self.assertIn("aynı", report.lines()[0])

    def test_reports_all_three_surfaces_as_list(self):
        head = _snap({"check-unit-tests": ["test_gone.py", "test_keep.py"],
                      "old-hook": ["test_old.py"]},
                     exempt=("test_ex_old.py",),
                     manifest=("test_gone.py", "test_keep.py"))
        wt = _snap({"check-unit-tests": ["test_keep.py", "test_new.py"],
                    "new-hook": ["test_new.py"]},
                   exempt=("test_ex_new.py",),
                   manifest=("test_keep.py", "test_new.py"))
        report = diff_contracts(head, wt, exists=self._exists("test_gone.py"))

        self.assertTrue(report.has_changes)
        self.assertEqual(report.hooks_added, ["new-hook"])
        self.assertEqual(report.hooks_removed, ["old-hook"])
        self.assertEqual(report.exempt_added, ["test_ex_new.py"])
        self.assertEqual(report.exempt_removed, ["test_ex_old.py"])
        self.assertEqual(report.manifest_added, ["test_new.py"])
        self.assertEqual(report.manifest_removed, ["test_gone.py"])

        lines = report.lines()
        self.assertIsInstance(lines, list)
        text = "\n".join(lines)
        for expected in ("HOOK_COVERAGE", "CHECK_EXEMPT", "MANIFEST",
                         "+ hook: new-hook", "- hook: old-hook",
                         "+ test_new.py", "- test_gone.py",
                         "- test_ex_old.py", "+ test_ex_new.py"):
            self.assertIn(expected, text)

    def test_removed_hook_files_are_listed(self):
        head = _snap({"old-hook": ["test_a.py"]})
        wt = _snap({})
        report = diff_contracts(head, wt, exists=self._exists("test_a.py"))
        self.assertEqual(report.hooks_removed, ["old-hook"])
        self.assertIn("(dosyaları: test_a.py)", "\n".join(report.lines()))

    def test_removal_with_missing_file_is_not_a_loss(self):
        head = _snap({"check-unit-tests": ["test_a.py"]}, manifest=("test_a.py",))
        wt = _snap({}, manifest=())
        report = diff_contracts(head, wt, exists=self._exists())  # dosya yok
        self.assertEqual(report.losses, [])
        self.assertTrue(report.has_changes)
        self.assertNotIn("KAPSAM KAYBI", "\n".join(report.lines()))

    def test_removal_with_existing_file_is_a_loss(self):
        head = _snap({"check-unit-tests": ["test_a.py"]}, manifest=("test_a.py",))
        wt = _snap({}, manifest=())
        report = diff_contracts(head, wt, exists=self._exists("test_a.py"))
        self.assertEqual([loss.file for loss in report.losses], ["test_a.py"])
        self.assertEqual(report.losses[0].head_hooks, ("check-unit-tests",))
        self.assertFalse(report.losses[0].exempt_now)
        text = "\n".join(report.lines())
        self.assertIn("KAPSAM KAYBI (FAIL)", text)
        self.assertIn("test_a.py — HEAD'te: check-unit-tests", text)

    def test_rehomed_to_other_hook_is_not_a_loss(self):
        head = _snap({"old-hook": ["test_a.py"]}, manifest=("test_a.py",))
        wt = _snap({"new-hook": ["test_a.py"]}, manifest=("test_a.py",))
        report = diff_contracts(head, wt, exists=self._exists("test_a.py"))
        self.assertEqual(report.losses, [])
        self.assertEqual(report.hooks_added, ["new-hook"])
        self.assertEqual(report.hooks_removed, ["old-hook"])

    def test_still_covered_by_another_hook_is_not_a_loss(self):
        # Yalnız manifestten düşmüş ama başka bir hook'ta duruyor (ör. kendi
        # hook'u olan test) → kapsam kaybı değil, batarya daralması olarak
        # raporda görünür.
        head = _snap({"check-unit-tests": ["test_a.py"],
                      "own-hook": ["test_a.py"]},
                     manifest=("test_a.py",))
        wt = _snap({"check-unit-tests": [],
                    "own-hook": ["test_a.py"]},
                   manifest=())
        report = diff_contracts(head, wt, exists=self._exists("test_a.py"))
        self.assertEqual(report.losses, [])
        self.assertEqual(report.manifest_removed, ["test_a.py"])
        self.assertIn("~ check-unit-tests: +0 / -1", "\n".join(report.lines()))

    def test_exempt_does_not_erase_existing_coverage(self):
        # Bir dosya hem hook'ta hem CHECK_EXEMPT'te olabilir (ör. kendi Node
        # hook'unda koşan .js testi). Muafiyet, FİİLEN koşan kapsamı silmez;
        # aksi halde kapı sahte kayıp üretir (mutasyonla ölçüldü).
        head = _snap({"check-unit-tests": ["test_a.py"]}, manifest=("test_a.py",))
        wt = _snap({"check-unit-tests": ["test_a.py"]}, exempt=("test_a.py",),
                   manifest=("test_a.py",))
        report = diff_contracts(head, wt, exists=self._exists("test_a.py"))
        self.assertEqual(report.losses, [])
        self.assertEqual(report.exempt_added, ["test_a.py"])

    def test_moving_covered_file_to_check_exempt_is_a_loss(self):
        head = _snap({"check-unit-tests": ["test_a.py"]}, manifest=("test_a.py",))
        wt = _snap({"check-unit-tests": []}, exempt=("test_a.py",))
        report = diff_contracts(head, wt, exists=self._exists("test_a.py"))
        self.assertEqual([loss.file for loss in report.losses], ["test_a.py"])
        self.assertTrue(report.losses[0].exempt_now)
        self.assertIn("worktree'de: CHECK_EXEMPT", "\n".join(report.lines()))

    def test_adding_new_test_and_hook_is_reported_not_failed(self):
        head = _snap({"check-unit-tests": ["test_a.py"]}, manifest=("test_a.py",))
        wt = _snap({"check-unit-tests": ["test_a.py", "test_new.py"],
                    "new-hook": ["test_new.py"]},
                   manifest=("test_a.py", "test_new.py"))
        report = diff_contracts(head, wt, exists=self._exists("test_a.py",
                                                              "test_new.py"))
        self.assertEqual(report.losses, [])
        self.assertTrue(report.has_changes)
        self.assertIn("+ test_new.py", "\n".join(report.lines()))

    def test_default_exists_is_fail_closed(self):
        # exists verilmezse dosya "duruyor" sayılır → kapsam kaybı raporlanır.
        head = _snap({"check-unit-tests": ["test_a.py"]}, manifest=("test_a.py",))
        wt = _snap({}, manifest=())
        report = diff_contracts(head, wt)
        self.assertEqual([loss.file for loss in report.losses], ["test_a.py"])


# ────────────────────────────────────────────────────────────────────────────
# Testler — gerçek git: HEAD tabanı worktree'den ayrı mı?
# ────────────────────────────────────────────────────────────────────────────


class _ScratchRepo(unittest.TestCase):
    """İzole scratch repo: gerçek `git show HEAD:` yolunu doğrular."""

    def setUp(self):
        if shutil.which("git") is None:
            self.skipTest("git yok")
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="scope-contract-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.dir = self.root / CIKTI_REL
        self.dir.mkdir(parents=True)
        self._git("init", "-q", ".")
        self._git("config", "user.email", "t@example.invalid")
        self._git("config", "user.name", "t")

    def _git(self, *args):
        return subprocess.run(
            ["git", *args], cwd=str(self.root), capture_output=True, text=True,
            timeout=120,
        )

    def _write(self, cov_src, manifest_src):
        (self.dir / "test_coverage_report.py").write_text(cov_src, encoding="utf-8")
        (self.dir / "check_unit_tests.list").write_text(manifest_src, encoding="utf-8")

    def _touch(self, *names):
        for name in names:
            (self.dir / name).write_text("", encoding="utf-8")

    def _commit(self, msg="contract"):
        self._git("add", "-A")
        res = self._git("-c", "commit.gpgsign=false", "commit", "-qm", msg)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def _compare(self):
        return compare(root=self.root, coverage_rel=COVERAGE_REL,
                       manifest_rel=MANIFEST_REL)


class TestHeadBaseline(_ScratchRepo):
    def test_head_baseline_is_read_from_the_commit_not_the_worktree(self):
        # HEAD: test_a.py kapsanıyor. Worktree: kapsam silinmiş ama dosya
        # diskte. Yalnız worktree'yi okuyan bir kapı bunu göremezdi.
        self._touch("test_a.py")
        self._write(_cov({"check-unit-tests": ["test_a.py"]}, exempt=()),
                    _manifest("test_a.py"))
        self._commit("v1")
        self._write(_cov({"check-unit-tests": []}, exempt=()), _manifest())

        report = self._compare()
        self.assertEqual([loss.file for loss in report.losses], ["test_a.py"])
        self.assertEqual(report.losses[0].head_hooks, ("check-unit-tests",))
        self.assertEqual(report.manifest_removed, ["test_a.py"])
        self.assertRegex(report.head_sha, r"^[0-9a-f]{7,64}$")
        self.assertIn("KAPSAM KAYBI (FAIL)", "\n".join(report.lines()))

    def test_deleted_file_is_reported_but_not_a_loss(self):
        self._touch("test_a.py")
        self._write(_cov({"check-unit-tests": ["test_a.py"]}, exempt=()),
                    _manifest("test_a.py"))
        self._commit("v1")
        (self.dir / "test_a.py").unlink()
        self._write(_cov({"check-unit-tests": []}, exempt=()), _manifest())

        report = self._compare()
        self.assertEqual(report.losses, [])
        self.assertEqual(report.manifest_removed, ["test_a.py"])

    def test_rehome_to_another_hook_is_not_a_loss(self):
        self._touch("test_a.py")
        self._write(_cov({"old-hook": ["test_a.py"]}, exempt=()),
                    _manifest("test_a.py"))
        self._commit("v1")
        self._write(_cov({"new-hook": ["test_a.py"]}, exempt=()),
                    _manifest("test_a.py"))

        report = self._compare()
        self.assertEqual(report.losses, [])
        self.assertEqual(report.hooks_added, ["new-hook"])
        self.assertEqual(report.hooks_removed, ["old-hook"])

    def test_identical_worktree_and_head_is_empty(self):
        self._touch("test_a.py")
        self._write(_cov({"check-unit-tests": ["test_a.py"]}, exempt=()),
                    _manifest("test_a.py"))
        self._commit("v1")

        report = self._compare()
        self.assertFalse(report.has_changes)
        self.assertEqual(report.lines(), [
            "KAPSAM SÖZLEŞMESİ: HEAD ile worktree aynı "
            "(HOOK_COVERAGE, CHECK_EXEMPT, manifest)."])

    def test_missing_contract_at_head_fails_closed(self):
        (self.root / "README.md").write_text("x\n", encoding="utf-8")
        self._commit("v1")
        self._write(_cov({}), _manifest())
        with self.assertRaises(ContractError) as ctx:
            self._compare()
        self.assertIn("kapsam tabanı ölçülemedi", str(ctx.exception))

    def test_missing_contract_in_worktree_fails_closed(self):
        self._write(_cov({}), _manifest())
        self._commit("v1")
        (self.dir / "check_unit_tests.list").unlink()
        with self.assertRaises(ContractError) as ctx:
            self._compare()
        self.assertIn("okunamadı", str(ctx.exception))

    def test_unparseable_head_contract_fails_closed(self):
        self._write("HOOK_COVERAGE = {\n", "")
        self._commit("v1")
        with self.assertRaises(ContractError) as ctx:
            self._compare()
        self.assertIn("sözdizimi", str(ctx.exception))


class TestCli(_ScratchRepo):
    """Commit kapısı olarak kullanılan CLI'nin exit sözleşmesi."""

    def test_check_exits_1_on_loss_and_0_when_clean(self):
        self._touch("test_a.py")
        self._write(_cov({"check-unit-tests": ["test_a.py"]}),
                    _manifest("test_a.py"))
        self._commit("v1")
        self.assertEqual(main(["--check", "--root", str(self.root)]), 0)

        self._write(_cov({"check-unit-tests": []}), _manifest())
        self.assertEqual(main(["--check", "--root", str(self.root)]), 1)

    def test_report_and_verdict_go_to_separate_streams(self):
        self._touch("test_a.py")
        self._write(_cov({"check-unit-tests": ["test_a.py"]}),
                    _manifest("test_a.py"))
        self._commit("v1")
        self._write(_cov({"check-unit-tests": []}), _manifest())

        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = main(["--check", "--root", str(self.root)])

        self.assertEqual(rc, 1)
        self.assertIn("KAPSAM KAYBI (FAIL)", out.getvalue())
        self.assertNotIn("KAPSAM SÖZLEŞMESİ:", out.getvalue())
        self.assertIn("KAPSAM SÖZLEŞMESİ: 1 kapsam kaybı — FAIL", err.getvalue())

        # Temiz ağaç: PASS verdict'i de aynı akışta doğrulanır (vakum değil).
        self._write(_cov({"check-unit-tests": ["test_a.py"]}),
                    _manifest("test_a.py"))
        out2, err2 = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out2), contextlib.redirect_stderr(err2):
            rc2 = main(["--check", "--root", str(self.root)])
        self.assertEqual(rc2, 0)
        self.assertIn("kapsam kaybı yok — PASS", err2.getvalue())
        self.assertNotIn("KAPSAM KAYBI", out2.getvalue())

    def test_unmeasurable_root_exits_2(self):
        root = pathlib.Path(tempfile.mkdtemp(prefix="scope-contract-cli-nogit-"))
        self.addCleanup(shutil.rmtree, root, True)
        self.assertEqual(main(["--check", "--root", str(root)]), 2)


class TestNotAGitRepo(unittest.TestCase):
    def test_not_a_repo_fails_closed(self):
        root = pathlib.Path(tempfile.mkdtemp(prefix="scope-contract-nogit-"))
        self.addCleanup(shutil.rmtree, root, True)
        with self.assertRaises(ContractError) as ctx:
            compare(root=root)
        self.assertIn("git deposu değil", str(ctx.exception))

    def test_repo_without_commit_fails_closed(self):
        if shutil.which("git") is None:
            self.skipTest("git yok")
        root = pathlib.Path(tempfile.mkdtemp(prefix="scope-contract-empty-"))
        self.addCleanup(shutil.rmtree, root, True)
        subprocess.run(["git", "init", "-q", "."], cwd=str(root), check=True,
                       capture_output=True, text=True, timeout=120)
        with self.assertRaises(ContractError) as ctx:
            compare(root=root)
        self.assertIn("HEAD yok", str(ctx.exception))


# ────────────────────────────────────────────────────────────────────────────
# Testler — gerçek ağaç (asıl kapı)
# ────────────────────────────────────────────────────────────────────────────


class TestRealTreeGate(unittest.TestCase):
    """Canlı sözleşme: ölçüm gerçekten yapılıyor mu ve kayıp var mı?"""

    def test_real_contracts_are_measurable(self):
        report = compare()
        self.assertTrue(report.head.hooks, "HEAD HOOK_COVERAGE okunamadı")
        self.assertTrue(report.worktree.hooks, "worktree HOOK_COVERAGE okunamadı")
        self.assertTrue(report.worktree.manifest,
                        "worktree manifest boş — batarya kapsamı ölçülemez")
        self.assertRegex(report.head_sha, r"^[0-9a-f]{7,64}$")
        self.assertIsInstance(report.lines(), list)

    def test_real_tree_has_no_coverage_loss(self):
        report = compare()
        self.assertEqual(
            report.losses, [],
            "Kapsam kaybı — HEAD'de kapsanan dosya worktree'de hiçbir "
            "hook/manifest tarafından kapsanmıyor:\n" + "\n".join(report.lines()),
        )


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="HEAD ↔ worktree kapsam sözleşmesi fark raporu")
    ap.add_argument("--check", action="store_true",
                    help="kapsam kaybı varsa exit 1 (fail-closed ölçüm hatası exit 2)")
    ap.add_argument("--root", default=None,
                    help="depo kökü (varsayılan: bu dosyanın deposu)")
    args = ap.parse_args(argv)

    try:
        report = compare(root=args.root)
    except ContractError as exc:
        print(f"HATA: {exc}", file=sys.stderr)
        return 2

    print("\n".join(report.lines()))

    # Verdict STDERR'e: stdout yalnız fark listesidir (pipe/kesme hâlinde bile
    # sonucu okuyabilmek için ayrı akış).
    if report.losses:
        print(f"KAPSAM SÖZLEŞMESİ: {len(report.losses)} kapsam kaybı — FAIL",
              file=sys.stderr)
        return 1 if args.check else 0
    print("KAPSAM SÖZLEŞMESİ: kapsam kaybı yok — PASS", file=sys.stderr)
    return 0


if __name__ == "__main__":
    if "--check" in sys.argv[1:] or "--root" in sys.argv[1:]:
        sys.exit(main())
    unittest.main()
