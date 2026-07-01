"""Testy eksportu — poprawność + gwarancja, że źródło otwierane jest raz.

Nie wymagają Qt (tylko PyMuPDF). Chronią refaktor wydajności (cache źródła)
przed regresją: liczba użytków nie może mnożyć otwarć pliku źródłowego.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import fitz
import pikepdf
import pytest

from summa_cut import export as E
from summa_cut.pdf_io import MM_PER_POINT
from summa_cut.layout import compute_layout
from summa_cut.models import ItemSpec, JobSettings, SelectedPage, SheetSpec

PT = 1.0 / MM_PER_POINT


@pytest.fixture()
def source_pdf(tmp_path: Path) -> str:
    side = 40 * PT
    doc = fitz.open()
    page = doc.new_page(width=side, height=side)
    page.draw_rect(fitz.Rect(3, 3, side - 3, side - 3), color=(0, 0, 1), width=1.5)
    path = tmp_path / "src.pdf"
    doc.save(path)
    doc.close()
    return str(path)


def _job(source: str, *, gap_enabled: bool = True, item: float = 30.0) -> JobSettings:
    side = 40 * PT
    bbox = (0.0, 0.0, side, side)
    return JobSettings(
        print_page=SelectedPage(source, 0),
        cut_page=SelectedPage(source, 0),
        print_page_size_mm=(40, 40), cut_page_size_mm=(40, 40),
        print_content_size_mm=(40, 40), cut_content_size_mm=(40, 40),
        print_content_bbox_pt=bbox, cut_content_bbox_pt=bbox,
        sheet_spec=SheetSpec(330, 480), item_spec=ItemSpec(item, item, False),
        gap_enabled=gap_enabled, gap_mm=3.0, generate_cut_grid=not gap_enabled,
    )


def test_source_opened_once_regardless_of_placement_count(source_pdf, monkeypatch):
    job = _job(source_pdf, item=30.0)
    layout = compute_layout(job)
    assert layout.count > 50  # dużo użytków → kiedyś = dużo otwarć

    real_open = fitz.open
    opens: list = []

    def spy(*args, **kwargs):
        opens.append(args[0] if args else None)
        return real_open(*args, **kwargs)

    monkeypatch.setattr(fitz, "open", spy)
    docs = E.generate_output_docs(job, layout)
    try:
        source_opens = sum(1 for a in opens if a == source_pdf)
        # druk i wykrojnik z tego samego pliku → otwierany najwyżej raz
        assert source_opens == 1, f"źródło otwarte {source_opens}x (regresja cache)"
    finally:
        docs.print_doc.close()
        docs.cut_doc.close()


def test_output_has_single_page_each(source_pdf):
    job = _job(source_pdf)
    docs = E.generate_output_docs(job, compute_layout(job))
    try:
        assert docs.print_doc.page_count == 1
        assert docs.cut_doc.page_count == 1
    finally:
        docs.print_doc.close()
        docs.cut_doc.close()


def test_save_writes_both_pdfs(source_pdf, tmp_path):
    job = _job(source_pdf)
    docs = E.generate_output_docs(job, compute_layout(job))
    try:
        out = tmp_path / "out"
        print_path, cut_path = E.save_output_docs(docs, out, base_name="moj_plik")
    finally:
        docs.print_doc.close()
        docs.cut_doc.close()
    assert print_path.name == "moj_plik_druk.pdf"
    assert cut_path.name == "moj_plik_wykrojnik.pdf"
    assert print_path.stat().st_size > 1000 and cut_path.stat().st_size > 1000


def _page_xobject_count(pdf_path: Path) -> int:
    with pikepdf.open(pdf_path) as pdf:
        page = pdf.pages[0]
        res = page.Resources
        if "/XObject" not in res:
            return 0
        return len(list(res.XObject.keys()))


@pytest.mark.skipif(shutil.which("gs") is None, reason="Ghostscript (gs) niedostępny")
def test_saved_cut_pdf_is_flattened_no_form_xobjects(source_pdf, tmp_path):
    """Wykrojnik zapisany na dysk musi mieć kontury jako natywne ścieżki
    (0 Form XObjectów) — inaczej SummaWinPlot przesuwa je względem OPOS.

    Druk zostaje z XObjectami (idzie na drukarkę) — nie sprawdzamy go tu.
    """
    job = _job(source_pdf, item=30.0)
    layout = compute_layout(job)
    assert layout.count > 50  # wiele użytków = wiele stempli XObject przed spłaszczeniem
    docs = E.generate_output_docs(job, layout)
    try:
        _, cut_path = E.save_output_docs(docs, tmp_path / "out", base_name="plik")
    finally:
        docs.print_doc.close()
        docs.cut_doc.close()
    assert _page_xobject_count(cut_path) == 0, "wykrojnik nie został spłaszczony (są Form XObjecty)"


@pytest.mark.skipif(shutil.which("gs") is None, reason="Ghostscript (gs) niedostępny")
def test_flattened_cut_is_visually_equal_to_unflattened(source_pdf, tmp_path):
    """Spłaszczenie nie może zmienić geometrii — render spłaszczonego wykrojnika
    musi się pokrywać z renderem przed spłaszczeniem (kontury + OPOS na miejscu)."""
    from render_util import fraction_differing, render_page_png

    job = _job(source_pdf, item=30.0)
    layout = compute_layout(job)
    docs = E.generate_output_docs(job, layout)
    try:
        before = render_page_png(docs.cut_doc)
        _, cut_path = E.save_output_docs(docs, tmp_path / "out", base_name="plik")
    finally:
        docs.print_doc.close()
        docs.cut_doc.close()
    with fitz.open(cut_path) as flat:
        after = render_page_png(flat)
    assert fraction_differing(before, after) < 0.01


def test_gapless_mode_does_not_open_cut_source(source_pdf, monkeypatch):
    # bez odstępów wykrojnik jest generowaną kratą — nie wkłada PDF wykrojnika
    job = _job(source_pdf, gap_enabled=False)
    layout = compute_layout(job)
    real_open = fitz.open
    opens: list = []
    monkeypatch.setattr(fitz, "open", lambda *a, **k: (opens.append(a[0] if a else None), real_open(*a, **k))[1])
    docs = E.generate_output_docs(job, layout)
    try:
        # tylko druk korzysta ze źródła → wciąż dokładnie 1 otwarcie pliku
        assert sum(1 for a in opens if a == source_pdf) == 1
    finally:
        docs.print_doc.close()
        docs.cut_doc.close()
