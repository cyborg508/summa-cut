# Tryb manualny: przestrzeń robocza po prawej + wymiar per plik — plan implementacji

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Przenieść paletę + interaktywną kanwę trybu manualnego do prawego, szerokiego panelu i pozwolić nadać każdemu plikowi własny wymiar (mm), który kadruje użytek na generowanym arkuszu.

**Architecture:** Frontend (vanilla JS + SVG) trzyma wymiary per plik w `manualState.dims`; paleta renderuje wiersze z polami W×H; kanwa i paleta żyją w nowym kontenerze `#manual-stage` w prawym panelu `.preview`. Backend (FastAPI + Pydantic) przyjmuje opcjonalne `width_mm/height_mm` w `manual_items` i używa ich jako footprintu użytku — istniejąca ścieżka kadrowania (`use_full_page=False`) bez zmian.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, PyMuPDF; vanilla JS + inline SVG; pytest; Playwright (weryfikacja UI). Uruchamianie testów: `.venv/bin/python -m pytest` (NIE goły `pytest`).

**Referencje:**
- Spec: `docs/superpowers/specs/2026-07-22-manual-prawa-strona-wymiary-design.md`
- Backend manualny: `web/job_builder.py` (`ManualItemParams`, `_build_manual_job`)
- Layout/eksport (bez zmian): `summa_cut/manual_layout.py`, `summa_cut/export.py`
- Frontend: `web/static/index.html`, `web/static/app.js`, `web/static/style.css`
- Wzorzec testu manualnego: `tests/test_web_job_builder.py:268`
- Struktura HTML: `tests/test_web_frontend.py` (`REQUIRED_IDS`)

---

## Struktura plików

- `web/job_builder.py` — Modify: `ManualItemParams` (+2 pola), `_build_manual_job` (override footprintu).
- `tests/test_web_job_builder.py` — Modify: +2 testy overrideu wymiaru.
- `web/static/index.html` — Modify: usuń `#manual-panel` z lewej; dodaj `#manual-stage` (hint+paleta+kanwa) w `.preview`; bump `?v=4`.
- `web/static/app.js` — Modify: `manualState.dims`, `ensureDims`, `renderPalette` (wiersze z W×H), `addInstance` (dims), `onDimInput` (rescale), `onManualToggle` (przenosiny/ukrycie podglądu), `manualJobBody` (wyślij dims).
- `web/static/style.css` — Modify: styl `.palette-row`, `#manual-stage`; usuń martwą regułę `#manual-panel`.
- `tests/test_web_frontend.py` — Modify: `REQUIRED_IDS` (−`manual-panel`, +`manual-stage`).

---

## Task 1: Backend — wymiar per plik nadpisuje footprint

**Files:**
- Modify: `web/job_builder.py:18-19` (`ManualItemParams`), `web/job_builder.py:151-167` (`_build_manual_job`)
- Test: `tests/test_web_job_builder.py`

- [ ] **Step 1: Write the failing tests**

Dopisz na końcu `tests/test_web_job_builder.py`:

```python
def _session_with_para(tmp_path, w_mm=40.0, h_mm=30.0):
    from summa_cut.pdf_io import MM_PER_POINT, read_pdf_info
    from web.sessions import SessionStore
    pt = 1.0 / MM_PER_POINT
    doc = fitz.open()
    doc.new_page(width=w_mm * pt, height=h_mm * pt)
    doc.new_page(width=w_mm * pt, height=h_mm * pt)
    path = tmp_path / "para.pdf"
    doc.save(path); doc.close()
    store = SessionStore(base_dir=tmp_path / "sess")
    session = store.create()
    session.uploads["para.pdf"] = read_pdf_info(str(path))
    return session


def _manual_params(items, placements):
    return JobParams(
        print_upload="para.pdf", item_w_mm=0, item_h_mm=0,
        manual_free_enabled=True,
        manual_items=items,
        manual_placements=placements,
        opos_side_offset_mm=10, opos_bottom_offset_mm=10, opos_top_offset_mm=40,
    )


def test_manual_item_dimension_overrides_footprint(tmp_path):
    from summa_cut.manual_layout import ManualPlacement, build_manual_layout
    session = _session_with_para(tmp_path)  # PDF 40x30
    params = _manual_params(
        items=[{"upload": "para.pdf", "width_mm": 25.0, "height_mm": 18.0}],
        placements=[{"item_index": 0, "x_mm": 20, "y_mm": 50, "rotation_deg": 0}],
    )
    job = build_job(params, session)
    assert job.montage_items[0].print_page_size_mm == (25.0, 18.0)
    assert job.montage_items[0].cut_page_size_mm == (25.0, 18.0)
    layout = build_manual_layout(job, [ManualPlacement(0, 20, 50, 0)])
    assert (layout.placements[0].width_mm, layout.placements[0].height_mm) == (25.0, 18.0)


def test_manual_item_without_dimension_uses_pdf_size(tmp_path):
    session = _session_with_para(tmp_path)  # PDF 40x30
    params = _manual_params(
        items=[{"upload": "para.pdf"}],
        placements=[{"item_index": 0, "x_mm": 20, "y_mm": 50, "rotation_deg": 0}],
    )
    job = build_job(params, session)
    assert job.montage_items[0].print_page_size_mm == (40.0, 30.0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_web_job_builder.py::test_manual_item_dimension_overrides_footprint -v`
