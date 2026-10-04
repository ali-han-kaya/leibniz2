# PREVIEW_STOP_ALLOWLIST — durum degistiren uclarda TCP-peer kapisi

`POST /api/stop` ve `POST /api/run-now` yalnizca _locustan_ cagrilabilir. Bu
belge, sandbox disi dagitimda bu kapinin nasil genisletilecegini ve neden
dikkatli genisletilmesi gerektigini anlatir.

Uygulama tek kaynak: `_calisma/CIKTI/preview_server.py`
(`DEFAULT_STOP_ALLOWLIST`, `load_stop_allowlist`, `_stop_peer_allowed`) ve
handler'daki ortak kapı `Handler._peer_gate`. Testler:
`_calisma/CIKTI/test_stop_peer_allowlist.py` ve matristeki
`TestStateChangingPeerParity`.

## 1. Kapı neyi koruyor

|                 |                                         |
| --------------- | --------------------------------------- |
| Korunan uçlar   | `POST /api/stop`, `POST /api/run-now`   |
| Varsayilan izin | yalniz `127.0.0.1` ve `::1`             |
| Karar kaynagi   | soket peer adresi (`client_address[0]`) |
| Red cevabı      | `403 {"error": "forbidden peer"}`       |

Iki tasarim karari buradan gelir:

**Peer, bind'den bagimsizdir.** Karar, sunucunun hangi adrese baglandigina
degil, _baglantiyi kimin yaptigina_ bakar. Bu yuzden `--bind 0.0.0.0`,
konteyner veya tunel kurgusunda bile uzak bir peer `/api/stop` cagiramaz.
Baglama adresini gevsetmek kapiyi acmaz.

**Sagtebilemez katman once gelir.** Peer kontrolu, istemcinin kontrolunde
olan Host/Origin (DNS-rebinding) kontrolunden _once_ degerlendirilir. Bir
istemci `Host`/`Origin` basligini kendisi yazabilir; peer adresini yazamaz.
Guven sirasi bu yuzden budur.

**Ortak kapı, kopyalanmış blok değil.** Iki uç da `Handler._peer_gate()`
yardımcısını çağırır; kararın kendisi tek yerde yaşar. Yeni bir
state-changing uç eklenirse aynı yardımcıyı çağırmak zorundadır — sapma
inceleme değil, derleme-zamanı bir olgu olur.

## 2. Sandbox disi dagitim icin env ornegi

Varsayilan izin yalniz loopback'tir. Bir konteyner/tunel icinden baska bir
makineden `POST /api/stop` gondermek istiyorsan, **o peer'in IP'sini acikca
vermelisin**.

### Kabuk

```bash
PREVIEW_STOP_ALLOWLIST="10.1.2.3,192.168.5.9" \
  python3 _calisma/CIKTI/preview_server.py --port 8000 --bind 0.0.0.0
```

### launchd (macOS GUI agent)

Bu deponun gercek dagitim yolu launchd'dir. Deger plist'in
`EnvironmentVariables` sozlugune yazilir:

```xml
<key>EnvironmentVariables</key>
<dict>
  <key>PREVIEW_STOP_ALLOWLIST</key>
  <string>10.1.2.3,192.168.5.9</string>
</dict>
```

### Docker Compose

```yaml
services:
  preview:
    image: python:3.11-slim-bookworm
    ports: ["8000:8000"]
    environment:
      # Virgulle ayrilmis IP listesi. Bos birakilirsa loopback kalir.
      PREVIEW_STOP_ALLOWLIST: "10.1.2.3,192.168.5.9"
    command:
      [
        "python3",
        "_calisma/CIKTI/preview_server.py",
        "--port",
        "8000",
        "--bind",
        "0.0.0.0",
      ]
```

### Yeniden baslatma zorunlu

Env **bir kez**, `main()` icinde sunucu baslarken okunur:

```python
STOP_ALLOWLIST = load_stop_allowlist(os.environ.get(_STOP_HOSTS_ENV))
```

Bu yuzden `PREVIEW_STOP_ALLOWLIST` degistirildikten sonra servisin **yeniden
baslatilmasi gerekir**. Calisan bir surec env degisikligini gormez.

