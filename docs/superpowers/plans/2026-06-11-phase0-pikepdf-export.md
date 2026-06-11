# Phase 0 — Port eksportu na pikepdf (deduplikacja stempli) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Przyspieszyć `generate_output_docs` z ~47 s do <1 s przy setkach użytków, bez zmiany wyglądu wyniku (fidelity), żeby zapis w desktopie i przyszły web działały natychmiastowo.

**Architecture:** Wolny element to setki wywołań `show_pdf_page` (superliniowe). W jednolitej siatce wszystkie użytki rysują **identyczną zawartość** — różni je tylko pozycja. Renderujemy więc każdą unikalną „komórkę" (sygnatura: źródło+strona+bbox+rozmiar+obrót) **raz** istniejącą ścieżką `show_pdf_page` do małej strony-stempla, a następnie **pikepdf** osadza ten stempel jako Form XObject i powiela go przez czyste **przesunięcie** (translację) w każdej pozycji. Piksele pochodzą z tego samego renderera → fidelity ~dokładne; pikepdf robi tylko translację (w PDF dokładną). Kolejność warstw bez zmian: krata cięcia / stemple pod spodem, OPOS na wierzchu.

**Tech Stack:** Python, PyMuPDF (fitz) — render stempli + OPOS + krata; pikepdf — osadzenie i powielenie stempli; pytest — golden-image regresja + licznik wywołań.

---

## File Structure

- **Modify:** `summa_cut/export.py` — nowa ścieżka montażu w `generate_output_docs`; nowe funkcje pomocnicze (`_placement_signature`, `_render_cell_stamp`, `_assemble_with_pikepdf`). Publiczne API (`generate_output_docs`, `save_output_docs`, `OutputDocs`) i sygnatury bez zmian.
- **Modify:** `requirements.txt` — dodać `pikepdf>=9`.
- **Create:** `tests/render_util.py` — helper renderujący stronę `fitz` do bajtów PNG i porównujący dwa rendery w tolerancji (bez numpy).
- **Create:** `tests/test_export_fidelity.py` — golden-image: wynik nie zmienia się po refaktorze; licznik wywołań `show_pdf_page` wymusza deduplikację.
- **Create:** `tests/fixtures/` — golden PNG-i (commitowane) generowane z bieżącego kodu PRZED refaktorem.

Istniejące `tests/test_export.py` (cache źródła, liczba stron, zapis, gapless) MUSZĄ dalej przechodzić bez zmian — to dodatkowa siatka bezpieczeństwa.

---

## Task 1: Dodać zależność pikepdf

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Dopisać pikepdf do requirements**

W `requirements.txt` dodać linię pod `PyMuPDF>=1.24`:

```
pikepdf>=9
```

- [ ] **Step 2: Potwierdzić, że pikepdf jest w .venv**

Run: `cd ~/summa-cut && .venv/bin/python -c "import pikepdf; print(pikepdf.__version__)"`
Expected: wypisuje wersję (np. `10.8.0`) bez błędu. (W .venv już zainstalowany; gdyby brakło: `.venv/bin/pip install 'pikepdf>=9'`.)

- [ ] **Step 3: Commit**

```bash
cd ~/summa-cut
git add requirements.txt
git commit -m "build: dodaj zależność pikepdf (eksport)"
```

---

## Task 2: Helper renderujący i porównujący strony PDF do PNG

**Files:**
- Create: `tests/render_util.py`

- [ ] **Step 1: Napisać helper (bez TDD — to narzędzie testowe)**

Utwórz `tests/render_util.py`:

