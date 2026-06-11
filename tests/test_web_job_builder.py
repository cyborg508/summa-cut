from __future__ import annotations

import fitz
import pytest

from summa_cut.layout import compute_layout
from summa_cut.pdf_io import MM_PER_POINT
from web.sessions import SessionStore
from web.job_builder import JobParams, build_job

PT = 1.0 / MM_PER_POINT


def _pdf_bytes() -> bytes:
    side = 40 * PT
    doc = fitz.open()
    doc.new_page(width=side, height=side).draw_rect(fitz.Rect(3, 3, side - 3, side - 3), color=(0, 0, 1))
    data = doc.tobytes()
    doc.close()
    return data


def _session_with_pdf(tmp_path):
    store = SessionStore(base_dir=tmp_path)
    s = store.create()
    store.save_upload(s, "src.pdf", _pdf_bytes())
    return s


def _params(**over) -> JobParams:
    base = dict(
        print_upload="src.pdf", print_page=0,
        cut_upload="src.pdf", cut_page=0,
        sheet_w_mm=330.0, sheet_h_mm=480.0,
        item_w_mm=30.0, item_h_mm=30.0, rotation_allowed=False,
        gap_enabled=True, gap_mm=3.0,
    )
    base.update(over)
    return JobParams(**base)


def test_build_job_basic_grid_produces_placements(tmp_path):
    s = _session_with_pdf(tmp_path)
    job = build_job(_params(), s)
    assert job.gap_enabled is True
    assert job.generate_cut_grid is False
    layout = compute_layout(job)
    assert layout.count > 50


def test_gapless_forces_cut_equals_print_and_grid(tmp_path):
    s = _session_with_pdf(tmp_path)
    job = build_job(_params(gap_enabled=False, cut_upload=None, cut_page=None), s)
    assert job.generate_cut_grid is True
    assert job.gap_enabled is False
    assert job.cut_page.pdf_path == job.print_page.pdf_path
    assert job.cut_page.page_index == job.print_page.page_index


def test_unknown_upload_raises(tmp_path):
    s = _session_with_pdf(tmp_path)
    with pytest.raises(ValueError):
        build_job(_params(print_upload="brak.pdf"), s)


def test_page_index_out_of_range_raises(tmp_path):
    s = _session_with_pdf(tmp_path)
    with pytest.raises(ValueError):
        build_job(_params(print_page=5), s)


def test_zero_item_size_raises(tmp_path):
    s = _session_with_pdf(tmp_path)
    with pytest.raises(ValueError):
        build_job(_params(item_w_mm=0.0), s)


def test_gap_mode_requires_cut_selection(tmp_path):
    s = _session_with_pdf(tmp_path)
    with pytest.raises(ValueError):
        build_job(_params(cut_upload=None), s)


def test_manual_grid_odd_rows_with_split_raises(tmp_path):
    s = _session_with_pdf(tmp_path)
    with pytest.raises(ValueError):
        build_job(_params(manual_grid_enabled=True, manual_columns=3, manual_rows=3,
                          split_horizontal_groups=True), s)


def test_opos_offsets_passed_through(tmp_path):
    s = _session_with_pdf(tmp_path)
    job = build_job(_params(opos_side_offset_mm=12.0, opos_bottom_offset_mm=8.0, opos_top_offset_mm=35.0), s)
    assert job.opos_spec.side_offset_mm == 12.0
    assert job.opos_spec.bottom_offset_mm == 8.0
    assert job.opos_spec.top_offset_mm == 35.0