Expected: FAIL — `TypeError`/`ValidationError` (nieznane pola `width_mm/height_mm`) lub `AssertionError` (footprint == (40,30)).

- [ ] **Step 3: Add fields to `ManualItemParams`**

W `web/job_builder.py` zamień (linie 18-19):

```python
class ManualItemParams(BaseModel):
    upload: str
    width_mm: float | None = None
    height_mm: float | None = None
```

- [ ] **Step 4: Override footprintu w `_build_manual_job`**

W `web/job_builder.py`, w pętli `for idx, mi in enumerate(params.manual_items):` (linie 153-167) zamień budowę `MontageItem` tak, by footprint pochodził z wymiaru gdy podany:

```python
    for idx, mi in enumerate(params.manual_items):
        p_info = _require_page(session, mi.upload, 0, f"druk palety #{idx + 1}")
        c_info = _require_page(session, mi.upload, 1, f"wykrojnik palety #{idx + 1}")
        if mi.width_mm and mi.height_mm and mi.width_mm > 0 and mi.height_mm > 0:
            footprint = (float(mi.width_mm), float(mi.height_mm))
        else:
            footprint = p_info.page_sizes_mm[0]
        items.append(MontageItem(
            label=mi.upload,
            print_page=SelectedPage(p_info.path, 0),
            cut_page=SelectedPage(c_info.path, 1),
            print_page_size_mm=footprint,
            cut_page_size_mm=footprint,
            print_content_size_mm=p_info.page_content_sizes_mm[0],
            cut_content_size_mm=c_info.page_content_sizes_mm[1],
            print_content_bbox_pt=p_info.page_content_boxes_pt[0],
            cut_content_bbox_pt=c_info.page_content_boxes_pt[1],
            quantity=1,
        ))
```

Uwaga: `*_content_bbox_pt` / `*_content_size_mm` zostają z PDF — dzięki temu kadr eksportu pozostaje wyśrodkowany na treści (decyzja D3 ze spec).

- [ ] **Step 5: Run tests to verify they pass + brak regresji**

Run: `.venv/bin/python -m pytest tests/test_web_job_builder.py -v`
Expected: wszystkie PASS (w tym 2 nowe).

- [ ] **Step 6: Commit**

```bash
git add web/job_builder.py tests/test_web_job_builder.py
git commit -m "feat(manual): wymiar per plik nadpisuje footprint użytku (backend)"
```

---

## Task 2: Frontend — stan wymiarów + paleta z polami W×H

**Files:**
- Modify: `web/static/app.js:11` (`manualState`), `web/static/app.js:414-451` (`renderPalette`, `addInstance`)

- [ ] **Step 1: Dodaj `dims` do stanu**

W `web/static/app.js` zamień linię 11:

```javascript
const manualState = { enabled: false, items: [], placements: [], selected: null, dims: {} };
// dims: { [uploadName]: { wMm, hMm } }  — wymiar per plik (kadr footprintu)
```

- [ ] **Step 2: Dodaj helpery `round1` i `ensureDims` oraz przepisz `renderPalette`**

W `web/static/app.js` zamień całą funkcję `renderPalette` (linie 414-430) na:

```javascript
function round1(v) { return Math.round((parseFloat(v) || 0) * 10) / 10; }

function ensureDims(name) {
  if (!manualState.dims[name]) {
    const info = uploadsInfo[name];
    const size = info && info.page_sizes_mm && info.page_sizes_mm[0];
    const w = size ? size[0] : 0, h = size ? size[1] : 0;
    manualState.dims[name] = { wMm: round1(w), hMm: round1(h) };
  }
  return manualState.dims[name];
}

// Paleta = wgrane PDF-y mające >= 2 strony (str.0=druk, str.1=wykrojnik).
function renderPalette() {
  const box = $("manual-palette");
  box.innerHTML = "";
  const names = Object.keys(uploads).filter((n) => (uploads[n] || 0) >= 2);
  if (names.length === 0) {
    box.innerHTML = '<span class="muted">Brak plików. Wgraj PDF 2-stronicowy (str.1 druk, str.2 wykrojnik) w sekcji „Pliki PDF" u góry — pojawi się tutaj do kliknięcia.</span>';
    return;
  }
  names.forEach((name) => {
    const d = ensureDims(name);
    const row = document.createElement("div");
    row.className = "palette-row";
    const nameEl = document.createElement("span");
    nameEl.className = "pal-name";
    nameEl.textContent = name;
    nameEl.title = name;
    const wLab = document.createElement("label");
    wLab.append("szer. ");
    const wIn = document.createElement("input");
    wIn.type = "number"; wIn.step = "0.1"; wIn.min = "0.1"; wIn.className = "pal-w"; wIn.value = d.wMm;
    wLab.appendChild(wIn);
    const hLab = document.createElement("label");
    hLab.append("wys. ");
    const hIn = document.createElement("input");
    hIn.type = "number"; hIn.step = "0.1"; hIn.min = "0.1"; hIn.className = "pal-h"; hIn.value = d.hMm;
    hLab.appendChild(hIn);
    const addBtn = document.createElement("button");
    addBtn.type = "button"; addBtn.className = "pal-add"; addBtn.textContent = "Dodaj na arkusz";
    wIn.addEventListener("input", () => onDimInput(name, wIn.value, hIn.value));
    hIn.addEventListener("input", () => onDimInput(name, wIn.value, hIn.value));
    addBtn.addEventListener("click", () => addInstance(name));
    row.append(nameEl, wLab, hLab, addBtn);
    box.appendChild(row);
  });
}

function onDimInput(name, wRaw, hRaw) {
  const w = round1(wRaw), h = round1(hRaw);
  if (w <= 0 || h <= 0) return;   // niepełna/nieprawidłowa wartość — czekamy
  manualState.dims[name] = { wMm: w, hMm: h };
  const itemIndex = manualState.items.findIndex((it) => it.upload === name);
  if (itemIndex !== -1) {
    manualState.placements.forEach((p) => {
      if (p.itemIndex !== itemIndex) return;
      if (p.rot === 90 || p.rot === 270) { p.wMm = h; p.hMm = w; }
      else { p.wMm = w; p.hMm = h; }
    });
  }
  renderCanvas();
  schedulePreview();
}
```

- [ ] **Step 3: `addInstance` używa wymiaru z palety**

W `web/static/app.js` zamień początek `addInstance` (linie 438-442) tak, by rozmiar brał się z `dims`:

```javascript
function addInstance(name) {
  const info = uploadsInfo[name];
  if (!info) return;
  const d = ensureDims(name);
  const wMm = d.wMm, hMm = d.hMm;
  const itemIndex = itemIndexForUpload(name);
```

(reszta funkcji bez zmian — dalej używa `wMm`, `hMm`, `workAreaMm()`).

- [ ] **Step 4: Weryfikacja składni (brak testu JS — sprawdzamy parsowanie)**

Run: `node --check web/static/app.js`
Expected: brak wyjścia (OK). Jeśli `node` niedostępne: `.venv/bin/python -c "import esprima" 2>/dev/null || true` — pomiń, weryfikacja pełna nastąpi Playwrightem w Task 5.

- [ ] **Step 5: Commit**

```bash
git add web/static/app.js
git commit -m "feat(manual): paleta z polami wymiaru per plik + rescale kopii"
```

---

## Task 3: Frontend — przeniesienie palety+kanwy do prawego panelu

**Files:**
- Modify: `web/static/index.html:68-75` (usuń `#manual-panel`), `web/static/index.html:120-128` (dodaj `#manual-stage` w `.preview`), `web/static/index.html:7,131` (bump `?v=4`)
- Modify: `web/static/app.js:402-411` (`onManualToggle`)
- Modify: `web/static/style.css` (styl palety+stage; usuń `#manual-panel`)
- Modify: `tests/test_web_frontend.py` (`REQUIRED_IDS`)

- [ ] **Step 1: Usuń lewy `#manual-panel` z index.html**

