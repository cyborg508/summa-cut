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


def test_centered_clip_swaps_dims_for_270():
    import fitz
    from summa_cut.export import _centered_clip_rect_pt, mm_to_pt
    page_rect = fitz.Rect(0, 0, mm_to_pt(100), mm_to_pt(100))
    content_bbox = (0.0, 0.0, mm_to_pt(100), mm_to_pt(100))
    # clip 30 (szer.) x 10 (wys.) mm; przy 90 i 270 footprint jest obrócony,
    # więc okno przycięcia musi mieć 10 (szer.) x 30 (wys.) mm.
    r90 = _centered_clip_rect_pt(page_rect, content_bbox, 30.0, 10.0, 90)
    r270 = _centered_clip_rect_pt(page_rect, content_bbox, 30.0, 10.0, 270)
    assert round(r270.width, 3) == round(r90.width, 3)
    assert round(r270.height, 3) == round(r90.height, 3)
    assert round(r270.width, 1) == round(mm_to_pt(10.0), 1)
    assert round(r270.height, 1) == round(mm_to_pt(30.0), 1)


def _stamp_content_size_mm(stamp_bytes: bytes) -> tuple[float, float]:
    """Rozmiar (mm) bboxa narysowanej treści w gotowym stemplu."""
    from summa_cut.export import mm_to_pt
    doc = fitz.open("pdf", stamp_bytes)
    page = doc[0]
    rects = [fitz.Rect(b) for _k, b in page.get_bboxlog() if fitz.Rect(b).width > 0 and fitz.Rect(b).height > 0]
    content = fitz.Rect(rects[0])
    for r in rects[1:]:
        content |= r
    content &= page.rect
    unit = mm_to_pt(1.0)
    return content.width / unit, content.height / unit


def test_stamp_does_not_stretch_source_when_cell_larger_than_page():
    """Kafel większy od strony źródła NIE może rozciągać druku.

    Regresja: w trybie manualnym footprint = rozmiar_druku + 3mm marginesu
    (DIE_MARGIN), więc kafel 46x46 dla strony 40x40 rozdmuchiwał druk zamiast
    zostawić margines. Druk ma lądować 1:1, wyśrodkowany."""
    from summa_cut.export import _render_cell_stamp, mm_to_pt
    side = mm_to_pt(40)
    src = fitz.open()
    page = src.new_page(width=side, height=side)
    # obrys tuż przy krawędzi → content bbox ≈ pełna strona 40x40 mm
    page.draw_rect(fitz.Rect(1, 1, side - 1, side - 1), color=(0, 0, 1), width=1.0)
    content_bbox = (0.0, 0.0, side, side)

    # kafel 46x46 mm (strona 40 + 3mm marginesu z każdej strony)
    stamp, _ = _render_cell_stamp(src, 0, content_bbox, 46.0, 46.0, 0, False)
    w_mm, h_mm = _stamp_content_size_mm(stamp)

    # druk ma zostać w skali 1:1 (~40mm), NIE rozdmuchany do ~46mm
    assert w_mm == pytest.approx(40.0, abs=1.5), f"druk rozciągnięty w poziomie: {w_mm:.2f} mm"
    assert h_mm == pytest.approx(40.0, abs=1.5), f"druk rozciągnięty w pionie: {h_mm:.2f} mm"


# --- Tryb bez odstępów: spad na zewnątrz bloku -------------------------------

def _bleed_source(tmp_path: Path, w_mm: float, h_mm: float) -> str:
    """Strona w×h cała czerwona (tło ze spadem) z niebieskim kwadratem 4 mm w środku."""
    doc = fitz.open()
    page = doc.new_page(width=w_mm * PT, height=h_mm * PT)
    page.draw_rect(page.rect, color=None, fill=(1, 0, 0))
    cx, cy = page.rect.width / 2, page.rect.height / 2
    page.draw_rect(fitz.Rect(cx - 2 * PT, cy - 2 * PT, cx + 2 * PT, cy + 2 * PT), color=None, fill=(0, 0, 1))
    path = tmp_path / f"bleed_{w_mm}x{h_mm}.pdf"
    doc.save(path)
    doc.close()
    return str(path)


