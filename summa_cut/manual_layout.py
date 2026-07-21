from __future__ import annotations

from dataclasses import dataclass

from .models import JobSettings, LayoutResult, Placement, RectMM


@dataclass
class ManualPlacement:
    """Jedna ręcznie ustawiona instancja użytku na arkuszu.

    `item_index` = indeks w `job.montage_items` (= `montage_item_index` placementu).
    `x_mm`/`y_mm` = lewy-GÓRNY róg (spójnie z semantyką `Placement` w eksporcie).
    `rotation_deg` = 0/90/180/270.
    """
    item_index: int
    x_mm: float
    y_mm: float
    rotation_deg: int = 0


def _work_area(job: JobSettings) -> RectMM:
    return RectMM(
        x_mm=job.opos_spec.side_offset_mm,
        y_mm=job.opos_spec.top_offset_mm,
        width_mm=max(job.sheet_spec.width_mm - 2 * job.opos_spec.side_offset_mm, 0.0),
        height_mm=max(
            job.sheet_spec.height_mm - job.opos_spec.top_offset_mm - job.opos_spec.bottom_offset_mm,
            0.0,
        ),
    )


def build_manual_layout(job: JobSettings, placements: list[ManualPlacement]) -> LayoutResult:
    """Składa LayoutResult wprost z ręcznych pozycji (bez auto-nestingu).

    Footprint placementu = rozmiar strony użytku, zamieniony przy 90°/270°."""
    out: list[Placement] = []
    for mp in placements:
        if not (0 <= mp.item_index < len(job.montage_items)):
            raise ValueError(f"Nieprawidłowy indeks użytku: {mp.item_index}")
        w, h = job.montage_items[mp.item_index].print_page_size_mm
        if mp.rotation_deg in (90, 270):
            w, h = h, w
        out.append(Placement(
            x_mm=mp.x_mm, y_mm=mp.y_mm, width_mm=w, height_mm=h,
            rotation_deg=mp.rotation_deg, row=0, column=0, group=0,
            montage_item_index=mp.item_index,
        ))
    return LayoutResult(
        placements=out,
        count=len(out),
        requested_count=len(out),
        work_area_rect=_work_area(job),
        sheet_rect=RectMM(0.0, 0.0, job.sheet_spec.width_mm, job.sheet_spec.height_mm),
    )


_EPS = 0.01  # mm — tolerancja na błąd zmiennoprzecinkowy


def _rects_overlap(a: Placement, b: Placement) -> bool:
    return (
        a.x_mm < b.x_mm + b.width_mm - _EPS
        and b.x_mm < a.x_mm + a.width_mm - _EPS
        and a.y_mm < b.y_mm + b.height_mm - _EPS
        and b.y_mm < a.y_mm + a.height_mm - _EPS
    )


def validate_manual_placements(job: JobSettings, layout: LayoutResult) -> list[str]:
    """Zwraca listę problemów (pustą, gdy układ jest poprawny).

    Reguły: każda instancja w obszarze roboczym OPOS; brak nachodzenia."""
    problems: list[str] = []
    wa = layout.work_area_rect
    for i, p in enumerate(layout.placements, start=1):
        if (
            p.x_mm < wa.x_mm - _EPS
            or p.y_mm < wa.y_mm - _EPS
            or p.x_mm + p.width_mm > wa.x_mm + wa.width_mm + _EPS
            or p.y_mm + p.height_mm > wa.y_mm + wa.height_mm + _EPS
        ):
            problems.append(f"Element #{i} wychodzi poza obszar OPOS.")
    placements = layout.placements
    for i in range(len(placements)):
        for j in range(i + 1, len(placements)):
            if _rects_overlap(placements[i], placements[j]):
                problems.append(f"Elementy #{i + 1} i #{j + 1} nachodzą na siebie.")
    return problems