W `web/static/index.html` usuń cały blok (linie 68-75):

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

- [ ] **Step 2: Dodaj `#manual-stage` w prawym panelu `.preview`**

W `web/static/index.html`, w sekcji `<section class="preview" id="panel">`, tuż po `<div class="segmented" id="view-switch" ...>...</div>` (po linii 100, przed `<div id="view-editor" hidden>`), wstaw:

```html
      <div id="manual-stage" hidden>
        <p id="manual-hint" class="muted">Kliknij „Dodaj na arkusz" przy pliku, aby umieścić go na arkuszu. Przeciągaj myszą; strzałki = przesuw, R = obrót 90°, D = duplikuj, Delete = usuń.</p>
        <div id="manual-palette" class="palette"></div>
        <div class="manual-canvas-wrap">
          <svg id="manual-canvas" xmlns="http://www.w3.org/2000/svg"></svg>
        </div>
      </div>
```

- [ ] **Step 3: Bump wersji assetów**

W `web/static/index.html` zamień `?v=3` → `?v=4` (linie 7 i 131, oba wystąpienia).

- [ ] **Step 4: Przepisz `onManualToggle`**

W `web/static/app.js` zamień całą funkcję `onManualToggle` (linie 402-411) na:

```javascript
function onManualToggle() {
  const on = $("manual-free").checked;
  manualState.enabled = on;
  // Prawy panel: w trybie manualnym pokazujemy przestrzeń montażu, chowamy podgląd PNG/edytor.
  $("manual-stage").hidden = !on;
  $("view-preview").hidden = on;
  $("view-editor").hidden = $("view-editor").hidden || on;
  $("view-switch").hidden = on ? true : !$("special-enable").checked;
  // Lewa kolumna: chowamy fieldsety auto-układu (zostaje „Tryb" z przełącznikiem).
  for (const fs of autoLayoutFieldsets()) {
    const isModeFs = fs.querySelector("legend").textContent.trim() === "Tryb";
    if (!isModeFs) fs.style.display = on ? "none" : "";
  }
  if (on) { renderPalette(); renderCanvas(); }
}
```

- [ ] **Step 5: CSS — styl palety+stage; usuń martwą regułę `#manual-panel`**

W `web/static/style.css` usuń regułę:

```css
/* Fieldsety nie kurczą się poniżej szerokości treści bez min-width:0 — bez tego
   szeroka kanwa SVG rozpycha panel poza kolumnę i wchodzi pod panel podglądu. */
#manual-panel { min-width: 0; }
```

i dodaj (obok istniejących reguł `.palette`):

```css
#manual-stage { display: flex; flex-direction: column; gap: 10px; }
.palette-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  padding: 6px 8px; border: 1px solid var(--line); border-radius: 6px; background: var(--surface); }
.palette-row .pal-name { font-weight: 600; flex: 1 1 140px; min-width: 0;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.palette-row label { display: inline-flex; align-items: center; gap: 4px; }
.palette-row input { width: 68px; }
.palette-row .pal-add { white-space: nowrap; }
```

- [ ] **Step 6: Zaktualizuj `REQUIRED_IDS` w teście struktury**

W `tests/test_web_frontend.py`, w liście `REQUIRED_IDS`, zamień pozycję `"manual-panel"` na `"manual-stage"` (pozostałe `manual-free`, `manual-palette`, `manual-canvas`, `manual-hint` zostają).

- [ ] **Step 7: Run struktura + brak regresji**

Run: `.venv/bin/python -m pytest tests/test_web_frontend.py -v`
Expected: PASS (index.html ma `manual-stage`, nie ma `manual-panel`).
Run: `node --check web/static/app.js`
Expected: OK.

- [ ] **Step 8: Commit**

```bash
git add web/static/index.html web/static/app.js web/static/style.css tests/test_web_frontend.py
git commit -m "feat(manual): przestrzeń montażu (paleta+kanwa) w prawym panelu, PNG-podgląd ukryty w trybie manualnym"
```

---

## Task 4: Frontend — wyślij wymiary w zleceniu

**Files:**
- Modify: `web/static/app.js:641` (`manualJobBody` → `manual_items`)

- [ ] **Step 1: Dołącz wymiary do `manual_items`**

W `web/static/app.js`, w `manualJobBody`, zamień budowę `manual_items` (linia 641):

```javascript
    manual_items: manualState.items.map((it) => {
      const d = manualState.dims[it.upload];
      return (d && d.wMm > 0 && d.hMm > 0)
        ? { upload: it.upload, width_mm: d.wMm, height_mm: d.hMm }
        : { upload: it.upload };
    }),
```

