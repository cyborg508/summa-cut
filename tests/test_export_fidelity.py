"""Golden-image: po porcie na pikepdf render wyniku nie może się zmienić."""
from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from summa_cut import export as E
from summa_cut.layout import compute_layout
from summa_cut.models import ItemSpec, JobSettings, SelectedPage, SheetSpec
from summa_cut.pdf_io import MM_PER_POINT
from tests.render_util import render_page_png, fraction_differing

PT = 1.0 / MM_PER_POINT
FIX = Path(__file__).parent / "fixtures"
TOLERANCE = 0.01  # max 1% pikseli może się różnić (kodowanie/antyaliasing)


@pytest.fixture()
def source_pdf(tmp_path: Path) -> str:
    side = 40 * PT
    doc = fitz.open()
    page = doc.new_page(width=side, height=side)
    page.draw_rect(fitz.Rect(3, 3, side - 3, side - 3), color=(0, 0, 1), width=1.5)
    page.draw_circle(fitz.Point(side / 2, side / 2), side / 4, color=(1, 0, 0), width=1.2)
    path = tmp_path / "src.pdf"
    doc.save(path)
    doc.close()
    return str(path)


def _job(source: str, *, gap_enabled: bool, item: float = 30.0) -> JobSettings:
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


def _assert_matches_golden(doc: fitz.Document, name: str):
    png = render_page_png(doc)
    golden_path = FIX / name
    if not golden_path.exists():
        golden_path.parent.mkdir(parents=True, exist_ok=True)
        golden_path.write_bytes(png)
        pytest.skip(f"zapisano nowy golden {name} — uruchom ponownie i zacommituj")
    frac = fraction_differing(golden_path.read_bytes(), png)
    assert frac <= TOLERANCE, f"{name}: {frac:.4f} pikseli różne (>{TOLERANCE})"


def test_fidelity_grid_with_gap(source_pdf):
    job = _job(source_pdf, gap_enabled=True)
    docs = E.generate_output_docs(job, compute_layout(job))
    try:
        _assert_matches_golden(docs.print_doc, "golden_print_grid.png")
        _assert_matches_golden(docs.cut_doc, "golden_cut_grid.png")
    finally:
        docs.print_doc.close(); docs.cut_doc.close()


def test_fidelity_gapless(source_pdf):
    job = _job(source_pdf, gap_enabled=False)
    docs = E.generate_output_docs(job, compute_layout(job))
    try:
        _assert_matches_golden(docs.print_doc, "golden_print_gapless.png")
        _assert_matches_golden(docs.cut_doc, "golden_cut_gapless.png")
    finally:
        docs.print_doc.close(); docs.cut_doc.close()
