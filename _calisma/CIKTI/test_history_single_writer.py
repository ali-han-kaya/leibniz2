#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_history_single_writer.py — HISTORY_PATH tek-yazıcı kapısı.

`load_history` mtime+boyut anahtarlı bir önbellek kullanır ve
`persist_history`'yi **tek yazıcı** varsayar: dosyayı her seferinde
`_write_atomic` ile yeniden üretir, .sha256 sidecar'ını aynı turda yazar.
Araya giren ikinci bir yazım yolu bu varsayımı bozar:

  * sidecar ile history.jsonl arasında yarım kalmış çift (K15 P1),
  * mtime değişmediyse bayat önbellek (append ile aynı boyut/mtime),
  * HISTORY_MAX budamasını atlayan sınırsız büyüme.

Bu dosya varsayımı kapıya çevirir: üretim Python yüzeyi AST ile taranır,
HISTORY_PATH'ten (veya `history.jsonl` sabitinden) türeyen bir hedefe yazan
her çağrı yalnız `preview_server.persist_history` gövdesinde olabilir.
İkinci yol eklendiği anda test kırmızıdır; tek yazıcı hiç bulunamazsa da
kırmızıdır (kapı sessizce boşalan bir denetim olamaz).

Kapsam bilinçli olarak fail-closed:
  * Yardımcı fonksiyona devredilen yol da yakalanır (`_help(HISTORY_PATH)` →
    `_help` içinde `open(path, "w")`) — yazım persist_history'den çıkmıştır.
  * `_write_atomic` yazım MEKANİZMASI olduğu için istisnadır; ona yapılan
    çağrı çağıranın gövdesinde sayılır.
  * Test dosyaları, sanal ortamlar, `recovery_patches_*` ve build kopyaları
    taranmaz (fixture'lar bilerek dosya yazar).

Kullanım:
    python3 -m unittest _calisma.CIKTI.test_history_single_writer -v
"""
from __future__ import annotations

import ast
import pathlib
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
OWNER = REPO_ROOT / "_calisma" / "CIKTI" / "preview_server.py"
WRITER = "persist_history"
WRITE_HELPER = "_write_atomic"
HISTORY_NAME = "HISTORY_PATH"
HISTORY_FILE = "history.jsonl"

# os.open için yazma anlamına gelen bayraklar (O_APPEND de yazımdır).
WRITE_FLAGS = ("O_WRONLY", "O_RDWR", "O_CREAT", "O_TRUNC", "O_APPEND")

EXCLUDE_DIRS = {
    ".git", ".venv", ".venv_z3", "__pycache__", ".freebuff", "node_modules",
    ".agents", ".build", ".lake", "slides_z3", ".worktrees", ".vercel",
}


def _dotted(node):
    """``open`` / ``os.open`` / ``x.y.write_text`` biçiminde ad zinciri."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def _mode_writes(call, index):
    """``open(...)`` çağrısı yazma modunda mı? (w / a / x / +)"""
    mode = None
    if len(call.args) > index:
        arg = call.args[index]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            mode = arg.value
    for kw in call.keywords:
        if (kw.arg == "mode" and isinstance(kw.value, ast.Constant)
                and isinstance(kw.value.value, str)):
            mode = kw.value.value
    return bool(mode) and any(ch in mode for ch in "wax+")


def _write_targets(call):
    """Yazan çağrıysa ``(mekanizma, [hedef ifadeleri])``, değilse ``None``.

    Okuma çağrıları (modsuz ``open``, ``os.stat``) burada yoktur: tek-yazıcı
    sözleşmesi okumayı kısıtlamaz.
    """
    func = call.func
    name = _dotted(func)
    leaf = name.rsplit(".", 1)[-1]
    args = call.args

    if name in (WRITE_HELPER, "write_atomic"):
        if args:
            return f"{name}()", [args[0]]
        for kw in call.keywords:
            if kw.arg in ("path", "dst"):
                return f"{name}()", [kw.value]
        return None

    if name in ("open", "io.open", "codecs.open"):
        if args and _mode_writes(call, 1):
            return f"{name}(write)", [args[0]]
        return None

    if isinstance(func, ast.Attribute):
        if leaf == "open" and _mode_writes(call, 0):
            return f"{name}(write)", [func.value]
        if leaf in ("write_text", "write_bytes", "touch", "unlink"):
            return f".{leaf}()", [func.value]

    if name == "os.open":
        rendered = ""
        if len(args) > 1:
            rendered = ast.unparse(args[1])
        for kw in call.keywords:
            if kw.arg == "flags":
                rendered += " " + ast.unparse(kw.value)
        if args and any(flag in rendered for flag in WRITE_FLAGS):
            return "os.open(write flags)", [args[0]]
        return None

    if name in ("os.remove", "os.unlink", "os.truncate", "os.rmdir"):
        if args:
            return f"{name}()", [args[0]]
        return None

    if name in ("os.replace", "os.rename", "shutil.move", "shutil.copy",
                "shutil.copyfile", "shutil.copy2"):
        if len(args) > 1:
            return f"{name}()", [args[1]]
        for kw in call.keywords:
            if kw.arg in ("dst", "dst_path"):
                return f"{name}()", [kw.value]
        return None

    return None


def _history_ref(node, aliases=()):
    """İfade HISTORY_PATH'i (veya sabit history.jsonl'i) anıyor mu?"""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and (sub.id == HISTORY_NAME
                                          or sub.id in aliases):
            return True
        if isinstance(sub, ast.Attribute) and sub.attr == HISTORY_NAME:
            return True
        if isinstance(sub, ast.Constant) and sub.value == HISTORY_FILE:
            return True
    return False


def _iter_own_nodes(node):
    """Fonksiyonun KENDİ gövdesi: iç içe def/class sınırlarını geçme."""
    stack = list(getattr(node, "body", []))
    while stack:
        current = stack.pop()
        yield current
        for child in ast.iter_child_nodes(current):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef,
                                  ast.ClassDef)):
                continue
            stack.append(child)