- [ ] **Step 2: Weryfikacja składni**

Run: `node --check web/static/app.js`
Expected: OK.

- [ ] **Step 3: Commit**

```bash
git add web/static/app.js
git commit -m "feat(manual): wyślij wymiar per plik do /api/job"
```

---

## Task 5: Weryfikacja end-to-end (Playwright na realnej apce) + deploy

**Files:** brak zmian kodu (skrypt weryfikacyjny w scratchpadzie).

- [ ] **Step 1: Uruchom całość testów**

Run: `.venv/bin/python -m pytest -q`
Expected: wszystkie zielone (98: 96 + 2 nowe).

- [ ] **Step 2: Uruchom apkę lokalnie**

Run (w tle): `.venv/bin/uvicorn web.app:app --host 127.0.0.1 --port 8899 --log-level warning`
Poczekaj aż `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8899/static/index.html` == `200`.

- [ ] **Step 3: Weryfikacja UI Playwrightem**

Zapisz i uruchom skrypt sprawdzający (viewport 1100×850). Kroki: włącz `#manual-free`; upload 2-str. PDF; sprawdź, że `#manual-stage` jest widoczny i leży w `<section class="preview">`; że `#view-preview` jest ukryty; że paleta ma pola `.pal-w`/`.pal-h` z domyślnymi wartościami = rozmiar strony; zmień `.pal-w`, kliknij `Dodaj na arkusz`, sprawdź, że prostokąt `.mc-item` ma szerokość zgodną z nowym wymiarem (`width` atrybutu ≈ nowy_w × MC_SCALE); przeciągnij i sprawdź zmianę `x`.

Asercje (skrypt kończy się `ALL PASS` gdy):
- `#manual-stage` widoczny, `closest('section.preview')` != null;
- `#view-preview` ukryty;
- paleta: liczba `.pal-w` == liczba plików ≥2 str.; wartość `.pal-w` == round1(page_w);
- po zmianie `.pal-w` na np. 20 i „Dodaj": `.mc-item` `width` ≈ `20 * 2.2` (±1);
- po dragu: `x` się zmienia.

Expected: `ALL PASS`.

- [ ] **Step 4: Zatrzymaj lokalną apkę**

Run: `pkill -f "uvicorn web.app:app"`

- [ ] **Step 5: Deploy na drukpol**

```bash
rsync -az --delete --exclude .venv --exclude .git --exclude __pycache__ --exclude '*.pyc' --exclude .superpowers --exclude .claude ~/summa-cut/ root@100.109.91.116:/mnt/data/apps/summa-cut/
ssh root@100.109.91.116 'docker build -q -t summa-cut-web:local /mnt/data/apps/summa-cut && midclt call app.redeploy summa-cut'
```

- [ ] **Step 6: Weryfikacja na live**

Poczekaj aż `curl -s https://summa.cyplos.pl/static/index.html | grep -o 'app.js?v=[0-9]'` == `app.js?v=4`.
Powtórz skrypt z kroku 3 z `BASE=https://summa.cyplos.pl`.
Expected: `ALL PASS`.

- [ ] **Step 7: Dual-push**

```bash
git push dom master
```

- [ ] **Step 8: Aktualizacja pamięci projektu**

Dopisz do `/mnt/claude/config/projects/-home-cyborg50/memory/project_summacut.md` notkę o nowej wersji (`?v=4`, HEAD master) i funkcji (montaż w prawym panelu + wymiar per plik kadrujący footprint).

---

## Self-review (wypełnione)

- **Pokrycie spec:** D1 (rescale kopii) → Task 2 Step 2 `onDimInput`; D2 (prawy panel = montaż, PNG ukryty) → Task 3 Step 4; D3 (kadr bez skalowania) → Task 1 Step 4 (footprint override, content bbox bez zmian); D4 (paleta+kanwa po prawej) → Task 3 Step 2. Backend → Task 1. Testy → Task 1 (pytest), Task 3 (struktura), Task 5 (Playwright).
- **Placeholdery:** brak — każdy krok ma konkretny kod/komendę.
- **Spójność typów/nazw:** `manualState.dims[name] = {wMm,hMm}` używane spójnie w `ensureDims`/`renderPalette`/`onDimInput`/`addInstance`/`manualJobBody`; backend `width_mm/height_mm` spójne między `ManualItemParams`, `_build_manual_job` i wysyłką z frontu.