## 3. Davranis sozlesmesi (calistirilarak dogrulanmis)

Asagidakiler `load_stop_allowlist` / `_stop_peer_allowed` cagrilarak
olculmustur; varsayim degil.

| Giris                   | Sonuc                                             |
| ----------------------- | ------------------------------------------------- |
| tanimsiz / bos          | `127.0.0.1`, `::1`                                |
| `10.1.2.3, 192.168.5.9` | varsayilan **+** ikisi                            |
| `10.0.0.0/8`            | varsayilan **+** hicbiri — CIDR desteklenmez      |
| `not-an-ip`             | varsayilan — bozuk girdi dusurulur                |
| `"  10.1.2.3 , , "`     | `10.1.2.3` eklenir (bosluk ve bos jeton zararsiz) |

| Peer                      | Sonuc                             |
| ------------------------- | --------------------------------- |
| `127.0.0.1`               | izinli                            |
| `::1`                     | izinli                            |
| `::ffff:127.0.0.1`        | izinli (IPv4-mapped IPv6 -> IPv4) |
| listeye yazilan IP        | izinli                            |
| listeye **yazilmamis** IP | `forbidden peer`                  |
| ayristirilamayan peer     | `forbidden peer`                  |

## 4. Guvenlik notu

**1. Genisletme yalnizca env ile yapilir.** Kod degisikligi veya yeniden
derleme gerekmez — bu, deploy eden operatorun bilincli bir kararidir ve
denetim izi env'de kalir.

**2. Kume birlesimdir; daraltamazsin.** Gecerli girdiler varsayilan kume
**eklenir**, degilmez:

```
L("10.1.2.3") icinde 127.0.0.1 var mi: True
```

Bu bilincli bir karardir: yanlislikla yazilmis bir env yerel operatoru
kilitleyemez. Bedeli, **sadece bu env ile guvenli bir sekilde daraltamazsin** —
`/api/stop`'u tum agdan kapatmak istiyorsan `PREVIEW_STOP_ALLOWLIST` degil,
`--bind 127.0.0.1` kullan.

**3. Bozuk girdi kapiyi genisletmez, daraltir da.** `ip_address()`'a
gecmeyen her jeton dusurulur. Yani `"10.0.0.0/8"` yazmak **sessizce** bir
seyi acmaz; sadece istedigin genislemeyi yapmamis olursun.

> **En sik tuzak — CIDR yok.** Su anki en kotu durum, operatorun
> `10.0.0.0/8` yazip "aciklamisim" sanmasi ve kapinin gercekte **kapali**
> kaldigini fark etmemesidir. Genisleme **tek tek IP** ile yazilir.

**4. IPv4-mapped IPv6 kanoniklenir.** `::ffff:127.0.0.1` bir _farkli_ peer
degildir; `127.0.0.1` olarak degerlendirilir ve her zaman izinlidir. Yani
ikinci bir loopback yolu bu kapidan gecmez.

**5. Ayristirilamayan peer reddedilir (fail-closed).** Beklenmeyen bir
peer bicimi sessizce gecmez; `forbidden peer` doner.

**6. Bu bir yetkilendirme katmani degildir.** Kapı, _ag yuzeyini_ daraltir;
kimligi dogrulamaz. `POST /api/run-now` icin ayrica bearer kapisi vardir ve
o yalniz `PREVIEW_RUN_NOW_TOKEN` tanimliysa devreye girer
(bkz. `docs/RUN_DASHBOARD.md`). Yalniz bu kapiya guvenerek cok genis bir
ag segmentini acma.

**7. Tercih edilen durum: kapali tutmak.** Uctan uca koruma istiyorsan env'i
hic ayarlama ve `--bind 127.0.0.1` ile baslat. `PREVIEW_STOP_ALLOWLIST`
yalniz "sandbox disina cikmam _gerekiyor_" durumu icindir ve en az
kullanilabilir yuzeyi (tek IP) kullan.

## 5. Ilgili belgeler

- `docs/PREVIEW_API_REFERENCE.md` — uclar, durum kodlari ve kapilama tablosu
- `docs/RUN_DASHBOARD.md` — `PREVIEW_RUN_NOW_TOKEN` ve yerel calistirma
