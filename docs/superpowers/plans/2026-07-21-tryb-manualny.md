# Tryb manualny (impozycja ręczna w stylu PlaceIt) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dodać do web-aplikacji summa-cut tryb manualny — ręczne układanie użytków (par druk/wykrojnik) na arkuszu jak w PlaceIt, z summa-cutowym wyjściem: dwa PDF-y (arkusz druku + arkusz wykrojnika z OPOS).

**Architecture:** Wariant A — interakcja PlaceIt trafia do summa-cut jako nowy tryb, a eksport zostaje summa-cutowy. Wykorzystujemy fakt, że `generate_output_docs` już stempluje dowolną listę `Placement` z `montage_item_index` (para druk/wykrojnik per placement). Backend dostaje nową ścieżkę „ręczne pozycje → `LayoutResult`" (`summa_cut/manual_layout.py`) omijającą auto-`compute_layout`; front dostaje kanwę SVG. Reszta pipeline'u (OPOS, spłaszczanie pod SummaWinPlot) bez zmian.

**Tech Stack:** Python 3.12, FastAPI, PyMuPDF (`fitz`), pikepdf, pydantic; frontend = czysty JS + SVG (bez frameworka); testy = pytest + `fastapi.testclient`.

**Spec:** `docs/superpowers/specs/2026-07-21-tryb-manualny-design.md`

---

## Struktura plików

**Backend (nowe / modyfikowane):**
- Modyfikacja `summa_cut/export.py` — `_centered_clip_rect_pt`: zamiana wymiarów clipu także dla 270° (dziś tylko 90°).
- Utworzenie `summa_cut/manual_layout.py` — `build_manual_layout()` (ręczne pozycje → `LayoutResult`) + `validate_manual_placements()` (nachodzenie / poza obszar OPOS).
- Modyfikacja `web/job_builder.py` — nowe pola `JobParams` (`manual_free_enabled`, `manual_items`, `manual_placements`) + gałąź manualna w `build_job` (`_build_manual_job`).
- Modyfikacja `web/server.py` — helper `_layout_for()` (rozgałęzienie manual/auto) użyty w `set_job` i `_job_and_layout`; bramka walidacji w `/api/generate`.

**Frontend (modyfikowane):**
- Modyfikacja `web/static/index.html` — przełącznik trybu, panel manualny (paleta + kanwa SVG).
- Modyfikacja `web/static/app.js` — stan `manualState`, paleta, kanwa, drag/obrót/kopia/usuń/strzałki, czerwona obwódka, budowa payloadu.
- Modyfikacja `web/static/style.css` — style palety/kanwy/obwódki.

**Testy (modyfikowane / nowe):**
- `tests/test_export.py` — rotacja 270° zamienia wymiary clipu.
- `tests/test_manual_layout.py` (nowy) — `build_manual_layout` + `validate_manual_placements`.
- `tests/test_web_job_builder.py` — gałąź manualna `build_job`.
- `tests/test_web_api.py` — end-to-end: set job → generate (2 pliki) + bramka 400 przy nachodzeniu.
- `tests/test_web_frontend.py` — obecność nowych id.

---

## Task 1: Poprawka rotacji 270° w eksporcie

Dziś `_centered_clip_rect_pt` zamienia wymiary okna przycięcia tylko dla `rotation_deg == 90`. Dla 270° footprint też jest obrócony (h×w), więc clip musi być zamieniony tak samo — inaczej wykrojnik/druk obrócony o 270° dostanie złe przycięcie. (180° nie wymaga zamiany — wymiary te same.)

**Files:**
- Modify: `summa_cut/export.py` (funkcja `_centered_clip_rect_pt`, ok. linia 44-64)
- Test: `tests/test_export.py`

- [ ] **Step 1: Dopisz test sprawdzający zamianę wymiarów clipu dla 270°**

W `tests/test_export.py` dopisz na końcu pliku:

```python
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
```

- [ ] **Step 2: Uruchom test — ma NIE przejść**

Run: `cd ~/summa-cut && .venv/bin/python -m pytest tests/test_export.py::test_centered_clip_swaps_dims_for_270 -v`
Expected: FAIL (dla 270° wymiary nie są zamienione, więc `r270.width != r90.width`).

- [ ] **Step 3: Popraw warunek zamiany**

W `summa_cut/export.py` w `_centered_clip_rect_pt` zmień:

```python
    if rotation_deg == 90:
        clip_w_pt, clip_h_pt = clip_h_pt, clip_w_pt
```

na:

```python
    if rotation_deg in (90, 270):
        clip_w_pt, clip_h_pt = clip_h_pt, clip_w_pt
```

- [ ] **Step 4: Uruchom test — ma przejść**

Run: `cd ~/summa-cut && .venv/bin/python -m pytest tests/test_export.py::test_centered_clip_swaps_dims_for_270 -v`
Expected: PASS

- [ ] **Step 5: Uruchom cały plik eksportu (brak regresji)**

Run: `cd ~/summa-cut && .venv/bin/python -m pytest tests/test_export.py tests/test_export_fidelity.py -q`
Expected: PASS (wszystkie)

- [ ] **Step 6: Commit**

```bash
cd ~/summa-cut && git add summa_cut/export.py tests/test_export.py
git commit -m "fix(export): zamień wymiary clipu także dla rotacji 270°

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: `build_manual_layout` — ręczne pozycje → LayoutResult

Nowy moduł z funkcją, która z listy ręcznych pozycji (`item_index, x_mm, y_mm, rotation_deg`) i rozmiarów użytków z `job.montage_items` składa `LayoutResult` (z `Placement`), pomijając auto-`compute_layout`. Footprint placementu = rozmiar strony użytku, zamieniony przy 90°/270°.

**Files:**
- Create: `summa_cut/manual_layout.py`
- Test: `tests/test_manual_layout.py`

- [ ] **Step 1: Napisz test `build_manual_layout`**

Utwórz `tests/test_manual_layout.py`:

```python
from __future__ import annotations

from summa_cut.manual_layout import ManualPlacement, build_manual_layout
from summa_cut.models import (
    JobSettings, MontageItem, OposSpec, SelectedPage, SheetSpec, ItemSpec,
)


def _item(w: float, h: float, idx: int) -> MontageItem:
    bbox = (0.0, 0.0, w, h)
    return MontageItem(
        label=f"#{idx}",
        print_page=SelectedPage("a.pdf", 0),
        cut_page=SelectedPage("a.pdf", 1),
        print_page_size_mm=(w, h), cut_page_size_mm=(w, h),
        print_content_size_mm=(w, h), cut_content_size_mm=(w, h),
        print_content_bbox_pt=bbox, cut_content_bbox_pt=bbox,
        quantity=1,
    )


