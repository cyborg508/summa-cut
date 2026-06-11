from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from summa_cut.special_trim import (
    drawings_to_polygons,
    extract_cut_outline,
    expand_outline,
    prepare_special_trim,
)

POINTS_PER_MM = 72.0 / 25.4


def _make_source_pdf(path: Path) -> None:
    """Strona A6-ish z wektorowym prostokątnym obrysem 'wykrojnika' (50x30 pt @ (20,20))
    oraz wypełnieniem 'druku' wewnątrz, na obu stronach identycznie."""
    doc = fitz.open()
    page = doc.new_page(width=120.0, height=100.0)
    # druk: szare wypełnienie
    page.draw_rect(fitz.Rect(20, 20, 70, 50), color=(0, 0, 0), fill=(0.6, 0.6, 0.6), width=0.0)
    # wykrojnik: wektorowy obrys (kreska)
    page.draw_rect(fitz.Rect(20, 20, 70, 50), color=(1, 0, 0), width=0.5)
    doc.save(str(path))
    doc.close()


def test_drawings_to_polygons_finds_rect(tmp_path: Path):
    src = tmp_path / "src.pdf"
    _make_source_pdf(src)
    doc = fitz.open(str(src))
    try:
        polys = drawings_to_polygons(doc[0])
    finally:
        doc.close()
    assert polys, "powinien być co najmniej jeden wielokąt"
    xs = [x for poly in polys for x, _ in poly]
    ys = [y for poly in polys for _, y in poly]
    assert min(xs) == pytest.approx(20.0, abs=1.0)
    assert max(xs) == pytest.approx(70.0, abs=1.0)
    assert min(ys) == pytest.approx(20.0, abs=1.0)
    assert max(ys) == pytest.approx(50.0, abs=1.0)


def test_expand_outline_grows_by_bleed(tmp_path: Path):
    src = tmp_path / "src.pdf"
    _make_source_pdf(src)
    doc = fitz.open(str(src))
    try:
        outline = extract_cut_outline(doc[0])
    finally:
        doc.close()
    bleed_pt = 3.0 * POINTS_PER_MM
    expanded = expand_outline(outline, bleed_pt)
    minx, miny, maxx, maxy = expanded.bounds
    # prostokąt 50x30 + 2*bleed na każdej osi
    assert (maxx - minx) == pytest.approx(50.0 + 2 * bleed_pt, abs=1.0)
    assert (maxy - miny) == pytest.approx(30.0 + 2 * bleed_pt, abs=1.0)


def test_prepare_special_trim_outputs_two_pdfs_and_size(tmp_path: Path):
    src = tmp_path / "src.pdf"
    _make_source_pdf(src)
    out = tmp_path / "out"
    out.mkdir()
    result = prepare_special_trim(
        print_pdf_path=str(src), print_page=0,
        cut_pdf_path=str(src), cut_page=0,
        bleed_mm=3.0, out_dir=out,
    )
    assert result.print_path.is_file()
    assert result.cut_path.is_file()
    bleed_pt = 3.0 * POINTS_PER_MM
    expected_w_mm = (50.0 + 2 * bleed_pt) / POINTS_PER_MM
    expected_h_mm = (30.0 + 2 * bleed_pt) / POINTS_PER_MM
    assert result.page_width_mm == pytest.approx(expected_w_mm, abs=0.5)
    assert result.page_height_mm == pytest.approx(expected_h_mm, abs=0.5)
    # przycięta strona druku ma rozmiar = bounding box obrysu + spad
    doc = fitz.open(str(result.print_path))
    try:
        assert doc[0].rect.width == pytest.approx(50.0 + 2 * bleed_pt, abs=0.6)
        assert doc[0].rect.height == pytest.approx(30.0 + 2 * bleed_pt, abs=0.6)
    finally:
        doc.close()


def test_prepare_special_trim_raises_on_no_vector_outline(tmp_path: Path):
    blank = tmp_path / "blank.pdf"
    doc = fitz.open()
    doc.new_page(width=100, height=100)  # brak rysunków wektorowych
    doc.save(str(blank))
    doc.close()
    out = tmp_path / "out"
    out.mkdir()
    with pytest.raises(ValueError):
        prepare_special_trim(
            print_pdf_path=str(blank), print_page=0,
            cut_pdf_path=str(blank), cut_page=0,
            bleed_mm=3.0, out_dir=out,
        )


import os

import numpy as np

pyside6 = pytest.importorskip("PySide6", reason="parność wymaga Qt (tylko dev)")


def _render_gray(pdf_path: Path, scale: float = 2.0) -> "np.ndarray":
    doc = fitz.open(str(pdf_path))
    try:
        pix = doc[0].get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        return arr.mean(axis=2)
    finally:
        doc.close()


def test_parity_with_desktop_prepare(tmp_path: Path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    # QPixmap (używany przez desktopowy render podglądu) wymaga instancji QApplication.
    if QApplication.instance() is None:
        QApplication([])

    from summa_cut.special_mode_window import prepare_special_mode_docs

    src = tmp_path / "src.pdf"
    _make_source_pdf(src)

    new = prepare_special_trim(str(src), 0, str(src), 0, bleed_mm=3.0, out_dir=tmp_path / "new")

    desk_dir = tmp_path / "desk"
    desk = prepare_special_mode_docs(str(src), 0, str(src), 0, bleed_mm=3.0, temp_work_dir=desk_dir)

    a = _render_gray(new.print_path)
    b = _render_gray(Path(desk.print_pdf_path))
    # te same wymiary (z dokł. do 1 px) i bliska zgodność pikselowa
    assert abs(a.shape[0] - b.shape[0]) <= 2
    assert abs(a.shape[1] - b.shape[1]) <= 2
    h = min(a.shape[0], b.shape[0])
    w = min(a.shape[1], b.shape[1])
    diff = np.abs(a[:h, :w].astype(float) - b[:h, :w].astype(float))
    assert diff.mean() < 6.0, f"średnia różnica pikseli {diff.mean():.2f} za duża"
