#!/usr/bin/env python3
"""Fake launchctl shim — K21-START bootstrap smoke test için.

update_preview.sh --bootstrap --start [HOME] çağrıldığında PATH'e konulan
bu shim, launchctl bootstrap/bootout/enable komutlarını yakalar ve bir
log dosyasına yazar. Gerçek launchctl çalışmaz — CI'da (macOS runners'da
 bile) izole test mümkün olur.

Kullanım:
    # Shim'i oluştur
    shim_dir = create_launchctl_shim(tmp_dir)
    # PATH'e ekle
    env["PATH"] = shim_dir + ":" + env["PATH"]
    # update_preview.sh --bootstrap --start [HOME] çalıştır
    # Shim log'unu oku: bootstrap çağrıları kayıtlı mı?
"""

import os
import sys
import tempfile


_SHIM_TEMPLATE = '''\
#!/bin/sh
# Fake launchctl — K21-START smoke test shim
# Her çağrıyı LAUNCHCTL_LOG dosyasına yazar ve exit 0 döner.
_log="${LAUNCHCTL_LOG:-/dev/null}"
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) launchctl $*" >> "$_log"
# Gerçek launchctl gibi davran: bootout hata verse bile devam et
case "$1" in
  bootout)  exit 0 ;;
  bootstrap) exit 0 ;;
  enable)   exit 0 ;;
  list)     echo "[]"; exit 0 ;;
  *)        exit 0 ;;
esac
'''


def create_launchctl_shim(dest_dir=None):
    """Fake launchctl shim dizinini oluşturur ve shim yolunu döndürür.

    Returns:
        (shim_bin_dir, shim_path, log_path)
    """
    if dest_dir is None:
        dest_dir = tempfile.mkdtemp(prefix="k21-shim-")
    shim_bin = os.path.join(dest_dir, "bin")
    os.makedirs(shim_bin, exist_ok=True)
    shim_path = os.path.join(shim_bin, "launchctl")
    log_path = os.path.join(dest_dir, "launchctl.log")
    with open(shim_path, "w") as f:
        f.write(_SHIM_TEMPLATE)
    os.chmod(shim_path, 0o755)
    return shim_bin, shim_path, log_path


def parse_launchctl_log(log_path):
    """Shim log'unu ayrıştırır — hangi komutlar çağrıldı?

    Returns:
        list of {"cmd": str, "args": list, "ts": str}
    """
    entries = []
    if not os.path.isfile(log_path):
        return entries
    with open(log_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            # Format: "2026-08-27T12:00:00Z launchctl bootstrap domain plist"
            parts = line.split(" launchctl ", 1)
            if len(parts) != 2:
                continue
            ts = parts[0]
            cmd_parts = parts[1].split()
            if cmd_parts:
                entries.append({
                    "ts": ts,
                    "cmd": cmd_parts[0],
                    "args": cmd_parts[1:],
                })
    return entries


def had_bootstrap_call(log_path):
    """Shim log'unda en az bir 'bootstrap' çağrısı var mı?"""
    for e in parse_launchctl_log(log_path):
        if e["cmd"] == "bootstrap":
            return True
    return False


# ---------- Fake curl shim (--verify HTTP 200 kontrolü için) ----------

_CURL_TEMPLATE = '''\
#!/bin/sh
# Fake curl — K21-START --verify smoke test shim
# /api/latest çağrılarında HTTP 200 döner; diğerleri 000.
_log="${CURL_LOG:-/dev/null}"
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) curl $*" >> "$_log"
while [ $# -gt 0 ]; do
  case "$1" in
    -w) shift; fmt="$1"; shift ;;
    *)  shift ;;
  esac
done
case "$fmt" in
  *http_code*) echo "200" ;;
  *)           echo "" ;;
esac
exit 0
'''


def create_curl_shim(dest_dir):
    """Fake curl shim oluşturur.

    Returns: (shim_bin_dir, shim_path, log_path)
    """
    shim_bin = os.path.join(dest_dir, "bin")
    os.makedirs(shim_bin, exist_ok=True)
    shim_path = os.path.join(shim_bin, "curl")
    log_path = os.path.join(dest_dir, "curl.log")
    with open(shim_path, "w") as f:
        f.write(_CURL_TEMPLATE)
    os.chmod(shim_path, 0o755)
    return shim_bin, shim_path, log_path


def create_full_shim_set(dest_dir=None):
    """launchctl + curl shim'lerini tek dizinde oluşturur.

    Returns: (shim_bin_dir, launchctl_log, curl_log)
    """
    if dest_dir is None:
        dest_dir = tempfile.mkdtemp(prefix="k21-shimset-")
    shim_bin, _, lc_log = create_launchctl_shim(dest_dir)
    _, _, curl_log = create_curl_shim(dest_dir)
    return shim_bin, lc_log, curl_log


if __name__ == "__main__":
    # Demo: shim oluştur ve test et
    shim_dir, shim_path, log_path = create_launchctl_shim()
    print(f"Shim: {shim_path}")
    print(f"Log:  {log_path}")
    # Test çağrısı
    import subprocess
    env = dict(os.environ)
    env["LAUNCHCTL_LOG"] = log_path
    env["PATH"] = shim_dir + ":" + env.get("PATH", "")
    subprocess.run(["launchctl", "bootstrap", "gui/501", "/tmp/test.plist"],
                   env=env)
    entries = parse_launchctl_log(log_path)
    for e in entries:
        print(f"  {e['cmd']} {' '.join(e['args'])}")
    print(f"bootstrap çağrıldı mı: {had_bootstrap_call(log_path)}")