```python
"""Narzędzia testowe: render strony fitz do PNG + porównanie w tolerancji.

Bez numpy — porównujemy surowe bajty pixmapy. Niska DPI (mały bufor, szybki
test), wystarczająca by wychwycić przesunięcia/zniknięcia użytków.
"""
from __future__ import annotations

import fitz

RENDER_DPI = 72


def render_page_png(doc: fitz.Document, page_index: int = 0, dpi: int = RENDER_DPI) -> bytes:
    page = doc[page_index]
    pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY, alpha=False)
    return pix.tobytes("png")


def _samples(png_bytes: bytes) -> bytes:
    pix = fitz.Pixmap(png_bytes)
    return pix.samples


def fraction_differing(png_a: bytes, png_b: bytes, byte_threshold: int = 24) -> float:
    """Ułamek bajtów (pikseli gray) różniących się o więcej niż byte_threshold.

    Zwraca 1.0 gdy rozmiary buforów różne (twarda regresja geometrii).
    """
    a = _samples(png_a)
    b = _samples(png_b)
    if len(a) != len(b) or not a:
        return 1.0
    diff = sum(1 for x, y in zip(a, b) if abs(x - y) > byte_threshold)
    return diff / len(a)
```

- [ ] **Step 2: Smoke helpera**

Run:
```bash
cd ~/summa-cut && QT_QPA_PLATFORM=offscreen .venv/bin/python -c "
import fitz
from tests.render_util import render_page_png, fraction_differing
d = fitz.open(); p = d.new_page(width=200, height=200)
p.draw_rect(fitz.Rect(10,10,190,190), fill=(0,0,0))
a = render_page_png(d)
print('frac same =', fraction_differing(a, a))
"
```
Expected: `frac same = 0.0`

- [ ] **Step 3: Commit**

```bash
cd ~/summa-cut
git add tests/render_util.py
git commit -m "test: helper render+porównanie stron PDF do PNG"
```

---

## Task 3: Golden-image — zamrożenie bieżącego wyglądu (PRZED refaktorem)

**Files:**
- Create: `tests/test_export_fidelity.py`
- Create: `tests/fixtures/golden_print_grid.png`, `tests/fixtures/golden_cut_grid.png`, `tests/fixtures/golden_print_gapless.png`, `tests/fixtures/golden_cut_gapless.png`

Cel: utrwalić obecny render jako wzorzec; po refaktorze nowy wynik musi być ~identyczny.

- [ ] **Step 1: Napisać test fidelity (czyta golden z fixtures)**

Utwórz `tests/test_export_fidelity.py`:

```python
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
```

- [ ] **Step 2: Wygenerować golden-y z BIEŻĄCEGO kodu (dwa przebiegi)**

Run:
```bash
cd ~/summa-cut && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_export_fidelity.py -q
```
Expected: pierwszy przebieg — testy `skipped` (zapisały fixtures). Uruchom ponownie:
```bash
cd ~/summa-cut && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_export_fidelity.py -q
```
Expected: 2 passed. Powstały 4 pliki w `tests/fixtures/`.

- [ ] **Step 3: Commit golden-ów (wzorzec sprzed refaktoru)**

```bash
cd ~/summa-cut
git add tests/test_export_fidelity.py tests/fixtures/
git commit -m "test: golden-image eksportu (zamrożenie wyglądu przed portem pikepdf)"
```

---

## Task 4: Test wymuszający deduplikację (licznik show_pdf_page) — RED

**Files:**
- Modify: `tests/test_export_fidelity.py`

Ten test ma teraz FAILOWAĆ na starym kodzie (po jednym `show_pdf_page` na użytek) i przejść po refaktorze.

- [ ] **Step 1: Dopisać test licznika wywołań**

Dodaj na końcu `tests/test_export_fidelity.py`:

```python
def test_show_pdf_page_called_once_per_unique_cell(source_pdf, monkeypatch):
    """Jednolita siatka = 1 unikalna komórka → render źródła najwyżej 2x
    (druk + wykrojnik), niezależnie od liczby użytków."""
    job = _job(source_pdf, gap_enabled=True, item=30.0)
    layout = compute_layout(job)
    assert layout.count > 50

    calls = {"n": 0}
    real = fitz.Page.show_pdf_page

    def spy(self, *a, **k):
        calls["n"] += 1
        return real(self, *a, **k)

    monkeypatch.setattr(fitz.Page, "show_pdf_page", spy)
    docs = E.generate_output_docs(job, layout)
    try:
        assert calls["n"] <= 2, f"show_pdf_page wołane {calls['n']}x (brak deduplikacji)"
    finally:
        docs.print_doc.close(); docs.cut_doc.close()
```

