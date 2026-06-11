from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

import fitz
from shapely.geometry import Polygon as ShapelyPolygon
from shapely.ops import unary_union

from .pdf_io import MM_PER_POINT

POINTS_PER_MM = 1.0 / MM_PER_POINT

# Liczba odcinków, na które dzielimy krzywą Béziera przy spłaszczaniu do wielokąta.
_BEZIER_STEPS = 16

SPECIAL_PRINT_NAME = "__special_print__.pdf"
SPECIAL_CUT_NAME = "__special_cut__.pdf"


@dataclass
class SpecialTrimResult:
    print_path: Path
    cut_path: Path
    page_width_mm: float
    page_height_mm: float


def _flatten_cubic(p0, p1, p2, p3, steps: int = _BEZIER_STEPS) -> list[tuple[float, float]]:
    """De Casteljau: krzywa sześcienna -> łamana (bez punktu startowego p0)."""
    pts: list[tuple[float, float]] = []
    for i in range(1, steps + 1):
        t = i / steps
        mt = 1.0 - t
        a = mt * mt * mt
        b = 3 * mt * mt * t
        c = 3 * mt * t * t
        d = t * t * t
        x = a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0]
        y = a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]
        pts.append((x, y))
    return pts


def drawings_to_polygons(page: fitz.Page) -> list[list[tuple[float, float]]]:
    """Z wektorowych rysunków strony buduje listę zamkniętych wielokątów (w pt, układ strony).

    Obsługuje operacje get_drawings: 're' (prostokąt), 'l' (linia), 'c' (Bézier),
    'qu' (czworokąt). Krzywe spłaszczane de Casteljau."""
    polygons: list[list[tuple[float, float]]] = []
    for drawing in page.get_drawings():
        current: list[tuple[float, float]] = []

        def _flush() -> None:
            if len(current) >= 3:
                polygons.append(current[:])

        for item in drawing.get("items", []):
            op = item[0]
            if op == "re":
                rect = item[1]
                _flush()
                current = []
                polygons.append([
                    (rect.x0, rect.y0), (rect.x1, rect.y0),
                    (rect.x1, rect.y1), (rect.x0, rect.y1),
                ])
            elif op == "qu":
                quad = item[1]
                _flush()
                current = []
                polygons.append([
                    (quad.ul.x, quad.ul.y), (quad.ur.x, quad.ur.y),
                    (quad.lr.x, quad.lr.y), (quad.ll.x, quad.ll.y),
                ])
            elif op == "l":
                p1, p2 = item[1], item[2]
                if not current:
                    current.append((p1.x, p1.y))
                current.append((p2.x, p2.y))
            elif op == "c":
                p1, p2, p3, p4 = item[1], item[2], item[3], item[4]
                if not current:
                    current.append((p1.x, p1.y))
                current.extend(_flatten_cubic(
                    (p1.x, p1.y), (p2.x, p2.y), (p3.x, p3.y), (p4.x, p4.y),
                ))
        _flush()
    return polygons


def extract_cut_outline(page: fitz.Page):
    """Suma logiczna wektorowych wielokątów strony wykrojnika -> geometria Shapely.

    Rzuca ValueError, gdy nie ma żadnego prawidłowego obrysu."""
    shapes = []
    for poly in drawings_to_polygons(page):
        try:
            sp = ShapelyPolygon(poly)
        except Exception:
            continue
        if sp.is_valid and sp.area > 0:
            shapes.append(sp)
        else:
            fixed = sp.buffer(0)
            if not fixed.is_empty and fixed.area > 0:
                shapes.append(fixed)
    if not shapes:
        raise ValueError("Nie udało się znaleźć wektorowego obrysu wykrojnika na wybranej stronie.")
    # Świadomie używamy sumy logicznej (unary_union) zamiast even-odd QPainterPath.simplified()
    # z desktopu — to odporniejszy zamiennik. Dla prostych obrysów wyniki są zgodne; dla
    # samoprzecinających się / zagnieżdżonych (z dziurami) mogą się różnić (union vs even-odd).
    union = unary_union(shapes)
    if union.is_empty or union.area <= 0:
        raise ValueError("Obrys wykrojnika jest pusty.")
    return union


def expand_outline(geom, bleed_pt: float):
    """Rozszerza obrys o spad (round join, jak QPainterPathStroker w desktopie)."""
    if bleed_pt <= 0:
        return geom
    expanded = geom.buffer(bleed_pt, join_style=1, cap_style=1)  # 1 = round
    if expanded.is_empty or expanded.area <= 0:
        raise ValueError("Obrys wykrojnika po dodaniu spadu jest pusty.")
    return expanded


