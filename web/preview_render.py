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
