#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""report_vercel_dashboard_drift.py — Vercel ↔ kök dashboard token farkını
MAKİNE-OKUNUR bir drift raporuna çevirir.

NEDEN: fark karşılaştırması elle yazılmış markdown olarak duruyordu
(`_calisma/CIKTI/VERCEL_DASHBOARD_TOKEN_FARK_RAPORU.md`). Elle yazılan rapor
kendi sayılarını taşır: iki kaynaktan biri yenilendiğinde sessizce bayatlar ve
CI'da hiç koşmadığı için bayatlığı kimse görmez. Bu betik karşılaştırmayı
dosyalardan TÜRETİR, iki biçimde yazar —

  (1) JSON  → `_calisma/CIKTI/vercel_dashboard_drift.json` (makine-okunur;
      CI'da `logs/vercel_dashboard_drift.json` olarak mevcut precommit-logs
      artifact'ına da girer, AYRI artifact adı açılmaz),
  (2) Markdown → `_calisma/CIKTI/VERCEL_DASHBOARD_TOKEN_FARK_RAPORU.md`
      (insan-okunur kopya, ÜRETİLİR; elle düzenleme = drift).

`--check` iki şeyi birden doğrular (fail-closed):
  * TAZELİK: diskteki iki kopya bu koşumun çıktısıyla BAYT birebir mi?
  * YAPISAL SAĞLIK: raporun kendi invaryantları tutuyor mu (`status == ok`)?
İkincisi vacuous-PASS yasağıdır: bozuk bir durumu jeneratörle yeniden üretip
commit etmek kapıyı YEŞİL bırakmamalıdır.

Kullanım:
    python3 design-system/scripts/report_vercel_dashboard_drift.py            # yaz
    python3 design-system/scripts/report_vercel_dashboard_drift.py --check    # drift → rc 1
    python3 design-system/scripts/report_vercel_dashboard_drift.py --json     # stdout = tek JSON
    python3 design-system/scripts/report_vercel_dashboard_drift.py --json-out P --md-out Q

Konvansiyon (repo geneli, `summary_pattern_drift.py` ile aynı): `--json` /
`--json-out` verildiğinde stdout TEK bir JSON belgesidir; tanı/verdict satırları
stderr'e gider. OFFLINE, stdlib-only, deterministik (zaman damgası YOK).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
VERCEL = ROOT / "design-system" / "vercel"
DASH_CSS = ROOT / "design-system" / "tokens.css"
DASH_JSON = ROOT / "design-system" / "tokens.json"
PREVIEW_HTML = ROOT / "_calisma" / "CIKTI" / "preview.html"
NEXT_GLOBALS = ROOT / "apps" / "dashboard-next" / "app" / "globals.css"
OUT_JSON = ROOT / "_calisma" / "CIKTI" / "vercel_dashboard_drift.json"
OUT_MD = ROOT / "_calisma" / "CIKTI" / "VERCEL_DASHBOARD_TOKEN_FARK_RAPORU.md"
SCHEMA = "vercel-dashboard-drift/1"

REL_VERCEL_RAW = "design-system/vercel/raw.json"
REL_VERCEL_CSS = "design-system/vercel/tokens.css"
REL_VERCEL_JSON = "design-system/vercel/tokens.json"
REL_DASH_CSS = "design-system/tokens.css"
REL_DASH_JSON = "design-system/tokens.json"

_VAR = re.compile(r"(--[\w-]+)\s*:\s*([^;{}]+?)\s*;")


def _block(text: str, selector_pat: str) -> dict:
    match = re.search(selector_pat + r"\s*\{(.*?)\}", text, re.S)
    if not match:
        return {}
    return {n: v.strip() for n, v in _VAR.findall(match.group(1))}


# ── Kategori kuralları ────────────────────────────────────────────────────
# SIRA ÖNEMLİ (ilk eşleşen kazanır) ve son kural TAM-BAĞLI bir RENK
# allowlist'idir: kurala uymayan bir ad "renk" diye yutulmaz, `uncategorized`
# olarak raporlanır (yeni token sessizce yanlış kategoriye düşmesin —
# fail-closed).
CATEGORY_RULES = (
    ("composition", "Composition shorthand", r"^--(card|badge|table|pre|button)-"),
    ("font_family", "Font family", r"^--font-"),
    ("font_size", "Font size", r"^--text-"),
    ("line_height", "Line height", r"^--lh-"),
    ("letter_spacing", "Letter spacing", r"^--ls-"),
    ("spacing", "Spacing", r"^--space-"),
    ("radius", "Radius", r"^--radius-"),
    ("motion", "Motion", r"^--(dur-|ease)"),
    ("layout", "Layout", r"(grid|max-width)"),
    (
        "color",
        "Renk, tint ve yüzey/effect",
        r"^--(bg|fg|muted|fg-dimmed|accent|ok|warn|err|border|budget|"
        r"surface(-\d+|-raised)?|on-accent|header-(start|end)|code-bg|"
        r"paper|paper-ink|tint-[\w-]+|shadow-tip|backdrop-lightbox)$",
    ),
)
UNCATEGORIZED = ("uncategorized", "Kategorisiz")

# ── EDİTÖRYEL VERİ (rakam değil, YORUM) ───────────────────────────────────
# "En yakın dashboard rolü" eşlemesi türetilemez (insan yargısı); bu yüzden
# veri olarak burada durur ve İKİ invaryantla korunur: (a) küme Vercel token
# kümesiyle BİREBİR olmalı, (b) yazılan değer raw.json'daki değerle birebir
# olmalı. İkisi de `--check` altında fail-closed'dur — yorum katmanı
# kaynaklardan kopamaz.
NEAREST_ROLE = (
    ("--color-background-100", "hsla(0, 0%, 100%, 1)",
     "Light `--surface` / `--paper`: `#fffdf8`",
     "Dashboard saf beyaz değil; hafif sıcak kâğıt zemin kullanıyor."),
    ("--color-gray-200", "hsla(0, 0%, 92%, 1)",
     "Light `--surface-raised`: `#e9e1d3`",
     "Yakın parlaklık; Vercel nötr gri, dashboard sıcak gri."),
    ("--color-gray-300", "hsla(0, 0%, 90%, 1)",
     "Light `--surface-raised`: `#e9e1d3`",
     "Aynı nötr/sıcak ton farkı."),
    ("--color-gray-500", "hsla(0, 0%, 79%, 1)",
     "Light `--border`: `#cfc5b5`",
     "Dashboard çizgisi daha koyu ve sıcak."),
    ("--color-gray-600", "hsla(0, 0%, 66%, 1)",
     "Light `--border` / `--muted` arası",
     "Tek bir karşılığı yok."),
    ("--color-gray-700", "hsla(0, 0%, 56%, 1)",
     "Light `--muted`: `#70695f`",
     "Dashboard daha koyu ve sıcak."),
    ("--color-gray-800", "hsla(0, 0%, 49%, 1)",
     "Light `--muted`: `#70695f`",
     "Nötr gri ile sıcak metin grisi farklı."),
    ("--color-gray-900", "hsla(0, 0%, 30%, 1)",
     "Light `--fg`: `#292722`",
     "Dashboard metni daha koyu ve sıcak."),
    ("--color-gray-1000", "hsla(0, 0%, 9%, 1)",
     "Light `--fg`: `#292722`",
     "En yakın koyu nötr ton; yine de değer ve ton farklı."),
    ("--color-gray-alpha-400", "#00000014",
     "Dashboard'da yarı saydam nötr sınır token'ı yok",
     "Status tint'leri semantik; genel alpha border'ın karşılığı değil."),
    ("--ship-text", "#ff5b4f",
     "`--err`: dark `#ff7b72`, light `#b42318`",
     "Anlam yakın; Vercel canlı üretim kırmızısı, light theme metin kontrastı daha koyu."),
    ("--develop-text", "#0a72ef",
     "`--accent`: dark `#58a6ff`, light `#8b5e2b`",
     "Dark temada mavi yakın; light temada dashboard accent kahverengi."),
    ("--preview-text", "#de1d8d",
     "`--budget`: dark `#bc8cff`, light `#7650a8`",
     "Mor/pink ailesi yakın; semantik ve değer farklı."),
    ("--geist-console-text-color-default", "#000",
     "Light `--fg`: `#292722`; dark `--bg`: `#0e1116`",
     "Console default'ı doğrudan dashboard foreground/background token'ı değil."),
    ("--geist-console-text-color-blue", "#0070f3",
     "Dark `--accent`: `#58a6ff`",
     "Blue semantiği korunur; dashboard light accent'i mavi değil."),
    ("--geist-console-text-color-purple", "#7928ca",
     "Light `--budget`: `#7650a8`",
     "Aile yakın; token görevi farklı."),
    ("--geist-console-text-color-pink", "#eb367f",
     "Light `--budget` / Vercel `--preview-text` ailesi",
     "Dashboard'da doğrudan pink semantic karşılığı yok."),
    ("--geist-selection-text-color", "hsla(0, 0%, 95%, 1)",
     "Light `--surface` / `--surface-raised`",
     "Nötr açık seçim yüzeyi; dashboard seçimleri mevcut tint/hover sözleşmesine bağlı."),
    ("--ds-focus-color", "hsla(212, 100%, 48%, 1)",
     "Dark `--accent`: `#58a6ff`",
     "Light temada doğrudan focus token'ı yok; `--accent` eşlemesi hue'yu brown'a çevirir."),
)

RISK_NOTES = (
    "**Birebir override yok.** Vercel token'larını import etmek dashboard mevcut "
    "token'larını değiştirmiyor; fakat mevcut görsel sistemi de değiştirmiyor. "
    "Etki ancak bu değişkenler tüketilirse başlar.",
    "**Light-theme kıyası gerekir.** Vercel capture light; dashboard'un default "
    "dark değerleriyle karşılaştırmak theme-crossing karşılaştırma olur. Renk "
    "rolleri bu nedenle light override'lar üzerinden yorumlanır.",
    "**Vendor token'ları semantik UI token'ları değildir.** `ship`, `preview`, "
    "`geist` ve `ds` adları ürün/console bağlamı taşır. Dashboard'un `ok`, `warn`, "
    "`err`, `accent`, `budget` token'ları farklı davranış sözleşmelerine sahiptir.",
    "**Kapsam dengesiz.** Vercel seti renk-only; dashboard renk/tint/effect, font, "
    "font-size, line-height, letter-spacing, spacing, radius, motion, layout ve "
    "composition sözleşmesini kapsar.",
    "**Global import riski.** Her iki katman da `:root` kullanıyor. İsim çakışması "
    "bugün yok; yine de Vercel referansı `.vercel-reference` gibi bir scope'a "
    "taşınmazsa global CSS yüzeyi gereksiz genişler.",
    "**JSON/CSS kapsam farkı.** Kök `tokens.json` yapılandırılmış renk değerlerini "
    "taşır; CSS'teki composition shorthand'leri (`card-*`, `badge-*`, `table-*`, "
    "`pre-*`, `button-*`) yalnız CSS'te bulunur. Mevcut drift gate özellikle "
    "JSON↔CSS renk eşitliğini doğrular; bu, Vercel'in tam kanonik eşitliğinden "
    "farklı bir sözleşmedir.",
)

RECOMMENDATIONS = (
    "**Token'ları birleştirmeyin veya otomatik yeniden adlandırmayın.** İki set "
    "farklı ürün bağlamlarından geliyor ve isim çakışması yok.",
    "Vercel setini yalnız referans olarak kullanacaksanız, dashboard dışında "
    "`.vercel-reference { … }` scope'unda veya ayrı bir preview yüzeyinde tutun.",
    "Gerçekten bir tema benzetmesi gerekiyorsa ayrı ve açık bir adapter katmanı "
    "oluşturun: her hedef eşleşmesi için semantik gerekçe, light/dark hedef, "
    "contrast sonucu ve görsel-regression kanıtı bulunmalı.",
    "Dashboard'da yeni focus/selection semanticleri gerekiyorsa bunları Vercel'in "
    "ham adlarıyla değil, dashboard sözleşmesine uygun `--focus-*` ve "
    "`--selection-*` adlarıyla tanımlayın.",
)


class MeasurementError(Exception):
    """Kaynak okunamadı / yapı beklenenden farklı — kapı kör (sessiz PASS yok)."""


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MeasurementError("%s okunamadı/ayrıştırılamadı: %s"
                               % (path.relative_to(ROOT), exc))


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise MeasurementError("%s okunamadı: %s" % (path.relative_to(ROOT), exc))


def vercel_side():
    """(raw_data, flat_tokens, manifest) — Vercel kanonik renk token'ları."""
    raw = load_json(VERCEL / "raw.json")
    variables = (raw.get("colors") or {}).get("cssVariables")
    if not isinstance(variables, dict) or not variables:
        raise MeasurementError("%s: colors.cssVariables haritası yok/boş"
                               % REL_VERCEL_RAW)
    flat = {}
    for name, meta in variables.items():
        value = meta.get("value") if isinstance(meta, dict) else meta
        if not isinstance(value, str):
            raise MeasurementError("%s: %s için metin değer yok"
                                   % (REL_VERCEL_RAW, name))
        flat[name] = value
    manifest = load_json(VERCEL / "tokens.json")
    return raw, flat, manifest


def dashboard_side():
    """(base, light, tokens_json) — kök dashboard token katmanı."""
    css = read_text(DASH_CSS)
    base = _block(css, r":root")
    light = _block(css, r':root\[data-theme="light"\]')
    if not base:
        raise MeasurementError("%s: :root bloğu yok" % REL_DASH_CSS)
    if not light:
        raise MeasurementError('%s: :root[data-theme="light"] bloğu yok'
                               % REL_DASH_CSS)
    return base, light, load_json(DASH_JSON)


def categorize(name: str) -> str:
    for key, _label, pattern in CATEGORY_RULES:
        if re.search(pattern, name):
            return key
    return UNCATEGORIZED[0]


def norm_value(value: str) -> str:
    return re.sub(r"\s+", "", value.strip().lower())


def consumer_imports(path: Path) -> bool:
    """Yüzey Vercel token katmanını tüketiyor mu (link/@import)?

    İki biçim sayılır: (1) ham ayna (`design-system/vercel/*tokens.css`),
    (2) GENERATED adapter varyantının servis rotası
    (`/design-system/vercel-theme.css`) — varyantın ön-koşul kapanışı aynadan
    birebir kopyalanır (üretici `generate_vercel_theme.py` aynayı okur), yani
    yüzey Vercel katmanını tüketiyor demektir. Tazelik bayt düzeyinde
    `--check` ile kilitli kalır.
    """
    text = read_text(path)
    return bool(
        re.search(r'design-system/vercel/[^"\'\s]*tokens\.css', text)
        or re.search(r'design-system/vercel-theme\.css', text)
    )


def build_payload() -> dict:
    raw, vercel, manifest = vercel_side()
    base, light, dash = dashboard_side()

    vercel_names = sorted(vercel)
    base_names = sorted(base)
    light_names = sorted(light)

    groups = manifest.get("tokens")
    if not isinstance(groups, dict) or not groups:
        raise MeasurementError("%s: tokens haritası yok" % REL_VERCEL_JSON)
    group_counts = {name: len(items) for name, items in sorted(groups.items())}

    counts = {}
    for name in base_names:
        key = categorize(name)
        counts[key] = counts.get(key, 0) + 1

    shared = sorted(set(vercel_names) & set(base_names))
    vercel_only = sorted(set(vercel_names) - set(base_names))
    dash_only = sorted(set(base_names) - set(vercel_names))
    conflicts = sorted(n for n in shared if vercel[n] != base[n])

    dash_by_value = {}
    for name in base_names:
        dash_by_value.setdefault(norm_value(base[name]), []).append(name)
    value_matches = []
    for name in vercel_names:
        hits = dash_by_value.get(norm_value(vercel[name]), [])
        value_matches.append({
            "vercel": name,
            "value": vercel[name],
            "dashboard_tokens": sorted(hits),
        })
    matched = [row for row in value_matches if row["dashboard_tokens"]]

    consumers = []
    for path in (PREVIEW_HTML, NEXT_GLOBALS):
        consumers.append({
            "path": str(path.relative_to(ROOT)),
            "imports_vercel": consumer_imports(path),
        })

    role_names = [row[0] for row in NEAREST_ROLE]
    findings = []

    def finding(fid, severity, message, detail=None):
        item = {"id": fid, "severity": severity, "message": message}
        if detail:
            item["detail"] = detail
        findings.append(item)

    uncategorized = sorted(n for n in base_names
                           if categorize(n) == UNCATEGORIZED[0])
    if uncategorized:
        finding(
            "dashboard-token-uncategorized", "block",
            "Dashboard token'ı kategori kurallarının hiçbirine uymuyor — "
            "kategori envanteri eksik sayar (allowlist'e adı ekleyin ya da "
            "yeni kategori tanımlayın).",
            uncategorized,
        )
    orphans = sorted(n for n in light_names if n not in base_names)
    if orphans:
        finding(
            "light-override-orphan", "block",
            "Light override'ı temel :root'ta olmayan bir adı override ediyor "
            "(ölü override — sessiz stil kaybı).",
            orphans,
        )
    if manifest.get("count") != len(vercel_names):
        finding(
            "vercel-count-pin", "block",
            "tokens.json `count` alanı raw.json'daki token sayısıyla uyuşmuyor.",
            {"count": manifest.get("count"), "raw": len(vercel_names)},
        )
    missing_css = sorted(
        "--%s" % name for name, value in (dash.get("color") or {}).items()
        if isinstance(value, str) and "--%s" % name not in base
    )
    if missing_css:
        finding(
            "dashboard-json-css-drift", "block",
            "tokens.json color adı tokens.css :root'ta yok (JSON↔CSS drift).",
            missing_css,
        )
    if conflicts:
        finding(
            "shared-name-conflict", "block",
            "İki katman AYNI adı farklı değerle taşıyor: aynı cascade'e import "
            "edilirse import sırası kazananı belirler (sessiz çakışma).",
            [{"name": n, "vercel": vercel[n], "dashboard": base[n]}
             for n in conflicts],
        )
    elif shared:
        finding(
            "shared-name-same-value", "warn",
            "İki katman aynı adı paylaşıyor (değerler aynı); yine de tek kaynak "
            "seçilmelidir.",
            shared,
        )
    if set(role_names) != set(vercel_names):
        finding(
            "nearest-role-coverage", "block",
            "Editoryel eşleme tablosu Vercel token kümesiyle birebir değil "
            "(eksik/fazla ad).",
            {"table_only": sorted(set(role_names) - set(vercel_names)),
             "vercel_only": sorted(set(vercel_names) - set(role_names))},
        )
    value_drift = []
    for name, value, _role, _note in NEAREST_ROLE:
        if name in vercel and vercel[name] != value:
            value_drift.append({"token": name, "table": value,
                                "raw": vercel[name]})
    if value_drift:
        finding(
            "nearest-role-value-drift", "block",
            "Editoryel tablodaki Vercel değeri raw.json'dan farklı (yorum "
            "katmanı kaynaktan koptu).",
            value_drift,
        )
    if not any(c["imports_vercel"] for c in consumers):
        finding(
            "vercel-not-consumed", "info",
            "Vercel katmanını import eden bir tüketici yok: set şu an yalnız "
            "referans katmanı (drift'in görünür etkisi yok).",
            [c["path"] for c in consumers],
        )
    finding(
        "theme-crossing", "info",
        "Vercel yakalaması yalnız light; dashboard varsayılanı dark + light "
        "override. Renk rolleri light override'lar üzerinden okunur.",
        {"vercel_theme": "light-only",
         "dashboard_theme": "dark default + light override"},
    )
    finding(
        "value-reuse", "info",
        "Vercel değerlerinden dashboard değeriyle BİREBİR aynı olanlar "
        "(ad bazlı çakışma olmadan değer kimliği).",
        {"exact_matches": len(matched), "rows": matched},
    )

    blocked = [f for f in findings if f["severity"] == "block"]
    payload = {
        "schema": SCHEMA,
        "generated_by": "design-system/scripts/report_vercel_dashboard_drift.py",
        "status": "blocked" if blocked else "ok",
        "sources": {
            "vercel": {
                "raw": REL_VERCEL_RAW,
                "css": REL_VERCEL_CSS,
                "json": REL_VERCEL_JSON,
                "page": raw.get("url"),
                "extractedAt": raw.get("extractedAt"),
                "tool": (manifest.get("source") or {}).get("tool"),
                "theme": "light-only",
                "count": len(vercel_names),
                "group_counts": group_counts,
            },
            "dashboard": {
                "css": REL_DASH_CSS,
                "json": REL_DASH_JSON,
                "theme": "dark default + light override",
                "captured": dash.get("extracted"),
                "base_count": len(base_names),
                "light_override_count": len(light_names),
                "json_color_count": sum(
                    1 for value in (dash.get("color") or {}).values()
                    if isinstance(value, str)
                ),
            },
            "consumers": consumers,
        },
        "vercel_tokens": vercel_names,
        "dashboard_base_tokens": base_names,
        "dashboard_light_overrides": light_names,
        "categories": {
            "counts": {key: counts.get(key, 0)
                       for key, _label, _pat in CATEGORY_RULES},
            "labels": {key: label for key, label, _pat in CATEGORY_RULES},
            "uncategorized": uncategorized,
        },
        "overlap": {
            "shared_names": shared,
            "shared_name_value_conflicts": conflicts,
            "vercel_only": vercel_only,
            "dashboard_only_count": len(dash_only),
            "distinct_css_names": len(set(base_names) | set(vercel_names)),
            "exact_value_matches": matched,
        },
        "nearest_role": [
            {"vercel": name, "vercel_value": value,
             "nearest_dashboard_role": role, "difference": note}
            for name, value, role, note in NEAREST_ROLE
        ],
        "findings": findings,
    }
    return payload


def render_json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2,
                      sort_keys=True) + "\n"


