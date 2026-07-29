from __future__ import annotations

import fitz

from summa_cut.export import generate_output_docs
from summa_cut.models import JobSettings, LayoutResult

PREVIEW_MAX_PX = 900


def render_output_png(job: JobSettings, layout: LayoutResult, which: str = "print", max_px: int = PREVIEW_MAX_PX) -> bytes:
    """Renderuje PRAWDZIWY wynik (druk/wykrojnik) do PNG przez fitz.

    Po Fazie 0 generowanie jest szybkie (~0,24 s @560), więc podgląd = realny
    wynik zrasteryzowany, a nie osobny silnik. Qt-free."""
    if which not in ("print", "cut"):
        raise ValueError(f"Nieznany podgląd: {which!r} (dozwolone: 'print', 'cut').")
    docs = generate_output_docs(job, layout)
    try:
        doc = docs.print_doc if which == "print" else docs.cut_doc
        page = doc[0]
        scale = max_px / max(page.rect.width, page.rect.height, 1.0)
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        return pix.tobytes("png")
    finally:
        docs.print_doc.close()
        docs.cut_doc.close()


def render_special_tile_png(print_pdf_path: str, cut_pdf_path: str, max_px: int = PREVIEW_MAX_PX) -> bytes:
    """Renderuje pojedynczy przygotowany kafel: pełna grafika druku + obrys wykrojnika na wierzchu.

    Używane przez edytor 3×3 trybu specjalnego — front powiela ten obrazek 9×."""
    with fitz.open(print_pdf_path) as pdoc, fitz.open(cut_pdf_path) as cdoc:
        rect = pdoc[0].rect
        out = fitz.open()
        try:
            page = out.new_page(width=rect.width, height=rect.height)
            page.show_pdf_page(page.rect, pdoc, 0)   # druk pod spodem
            page.show_pdf_page(page.rect, cdoc, 0)   # wykrojnik na wierzchu
            scale = max_px / max(rect.width, rect.height, 1.0)
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            return pix.tobytes("png")
        finally:
            out.close()


def render_manual_tile_png(
    print_path: str, print_page: int, print_bbox_pt,
    cut_path: str, cut_page: int, cut_bbox_pt,
    width_mm: float, height_mm: float, rotation_deg: int = 0,
    max_px: int = PREVIEW_MAX_PX,
) -> bytes:
    """Wierny kafel kanwy: kadr W×H strony druku + wykrojnik na wierzchu → PNG.

    Kadr identyczny jak w eksporcie (`_render_cell_stamp` / `_centered_clip_rect_pt`),
    więc podgląd = to, co trafi na arkusz. Tylko do wyświetlania — nie dotyka wyjścia."""
    from summa_cut.export import _centered_clip_rect_pt, _fit_target_rect, mm_to_pt
    cell_w_pt = mm_to_pt(width_mm)
    cell_h_pt = mm_to_pt(height_mm)
    with fitz.open(print_path) as pdoc, fitz.open(cut_path) as cdoc:
        p_clip = _centered_clip_rect_pt(pdoc[print_page].rect, tuple(print_bbox_pt), width_mm, height_mm, rotation_deg)
        c_clip = _centered_clip_rect_pt(cdoc[cut_page].rect, tuple(cut_bbox_pt), width_mm, height_mm, rotation_deg)
        # Cel 1:1 wyśrodkowany w kaflu — spójnie z eksportem, bez rozciągania źródła.
        p_target = _fit_target_rect(p_clip, cell_w_pt, cell_h_pt, rotation_deg)
        c_target = _fit_target_rect(c_clip, cell_w_pt, cell_h_pt, rotation_deg)
        out = fitz.open()
        try:
            page = out.new_page(width=cell_w_pt, height=cell_h_pt)
            page.show_pdf_page(p_target, pdoc, print_page, rotate=rotation_deg, clip=p_clip)
            page.show_pdf_page(c_target, cdoc, cut_page, rotate=rotation_deg, clip=c_clip)
            scale = max_px / max(cell_w_pt, cell_h_pt, 1.0)
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            return pix.tobytes("png")
        finally:
            out.close()
