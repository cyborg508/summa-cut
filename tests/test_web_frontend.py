from __future__ import annotations

from fastapi.testclient import TestClient

from web.server import create_app
from web.sessions import SessionStore


def _client(tmp_path):
    return TestClient(create_app(store=SessionStore(base_dir=tmp_path)))


def test_root_serves_html(tmp_path):
    c = _client(tmp_path)
    r = c.get("/")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "summa-cut" in r.text


def test_static_assets_served(tmp_path):
    c = _client(tmp_path)
    assert _client(tmp_path).get("/static/app.js").status_code == 200
    assert c.get("/static/style.css").status_code == 200


REQUIRED_IDS = [
    "upload-input", "upload-btn", "uploads-list",
    "print-file", "print-page", "cut-file", "cut-page",
    "sheet-w", "sheet-h", "item-w", "item-h", "rotation",
    "gap-mm", "split", "split-spread", "manual", "manual-cols", "manual-rows",
    "opos-side", "opos-bottom", "opos-top",
    "montage-enable", "montage-rows", "montage-add",
    "generate-btn", "summary", "error",
    "preview-print", "preview-cut",
]


REMOVED_IDS = ["base-name", "download-print", "download-cut"]


def test_index_no_longer_has_removed_ids(tmp_path):
    html = _client(tmp_path).get("/").text
    present = [i for i in REMOVED_IDS if f'id="{i}"' in html]
    assert not present, f"usunięte elementy wciąż w index.html: {present}"


def test_index_has_required_element_ids(tmp_path):
    html = _client(tmp_path).get("/").text
    missing = [i for i in REQUIRED_IDS if f'id="{i}"' not in html]
    assert not missing, f"brak id w index.html: {missing}"


def test_index_references_assets(tmp_path):
    html = _client(tmp_path).get("/").text
    assert "/static/app.js" in html
    assert "/static/style.css" in html


def test_index_has_special_mode_controls():
    from pathlib import Path
    html = (Path(__file__).resolve().parents[1] / "web" / "static" / "index.html").read_text(encoding="utf-8")
    for el_id in [
        "special-enable", "special-bleed", "special-prepare-btn",
        "special-row0", "special-row1", "special-col0", "special-col1",
        "special-colx0", "special-colx1", "special-rowy0", "special-rowy1",
        "special-status",
    ]:
        assert f'id="{el_id}"' in html, f"brak #{el_id} w index.html"


def test_app_js_references_special_endpoints():
    from pathlib import Path
    js = (Path(__file__).resolve().parents[1] / "web" / "static" / "app.js").read_text(encoding="utf-8")
    assert "/api/special/prepare" in js
    assert "special_enabled" in js


def test_app_js_invalidates_special_on_input_change():
    # Po przygotowaniu wykrojnika zmiana pliku/strony/spadu musi unieważnić
    # gotowość trybu specjalnego, inaczej collectParams() wysłałby stare
    # przycięcie. Pilnujemy, że funkcja istnieje i jest podpięta pod te wejścia.
    from pathlib import Path
    js = (Path(__file__).resolve().parents[1] / "web" / "static" / "app.js").read_text(encoding="utf-8")
    assert "function invalidateSpecial(" in js
    for el_id in ["print-file", "print-page", "cut-file", "cut-page", "special-bleed"]:
        assert f'$("{el_id}").addEventListener' in js
    # wszystkie te wejścia wołają invalidateSpecial
    assert js.count("invalidateSpecial") >= 6
