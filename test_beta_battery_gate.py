"""Battery gate - mock tabanlı senkron süiti"""
import pathlib, json
def test_gate():
    idx = pathlib.Path("_calisma/CIKTI/refs-index.json")
    assert idx.exists(), "refs-index.json yok - gen_refs_index.py çalıştır"
    data = json.loads(idx.read_text())
    assert "refs" in data
    print("PASS: battery gate")
if __name__ == "__main__":
    test_gate()