def _job(items: list[MontageItem]) -> JobSettings:
    base = items[0]
    return JobSettings(
        print_page=base.print_page, cut_page=base.cut_page,
        print_page_size_mm=base.print_page_size_mm, cut_page_size_mm=base.cut_page_size_mm,
        print_content_size_mm=base.print_content_size_mm, cut_content_size_mm=base.cut_content_size_mm,
        print_content_bbox_pt=base.print_content_bbox_pt, cut_content_bbox_pt=base.cut_content_bbox_pt,
        sheet_spec=SheetSpec(330, 480), item_spec=ItemSpec(0, 0, False),
        gap_enabled=True, gap_mm=0.0, generate_cut_grid=False,
        montage_items=items, opos_spec=OposSpec(10, 10, 40),
    )


def test_build_manual_layout_maps_positions_and_index():
    job = _job([_item(40, 30, 0), _item(20, 50, 1)])
    placements = [
        ManualPlacement(item_index=0, x_mm=15.0, y_mm=45.0, rotation_deg=0),
        ManualPlacement(item_index=1, x_mm=100.0, y_mm=45.0, rotation_deg=0),
    ]
    layout = build_manual_layout(job, placements)
    assert layout.count == 2
    p0 = layout.placements[0]
    assert (p0.x_mm, p0.y_mm) == (15.0, 45.0)
    assert (p0.width_mm, p0.height_mm) == (40.0, 30.0)
    assert p0.montage_item_index == 0
    assert layout.placements[1].montage_item_index == 1


def test_build_manual_layout_swaps_footprint_for_90_and_270():
    job = _job([_item(40, 30, 0)])
    for rot in (90, 270):
        layout = build_manual_layout(job, [ManualPlacement(0, 10.0, 50.0, rot)])
        p = layout.placements[0]
        assert (p.width_mm, p.height_mm) == (30.0, 40.0)
        assert p.rotation_deg == rot


def test_build_manual_layout_sets_work_area_from_opos():
    job = _job([_item(40, 30, 0)])
    layout = build_manual_layout(job, [])
    wa = layout.work_area_rect
    assert (wa.x_mm, wa.y_mm) == (10.0, 40.0)      # side, top
    assert wa.width_mm == 330 - 2 * 10             # sheet_w - 2*side
    assert wa.height_mm == 480 - 40 - 10           # sheet_h - top - bottom


def test_build_manual_layout_rejects_bad_index():
    import pytest
    job = _job([_item(40, 30, 0)])
    with pytest.raises(ValueError):
        build_manual_layout(job, [ManualPlacement(item_index=5, x_mm=0, y_mm=0, rotation_deg=0)])
```

- [ ] **Step 2: Uruchom test — ma NIE przejść**

Run: `cd ~/summa-cut && .venv/bin/python -m pytest tests/test_manual_layout.py -v`
Expected: FAIL z `ModuleNotFoundError: No module named 'summa_cut.manual_layout'`

- [ ] **Step 3: Zaimplementuj moduł**

Utwórz `summa_cut/manual_layout.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from .models import JobSettings, LayoutResult, Placement, RectMM


@dataclass
class ManualPlacement:
    """Jedna ręcznie ustawiona instancja użytku na arkuszu.

    `item_index` = indeks w `job.montage_items` (= `montage_item_index` placementu).
    `x_mm`/`y_mm` = lewy-GÓRNY róg (spójnie z semantyką `Placement` w eksporcie).
    `rotation_deg` = 0/90/180/270.
    """
    item_index: int
    x_mm: float
    y_mm: float
    rotation_deg: int = 0


def _work_area(job: JobSettings) -> RectMM:
    return RectMM(
        x_mm=job.opos_spec.side_offset_mm,
        y_mm=job.opos_spec.top_offset_mm,
        width_mm=max(job.sheet_spec.width_mm - 2 * job.opos_spec.side_offset_mm, 0.0),
        height_mm=max(
            job.sheet_spec.height_mm - job.opos_spec.top_offset_mm - job.opos_spec.bottom_offset_mm,
            0.0,
        ),
    )


def build_manual_layout(job: JobSettings, placements: list[ManualPlacement]) -> LayoutResult:
    """Składa LayoutResult wprost z ręcznych pozycji (bez auto-nestingu).

    Footprint placementu = rozmiar strony użytku, zamieniony przy 90°/270°."""
    out: list[Placement] = []
    for mp in placements:
        if not (0 <= mp.item_index < len(job.montage_items)):
            raise ValueError(f"Nieprawidłowy indeks użytku: {mp.item_index}")
        w, h = job.montage_items[mp.item_index].print_page_size_mm
        if mp.rotation_deg in (90, 270):
            w, h = h, w
        out.append(Placement(
            x_mm=mp.x_mm, y_mm=mp.y_mm, width_mm=w, height_mm=h,
            rotation_deg=mp.rotation_deg, row=0, column=0, group=0,
            montage_item_index=mp.item_index,
        ))
    return LayoutResult(
        placements=out,
        count=len(out),
        requested_count=len(out),
        work_area_rect=_work_area(job),
        sheet_rect=RectMM(0.0, 0.0, job.sheet_spec.width_mm, job.sheet_spec.height_mm),
    )
```

- [ ] **Step 4: Uruchom test — ma przejść**

Run: `cd ~/summa-cut && .venv/bin/python -m pytest tests/test_manual_layout.py -v`
Expected: PASS (4 testy)

- [ ] **Step 5: Commit**

```bash
cd ~/summa-cut && git add summa_cut/manual_layout.py tests/test_manual_layout.py
git commit -m "feat(manual): build_manual_layout — ręczne pozycje → LayoutResult

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: `validate_manual_placements` — bramka nachodzenia / poza OPOS

Walidacja geometryczna gotowego `LayoutResult`: żadna instancja nie może wychodzić poza obszar roboczy OPOS ani nachodzić na inną. Zwraca listę komunikatów po polsku (pusta = OK).

**Files:**
- Modify: `summa_cut/manual_layout.py`
- Test: `tests/test_manual_layout.py`

- [ ] **Step 1: Dopisz testy walidacji**

Dopisz na końcu `tests/test_manual_layout.py`:

