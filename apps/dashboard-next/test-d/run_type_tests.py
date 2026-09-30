#!/usr/bin/env python3
"""run_type_tests.py — dashboard-next tip-testleri (pozitif + negatif).

`tsc` iki ayrı soruyu tek koşuda cevaplamaz, bu yüzden iki geçiş var:

  GEÇİŞ 1 — sözleşmeler (`tsconfig.typetests.json`)
    `Assert<Equal<..>>` iddiaları (AssertEqual deseni) tutmalı ve her
    `@ts-expect-error` HÂLÂ gerekli olmalı. Kullanılmayan bir direktif tsc'de
    TS2578 üretir, yani "artık hata yok" durumu sessizce geçemez: iddia
    ölünce kapı kırmızıya döner.

  GEÇİŞ 2 — tanı KİMLİĞİ (`tsconfig.typetests.negative.json`)
    Geçiş 1 yalnız "bir hata VAR" der, "BEKLEDİĞİM hata var" demez.
    `countTone`un ikinci parametresi `string`e gevşetilseydi
    `countTone(1, "none")` yine hata verirdi — ama artık BAŞKA bir hata ve
    iddia sessizce anlamını yitirirdi. Bunu yakalamak için `test-d/` ağacı
    `test-d/stripped/` altına kopyalanır, kopyadaki direktifler devre dışı
    bırakılır (`@ts-expect-error` → `ts-expect-error`: yalnız `@` düşürülür,
    satır sayısı ve yorum yapısı korunur), tsc'nin bastığı tanı kodları
    toplanır ve her satırdaki `TSxxxx` etiketiyle birebir karşılaştırılır.

    Üç ihlal birden hata sayılır: etiketi olmayan direktif, eşleşmeyen kod,
    ve İDDİA EDİLMEYEN tanı (yani test dışı bir derleme hatası).

Bağımlılık yok — yalnız stdlib ve repoda kurulu yerel `tsc`. Çalışma zamanı
bağımlılığı (tsd/dtslint/jest) eklemek, tek bir kapı için yeni bir paket
yüzeyi açardı; repo'nun "stdlib-only koşucu" kültürü buna karşı
(bkz. apps/trend-db/test/mini.mjs).

Kullanım:
    python3 test-d/run_type_tests.py              # kapı (fail-closed)
    python3 test-d/run_type_tests.py --selftest   # tsc'siz saf fonksiyon testleri
    python3 test-d/run_type_tests.py --suggest    # etiket/eslesme tablosu
"""
from __future__ import annotations

import argparse
import pathlib
import re
import shutil
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
APP = HERE.parent
TSC = APP / "node_modules" / ".bin" / "tsc"
CONFIG_POSITIVE = "tsconfig.typetests.json"
CONFIG_NEGATIVE = "tsconfig.typetests.negative.json"
STRIPPED = HERE / "stripped"

# Devre dışı bırakma `@`düşürülerek yapılır — `-disabled` EKLEMEK YETMEZ:
# tsc `@ts-expect-error`ı alt-dize olarak arar, yani `@ts-expect-error-disabled`
# da susturur (ölçüldü: direktifler kapalı sansür edilince geçiş 2 hiç tanı
# basmadı). `@` gidince direktif tümden tanınmaz olur; satır sayısı korunur.
DISABLED_TOKEN = "ts-expect-error"
# Direktifler YORUMUN BAŞINDA olmalı (`// @ts-expect-error ...`). tsc'nin
# kendisi metin içinde geçen `@ts-expect-error`ı da direktif sayar, ama bu
# dosyalar direktifi ANLATAN prose de içeriyor; gevşek bir desen o prose'u
# iddia sanıp sahte-pozitif üretirdi (ölçüldü). Sıkı desenin riski sessiz
# değil gürültülü: eşleşmeyen gerçek bir direktif, geçiş 2'de "İDDİA
# EDİLMEYEN tanı" olarak fail-closed patlar.
# Kanonik biçim kod ETİKETLİdir; etiketsiz direktif reddedilir, çünkü kimliği
# doğrulanamayan iddia iddia sayılmaz.
# `re.MULTILINE` ZORUNLU: satır-başı çapası olmadan `^` yalnız metnin ilk
# karakterinde eşleşir ve `strip_directives` sessizce hiçbir şey yapmaz
# (ölçüldü: kopyada direktifler aktif kaldı, geçiş 2 sıfır tanı bastı).
DIRECTIVE = re.compile(r"^[ \t]*//[ \t]*@ts-expect-error[ \t]+(TS\d+)\b",
                       re.MULTILINE)