def _scope_aliases(node):
    """``p = HISTORY_PATH`` zincirlerini sabit noktaya kadar izle."""
    aliases = set()
    changed = True
    while changed:
        changed = False
        for sub in _iter_own_nodes(node):
            if isinstance(sub, (ast.Assign, ast.AnnAssign)):
                targets = sub.targets if isinstance(sub, ast.Assign) else [sub.target]
                value = sub.value
                if value is None or not _history_ref(value, aliases):
                    continue
                for target in targets:
                    if isinstance(target, ast.Name) and target.id != HISTORY_NAME:
                        if target.id not in aliases:
                            aliases.add(target.id)
                            changed = True
    return aliases


class _Scope:
    def __init__(self, name):
        self.name = name
        self.aliases = set()
        self.tainted = set()
        self.node = None


class _FuncInfo(_Scope):
    def __init__(self, node):
        super().__init__(node.name)
        self.node = node
        self.aliases = _scope_aliases(node)


def _collect(tree):
    """Fonksiyonları, modül kapsamını ve yerel çağrıları topla."""
    funcs = {}
    call_sites = []  # (caller_scope, Call)

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs[node.name] = _FuncInfo(node)

    module_scope = _Scope("<module>")
    module_scope.aliases = _scope_aliases(tree)

    class _Walker(ast.NodeVisitor):
        def __init__(self):
            self.stack = [module_scope]

        def visit_FunctionDef(self, node):
            info = funcs.get(node.name)
            self.stack.append(info if info is not None else _Scope(node.name))
            self.generic_visit(node)
            self.stack.pop()

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_Call(self, node):
            call_sites.append((self.stack[-1], node))
            self.generic_visit(node)

    _Walker().visit(tree)
    return funcs, module_scope, call_sites