```python
from summa_cut.manual_layout import validate_manual_placements


def test_validate_ok_when_inside_and_disjoint():
    job = _job([_item(40, 30, 0), _item(40, 30, 1)])
    layout = build_manual_layout(job, [
        ManualPlacement(0, 20.0, 50.0, 0),
        ManualPlacement(1, 80.0, 50.0, 0),
    ])
    assert validate_manual_placements(job, layout) == []


def test_validate_flags_out_of_work_area():
    job = _job([_item(40, 30, 0)])
    # y=0 jest powyżej górnego offsetu OPOS (top=40) → poza obszarem
    layout = build_manual_layout(job, [ManualPlacement(0, 20.0, 0.0, 0)])
    problems = validate_manual_placements(job, layout)
    assert problems and any("poza" in p.lower() for p in problems)


def test_validate_flags_overlap():
    job = _job([_item(40, 30, 0), _item(40, 30, 1)])
    layout = build_manual_layout(job, [
        ManualPlacement(0, 50.0, 60.0, 0),
        ManualPlacement(1, 60.0, 70.0, 0),   # nachodzi na pierwszy
    ])
    problems = validate_manual_placements(job, layout)
    assert problems and any("nachodz" in p.lower() for p in problems)
```

- [ ] **Step 2: Uruchom testy — mają NIE przejść**

Run: `cd ~/summa-cut && .venv/bin/python -m pytest tests/test_manual_layout.py -k validate -v`
Expected: FAIL z `ImportError: cannot import name 'validate_manual_placements'`

- [ ] **Step 3: Zaimplementuj walidację**

Dopisz do `summa_cut/manual_layout.py`:

```python
_EPS = 0.01  # mm — tolerancja na błąd zmiennoprzecinkowy


def _rects_overlap(a: Placement, b: Placement) -> bool:
    return (
        a.x_mm < b.x_mm + b.width_mm - _EPS
        and b.x_mm < a.x_mm + a.width_mm - _EPS
        and a.y_mm < b.y_mm + b.height_mm - _EPS
        and b.y_mm < a.y_mm + a.height_mm - _EPS
    )


def validate_manual_placements(job: JobSettings, layout: LayoutResult) -> list[str]:
    """Zwraca listę problemów (pustą, gdy układ jest poprawny).

    Reguły: każda instancja w obszarze roboczym OPOS; brak nachodzenia."""
    problems: list[str] = []
    wa = layout.work_area_rect
    for i, p in enumerate(layout.placements, start=1):
        if (
            p.x_mm < wa.x_mm - _EPS
            or p.y_mm < wa.y_mm - _EPS
            or p.x_mm + p.width_mm > wa.x_mm + wa.width_mm + _EPS
            or p.y_mm + p.height_mm > wa.y_mm + wa.height_mm + _EPS
        ):
            problems.append(f"Element #{i} wychodzi poza obszar OPOS.")
    placements = layout.placements
    for i in range(len(placements)):
        for j in range(i + 1, len(placements)):
            if _rects_overlap(placements[i], placements[j]):
                problems.append(f"Elementy #{i + 1} i #{j + 1} nachodzą na siebie.")
    return problems
```

- [ ] **Step 4: Uruchom testy — mają przejść**

Run: `cd ~/summa-cut && .venv/bin/python -m pytest tests/test_manual_layout.py -v`
Expected: PASS (7 testów)

- [ ] **Step 5: Commit**

```bash
cd ~/summa-cut && git add summa_cut/manual_layout.py tests/test_manual_layout.py
git commit -m "feat(manual): validate_manual_placements — bramka nachodzenia i obszaru OPOS

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Parametry i gałąź manualna w `build_job`

`JobParams` dostaje pola trybu manualnego, a `build_job` — wczesną gałąź `_build_manual_job`, która buduje `montage_items` z palety (każdy wgrany PDF 2-str.: druk=str.0, wykrojnik=str.1) i zwraca `JobSettings` gotowe pod `build_manual_layout`. Gałąź jest PRZED walidacją rozmiaru użytku, więc manual nie wymaga `item_w/item_h`.

**Files:**
- Modify: `web/job_builder.py`
- Test: `tests/test_web_job_builder.py`

- [ ] **Step 1: Napisz test gałęzi manualnej**

Dopisz do `tests/test_web_job_builder.py` (użyj istniejących w pliku pomocników do sesji/uploadu; jeśli ich nie ma, wzór poniżej jest samowystarczalny):

```python
def test_build_manual_job_builds_montage_items_from_palette(tmp_path):
    import fitz
    from summa_cut.pdf_io import MM_PER_POINT, read_pdf_info
    from web.job_builder import JobParams, build_job
    from web.sessions import SessionStore

    PT = 1.0 / MM_PER_POINT
    # dwustronicowy PDF: str.0 = druk, str.1 = wykrojnik
    doc = fitz.open()
    doc.new_page(width=40 * PT, height=30 * PT)
    doc.new_page(width=40 * PT, height=30 * PT)
    path = tmp_path / "para.pdf"
    doc.save(path); doc.close()

    store = SessionStore(base_dir=tmp_path / "sess")
    session = store.create()
    session.uploads["para.pdf"] = read_pdf_info(str(path))

    params = JobParams(
        print_upload="para.pdf", item_w_mm=0, item_h_mm=0,
        manual_free_enabled=True,
        manual_items=[{"upload": "para.pdf"}],
        manual_placements=[{"item_index": 0, "x_mm": 20, "y_mm": 50, "rotation_deg": 0}],
        opos_side_offset_mm=10, opos_bottom_offset_mm=10, opos_top_offset_mm=40,
    )
    job = build_job(params, session)
    assert len(job.montage_items) == 1
    item = job.montage_items[0]
    assert item.print_page.page_index == 0
    assert item.cut_page.page_index == 1
    assert item.print_page_size_mm == (40.0, 30.0)
```

- [ ] **Step 2: Uruchom test — ma NIE przejść**

Run: `cd ~/summa-cut && .venv/bin/python -m pytest tests/test_web_job_builder.py::test_build_manual_job_builds_montage_items_from_palette -v`
Expected: FAIL (pydantic: nieznane pola `manual_free_enabled` itd.)

- [ ] **Step 3: Dodaj klasy parametrów manualnych**

W `web/job_builder.py`, PRZED klasą `JobParams`, dodaj:

```python
class ManualItemParams(BaseModel):
    upload: str


class ManualPlacementParams(BaseModel):
    item_index: int
    x_mm: float
    y_mm: float
    rotation_deg: int = 0
```

- [ ] **Step 4: Dodaj pola do `JobParams`**

W klasie `JobParams`, tuż po polu `montage: list[MontageItemParams] = Field(default_factory=list)`, dodaj:

```python
    manual_free_enabled: bool = False
    manual_items: list[ManualItemParams] = Field(default_factory=list)
    manual_placements: list[ManualPlacementParams] = Field(default_factory=list)
