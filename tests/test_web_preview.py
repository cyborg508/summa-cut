from __future__ import annotations

import fitz
import pytest

from summa_cut.layout import compute_layout
from summa_cut.pdf_io import MM_PER_POINT
from web.sessions import SessionStore
from web.job_builder import JobParams, build_job
from web.preview_render import render_output_png

PT = 1.0 / MM_PER_POINT


def _job(tmp_path, **over):
    doc = fitz.open(); side = 40 * PT
    doc.new_page(width=side, height=side).draw_rect(fitz.Rect(3, 3, side - 3, side - 3), color=(0, 0, 1))
    data = doc.tobytes(); doc.close()
    store = SessionStore(base_dir=tmp_path); s = store.create()
    store.save_upload(s, "src.pdf", data)
    params = JobParams(print_upload="src.pdf", print_page=0, cut_upload="src.pdf", cut_page=0,
                       item_w_mm=30.0, item_h_mm=30.0, gap_enabled=True, gap_mm=3.0, **over)
    job = build_job(params, s)
    return job, compute_layout(job)


def test_render_print_returns_png_bytes(tmp_path):
    job, layout = _job(tmp_path)
    data = render_output_png(job, layout, which="print", max_px=400)
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(data) > 500


def test_render_cut_returns_png_bytes(tmp_path):
    job, layout = _job(tmp_path)
    data = render_output_png(job, layout, which="cut", max_px=400)
    assert data[:8] == b"\x89PNG\r\n\x1a\n"


def test_invalid_which_raises(tmp_path):
    job, layout = _job(tmp_path)
    with pytest.raises(ValueError):
        render_output_png(job, layout, which="bok", max_px=400)


def test_render_special_tile_png_nonzero(tmp_path):
    import fitz
    from web.preview_render import render_special_tile_png
    # „przycięty druk": szare wypełnienie; „przycięty wykrojnik": czerwony obrys
    pp = tmp_path / "p.pdf"
    doc = fitz.open(); pg = doc.new_page(width=80, height=60)
    pg.draw_rect(fitz.Rect(0, 0, 80, 60), color=(0, 0, 0), fill=(0.6, 0.6, 0.6), width=0)
    doc.save(str(pp)); doc.close()
    cp = tmp_path / "c.pdf"
    doc = fitz.open(); pg = doc.new_page(width=80, height=60)
    pg.draw_rect(fitz.Rect(2, 2, 78, 58), color=(1, 0, 0), width=1.0)
    doc.save(str(cp)); doc.close()

    png = render_special_tile_png(str(pp), str(cp), max_px=200)
    assert isinstance(png, bytes) and len(png) > 100
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def _two_page_para(tmp_path, w_mm=40.0, h_mm=30.0):
    doc = fitz.open()
    doc.new_page(width=w_mm * PT, height=h_mm * PT).draw_rect(
        fitz.Rect(2 * PT, 2 * PT, (w_mm - 2) * PT, (h_mm - 2) * PT), color=(0, 0, 1))
    doc.new_page(width=w_mm * PT, height=h_mm * PT).draw_rect(
        fitz.Rect(1 * PT, 1 * PT, (w_mm - 1) * PT, (h_mm - 1) * PT), color=(1, 0, 0))
    path = tmp_path / "para.pdf"
    doc.save(path); doc.close()
    return str(path)


def test_render_manual_tile_png_returns_png_with_aspect(tmp_path):
    import io
    from web.preview_render import render_manual_tile_png
    path = _two_page_para(tmp_path)  # 40x30
    bbox0 = (0.0, 0.0, 40 * PT, 30 * PT)
    bbox1 = (0.0, 0.0, 40 * PT, 30 * PT)
    png = render_manual_tile_png(path, 0, bbox0, path, 1, bbox1, 40.0, 30.0, 0, max_px=200)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    pix = fitz.Pixmap(io.BytesIO(png))
    assert pix.width == 200 and 140 <= pix.height <= 160