def _geom_rings(geom) -> list[list[tuple[float, float]]]:
    """Wszystkie pierścienie (zewnętrzne i wewnętrzne) geometrii jako listy punktów."""
    rings: list[list[tuple[float, float]]] = []
    geoms = list(getattr(geom, "geoms", [geom]))
    for g in geoms:
        ext = getattr(g, "exterior", None)
        if ext is None:
            continue
        rings.append(list(ext.coords))
        for interior in g.interiors:
            rings.append(list(interior.coords))
    return rings


def _clip_commands(geom, out_page: fitz.Page, offset_x: float, offset_y: float) -> str:
    """Port qpath_to_pdf_clip_commands: pierścienie Shapely -> strumień clipu PDF.

    Punkty (w układzie strony, pt) przesuwamy o (offset_x, offset_y) i mapujemy
    przez macierz transformacji strony do układu PDF, jak w desktopie."""
    pdf_matrix = out_page.transformation_matrix
    commands: list[str] = ["q"]
    for ring in _geom_rings(geom):
        if len(ring) < 3:
            continue
        first = fitz.Point(ring[0][0] - offset_x, ring[0][1] - offset_y) * pdf_matrix
        commands.append(f"{first.x:.3f} {first.y:.3f} m")
        for x, y in ring[1:]:
            mapped = fitz.Point(x - offset_x, y - offset_y) * pdf_matrix
            commands.append(f"{mapped.x:.3f} {mapped.y:.3f} l")
        commands.append("h")
    commands.append("W n")
    commands.append("/fzFrm0 Do")
    commands.append("Q")
    return "\n".join(commands)


def _save_vector_trim_pdf(
    output_path: Path,
    source_doc: fitz.Document,
    source_page_index: int,
    geom,
    page_rect: fitz.Rect,
) -> tuple[float, float]:
    """Port save_vector_trim_pdf: osadza stronę źródła i zastępuje strumień treści clipem."""
    minx, miny, maxx, maxy = geom.bounds
    width = maxx - minx
    height = maxy - miny
    if width <= 0 or height <= 0:
        raise ValueError("Obrys wykrojnika po dodaniu spadu jest pusty.")
    out_doc = fitz.open()
    try:
        out_page = out_doc.new_page(width=width, height=height)
        target_rect = fitz.Rect(-minx, -miny, page_rect.width - minx, page_rect.height - miny)
        out_page.show_pdf_page(target_rect, source_doc, source_page_index)
        content_xrefs = out_page.get_contents()
        if not content_xrefs:
            raise ValueError("Nie udało się utworzyć treści strony wynikowej PDF.")
        clip_stream = _clip_commands(geom, out_page, minx, miny).encode("ascii")
        out_doc.update_stream(content_xrefs[0], clip_stream)
        out_doc.save(str(output_path))
    finally:
        out_doc.close()
    return width, height


def prepare_special_trim(
    print_pdf_path: str,
    print_page: int,
    cut_pdf_path: str,
    cut_page: int,
    bleed_mm: float,
    out_dir: Path | None = None,
) -> SpecialTrimResult:
    """Z obrysu wykrojnika + spadu tworzy dwa przycięte PDF-y (druk i wykrojnik) i zwraca rozmiar strony w mm."""
    work_dir = out_dir or Path(tempfile.mkdtemp(prefix="summa-cut-special-"))
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    print_doc = fitz.open(print_pdf_path)
    cut_doc = fitz.open(cut_pdf_path)
    try:
        cut_page_obj = cut_doc[cut_page]
        print_page_obj = print_doc[print_page]
        outline = extract_cut_outline(cut_page_obj)
        expanded = expand_outline(outline, bleed_mm * POINTS_PER_MM)
        out_print = work_dir / SPECIAL_PRINT_NAME
        out_cut = work_dir / SPECIAL_CUT_NAME
        w_pt, h_pt = _save_vector_trim_pdf(out_print, print_doc, print_page, expanded, print_page_obj.rect)
        _save_vector_trim_pdf(out_cut, cut_doc, cut_page, expanded, cut_page_obj.rect)
        return SpecialTrimResult(
            print_path=out_print,
            cut_path=out_cut,
            page_width_mm=w_pt * MM_PER_POINT,
            page_height_mm=h_pt * MM_PER_POINT,
        )
    finally:
        print_doc.close()
        cut_doc.close()