def _gapless_job(source: str, page_mm: tuple[float, float], item_mm: tuple[float, float],
                 forced_rotation: int | None = None) -> JobSettings:
    w_pt, h_pt = page_mm[0] * PT, page_mm[1] * PT
    bbox = (0.0, 0.0, w_pt, h_pt)
    return JobSettings(
        print_page=SelectedPage(source, 0), cut_page=SelectedPage(source, 0),
        print_page_size_mm=page_mm, cut_page_size_mm=page_mm,
        print_content_size_mm=page_mm, cut_content_size_mm=page_mm,
        print_content_bbox_pt=bbox, cut_content_bbox_pt=bbox,
        sheet_spec=SheetSpec(330, 480),
        item_spec=ItemSpec(item_mm[0], item_mm[1], forced_rotation is not None,
                           forced_rotation_deg=forced_rotation),
        gap_enabled=False, gap_mm=0.0, generate_cut_grid=True,
    )


def _px(pix: fitz.Pixmap, x_mm: float, y_mm: float, dpi: int) -> tuple:
    s = dpi / 25.4
    return pix.pixel(int(round(x_mm * s)), int(round(y_mm * s)))


RED, BLUE, WHITE = (255, 0, 0), (0, 0, 255), (255, 255, 255)


@pytest.mark.parametrize("forced_rotation,item_mm", [(None, (30.0, 30.0)), (90, (30.0, 20.0))])
def test_gapless_print_has_outer_bleed_only(tmp_path, forced_rotation, item_mm):
    """Bez odstępów skrajne użytki dostają 1 mm spadu TYLKO na zewnątrz bloku;
    w środku bloku grafika dalej przycięta 1:1, a środek użytku na środku kafla
    (także przy obrocie 90°)."""
    page_mm = (item_mm[0] + 6, item_mm[1] + 6)  # plik ma 3 mm spadu z każdej strony
    src = _bleed_source(tmp_path, *page_mm)
    job = _gapless_job(src, page_mm, item_mm, forced_rotation)
    layout = compute_layout(job)
    assert layout.count >= 4
    if forced_rotation:
        assert all(p.rotation_deg == 90 for p in layout.placements)
    xs0 = min(p.x_mm for p in layout.placements)
    ys0 = min(p.y_mm for p in layout.placements)
    xs1 = max(p.x_mm + p.width_mm for p in layout.placements)
    ys1 = max(p.y_mm + p.height_mm for p in layout.placements)
    dpi = 150
    docs = E.generate_output_docs(job, layout)
    try:
        pix = docs.print_doc[0].get_pixmap(dpi=dpi)
    finally:
        docs.print_doc.close()
        docs.cut_doc.close()
    midy = (ys0 + ys1) / 2
    midx = (xs0 + xs1) / 2
    # 0,5 mm na zewnątrz każdej krawędzi bloku = spad (czerwony)
    assert _px(pix, xs0 - 0.5, midy, dpi) == RED
    assert _px(pix, xs1 + 0.5, midy, dpi) == RED
    assert _px(pix, midx, ys0 - 0.5, dpi) == RED
    assert _px(pix, midx, ys1 + 0.5, dpi) == RED
    # 2 mm na zewnątrz = już nic (spad tylko 1 mm)
    assert _px(pix, xs0 - 2, midy, dpi) == WHITE
    assert _px(pix, xs1 + 2, midy, dpi) == WHITE
    # każdy użytek: niebieski środek dokładnie na środku kafla
    for p in layout.placements:
        assert _px(pix, p.x_mm + p.width_mm / 2, p.y_mm + p.height_mm / 2, dpi) == BLUE
        assert _px(pix, p.x_mm + p.width_mm / 2 + 2.6, p.y_mm + p.height_mm / 2, dpi) == RED


def test_gap_mode_print_has_no_bleed(tmp_path):
    """Tryb z odstępami bez zmian — żadnego spadu poza kaflem."""
    src = _bleed_source(tmp_path, 36, 36)
    job = _gapless_job(src, (36, 36), (30, 30))
    job.gap_enabled, job.gap_mm, job.generate_cut_grid = True, 3.0, False
    layout = compute_layout(job)
    p = layout.placements[0]
    dpi = 150
    docs = E.generate_output_docs(job, layout)
    try:
        pix = docs.print_doc[0].get_pixmap(dpi=dpi)
    finally:
        docs.print_doc.close()
        docs.cut_doc.close()
    assert _px(pix, p.x_mm - 0.5, p.y_mm + p.height_mm / 2, dpi) == WHITE
