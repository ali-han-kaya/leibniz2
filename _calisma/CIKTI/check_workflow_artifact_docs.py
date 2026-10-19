#!/usr/bin/env python3
"""verify.yml artifact üretimleri ile doc/manifest kapsamını karşılaştır."""
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
WORKFLOW = ROOT / ".github/workflows/verify.yml"
DOC = ROOT / "docs/PUBLISH_SCENARIO.md"
sys.path.insert(0, str(HERE))
import audit_live_ci_sync as als  # noqa: E402
import gen_repro_manifest as grm  # noqa: E402
# TEK KAYNAK: workflow_contract.UPLOAD_EXCEPTIONS — badge/action-pin/meta
# denetçi artifact'ları ARTIFACT_JOBS kapsamı dışında bilinçli tutulur
# (kopya değil, re-export; test_workflow_contract drift'i yakalar).
from workflow_contract import UPLOAD_EXCEPTIONS  # noqa: E402


def _matrix_values(text):
    """YAML'daki `key: [v1, v2]` matrix tanımlarını topla (dosya geneli)."""
    matrix_values = {}
    for match in re.finditer(
            r"^\s+([A-Za-z_][A-Za-z0-9_-]*):\s*\[([^]\n]+)\]\s*$",
            text, flags=re.M):
        matrix_values[match.group(1)] = [
            value.strip().strip("'\"") for value in match.group(2).split(",")
        ]
    return matrix_values


def _step_env_aliases(block):
    """Adım bloğundaki `VAR: ${{ matrix.KEY }}` env eşlemeleri (YAML adı).

    Örn. a11y-gate adımlarındaki `A11Y_THEME: ${{ matrix.theme }}` — shell
    `${VAR}` şablonları bu eşleme üzerinden matrix değerlerine çözülür.
    """
    return {
        m.group(1): m.group(2)
        for m in re.finditer(
            r"^\s{10}([A-Za-z_][A-Za-z0-9_]*):\s*\$\{\{\s*matrix\.([A-Za-z_][A-Za-z0-9_-]*)\s*\}\}\s*$",
            block, flags=re.M)
    }


def _step_theme_gate(block, matrix_values):
    """Adım `if:`indeki `matrix.<key> == 'literal'` kısıtları (matrix adı).

    Tema-kapılı adımlar (örn. `if: ... matrix.theme == 'dark'`) yalnızca
    izinli child değerlerine genişler; kapısız adımlar tüm değerlere.
    Bilinmeyen literal kısıt uygulamaz (genişletme güvenli tarafta kalır).
    """
    gated = {}
    m = re.search(r"^\s*if:.*$", block, flags=re.M)
    if not m:
        return gated
    for key, lit in re.findall(
            r"matrix\.([A-Za-z_][A-Za-z0-9_-]*)\s*==\s*['\"]([^'\"]+)['\"]",
            m.group(0)):
        if key in matrix_values and lit in matrix_values[key]:
            gated[key] = [lit]
    return gated


def expand_names(template, matrix_values, env_aliases=None, gate_restrict=None):
    """Artifact şablonunu matrix değerlerine fail-closed aç.

    Üç kaynak sırayla uygulanır: `${{ matrix.KEY }}` (YAML ifadesi),
    `${VAR}` (adım env'indirection — `VAR: ${{ matrix.KEY }}`), adım `if:`
    tema kapısı (izinli child'larla sınırlar).
    """
    values = dict(matrix_values)
    for key, vals in (gate_restrict or {}).items():
        if key in values:
            values[key] = list(vals)
    expanded = [template]
    for key, vals in values.items():
        token = "${{ matrix.%s }}" % key
        if not any(token in name for name in expanded):
            continue
        expanded = [name.replace(token, value)
                    for name in expanded for value in vals]
    for var, key in (env_aliases or {}).items():
        token = "${%s}" % var
        vals = values.get(key, [])
        if not vals or not any(token in name for name in expanded):
            continue
        expanded = [name.replace(token, value)
                    for name in expanded for value in vals]
    return expanded


def workflow_artifacts(text):
    """Upload artifact adlarını matrix child'larına göre fail-closed aç.

    GitHub Actions aynı artifact step'ini N matrix child'da çalıştırır ve
    sonuç adları child değeridir. Denetleyici de doc/manifest karşılaştırmasında
    aynı genişletilmiş adları görmelidir; aksi halde doğru bir workflow yanlışlıkla
    eksik artifact üretimi gibi raporlanır.

    Adım-içi çözümleme (YAML adı + matrix adı): `${VAR}` shell şablonları
    adımın `env:` eşlemesi (`VAR: ${{ matrix.KEY }}`) üzerinden, `if:`
    tema kapıları (`matrix.<key> == 'literal'`) izinli child'larla çözülür.
    """
    matrix_values = _matrix_values(text)
    names = []
    # Adım bloklarına böl: her `- name:` yeni blok başlatır; Upload
    # adımının adı/env/koşulu kendi bloğundan okunur.
    blocks = []
    current = None
    for line in text.splitlines():
        if re.match(r"^\s*- name:", line):
            current = [line]
            blocks.append(current)
        elif current is not None:
            current.append(line)
    for block in blocks:
        if not re.match(r"^\s*- name: Upload ", block[0]):
            continue
        block_text = "\n".join(block)
        aliases = _step_env_aliases(block_text)
        gate = _step_theme_gate(block_text, matrix_values)
        for line in block:
            m = re.match(r"^\s{10}name:\s*([^#\n]+)", line)
            if not m:
                continue
            template = m.group(1).strip().strip("'\"")
            for name in expand_names(template, matrix_values, aliases, gate):
                if name not in names:
                    names.append(name)
    return names


def check():
    errors = []
    wf = workflow_artifacts(WORKFLOW.read_text(encoding="utf-8"))
    doc = als.parse_doc_artifacts(DOC.read_text(encoding="utf-8"))
    jobs = set(grm.ARTIFACT_JOBS)
    for name in sorted(set(wf) - set(doc) - {"badge-check"}):
        errors.append(f"workflow upload-artifact '{name}' PUBLISH_SCENARIO listesinde yok")
    for name in sorted(set(wf) - jobs - UPLOAD_EXCEPTIONS):
        errors.append(f"workflow upload-artifact '{name}' ARTIFACT_JOBS'ta yok")
    for name in sorted(jobs - set(wf) - {"reproducibility"}):
        errors.append(f"ARTIFACT_JOBS '{name}' için verify.yml upload-artifact yok")
    return wf, doc, errors


def main():
    wf, doc, errors = check()
    print(f"workflow upload-artifact: {len(wf)}")
    print(f"PUBLISH_SCENARIO artifact: {len(doc)}")
    print(f"ARTIFACT_JOBS: {len(grm.ARTIFACT_JOBS)}")
    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print("PASS: workflow ↔ PUBLISH_SCENARIO ↔ ARTIFACT_JOBS senkron")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
