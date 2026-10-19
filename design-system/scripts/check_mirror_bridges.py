#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""check_mirror_bridges.py — marka aynası @theme köprülerinin kapısı.

Neden ayrı kapı: `generate_mirror_tailwind.py` dört marka aynası için
`<marka>/tailwind.css` üretir ve kök köprünün aksine bu dosyalar TEK bir
paletin parçası değildir — birlikte import edilebilirler. Linear ve Vercel
token'ları `--color-*` adları taşıdığı için ön-ek olmadan üretim, temel
paleti (`bg-bg`/`bg-accent`) sessizce marka paletine kaydırırdı. Bu kapı o
ayrıklığı ve ayna→köprü bağını fail-closed doğrular.

Sözleşmeler (hepsi fail-closed):
  B1 ROSTER           : roster okunur (eksik/bozuk → exit 2) ve her kayıtlı
                        aynanın köprüsü diskte olmalı (yok → exit 2).
  B2 ÜRETİM           : köprü, jeneratörün `render()` çıktısıyla BİREBİR
                        olmalı (elle düzenleme / stale üretim → exit 1).
  B3 TEMEL PALET      : ön-koşul adları `<marka>-` ön-ekli, @theme anahtarları
                        `<namespace>-<marka>-*` (namespace kapsam içinde) ve
                        HİÇBİR ad temel paletin `:root` adları ya da kök
                        köprünün `@theme` anahtarlarıyla kesişemez.
  B4 BAĞLANTI         : her @theme değeri yalnız `var(<marka>-…)` ve o ad
                        dosyadaki bir ön-koşulda tanımlı (literal/çürük
                        referans yasak).
  B5 ÖN-KOŞUL BİREBİR : her ön-koşul değeri, aynadaki değerin deterministik
                        ön-ek yeniden yazımıyla birebir (elle yazılmış ton
                        yakalanır); adı aynada olmayan ön-koşul yasak.
  B6 KAPSAMA          : sayım bloğu ayrıştırılır ve `aliases + skipped =
                        tokens`, gerekçe sayımları toplamı `skipped`, her ayna
                        token'ı ya yuva ya gerekçeli atlama olmalı — sessiz
                        kayıp ve vacuous PASS yasak.
  B7 BLOK DİSİPLİNİ   : dosyada tam olarak bir `:root` ve bir `@theme` bloğu
                        bulunur; başka seçici/@rule kapsam sızıntısıdır.

Exit kodları: 0 = tüm aynalar PASS, 1 = drift/sözleşme ihlali, 2 = yapısal
hata (roster/köprü yok). READ-ONLY: hiçbir dosyayı yazmaz, üretmez, silmez.
OFFLINE, stdlib-only, ~0.3s.

Kullanım:
  python3 design-system/scripts/check_mirror_bridges.py
  python3 design-system/scripts/check_mirror_bridges.py --root . --roster <dosya>
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from check_brand_mirrors import (  # noqa: E402
    DEFAULT_ROSTER,
    SetupError,
    load_roster,
)
import generate_mirror_tailwind as gen  # noqa: E402

DEFAULT_ROOT = HERE.parent.parent
BASE_TOKENS = ("design-system", "tokens.css")
BASE_BRIDGE = ("design-system", "tailwind.css")

BLOCK_RE = {
    ":root": re.compile(r":root\s*\{(.*?)\}", re.S),
    "@theme": re.compile(r"@theme\s*\{(.*?)\}", re.S),
}
SELECTOR_RE = re.compile(r"^[^\s/*@{}][^{}]*\{", re.M)
AT_RULE_RE = re.compile(r"^\s*@([A-Za-z-]+)", re.M)
# Sayım bloğu bir CSS yorumu: yorumları ayırıp içinde '── sayımlar' geçeni
# almak, yorum gövdesinde `*` bulunduğu için gövde-deseni yazmaktan sağlamdır.
COMMENT_RE = re.compile(r"/\*(.*?)\*/", re.S)
LEDGER_ENTRY_RE = re.compile(r"^\s*\*\s+([A-Za-z_][\w:-]*)=(\d+)\s*$", re.M)
LEDGER_EXTERNAL_RE = re.compile(r"^\s*\*\s+external=(--\S+)\s*$", re.M)
# `var(--x)` ve `var(--x, fallback)` — değerin TAMAMI tek bir var() referansı
# olmalı; bu desen tam eşleşme için kullanılır.
ONLY_VAR_RE = re.compile(r"^var\(\s*(--[A-Za-z0-9_-]+)\s*(?:,[^()]*)?\)$")

VALID_REASONS = frozenset(gen.REASON_ORDER)


class Violation(Exception):
    """Sözleşme ihlali (drift) — exit 1."""


def parse_block(text: str, selector: str) -> dict:
    match = BLOCK_RE[selector].search(text)
    if not match:
        raise Violation("%s bloğu yok" % selector)
    out = {}
    for name, value in gen.PAIR.findall(match.group(1)):
        if name in out:
            raise Violation("%s bloğunda yinelenen ad: %s" % (selector, name))
        out[name] = re.sub(r"\s+", " ", value).strip()
    return out


