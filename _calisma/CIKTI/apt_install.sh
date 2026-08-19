#!/bin/bash
# apt-get'i GitHub Actions runner'larında sağlamlaştırılmış şekilde çalıştırır.
#
# GitHub ubuntu-latest runner'larında azure.archive.ubuntu.com mirror'ı
# runner'a göre erişilemez olabiliyor (2026-08-19: aynı run'da bir job geçti,
# diğeri 300 sn Ign retry'ından sonra timeout ile düştü — exit 124).
# Kök neden mirror seçimi olduğundan, çözüm sources'u herkese açık
# archive.ubuntu.com'a çevirip cache'i temizlemek; ardından retry + timeout
# ile güncelle/kur.
#
# Kullanım: apt_install.sh <paket...>
# (sudo gerektirir; workflow'da sudo ile çağrılır.)

set -euo pipefail

# 1) Mirror'ı archive.ubuntu.com'a sabitle (azure/ports varyantları dahil).
#    Runners: /etc/apt/sources.list.d/ubuntu.sources (deb822) veya
#    /etc/apt/sources.list (klasik). İkisini de hedefliyoruz.
for f in /etc/apt/sources.list.d/*.sources /etc/apt/sources.list; do
    [ -f "$f" ] || continue
    sudo sed -i \
        -e 's|https\?://azure\.archive\.ubuntu\.com|http://archive.ubuntu.com|g' \
        -e 's|https\?://ports\.ubuntu\.com|http://archive.ubuntu.com|g' \
        "$f" 2>/dev/null || true
done
# apt-mirrors.txt varsa kaldır (mirror listesi seçimini ezmemek için).
sudo rm -f /etc/apt/apt-mirrors.txt 2>/dev/null || true

# 2) Güncelle — ilk deneme; başarısızsa cache temizle + ikinci deneme.
timeout 300 sudo apt-get update -o Acquire::Retries=5 || {
    sudo rm -rf /var/lib/apt/lists/*
    timeout 300 sudo apt-get update -o Acquire::Retries=5
}

# 3) Kur.
timeout 300 sudo apt-get install -y -o Acquire::Retries=5 "$@"

echo "apt_install.sh: OK — paketler kuruldu: $*"
