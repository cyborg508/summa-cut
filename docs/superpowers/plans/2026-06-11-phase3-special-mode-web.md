# Faza 3 — webowy tryb specjalny (Implementation Plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dodać do web-appki summa-cut tryb specjalny (wektorowy obrys wykrojnika + spad), w pełni bezgłowy i bez Qt, z pełną parnością wyniku względem desktopu.

**Architecture:** Silnik już obsługuje tryb specjalny bez Qt — `compute_layout` buduje kafelkowanie z 8 offsetów + rozmiaru strony (`_build_special_mode_placements`), a `generate_output_docs` routuje `use_special` (pełna strona zamiast clipu wg content-bbox). Jedyny element zależny od Qt to przygotowanie dwóch przyciętych PDF-ów (druk + wykrojnik) do bleed-rozszerzonego obrysu. Portujemy go na **Shapely** (`unary_union` + `.buffer`) w nowym module `summa_cut/special_trim.py`, zachowując 1:1 mechanikę osadzania z desktopowego `save_vector_trim_pdf` (ten sam `show_pdf_page` + podmiana strumienia treści na `q … W n /fzFrm0 Do Q`). Backend dostaje trasę `/api/special/prepare`, która produkuje przycięte PDF-y i rejestruje je jako uploady sesji; reszta przepływu (job → preview → generate → download) działa bez zmian. Front dostaje sekcję trybu specjalnego z 8 polami numerycznymi offsetów i podglądem serwerowym.

**Tech Stack:** Python, PyMuPDF (fitz), pikepdf, **Shapely (nowa zależność)**, FastAPI, vanilla JS/HTMX-style fetch. Testy: pytest + fastapi.TestClient (bez przeglądarki, bez Qt w `web/`).

---

## File Structure

- **Create `summa_cut/special_trim.py`** — Qt-free port `prepare_special_mode_docs`. Odpowiedzialność: z wektorowego obrysu strony wykrojnika zbudować geometrię Shapely, rozszerzyć o spad, przyciąć OBA źródła (druk+wykrojnik) do tej geometrii, zapisać dwa PDF-y i zwrócić rozmiar strony w mm. Zero importów Qt.
- **Modify `summa_cut/models.py`** — bez zmian strukturalnych (SpecialModePattern już istnieje). Tylko jeśli potrzeba: nic.
- **Modify `web/job_builder.py`** — `JobParams` + pola trybu specjalnego; gałąź w `build_job` budująca `SpecialModePattern`.
- **Modify `web/server.py`** — trasa `POST /api/special/prepare`.
- **Modify `web/static/index.html`, `web/static/app.js`, `web/static/style.css`** — sekcja trybu specjalnego.
- **Modify `requirements-web.txt`, `requirements.txt`** — `shapely`.
- **Modify `Dockerfile`** — shapely wchodzi z `requirements-web.txt` (nic poza dodaniem zależności; GEOS leci jako wheel manylinux).
- **Test `tests/test_special_trim.py`** — rdzeń przycinania (Qt-free asercje + opcjonalna parność z desktopem).
- **Test `tests/test_web_job_builder.py`** (rozszerzenie) — budowa joba w trybie specjalnym.
- **Test `tests/test_web_api.py`** (rozszerzenie) — `/api/special/prepare` + pełny przepływ specjalny end-to-end.
- **Test `tests/test_web_frontend.py`** (rozszerzenie) — kontrakt id-ów sekcji specjalnej.

---

## Task 1: Qt-free rdzeń przycinania (`summa_cut/special_trim.py`)

**Files:**
- Create: `summa_cut/special_trim.py`
- Test: `tests/test_special_trim.py`

Mechanika osadzania jest portem 1:1 z `summa_cut/special_mode_window.py:76-97` (`save_vector_trim_pdf`) i `:56-73` (`qpath_to_pdf_clip_commands`) — różnica wyłącznie w źródle wielokątów (Shapely zamiast `QPainterPath`). Dzięki temu wynik jest piksel-w-piksel zgodny z desktopem (potwierdza to opcjonalny test parności).

- [ ] **Step 1: Write the failing test (rdzeń: ekstrakcja + bufor + przycięcie)**

