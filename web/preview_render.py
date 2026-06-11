from __future__ import annotations

import fitz

from summa_cut.export import generate_output_docs
from summa_cut.models import JobSettings, LayoutResult


def render_output_png(job: JobSettings, layout: LayoutResult, which: str = "print", max_px: int = 900) -> bytes:
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