def md_table(header, rows):
    out = ["| " + " | ".join(str(c) for c in header) + " |",
           "|" + "|".join(["---"] * len(header)) + "|"]
    for row in rows:
        out.append("| " + " | ".join(str(c) for c in row) + " |")
    return out


def render_md(payload: dict) -> str:
    sources = payload["sources"]
    v = sources["vercel"]
    d = sources["dashboard"]
    overlap = payload["overlap"]
    counts = payload["categories"]["counts"]
    labels = payload["categories"]["labels"]
    base_count = d["base_count"]
    vercel_count = v["count"]
    light_count = d["light_override_count"]
    shared = overlap["shared_names"]
    conflicts = overlap["shared_name_value_conflicts"]

    lines = []
    add = lines.append
    add("# Vercel ↔ kök dashboard design-token fark raporu")
    add("")
    add("**ÜRETİLİR:** `design-system/scripts/report_vercel_dashboard_drift.py` —")
    add("bu dosya elle düzenlenmez. `--check` diskteki kopyayı (bu markdown +")
    add("`vercel_dashboard_drift.json`) jeneratör çıktısıyla BAYT karşılaştırır;")
    add("elle düzenleme veya kaynak yenilenmesi drift sayılır ve CI'da fail-closed")
    add("bloke eder.")
    add("")
    add("**Makine-okunur kopya:** `_calisma/CIKTI/vercel_dashboard_drift.json`")
    add("(`schema: %s`). CI'da aynı belge `logs/vercel_dashboard_drift.json`" % SCHEMA)
    add("olarak mevcut `precommit-logs` artifact'ına girer; ayrı artifact adı")
    add("açılmaz.")
    add("")
    add("> Bu rapor tasarım token'larını karşılaştırır; GitHub/Vercel kimlik")
    add("> doğrulama veya API secret'larıyla ilgili değildir.")
    add("")
    add("## Karşılaştırma kapsamı")
    add("")
    add("- Vercel: `%s` ve `%s` (ham kaynak: `%s`)"
        % (REL_VERCEL_CSS, REL_VERCEL_JSON, REL_VERCEL_RAW))
    add("- Kök dashboard: `%s` ve `%s`" % (REL_DASH_CSS, REL_DASH_JSON))
    add("- Dashboard tüketimi: %s"
        % ", ".join("`%s`" % c["path"] for c in sources["consumers"]))
    add("")
    add("## Yönetici özeti")
    add("")
    add("- Vercel kanonik katmanı **%d light-theme renk token'ı** içerir." % vercel_count)
    add("- Kök dashboard kanonik CSS'i **%d temel token** ve bunların **%d light-theme"
        % (base_count, light_count))
    add("  override'ı** içerir.")
    add("- İki CSS katmanı arasında **aynı adlı token %s**: doğrudan override veya"
        % ("yok" if not shared else "%d adet" % len(shared)))
    add("  çakışma riski `%d/%d`; birlikte import edilseler toplam `%d` benzersiz CSS"
        % (len(conflicts), vercel_count, overlap["distinct_css_names"]))
    add("  custom-property adı oluşur.")
    matched = len(overlap["exact_value_matches"])
    add("- Birebir değer eşleşmesi: Vercel'in %d değerinden **%d**'i dashboard"
        % (vercel_count, matched))
    if matched:
        add("  değerleriyle birebir aynı — ama **ad bazlı çakışma yok**, yani bu bir")
        add("  ad eşleşmesi değil, değer kimliğidir.")
    else:
        add("  değerleriyle birebir aynı değil: iki palet değer düzeyinde de")
        add("  bağımsız (yeniden kullanım yok).")
    add("- Vercel seti renk dışında token içermez. Dashboard ise %d kategoride"
        % len([k for k, c in counts.items() if c]))
    add("  toplam %d token taşır (%s)."
        % (base_count, ", ".join(
            "%s %d" % (labels[k], counts[k])
            for k, _l, _p in CATEGORY_RULES if counts.get(k))))
    consumed = any(c["imports_vercel"] for c in sources["consumers"])
    if consumed:
        who = ", ".join("`%s`" % c["path"] for c in sources["consumers"]
                        if c["imports_vercel"])
        add("- Vercel token'ları bir tüketici tarafından import ediliyor")
        add("  (%s Vercel adapter varyantını — "
            "`/design-system/vercel-theme.css` — yükler; ön-koşul kapanışı "
            "aynadan birebir)." % who)
    else:
        add("- Vercel token'ları şu anda dashboard tarafından tüketilmiyor")
        add("  (`%s` yalnız kök token katmanını import ediyor)."
            % sources["consumers"][0]["path"])
    add("")
    add("**Rapor durumu:** `%s`" % payload["status"])
    add("")
    lines.extend(md_table(
        ["Bulgu", "Önem", "Açıklama"],
        [["`%s`" % f["id"], f["severity"], f["message"]]
         for f in payload["findings"]],
    ))
    add("")
    add("## Kaynak ve kapsam farkları")
    add("")
    lines.extend(md_table(
        ["Özellik", "Vercel token seti", "Kök dashboard token seti"],
        [
            ["Kaynak", "Canlı `%s` computed-style yakalama" % v["page"],
             "Canlı CI dashboard `%s` çıkarımı" % sources["consumers"][0]["path"]],
            ["Yakalama tarihi", v["extractedAt"], d.get("captured") or "—"],
            ["Tema", v["theme"], d["theme"]],
            ["Kanonik CSS", "%d color" % vercel_count,
             "%d temel token + %d light override" % (base_count, light_count)],
            ["Kapsam", "Kısmi; yalnız renk",
             "Uygulama geneli UI sözleşmesi (%d kategori)" % len(
                 [k for k, c in counts.items() if c])],
            ["Tüketici", "Şu anda dashboard dışında referans katmanı",
             ", ".join("`%s`" % c["path"] for c in sources["consumers"])],
        ],
    ))
    add("")
    add("## Dashboard kategori envanteri")
    add("")
    add("Kök dashboard'un %d temel CSS token'ının kategori dağılımı:" % base_count)
    add("")
    rows = [[labels[k], counts[k]] for k, _l, _p in CATEGORY_RULES]
    rows.append(["**Toplam**", "**%d**" % base_count])
    lines.extend(md_table(["Kategori", "Adet"], rows))
    add("")
    add("Light tema bu %d adın %d'sini override eder; %d yeni ve benzersiz ad"
        % (base_count, light_count, len(set(payload["dashboard_light_overrides"])
                                       - set(payload["dashboard_base_tokens"]))))
    add("eklemez. Vercel'in %d token'ının tamamı renk kategorisindedir." % vercel_count)
    add("")
    add("## Vercel token'larının dashboard karşılıkları")
    add("")
    add("Aşağıdaki eşleştirmeler **birebir CSS adı eşlemesi değildir** (editoryel")
    add("veri; değerler `raw.json` ile kapıda doğrulanır). En yakın olası dashboard")
    add("rolü gösterilmiştir; renk/oyut veya semantik farkı olan yerler açıkça")
    add("belirtilmiştir.")
    add("")
    lines.extend(md_table(
        ["Vercel token", "Vercel değeri", "Dashboard'daki en yakın rol", "Fark"],
        [["`%s`" % r["vercel"], "`%s`" % r["vercel_value"],
          r["nearest_dashboard_role"], r["difference"]]
         for r in payload["nearest_role"]],
    ))
    add("")
    add("## En önemli farklar ve riskler")
    add("")
    for idx, note in enumerate(RISK_NOTES, 1):
        add("%d. %s" % (idx, note))
    add("")
    add("## Öneri")
    add("")
    for note in RECOMMENDATIONS:
        add("- %s" % note)
    if consumed:
        add("")
        add("**Uygulandı:** Vercel katmanı **scoped adapter** olarak bağlandı — "
            "`design-system/vercel/theme.css` (`:root[data-theme=\"vercel\"]`; "
            "32 yuvanın 28'i bağlı, success/warning ailesindeki 4 yuva adıyla "
            "ilan edilmiş istisna). Ham katman global import EDİLMEZ; kapı: "
            "`check-design-tokens` contract 9 + `check-vercel-drift-report`.")
    add("")
    add("## Makine-okunur rapor şeması")
    add("")
    add("`vercel_dashboard_drift.json` alanları (`--json` ile stdout'tan da alınır):")
    add("")
    lines.extend(md_table(
        ["Alan", "İçerik"],
        [
            ["`schema`", "Belge sürümü (`%s`)" % SCHEMA],
            ["`status`", "`ok` ya da `blocked` (block bulgu varsa)"],
            ["`sources.*`", "İki katmanın kaynak yolu, tema, sayı ve provenansı"],
            ["`sources.consumers[]`", "Yüzey → `imports_vercel` (tüketim kanıtı)"],
            ["`vercel_tokens` / `dashboard_base_tokens`", "İki katmanın tam ad listeleri"],
            ["`dashboard_light_overrides`", "Light override adları"],
            ["`categories.counts` / `.uncategorized`", "Kategori dağılımı; kurala uymayan ad"],
            ["`overlap.*`", "Paylaşılan/tek-taraflı adlar, değer kimliği, çakışmalar"],
            ["`nearest_role[]`", "Editoryel eşleme (değeri raw.json ile kapıda doğrulanır)"],
            ["`findings[]`", "`id` + `severity` (`block`/`warn`/`info`) + `detail`"],
        ],
    ))
    add("")
    add("Tüketici tarafı: `status` ve `findings[].severity == \"block\"` alanları")
    add("kapıdır; `overlap.distinct_css_names` ve `categories.counts` ölçümdür.")
    add("")
    add("## Yeniden üretim")
    add("")
    add("```bash")
    add("# iki kopyayı kaynaklardan yeniden üret (JSON + markdown)")
    add("python3 design-system/scripts/report_vercel_dashboard_drift.py")
    add("")
    add("# tazelik + yapısal sağlık kapısı (drift → rc 1)")
    add("python3 design-system/scripts/report_vercel_dashboard_drift.py --check")
    add("")
    add("# yalnız makine-okunur belge (stdout = tek JSON)")
    add("python3 design-system/scripts/report_vercel_dashboard_drift.py --json")
    add("")
    add("# mirror katmanı hâlâ raw.json'a birebir mi?")
    add("python3 design-system/vercel/scripts/check_vercel_tokens.py")
    add("python3 design-system/scripts/check_tokens.py")
    add("```")
    add("")
    add("## Kanıt dosyaları")
    add("")
    for rel in (
        REL_VERCEL_RAW,
        REL_VERCEL_CSS,
        REL_VERCEL_JSON,
        "design-system/vercel/scripts/check_vercel_tokens.py",
        REL_DASH_CSS,
        REL_DASH_JSON,
        "design-system/scripts/check_tokens.py",
        "design-system/scripts/report_vercel_dashboard_drift.py",
        "_calisma/CIKTI/vercel_dashboard_drift.json",
        "_calisma/CIKTI/test_vercel_dashboard_drift.py",
    ):
        add("- `%s`" % rel)
    add("")
    return "\n".join(lines)