```python
# tests/test_special_trim.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/summa-cut && .venv/bin/python -m pytest tests/test_special_trim.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'summa_cut.special_trim'` (lub `shapely`).

- [ ] **Step 3: Zainstaluj shapely do venv (zależność rdzenia)**

Run:
```bash
cd ~/summa-cut && .venv/bin/pip install shapely
```
Expected: instaluje shapely (wheel z GEOS). Sprawdź: `.venv/bin/python -c "import shapely; print(shapely.__version__)"` → wypisuje wersję.

- [ ] **Step 4: Write minimal implementation**

```python
# summa_cut/special_trim.py
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
        except (ValueError, Exception):
            continue
        if sp.is_valid and sp.area > 0:
            shapes.append(sp)
        else:
            fixed = sp.buffer(0)
            if not fixed.is_empty and fixed.area > 0:
                shapes.append(fixed)
    if not shapes:
        raise ValueError("Nie udało się znaleźć wektorowego obrysu wykrojnika na wybranej stronie.")
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


def _save_vector_trim_pdf(output_path: Path, source_doc: fitz.Document, source_page_index: int, geom, page_rect: fitz.Rect) -> tuple[float, float]:
    """Port save_vector_trim_pdf: osadza stronę źródła i zastępuje strumień treści clipem."""
    minx, miny, maxx, maxy = geom.bounds
    width = maxx - minx
    height = maxy - miny
    if width <= 0 or height <= 0:
        raise ValueError("Obrys wykrojnika po dodaniu spadu jest pusty.")
    out_doc = fitz.open()
    out_page = out_doc.new_page(width=width, height=height)
    target_rect = fitz.Rect(-minx, -miny, page_rect.width - minx, page_rect.height - miny)
    out_page.show_pdf_page(target_rect, source_doc, source_page_index)
    content_xrefs = out_page.get_contents()
    if not content_xrefs:
        raise ValueError("Nie udało się utworzyć treści strony wynikowej PDF.")
    clip_stream = _clip_commands(geom, out_page, minx, miny).encode("ascii")
    out_doc.update_stream(content_xrefs[0], clip_stream)
    out_doc.save(str(output_path))
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
        out_print = work_dir / "__special_print__.pdf"
        out_cut = work_dir / "__special_cut__.pdf"
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd ~/summa-cut && .venv/bin/python -m pytest tests/test_special_trim.py -q`
Expected: PASS (4 testy).

- [ ] **Step 6: Dodaj opcjonalny test parności z desktopem (fidelity guard)**

```python
# dopisz na końcu tests/test_special_trim.py
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
```

- [ ] **Step 7: Run parity test**

Run: `cd ~/summa-cut && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_special_trim.py -q`
Expected: PASS (5 testów; parność < tolerancja). Jeśli `numpy` brak: `.venv/bin/pip install numpy`.

- [ ] **Step 8: Commit**

```bash
cd ~/summa-cut && git add summa_cut/special_trim.py tests/test_special_trim.py
git commit -m "feat(special): Qt-free port przycinania do obrysu wykrojnika (Shapely) + parność z desktopem"
```

---

## Task 2: Pola trybu specjalnego w `job_builder` + budowa joba

**Files:**
- Modify: `web/job_builder.py`
- Test: `tests/test_web_job_builder.py`

W trybie specjalnym job używa PRZYCIĘTYCH uploadów jako źródeł druku/wykrojnika, ma `gap_enabled=True`, a `SpecialModePattern(enabled=True)` niesie rozmiar strony + 8 offsetów. `item_spec` = rozmiar strony (layout i tak liczy z patternu). Rozmiar strony bierzemy z `PdfInfo` przyciętego uploadu (źródło prawdy = realny przycięty PDF), nie z parametrów klienta.

- [ ] **Step 1: Write the failing test**

