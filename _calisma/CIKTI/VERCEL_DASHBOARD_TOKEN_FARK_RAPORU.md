# Vercel ↔ kök dashboard design-token fark raporu

**Tarih:** 2026-09-25  
**Karşılaştırma kapsamı:**

- Vercel: `design-system/vercel/tokens.css` ve `design-system/vercel/tokens.json`
- Kök dashboard: `design-system/tokens.css` ve `design-system/tokens.json`
- Dashboard tüketimi: `_calisma/CIKTI/preview.html`

> Bu rapor tasarım token'larını karşılaştırır; GitHub/Vercel kimlik
> doğrulama veya API secret'larıyla ilgili değildir.

## Yönetici özeti

- Vercel kanonik katmanı **19 light-theme renk token'ı** içerir.
- Kök dashboard kanonik CSS'i **86 temel token** ve bunların **20 light-theme
  override'ı** içerir.
- İki CSS katmanı arasında **aynı adlı token yok**: doğrudan override veya
  çakışma riski `0/19`; birlikte import edilseler toplam `105` benzersiz CSS
  custom-property adı oluşur.
- Vercel seti renk dışında token içermez. Dashboard ise renk/tint/effect,
  font, font-size, line-height, letter-spacing, spacing, radius, motion,
  layout ve composition sözleşmesini kapsar.
- Vercel token'ları şu anda dashboard tarafından tüketilmiyor. Dashboard yalnız
  `/design-system/tokens.css` kök token katmanını import ediyor.
- Vercel'in canlı sitesinden alınan marka/console renkleri ile dashboard'un
  semantik durum renkleri aynı görevi taşımıyor. Doğrudan yeniden adlandırma
  veya toplu değer eşlemesi yapılmamalı.

## Kaynak ve kapsam farkları

| Özellik | Vercel token seti | Kök dashboard token seti |
|---|---|---|
| Kaynak | Canlı `https://vercel.com/` computed-style yakalama | Canlı CI dashboard `preview.html` çıkarımı |
| Yakalama tarihi | 2026-09-18 | 2026-09-02 |
| Tema | Yalnız light | Varsayılan dark + light override |
| Kanonik CSS | 19 color | 86 temel token + 20 light override |
| Kapsam | Kısmi; yalnız renk | Uygulama geneli UI sözleşmesi |
| Değer biçimi | Çoğunlukla verbatim `hsla(...)`, kısa/8 hane hex | Hex, `rgba(...)`, font stack, süre ve `var()` bileşimleri |
| Tüketici | Şu anda dashboard dışında referans katmanı | `preview.html`, Tailwind bridge ve dashboard-next |
| Kayıp durumu | Ham yakalama, CSS ve JSON drift kapılarıyla eşit | CSS, Tailwind bridge ve dashboard import kapılarıyla eşit |

Her iki kaynağın mevcut drift kontrolü yeşildir:

```text
OK — 19 Vercel tokens verbatim against raw.json (tokens.css + tokens.json in sync)
OK — import present, tokens.css :root 86 + light 20 vars, 12 tints in sheet, dashboard-next bridge OK
```

## Dashboard kategori envanteri

Kök dashboard'un 86 temel CSS token'ının kategori dağılımı:

| Kategori | Adet |
|---|---:|
| Renk, tint ve yüzey/effect | 32 |
| Font family | 3 |
| Font size | 7 |
| Line height | 2 |
| Letter spacing | 1 |
| Spacing | 10 |
| Radius | 8 |
| Motion | 9 |
| Layout | 5 |
| Composition shorthand | 9 |
| **Toplam** | **86** |

Light tema bu 86 adın 20'sini override eder; 20 yeni ve benzersiz ad
eklemez. Vercel'in 19 token'ının tamamı renk kategorisindedir.

## Vercel token'larının dashboard karşılıkları

Aşağıdaki eşleştirmeler **birebir CSS adı eşlemesi değildir**. En yakın olası
dashboard rolü gösterilmiştir; renk/oyut veya semantik farkı olan yerler
açıkça belirtilmiştir.

