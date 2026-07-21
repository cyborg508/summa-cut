from __future__ import annotations

from summa_cut.manual_layout import ManualPlacement, build_manual_layout
from summa_cut.models import (
    JobSettings, MontageItem, OposSpec, SelectedPage, SheetSpec, ItemSpec,
)


def _item(w: float, h: float, idx: int) -> MontageItem:
    bbox = (0.0, 0.0, w, h)
    return MontageItem(
        label=f"#{idx}",
        print_page=SelectedPage("a.pdf", 0),
        cut_page=SelectedPage("a.pdf", 1),
        print_page_size_mm=(w, h), cut_page_size_mm=(w, h),
        print_content_size_mm=(w, h), cut_content_size_mm=(w, h),
        print_content_bbox_pt=bbox, cut_content_bbox_pt=bbox,
        quantity=1,
    )


def _job(items: list[MontageItem]) -> JobSettings:
    base = items[0]
    return JobSettings(
        print_page=base.print_page, cut_page=base.cut_page,
        print_page_size_mm=base.print_page_size_mm, cut_page_size_mm=base.cut_page_size_mm,
        print_content_size_mm=base.print_content_size_mm, cut_content_size_mm=base.cut_content_size_mm,
        print_content_bbox_pt=base.print_content_bbox_pt, cut_content_bbox_pt=base.cut_content_bbox_pt,
        sheet_spec=SheetSpec(330, 480), item_spec=ItemSpec(0, 0, False),
        gap_enabled=True, gap_mm=0.0, generate_cut_grid=False,
        montage_items=items, opos_spec=OposSpec(10, 10, 40),
    )


def test_build_manual_layout_maps_positions_and_index():
    job = _job([_item(40, 30, 0), _item(20, 50, 1)])
    placements = [
        ManualPlacement(item_index=0, x_mm=15.0, y_mm=45.0, rotation_deg=0),
        ManualPlacement(item_index=1, x_mm=100.0, y_mm=45.0, rotation_deg=0),
    ]
    layout = build_manual_layout(job, placements)
    assert layout.count == 2
    p0 = layout.placements[0]
    assert (p0.x_mm, p0.y_mm) == (15.0, 45.0)
    assert (p0.width_mm, p0.height_mm) == (40.0, 30.0)
    assert p0.montage_item_index == 0
    assert layout.placements[1].montage_item_index == 1


def test_build_manual_layout_swaps_footprint_for_90_and_270():
    job = _job([_item(40, 30, 0)])
    for rot in (90, 270):
        layout = build_manual_layout(job, [ManualPlacement(0, 10.0, 50.0, rot)])
        p = layout.placements[0]
        assert (p.width_mm, p.height_mm) == (30.0, 40.0)
        assert p.rotation_deg == rot


def test_build_manual_layout_sets_work_area_from_opos():
    job = _job([_item(40, 30, 0)])
    layout = build_manual_layout(job, [])
    wa = layout.work_area_rect
    assert (wa.x_mm, wa.y_mm) == (10.0, 40.0)
    assert wa.width_mm == 330 - 2 * 10
    assert wa.height_mm == 480 - 40 - 10


def test_build_manual_layout_rejects_bad_index():
    import pytest
    job = _job([_item(40, 30, 0)])
    with pytest.raises(ValueError):
        build_manual_layout(job, [ManualPlacement(item_index=5, x_mm=0, y_mm=0, rotation_deg=0)])