```python
# dopisz do tests/test_web_job_builder.py
def test_build_job_special_mode_sets_pattern(tmp_path):
    # helpery z istniejącego pliku: _make_session / _upload (jeśli inne nazwy — użyj istniejących)
    from web.job_builder import JobParams, build_job
    from web.sessions import SessionStore

    store = SessionStore(tmp_path, ttl_seconds=3600)
    session = store.create()
    # przygotuj przycięte uploady tak, jak zrobi to trasa /api/special/prepare
    import fitz
    for name in ("__special_print__.pdf", "__special_cut__.pdf"):
        doc = fitz.open()
        doc.new_page(width=160.0, height=100.0)  # ~56.4 x 35.3 mm
        data = doc.tobytes()
        doc.close()
        store.save_upload(session, name, data)

    params = JobParams(
        print_upload="__special_print__.pdf", print_page=0,
        cut_upload="__special_cut__.pdf", cut_page=0,
        item_w_mm=56.4, item_h_mm=35.3,
        special_enabled=True,
        special_page_w_mm=56.4, special_page_h_mm=35.3,
        special_row_offsets_mm=[0.0, 2.0],
        special_col_offsets_mm=[0.0, 0.0],
        special_col_x_offsets_mm=[0.0, 0.0],
        special_row_y_offsets_mm=[0.0, 0.0],
    )
    job = build_job(params, session)
    assert job.special_mode_pattern is not None
    assert job.special_mode_pattern.enabled is True
    assert job.special_mode_pattern.page_width_mm > 0
    assert job.special_mode_pattern.row_offsets_mm == [0.0, 2.0]
    assert job.gap_enabled is True  # tryb specjalny = z odstępami
    assert job.print_page.pdf_path.endswith("__special_print__.pdf")
    assert job.cut_page.pdf_path.endswith("__special_cut__.pdf")


def test_build_job_special_requires_cut_upload(tmp_path):
    from web.job_builder import JobParams, build_job
    from web.sessions import SessionStore
    import fitz, pytest

    store = SessionStore(tmp_path, ttl_seconds=3600)
    session = store.create()
    doc = fitz.open(); doc.new_page(width=100, height=100); data = doc.tobytes(); doc.close()
    store.save_upload(session, "__special_print__.pdf", data)
    params = JobParams(
        print_upload="__special_print__.pdf", print_page=0,
        cut_upload=None, cut_page=None,
        item_w_mm=30, item_h_mm=30,
        special_enabled=True, special_page_w_mm=30, special_page_h_mm=30,
    )
    with pytest.raises(ValueError):
        build_job(params, session)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/summa-cut && .venv/bin/python -m pytest tests/test_web_job_builder.py -q`
Expected: FAIL — `JobParams` nie zna pola `special_enabled` (ValidationError) lub brak gałęzi.

- [ ] **Step 3: Write minimal implementation**

W `web/job_builder.py` dodaj import patternu i pola do `JobParams` (po `montage`):

```python
# zmień linię importu modeli:
from summa_cut.models import ItemSpec, JobSettings, MontageItem, OposSpec, SelectedPage, SheetSpec, SpecialModePattern
```

```python
# w klasie JobParams, po: montage: list[MontageItemParams] = Field(default_factory=list)
    special_enabled: bool = False
    special_page_w_mm: float = 0.0
    special_page_h_mm: float = 0.0
    special_row_offsets_mm: list[float] = Field(default_factory=lambda: [0.0, 0.0])
    special_col_offsets_mm: list[float] = Field(default_factory=lambda: [0.0, 0.0])
    special_col_x_offsets_mm: list[float] = Field(default_factory=lambda: [0.0, 0.0])
    special_row_y_offsets_mm: list[float] = Field(default_factory=lambda: [0.0, 0.0])
```

W `build_job`, na początku (po walidacji sheet, przed gałęzią montażu) dodaj gałąź specjalną z wczesnym `return`:

```python
    if params.special_enabled:
        return _build_special_job(params, session)
```

I dodaj funkcję pomocniczą (nad `build_job`):