def parse_ledger(text: str) -> dict:
    body = next((c for c in COMMENT_RE.findall(text) if "── sayımlar" in c), None)
    if body is None:
        raise Violation("sayım bloğu yok (kapsama kanıtlanamaz)")
    entries = {k: int(v) for k, v in LEDGER_ENTRY_RE.findall(body)}
    if not entries:
        raise Violation("sayım bloğu boş")
    entries["_external"] = LEDGER_EXTERNAL_RE.findall(body)
    return entries


def check_blocks(text: str) -> None:
    """B7 — yalnız bir :root + bir @theme; başka kapsam yok."""
    for selector in (":root", "@theme"):
        if len(BLOCK_RE[selector].findall(text)) != 1:
            raise Violation("%s bloğu tam olarak bir tane olmalı" % selector)
    striped = BLOCK_RE[":root"].sub(" ", text)
    striped = BLOCK_RE["@theme"].sub(" ", striped)
    striped = re.sub(r"/\*.*?\*/", " ", striped, flags=re.S)
    stray_at = [a for a in AT_RULE_RE.findall(striped) if a != "theme"]
    stray_sel = SELECTOR_RE.findall(striped)
    if stray_at or stray_sel:
        raise Violation(
            "kapsam sızıntısı: beklenmeyen @rule=%s seçici=%s "
            "(dosya yalnız :root + @theme taşır)" % (stray_at, stray_sel))


def check_base_disjoint(names: set, base_names: set) -> None:
    """B3 — temel palet adlarıyla kesişim yasak."""
    clash = sorted(names & base_names)
    if clash:
        raise Violation(
            "%d ad temel paletle çakışıyor (%s …) — ön-ek kuralı bozulmuş: "
            "temel `bg-bg`/`bg-accent` marka paletine kayardı"
            % (len(clash), ", ".join(clash[:4])))


def check_mirror(mirror: str, root: Path, base_names: set) -> dict:
    bridge = gen.bridge_path(mirror, root)
    if not bridge.is_file():
        raise SetupError(
            "köprü yok: design-system/%s/%s (remedy: python3 "
            "design-system/scripts/generate_mirror_tailwind.py)"
            % (mirror, gen.BRIDGE_NAME))
    text = bridge.read_text(encoding="utf-8")

    # B2 — üretim birebirliği
    rendered = gen.render(mirror, root)
    if text != rendered:
        raise Violation(
            "köprü jeneratörle birebir değil (elle düzenleme ya da stale "
            "üretim) — remedy: python3 "
            "design-system/scripts/generate_mirror_tailwind.py")

    check_blocks(text)
    preconditions = parse_block(text, ":root")
    theme = parse_block(text, "@theme")

    # B3 — ön-ek disiplini + temel paletten ayrıklık
    prefix = "--%s-" % mirror
    bad = sorted(n for n in preconditions if not n.startswith(prefix))
    if bad:
        raise Violation("ön-koşul adı `<marka>-` ön-ekli değil: %s"
                        % ", ".join(bad[:4]))
    for name in theme:
        segments = name[2:].split("-")
        if len(segments) < 3 or segments[0] not in gen.TARGET_NS \
                or segments[1] != mirror:
            raise Violation(
                "@theme anahtarı `<namespace>-<marka>-*` düzeninde değil: %s"
                % name)
    check_base_disjoint(set(preconditions) | set(theme), base_names)

    # B4 — her yuva yalnız var() ve hedef ön-koşul dosyada
    for name, value in theme.items():
        match = ONLY_VAR_RE.match(value)
        if not match:
            raise Violation("%s literal taşıyor (%r) — değer yalnız var() "
                            "olabilir" % (name, value))
        if match.group(1) not in preconditions:
            raise Violation("%s ön-koşulu dosyada tanımlı değil (%s)"
                            % (name, match.group(1)))

    # B5 — ön-koşullar aynadan deterministik yeniden yazımla birebir
    tokens = gen.mirror_tokens(mirror, root)
    for name, value in preconditions.items():
        token = "--" + name[len(prefix):]
        if token not in tokens:
            raise Violation("%s aynada yok (uydurma ön-koşul)" % name)
        expected = gen.rewrite_value(mirror, tokens[token], tokens)
        if value != expected:
            raise Violation(
                "%s aynadaki değerle birebir değil (elle yazılmış ton?) — "
                "beklenen %r, dosyada %r" % (name, expected, value))

    # B6 — kapsama: sayım bloğu + sessiz kayıp yasağı
    ledger = parse_ledger(text)
    info = gen.analyse(mirror, root)
    expected_counts = {
        "tokens": len(tokens),
        "aliases": len(info["plans"]),
        "preconditions": len(info["preconditions"]),
        "skipped": len(info["skipped"]),
        "external_refs": len(info["external"]),
        "collisions": info["collisions"],
    }
    for key, expected in expected_counts.items():
        if ledger.get(key) != expected:
            raise Violation("sayım bloğu %s=%s diyor, ölçülen %d"
                            % (key, ledger.get(key), expected))
    for key in (k for k in ledger if not k.startswith("_")
                and k not in expected_counts):
        if not key.startswith("skip:") or key[5:] not in VALID_REASONS:
            raise Violation("tanınmayan sayım anahtarı: %s" % key)
    if not theme:
        raise Violation("@theme boş (vacuous PASS yasağı)")
    if ledger["aliases"] + ledger["skipped"] != ledger["tokens"]:
        raise Violation("aliases + skipped != tokens (%d + %d != %d) — "
                        "sessiz kayıp" % (ledger["aliases"], ledger["skipped"],
                                          ledger["tokens"]))
    reason_total = sum(v for k, v in ledger.items() if k.startswith("skip:"))
    if reason_total != ledger["skipped"]:
        raise Violation("gerekçe sayımları toplamı (%d) skipped (%d) ile "
                        "uyuşmuyor" % (reason_total, ledger["skipped"]))
    covered = set(info["plans"].values()) | set(info["skipped"])
    if covered != set(tokens):
        missing = sorted(set(tokens) - covered)
        raise Violation("kapsamsız token(lar): %s" % ", ".join(missing[:4]))
    if ledger["preconditions"] != len(preconditions) or \
            ledger["aliases"] != len(theme):
        raise Violation("sayım bloğu dosyadaki bloklarla uyuşmuyor "
                        "(preconditions=%d/%d, aliases=%d/%d)"
                        % (ledger["preconditions"], len(preconditions),
                           ledger["aliases"], len(theme)))

    return {
        "mirror": mirror,
        "tokens": ledger["tokens"],
        "aliases": ledger["aliases"],
        "preconditions": ledger["preconditions"],
        "skipped": ledger["skipped"],
        "collisions": ledger["collisions"],
    }


