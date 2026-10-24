#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_dashboard_security_surface.py — panonun güvenlik-yüzeyi kartı.

Sözleşme (kullanıcı isteği: "hangi savunmaların aktif olduğunu /api/health'ten
gösteren küçük bir görünüm"):

  * TEK KAYNAK: kapı listesi yalnız `apps/dashboard-next/lib/security-surface.ts`
    içinde tanımlanır. Uç (`app/api/health/route.ts`) onu yayınlar, kart
    (`components/SecuritySurfaceCard.tsx`) yayını okur. Kapı id'si ya da durum
    etiketi ikinci bir dosyada tekrar ederse bu dosya kırmızıya döner —
    ayrışan bir liste, panelin yalan söylemesinin en olası yoludur.
  * TEL FAIL-CLOSED: `/api/health` gövdesi bir gözlemdir, iddia değil.
    Tanınmayan durum `unknown`a düşer, `active`e ASLA. `parseSecuritySurface`
    bunu tek geçitte uygular; bozuk/eksik gövde boş liste döner ve kart
    "bilinmiyor" basar — "hepsi aktif" diye değil.
  * TOKEN YOK → YEŞİL YOK: `PREVIEW_RUN_NOW_TOKEN` tanımsızken run-now
    kapısının durumu `fail-closed`tır. Bu, bir önceki turda sunucu tarafında
    sabitlenen davranışın (tokensız mod fail-closed) pano aynasıdır; yeşile
    dönmesi sessiz bir fail-open iddiası olurdu.
  * RENK KAPALI: rozet varyant tablosu (`defenseBadge`) durum kümesiyle
    birebir hizalı ve yalnız `active` yeşil. `widened`/`fail-closed` sarı
    kalır: ikisi de "dikkat"tir, "her şey yolunda" değil.

İki katman:
  1. STATİK (her ortam): kaynak ayrıştırma — id tekliği, uç/kart kablosu,
     varyant tablosunun kapalılığı. Node/Next/Chromium GEREKMEZ.
  2. DAVRANIŞ (node varsa): `security-surface.ts` Node'un type-stripping'i ile
     gerçekten çalıştırılır ve durum tablosu env matrisleriyle ölçülür.
     Node yoksa (ya da `--experimental-strip-types` desteklenmiyorsa) SKIP —
     sebebi açıkça yazılır; sessiz skip bu depodaki hastalıktır.

Koşum:
  python3 -m unittest _calisma.CIKTI.test_dashboard_security_surface
"""

import json
import pathlib
import re
import shutil
import subprocess
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
NEXT = REPO / "apps" / "dashboard-next"
LIB = NEXT / "lib" / "security-surface.ts"
ROUTE = NEXT / "app" / "api" / "health" / "route.ts"
CARD = NEXT / "components" / "SecuritySurfaceCard.tsx"
PANEL_STYLE = NEXT / "components" / "panel-style.ts"
PANEL_PAGE = NEXT / "app" / "(panel)" / "page.tsx"

SOURCE_ROOTS = (NEXT / "app", NEXT / "components", NEXT / "lib")

NODE = shutil.which("node")

# Kapıların beklenen kümesi. Kasten burada da yazılı: kaynak silinirse
# (varyant/id kaybolursa) id tekliği testi tek başına geçemez.
EXPECTED_INVARIANT_IDS = {"trusted-host", "csp-nonce", "static-root"}
ENV_DRIVEN_IDS = {"stop-peer", "run-now-token"}
EXPECTED_IDS = EXPECTED_INVARIANT_IDS | ENV_DRIVEN_IDS

# Durum etiketleri tek kaynakta (`STATE_LABELS`) yaşar; bu literaller başka
# dosyada görünürse panel kendi metnini yazmış demektir.
STATE_LABEL_LITERALS = ("AKTİF", "FAIL-CLOSED", "GENİŞ", "BİLİNMİYOR")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def app_sources():
    """(yol, kaynak) — app/ + components/ + lib/ altındaki tüm TS/TSX."""
    files = set()
    for root in SOURCE_ROOTS:
        for pat in ("*.ts", "*.tsx"):
            files.update(root.rglob(pat))
    return [(p, read(p)) for p in sorted(files)]


def strip_js_comments(text):
    """Yorumları soy: prose içindeki id/etiket adı iddiayı vakumlamasın."""
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    return re.sub(r"//[^\n]*", " ", text)


def source_defense_ids(text):
    """`securitySurface()`in satırlarındaki `id: "..."` değerleri."""
    return set(re.findall(r'id:\s*"([^"]+)"', text))


def cva_variant_map(text, name):
    """`const <name> = cva("...", { variants: { <key>: { ... } } })` haritası.

    Anahtar → varyantın sınıf dizgesi. Tam bir TS ayrıştırıcısı değil; kapalı
    küme iddiasını ölçmek için yeterli (varyant bloğunun ilk seviyesi).
    """
    anchor = text.find("const %s = cva(" % name)
    if anchor < 0:
        raise AssertionError("%s cva tabanı bulunamadı" % name)
    variants = text.find("variants:", anchor)
    if variants < 0:
        raise AssertionError("%s variants bloğu bulunamadı" % name)
    open_brace = text.find("{", variants)
    depth, i = 0, open_brace
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                break
        i += 1
    body = text[open_brace + 1 : i]
    out = {}
    for m in re.finditer(
        r'(?:"([^"]+)"|\'([^\']+)\'|([A-Za-z][\w-]*))\s*:\s*("(?:[^"]*)"|\'(?:[^\']*)\')',
        body,
    ):
        key = m.group(1) or m.group(2) or m.group(3)
        out[key] = m.group(4)[1:-1]
    return out


class SourceSingleSourceTest(unittest.TestCase):
    """Kapı listesinin TEK kaynakta yaşadığının statik kanıtı."""

    def test_library_declares_the_expected_gates(self):
        ids = source_defense_ids(read(LIB))
        self.assertEqual(ids, EXPECTED_IDS,
                         "güvenlik kapısı kümesi değişti — beklenen %s, bulunan %s"
                         % (sorted(EXPECTED_IDS), sorted(ids)))

    def test_state_set_is_closed_and_matches_the_type(self):
        """`DEFENSE_STATES` kapalı kümedir ve tip ondan türetilmiş gibi birebir."""
        src = read(LIB)
        m = re.search(r"DEFENSE_STATES\s*=\s*\[(.*?)\]\s*as const", src, re.S)
        self.assertIsNotNone(m, "DEFENSE_STATES bulunamadı")
        states = re.findall(r'"([^"]+)"', m.group(1))
        self.assertEqual(states, ["active", "fail-closed", "widened", "unknown"],
                         "durum kümesi değişti: %s" % states)
        self.assertIn("satisfies readonly DefenseState[]", src,
                      "durum kümesi `satisfies` ile tipe bağlanmalı (ayrışma "
                      "derleme hatası olsun, runtime sürprizi değil)")

    def test_no_defense_id_literal_leaks_outside_the_library(self):
        """Uç ya da kart kendi id listesini yazarsa iki liste ayrışır."""
        leaks = []
        for path, src in app_sources():
            if path == LIB:
                continue
            stripped = strip_js_comments(src)
            for gate_id in sorted(EXPECTED_IDS):
                if '"%s"' % gate_id in stripped:
                    leaks.append("%s: %s" % (path.name, gate_id))
        self.assertEqual(leaks, [],
                         "kapı id'si tek kaynağın dışında tekrar edilmiş: %s"
                         % leaks)

    def test_no_state_label_literal_leaks_outside_the_library(self):
        leaks = []
        for path, src in app_sources():
            if path == LIB:
                continue
            stripped = strip_js_comments(src)
            for label in STATE_LABEL_LITERALS:
                if label in stripped:
                    leaks.append("%s: %s" % (path.name, label))
        self.assertEqual(leaks, [],
                         "durum etiketi panelde elle yazılmış (tek kaynak "
                         "ihlali): %s" % leaks)


class HealthRouteWiringTest(unittest.TestCase):
    """Uç, kararı üretmez; tek kaynağı yayınlar."""

    def test_route_publishes_the_single_source(self):
        src = read(ROUTE)
        self.assertIn('from "@/lib/security-surface"', src)
        self.assertRegex(src, r"security:\s*securitySurface\(",
                         "sağlık ucu `security` alanını `securitySurface()`ten "
                         "almalı — elle yazılmış liste ikinci kaynak olurdu")

    def test_route_keeps_the_existing_health_fields(self):
        """Geriye uyum: kart eklenirken mevcut alanlar düşmemeli."""
        src = read(ROUTE)
        for field in ("status", "archil", "a11y"):
            self.assertIn(field, src, "sağlık gövdesinden alan düştü: %s" % field)


class CardWiringTest(unittest.TestCase):
    """Kart, `/api/health`i okur ve kararı kendisi vermez."""

    @classmethod
    def setUpClass(cls):
        cls.src = read(CARD)

    def test_card_reads_the_health_endpoint(self):
        self.assertIn("/api/health", self.src,
                      "kart savunma durumunu `/api/health`ten okumalı")

    def test_card_parses_the_wire_fail_closed(self):
        self.assertIn('from "@/lib/security-surface"', self.src)
        self.assertIn("parseSecuritySurface(", self.src,
                      "kart gövdeyi doğrulayan ayrıştırıcıdan geçirmeli")

    def test_card_uses_the_panel_shell_and_variant_table(self):
        for token in ("PanelCard", "PanelCardHeader", "PanelCardTitle"):
            self.assertIn(token, self.src, "kart kabuğu eksik: %s" % token)
        self.assertIn("defenseBadge(", self.src,
                      "rozet tonu varyant tablosundan gelmeli (çağrı yerinde "
                      "ternary değil)")

    def test_card_never_assumes_all_active(self):
        """Okunamayan yüzey 'bilinmiyor' basar; 'aktif' değil."""
        self.assertIn('defenseStateLabel("unknown")', self.src,
                      "boş/bozuk gövde 'bilinmiyor' olarak basılmalı")
        self.assertNotIn("defaultState", self.src)

    def test_page_renders_the_card(self):
        page = read(PANEL_PAGE)
        self.assertIn('from "@/components/SecuritySurfaceCard"', page)
        self.assertIn("<SecuritySurfaceCard", page,
                      "kart hiçbir sayfada render edilmiyorsa görünüm yok")


class BadgeVariantTableTest(unittest.TestCase):
    """Rozet tablosu kapalı küme; yalnız `active` yeşildir."""

    @classmethod
    def setUpClass(cls):
        cls.variants = cva_variant_map(read(PANEL_STYLE), "defenseBadge")
        m = re.search(r"DEFENSE_STATES\s*=\s*\[(.*?)\]\s*as const",
                      read(LIB), re.S)
        cls.states = re.findall(r'"([^"]+)"', m.group(1)) if m else []

    def test_table_covers_exactly_the_closed_state_set(self):
        self.assertEqual(sorted(self.variants), sorted(self.states),
                         "rozet tablosu durum kümesiyle hizasız — yeni bir "
                         "durum sessizce renksiz kalırdı")

    def test_only_active_is_green(self):
        green = [k for k, cls in self.variants.items() if "text-ok" in cls]
        self.assertEqual(green, ["active"],
                         "yeşil yalnız `active` olmalı; bulunan: %s" % green)
        for state in ("fail-closed", "widened"):
            self.assertIn("text-warn", self.variants[state],
                          "`%s` uyarı tonunda olmalı (sarı), yeşil değil"
                          % state)
        self.assertIn("text-muted", self.variants["unknown"])

    def test_default_variant_is_the_neutral_one(self):
        src = read(PANEL_STYLE)
        m = re.search(
            r"const defenseBadge = cva\(.*?defaultVariants:\s*\{([^}]*)\}",
            src, re.S)
        self.assertIsNotNone(m, "defenseBadge defaultVariants bulunamadı")
        self.assertIn("unknown", m.group(1),
                      "varsayılan durum `unknown` olmalı — renksiz varsayılan "
                      "yeşile düşen bir varsayılan olurdu")


# ── davranış katmanı (node varsa) ───────────────────────────────────────────

PROBE = r"""
const { pathToFileURL } = await import("node:url");
const mod = await import(pathToFileURL(process.argv[2]).href);
const envs = JSON.parse(process.argv[3]);
const out = [];
for (const env of envs) {
  out.push({
    env,
    rows: mod.securitySurface(env),
    runNow: mod.securitySurface(env).find((d) => d.id === "run-now-token"),
    stop: mod.securitySurface(env).find((d) => d.id === "stop-peer"),
  });
}
const parsed = {
  unknownState: mod.parseSecuritySurface({
    security: [{ id: "k", label: "etiket", state: "open" }],
  }),
  missingId: mod.parseSecuritySurface({
    security: [{ id: "", label: "etiket", state: "active" }],
  }),
  notArray: mod.parseSecuritySurface({ security: "nope" }),
  nullBody: mod.parseSecuritySurface(null),
};
console.log(JSON.stringify({ envs: out, parsed, states: mod.DEFENSE_STATES }));
"""


def _node_strip_types_supported():
    if not NODE:
        return "node yok"
    try:
        probe = subprocess.run(
            [NODE, "--experimental-strip-types", "-e", "0"],
            capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover
        return "node çalıştırılamadı: %s" % exc
    if probe.returncode != 0:
        return "node --experimental-strip-types desteklenmiyor"
    return ""


_STRIP_TYPES_GAP = _node_strip_types_supported()


@unittest.skipIf(_STRIP_TYPES_GAP, "davranış katmanı atlandı: %s"
                 % (_STRIP_TYPES_GAP or ""))
class FailClosedBehaviourTest(unittest.TestCase):
    """`security-surface.ts` GERÇEKTEN çalıştırılır — kaynak okumak yetmez.

    Aşağıdaki env matrisi, bir önceki turda sunucu tarafında sabitlenen
    "tokensız mod fail-closed" davranışının pano aynasını ölçer.
    """

    @classmethod
    def setUpClass(cls):
        cls.envs = [
            {},
            {"PREVIEW_RUN_NOW_TOKEN": "s3cret"},
            {"PREVIEW_STOP_ALLOWLIST": "10.0.0.5, 192.168.1.9"},
            {"PREVIEW_RUN_NOW_TOKEN": "  ", "PREVIEW_STOP_ALLOWLIST": "10.0.0.5"},
        ]
        td = tempfile.mkdtemp(prefix="security_surface_")
        cls.addClassCleanup(shutil.rmtree, td, True)
        script = pathlib.Path(td) / "probe.mjs"
        script.write_text(PROBE, encoding="utf-8")
        proc = subprocess.run(
            [NODE, "--experimental-strip-types", str(script), str(LIB),
             json.dumps(cls.envs)],
            capture_output=True, text=True, timeout=60)
        if proc.returncode != 0:
            raise AssertionError("node probe düştü: %s" % proc.stderr[-2000:])
        cls.data = json.loads(proc.stdout)

    def test_no_token_means_fail_closed_never_active(self):
        empty = self.data["envs"][0]
        self.assertEqual(empty["runNow"]["state"], "fail-closed",
                         "token yokken run-now kapısı `fail-closed` olmalı — "
                         "yeşil durum sessiz bir fail-open iddiasıdır")
        # Boşluk-only token da token DEĞİLDİR (sunucu tarafı `.trim()` aynası).
        blank = self.data["envs"][3]
        self.assertEqual(blank["runNow"]["state"], "fail-closed",
                         "yalnız boşluk içeren token token sayılmamalı")

    def test_present_token_arms_the_gate(self):
        armed = self.data["envs"][1]
        self.assertEqual(armed["runNow"]["state"], "active",
                         "token varken run-now kapısı `active` olmalı")

    def test_stop_allowlist_widening_is_reported(self):
        default = self.data["envs"][0]["stop"]
        widened = self.data["envs"][2]["stop"]
        self.assertEqual(default["state"], "active",
                         "izin kümesi verilmezse loopback-only kalmalı")
        self.assertEqual(widened["state"], "widened",
                         "izin kümesi genişletilince durum `widened` olmalı")
        self.assertIn("10.0.0.5", widened["detail"],
                      "genişletilen peer ayrıntıda GÖRÜNMELİ (sessiz genişleme "
                      "panelde iz bırakmazsa uyarı anlamsız olur)")

    def test_invariant_gates_are_always_active(self):
        for entry in self.data["envs"]:
            for gate_id in ("trusted-host", "csp-nonce", "static-root"):
                row = next(r for r in entry["rows"] if r["id"] == gate_id)
                self.assertEqual(row["state"], "active",
                                 "%s değişmez kapı, her ortamda aktif: %s"
                                 % (gate_id, entry["env"]))

    def test_every_state_stays_inside_the_closed_set(self):
        states = set(self.data["states"])
        for entry in self.data["envs"]:
            for row in entry["rows"]:
                self.assertIn(row["state"], states,
                              "kapalı küme dışı durum: %s" % row["state"])
        self.assertEqual(states, set(self.data["states"]),
                         "durum kümesi sabit olmalı")

    def test_all_gates_are_reported_in_every_environment(self):
        """Eksik satır, eksik uyarıdır: liste her ortamda tam olmalı."""
        for entry in self.data["envs"]:
            ids = {r["id"] for r in entry["rows"]}
            self.assertEqual(ids, EXPECTED_IDS,
                             "kapı listesi eksik/fazla: %s (env=%s)"
                             % (sorted(ids), entry["env"]))

    def test_wire_parser_is_fail_closed(self):
        parsed = self.data["parsed"]
        self.assertEqual(parsed["unknownState"][0]["state"], "unknown",
                         "tanınmayan durum `unknown`a düşmeli, `active`e değil")
        self.assertEqual(parsed["missingId"], [],
                         "id'siz satır listeye girmemeli")
        self.assertEqual(parsed["notArray"], [],
                         "`security` bir dizi değilse yüzey BİLİNMİYOR olmalı")
        self.assertEqual(parsed["nullBody"], [],
                         "gövde yoksa yüzey BİLİNMİYOR olmalı")


if __name__ == "__main__":
    unittest.main()