- [ ] **Step 2: Uruchomić — ma FAILOWAĆ**

Run: `cd ~/summa-cut && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_export_fidelity.py::test_show_pdf_page_called_once_per_unique_cell -q`
Expected: FAIL — `show_pdf_page wołane >50x` (stary kod woła per użytek).

- [ ] **Step 3: Commit (test RED towarzyszy implementacji w następnym tasku)**

```bash
cd ~/summa-cut
git add tests/test_export_fidelity.py
git commit -m "test: wymuś deduplikację renderu komórki (RED)"
```

---

## Task 5: Implementacja — sygnatura komórki + render stempla + montaż pikepdf

**Files:**
- Modify: `summa_cut/export.py`

- [ ] **Step 1: Dodać import pikepdf i funkcję sygnatury komórki**

W `summa_cut/export.py` pod `import fitz` (linia 6) dodaj:

```python
import pikepdf
```

Pod `_resolve_cut_source` (po linii 123) dodaj:

```python
def _placement_signature(
    source_path: str,
    page_index: int,
    content_bbox_pt: tuple[float, float, float, float],
    placement: Placement,
    use_full_page: bool,
) -> tuple:
    """Klucz identyczności RYSUNKU komórki — bez pozycji (x,y/group/index).

    Dwa użytki o tej samej sygnaturze rysują piksel w piksel to samo, więc
    stempel renderujemy raz i tylko przesuwamy."""
    return (
        source_path,
        page_index,
        content_bbox_pt,
        round(placement.width_mm, 4),
        round(placement.height_mm, 4),
        placement.rotation_deg,
        use_full_page,
    )
```

- [ ] **Step 2: Dodać render pojedynczego stempla (źródło w komórce u origin)**

Pod `_placement_signature` dodaj:

```python
def _render_cell_stamp(
    src: fitz.Document,
    page_index: int,
    content_bbox_pt: tuple[float, float, float, float],
    width_mm: float,
    height_mm: float,
    rotation_deg: int,
    use_full_page: bool,
) -> bytes:
    """Jednostronicowy PDF rozmiaru komórki z osadzonym źródłem w (0,0).

    Używa istniejącej ścieżki show_pdf_page (identyczny render jak dawniej),
    ale TYLKO raz na unikalną sygnaturę."""
    cell_w_pt = mm_to_pt(width_mm)
    cell_h_pt = mm_to_pt(height_mm)
    stamp = fitz.open()
    page = stamp.new_page(width=cell_w_pt, height=cell_h_pt)
    src_page = src[page_index]
    clip_rect = src_page.rect if use_full_page else _centered_clip_rect_pt(
        src_page.rect, content_bbox_pt, width_mm, height_mm, rotation_deg,
    )
    page.show_pdf_page(
        fitz.Rect(0, 0, cell_w_pt, cell_h_pt),
        src, page_index, rotate=rotation_deg, clip=clip_rect,
    )
    data = stamp.tobytes()
    stamp.close()
    return data
```

- [ ] **Step 3: Dodać montaż przez pikepdf (translacja-stempel N razy)**

Pod `_render_cell_stamp` dodaj:

```python
def _stamp_placements_pikepdf(
    base_pdf_bytes: bytes,
    sheet_height_mm: float,
    stamp_bytes_by_sig: dict[tuple, bytes],
    placements_with_sig: list[tuple[Placement, tuple]],
) -> bytes:
    """Na stronę bazową (krata/puste + bez OPOS) nakłada stemple przez overlay.

    Konwersja układu współrzędnych: nasze mm mają origin w LEWYM-GÓRNYM rogu,
    PDF w LEWYM-DOLNYM → odbicie osi Y."""
    sheet_h_pt = mm_to_pt(sheet_height_mm)
    base = pikepdf.Pdf.open(BytesIO(base_pdf_bytes))
    target_page = base.pages[0]
    # cache otwartych stempli (pikepdf.Pdf) per sygnatura
    stamp_pdfs: dict[tuple, pikepdf.Pdf] = {}
    try:
        for placement, sig in placements_with_sig:
            sp = stamp_pdfs.get(sig)
            if sp is None:
                sp = pikepdf.Pdf.open(BytesIO(stamp_bytes_by_sig[sig]))
                stamp_pdfs[sig] = sp
            x0 = mm_to_pt(placement.x_mm)
            w = mm_to_pt(placement.width_mm)
            h = mm_to_pt(placement.height_mm)
            y_top = mm_to_pt(placement.y_mm)
            lly = sheet_h_pt - (y_top + h)
            rect = pikepdf.Rectangle(x0, lly, x0 + w, lly + h)
            target_page.add_overlay(sp.pages[0], rect)
        out = BytesIO()
        base.save(out)
        return out.getvalue()
    finally:
        for sp in stamp_pdfs.values():
            sp.close()
        base.close()
```

Oraz dodaj na górze pliku (pod `from pathlib import Path`, linia 4):

```python
from io import BytesIO
```

(API zweryfikowane: `pikepdf.Pdf.open(BytesIO(...))`, `pikepdf.Rectangle(llx,lly,urx,ury)`, `Page.add_overlay(other, rect)` — działają w pikepdf 10.8.)

- [ ] **Step 4: Przepisać `generate_output_docs` na ścieżkę stempli**

Zastąp ciało `generate_output_docs` (linie 157-195) wersją: bazę (krata/puste, BEZ stempli i BEZ OPOS) buduje fitz → bajty; stemple nakłada pikepdf → bajty; OPOS dorysowuje fitz na wierzchu. Pełna nowa treść funkcji:

```python
def generate_output_docs(job: JobSettings, layout: LayoutResult) -> OutputDocs:
    page_rect = _rect_mm_to_pt(0, 0, job.sheet_spec.width_mm, job.sheet_spec.height_mm)
    use_special = bool(job.special_mode_pattern and job.special_mode_pattern.enabled)

    # 1) BAZA (fitz): puste strony; na wykrojniku krata gdy gapless. Bez OPOS.
    print_base = fitz.open()
    cut_base = fitz.open()
    print_base.new_page(width=page_rect.width, height=page_rect.height)
    cut_base_page = cut_base.new_page(width=page_rect.width, height=page_rect.height)
    if job.generate_cut_grid:
        _draw_generated_cut_grid(cut_base_page, layout)
    print_base_bytes = print_base.tobytes()
    cut_base_bytes = cut_base.tobytes()
    print_base.close(); cut_base.close()

    # 2) Render unikalnych stempli RAZ + lista (placement, sygnatura).
    sources = _SourceCache()
    print_stamps: dict[tuple, bytes] = {}
    cut_stamps: dict[tuple, bytes] = {}
    print_list: list[tuple[Placement, tuple]] = []
    cut_list: list[tuple[Placement, tuple]] = []
    try:
        for placement in layout.placements:
            p_path, p_idx, p_bbox = _resolve_print_source(job, placement)
            sig = _placement_signature(p_path, p_idx, p_bbox, placement, use_special)
            if sig not in print_stamps:
                print_stamps[sig] = _render_cell_stamp(
                    sources.get(p_path), p_idx, p_bbox,
                    placement.width_mm, placement.height_mm,
                    placement.rotation_deg, use_special,
                )
            print_list.append((placement, sig))

            if not job.generate_cut_grid:
                c_path, c_idx, c_bbox = _resolve_cut_source(job, placement)
                csig = _placement_signature(c_path, c_idx, c_bbox, placement, use_special)
                if csig not in cut_stamps:
                    cut_stamps[csig] = _render_cell_stamp(
                        sources.get(c_path), c_idx, c_bbox,
                        placement.width_mm, placement.height_mm,
                        placement.rotation_deg, use_special,
                    )
                cut_list.append((placement, csig))
    finally:
        sources.close()

    # 3) Montaż stempli (pikepdf).
    print_bytes = _stamp_placements_pikepdf(
        print_base_bytes, job.sheet_spec.height_mm, print_stamps, print_list,
    )
    if job.generate_cut_grid:
        cut_bytes = cut_base_bytes
    else:
        cut_bytes = _stamp_placements_pikepdf(
            cut_base_bytes, job.sheet_spec.height_mm, cut_stamps, cut_list,
        )

    # 4) OPOS na wierzchu (fitz).
    print_doc = fitz.open("pdf", print_bytes)
    cut_doc = fitz.open("pdf", cut_bytes)
    _draw_opos(print_doc[0], job)
    _draw_opos(cut_doc[0], job)
    return OutputDocs(print_doc=print_doc, cut_doc=cut_doc)
```