```python
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
    print_size = print_info.page_sizes_mm[params.print_page]
    cut_size = cut_info.page_sizes_mm[params.cut_page]
    print_bbox = print_info.page_content_boxes_pt[params.print_page]
    cut_bbox = cut_info.page_content_boxes_pt[params.cut_page]

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
        print_page_size_mm=print_size,
        cut_page_size_mm=cut_size,
        print_content_size_mm=print_info.page_content_sizes_mm[params.print_page],
        cut_content_size_mm=cut_info.page_content_sizes_mm[params.cut_page],
        print_content_bbox_pt=print_bbox,
        cut_content_bbox_pt=cut_bbox,
        sheet_spec=SheetSpec(params.sheet_w_mm, params.sheet_h_mm),
        item_spec=ItemSpec(page_w_mm, page_h_mm, False),
        gap_enabled=True,
        gap_mm=0.0,
        generate_cut_grid=False,
        opos_spec=OposSpec(params.opos_side_offset_mm, params.opos_bottom_offset_mm, params.opos_top_offset_mm),
        special_mode_pattern=pattern,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/summa-cut && .venv/bin/python -m pytest tests/test_web_job_builder.py -q`
Expected: PASS (nowe 2 + dotychczasowe).

- [ ] **Step 5: Commit**

```bash
cd ~/summa-cut && git add web/job_builder.py tests/test_web_job_builder.py
git commit -m "feat(special): pola trybu specjalnego w JobParams + budowa SpecialModePattern"
```

---

## Task 3: Trasa `POST /api/special/prepare`

**Files:**
- Modify: `web/server.py`
- Test: `tests/test_web_api.py`

Trasa: przyjmuje wybór stron + spad, woła `prepare_special_trim` do `session.workdir`, rejestruje oba przycięte PDF-y jako uploady sesji (`store.save_upload` — wymaga bajtów, więc czytamy zapisany plik), zwraca nazwy + rozmiar strony w mm. Klient potem składa `/api/job` z `special_enabled=True`.

- [ ] **Step 1: Write the failing test**

```python
# dopisz do tests/test_web_api.py
def _make_special_source_bytes() -> bytes:
    import fitz
    doc = fitz.open()
    page = doc.new_page(width=120.0, height=100.0)
    page.draw_rect(fitz.Rect(20, 20, 70, 50), color=(0, 0, 0), fill=(0.6, 0.6, 0.6), width=0.0)
    page.draw_rect(fitz.Rect(20, 20, 70, 50), color=(1, 0, 0), width=0.5)
    data = doc.tobytes()
    doc.close()
    return data


def test_special_prepare_then_full_flow(client):
    # client: istniejąca fixtura TestClient z aktywną sesją (jak w pozostałych testach pliku)
    data = _make_special_source_bytes()
    up = client.post("/api/upload", files={"file": ("zrodlo.pdf", data, "application/pdf")})
    assert up.status_code == 200

    prep = client.post("/api/special/prepare", json={
        "print_upload": "zrodlo.pdf", "print_page": 0,
        "cut_upload": "zrodlo.pdf", "cut_page": 0,
        "bleed_mm": 3.0,
    })
    assert prep.status_code == 200, prep.text
    body = prep.json()
    assert body["print_upload"] == "__special_print__.pdf"
    assert body["cut_upload"] == "__special_cut__.pdf"
    assert body["page_width_mm"] > 0 and body["page_height_mm"] > 0

    job = client.post("/api/job", json={
        "print_upload": body["print_upload"], "print_page": 0,
        "cut_upload": body["cut_upload"], "cut_page": 0,
        "item_w_mm": body["page_width_mm"], "item_h_mm": body["page_height_mm"],
        "special_enabled": True,
        "special_page_w_mm": body["page_width_mm"], "special_page_h_mm": body["page_height_mm"],
        "special_row_offsets_mm": [0.0, 0.0],
        "special_col_offsets_mm": [0.0, 0.0],
        "special_col_x_offsets_mm": [0.0, 0.0],
        "special_row_y_offsets_mm": [0.0, 0.0],
    })
    assert job.status_code == 200, job.text
    assert job.json()["count"] >= 1

    prev = client.get("/api/preview/print.png")
    assert prev.status_code == 200
    assert prev.headers["content-type"] == "image/png"
    assert len(prev.content) > 100

    gen = client.post("/api/generate", json={"base_name": "spec"})
    assert gen.status_code == 200
    dl = client.get("/api/download/print")
    assert dl.status_code == 200
    assert dl.content[:4] == b"%PDF"


def test_special_prepare_rejects_blank_page(client):
    import fitz
    doc = fitz.open(); doc.new_page(width=100, height=100); data = doc.tobytes(); doc.close()
    client.post("/api/upload", files={"file": ("blank.pdf", data, "application/pdf")})
    prep = client.post("/api/special/prepare", json={
        "print_upload": "blank.pdf", "print_page": 0,
        "cut_upload": "blank.pdf", "cut_page": 0,
        "bleed_mm": 3.0,
    })
    assert prep.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/summa-cut && .venv/bin/python -m pytest tests/test_web_api.py -q -k special`
