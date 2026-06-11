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