`_place_pdf_page` pozostaje w pliku (używany pośrednio? sprawdź) — jeśli nieużywany po refaktorze, usuń go i jego test zależności w kroku weryfikacji. `_centered_clip_rect_pt`, `_draw_opos`, `_draw_generated_cut_grid`, `_SourceCache`, `_resolve_*`, `save_output_docs`, `OutputDocs` — bez zmian.

- [ ] **Step 5: Uruchomić test licznika — ma PRZEJŚĆ**

Run: `cd ~/summa-cut && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_export_fidelity.py::test_show_pdf_page_called_once_per_unique_cell -q`
Expected: PASS (`show_pdf_page` ≤ 2).

- [ ] **Step 6: Uruchomić golden-fidelity — ma PRZEJŚĆ w tolerancji**

Run: `cd ~/summa-cut && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_export_fidelity.py -q`
Expected: wszystkie passed. Jeśli golden faila >1%: najpewniej odbicie Y (sprawdź `lly`) lub aspekt stempla — zdiagnozuj porównując wizualnie `docs.print_doc.save('/tmp/new.pdf')` ze wzorcem; NIE regeneruj golden-ów (one są wzorcem prawdy).

- [ ] **Step 7: Commit**

```bash
cd ~/summa-cut
git add summa_cut/export.py
git commit -m "perf: port eksportu na pikepdf (dedup stempli) — 47s→<1s @560, fidelity zachowane"
```

---

## Task 6: Pełny pomiar i regresja całości

**Files:** brak zmian (weryfikacja)

- [ ] **Step 1: Cały zestaw testów przechodzi**

Run: `cd ~/summa-cut && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -q`
Expected: wszystkie passed (stare `test_export.py` + `test_layout.py` + nowe fidelity). Jeśli `test_export.py::test_source_opened_once...` faila — `_SourceCache` musi nadal otwierać źródło raz (woła `sources.get`), zachowane w nowej pętli.

- [ ] **Step 2: Zmierzyć realny czas na dużym arkuszu**

Run:
```bash
cd ~/summa-cut && QT_QPA_PLATFORM=offscreen .venv/bin/python -c "
import time, fitz
from summa_cut import export as E
from summa_cut.layout import compute_layout
from summa_cut.models import ItemSpec, JobSettings, SelectedPage, SheetSpec
from summa_cut.pdf_io import MM_PER_POINT
PT=1.0/MM_PER_POINT; side=40*PT; bbox=(0,0,side,side)
d=fitz.open(); p=d.new_page(width=side,height=side); p.draw_rect(fitz.Rect(3,3,side-3,side-3),color=(0,0,1),width=1.5); d.save('/tmp/src.pdf')
job=JobSettings(SelectedPage('/tmp/src.pdf',0),SelectedPage('/tmp/src.pdf',0),(40,40),(40,40),(40,40),(40,40),bbox,bbox,SheetSpec(330,480),ItemSpec(13,13,False),True,2.0)
lay=compute_layout(job); 
t=time.time(); docs=E.generate_output_docs(job,lay); dt=time.time()-t
print('użytków',lay.count,'czas',round(dt,3),'s'); docs.print_doc.close(); docs.cut_doc.close()
"
```
Expected: kilkaset użytków, czas znacząco poniżej 1 s (dawniej dziesiątki sekund).

