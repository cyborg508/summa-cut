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
