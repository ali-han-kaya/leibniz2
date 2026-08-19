#!/bin/bash
# apt-get'i GitHub Actions runner'larında sağlamlaştırılmış şekilde çalıştırır.
#
# GitHub ubuntu-latest runner'larında azure.archive.ubuntu.com mirror'ı
# runner'a göre erişilemez olabiliyor (2026-08-19: aynı run'da bir job geçti,
# diğeri 300 sn Ign retry'ından sonra timeout ile düştü — exit 124).
# Runner sources'ları "mirror+file:/etc/apt/apt-mirrors.txt" URI'si kullanır;
# mirror dosyasını SİLMEK kaynağı kırar ("Downloading mirror file failed").
# Doğru çözüm: sources'taki mirror URI'sini herkese açık archive.ubuntu.com'a
# çevirip güncelle/kur'u retry + timeout ile koşmak.
#
# Kullanım: apt_install.sh <paket...>
# (sudo gerektirir; workflow'da sudo olmadan çağrılır — script içinde sudo kullanır.)

set -euo pipefail

# 1) Sources'taki mirror URI'lerini archive.ubuntu.com'a sabitle.
#    Runner'lar: /etc/apt/sources.list.d/ubuntu.sources (deb822) veya
#    /etc/apt/sources.list (klasik). İkisini de hedefliyoruz.
for f in /etc/apt/sources.list.d/*.sources /etc/apt/sources.list; do
    [ -f "$f" ] || continue
    sudo sed -i \
        -e 's|mirror+file:/etc/apt/apt-mirrors\.txt|http://archive.ubuntu.com/ubuntu/|g' \
        -e 's|https\?://azure\.archive\.ubuntu\.com|http://archive.ubuntu.com|g' \
        -e 's|https\?://ports\.ubuntu\.com|http://archive.ubuntu.com|g' \
        "$f" 2>/dev/null || true
done

# 2) Güncelle — ilk deneme; başarısızsa cache temizle + ikinci deneme.
timeout 300 sudo apt-get update -o Acquire::Retries=5 || {
    sudo rm -rf /var/lib/apt/lists/*
    timeout 300 sudo apt-get update -o Acquire::Retries=5
}

# 3) Kur.
timeout 300 sudo apt-get install -y -o Acquire::Retries=5 "$@"

echo "apt_install.sh: OK — paketler kuruldu: $*"