ANY_DIRECTIVE = re.compile(r"^[ \t]*//[ \t]*@ts-expect-error\b", re.MULTILINE)
# Ayrı bir desen, çünkü YALNIZ jeton değişmeli: yorum ön-ekini (`//`) de
# eşleştirip yutarsa devre dışı satır yorum olmaktan çıkar ve dosya sözdizimi
# bozulur (ölçüldü: TS1005/TS1127/TS1434 yağmuru). Yakalama grubu ön-eki korur.
STRIP_DIRECTIVE = re.compile(r"^([ \t]*//[ \t]*)@ts-expect-error\b", re.MULTILINE)
# `--pretty false` çıktısı: <dosya>(<satır>,<kolon>): error TSxxxx: <mesaj>
DIAGNOSTIC = re.compile(
    r"^(?P<file>.+?)\((?P<line>\d+),(?P<column>\d+)\): error (?P<code>TS\d+): "
    r"(?P<message>.*)$"
)


# ── saf fonksiyonlar (selftest bunları doğrular) ────────────────────────────

def strip_directives(text: str) -> str:
    """Direktifleri DEVRE DIŞI bırakır; satır sayısını ve yorum yapısını korur.

    İki değişmez: (1) satır SAYISI aynı kalmalı — geçiş 2'nin tanıları özgün
    dosyanın satır numaralarıyla eşleştirilir; (2) satır yorum KALMALI —
    yalnız `@` düşürülür, `//` korunur.
    """
    return STRIP_DIRECTIVE.sub(lambda m: m.group(1) + DISABLED_TOKEN, text)


def parse_annotations(text: str) -> tuple[dict[int, str], list[int]]:
    """(KORUNAN satır → beklenen kod, etiketsiz direktif satırları).

    Anahtar korunan satırdır, direktifin kendi satırı değil: direktif bir
    SONRAKİ satırı susturur ve tsc tanıyı da o satıra yazar. Çeviri burada, tek
    yerde yapılır; çağrı yerleri +1 aritmetiği tekrarlamaz. Anahtarı direktif
    satırı sanmak, tüm iddiaları tek satır kaydırır ve her birini "kapsanmamış
    tanı" olarak gösterir (ilk koşuda tam olarak bu oldu).
    """
    codes: dict[int, str] = {}
    bare: list[int] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not ANY_DIRECTIVE.search(line):
            continue
        found = DIRECTIVE.search(line)
        if found:
            codes[number + 1] = found.group(1)
        else:
            bare.append(number)
    return codes, bare


def original_of(rel_path: str) -> str:
    """`test-d/stripped/x.ts` → `test-d/x.ts` (kopya özgün dosyayı temsil eder)."""
    prefix = f"test-d/{STRIPPED.name}/"
    if rel_path.startswith(prefix):
        return "test-d/" + rel_path[len(prefix):]
    return rel_path


def parse_diagnostics(output: str) -> list[dict[str, object]]:
    found: list[dict[str, object]] = []
    for line in output.splitlines():
        match = DIAGNOSTIC.match(line)
        if not match:
            continue
        path = pathlib.Path(match.group("file"))
        rel = path if not path.is_absolute() else pathlib.Path(
            path.relative_to(APP) if APP in path.parents else path)
        found.append({
            "file": original_of(str(rel).replace("\\", "/")),
            "line": int(match.group("line")),
            "code": match.group("code"),
            "message": match.group("message"),
        })
    return found


def compare(expected: dict[tuple[str, int], str],
            diagnostics: list[dict[str, object]]) -> tuple[list[str], list[tuple]]:
    """Beklenen etiketlerle tsc tanılarını birebir karşılaştırır (saf)."""
    problems: list[str] = []
    seen: dict[tuple[str, int], list[str]] = {}
    for diag in diagnostics:
        key = (str(diag["file"]), int(diag["line"]))
        seen.setdefault(key, []).append(str(diag["code"]))

    table: list[tuple] = []
    for key in sorted(expected):
        actual = seen.get(key, [])
        wanted = expected[key]
        table.append((key[0], key[1], wanted, ",".join(actual) if actual else "—"))
        if not actual:
            problems.append(
                f"{key[0]}:{key[1]} — etiket doğrulanamadı: tsc bu satırda tanı "
                f"basmadı (beklenen {wanted}). Yasak gevşemiş olabilir.")
        elif wanted not in actual:
            problems.append(
                f"{key[0]}:{key[1]} — kod uyuşmuyor: beklenen {wanted}, gelen "
                f"{','.join(actual)}. Yasak hâlâ var ama artık BAŞKA bir "
                f"nedenden; iddia anlamını yitirmiş.")
        elif len(actual) > 1:
            problems.append(
                f"{key[0]}:{key[1]} — aynı satırda {len(actual)} tanı var; her "
                f"iddia tek bir hatayı hedeflemeli.")

    for key in sorted(seen):
        if key not in expected:
            problems.append(
                f"{key[0]}:{key[1]} — İDDİA EDİLMEYEN tanı "
                f"({','.join(seen[key])}). Test dışı bir derleme hatası var; "
                f"ya düzelt ya da bir `@ts-expect-error TSxxxx` ile sahiplen.")
    return problems, table


