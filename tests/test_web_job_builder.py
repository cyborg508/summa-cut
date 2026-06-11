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


def _session_with_two_pdfs(tmp_path):
    store = SessionStore(base_dir=tmp_path)
    s = store.create()
    store.save_upload(s, "a.pdf", _pdf_bytes())
    store.save_upload(s, "b.pdf", _pdf_bytes())
    return s


def _montage_params(items, **over) -> JobParams:
    base = dict(
        print_upload="a.pdf", print_page=0, cut_upload="a.pdf", cut_page=0,
        sheet_w_mm=330.0, sheet_h_mm=480.0, item_w_mm=30.0, item_h_mm=30.0,
        gap_enabled=True, gap_mm=3.0, montage=items,
    )
    base.update(over)
    return JobParams(**base)


def test_montage_builds_items_with_quantities(tmp_path):
    s = _session_with_two_pdfs(tmp_path)
    params = _montage_params([
        {"label": "A", "print_upload": "a.pdf", "print_page": 0, "cut_upload": "a.pdf", "cut_page": 0, "quantity": 3},
        {"label": "B", "print_upload": "b.pdf", "print_page": 0, "cut_upload": "b.pdf", "cut_page": 0, "quantity": 2},
    ])
    job = build_job(params, s)
    assert len(job.montage_items) == 2
    assert [it.quantity for it in job.montage_items] == [3, 2]
    assert job.montage_items[0].label == "A"
    layout = compute_layout(job)
    assert layout.requested_count == 5
    assert layout.count == 5  # mieści się w arkuszu
    assert sorted(p.montage_item_index for p in layout.placements) == [0, 0, 0, 1, 1]


def test_montage_base_fields_taken_from_first_item(tmp_path):
    s = _session_with_two_pdfs(tmp_path)
    params = _montage_params([
        {"print_upload": "b.pdf", "print_page": 0, "cut_upload": "b.pdf", "cut_page": 0, "quantity": 1},
    ])
    job = build_job(params, s)
    assert job.print_page.pdf_path.endswith("b.pdf")
    assert job.cut_page.pdf_path.endswith("b.pdf")


def test_montage_unknown_upload_raises(tmp_path):
    s = _session_with_two_pdfs(tmp_path)
    params = _montage_params([
        {"print_upload": "brak.pdf", "print_page": 0, "cut_upload": "a.pdf", "cut_page": 0, "quantity": 1},
    ])
    with pytest.raises(ValueError):
        build_job(params, s)


def test_montage_zero_quantity_raises(tmp_path):
    s = _session_with_two_pdfs(tmp_path)
    params = _montage_params([
        {"print_upload": "a.pdf", "print_page": 0, "cut_upload": "a.pdf", "cut_page": 0, "quantity": 0},
    ])
    with pytest.raises(ValueError):
        build_job(params, s)


def test_montage_empty_list_uses_single_product_path(tmp_path):
    s = _session_with_two_pdfs(tmp_path)
    job = build_job(_montage_params([]), s)  # montage=[] → pojedynczy produkt
    assert job.montage_items == []
    assert compute_layout(job).count > 50


def test_montage_requires_gap_mode(tmp_path):
    s = _session_with_two_pdfs(tmp_path)
    params = _montage_params([
        {"print_upload": "a.pdf", "print_page": 0, "cut_upload": "a.pdf", "cut_page": 0, "quantity": 1},
    ], gap_enabled=False)
    with pytest.raises(ValueError):
        build_job(params, s)


def test_build_job_special_mode_sets_pattern(tmp_path):
    from web.job_builder import JobParams, build_job
    from web.sessions import SessionStore

    store = SessionStore(tmp_path, ttl_seconds=3600)
    session = store.create()
    # przygotuj przycięte uploady tak, jak zrobi to trasa /api/special/prepare
    import fitz
    for name in ("__special_print__.pdf", "__special_cut__.pdf"):
        doc = fitz.open()
        doc.new_page(width=160.0, height=100.0)  # ~56.4 x 35.3 mm
        data = doc.tobytes()
        doc.close()
        store.save_upload(session, name, data)

    params = JobParams(
        print_upload="__special_print__.pdf", print_page=0,
        cut_upload="__special_cut__.pdf", cut_page=0,
        item_w_mm=56.4, item_h_mm=35.3,
        special_enabled=True,
        special_row_offsets_mm=[0.0, 2.0],
        special_col_offsets_mm=[0.0, 0.0],
        special_col_x_offsets_mm=[0.0, 0.0],
        special_row_y_offsets_mm=[0.0, 0.0],
    )
    job = build_job(params, session)
    assert job.special_mode_pattern is not None
    assert job.special_mode_pattern.enabled is True
    assert job.special_mode_pattern.page_width_mm > 0
    assert job.special_mode_pattern.row_offsets_mm == [0.0, 2.0]
    assert job.gap_enabled is True  # tryb specjalny = z odstępami
    assert job.print_page.pdf_path.endswith("__special_print__.pdf")
    assert job.cut_page.pdf_path.endswith("__special_cut__.pdf")


def test_build_job_special_pads_offsets_and_derives_item_size(tmp_path):
    from web.job_builder import JobParams, build_job
    from web.sessions import SessionStore

    store = SessionStore(tmp_path, ttl_seconds=3600)
    session = store.create()
    import fitz
    for name in ("__special_print__.pdf", "__special_cut__.pdf"):
        doc = fitz.open()
        doc.new_page(width=160.0, height=100.0)  # ~56.4 x 35.3 mm
        data = doc.tobytes()
        doc.close()
        store.save_upload(session, name, data)

    params = JobParams(
        print_upload="__special_print__.pdf", print_page=0,
        cut_upload="__special_cut__.pdf", cut_page=0,
        item_w_mm=1.0, item_h_mm=1.0,  # klient — ignorowane w trybie specjalnym
        special_enabled=True,
        special_row_offsets_mm=[1.0, 2.0, 9.0],   # 3 elementy → obcięte do 2
        special_col_offsets_mm=[],                # puste → dopełnione zerami
        special_col_x_offsets_mm=[3.0, 4.0],      # zachowane verbatim
        special_row_y_offsets_mm=[5.0, 6.0],      # zachowane verbatim
    )
    job = build_job(params, session)
    pattern = job.special_mode_pattern
    assert pattern is not None
    assert pattern.row_offsets_mm == [1.0, 2.0]
    assert pattern.col_offsets_mm == [0.0, 0.0]
    assert pattern.col_x_offsets_mm == [3.0, 4.0]
    assert pattern.row_y_offsets_mm == [5.0, 6.0]
    # rozmiar użytku pochodzi z przyciętego PDF (160 pt), NIE z item_w_mm=1.0
    assert job.item_spec.width_mm == pytest.approx(160.0 * MM_PER_POINT, abs=0.1)
    assert job.item_spec.width_mm == pytest.approx(56.4, abs=0.1)


def test_build_job_special_requires_cut_upload(tmp_path):
    from web.job_builder import JobParams, build_job
    from web.sessions import SessionStore
    import fitz, pytest

    store = SessionStore(tmp_path, ttl_seconds=3600)
    session = store.create()
    doc = fitz.open(); doc.new_page(width=100, height=100); data = doc.tobytes(); doc.close()
    store.save_upload(session, "__special_print__.pdf", data)
    params = JobParams(
        print_upload="__special_print__.pdf", print_page=0,
        cut_upload=None, cut_page=None,
        item_w_mm=30, item_h_mm=30,
        special_enabled=True,
    )
    with pytest.raises(ValueError):
        build_job(params, session)
