"""test_bootstrap_unit_coverage.py — bootstrap_units.conf <-> battery drift guard.

Sözleşme: bootstrap_units.conf'taki her unit, check-unit-tests bataryasındaki
(manifest: check_unit_tests.list) en az bir test dosyasında adıyla geçmelidir.
conf'a yeni unit eklenip hiçbir test ona değinmiyorsa bu test kırmızıya düşer
(fail-closed) — kapsamasız unit gönderilemez.

conf dinamik okunur: yeni unit otomatik denetlenir, bu dosyada elle unit
listesi yoktur. Kapsama kanıtı, manifestteki test kaynaklarında unit adının
geçmesidir (örn. test_dev_bootstrap.py'deki UNITS tablosu). EXCLUDE'daki
dosyalar bataryada değildir; sayılmazlar (manifest = batarya).

stdlib-only, ortamsız: her yerde koşar (venv/node gerekmez).
"""
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, os.pardir, os.pardir))
CIKTI = os.path.join(ROOT, "_calisma", "CIKTI")
CONF = os.path.join(ROOT, "_calisma", "bootstrap_units.conf")
MANIFEST = os.path.join(CIKTI, "check_unit_tests.list")


def _read_conf_units(path=CONF):
    """bootstrap_units.conf'taki unit adları (yorum/boş satır dışı)."""
    units = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key = line.split("=", 1)[0].strip()
            if "." in key:
                continue  # metadata (unit.install_time_s), unit değil
            units.append(key)
    return units


def _read_manifest(path=MANIFEST):
    """Batarya manifestindeki test dosya adları."""
    entries = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            entries.append(line)
    return entries


def _covering_tests(unit, manifest_entries):
    """Unit adını kaynak metninde geçiren manifest testleri."""
    hits = []
    for entry in manifest_entries:
        path = os.path.join(CIKTI, entry)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            continue
        if unit in text:
            hits.append(entry)
    return hits


class TestBootstrapUnitCoverage(unittest.TestCase):
    def test_every_conf_unit_covered_by_battery(self):
        units = _read_conf_units()
        self.assertTrue(units, "bootstrap_units.conf'ta hiç unit yok")
        manifest = _read_manifest()
        uncovered = {}
        for unit in units:
            hits = _covering_tests(unit, manifest)
            if not hits:
                uncovered[unit] = hits
        self.assertEqual(
            uncovered, {},
            "kapsamasız unit (conf'ta var, bataryada geçen test yok): %s"
            % sorted(uncovered),
        )

    def test_guard_itself_in_manifest(self):
        """Bu guard manifestten düşerse sessizce körleşir — onu da denetle."""
        manifest = _read_manifest()
        self.assertIn(
            os.path.basename(__file__), manifest,
            "guard manifestte yok: drift koruması bataryada koşmuyor",
        )


if __name__ == "__main__":
    unittest.main()
