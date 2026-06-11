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