```

- [ ] **Step 5: Dodaj `_build_manual_job` i wczesną gałąź**

W `web/job_builder.py` dodaj funkcję `_build_manual_job` (obok `_build_special_job`):

```python
def _build_manual_job(params: JobParams, session: Session) -> JobSettings:
    items: list[MontageItem] = []
    for idx, mi in enumerate(params.manual_items):
        p_info = _require_page(session, mi.upload, 0, f"druk palety #{idx + 1}")
        c_info = _require_page(session, mi.upload, 1, f"wykrojnik palety #{idx + 1}")
        items.append(MontageItem(
            label=mi.upload,
            print_page=SelectedPage(p_info.path, 0),
            cut_page=SelectedPage(c_info.path, 1),
            print_page_size_mm=p_info.page_sizes_mm[0],
            cut_page_size_mm=c_info.page_sizes_mm[1],
            print_content_size_mm=p_info.page_content_sizes_mm[0],
            cut_content_size_mm=c_info.page_content_sizes_mm[1],
            print_content_bbox_pt=p_info.page_content_boxes_pt[0],
            cut_content_bbox_pt=c_info.page_content_boxes_pt[1],
            quantity=1,
        ))
    base = items[0] if items else None
    empty_page = SelectedPage("", 0)
    zero_bbox = (0.0, 0.0, 0.0, 0.0)
    return JobSettings(
        print_page=base.print_page if base else empty_page,
        cut_page=base.cut_page if base else empty_page,
        print_page_size_mm=base.print_page_size_mm if base else (0.0, 0.0),
        cut_page_size_mm=base.cut_page_size_mm if base else (0.0, 0.0),
        print_content_size_mm=base.print_content_size_mm if base else (0.0, 0.0),
        cut_content_size_mm=base.cut_content_size_mm if base else (0.0, 0.0),
        print_content_bbox_pt=base.print_content_bbox_pt if base else zero_bbox,
        cut_content_bbox_pt=base.cut_content_bbox_pt if base else zero_bbox,
        sheet_spec=SheetSpec(params.sheet_w_mm, params.sheet_h_mm),
        item_spec=ItemSpec(0.0, 0.0, False),
        gap_enabled=True,
        gap_mm=0.0,
        generate_cut_grid=False,
        montage_items=items,
        opos_spec=OposSpec(params.opos_side_offset_mm, params.opos_bottom_offset_mm, params.opos_top_offset_mm),
    )
```

Następnie w `build_job`, na SAMYM POCZĄTKU (przed walidacją `item_w_mm/item_h_mm`), dodaj:

```python
    if params.manual_free_enabled:
        return _build_manual_job(params, session)
```

(Wstaw tę gałąź jako pierwszą instrukcję w `build_job`, przed `if not params.special_enabled and (...)`.)

- [ ] **Step 6: Uruchom test — ma przejść**

Run: `cd ~/summa-cut && .venv/bin/python -m pytest tests/test_web_job_builder.py::test_build_manual_job_builds_montage_items_from_palette -v`
Expected: PASS

- [ ] **Step 7: Cały plik job_builder (brak regresji)**

Run: `cd ~/summa-cut && .venv/bin/python -m pytest tests/test_web_job_builder.py -q`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
cd ~/summa-cut && git add web/job_builder.py tests/test_web_job_builder.py
git commit -m "feat(manual): parametry trybu manualnego + gałąź build_job (paleta par druk/wykrojnik)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Wpięcie w serwer + bramka walidacji przy generowaniu

`set_job` i `_job_and_layout` używają wspólnego `_layout_for` rozgałęziającego manual/auto. `/api/generate` w trybie manualnym uruchamia `validate_manual_placements` i przy problemach zwraca 400 (nie wypuszcza wadliwego arkusza).

**Files:**
- Modify: `web/server.py`
- Test: `tests/test_web_api.py`

- [ ] **Step 1: Napisz testy end-to-end (poprawny + bramka)**

Dopisz do `tests/test_web_api.py`:

```python
def _two_page_pdf_bytes(w_mm=40.0, h_mm=30.0) -> bytes:
    doc = fitz.open()
    doc.new_page(width=w_mm / MM_PER_POINT, height=h_mm / MM_PER_POINT)
    doc.new_page(width=w_mm / MM_PER_POINT, height=h_mm / MM_PER_POINT)
    data = doc.tobytes(); doc.close()
    return data


def _manual_job_body(rotation=0, x=20.0, y=50.0, second_x=90.0, second_y=50.0):
    return {
        "print_upload": "para.pdf", "item_w_mm": 0, "item_h_mm": 0,
        "sheet_w_mm": 330, "sheet_h_mm": 480,
        "opos_side_offset_mm": 10, "opos_bottom_offset_mm": 10, "opos_top_offset_mm": 40,
        "manual_free_enabled": True,
        "manual_items": [{"upload": "para.pdf"}],
        "manual_placements": [
            {"item_index": 0, "x_mm": x, "y_mm": y, "rotation_deg": rotation},
            {"item_index": 0, "x_mm": second_x, "y_mm": second_y, "rotation_deg": 0},
        ],
    }


def test_manual_generate_produces_two_pdfs(tmp_path):
    c = _client(tmp_path)
    c.post("/api/session")
    c.post("/api/upload", files={"file": ("para.pdf", _two_page_pdf_bytes(), "application/pdf")})
    assert c.post("/api/job", json=_manual_job_body()).status_code == 200
    r = c.post("/api/generate", json={"base_name": "manual"})
    assert r.status_code == 200
    body = r.json()
    assert body["print_name"].endswith("_druk.pdf")
    assert body["cut_name"].endswith("_wykrojnik.pdf")
    assert c.get(f"/api/download/print").status_code == 200
    assert c.get(f"/api/download/cut").status_code == 200


def test_manual_generate_blocked_on_overlap(tmp_path):
    c = _client(tmp_path)
    c.post("/api/session")
    c.post("/api/upload", files={"file": ("para.pdf", _two_page_pdf_bytes(), "application/pdf")})
    # drugi element w tym samym miejscu → nachodzenie
    body = _manual_job_body(second_x=25.0, second_y=55.0)
    assert c.post("/api/job", json=body).status_code == 200
    r = c.post("/api/generate", json={"base_name": "manual"})
    assert r.status_code == 400
    assert "nachodz" in r.json()["detail"].lower()