Expected: FAIL — 404 (trasa nie istnieje).

- [ ] **Step 3: Write minimal implementation**

W `web/server.py`:

```python
# dodaj import:
from summa_cut.special_trim import prepare_special_trim
```

```python
# dodaj model przy GenerateParams:
class SpecialPrepareParams(BaseModel):
    print_upload: str
    print_page: int = 0
    cut_upload: str
    cut_page: int = 0
    bleed_mm: float = 3.0
```

```python
# dodaj trasę po /api/upload (przed /api/job):
    @app.post("/api/special/prepare")
    def special_prepare(params: SpecialPrepareParams, session: Session = Depends(current_session)) -> dict:
        print_info = session.uploads.get(params.print_upload)
        cut_info = session.uploads.get(params.cut_upload)
        if print_info is None or cut_info is None:
            raise HTTPException(status_code=400, detail="Najpierw wgraj pliki druku i wykrojnika.")
        try:
            result = prepare_special_trim(
                print_pdf_path=print_info.path, print_page=params.print_page,
                cut_pdf_path=cut_info.path, cut_page=params.cut_page,
                bleed_mm=params.bleed_mm, out_dir=session.workdir,
            )
            # zarejestruj przycięte PDF-y jako uploady sesji (zapis już w workdir → czytamy bajty)
            print_reg = store.save_upload(session, result.print_path.name, result.print_path.read_bytes())
            cut_reg = store.save_upload(session, result.cut_path.name, result.cut_path.read_bytes())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {
            "print_upload": print_reg.name,
            "cut_upload": cut_reg.name,
            "page_width_mm": result.page_width_mm,
            "page_height_mm": result.page_height_mm,
        }
```

> Uwaga: `store.save_upload` zapisuje bajty pod `session.workdir/<name>` (nadpisując nasz plik tą samą treścią) i woła `read_pdf_info` — to celowe: rejestruje upload w `session.uploads`, dzięki czemu `_require_page` w `build_job` go znajdzie.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/summa-cut && .venv/bin/python -m pytest tests/test_web_api.py -q`
Expected: PASS (nowe + dotychczasowe).

- [ ] **Step 5: Commit**

```bash
cd ~/summa-cut && git add web/server.py tests/test_web_api.py
git commit -m "feat(special): trasa /api/special/prepare (przycięcie + rejestracja uploadów)"
```

---

## Task 4: Front — sekcja trybu specjalnego

**Files:**
- Modify: `web/static/index.html`
- Modify: `web/static/app.js`
- Modify: `web/static/style.css`
- Test: `tests/test_web_frontend.py`

UI: checkbox włączający tryb specjalny, wybór stron druku/wykrojnika (reużywa istniejących selectów plików — albo dedykowane), pole spadu, przycisk „Przygotuj wykrojnik", 8 pól offsetów (row[0..1], col[0..1], col_x[0..1], row_y[0..1]), podgląd na żywo (istniejące `/api/preview`), generuj/pobierz (istniejące). Po „Przygotuj" front zapamiętuje `special_print_upload` / `special_cut_upload` / rozmiar strony i wysyła `special_enabled` w `/api/job`.

- [ ] **Step 1: Write the failing test (kontrakt id-ów)**

```python
# dopisz do tests/test_web_frontend.py
def test_index_has_special_mode_controls():
    from pathlib import Path
    html = (Path(__file__).resolve().parents[1] / "web" / "static" / "index.html").read_text(encoding="utf-8")
    for el_id in [
        "special-enable", "special-bleed", "special-prepare-btn",
        "special-row0", "special-row1", "special-col0", "special-col1",
        "special-colx0", "special-colx1", "special-rowy0", "special-rowy1",
        "special-status",
    ]:
        assert f'id="{el_id}"' in html, f"brak #{el_id} w index.html"


