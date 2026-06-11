from __future__ import annotations

from pydantic import BaseModel, Field

from summa_cut.models import ItemSpec, JobSettings, MontageItem, OposSpec, SelectedPage, SheetSpec, SpecialModePattern
from web.sessions import Session


class MontageItemParams(BaseModel):
    label: str = ""
    print_upload: str
    print_page: int = 0
    cut_upload: str
    cut_page: int = 0
    quantity: int = 1


class JobParams(BaseModel):
    """Parametry zlecenia. `montage` niepuste → montaż wielu użytków; puste → pojedynczy produkt."""
    print_upload: str
    print_page: int = 0
    cut_upload: str | None = None
    cut_page: int | None = None

    sheet_w_mm: float = 330.0
    sheet_h_mm: float = 480.0
    item_w_mm: float
    item_h_mm: float
    rotation_allowed: bool = False

    gap_enabled: bool = True
    gap_mm: float = 3.0

    split_horizontal_groups: bool = False
    split_max_spread: bool = False
    manual_grid_enabled: bool = False
    manual_columns: int = 0
    manual_rows: int = 0

    opos_side_offset_mm: float = Field(default=10.0)
    opos_bottom_offset_mm: float = Field(default=10.0)
    opos_top_offset_mm: float = Field(default=40.0)

    montage: list[MontageItemParams] = Field(default_factory=list)

    special_enabled: bool = False
    special_page_w_mm: float = 0.0
    special_page_h_mm: float = 0.0
    special_row_offsets_mm: list[float] = Field(default_factory=lambda: [0.0, 0.0])
    special_col_offsets_mm: list[float] = Field(default_factory=lambda: [0.0, 0.0])
    special_col_x_offsets_mm: list[float] = Field(default_factory=lambda: [0.0, 0.0])
    special_row_y_offsets_mm: list[float] = Field(default_factory=lambda: [0.0, 0.0])


def _require_page(session: Session, upload: str, page_index: int, what: str):
    info = session.uploads.get(upload)
    if info is None:
        raise ValueError(f"Nie wgrano pliku: {upload} ({what}).")
    if page_index < 0 or page_index >= info.page_count:
        raise ValueError(f"Strona {page_index} poza zakresem pliku {upload} ({what}).")
    return info


def _build_montage_items(params: JobParams, session: Session) -> list[MontageItem]:
    items: list[MontageItem] = []
    for idx, m in enumerate(params.montage):
        if m.quantity < 1:
            raise ValueError(f"Ilość użytku #{idx + 1} musi być >= 1.")
        p_info = _require_page(session, m.print_upload, m.print_page, f"druk montażu #{idx + 1}")
        c_info = _require_page(session, m.cut_upload, m.cut_page, f"wykrojnik montażu #{idx + 1}")
        items.append(MontageItem(
            label=m.label or f"#{idx + 1}",
            print_page=SelectedPage(p_info.path, m.print_page),
            cut_page=SelectedPage(c_info.path, m.cut_page),
            print_page_size_mm=p_info.page_sizes_mm[m.print_page],
            cut_page_size_mm=c_info.page_sizes_mm[m.cut_page],
            print_content_size_mm=p_info.page_content_sizes_mm[m.print_page],
            cut_content_size_mm=c_info.page_content_sizes_mm[m.cut_page],
            print_content_bbox_pt=p_info.page_content_boxes_pt[m.print_page],
            cut_content_bbox_pt=c_info.page_content_boxes_pt[m.cut_page],
            quantity=m.quantity,
        ))
    return items


def _pad2(values: list[float]) -> list[float]:
    out = list(values[:2]) if values else [0.0, 0.0]
    while len(out) < 2:
        out.append(0.0)
    return out


def _build_special_job(params: JobParams, session: Session) -> JobSettings:
    if not params.cut_upload or params.cut_page is None:
        raise ValueError("Tryb specjalny: najpierw przygotuj wykrojnik (/api/special/prepare).")
    print_info = _require_page(session, params.print_upload, params.print_page, "druk (tryb specjalny)")
    cut_info = _require_page(session, params.cut_upload, params.cut_page, "wykrojnik (tryb specjalny)")

    page_w_mm, page_h_mm = print_info.page_sizes_mm[params.print_page]
    print_page = SelectedPage(print_info.path, params.print_page)
    cut_page = SelectedPage(cut_info.path, params.cut_page)

    pattern = SpecialModePattern(
        enabled=True,
        print_pdf_path=print_info.path,
        cut_pdf_path=cut_info.path,
        page_width_mm=page_w_mm,
        page_height_mm=page_h_mm,
        row_offsets_mm=_pad2(params.special_row_offsets_mm),
        col_offsets_mm=_pad2(params.special_col_offsets_mm),
        col_x_offsets_mm=_pad2(params.special_col_x_offsets_mm),
        row_y_offsets_mm=_pad2(params.special_row_y_offsets_mm),
    )
    return JobSettings(
        print_page=print_page,
        cut_page=cut_page,
        print_page_size_mm=print_info.page_sizes_mm[params.print_page],
        cut_page_size_mm=cut_info.page_sizes_mm[params.cut_page],
        print_content_size_mm=print_info.page_content_sizes_mm[params.print_page],
        cut_content_size_mm=cut_info.page_content_sizes_mm[params.cut_page],
        print_content_bbox_pt=print_info.page_content_boxes_pt[params.print_page],
        cut_content_bbox_pt=cut_info.page_content_boxes_pt[params.cut_page],
        sheet_spec=SheetSpec(params.sheet_w_mm, params.sheet_h_mm),
        item_spec=ItemSpec(page_w_mm, page_h_mm, False),
        gap_enabled=True,
        gap_mm=0.0,
        generate_cut_grid=False,
        montage_items=[],
        opos_spec=OposSpec(params.opos_side_offset_mm, params.opos_bottom_offset_mm, params.opos_top_offset_mm),
        special_mode_pattern=pattern,
    )


