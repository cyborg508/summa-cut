from __future__ import annotations

from pydantic import BaseModel, Field

from summa_cut.models import ItemSpec, JobSettings, OposSpec, SelectedPage, SheetSpec
from web.sessions import Session


class JobParams(BaseModel):
    """Parametry zlecenia (pojedynczy produkt). Montaż/tryb specjalny — później."""
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


def _require_page(session: Session, upload: str, page_index: int, what: str):
    info = session.uploads.get(upload)
    if info is None:
        raise ValueError(f"Nie wgrano pliku: {upload} ({what}).")
    if page_index < 0 or page_index >= info.page_count:
        raise ValueError(f"Strona {page_index} poza zakresem pliku {upload} ({what}).")
    return info


def build_job(params: JobParams, session: Session) -> JobSettings:
    if params.item_w_mm <= 0 or params.item_h_mm <= 0:
        raise ValueError("Rozmiar użytku musi być większy od zera.")
    if params.sheet_w_mm <= 0 or params.sheet_h_mm <= 0:
        raise ValueError("Rozmiar arkusza musi być większy od zera.")

    with_gap = params.gap_enabled
    print_info = _require_page(session, params.print_upload, params.print_page, "druk")

    if with_gap:
        if not params.cut_upload or params.cut_page is None:
            raise ValueError("W trybie z odstępami wybierz też plik i stronę wykrojnika.")
        cut_upload, cut_page_index = params.cut_upload, params.cut_page
    else:
        cut_upload, cut_page_index = params.print_upload, params.print_page
    cut_info = _require_page(session, cut_upload, cut_page_index, "wykrojnik")

    if params.manual_grid_enabled:
        if params.manual_columns <= 0 or params.manual_rows <= 0:
            raise ValueError("W trybie manualnym liczba kolumn i rzędów musi być większa od zera.")
        if params.split_horizontal_groups and params.manual_rows % 2 == 1:
            raise ValueError("Przy podziale na 2 grupy manualna liczba rzędów musi być parzysta.")

    return JobSettings(
        print_page=SelectedPage(print_info.path, params.print_page),
        cut_page=SelectedPage(cut_info.path, cut_page_index),
        print_page_size_mm=print_info.page_sizes_mm[params.print_page],
        cut_page_size_mm=cut_info.page_sizes_mm[cut_page_index],
        print_content_size_mm=print_info.page_content_sizes_mm[params.print_page],
        cut_content_size_mm=cut_info.page_content_sizes_mm[cut_page_index],
        print_content_bbox_pt=print_info.page_content_boxes_pt[params.print_page],
        cut_content_bbox_pt=cut_info.page_content_boxes_pt[cut_page_index],
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
        opos_spec=OposSpec(params.opos_side_offset_mm, params.opos_bottom_offset_mm, params.opos_top_offset_mm),
    )