# ── koşum yardımcıları ──────────────────────────────────────────────────────

def run_tsc(config: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(TSC), "-p", config, "--pretty", "false"],
        cwd=str(APP), capture_output=True, text=True, timeout=300,
    )


def build_stripped() -> int:
    """`test-d/` ağacını `test-d/stripped/`e kopyalar (direktifler kapalı)."""
    shutil.rmtree(STRIPPED, ignore_errors=True)
    copied = 0
    for src in sorted(HERE.rglob("*")):
        if src.is_dir() or STRIPPED in src.parents or src == STRIPPED:
            continue
        dest = STRIPPED / src.relative_to(HERE)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if src.suffix == ".ts":
            dest.write_text(strip_directives(src.read_text(encoding="utf-8")),
                            encoding="utf-8")
        else:
            shutil.copy2(src, dest)
        copied += 1
    return copied


def selftest() -> int:
    """Saf fonksiyonların kendi testleri (tsc çağırmadan)."""
    failures: list[str] = []
    total = [0]

    def check(name: str, ok: bool, detail: str = "") -> None:
        total[0] += 1
        if not ok:
            failures.append(f"{name}: {detail}")

    sample = ("// açıklama\n"
              "// @ts-expect-error TS2345 — gerekçe\n"
              "toneForVerdict(null);\n")
    stripped = strip_directives(sample)
    check("strip/satır-sayısı", len(stripped.splitlines()) == len(sample.splitlines()),
          f"{len(stripped.splitlines())} != {len(sample.splitlines())}")
    # Zayıf kontrol TUZAĞI: `DISABLED_TOKEN in stripped` HER ZAMAN doğrudur,
    # çünkü "ts-expect-error" zaten "@ts-expect-error"ın alt-dizesidir; bu
    # kontrol `@` kaldırılmadığında da yeşil kalırdı. Aranan şey `@`in YOKLUĞU.
    check("strip/@-kaldırıldı", "@ts-expect-error" not in stripped, stripped)
    # Yorum yapısı korunmalı: ön-ek yutulursa satır kod olur, dosya sözdizimi
    # bozulur ve geçiş 2 sahte sözdizimi tanılarıyla dolar.
    check("strip/yorum-kalır",
          stripped.splitlines()[1].lstrip().startswith("//"),
          stripped.splitlines()[1])
    check("strip/aktif-direktif-kalmadı", not ANY_DIRECTIVE.search(stripped), stripped)
    check("strip/idempotent", strip_directives(stripped) == stripped, "ikinci kez değişti")
    # Regresyon: tsc alt-dize arar, o yüzden devre dışı biçim `@` TAŞIMAMALI.
    # `-disabled` eki taşıyan bir biçim sessizce susturmaya devam ederdi.
    check("strip/@-taşımaz", "@" not in DISABLED_TOKEN, DISABLED_TOKEN)
    # Kopyayı okuyan insan etiketi görebilmeli (devre dışı biçim kodu korur).
    check("strip/etikette-kod-kalır", "TS2345" in stripped, stripped)

    codes, bare = parse_annotations(
        "// @ts-expect-error TS2554 — a\ncountTone(1);\n// @ts-expect-error etiketsiz\nx;\n")
    check("parse/korunan-satır", codes == {2: "TS2554"}, str(codes))
    check("parse/etiketsiz", bare == [3], str(bare))
    # Prose'da anılan direktif iddia SAYILMAMALI (sahte-pozitif regresyonu).
    codes, bare = parse_annotations(
        "// Her hata bir `@ts-expect-error` ile susturulur;\n"
        "//   // @ts-expect-error TS1 iç içe\n"
        "  //   @ts-expect-error TS2345 — girintili\n"
        "x;\n")
    check("parse/prose-sayılmaz", codes == {4: "TS2345"}, str(codes))
    check("parse/prose-etiketsiz", bare == [], str(bare))

    diags = parse_diagnostics(
        "test-d/stripped/negatives.test-d.ts(7,3): error TS2345: bad arg\n"
        "test-d/contracts.test-d.ts(1,1): error TS2322: nope\n"
        "önemsiz satır\n")
    check("parse/tanı-sayısı", len(diags) == 2, str(len(diags)))
    check("map/kopya-özgüne", diags[0]["file"] == "test-d/negatives.test-d.ts",
          str(diags[0]["file"]))
    check("map/dokunulmayan", diags[1]["file"] == "test-d/contracts.test-d.ts",
          str(diags[1]["file"]))

    exp = {("test-d/x.ts", 5): "TS2345"}
    problems, _ = compare(exp, [{"file": "test-d/x.ts", "line": 5, "code": "TS2345",
                                 "message": "m"}])
    check("compare/eşleşme-temiz", problems == [], str(problems))
    problems, _ = compare(exp, [{"file": "test-d/x.ts", "line": 5, "code": "TS2322",
                                 "message": "m"}])
    check("compare/yanlış-kod", any("kod uyuşmuyor" in p for p in problems), str(problems))
    problems, _ = compare(exp, [])
    check("compare/tanı-yok", any("doğrulanamadı" in p for p in problems), str(problems))
    problems, _ = compare(exp, [{"file": "test-d/x.ts", "line": 5, "code": "TS2345",
                                 "message": "m"},
                                {"file": "test-d/y.ts", "line": 9, "code": "TS1005",
                                 "message": "m"}])
    check("compare/fazladan-tanı",
          any("İDDİA EDİLMEYEN" in p for p in problems), str(problems))

    if failures:
        print("tip-test koşucusu SELFTEST: FAIL")
        for failure in failures:
            print(f"  {failure}")
        return 1
    print(f"tip-test koşucusu selftest: OK ({total[0]} vaka)")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="dashboard-next tip-testleri")
    parser.add_argument("--selftest", action="store_true",
                        help="yalnız saf fonksiyon testlerini koş (tsc'siz)")
    parser.add_argument("--suggest", action="store_true",
                        help="her direktifin yazılı ve GERÇEK kodunu tablo olarak bas")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()

    if not TSC.is_file() or not (APP / CONFIG_POSITIVE).is_file() \
            or not (APP / CONFIG_NEGATIVE).is_file():
        print("tip-testleri: tsc/tsconfig yok — SKIP")
        return 0

    # ── geçiş 1: iddialar tutmalı, direktifler kullanılmış olmalı ──
    first = run_tsc(CONFIG_POSITIVE)
    if first.returncode != 0:
        print("tip-testleri GEÇİŞ 1: FAIL — pozitif iddia düştü ya da "
              "kullanılmayan `@ts-expect-error` var (TS2578):")
        print(first.stdout or first.stderr)
        return 1
    print("tip-testleri GEÇİŞ 1: OK — iddialar tutuyor, tüm direktifler gerekli")

    # ── geçiş 2: tanı kimliği ──
    expected: dict[tuple[str, int], str] = {}
    bare_lines: list[str] = []
    for source in sorted(HERE.rglob("*.ts")):
        if STRIPPED in source.parents:
            continue
        codes, bare = parse_annotations(source.read_text(encoding="utf-8"))
        rel = str(source.relative_to(APP)).replace("\\", "/")
        for guarded_line, code in codes.items():
            expected[(rel, guarded_line)] = code
        bare_lines.extend(f"{rel}:{line}" for line in bare)

    if bare_lines:
        print("tip-testleri: FAIL — kod etiketi olmayan direktif(ler): "
              + ", ".join(bare_lines))
        print("  Her negatif iddia beklenen tanıyı yazmalı: "
              "`// @ts-expect-error TSxxxx — gerekçe`")
        return 1
    if not expected:
        print("tip-testleri: FAIL — hiç negatif iddia yok; altyapı ölü.")
        return 1

    build_stripped()
    second = run_tsc(CONFIG_NEGATIVE)
    diagnostics = parse_diagnostics(second.stdout + second.stderr)
    problems, table = compare(expected, diagnostics)

    if args.suggest:
        print("etiket / gerçek kod tablosu:")
        for file, line, wanted, actual in table:
            print(f"  {file}:{line}  yazılı={wanted}  gerçek={actual}")
        shutil.rmtree(STRIPPED, ignore_errors=True)
        return 0

    if second.returncode == 0 and not problems:
        print("tip-testleri: FAIL — direktifler kapalıyken tsc hiç tanı "
              "basması; negatif iddialar ölü.")
        return 1
    if problems:
        print(f"tip-testleri GEÇİŞ 2: FAIL — {len(problems)} sorun "
              f"({len(expected)} direktif, {len(diagnostics)} tanı)")
        for problem in problems:
            print(f"  {problem}")
        print(f"  (kopya incelenebilir: {STRIPPED})")
        return 1

    # Kopya yalnız BAŞARIDA silinir: arıza hâlinde tsc'nin gerçekte ne dediği
    # incelenebilir kalmalı (dizin .gitignore'da, commit'e sızmaz).
    shutil.rmtree(STRIPPED, ignore_errors=True)
    print(f"tip-testleri GEÇİŞ 2: OK — {len(expected)} direktif, "
          f"{len(diagnostics)} tanı, 0 sorun (kod kimliği doğrulandı)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