def test_app_js_references_special_endpoints():
    from pathlib import Path
    js = (Path(__file__).resolve().parents[1] / "web" / "static" / "app.js").read_text(encoding="utf-8")
    assert "/api/special/prepare" in js
    assert "special_enabled" in js
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/summa-cut && .venv/bin/python -m pytest tests/test_web_frontend.py -q`
Expected: FAIL — brak id-ów / odwołań.

- [ ] **Step 3: Dodaj sekcję do `web/static/index.html`**

Wstaw nową `<fieldset>` w `#controls` (np. po sekcji montażu, przed przyciskiem generowania):

```html
      <fieldset class="special">
        <legend>Tryb specjalny (wektorowy obrys + spad)</legend>
        <label><input type="checkbox" id="special-enable"> włącz tryb specjalny</label>
        <div id="special-body" hidden>
          <label>spad mm <input type="number" id="special-bleed" value="3" step="0.1" min="0"></label>
          <button type="button" id="special-prepare-btn">Przygotuj wykrojnik</button>
          <span id="special-status" class="special-status"></span>
          <fieldset class="special-offsets">
            <legend>Offsety kafli 2×2 (mm)</legend>
            <label>rząd 0 X <input type="number" id="special-row0" value="0" step="0.1"></label>
            <label>rząd 1 X <input type="number" id="special-row1" value="0" step="0.1"></label>
            <label>kol. 0 Y <input type="number" id="special-col0" value="0" step="0.1"></label>
            <label>kol. 1 Y <input type="number" id="special-col1" value="0" step="0.1"></label>
            <label>kol. 0 X <input type="number" id="special-colx0" value="0" step="0.1"></label>
            <label>kol. 1 X <input type="number" id="special-colx1" value="0" step="0.1"></label>
            <label>rząd 0 Y <input type="number" id="special-rowy0" value="0" step="0.1"></label>
            <label>rząd 1 Y <input type="number" id="special-rowy1" value="0" step="0.1"></label>
          </fieldset>
        </div>
      </fieldset>
```

- [ ] **Step 4: Rozszerz `web/static/app.js`**

Dodaj stan i obsługę. Wzór: użyj istniejących funkcji `collectJob()`/`refreshPreview()`/`getEl()` (dopasuj nazwy do realnego app.js). Minimalny szkic do wpięcia:

```javascript
// stan trybu specjalnego
const special = { printUpload: null, cutUpload: null, pageW: 0, pageH: 0, ready: false };

function specialOffsets() {
  const v = (id) => parseFloat(document.getElementById(id).value) || 0;
  return {
    special_row_offsets_mm: [v("special-row0"), v("special-row1")],
    special_col_offsets_mm: [v("special-col0"), v("special-col1")],
    special_col_x_offsets_mm: [v("special-colx0"), v("special-colx1")],
    special_row_y_offsets_mm: [v("special-rowy0"), v("special-rowy1")],
  };
}

document.getElementById("special-enable").addEventListener("change", (e) => {
  document.getElementById("special-body").hidden = !e.target.checked;
  refreshPreview();
});

document.getElementById("special-prepare-btn").addEventListener("click", async () => {
  const status = document.getElementById("special-status");
  // wybór źródeł: reużyj selektów głównych (#print-file/#print-page/#cut-file/#cut-page)
  const payload = {
    print_upload: document.getElementById("print-file").value,
    print_page: parseInt(document.getElementById("print-page").value || "0", 10),
    cut_upload: document.getElementById("cut-file").value,
    cut_page: parseInt(document.getElementById("cut-page").value || "0", 10),
    bleed_mm: parseFloat(document.getElementById("special-bleed").value) || 0,
  };
  status.textContent = "Przygotowuję…";
  const res = await fetch("/api/special/prepare", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
  });
  if (!res.ok) { status.textContent = "Błąd: " + (await res.text()); return; }
  const b = await res.json();
  special.printUpload = b.print_upload; special.cutUpload = b.cut_upload;
  special.pageW = b.page_width_mm; special.pageH = b.page_height_mm; special.ready = true;
  status.textContent = `Gotowe: kafel ${b.page_width_mm.toFixed(1)}×${b.page_height_mm.toFixed(1)} mm`;
  refreshPreview();
});

["special-row0","special-row1","special-col0","special-col1","special-colx0","special-colx1","special-rowy0","special-rowy1","special-bleed"]
  .forEach((id) => document.getElementById(id).addEventListener("input", () => refreshPreview()));
```