def _resolve_taint(funcs, call_sites):
    """Bir adım interprosedürel taint: yardımcıya verilen HISTORY_PATH.

    ``_write_atomic`` mekanizma olduğu için taint almaz; ona yapılan çağrı
    zaten çağıranın gövdesinde yazım olarak sayılır. Tek adım bilinçlidir:
    iki adım öteye taşınan yol statik olarak görünmez, bu yüzden kapı
    doğrudan/aliash/tek-hop yollarını kapsar.
    """
    for caller, call in call_sites:
        if not isinstance(call.func, ast.Name):
            continue
        callee = funcs.get(call.func.id)
        if callee is None or callee.name == WRITE_HELPER:
            continue
        params = [a.arg for a in callee.node.args.args]
        for index, arg in enumerate(call.args):
            if index >= len(params):
                break
            if _history_ref(arg, caller.aliases):
                callee.tainted.add(params[index])


def analyze(source, filename="preview_server.py"):
    """Kaynağı tara → ``(writes, violations)``.

    writes: ``[(fonksiyon, satır, mekanizma), ...]`` — kapsamı ne olursa
    olsun HISTORY_PATH'e yazan çağrılar.
    violations: ``[(fonksiyon, satır, mekanizma, kaynak), ...]`` — yazan ama
    ``persist_history`` dışında olan çağrılar (fail-closed).
    """
    tree = ast.parse(source, filename=filename)
    funcs, module_scope, call_sites = _collect(tree)
    _resolve_taint(funcs, call_sites)

    writes = []
    violations = []

    class _SinkWalker(ast.NodeVisitor):
        def __init__(self):
            self.stack = [module_scope]

        def visit_FunctionDef(self, node):
            info = funcs.get(node.name)
            self.stack.append(info if info is not None else _Scope(node.name))
            self.generic_visit(node)
            self.stack.pop()

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_Call(self, node):
            classified = _write_targets(node)
            if classified is not None:
                mechanism, targets = classified
                hit = any(_history_ref(t, self.stack[-1].aliases) for t in targets)
                if not hit:
                    hit = any(isinstance(t, ast.Name)
                              and t.id in self.stack[-1].tainted
                              for t in targets)
                if hit:
                    scope = self.stack[-1]
                    writes.append((scope.name, node.lineno, mechanism))
                    allowed = (filename == str(OWNER)
                               and scope.name in (WRITER, WRITE_HELPER))
                    if not allowed:
                        try:
                            segment = ast.get_source_segment(source, node) or ""
                        except Exception:
                            segment = ""
                        violations.append((scope.name, node.lineno,
                                           mechanism, segment.strip()))
            self.generic_visit(node)

    _SinkWalker().visit(tree)
    return writes, violations


