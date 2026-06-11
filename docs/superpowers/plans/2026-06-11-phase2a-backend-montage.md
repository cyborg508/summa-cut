# Phase 2a — Backend: montaż wielu użytków — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rozszerzyć backend (`web/job_builder.py`) o montaż wielu różnych użytków z indywidualną ilością (quantity), tak by `/api/job`, `/api/preview` i `/api/generate` obsługiwały listę montażową — bez zmian w rdzeniu ani w trasach.

**Architecture:** Rdzeń już to umie (`JobSettings.montage_items` + `layout._apply_montage_quantities` + `export._resolve_*_source` per `montage_item_index`). Dodajemy do `JobParams` pole `montage: list[MontageItemParams]`; gdy niepuste, `build_job` buduje `MontageItem`-y z wgranych plików (każdy element: plik+strona druku, plik+strona wykrojnika, ilość) i ustawia pola bazowe z pierwszego elementu. Trasy się nie zmieniają — `JobParams` przepływa przez `/api/job` automatycznie. Upload wielu plików już działa (`/api/upload` zapisuje per nazwa).

**Tech Stack:** Python, pydantic (JobParams), istniejący silnik summa_cut, pytest + TestClient.

---

## File Structure

- **Modify:** `web/job_builder.py` — dodać model `MontageItemParams`, pole `montage` w `JobParams`, gałąź montażu w `build_job` (+ helper `_build_montage_items`). Ścieżka pojedynczego produktu bez zmian funkcjonalnych (refaktor do gałęzi `else`).
- **Modify:** `tests/test_web_job_builder.py` — testy gałęzi montażu.
- **Modify:** `tests/test_web_api.py` — test end-to-end montażu przez API (job→preview→generate→download).

Reguła: montaż NIE rusza tras ani rdzenia. `MontageItem` z `summa_cut.models` jest budowany w `job_builder`.

---

## Task 1: Model i builder montażu (`web/job_builder.py`)

**Files:**
- Modify: `web/job_builder.py`
- Test: `tests/test_web_job_builder.py`

- [ ] **Step 1: Dopisać testy montażu**

Dodaj na końcu `tests/test_web_job_builder.py`:

```python
def _session_with_two_pdfs(tmp_path):
    store = SessionStore(base_dir=tmp_path)
    s = store.create()
    store.save_upload(s, "a.pdf", _pdf_bytes())
    store.save_upload(s, "b.pdf", _pdf_bytes())
    return s


def _montage_params(items, **over) -> JobParams:
    base = dict(
        print_upload="a.pdf", print_page=0, cut_upload="a.pdf", cut_page=0,
        sheet_w_mm=330.0, sheet_h_mm=480.0, item_w_mm=30.0, item_h_mm=30.0,
        gap_enabled=True, gap_mm=3.0, montage=items,
    )
    base.update(over)
    return JobParams(**base)


def test_montage_builds_items_with_quantities(tmp_path):
    s = _session_with_two_pdfs(tmp_path)
    params = _montage_params([
        {"label": "A", "print_upload": "a.pdf", "print_page": 0, "cut_upload": "a.pdf", "cut_page": 0, "quantity": 3},
        {"label": "B", "print_upload": "b.pdf", "print_page": 0, "cut_upload": "b.pdf", "cut_page": 0, "quantity": 2},
    ])
    job = build_job(params, s)
    assert len(job.montage_items) == 2
    assert [it.quantity for it in job.montage_items] == [3, 2]
    assert job.montage_items[0].label == "A"
    layout = compute_layout(job)
    assert layout.requested_count == 5
    assert layout.count == 5  # mieści się w arkuszu
    assert sorted(p.montage_item_index for p in layout.placements) == [0, 0, 0, 1, 1]


def test_montage_base_fields_taken_from_first_item(tmp_path):
    s = _session_with_two_pdfs(tmp_path)
    params = _montage_params([
        {"print_upload": "b.pdf", "print_page": 0, "cut_upload": "b.pdf", "cut_page": 0, "quantity": 1},
    ])
    job = build_job(params, s)
    assert job.print_page.pdf_path.endswith("b.pdf")
    assert job.cut_page.pdf_path.endswith("b.pdf")


def test_montage_unknown_upload_raises(tmp_path):
    s = _session_with_two_pdfs(tmp_path)
    params = _montage_params([
        {"print_upload": "brak.pdf", "print_page": 0, "cut_upload": "a.pdf", "cut_page": 0, "quantity": 1},
    ])
    with pytest.raises(ValueError):
        build_job(params, s)


def test_montage_zero_quantity_raises(tmp_path):
    s = _session_with_two_pdfs(tmp_path)
    params = _montage_params([
        {"print_upload": "a.pdf", "print_page": 0, "cut_upload": "a.pdf", "cut_page": 0, "quantity": 0},
    ])
    with pytest.raises(ValueError):
        build_job(params, s)


def test_montage_empty_list_uses_single_product_path(tmp_path):
    s = _session_with_two_pdfs(tmp_path)
    job = build_job(_montage_params([]), s)  # montage=[] → pojedynczy produkt
    assert job.montage_items == []
    assert compute_layout(job).count > 50
```

