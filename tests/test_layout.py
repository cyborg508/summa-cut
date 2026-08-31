"""Testy logiki układania (czysta geometria, bez PDF/Qt)."""
from __future__ import annotations

from summa_cut.layout import compute_layout
from summa_cut.models import ItemSpec, JobSettings, SelectedPage, SheetSpec


def _job(**over) -> JobSettings:
    base = dict(
        print_page=SelectedPage("x", 0), cut_page=SelectedPage("x", 0),
        print_page_size_mm=(50, 50), cut_page_size_mm=(50, 50),
        print_content_size_mm=(50, 50), cut_content_size_mm=(50, 50),
        print_content_bbox_pt=(0, 0, 100, 100), cut_content_bbox_pt=(0, 0, 100, 100),
        sheet_spec=SheetSpec(330, 480), item_spec=ItemSpec(50, 50, False),
        gap_enabled=True, gap_mm=3.0,
    )
    base.update(over)
    return JobSettings(**base)


def test_basic_grid_count():
    # work_area = 310 x 430 (OPOS 10 boki/dół, 40 góra); kafel 53 → 5 x 8
    res = compute_layout(_job())
    assert (res.columns, res.rows, res.count) == (5, 8, 40)
    assert res.work_area_rect.width_mm == 310.0
    assert res.work_area_rect.height_mm == 430.0


def test_gapless_packs_more():
    with_gap = compute_layout(_job(gap_enabled=True, gap_mm=3.0)).count
    without_gap = compute_layout(_job(gap_enabled=False)).count
    assert without_gap > with_gap


def test_rotation_picks_better_orientation():
    # użytek 100x40: w 310x430 obrót może dać inną (lepszą) liczbę
    no_rot = compute_layout(_job(item_spec=ItemSpec(100, 40, False)))
    rot = compute_layout(_job(item_spec=ItemSpec(100, 40, True)))
    assert rot.count >= no_rot.count


def test_manual_grid_respects_requested_dims():
    res = compute_layout(_job(manual_grid_enabled=True, manual_columns=3, manual_rows=4))
    assert res.columns == 3 and res.rows == 4 and res.count == 12


def test_too_big_item_yields_nothing():
    res = compute_layout(_job(item_spec=ItemSpec(1000, 1000, False)))
    assert res.count == 0


def test_split_groups_even_rows_two_groups():
    res = compute_layout(_job(item_spec=ItemSpec(50, 50, False), split_horizontal_groups=True))
    # rzędy dzielone na 2 równe grupy (parzysta liczba); grupy oznaczone 0/1
    groups = {p.group for p in res.placements}
    assert groups == {0, 1}
    assert res.rows % 2 == 0


# --- wymuszona orientacja (forced_rotation_deg) ---

def test_forced_90_wins_even_when_0_packs_more():
    # użytek 100x40 w polu 310x430, gap 3 → 0°: 3x10=30, 90°: 7x4=28
    auto = compute_layout(_job(item_spec=ItemSpec(100, 40, True)))
    assert (auto.count, auto.used_rotation) == (30, False)

    forced = compute_layout(_job(item_spec=ItemSpec(100, 40, True, forced_rotation_deg=90)))
    assert (forced.count, forced.used_rotation) == (28, True)
    assert all(p.rotation_deg == 90 for p in forced.placements)


def test_forced_0_ignores_better_rotated_variant():
    # użytek 40x100 → 0°: 7x4=28, 90°: 3x10=30 (auto wybierze 90°)
    auto = compute_layout(_job(item_spec=ItemSpec(40, 100, True)))
    assert (auto.count, auto.used_rotation) == (30, True)

    forced = compute_layout(_job(item_spec=ItemSpec(40, 100, True, forced_rotation_deg=0)))
    assert (forced.count, forced.used_rotation) == (28, False)
    assert all(p.rotation_deg == 0 for p in forced.placements)


def test_forced_90_applies_to_square_item():
    # kwadrat: obrót nie zmienia upakowania, ale grafika w środku może nie być symetryczna
    forced = compute_layout(_job(item_spec=ItemSpec(50, 50, False, forced_rotation_deg=90)))
    assert forced.count == 40
    assert forced.used_rotation is True
    assert all(p.rotation_deg == 90 for p in forced.placements)


def test_forced_orientation_that_does_not_fit_yields_nothing():
    # użytek 40x420 mieści się na leżąco (7x1), po wymuszeniu 90° szerokość 423 > 310
    auto = compute_layout(_job(item_spec=ItemSpec(40, 420, True)))
    assert auto.count == 7

    forced = compute_layout(_job(item_spec=ItemSpec(40, 420, True, forced_rotation_deg=90)))
    assert forced.count == 0
    assert forced.placements == []
