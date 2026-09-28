// Negatif tip-testleri — "derlenmemesi GEREKEN" kullanımlar.
//
// Bu dosya bilerek hata içerir. Her hata bir `@ts-expect-error` ile susturulur;
// tsc susturulan satırda HATA BULAMAZSA TS2578 ("Unused '@ts-expect-error'
// directive") verir. Yani:
//
//   * tsc temiz geçiyorsa → her yasak hâlâ yasak (iddia diri),
//   * bir yasak gevşemişse  → direktif kullanılmaz hâle gelir ve tsc kırmızıya
//                            döner (iddia kendini duyurur).
//
// Tek başına "bir hata var" yeterli değildir: `countTone`un ikinci parametresi
// `string`e gevşetilseydi `countTone(1, "none")` yine hata verirdi — ama artık
// BAŞKA bir hata. Bu yüzden her direktif beklenen tanı KODUNU taşır ve koşucu
// (`test-d/run_type_tests.py`) direktifleri geçici bir kopyada devre dışı
// bırakıp tsc'nin bastığı kodlarla birebir karşılaştırır. Kod etiketsiz
// direktif koşucu tarafından reddedilir.
//
// `@ts-ignore` KULLANILMAZ: o, hatayı koşulsuz yutar ve iddiayı sessizce
// ölümsüzleştirir.

import {
  countTone,
  panelCard,
  statBadge,
  toneForVerdict,
  verdictTone,
  type VerdictTone,
} from "@/components/panel-style";
import { getTrend, type Latest, type TrendSource } from "@/lib/preview";
import type { Assert, Equal } from "./assertions";

// ── araç setinin kendisi fail-closed mu ─────────────────────────────────────
// En önemli vaka: `Assert` yalnız `true` kabul etmeli. Kabul etmezse bu
// dosyadaki tüm pozitif iddialar sessiz birer no-op olurdu.

// @ts-expect-error TS2344 — Assert yalnız `true` kabul eder
type _AssertRejectsFalse = Assert<false>;

// @ts-expect-error TS2344 — AssertEqual deseni eşitsizlikte hataya düşer
type _AssertEqualRejectsInequality = Assert<Equal<1, 2>>;

// ── karar → ton eşlemesi ────────────────────────────────────────────────────

// `null` "yok" değildir: tel-alanı yokluğu `undefined` ile temsil edilir.
// @ts-expect-error TS2345 — null kabul edilmemeli (undefined kabul edilir)
toneForVerdict(null);

// Alan zorunlu: kararı unutup argümansız çağırmak derlenmemeli.
// @ts-expect-error TS2554 — parametre zorunlu, argümansız çağrı geçmez
toneForVerdict();

// ── sayı → ciddiyet eşlemesi ────────────────────────────────────────────────

// "none" ciddiyet değil, yokluk tonudur: sıfır sayı sessiz kalır ve çağrı yeri
// bu kararı zorla görünür yapamaz.
// @ts-expect-error TS2345 — "none" ciddiyet parametresine giremez
countTone(1, "none");

// Ciddiyet zorunlu: çağrı yeri kararını saklayamaz (explicit-variant kültürü).
// @ts-expect-error TS2554 — ciddiyet parametresi zorunlu
countTone(1);

// ── ton sözlüğü kapalı ──────────────────────────────────────────────────────

// Ton değerleri küçük harf sözleşmesidir; "PASS" bir KARAR metnidir, ton değil.
// Karar önce `toneForVerdict`ten geçmek zorunda.
// Kod TS2820 (TS2322'nin "did you mean 'pass'?" önerili biçimi): tsc yalnız
// reddetmiyor, doğru literali de öneriyor — yani ton kümesi harf durumuna
// kadar kapalı.
// @ts-expect-error TS2820 — "PASS" bir VerdictTone değil, doğrusu "pass"
const _badToneCase: VerdictTone = "PASS";

// Ham karar metni doğrudan tona geçemez: eşleme tek kapıdan yapılır.
const _rawVerdict: string = "PASS";
// @ts-expect-error TS2322 — string, ton union'ına atanamaz (önce eşleme)
verdictTone({ tone: _rawVerdict });

// Rozet varyant tablosu kapalı: bilinmeyen ton sessizce geçemez.
// @ts-expect-error TS2322 — "unknown" varyant tablosunda yok
statBadge({ tone: "unknown" });

// Yüzey tonu ile KARAR tonu ayrı sözlüklerdir. `panelCard`in ton kümesi
// {default, error} — verdict tonları değil. İkisi karışırsa hata yüzeyi
// "pass" diye boyanır ve tek bir varyant tablosu iki farklı anlam taşır.
// (Kod TS2353 DEĞİL TS2322: `tone` artık bilinen bir anahtar, ama değeri
// kapalı kümeye girmiyor — eskiden anahtarın kendisi yoktu.)
// @ts-expect-error TS2322 — "pass" bir PanelTone değil (kapalı küme)
panelCard({ tone: "pass" });

// ── veri katmanı ────────────────────────────────────────────────────────────

// Pencere sayısaldır; sorgu dizesi `take`e sızmamalı.
// @ts-expect-error TS2345 — limit sayı olmalı, dize değil
getTrend("20");

// Tel-sözleşmesinin sayısal alanları sayı kabul eder: "3" sessizce geçerse
// karşılaştırmalar (`p0 > 0`) yanlış sonuç verirdi.
// @ts-expect-error TS2322 — p0 sayı olmalı
const _badLatestNumber: Latest = { p0: "3" };

// Alan adı yanlış yazılırsa tip yakalar. Runtime'da bu hata görünmez: eksik
// alan "—" basar, yani pano bozulmadan yanlış okunur.
// Kod TS2551 (TS2339'un "did you mean 'verdict'?" önerili biçimi): typo
// yakalanmakla kalmıyor, doğru alan adı da öneriliyor.
// @ts-expect-error TS2551 — `verdicts` alanı yok, doğrusu `verdict`
const _badFieldName = ({} as Latest).verdicts;

// Kaynak kümesi kapalı: yeni bir kaynak `trendSource()` guard'ı elden
// geçirilmeden eklenemez.
// @ts-expect-error TS2322 — "fixture" bir TrendSource değil
const _badSourceName: TrendSource = "fixture";