- [ ] **Step 2: Uruchomić — FAIL**

Run: `cd ~/summa-cut && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_web_job_builder.py -q`
Expected: nowe testy FAIL (`JobParams` nie ma pola `montage` / brak gałęzi montażu), stare 8 PASS.

- [ ] **Step 3: Zaimplementować — zastąp całą treść `web/job_builder.py`**

```python
from __future__ import annotations

from pydantic import BaseModel, Field

from summa_cut.models import ItemSpec, JobSettings, MontageItem, OposSpec, SelectedPage, SheetSpec
from web.sessions import Session


class MontageItemParams(BaseModel):
    label: str = ""
    print_upload: str
    print_page: int = 0
    cut_upload: str
    cut_page: int = 0
    quantity: int = 1


class JobParams(BaseModel):
    """Parametry zlecenia. `montage` niepuste → montaż wielu użytków; puste → pojedynczy produkt."""
    print_upload: str
    print_page: int = 0
    cut_upload: str | None = None
    cut_page: int | None = None

    sheet_w_mm: float = 330.0
    sheet_h_mm: float = 480.0
    item_w_mm: float
    item_h_mm: float
    rotation_allowed: bool = False

    gap_enabled: bool = True
    gap_mm: float = 3.0

    split_horizontal_groups: bool = False
    split_max_spread: bool = False
    manual_grid_enabled: bool = False
    manual_columns: int = 0
    manual_rows: int = 0

    opos_side_offset_mm: float = Field(default=10.0)
    opos_bottom_offset_mm: float = Field(default=10.0)
    opos_top_offset_mm: float = Field(default=40.0)

    montage: list[MontageItemParams] = Field(default_factory=list)


def _require_page(session: Session, upload: str, page_index: int, what: str):
    info = session.uploads.get(upload)
    if info is None:
        raise ValueError(f"Nie wgrano pliku: {upload} ({what}).")
    if page_index < 0 or page_index >= info.page_count:
        raise ValueError(f"Strona {page_index} poza zakresem pliku {upload} ({what}).")
    return info


def _build_montage_items(params: JobParams, session: Session) -> list[MontageItem]:
    items: list[MontageItem] = []
    for idx, m in enumerate(params.montage):
        if m.quantity < 1:
            raise ValueError(f"Ilość użytku #{idx + 1} musi być >= 1.")
        p_info = _require_page(session, m.print_upload, m.print_page, f"druk montażu #{idx + 1}")
        c_info = _require_page(session, m.cut_upload, m.cut_page, f"wykrojnik montażu #{idx + 1}")
        items.append(MontageItem(
            label=m.label or f"#{idx + 1}",
            print_page=SelectedPage(p_info.path, m.print_page),
            cut_page=SelectedPage(c_info.path, m.cut_page),
            print_page_size_mm=p_info.page_sizes_mm[m.print_page],
            cut_page_size_mm=c_info.page_sizes_mm[m.cut_page],
            print_content_size_mm=p_info.page_content_sizes_mm[m.print_page],
            cut_content_size_mm=c_info.page_content_sizes_mm[m.cut_page],
            print_content_bbox_pt=p_info.page_content_boxes_pt[m.print_page],
            cut_content_bbox_pt=c_info.page_content_boxes_pt[m.cut_page],
            quantity=m.quantity,
        ))
    return items


def build_job(params: JobParams, session: Session) -> JobSettings:
    if params.item_w_mm <= 0 or params.item_h_mm <= 0:
        raise ValueError("Rozmiar użytku musi być większy od zera.")
    if params.sheet_w_mm <= 0 or params.sheet_h_mm <= 0:
        raise ValueError("Rozmiar arkusza musi być większy od zera.")

    with_gap = params.gap_enabled
    montage_items = _build_montage_items(params, session) if params.montage else []

    if montage_items:
        base = montage_items[0]
        print_page = base.print_page
        cut_page = base.cut_page
        print_page_size_mm = base.print_page_size_mm
        cut_page_size_mm = base.cut_page_size_mm
        print_content_size_mm = base.print_content_size_mm
        cut_content_size_mm = base.cut_content_size_mm
        print_content_bbox_pt = base.print_content_bbox_pt
        cut_content_bbox_pt = base.cut_content_bbox_pt
    else:
        print_info = _require_page(session, params.print_upload, params.print_page, "druk")
        if with_gap:
            if not params.cut_upload or params.cut_page is None:
                raise ValueError("W trybie z odstępami wybierz też plik i stronę wykrojnika.")
            cut_upload, cut_page_index = params.cut_upload, params.cut_page
        else:
            cut_upload, cut_page_index = params.print_upload, params.print_page
        cut_info = _require_page(session, cut_upload, cut_page_index, "wykrojnik")
        print_page = SelectedPage(print_info.path, params.print_page)
        cut_page = SelectedPage(cut_info.path, cut_page_index)
        print_page_size_mm = print_info.page_sizes_mm[params.print_page]
        cut_page_size_mm = cut_info.page_sizes_mm[cut_page_index]
        print_content_size_mm = print_info.page_content_sizes_mm[params.print_page]
        cut_content_size_mm = cut_info.page_content_sizes_mm[cut_page_index]
        print_content_bbox_pt = print_info.page_content_boxes_pt[params.print_page]
        cut_content_bbox_pt = cut_info.page_content_boxes_pt[cut_page_index]

    if params.manual_grid_enabled:
        if params.manual_columns <= 0 or params.manual_rows <= 0:
            raise ValueError("W trybie manualnym liczba kolumn i rzędów musi być większa od zera.")
        if params.split_horizontal_groups and params.manual_rows % 2 == 1:
            raise ValueError("Przy podziale na 2 grupy manualna liczba rzędów musi być parzysta.")

    return JobSettings(
        print_page=print_page,
        cut_page=cut_page,
        print_page_size_mm=print_page_size_mm,
        cut_page_size_mm=cut_page_size_mm,
        print_content_size_mm=print_content_size_mm,
        cut_content_size_mm=cut_content_size_mm,
        print_content_bbox_pt=print_content_bbox_pt,
        cut_content_bbox_pt=cut_content_bbox_pt,
        sheet_spec=SheetSpec(params.sheet_w_mm, params.sheet_h_mm),
        item_spec=ItemSpec(params.item_w_mm, params.item_h_mm, params.rotation_allowed),
        gap_enabled=with_gap,
        gap_mm=params.gap_mm if with_gap else 0.0,
        generate_cut_grid=not with_gap,
        split_horizontal_groups=params.split_horizontal_groups,
        split_max_spread=params.split_horizontal_groups and params.split_max_spread,
        manual_grid_enabled=params.manual_grid_enabled,
        manual_columns=params.manual_columns,
        manual_rows=params.manual_rows,
        montage_items=montage_items,
        opos_spec=OposSpec(params.opos_side_offset_mm, params.opos_bottom_offset_mm, params.opos_top_offset_mm),
    )
```