def _candidate_files():
    """Üretim Python yüzeyi: HISTORY_PATH / history.jsonl geçen dosyalar."""
    for path in REPO_ROOT.rglob("*.py"):
        if any(part in EXCLUDE_DIRS for part in path.parts):
            continue
        if path.name.startswith("test_"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if HISTORY_NAME not in text and HISTORY_FILE not in text:
            continue
        yield path, text


def _render(violation):
    func, line, mechanism, segment = violation
    return f"{func}:{line} [{mechanism}] {segment}"


class HistorySingleWriterGate(unittest.TestCase):
    def test_real_tree_has_exactly_one_history_writer(self):
        violations = []
        writes = []
        for path, text in _candidate_files():
            try:
                file_writes, file_violations = analyze(text, filename=str(path))
            except SyntaxError as exc:  # pragma: no cover - defensive
                self.fail(f"{path}: AST ayrıştırılamadı: {exc}")
            writes.extend((str(path), w) for w in file_writes)
            violations.extend((str(path), v) for v in file_violations)

        self.assertEqual(
            violations, [],
            "HISTORY_PATH'e persist_history dışında yazan yol(lar) var — "
            "tek-yazıcı varsayımı (load_history önbelleği + K15 sidecar) "
            "bozulur:\n" + "\n".join(
                f"{path}: {_render(v)}" for path, v in violations),
        )

        owners = {(path, func) for path, (func, _line, _mech) in writes}
        self.assertIn(
            (str(OWNER), WRITER), owners,
            "kapı boşaldı: persist_history'de HISTORY_PATH yazımı bulunamadı "
            "— denetim hiçbir şey ölçmüyor olabilir",
        )
        self.assertTrue(
            all(func == WRITER for path, (func, _l, _m) in writes
                if path == str(OWNER)),
            f"persist_history dışında yazım: {writes}",
        )


class GateSelfTests(unittest.TestCase):
    """Kapının kendisi: sentetik kaynaklarda kırmızı/yeşil davranışı."""

    def _run(self, source, filename=str(OWNER)):
        return analyze(source, filename=filename)

    def test_second_writer_is_flagged(self):
        src = '''
def persist_history(rec):
    _write_atomic(HISTORY_PATH, "ok\\n")

def load_history():
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        f.write("ikinci yol")
'''
        writes, violations = self._run(src)
        self.assertEqual(len(writes), 2, writes)
        self.assertEqual(len(violations), 1, violations)
        self.assertEqual(violations[0][0], "load_history")

    def test_append_is_a_write(self):
        src = '''
def persist_history(rec):
    _write_atomic(HISTORY_PATH, "ok\\n")

def rotate():
    with open(HISTORY_PATH, "a", encoding="utf-8") as f:
        f.write("ek")
'''
        _, violations = self._run(src)
        self.assertEqual(len(violations), 1, violations)
        self.assertIn("open(write)", violations[0][2])

    def test_read_only_open_is_not_flagged(self):
        src = '''
def persist_history(rec):
    _write_atomic(HISTORY_PATH, "ok\\n")

def load_history():
    with open(HISTORY_PATH, encoding="utf-8") as f:
        return f.read()
'''
        _, violations = self._run(src)
        self.assertEqual(violations, [])

    def test_alias_is_tracked(self):
        src = '''
def persist_history(rec):
    _write_atomic(HISTORY_PATH, "ok\\n")

def tamper():
    p = HISTORY_PATH
    _write_atomic(p, "alias")
'''
        _, violations = self._run(src)
        self.assertEqual(len(violations), 1, violations)
        self.assertEqual(violations[0][0], "tamper")

    def test_sidecar_outside_writer_is_flagged(self):
        src = '''
def persist_history(rec):
    _write_atomic(HISTORY_PATH, "ok\\n")
    _write_atomic(HISTORY_PATH + ".sha256", "h  history.jsonl\\n")

def reseal():
    _write_atomic(HISTORY_PATH + ".sha256", "h  history.jsonl\\n")
'''
        _, violations = self._run(src)
        self.assertEqual(len(violations), 1, violations)
        self.assertEqual(violations[0][0], "reseal")

    def test_helper_receiving_history_path_is_flagged(self):
        """Yolu yardımcıya devretmek de ikinci yazıcıdır (fail-closed)."""
        src = '''
def persist_history(rec):
    _write_atomic(HISTORY_PATH, "ok\\n")

def _append(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)

def rotate():
    _append(HISTORY_PATH, "x")
'''
        _, violations = self._run(src)
        self.assertEqual(len(violations), 1, violations)
        self.assertEqual(violations[0][0], "_append")

    def test_write_helper_itself_is_not_flagged(self):
        """`_write_atomic` mekanizmadır: içindeki os.replace yazıcı değildir."""
        src = '''
def _write_atomic(path, data):
    fd, tmp = _mkstemp()
    os.replace(tmp, path)

def persist_history(rec):
    _write_atomic(HISTORY_PATH, "ok\\n")
'''
        writes, violations = self._run(src)
        self.assertEqual(violations, [], violations)
        self.assertEqual([w[0] for w in writes], ["persist_history"])

    def test_other_module_writing_module_attr_is_flagged(self):
        src = '''
def tamper(ps):
    with open(ps.HISTORY_PATH, "w", encoding="utf-8") as f:
        f.write("x")
'''
        _, violations = self._run(src, filename="api/_adapter.py")
        self.assertEqual(len(violations), 1, violations)
        self.assertEqual(violations[0][0], "tamper")

    def test_literal_history_file_is_flagged(self):
        src = '''
def persist_history(rec):
    _write_atomic(HISTORY_PATH, "ok\\n")

def reset(root):
    pathlib.Path(root, "history.jsonl").write_text("x")
'''
        _, violations = self._run(src)
        self.assertEqual(len(violations), 1, violations)
        self.assertEqual(violations[0][0], "reset")


if __name__ == "__main__":
    unittest.main()
