from __future__ import annotations

import fitz
from fastapi.testclient import TestClient

from summa_cut.pdf_io import MM_PER_POINT
from web.server import create_app
from web.sessions import SessionStore

PT = 1.0 / MM_PER_POINT


def _pdf_bytes() -> bytes:
    doc = fitz.open(); side = 40 * PT
    doc.new_page(width=side, height=side).draw_rect(fitz.Rect(3, 3, side - 3, side - 3), color=(0, 0, 1))
    data = doc.tobytes(); doc.close()
    return data


def _client(tmp_path) -> TestClient:
    app = create_app(store=SessionStore(base_dir=tmp_path))
    return TestClient(app)


def test_create_session_sets_cookie(tmp_path):
    c = _client(tmp_path)
    r = c.post("/api/session")
    assert r.status_code == 200
    assert "sid" in r.cookies or "sid" in c.cookies
    assert r.json()["session_id"]


def test_upload_returns_page_info(tmp_path):
    c = _client(tmp_path)
    c.post("/api/session")
    r = c.post("/api/upload", files={"file": ("src.pdf", _pdf_bytes(), "application/pdf")})
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "src.pdf"
    assert body["page_count"] == 1
    assert len(body["page_sizes_mm"]) == 1


def test_upload_without_session_is_401(tmp_path):
    c = _client(tmp_path)
    r = c.post("/api/upload", files={"file": ("src.pdf", _pdf_bytes(), "application/pdf")})
    assert r.status_code == 401


def test_upload_rejects_non_pdf(tmp_path):
    c = _client(tmp_path)
    c.post("/api/session")
    r = c.post("/api/upload", files={"file": ("x.pdf", b"nie-pdf", "application/pdf")})
    assert r.status_code == 400


def _session_with_upload(tmp_path):
    c = _client(tmp_path)
    c.post("/api/session")
    c.post("/api/upload", files={"file": ("src.pdf", _pdf_bytes(), "application/pdf")})
    return c


_JOB = dict(
    print_upload="src.pdf", print_page=0, cut_upload="src.pdf", cut_page=0,
    sheet_w_mm=330.0, sheet_h_mm=480.0, item_w_mm=30.0, item_h_mm=30.0,
    gap_enabled=True, gap_mm=3.0,
)


def test_job_returns_layout_summary(tmp_path):
    c = _session_with_upload(tmp_path)
    r = c.post("/api/job", json=_JOB)
    assert r.status_code == 200
    body = r.json()
    assert body["count"] > 50
    assert body["columns"] > 0 and body["rows"] > 0


def test_job_with_bad_params_is_400(tmp_path):
    c = _session_with_upload(tmp_path)
    r = c.post("/api/job", json={**_JOB, "item_w_mm": 0.0})
    assert r.status_code == 400


def test_preview_returns_png(tmp_path):
    c = _session_with_upload(tmp_path)
    c.post("/api/job", json=_JOB)
    r = c.get("/api/preview/print.png")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_preview_before_job_is_400(tmp_path):
    c = _session_with_upload(tmp_path)
    r = c.get("/api/preview/print.png")
    assert r.status_code == 400


def test_preview_bad_which_is_404(tmp_path):
    c = _session_with_upload(tmp_path)
    c.post("/api/job", json=_JOB)
    r = c.get("/api/preview/bok.png")
    assert r.status_code == 404