- [ ] **Step 4: Uruchomić — PASS**

Run: `cd ~/summa-cut && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_web_job_builder.py -q`
Expected: 13 passed (8 starych + 5 nowych).

- [ ] **Step 5: Commit**

```bash
cd ~/summa-cut
git add web/job_builder.py tests/test_web_job_builder.py
git commit -m "feat(web): montaż wielu użytków w build_job (MontageItemParams + quantity)"
```

---

## Task 2: Montaż end-to-end przez API + regresja

**Files:**
- Modify: `tests/test_web_api.py`

`JobParams` przepływa przez `/api/job` bez zmian w `server.py` — ten task potwierdza całą ścieżkę i chroni przed regresją.

- [ ] **Step 1: Dopisać test montażu przez API**

Dodaj na końcu `tests/test_web_api.py`:

```python
def test_montage_job_preview_generate_download(tmp_path):
    c = _client(tmp_path)
    c.post("/api/session")
    c.post("/api/upload", files={"file": ("a.pdf", _pdf_bytes(), "application/pdf")})
    c.post("/api/upload", files={"file": ("b.pdf", _pdf_bytes(), "application/pdf")})

    job = {
        "print_upload": "a.pdf", "print_page": 0, "cut_upload": "a.pdf", "cut_page": 0,
        "sheet_w_mm": 330.0, "sheet_h_mm": 480.0, "item_w_mm": 30.0, "item_h_mm": 30.0,
        "gap_enabled": True, "gap_mm": 3.0,
        "montage": [
            {"label": "A", "print_upload": "a.pdf", "print_page": 0, "cut_upload": "a.pdf", "cut_page": 0, "quantity": 4},
            {"label": "B", "print_upload": "b.pdf", "print_page": 0, "cut_upload": "b.pdf", "cut_page": 0, "quantity": 2},
        ],
    }
    r = c.post("/api/job", json=job)
    assert r.status_code == 200
    body = r.json()
    assert body["requested_count"] == 6
    assert body["count"] == 6

    rp = c.get("/api/preview/print.png")
    assert rp.status_code == 200 and rp.content[:8] == b"\x89PNG\r\n\x1a\n"

    rg = c.post("/api/generate", json={"base_name": "montaz"})
    assert rg.status_code == 200
    assert rg.json()["print_name"] == "montaz_druk.pdf"
    rd = c.get("/api/download/print")
    assert rd.status_code == 200 and rd.content[:5] == b"%PDF-"


def test_montage_bad_upload_is_400(tmp_path):
    c = _client(tmp_path)
    c.post("/api/session")
    c.post("/api/upload", files={"file": ("a.pdf", _pdf_bytes(), "application/pdf")})
    job = {
        "print_upload": "a.pdf", "print_page": 0, "cut_upload": "a.pdf", "cut_page": 0,
        "item_w_mm": 30.0, "item_h_mm": 30.0, "gap_enabled": True, "gap_mm": 3.0,
        "montage": [{"print_upload": "brak.pdf", "print_page": 0, "cut_upload": "a.pdf", "cut_page": 0, "quantity": 1}],
    }
    r = c.post("/api/job", json=job)
    assert r.status_code == 400
```