```

- [ ] **Step 2: Uruchom testy — mają NIE przejść**

Run: `cd ~/summa-cut && .venv/bin/python -m pytest tests/test_web_api.py -k manual -v`
Expected: FAIL — `/api/job` zwróci 500/400, bo `set_job` woła `compute_layout` na jobie manualnym (brak `item_spec`), a bramki brak.

- [ ] **Step 3: Dodaj helper `_layout_for` i rozgałęzienie**

W `web/server.py` dodaj import na górze (obok pozostałych importów `from summa_cut...`):

```python
from summa_cut.manual_layout import ManualPlacement, build_manual_layout, validate_manual_placements
```

`build_manual_layout` przyjmuje `ManualPlacement` (dataclass z `summa_cut.manual_layout`), a params trzyma `ManualPlacementParams` (pydantic) — helper poniżej mapuje jedno na drugie.

Następnie, wewnątrz `create_app`, dodaj funkcję pomocniczą (przed `set_job`):

```python
    def _layout_for(job, params: JobParams):
        if params.manual_free_enabled:
            mps = [
                ManualPlacement(mp.item_index, mp.x_mm, mp.y_mm, mp.rotation_deg)
                for mp in params.manual_placements
            ]
            return build_manual_layout(job, mps)
        return compute_layout(job)
```

- [ ] **Step 4: Użyj `_layout_for` w `set_job`**

W `set_job` zamień:

```python
            job = build_job(params, session)
            layout = compute_layout(job)
```

na:

```python
            job = build_job(params, session)
            layout = _layout_for(job, params)
```

- [ ] **Step 5: Użyj `_layout_for` w `_job_and_layout` i zwróć `params`**

Zamień treść `_job_and_layout` na:

```python
    def _job_and_layout(session: Session):
        if session.job_params is None:
            raise HTTPException(status_code=400, detail="Najpierw ustaw zlecenie (/api/job).")
        params = JobParams(**session.job_params)
        job = build_job(params, session)
        return job, _layout_for(job, params), params
```

Zaktualizuj oba miejsca wywołania, które dziś rozpakowują dwie wartości:

W `preview`:
```python
        job, layout, _params = _job_and_layout(session)
```

W `generate`:
```python
        job, layout, params = _job_and_layout(session)
```

- [ ] **Step 6: Dodaj bramkę walidacji w `generate`**

W `generate`, zaraz po `job, layout, params = _job_and_layout(session)` a przed `docs = generate_output_docs(...)`, dodaj:

```python
        if params.manual_free_enabled:
            problems = validate_manual_placements(job, layout)
            if problems:
                raise HTTPException(status_code=400, detail="; ".join(problems))
```

- [ ] **Step 7: Uruchom testy manualne — mają przejść**

Run: `cd ~/summa-cut && .venv/bin/python -m pytest tests/test_web_api.py -k manual -v`
Expected: PASS (2 testy)

- [ ] **Step 8: Cały pakiet web (brak regresji)**

Run: `cd ~/summa-cut && .venv/bin/python -m pytest tests/test_web_api.py tests/test_web_preview.py -q`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
cd ~/summa-cut && git add web/server.py tests/test_web_api.py
git commit -m "feat(manual): wpięcie w serwer (_layout_for) + bramka walidacji w /api/generate

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: HTML — przełącznik trybu i panel manualny

Dodaj checkbox trybu manualnego, kontener palety i kanwę SVG. Test frontendowy pilnuje obecności nowych id.

**Files:**
- Modify: `web/static/index.html`
- Test: `tests/test_web_frontend.py`

- [ ] **Step 1: Dodaj nowe id do wymaganych w teście**

W `tests/test_web_frontend.py`, w liście `REQUIRED_IDS`, dopisz na końcu:

```python
    "manual-free", "manual-panel", "manual-palette", "manual-canvas",
    "manual-hint",
```

- [ ] **Step 2: Uruchom test — ma NIE przejść**

Run: `cd ~/summa-cut && .venv/bin/python -m pytest tests/test_web_frontend.py::test_index_has_required_element_ids -v`
Expected: FAIL — `brak id w index.html: ['manual-free', ...]`

- [ ] **Step 3: Dodaj przełącznik trybu**

W `web/static/index.html`, w `<fieldset>` z `<legend>Tryb</legend>`, po linii z `id="manual"` (siatka manualna) dodaj:

```html
        <label><input type="checkbox" id="manual-free"> tryb manualny (ręczna impozycja)</label>
```

- [ ] **Step 4: Dodaj panel manualny**

W `web/static/index.html`, bezpośrednio po `<fieldset>` „Montaż wielu użytków" (zamykający `</fieldset>`), dodaj:

```html
      <fieldset id="manual-panel" style="display:none">
        <legend>Tryb manualny</legend>
        <p id="manual-hint" class="muted">Kliknij użytek w palecie, aby dodać go na arkusz. Przeciągaj myszą; strzałki = przesuw, R = obrót 90°, D = duplikuj, Delete = usuń.</p>
        <div id="manual-palette" class="palette"></div>
        <div class="manual-canvas-wrap">
          <svg id="manual-canvas" xmlns="http://www.w3.org/2000/svg"></svg>
        </div>
      </fieldset>
```

- [ ] **Step 5: Uruchom test — ma przejść**

Run: `cd ~/summa-cut && .venv/bin/python -m pytest tests/test_web_frontend.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
cd ~/summa-cut && git add web/static/index.html tests/test_web_frontend.py
git commit -m "feat(manual): HTML — przełącznik trybu + panel (paleta + kanwa SVG)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: JS — stan trybu, przełączanie widoczności, paleta

Wprowadź `manualState`, obsługę przełącznika (chowanie pól auto-układu + pokazanie panelu), renderowanie palety z wgranych PDF-ów 2-stronicowych i dodawanie instancji kliknięciem. Bez kanwy jeszcze (Task 8).

**Files:**
- Modify: `web/static/app.js`
- Weryfikacja: przeglądarka (brak runnera JS w repo)

- [ ] **Step 1: Dodaj stan i referencje**

W `web/static/app.js`, obok istniejącego `const special = {...}` (ok. linia 9), dodaj:

```javascript
const manualState = { enabled: false, items: [], placements: [], selected: null };
// items: [{ upload }]   placements: [{ itemIndex, xMm, yMm, rot, wMm, hMm }]
```

- [ ] **Step 2: Podepnij przełącznik trybu**

W funkcji `wireEvents()` (ok. linia 161) dodaj:

```javascript
  $("manual-free").addEventListener("change", onManualToggle);
```

- [ ] **Step 3: Zaimplementuj przełączanie widoczności**

Dodaj funkcje do `web/static/app.js`:

```javascript
// Fieldsety auto-układu chowane w trybie manualnym (po legendach).
function autoLayoutFieldsets() {
  const legends = ["Źródło (gdy bez montażu)", "Arkusz i użytek (mm)", "Tryb", "Montaż wielu użytków"];
  return Array.from(document.querySelectorAll("#controls fieldset")).filter((fs) => {
    const lg = fs.querySelector("legend");
    return lg && legends.includes(lg.textContent.trim());
  });
}

function onManualToggle() {
  manualState.enabled = $("manual-free").checked;
  $("manual-panel").style.display = manualState.enabled ? "" : "none";
  for (const fs of autoLayoutFieldsets()) {
    // „Tryb" zostawiamy widoczny (jest w nim przełącznik manualny); reszta znika.
    const isModeFs = fs.querySelector("legend").textContent.trim() === "Tryb";
    if (!isModeFs) fs.style.display = manualState.enabled ? "none" : "";
  }
  if (manualState.enabled) { renderPalette(); renderCanvas(); }
}
```

- [ ] **Step 4: Zaimplementuj paletę**

Dodaj do `web/static/app.js`:

```javascript
// Paleta = wgrane PDF-y mające >= 2 strony (str.0=druk, str.1=wykrojnik).
function renderPalette() {
  const box = $("manual-palette");
  box.innerHTML = "";
  const names = Object.keys(uploads).filter((n) => (uploads[n] || 0) >= 2);
  if (names.length === 0) {
    box.innerHTML = '<span class="muted">Wgraj PDF 2-stronicowy (str.1 druk, str.2 wykrojnik).</span>';
    return;
  }
  names.forEach((name) => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "palette-chip";
    chip.textContent = name;
    chip.addEventListener("click", () => addInstance(name));
    box.appendChild(chip);
  });
}
```

- [ ] **Step 5: Zaimplementuj dodawanie instancji**

`uploadInfo(name)` musi dać rozmiar strony 0 w mm. W repo `uploads[name]` trzyma tylko liczbę stron; potrzebny pełny rozmiar. Rozszerz cache uploadów: w miejscu gdzie po uploadzie zapisywane jest `uploads[info.name] = info.page_count;` (ok. linia 209) zmień na przechowywanie całego info równolegle:

```javascript
      uploads[info.name] = info.page_count;
      uploadsInfo[info.name] = info;   // pełne info (page_sizes_mm itd.)
```

oraz zadeklaruj obok `const uploads` (na górze pliku):

```javascript
const uploadsInfo = {};   // name -> pełny obiekt z /api/upload (page_sizes_mm, ...)
```

Następnie dodaj:

```javascript
function itemIndexForUpload(name) {
  let idx = manualState.items.findIndex((it) => it.upload === name);
  if (idx === -1) { manualState.items.push({ upload: name }); idx = manualState.items.length - 1; }
  return idx;
}

function addInstance(name) {
  const info = uploadsInfo[name];
  if (!info) return;
  const [wMm, hMm] = info.page_sizes_mm[0];
  const itemIndex = itemIndexForUpload(name);
  // domyślnie w środku obszaru roboczego OPOS
  const wa = workAreaMm();
  const xMm = wa.x + Math.max((wa.w - wMm) / 2, 0);
  const yMm = wa.y + Math.max((wa.h - hMm) / 2, 0);
  manualState.placements.push({ itemIndex, xMm, yMm, rot: 0, wMm, hMm });
  manualState.selected = manualState.placements.length - 1;
  renderCanvas();
}

function workAreaMm() {
  const sw = parseFloat($("sheet-w").value) || 0;
  const sh = parseFloat($("sheet-h").value) || 0;
  const side = parseFloat($("opos-side").value) || 0;
  const top = parseFloat($("opos-top").value) || 0;
  const bottom = parseFloat($("opos-bottom").value) || 0;
  return { x: side, y: top, w: Math.max(sw - 2 * side, 0), h: Math.max(sh - top - bottom, 0) };
}
```

- [ ] **Step 6: Dodaj tymczasowy stub `renderCanvas`**

Aby strona działała przed Task 8, dodaj (zostanie zastąpiony w Task 8):

```javascript
function renderCanvas() { /* implementacja w Task 8 */ }
```

- [ ] **Step 7: Weryfikacja w przeglądarce**

Uruchom lokalnie i sprawdź, że przełącznik chowa pola i pokazuje paletę:

Run: `cd ~/summa-cut && .venv/bin/python -m uvicorn web.app:app --port 8899 &`, potem otwórz `http://localhost:8899` (uwaga: `app.py`/`run.sh` to wersja DESKTOP Qt — do weryfikacji web zawsze `web.app:app`).
Expected: zaznaczenie „tryb manualny" chowa fieldsety źródła/arkusza/montażu, pokazuje panel; po wgraniu 2-str. PDF paleta pokazuje jego nazwę; klik dodaje instancję do `manualState.placements` (sprawdź w konsoli: `manualState.placements.length`).

Zatrzymaj serwer: `kill %1`.

- [ ] **Step 8: Nie psujemy testów Pythona**

Run: `cd ~/summa-cut && .venv/bin/python -m pytest tests/test_web_frontend.py tests/test_web_no_qt.py -q`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
cd ~/summa-cut && git add web/static/app.js
git commit -m "feat(manual): JS — stan trybu, przełączanie pól, paleta i dodawanie instancji

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 8: JS — kanwa SVG, przeciąganie, obwódka nachodzenia/poza-OPOS

Renderowanie kanwy (arkusz + obszar OPOS + instancje) w skali mm→px, przeciąganie myszą, zaznaczanie, czerwona obwódka gdy instancja nachodzi na inną lub wychodzi poza obszar. Detekcja liczona w JS (te same reguły co serwer).

**Files:**
- Modify: `web/static/app.js`
- Modify: `web/static/style.css`
- Weryfikacja: przeglądarka

- [ ] **Step 1: Style kanwy i palety**

Dopisz do `web/static/style.css`:

```css
.palette { display: flex; flex-wrap: wrap; gap: 6px; margin: 6px 0; }
.palette-chip { padding: 4px 8px; border: 1px solid #888; border-radius: 4px; cursor: pointer; background: #f4f4f4; }
.manual-canvas-wrap { overflow: auto; border: 1px solid #ccc; max-height: 70vh; }
#manual-canvas { display: block; background: #fff; }
.mc-item { fill: rgba(40, 90, 200, 0.12); stroke: #285ac8; stroke-width: 1; cursor: move; }
.mc-item.sel { stroke-width: 2; }
.mc-item.bad { fill: rgba(210, 40, 40, 0.15); stroke: #d22828; }
.mc-work { fill: none; stroke: #2a2; stroke-dasharray: 4 3; }
.mc-sheet { fill: #fafafa; stroke: #333; }
.mc-label { font: 10px sans-serif; fill: #223; pointer-events: none; }
```

