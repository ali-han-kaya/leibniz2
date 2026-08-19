#!/usr/bin/env python3
"""check_commit_messages.py — commit-msg kurallarını CI'da advisory denetle.

commit_msg_hook.sh (pre-commit commit-msg stage) yerel `git commit`'i BLOKE
eder; CI'da zaten push edilmiş commit'leri denetleyip ihlalleri
logs/commit_msg_findings.json sidecar'ına yazar. Advisory: her zaman exit 0
döner — ihlal olsa bile build bloke edilmez. gen_precommit_report.py bu
sidecar'ı okuyup PRECOMMIT_RAPORU'na "Commit-msg (CI advisory)" bölümü ekler.

Tek kaynak kuralı: kurallar commit_msg_hook.sh'da yaşar; bu script onları
KOPYALAMAZ — her commit mesajını o hook'a geçirir (drift yok). Yalnızca
mesajı geçici dosyaya yazar + hook'u `sh` ile çağırır + çıktıyı toplar.

Kullanım (CI çalışma dizininden; checkout fetch-depth:0 olmalı):
  python3 check_commit_messages.py --range 'origin/main...HEAD' \
      --out logs/commit_msg_findings.json
  python3 check_commit_messages.py --shas <sha1> <sha2> ...   # test/smoke
"""
import argparse
import json
import pathlib
import subprocess
import sys
import tempfile

# Mutlak yol — script herhangi bir cwd'den çağrılsa da (ör. simulate_verify_job.sh
# SIM_DIR altından) hook bulunur. Tek kaynak: commit_msg_hook.sh.
HOOK = str(pathlib.Path(__file__).resolve().parent / "commit_msg_hook.sh")


def check_message(msg, hook=HOOK):
    """commit-msg hook'unu mesaja uygula; (returncode, detail) döndür.

    returncode 0 = PASS; 0 dışı = ihlal (detail, hook'un stdout/stderr'i).
    """
    fd, path = tempfile.mkstemp(prefix="commit-msg-", text=True)
    try:
        with open(fd, "w", encoding="utf-8") as f:
            f.write(msg)
        r = subprocess.run(["sh", hook, path],
                           capture_output=True, text=True)
        detail = ((r.stdout or "") + (r.stderr or "")).strip()
        return r.returncode, detail
    finally:
        pathlib.Path(path).unlink(missing_ok=True)


def git_log(range_spec):
    r = subprocess.run(["git", "log", "--format=%H", range_spec],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return []
    return [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]


def git_message(sha):
    r = subprocess.run(["git", "show", "-s", "--format=%B", sha],
                       capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ""


def git_subject(sha):
    r = subprocess.run(["git", "show", "-s", "--format=%s", sha],
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--range", default=None,
                    help="git aralığı (örn. origin/main...HEAD)")
    ap.add_argument("--shas", nargs="*", default=None,
                    help="açık commit SHA listesi (test için)")
    ap.add_argument("--out", default="logs/commit_msg_findings.json")
    ap.add_argument("--hook", default=HOOK)
    args = ap.parse_args(argv)

    if args.shas is not None:
        shas = args.shas
    elif args.range:
        shas = git_log(args.range)
    else:
        print("HATA: --range veya --shas gerekli", file=sys.stderr)
        return 2

    violations = []
    for sha in shas:
        rc, detail = check_message(git_message(sha), args.hook)
        if rc != 0:
            violations.append({
                "commit": sha[:12],
                "subject": git_subject(sha)[:120],
                "detail": detail,
            })

    data = {"checked": len(shas), "violations": violations}
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print(f"commit-msg denetimi: {len(shas)} commit, {len(violations)} ihlal")
    for v in violations:
        print(f"  [IHLAL] {v['commit']} {v['subject']}")
    return 0  # advisory — asla bloke etmez


if __name__ == "__main__":
    sys.exit(main())