def base_palette_names(root: Path) -> set:
    """Temel paletin adları: tokens.css :root + kök köprünün @theme anahtarları."""
    names = set()
    tokens_path = root.joinpath(*BASE_TOKENS)
    if tokens_path.is_file():
        names.update(n for n, _ in gen.PAIR.findall(
            tokens_path.read_text(encoding="utf-8")))
    bridge_path = root.joinpath(*BASE_BRIDGE)
    if bridge_path.is_file():
        bridge = bridge_path.read_text(encoding="utf-8")
        names.update(n for n, _ in gen.PAIR.findall(
            BLOCK_RE["@theme"].search(bridge).group(1)
            if BLOCK_RE["@theme"].search(bridge) else ""))
    return names


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Marka aynası @theme köprüleri kapısı (fail-closed, read-only)")
    ap.add_argument("--root", default=str(DEFAULT_ROOT),
                    help="repo kökü (varsayılan: script konumundan türetilir)")
    ap.add_argument("--roster", default=str(DEFAULT_ROSTER),
                    help="marka roster'ı (varsayılan: brand_mirrors.list)")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    try:
        entries, _exempt = load_roster(Path(args.roster))
        mirrors = sorted(e["dir"] for e in entries)
        if not mirrors:
            raise SetupError("roster'da marka aynası yok")
        base_names = base_palette_names(root)
        if not base_names:
            raise SetupError("temel palet adları okunamadı (tokens.css/)")
    except SetupError as exc:
        print("check-mirror-bridges: YAPISAL HATA: %s" % exc, file=sys.stderr)
        return 2

    print("check-mirror-bridges: %d marka aynası · temel palet %d ad "
          "(ayrıklık zorunlu)" % (len(mirrors), len(base_names)))

    stats = []
    for mirror in mirrors:
        tag = "design-system/%s" % mirror
        try:
            stats.append(check_mirror(mirror, root, base_names))
        except SetupError as exc:
            print("check-mirror-bridges: YAPISAL HATA: %s" % exc, file=sys.stderr)
            return 2
        except Violation as exc:
            print("  FAIL  %s: %s" % (tag, exc), file=sys.stderr)
            print("check-mirror-bridges: commit BLOKE (drift)", file=sys.stderr)
            return 1
        last = stats[-1]
        print("  PASS  %-24s %4d token · %4d yuva · %3d ön-koşul · "
              "%3d kapsam dışı"
              % (tag, last["tokens"], last["aliases"], last["preconditions"],
                 last["skipped"]))

    total_aliases = sum(s["aliases"] for s in stats)
    total_tokens = sum(s["tokens"] for s in stats)
    print("OK — %d/%d marka @theme köprüsü (%d/%d token yuvalandı; temel "
          "palet ayrık, literal yok, sayımlar kilitli)"
          % (len(stats), len(stats), total_aliases, total_tokens))
    return 0


if __name__ == "__main__":
    sys.exit(main())