def build_job(params: JobParams, session: Session) -> JobSettings:
    if params.item_w_mm <= 0 or params.item_h_mm <= 0:
        raise ValueError("Rozmiar użytku musi być większy od zera.")
    if params.sheet_w_mm <= 0 or params.sheet_h_mm <= 0:
        raise ValueError("Rozmiar arkusza musi być większy od zera.")

    if params.special_enabled:
        return _build_special_job(params, session)

    with_gap = params.gap_enabled
    montage_items = _build_montage_items(params, session) if params.montage else []

    if montage_items and not with_gap:
        # Każdy użytek montażu ma własny wykrojnik; tryb bez odstępów rysowałby
        # generowaną kratę i ignorował te wykrojniki. Desktop wymusza tu tryb z
        # odstępami — API odrzuca jawnie, zamiast po cichu pomijać dane.
        raise ValueError("Montaż wymaga trybu z odstępami (każdy użytek ma własny wykrojnik).")

    if montage_items:
        base = montage_items[0]
        print_page = base.print_page
        cut_page = base.cut_page
        print_page_size_mm = base.print_page_size_mm
        cut_page_size_mm = base.cut_page_size_mm
        print_content_size_mm = base.print_content_size_mm
        cut_content_size_mm = base.cut_content_size_mm
        print_content_bbox_pt = base.print_content_bbox_pt
        cut_content_bbox_pt = base.cut_content_bbox_pt
    else:
        print_info = _require_page(session, params.print_upload, params.print_page, "druk")
        if with_gap:
            if not params.cut_upload or params.cut_page is None:
                raise ValueError("W trybie z odstępami wybierz też plik i stronę wykrojnika.")
            cut_upload, cut_page_index = params.cut_upload, params.cut_page
        else:
            cut_upload, cut_page_index = params.print_upload, params.print_page
        cut_info = _require_page(session, cut_upload, cut_page_index, "wykrojnik")
        print_page = SelectedPage(print_info.path, params.print_page)
        cut_page = SelectedPage(cut_info.path, cut_page_index)
        print_page_size_mm = print_info.page_sizes_mm[params.print_page]
        cut_page_size_mm = cut_info.page_sizes_mm[cut_page_index]
        print_content_size_mm = print_info.page_content_sizes_mm[params.print_page]
        cut_content_size_mm = cut_info.page_content_sizes_mm[cut_page_index]
        print_content_bbox_pt = print_info.page_content_boxes_pt[params.print_page]
        cut_content_bbox_pt = cut_info.page_content_boxes_pt[cut_page_index]

    if params.manual_grid_enabled:
        if params.manual_columns <= 0 or params.manual_rows <= 0:
            raise ValueError("W trybie manualnym liczba kolumn i rzędów musi być większa od zera.")
        if params.split_horizontal_groups and params.manual_rows % 2 == 1:
            raise ValueError("Przy podziale na 2 grupy manualna liczba rzędów musi być parzysta.")

    return JobSettings(
        print_page=print_page,
        cut_page=cut_page,
        print_page_size_mm=print_page_size_mm,
        cut_page_size_mm=cut_page_size_mm,
        print_content_size_mm=print_content_size_mm,
        cut_content_size_mm=cut_content_size_mm,
        print_content_bbox_pt=print_content_bbox_pt,
        cut_content_bbox_pt=cut_content_bbox_pt,
        sheet_spec=SheetSpec(params.sheet_w_mm, params.sheet_h_mm),
        item_spec=ItemSpec(params.item_w_mm, params.item_h_mm, params.rotation_allowed),
        gap_enabled=with_gap,
        gap_mm=params.gap_mm if with_gap else 0.0,
        generate_cut_grid=not with_gap,
        split_horizontal_groups=params.split_horizontal_groups,
        split_max_spread=params.split_horizontal_groups and params.split_max_spread,
        manual_grid_enabled=params.manual_grid_enabled,
        manual_columns=params.manual_columns,
        manual_rows=params.manual_rows,
        montage_items=montage_items,
        opos_spec=OposSpec(params.opos_side_offset_mm, params.opos_bottom_offset_mm, params.opos_top_offset_mm),
    )