- [ ] **Step 2: Zastąp stub `renderCanvas` pełną implementacją**

W `web/static/app.js` zastąp `function renderCanvas() { /* ... */ }` przez:

```javascript
const MC_SCALE = 2.2;   // px na mm (podgląd)
const SVGNS = "http://www.w3.org/2000/svg";

function mcRectBad(p, others, wa) {
  const outside = p.xMm < wa.x - 0.01 || p.yMm < wa.y - 0.01
    || p.xMm + p.wMm > wa.x + wa.w + 0.01 || p.yMm + p.hMm > wa.y + wa.h + 0.01;
  if (outside) return true;
  return others.some((o) => o !== p
    && p.xMm < o.xMm + o.wMm - 0.01 && o.xMm < p.xMm + p.wMm - 0.01
    && p.yMm < o.yMm + o.hMm - 0.01 && o.yMm < p.yMm + p.hMm - 0.01);
}

function renderCanvas() {
  const svg = $("manual-canvas");
  if (!svg) return;
  svg.innerHTML = "";
  const sw = parseFloat($("sheet-w").value) || 0;
  const sh = parseFloat($("sheet-h").value) || 0;
  svg.setAttribute("width", sw * MC_SCALE);
  svg.setAttribute("height", sh * MC_SCALE);
  const add = (tag, attrs, cls) => {
    const el = document.createElementNS(SVGNS, tag);
    for (const k in attrs) el.setAttribute(k, attrs[k]);
    if (cls) el.setAttribute("class", cls);
    svg.appendChild(el);
    return el;
  };
  add("rect", { x: 0, y: 0, width: sw * MC_SCALE, height: sh * MC_SCALE }, "mc-sheet");
  const wa = workAreaMm();
  add("rect", { x: wa.x * MC_SCALE, y: wa.y * MC_SCALE, width: wa.w * MC_SCALE, height: wa.h * MC_SCALE }, "mc-work");

  manualState.placements.forEach((p, i) => {
    const bad = mcRectBad(p, manualState.placements, wa);
    let cls = "mc-item";
    if (i === manualState.selected) cls += " sel";
    if (bad) cls += " bad";
    const rect = add("rect", {
      x: p.xMm * MC_SCALE, y: p.yMm * MC_SCALE,
      width: p.wMm * MC_SCALE, height: p.hMm * MC_SCALE,
      "data-idx": i,
    }, cls);
    rect.addEventListener("pointerdown", (e) => mcPointerDown(e, i));
    add("text", { x: (p.xMm + 2) * MC_SCALE, y: (p.yMm + 4) * MC_SCALE }, "mc-label")
      .textContent = `#${i + 1}${p.rot ? " " + p.rot + "°" : ""}`;
  });
}
```

- [ ] **Step 3: Przeciąganie myszą**

Dodaj do `web/static/app.js`:

```javascript
let mcDrag = null;   // { idx, startX, startY, origX, origY }

function mcPointerDown(e, idx) {
  e.preventDefault();
  manualState.selected = idx;
  const p = manualState.placements[idx];
  mcDrag = { idx, startX: e.clientX, startY: e.clientY, origX: p.xMm, origY: p.yMm };
  $("manual-canvas").setPointerCapture?.(e.pointerId);
  renderCanvas();
}

function mcPointerMove(e) {
  if (!mcDrag) return;
  const p = manualState.placements[mcDrag.idx];
  p.xMm = Math.round((mcDrag.origX + (e.clientX - mcDrag.startX) / MC_SCALE) * 10) / 10;
  p.yMm = Math.round((mcDrag.origY + (e.clientY - mcDrag.startY) / MC_SCALE) * 10) / 10;
  renderCanvas();
}

function mcPointerUp() { mcDrag = null; }
```

Podepnij w `wireEvents()`:

```javascript
  $("manual-canvas").addEventListener("pointermove", mcPointerMove);
  $("manual-canvas").addEventListener("pointerup", mcPointerUp);
  $("manual-canvas").addEventListener("pointerleave", mcPointerUp);
```

- [ ] **Step 4: Weryfikacja w przeglądarce**

Run: `cd ~/summa-cut && .venv/bin/python -m uvicorn web.app:app --port 8899 &`, otwórz `http://localhost:8899`.
Expected: po włączeniu trybu i dodaniu 2 instancji widać arkusz, zielony obrys OPOS i prostokąty; przeciąganie działa; nałożone na siebie / wystające prostokąty robią się czerwone; ustawione rozłącznie w obszarze — niebieskie. Zatrzymaj: `kill %1`.

- [ ] **Step 5: Commit**

```bash
cd ~/summa-cut && git add web/static/app.js web/static/style.css
git commit -m "feat(manual): kanwa SVG — render, przeciąganie, czerwona obwódka nachodzenia/poza-OPOS

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 9: JS — obrót 90°, duplikuj, usuń, przesuw strzałkami

Klawiatura na zaznaczonej instancji: R = obrót 90° (0→90→180→270→0, zamiana wMm/hMm), D = duplikuj (z małym przesunięciem), Delete/Backspace = usuń, strzałki = przesuw o 1 mm (Shift = 10 mm).

**Files:**
- Modify: `web/static/app.js`
- Weryfikacja: przeglądarka

- [ ] **Step 1: Obsługa klawiatury**

Dodaj do `web/static/app.js`:

```javascript
function mcRotateSelected() {
  const p = manualState.placements[manualState.selected];
  if (!p) return;
  p.rot = (p.rot + 90) % 360;
  [p.wMm, p.hMm] = [p.hMm, p.wMm];
  renderCanvas();
}

function mcDuplicateSelected() {
  const p = manualState.placements[manualState.selected];
  if (!p) return;
  manualState.placements.push({ ...p, xMm: Math.round((p.xMm + 5) * 10) / 10, yMm: Math.round((p.yMm + 5) * 10) / 10 });
  manualState.selected = manualState.placements.length - 1;
  renderCanvas();
}

function mcDeleteSelected() {
  if (manualState.selected == null) return;
  manualState.placements.splice(manualState.selected, 1);
  manualState.selected = null;
  renderCanvas();
}

function mcNudge(dx, dy) {
  const p = manualState.placements[manualState.selected];
  if (!p) return;
  p.xMm = Math.round((p.xMm + dx) * 10) / 10;
  p.yMm = Math.round((p.yMm + dy) * 10) / 10;
  renderCanvas();
}