- [ ] **Step 2: Uruchomić — PASS (montaż działa dzięki Task 1)**

Run: `cd ~/summa-cut && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_web_api.py -q`
Expected: wszystkie passed (12 starych + 2 nowe = 14). (Implementacja tras się nie zmienia — montaż wpływa przez `JobParams`.)

- [ ] **Step 3: Cały zestaw + commit + tag**

Run: `cd ~/summa-cut && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -q`
Expected: wszystkie passed (Faza 0: 13, sessions 4, job_builder 13, preview 3, api 14 = 47).

```bash
cd ~/summa-cut
git add tests/test_web_api.py
git commit -m "test(web): montaż end-to-end przez API (job/preview/generate/download)"
git tag -a phase2a-montage -m "Phase 2a: backend montażu wielu użytków"
```

---

## Self-Review (autor planu)

**Pokrycie:** montaż w backendzie ✔ — `MontageItemParams` + `JobParams.montage` + gałąź montażu w `build_job` (Task 1); end-to-end przez `/api/job`+`/api/preview`+`/api/generate`+`/api/download` ✔ (Task 2). Quantity → `requested_count`/`count`/`montage_item_index` zgodne z `layout._apply_montage_quantities` (test sprawdza `[0,0,0,1,1]` i sumę). Upload wielu plików — bez zmian (`/api/upload` per nazwa). Pojedynczy produkt nietknięty funkcjonalnie (gałąź `else`, `montage=[]` → stara ścieżka; test to potwierdza).

**Placeholdery:** brak. Pełny kod `job_builder.py` podany w całości (zastąpienie pliku), testy kompletne.

**Spójność typów/nazw:** `MontageItemParams(label, print_upload, print_page, cut_upload, cut_page, quantity)` ↔ używane w testach jako dict-y (pydantic koeruje); `JobParams.montage: list[MontageItemParams]`; `_build_montage_items(params, session) -> list[MontageItem]`; `MontageItem` z `summa_cut.models` (pola dokładnie jak w modelu: label/print_page/cut_page/*_size_mm/*_bbox_pt/quantity). `build_job` zwraca `JobSettings` z `montage_items=...` — pole istnieje w modelu. Trasy `server.py` bez zmian (JobParams ma nowe pole z domyślną pustą listą → wstecznie zgodne ze wszystkimi dotychczasowymi testami API).

**Ryzyko:** w montażu pola bazowe (`print_*`/`cut_*` top-level) biorę z `montage_items[0]` — export i tak rozwiązuje źródło per `montage_item_index`, więc pola bazowe są fallbackiem; spójne z tym, że layout/eksport używają listy montażowej, gdy niepusta.
```