def _rel(path: Path) -> str:
    """Repo-içi yol kısaltması; repo dışı yol (test/fixture) olduğu gibi kalır."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _print_findings(payload: dict, stream) -> None:
    for item in payload["findings"]:
        print("  [%s] %s: %s" % (item["severity"], item["id"], item["message"]),
              file=stream)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Vercel ↔ dashboard token farkı (makine-okunur + markdown)")
    parser.add_argument("--check", action="store_true",
                        help="diskteki iki kopya taze + yapı sağlıklı değilse rc 1")
    parser.add_argument("--json", action="store_true",
                        help="stdout'a tek JSON belgesi bas (dosya yazmaz)")
    parser.add_argument("--json-out", help="JSON belgesini bu yola yaz")
    parser.add_argument("--md-out", help="markdown raporunu bu yola yaz")
    args = parser.parse_args(argv)

    json_mode = bool(args.json or args.json_out)

    try:
        payload = build_payload()
    except MeasurementError as exc:
        print("VERCEL DRIFT RAPORU (ölçüm imkânsız): %s" % exc,
              file=sys.stderr)
        return 2

    rendered_json = render_json(payload)
    rendered_md = render_md(payload)

    if args.json and not args.json_out and not args.md_out:
        sys.stdout.write(rendered_json)
        return 0

    if args.json or args.json_out or args.md_out:
        if args.json_out:
            Path(args.json_out).write_text(rendered_json, encoding="utf-8")
            print("yazıldı: %s" % args.json_out, file=sys.stderr)
        if args.md_out:
            Path(args.md_out).write_text(rendered_md, encoding="utf-8")
            print("yazıldı: %s" % args.md_out, file=sys.stderr)
        if json_mode:
            sys.stdout.write(rendered_json)
        return 0

    if args.check:
        problems = []
        for path, rendered in ((OUT_JSON, rendered_json), (OUT_MD, rendered_md)):
            rel = _rel(path)
            if not path.exists():
                problems.append("eksik dosya: %s" % rel)
            elif path.read_text(encoding="utf-8") != rendered:
                problems.append("%s jeneratör çıktısıyla birebir değil" % rel)
        if payload["status"] != "ok":
            problems.append("rapor durumu `%s` — block bulgular var"
                            % payload["status"])
        if problems:
            print("VERCEL DRIFT RAPORU DRIFT:", file=sys.stderr)
            for line in problems:
                print("  %s" % line, file=sys.stderr)
            _print_findings(payload, sys.stderr)
            print("  yeniden üret: python3 "
                  "design-system/scripts/report_vercel_dashboard_drift.py",
                  file=sys.stderr)
            return 1
        print("OK — Vercel↔dashboard drift raporu taze ve yapısal olarak sağlıklı "
              "(%d Vercel + %d dashboard token, paylaşılan ad %d)"
              % (payload["sources"]["vercel"]["count"],
                 payload["sources"]["dashboard"]["base_count"],
                 len(payload["overlap"]["shared_names"])), file=sys.stderr)
        return 0

    OUT_JSON.write_text(rendered_json, encoding="utf-8")
    OUT_MD.write_text(rendered_md, encoding="utf-8")
    print("yazıldı: %s (%d bayt)" % (_rel(OUT_JSON),
                                     len(rendered_json.encode("utf-8"))))
    print("yazıldı: %s (%d satır)" % (_rel(OUT_MD),
                                      rendered_md.count("\n") + 1))
    print("durum: %s (%d bulgu)" % (payload["status"], len(payload["findings"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