| Vercel token | Vercel değeri | Dashboard'daki en yakın rol | Fark |
|---|---|---|---|
| `--color-background-100` | `hsla(0, 0%, 100%, 1)` | Light `--surface` / `--paper`: `#fffdf8` | Dashboard saf beyaz değil; hafif sıcak kâğıt zemin kullanıyor. |
| `--color-gray-200` | `hsla(0, 0%, 92%, 1)` | Light `--surface-raised`: `#e9e1d3` | Yakın parlaklık; Vercel nötr gri, dashboard sıcak gri. |
| `--color-gray-300` | `hsla(0, 0%, 90%, 1)` | Light `--surface-raised`: `#e9e1d3` | Aynı nötr/sıcak ton farkı. |
| `--color-gray-500` | `hsla(0, 0%, 79%, 1)` | Light `--border`: `#cfc5b5` | Dashboard çizgisi daha koyu ve sıcak. |
| `--color-gray-600` | `hsla(0, 0%, 66%, 1)` | Light `--border` / `--muted` arası | Tek bir karşılığı yok. |
| `--color-gray-700` | `hsla(0, 0%, 56%, 1)` | Light `--muted`: `#70695f` | Dashboard daha koyu ve sıcak. |
| `--color-gray-800` | `hsla(0, 0%, 49%, 1)` | Light `--muted`: `#70695f` | Nötr gri ile sıcak metin grisi farklı. |
| `--color-gray-900` | `hsla(0, 0%, 30%, 1)` | Light `--fg`: `#292722` | Dashboard metni daha koyu ve sıcak. |
| `--color-gray-1000` | `hsla(0, 0%, 9%, 1)` | Light `--fg`: `#292722` | En yakın koyu nötr ton; yine de değer ve ton farklı. |
| `--color-gray-alpha-400` | `#00000014` | Dashboard'da yarı saydam nötr sınır token'ı yok | Status tint'leri semantik; genel alpha border'ın karşılığı değil. |
| `--ship-text` | `#ff5b4f` | `--err`: dark `#ff7b72`, light `#b42318` | Anlam yakın; Vercel canlı üretim kırmızısı, light theme metin kontrastı daha koyu. |
| `--develop-text` | `#0a72ef` | `--accent`: dark `#58a6ff`, light `#8b5e2b` | Dark temada mavi yakın; light temada dashboard accent kahverengi. |
| `--preview-text` | `#de1d8d` | `--budget`: dark `#bc8cff`, light `#7650a8` | Mor/pink ailesi yakın; semantik ve değer farklı. |
| `--geist-console-text-color-default` | `#000` | Light `--fg`: `#292722`; dark `--bg`: `#0e1116` | Console default'ı doğrudan dashboard foreground/background token'ı değil. |
| `--geist-console-text-color-blue` | `#0070f3` | Dark `--accent`: `#58a6ff` | Blue semantiği korunur; dashboard light accent'i mavi değil. |
| `--geist-console-text-color-purple` | `#7928ca` | Light `--budget`: `#7650a8` | Aile yakın; token görevi farklı. |
| `--geist-console-text-color-pink` | `#eb367f` | Light `--budget` / Vercel `--preview-text` ailesi | Dashboard'da doğrudan pink semantic karşılığı yok. |
| `--geist-selection-text-color` | `hsla(0, 0%, 95%, 1)` | Light `--surface` / `--surface-raised` | Nötr açık seçim yüzeyi; dashboard seçimleri mevcut tint/hover sözleşmesine bağlı. |
| `--ds-focus-color` | `hsla(212, 100%, 48%, 1)` | Dark `--accent`: `#58a6ff` | Light temada doğrudan focus token'ı yok; `--accent` eşlemesi hue'yu brown'a çevirir. |

## En önemli farklar ve riskler

1. **Birebir override yok.** Vercel token'larını import etmek dashboard mevcut
   token'larını değiştirmiyor; fakat aynı zamanda mevcut görsel sistemi
   değiştirmiyor. Etki ancak bu değişkenler tüketilirse başlar.
2. **Light-theme kıyası gerekir.** Vercel capture light; dashboard'un default
   dark değerleriyle karşılaştırmak theme-crossing karşılaştırma olur.
   Renk rolleri bu nedenle light override'lar üzerinden yorumlandı.
3. **Vendor token'ları semantik UI token'ları değildir.** `ship`, `preview`,
   `geist` ve `ds` adları ürün/console bağlamı taşır. Dashboard'un `ok`, `warn`,
   `err`, `accent`, `budget` token'ları farklı davranış sözleşmelerine sahiptir.
4. **Kapsam dengesiz.** Vercel 19 color-only token; dashboard 86 temel token.
   Vercel eklentisi typography, spacing, radius, motion veya layout kapsamaz.
5. **Global import riski.** Her iki katman da `:root` kullanıyor. İsim çakışması
   bugün yok; yine de Vercel referansı ileride `.vercel-reference` gibi bir
   scope'a taşınmamalı değilse global CSS yüzeyi gereksiz genişler.
6. **JSON/CSS kapsam farkı.** Kök `tokens.json` yapılandırılmış 77 temel
   değeri taşıyor; CSS'teki 9 composition shorthand (`card-*`, `badge-*`,
   `table-*`, `pre-*`, `button-*`) yalnız CSS'te bulunuyor. Mevcut drift gate
   özellikle JSON↔CSS renk eşitliğini doğruluyor. Bu, Vercel'in 19/19 tam
   kanonik eşitliğinden farklı bir sözleşmedir.

## Öneri

- **Token'ları birleştirme veya otomatik yeniden adlandırma.** İki set farklı
  ürün bağlamlarından geliyor ve isim çakışması yok.
- Vercel setini yalnız referans olarak kullanacaksanız, dashboard dışında
  `.vercel-reference { ... }` scope'unda veya ayrı bir preview yüzeyinde tutun.
- Gerçekten bir tema benzetmesi gerekiyorsa ayrı ve açık bir adapter katmanı
  oluşturun: her hedef eşleşmesi için semantik gerekçe, light/dark hedef,
  contrast sonucu ve görsel-regression kanıtı bulunmalı.
- Dashboard'da yeni focus/selection semanticleri gerekiyorsa bunları Vercel'in
  ham adlarıyla değil, dashboard sözleşmesine uygun `--focus-*` ve
  `--selection-*` adlarıyla tanımlayın.

## Kanıt dosyaları

- `design-system/vercel/tokens.css`
- `design-system/vercel/tokens.json`
- `design-system/vercel/raw.json`
- `design-system/vercel/scripts/check_vercel_tokens.py`
- `design-system/tokens.css`
- `design-system/tokens.json`
- `design-system/scripts/check_tokens.py`
- `_calisma/CIKTI/preview.html`
