from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from summa_cut.pdf_io import MM_PER_POINT
from web.sessions import SessionStore

PT = 1.0 / MM_PER_POINT


def _pdf_bytes() -> bytes:
    side = 40 * PT
    doc = fitz.open()
    page = doc.new_page(width=side, height=side)
    page.draw_rect(fitz.Rect(3, 3, side - 3, side - 3), color=(0, 0, 1), width=1.5)
    data = doc.tobytes()
    doc.close()
    return data


def test_create_makes_unique_sessions_with_workdir(tmp_path):
    store = SessionStore(base_dir=tmp_path)
    a = store.create()
    b = store.create()
    assert a.id != b.id
    assert Path(a.workdir).is_dir()
    assert store.get(a.id) is a
    assert store.get("nieistnieje") is None


def test_save_upload_returns_pdfinfo_and_stores_it(tmp_path):
    store = SessionStore(base_dir=tmp_path)
    s = store.create()
    info = store.save_upload(s, "plik.pdf", _pdf_bytes())
    assert info.page_count == 1
    assert info.name == "plik.pdf"
    assert "plik.pdf" in s.uploads
    assert Path(info.path).is_file()
    assert Path(info.path).parent == Path(s.workdir)


def test_save_upload_rejects_non_pdf(tmp_path):
    store = SessionStore(base_dir=tmp_path)
    s = store.create()
    with pytest.raises(ValueError):
        store.save_upload(s, "zly.pdf", b"to nie jest pdf")


def test_sweep_removes_expired_and_deletes_workdir(tmp_path):
    store = SessionStore(base_dir=tmp_path, ttl_seconds=0)
    s = store.create()
    workdir = Path(s.workdir)
    assert workdir.is_dir()
    store.sweep()
    assert store.get(s.id) is None
    assert not workdir.exists()