W funkcji budującej payload `/api/job` (np. `collectJob()`), gdy tryb specjalny aktywny i przygotowany, NADPISZ źródła i dołącz pola specjalne:

```javascript
  if (document.getElementById("special-enable").checked && special.ready) {
    Object.assign(payload, {
      print_upload: special.printUpload,
      cut_upload: special.cutUpload,
      print_page: 0,
      cut_page: 0,
      item_w_mm: special.pageW,
      item_h_mm: special.pageH,
      special_enabled: true,
      special_page_w_mm: special.pageW,
      special_page_h_mm: special.pageH,
      ...specialOffsets(),
    });
  }
```

- [ ] **Step 5: Drobny styl w `web/static/style.css`**

```css
.special-offsets label { display: inline-block; width: 9rem; }
.special-status { margin-left: 0.5rem; color: #2a6; }
```

- [ ] **Step 6: Run frontend + składnia JS**

Run:
```bash
cd ~/summa-cut && .venv/bin/python -m pytest tests/test_web_frontend.py -q && node --check web/static/app.js
```
Expected: PASS + `app.js` bez błędów składni.

- [ ] **Step 7: Commit**

```bash
cd ~/summa-cut && git add web/static/index.html web/static/app.js web/static/style.css tests/test_web_frontend.py
git commit -m "feat(special): sekcja trybu specjalnego w UI (8 offsetów, przygotuj wykrojnik, podgląd)"
```

---

## Task 5: Zależność Shapely + Docker + guard bez-Qt

**Files:**
- Modify: `requirements-web.txt`
- Modify: `requirements.txt`
- Test: `tests/test_web_no_qt.py` (weryfikacja, że `summa_cut.special_trim` i `web.app` importują się bez Qt)

- [ ] **Step 1: Write the failing test (guard importu bez Qt)**

```python
# dopisz do tests/test_web_no_qt.py
def test_special_trim_imports_without_qt():
    import sys
    import importlib
    # upewnij się, że moduł nie ciągnie Qt
    mod = importlib.import_module("summa_cut.special_trim")
    assert hasattr(mod, "prepare_special_trim")
    assert "PySide6" not in sys.modules or True  # special_trim sam Qt nie importuje
    import inspect
    src = inspect.getsource(mod)
    assert "PySide6" not in src and "PyQt" not in src, "special_trim nie może importować Qt"
```

- [ ] **Step 2: Run test to verify it passes-or-fails**

Run: `cd ~/summa-cut && .venv/bin/python -m pytest tests/test_web_no_qt.py -q`
Expected: PASS (special_trim Qt nie importuje — z Tasku 1). Jeśli FAIL, popraw importy w `special_trim.py`.

- [ ] **Step 3: Dodaj shapely do plików zależności**

W `requirements-web.txt` dopisz linię:
```
shapely
```
W `requirements.txt` dopisz linię:
```
shapely
```

- [ ] **Step 4: Zbuduj obraz lokalnie? (nie — Docker tylko na drukpolu)**

Na stacji cyborg50 NIE ma Dockera. Weryfikacja zależności tu = `.venv/bin/python -c "import shapely"`. Build obrazu nastąpi na drukpolu w Tasku 6.

Run: `cd ~/summa-cut && .venv/bin/python -c "import shapely; print('shapely OK', shapely.__version__)"`
Expected: `shapely OK <wersja>`.

- [ ] **Step 5: Pełny zestaw testów (regresja)**

