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


def test_generate_then_download_pdfs(tmp_path):
    c = _session_with_upload(tmp_path)
    c.post("/api/job", json=_JOB)
    r = c.post("/api/generate", json={"base_name": "moj_arkusz"})
    assert r.status_code == 200
    names = r.json()
    assert names["print_name"] == "moj_arkusz_druk.pdf"
    assert names["cut_name"] == "moj_arkusz_wykrojnik.pdf"

    rp = c.get("/api/download/print")
    assert rp.status_code == 200
    assert rp.headers["content-type"] == "application/pdf"
    assert rp.content[:5] == b"%PDF-"

    rc = c.get("/api/download/cut")
    assert rc.status_code == 200
    assert rc.content[:5] == b"%PDF-"


def test_generate_before_job_is_400(tmp_path):
    c = _session_with_upload(tmp_path)
    r = c.post("/api/generate", json={"base_name": "x"})
    assert r.status_code == 400


def test_download_before_generate_is_404(tmp_path):
    c = _session_with_upload(tmp_path)
    c.post("/api/job", json=_JOB)
    r = c.get("/api/download/print")
    assert r.status_code == 404


def test_montage_job_preview_generate_download(tmp_path):
    c = _client(tmp_path)
    c.post("/api/session")
    c.post("/api/upload", files={"file": ("a.pdf", _pdf_bytes(), "application/pdf")})
    c.post("/api/upload", files={"file": ("b.pdf", _pdf_bytes(), "application/pdf")})

    job = {
        "print_upload": "a.pdf", "print_page": 0, "cut_upload": "a.pdf", "cut_page": 0,
        "sheet_w_mm": 330.0, "sheet_h_mm": 480.0, "item_w_mm": 30.0, "item_h_mm": 30.0,
        "gap_enabled": True, "gap_mm": 3.0,
        "montage": [
            {"label": "A", "print_upload": "a.pdf", "print_page": 0, "cut_upload": "a.pdf", "cut_page": 0, "quantity": 4},
            {"label": "B", "print_upload": "b.pdf", "print_page": 0, "cut_upload": "b.pdf", "cut_page": 0, "quantity": 2},
        ],
    }
    r = c.post("/api/job", json=job)
    assert r.status_code == 200
    body = r.json()
    assert body["requested_count"] == 6
    assert body["count"] == 6

    rp = c.get("/api/preview/print.png")
    assert rp.status_code == 200 and rp.content[:8] == b"\x89PNG\r\n\x1a\n"

    rg = c.post("/api/generate", json={"base_name": "montaz"})
    assert rg.status_code == 200
    assert rg.json()["print_name"] == "montaz_druk.pdf"
    rd = c.get("/api/download/print")
    assert rd.status_code == 200 and rd.content[:5] == b"%PDF-"


def test_montage_bad_upload_is_400(tmp_path):
    c = _client(tmp_path)
    c.post("/api/session")
    c.post("/api/upload", files={"file": ("a.pdf", _pdf_bytes(), "application/pdf")})
    job = {
        "print_upload": "a.pdf", "print_page": 0, "cut_upload": "a.pdf", "cut_page": 0,
        "item_w_mm": 30.0, "item_h_mm": 30.0, "gap_enabled": True, "gap_mm": 3.0,
        "montage": [{"print_upload": "brak.pdf", "print_page": 0, "cut_upload": "a.pdf", "cut_page": 0, "quantity": 1}],
    }
    r = c.post("/api/job", json=job)
    assert r.status_code == 400