- [ ] **Step 3: Smoke desktopu (zapis działa, plik powstaje)**

Run:
```bash
cd ~/summa-cut && QT_QPA_PLATFORM=offscreen .venv/bin/python -c "
import fitz
from summa_cut import export as E
from summa_cut.layout import compute_layout
from summa_cut.models import ItemSpec, JobSettings, SelectedPage, SheetSpec
from summa_cut.pdf_io import MM_PER_POINT
PT=1.0/MM_PER_POINT; side=40*PT; bbox=(0,0,side,side)
d=fitz.open(); d.new_page(width=side,height=side).draw_rect(fitz.Rect(3,3,side-3,side-3),color=(0,0,1)); d.save('/tmp/src.pdf')
job=JobSettings(SelectedPage('/tmp/src.pdf',0),SelectedPage('/tmp/src.pdf',0),(40,40),(40,40),(40,40),(40,40),bbox,bbox,SheetSpec(330,480),ItemSpec(30,30,False),True,3.0)
docs=E.generate_output_docs(job,compute_layout(job))
pp,cp=E.save_output_docs(docs,'/tmp/out',base_name='smoke')
print('zapisano',pp,cp); docs.print_doc.close(); docs.cut_doc.close()
"
```
Expected: wypisuje ścieżki `smoke_druk.pdf` i `smoke_wykrojnik.pdf`.

- [ ] **Step 4: Tag i podsumowanie**

```bash
cd ~/summa-cut
git tag -a phase0-pikepdf -m "Phase 0: eksport na pikepdf, dedup stempli"
git log --oneline -6
```

---

## Self-Review (autor planu)

**Pokrycie specu (sekcja 6 + faza 0):** port `show_pdf_page`→osadzenie XObject + N odwołań ✔ (Task 5); test regresji fidelity render→PNG porównanie ✔ (Task 3); `generate_cut_grid` bez zmian — krata dalej rysowana fitz, bez stempli ✔ (Task 5 krok 4); wartość dla desktopu (save) ✔ (Task 6 krok 3).

**Placeholdery:** brak „TODO/TBD"; każdy krok ma realny kod/komendę. Uwaga przy `_stamp_placements_pikepdf`: docelowa linia otwarcia to `base = pikepdf.Pdf.open(BytesIO(base_pdf_bytes))` (gałąź `hasattr` to wyłącznie zabezpieczenie — przy ręcznej edycji zostaw prostą wersję).

**Spójność typów:** `_placement_signature` zwraca krotkę użytą jako klucz w `print_stamps`/`cut_stamps` i w `placements_with_sig` ✔; `_render_cell_stamp` zwraca `bytes`, konsumowane przez `pikepdf.Pdf.open(BytesIO(...))` ✔; `_stamp_placements_pikepdf` zwraca `bytes`, ładowane przez `fitz.open("pdf", ...)` ✔; publiczne API (`OutputDocs`, `generate_output_docs`, `save_output_docs`) niezmienione → desktop i `test_export.py` bez zmian ✔.

**Ryzyko do pilnowania w trakcie:** (1) odbicie osi Y (`lly = sheet_h_pt - (y_top+h)`) — golden to wychwyci; (2) `add_overlay` zachowuje aspekt i centruje — stempel ma rozmiar komórki = aspekt 1:1 z rect, więc wypełnia dokładnie; (3) gdyby `add_overlay` różniło się w API wersji pikepdf, sprawdź sygnaturę `Page.add_overlay(other, rect)` w `.venv/bin/python -c "import pikepdf,inspect;print(inspect.signature(pikepdf.Page.add_overlay))"`.
```