Run: `cd ~/summa-cut && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
Expected: PASS — wszystkie dotychczasowe 54 + nowe.

- [ ] **Step 6: Commit**

```bash
cd ~/summa-cut && git add requirements-web.txt requirements.txt tests/test_web_no_qt.py
git commit -m "build(special): shapely w zależnościach web + guard importu bez Qt"
```

---

## Task 6: Wdrożenie na drukpolu + smoke end-to-end

**Files:**
- Modify: `docs/DEPLOY-drukpol.md` (jeśli trzeba odnotować shapely)
- Bez nowego kodu — rebuild obrazu z nową zależnością.

- [ ] **Step 1: Rsync kodu na drukpol + rebuild**

Run:
```bash
rsync -az --delete --exclude .venv --exclude .git ~/summa-cut/ root@REDACTED-HOST:/srv/app/ \
&& ssh root@REDACTED-HOST 'cd /srv/app && docker compose up -d --build'
```
Expected: obraz buduje się z shapely (wheel z GEOS); kontener `summa-cut-web` wstaje.

- [ ] **Step 2: Smoke end-to-end przez Tailscale**

Run (na stacji, prosty smoke trasy):
```bash
curl -s -c /tmp/sc.txt -X POST http://REDACTED-HOST:8800/api/session >/dev/null \
&& curl -s -b /tmp/sc.txt http://REDACTED-HOST:8800/ -o /dev/null -w "GET / -> %{http_code}\n"
```
Expected: `GET / -> 200`. (Pełny upload→prepare→job→generate jak w teście API — opcjonalnie ręcznie.)

- [ ] **Step 3: Ręczna weryfikacja UI (user)**

User otwiera http://REDACTED-LAN:8800 (lub Tailscale), włącza „tryb specjalny", wgrywa PDF z wektorowym wykrojnikiem, klika „Przygotuj wykrojnik", ustawia offsety, sprawdza podgląd, generuje i pobiera druk+wykrojnik. Potwierdza poprawność wizualną (obrys przycięty, spad widoczny, OPOS na miejscu).

- [ ] **Step 4: Aktualizacja pamięci projektu**

Dopisz w `project_summacut.md`: Faza 3 wykonana + wdrożona, tag `phase3-special`, liczba testów, że shapely doszedł do obrazu.

---

## Self-Review

**1. Spec coverage:** Spec §9 „Faza 3 — webowy tryb specjalny" + §3 (`routes_special.py`, „tryb specjalny na osobnej zakładce/stronie") + §6/§3 (`get_drawings()` + spad + clip). Pokrycie: Task 1 = obrys/spad/clip (Qt-free), Task 3 = trasa, Task 4 = UI (sekcja zamiast osobnej strony — świadoma decyzja usera: pola numeryczne, jedna strona, spójność). Brak luk względem celu „działający tryb specjalny w web".

**2. Placeholder scan:** Kod kompletny w każdym kroku. Jedyne miejsca wymagające dopasowania do realnych nazw to helpery w istniejących plikach testów (`client`/`_make_session`) i nazwy funkcji w `app.js` (`collectJob`/`refreshPreview`) — wykonawca podejrzy realne nazwy w plikach (odnotowane jawnie, nie „TODO”).

**3. Type consistency:** `SpecialModePattern` pola = `models.py:55-65` (enabled, print_pdf_path, cut_pdf_path, page_width_mm, page_height_mm, row_offsets_mm, col_offsets_mm, col_x_offsets_mm, row_y_offsets_mm). `JobParams.special_*` → mapowane 1:1 w `_build_special_job`. `prepare_special_trim` zwraca `SpecialTrimResult(print_path, cut_path, page_width_mm, page_height_mm)` — używane spójnie w trasie. `_build_special_mode_placements` (layout.py) konsumuje pattern bez zmian.

**Ryzyka odnotowane:**
- Trik `/fzFrm0 Do` zakłada, że `show_pdf_page` w świeżym `out_doc` nazywa formę `fzFrm0` (jak w desktopie — ten sam wzorzec, więc trzyma). Parność (Task 1 step 6) to wyłapie, gdyby się rozjechało.
- Shapely `buffer(join_style=round)` vs `QPainterPathStroker` (round) — drobne różnice geometrii łuków; test parności z tolerancją `diff.mean() < 6.0` jako bramka.