function mcKey(e) {
  if (!manualState.enabled || manualState.selected == null) return;
  const step = e.shiftKey ? 10 : 1;
  const map = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] };
  if (map[e.key]) { e.preventDefault(); mcNudge(...map[e.key]); return; }
  if (e.key === "r" || e.key === "R") { e.preventDefault(); mcRotateSelected(); }
  else if (e.key === "d" || e.key === "D") { e.preventDefault(); mcDuplicateSelected(); }
  else if (e.key === "Delete" || e.key === "Backspace") { e.preventDefault(); mcDeleteSelected(); }
}
```

Podepnij w `wireEvents()`:

```javascript
  document.addEventListener("keydown", mcKey);
```

- [ ] **Step 2: Weryfikacja w przeglądarce**

Run: `cd ~/summa-cut && .venv/bin/python -m uvicorn web.app:app --port 8899 &`, otwórz stronę.
Expected: zaznacz instancję → R obraca (prostokąt zmienia proporcje, etykieta pokazuje kąt), D duplikuje z przesunięciem, Delete usuwa, strzałki przesuwają (Shift szybciej). Zatrzymaj: `kill %1`.

- [ ] **Step 3: Commit**

```bash
cd ~/summa-cut && git add web/static/app.js
git commit -m "feat(manual): klawiatura — obrót 90°, duplikuj, usuń, przesuw strzałkami

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 10: JS — wysłanie zlecenia manualnego i generowanie

Cały ruch do `/api/job` przechodzi przez jeden lejek `collectParams()` (używany przez `applyJob`, `updatePreview` i pośrednio `doGenerate`, który sam woła `applyJob()` przed generowaniem). Wystarczy strażnik na początku `collectParams()` zwracający payload manualny. Obsługa błędu 400 z bramki już istnieje (`doGenerate` → `showError((await r.json()).detail)`), więc nic tam nie zmieniamy.

**Files:**
- Modify: `web/static/app.js`
- Weryfikacja: przeglądarka + istniejące testy API

- [ ] **Step 1: Dodaj builder payloadu manualnego**

W `web/static/app.js` dodaj funkcję (obok `collectParams`, ok. linia 423):

```javascript
function manualJobBody() {
  return {
    print_upload: manualState.items[0] ? manualState.items[0].upload : "",
    print_page: 0, cut_page: 0,
    item_w_mm: 0, item_h_mm: 0,
    sheet_w_mm: parseFloat($("sheet-w").value),
    sheet_h_mm: parseFloat($("sheet-h").value),
    opos_side_offset_mm: parseFloat($("opos-side").value),
    opos_bottom_offset_mm: parseFloat($("opos-bottom").value),
    opos_top_offset_mm: parseFloat($("opos-top").value),
    manual_free_enabled: true,
    manual_items: manualState.items.map((it) => ({ upload: it.upload })),
    manual_placements: manualState.placements.map((p) => ({
      item_index: p.itemIndex, x_mm: p.xMm, y_mm: p.yMm, rotation_deg: p.rot,
    })),
  };
}
```

- [ ] **Step 2: Dodaj strażnika na początku `collectParams()`**

W `collectParams()` (ok. linia 423), jako PIERWSZĄ instrukcję funkcji, dodaj:

```javascript
  if (manualState.enabled) return manualJobBody();
```

To sprawia, że `applyJob`, podgląd i `doGenerate` w trybie manualnym wysyłają payload manualny. Bramka 400 z `/api/generate` jest już obsłużona przez `showError` w `doGenerate` — bez zmian.

- [ ] **Step 3: Weryfikacja end-to-end w przeglądarce**

Run: `cd ~/summa-cut && .venv/bin/python -m uvicorn web.app:app --port 8899 &`, otwórz stronę.
Expected:
1. Wgraj 2-str. PDF, włącz tryb manualny, dodaj 2 rozłączne instancje → „Generuj" tworzy dwa PDF-y; pobierz druk i wykrojnik, otwórz — pozycje zgadzają się z kanwą, wykrojnik ma OPOS.
2. Nałóż instancje → „Generuj" pokazuje błąd „…nachodzą…" i nie generuje.
Zatrzymaj: `kill %1`.

- [ ] **Step 4: Pełny pakiet testów (regresja całości)**

Run: `cd ~/summa-cut && .venv/bin/python -m pytest -q`
Expected: PASS (wszystkie ~83 dotychczasowe + nowe z tego planu)

- [ ] **Step 5: Commit**

```bash
cd ~/summa-cut && git add web/static/app.js
git commit -m "feat(manual): wysyłka zlecenia manualnego do /api/job + obsługa bramki 400

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 11: Podbicie wersji assetów i dokumentacja

Wymuś odświeżenie JS/CSS w przeglądarce (cache) i dopisz krótką notkę o trybie do STATUS/README.

**Files:**
- Modify: `web/static/index.html` (parametry `?v=N` przy `app.js`/`style.css`)
- Modify: `STATUS.md`

- [ ] **Step 1: Podbij `?v=` przy assetach**

W `web/static/index.html` znajdź odwołania `app.js` i `style.css`. Jeśli mają `?v=N`, zwiększ N o 1; jeśli nie mają, dodaj `?v=1` (np. `href="/static/style.css?v=1"`, `src="/static/app.js?v=1"`).

- [ ] **Step 2: Dopisz notkę do STATUS.md**

Dodaj akapit:

```markdown
## Tryb manualny (2026-07-21)

Impozycja ręczna w stylu PlaceIt: paleta wgranych PDF-ów 2-stronicowych
(str.1 druk, str.2 wykrojnik), kanwa SVG z przeciąganiem, obrotem 90°,
duplikacją i usuwaniem, czerwoną obwódką przy nachodzeniu/wyjściu poza OPOS.
Wyjście: dwa PDF-y (druk + wykrojnik z OPOS), przez istniejący eksport
(`build_manual_layout` → `generate_output_docs`). Bramka `/api/generate`
blokuje generowanie przy nachodzeniu lub wyjściu poza obszar OPOS.
```

- [ ] **Step 3: Testy frontendu (asset-refs) nadal zielone**

Run: `cd ~/summa-cut && .venv/bin/python -m pytest tests/test_web_frontend.py -q`
Expected: PASS (test `test_index_references_assets` sprawdza obecność `/static/app.js` i `/static/style.css` — parametr `?v=` nie przeszkadza).

- [ ] **Step 4: Commit**

```bash
cd ~/summa-cut && git add web/static/index.html STATUS.md
git commit -m "chore(manual): podbicie wersji assetów + notka w STATUS

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Uwaga o wdrożeniu (po zakończeniu planu)

Deploy jak dotąd (bez zmian): `rsync` na drukpol → `docker build -t summa-cut-web:local .` → `midclt call app.redeploy summa-cut`. JS/CSS wymagają podbitego `?v=` (Task 11). Najpierw pełne `pytest -q` lokalnie.
