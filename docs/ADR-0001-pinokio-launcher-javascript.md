# ADR-0001: Pinokio launcher betiklerini JavaScript olarak tut

- **Durum:** Accepted
- **Tarih:** 2026-09-25
- **Kapsam:** Pinokio launcher ve bu repodaki araç çalışma zamanı

## Bağlam

Pinokio, launcher modülünü Node/CommonJS üzerinden yükler ve `kernel`,
`shell.run`, `local.set` gibi Pinokio API'lerini bu katmandan bekler. Mevcut
`pinokio/pinokio.js`, `runtime.js`, `start.js` ve `install.js` dosyaları bu
sözleşmeye göre çalışır; dashboard sunucusu ise Python tarafındadır.

Gepeto tarafındaki açık konu, yeni launcher çalışmasının Go yerine mevcut
JavaScript kurallarına sadık kalması yönündeydi. Go'ya geçmek çalışma zamanı
uyumluluğunu ve ortak JS stilini bozacağı gibi yeni bir toolchain, modül,
derleme ve dağıtım yüzeyi getirecekti. Bu gereksiz karmaşıklık launcher'ın
dar görevine orantısızdır.

## Karar

Pinokio launcher betikleri JavaScript olarak kalacak ve gepeto'nun JS kuralları
bu dosyalarda da uygulanacak. Bu repoya Go kaynağı, `go.mod`/`go.sum`, Go
toolchain kurulumu veya Go ile üretilmiş launcher artifact'ı eklenmeyecek.

Launcher değişiklikleri `pinokio/*.js` içinde, mevcut CommonJS/export ve Pinokio
API sözleşmesini bozmadan yapılacak. Dashboard ve verification mantığı Python'da
kalacak; JS yalnızca Pinokio ile bu runtime' arasındaki ince adapter olacak.

Gelecekte Go ihtiyacı doğarsa bu karar kendiliğinden genişletilemez: Go'yu
launcher dışında gerçekten gerekli kılan ayrı bir ihtiyaç ve bu ADR'yi geçersiz
kılan yeni bir karar kaydı gerekir.

## Sonuçlar

**Olumlu:**

- Pinokio'nun Node/CommonJS yaşam döngüsü ve mevcut `kernel` API'siyle uyum
  korunur.
- Gepeto ile ortak JS stil ve review disiplini uygulanabilir.
- Root `go.mod`, ek binary, çapraz derleme ve ikinci runtime bağımlılığı oluşmaz.
- Launcher ile dashboard'un Python/JS sınırı açık ve küçük kalır.

**Negatif:**

- Launcher için statik tip güvenliği yoktur; dar fonksiyonlar, `node --check` ve
  davranış testleriyle telafi edilir.
- Gepeto'daki JS lint/format değişiklikleri bu repodaki launcher dosyalarına da
  uygulanmalıdır.

## Değerlendirilen alternatifler

- **Go launcher:** Reddedildi; Pinokio API'siyle ek bir runtime ve dağıtım
  yüzeyi getirir, fakat launcher için anlamlı bir fayda sağlamaz.
- **Python launcher:** Reddedildi; Pinokio'nun JS modül yükleyici sözleşmesini
  dolaylı ve kırılgan biçimde bozabilir.
- **Shell launcher:** Reddedildi; platform farkları, quoting ve menu durumlarının
  test edilmesi JS adapter'ından daha zordur.
