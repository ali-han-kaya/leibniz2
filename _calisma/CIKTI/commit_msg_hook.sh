#!/bin/sh
# commit-msg denetimi — .gitmessage kurallarını uygular (noise commit önleme).
# pre-commit framework'ü commit-msg stage'inde çağırır; $1 = mesaj dosyası.
# Kural ihlali = sıfır-dışı exit → git commit'i BLOKE EDER (fail-closed).

MSG_FILE="${1:?commit-msg: mesaj dosyası gerekli}"
[ -f "$MSG_FILE" ] || { echo "commit-msg: mesaj dosyası bulunamadı: $MSG_FILE"; exit 1; }

# Yorum (#) ve boş satırları at; ilk kalan satır = başlık.
SUBJECT=$(sed '/^#/d' "$MSG_FILE" | grep -v '^[[:space:]]*$' | head -1)
[ -n "$SUBJECT" ] || { echo "commit-msg: HATA — commit mesajı boş"; exit 1; }

fail() {
    echo "commit-msg: HATA — $1"
    echo "commit-msg:   başlık: $SUBJECT"
    echo "commit-msg:   kural: bkz. .gitmessage (git config commit.template .gitmessage)"
    exit 1
}

# 1) Merge/Revert başlıkları izinli (git tarafından üretilir).
case "$SUBJECT" in
    Merge\ *|Revert\ *) exit 0 ;;
esac

# 2) Şablon placeholder'ı düzenlenmeden bırakılmış mı? (git commit --template)
case "$SUBJECT" in
    *'<'*|*'>'*) fail "şablon placeholder'ı düzenlenmemiş — başlığı yaz" ;;
esac

# 3) Format: "<kapsam>: <eylem>" — iki nokta + boşluk şart.
case "$SUBJECT" in
    *": "*) : ;;
    *) fail "başlık '<kapsam>: <eylem>' formatında olmalı (iki nokta + boşluk)" ;;
esac

# 4) Uzunluk ≤ 72 karakter.
LEN=$(printf '%s' "$SUBJECT" | wc -m | tr -d ' ')
[ "$LEN" -le 72 ] || fail "başlık $LEN karakter (sınır: 72)"

# 5) Noise/marker başlıklar — küçük harfe çevirip eşle (tam kelime/önek).
LOW=$(printf '%s' "$SUBJECT" | tr '[:upper:]' '[:lower:]')
case "$LOW" in
    wip|wip:*|*' wip'|*' wip '*|*' wip:'*|smoke*|test\ marker*|test:*|test|fix\ typo*|minor\ fix*|temp|tmp|asd|asdf|foo|foo:*|bar|bar:*|lorem*|lorem\ ipsum*)
        fail "noise/marker başlık yasak" ;;
esac

exit 0
