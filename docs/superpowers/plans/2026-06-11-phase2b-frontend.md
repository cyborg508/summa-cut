# Phase 2b — Frontend HTML/HTMX (tryb główny + montaż) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Webowy interfejs summa-cut w przeglądarce: upload PDF, komplet kontrolek 1:1 z `JobParams` (arkusz/użytek/obrót/odstępy/split/manual/OPOS), lista montażowa, podgląd druku i wykrojnika na żywo (server-rendered PNG) oraz generowanie i pobranie wyników — nad istniejącym, przetestowanym API JSON.

**Architecture:** Backend dokłada tylko `GET /` (serwuje `index.html`) i montaż katalogu statycznego `/static`. Cała logika sterowania to jeden lekki kontroler `app.js` (vanilla JS, bez frameworka/builda), który woła istniejące trasy: `POST /api/session`, `/api/upload`, `/api/job`, `GET /api/preview/{which}.png`, `POST /api/generate`, `GET /api/download/{which}`. Podgląd to `<img>` ze server-rendered PNG (decyzja ze specu zachowana), odświeżany cache-bustingiem po debounce. Układ dwukolumnowy: kontrolki z lewej, podglądy+podsumowanie+pobieranie z prawej. Montaż: lista wierszy zarządzana w JS (tablica), wysyłana w polu `montage` do `/api/job`.

**Tech Stack:** FastAPI (+ Starlette StaticFiles/FileResponse — bez nowych zależności), vanilla JS, CSS. pytest + TestClient (smoke serwowania i kontraktu HTML).

---

## File Structure

```
web/
  server.py          # + GET / (FileResponse index.html) + app.mount("/static", StaticFiles(...))
  static/
    index.html       # struktura: dwie kolumny, wszystkie kontrolki, lista montażu, podglądy
    style.css        # układ dwukolumnowy, lekki styl narzędzia wewnętrznego
    app.js           # kontroler: sesja, upload, zbieranie params, podgląd (debounce), montaż, generuj
tests/
  test_web_frontend.py  # smoke: GET / serwuje HTML z wymaganymi id; /static/app.js i style.css serwowane
```

Reguła: backend nie zyskuje logiki domenowej — tylko serwowanie. `app.js` jest jedynym konsumentem kontraktu id-ów z `index.html`; trasy API bez zmian.

---

## Task 1: Serwowanie strony i statyków (`web/server.py`)

**Files:**
- Modify: `web/server.py`
- Create: `web/static/index.html` (tymczasowy minimalny — pełny w Task 2), `web/static/app.js` (pusty placeholder — pełny w Task 3), `web/static/style.css` (pusty — pełny w Task 2)
- Test: `tests/test_web_frontend.py`

- [ ] **Step 1: Utworzyć katalog `web/static/` z minimalnymi plikami**

`web/static/index.html` (na teraz minimalny — Task 2 nadpisze):
```html
<!doctype html>
<html lang="pl"><head><meta charset="utf-8"><title>summa-cut web</title></head>
<body><div id="app">summa-cut</div></body></html>
```
`web/static/style.css`:
```css
/* uzupełnione w Task 2 */
```
`web/static/app.js`:
```javascript
// uzupełnione w Task 3
```

- [ ] **Step 2: Napisać test serwowania**

Utwórz `tests/test_web_frontend.py`:
```python
from __future__ import annotations

from fastapi.testclient import TestClient

from web.server import create_app
from web.sessions import SessionStore


def _client(tmp_path):
    return TestClient(create_app(store=SessionStore(base_dir=tmp_path)))


def test_root_serves_html(tmp_path):
    c = _client(tmp_path)
    r = c.get("/")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "summa-cut" in r.text


def test_static_assets_served(tmp_path):
    c = _client(tmp_path)
    assert _client(tmp_path).get("/static/app.js").status_code == 200
    assert c.get("/static/style.css").status_code == 200
```

- [ ] **Step 3: Uruchomić — FAIL**

Run: `cd ~/summa-cut && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_web_frontend.py -q`
Expected: FAIL (404 — brak tras `/` i `/static`).

- [ ] **Step 4: Dodać serwowanie do `web/server.py`**

Dodaj do importów na górze (obok pozostałych `from fastapi...`):
```python
from pathlib import Path as _Path

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
```
(Uwaga: jeśli `from pathlib import Path` już istnieje w pliku — a istnieje, dodany w Fazie 1 — NIE dubluj; użyj istniejącego `Path` i pomiń alias `_Path`. Wystarczą wtedy importy `FileResponse` i `StaticFiles`.)

Wewnątrz `create_app`, zaraz po `app = FastAPI(...)` (i po `app.state.store = store`), dodaj montaż statyków i trasę głównej strony:
```python
    _static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(_static_dir / "index.html")
```
(Wstaw to PRZED definicjami tras API albo tuż przed `return app` — kolejność nie ma znaczenia, byle wewnątrz `create_app`.)

- [ ] **Step 5: Uruchomić — PASS**

Run: `cd ~/summa-cut && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_web_frontend.py -q`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
cd ~/summa-cut
git add web/server.py web/static/ tests/test_web_frontend.py
git commit -m "feat(web): serwowanie strony / + katalog statyczny /static"
```

---

## Task 2: Struktura strony + styl (`index.html`, `style.css`)

**Files:**
- Modify: `web/static/index.html`, `web/static/style.css`
- Test: `tests/test_web_frontend.py`

- [ ] **Step 1: Dopisać test kontraktu id-ów**

Dodaj na końcu `tests/test_web_frontend.py`:
```python
REQUIRED_IDS = [
    "upload-input", "upload-btn", "uploads-list",
    "print-file", "print-page", "cut-file", "cut-page",
    "sheet-w", "sheet-h", "item-w", "item-h", "rotation",
    "gap-mm", "split", "split-spread", "manual", "manual-cols", "manual-rows",
    "opos-side", "opos-bottom", "opos-top",
    "montage-enable", "montage-rows", "montage-add",
    "base-name", "generate-btn", "summary", "error",
    "preview-print", "preview-cut", "download-print", "download-cut",
]


def test_index_has_required_element_ids(tmp_path):
    html = _client(tmp_path).get("/").text
    missing = [i for i in REQUIRED_IDS if f'id="{i}"' not in html]
    assert not missing, f"brak id w index.html: {missing}"


def test_index_references_assets(tmp_path):
    html = _client(tmp_path).get("/").text
    assert "/static/app.js" in html
    assert "/static/style.css" in html
```

- [ ] **Step 2: Uruchomić — FAIL**

Run: `cd ~/summa-cut && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_web_frontend.py -q`
Expected: nowe testy FAIL (minimalny html nie ma id-ów).

- [ ] **Step 3: Zastąpić `web/static/index.html` pełną treścią**

```html
<!doctype html>
<html lang="pl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>summa-cut web</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
  <header><h1>summa-cut <span class="muted">— impozytor druk + wykrojnik</span></h1></header>
  <main>
    <section class="controls" id="controls">
      <fieldset>
        <legend>Pliki PDF</legend>
        <input type="file" id="upload-input" accept="application/pdf" multiple>
        <button type="button" id="upload-btn">Wgraj</button>
        <ul id="uploads-list" class="uploads"></ul>
      </fieldset>

      <fieldset>
        <legend>Źródło (gdy bez montażu)</legend>
        <label>Druk plik <select id="print-file"></select></label>
        <label>strona <select id="print-page"></select></label>
        <label>Wykrojnik plik <select id="cut-file"></select></label>
        <label>strona <select id="cut-page"></select></label>
      </fieldset>

      <fieldset>
        <legend>Arkusz i użytek (mm)</legend>
        <label>Arkusz szer. <input type="number" id="sheet-w" value="330" step="1" min="1"></label>
        <label>wys. <input type="number" id="sheet-h" value="480" step="1" min="1"></label>
        <label>Użytek szer. <input type="number" id="item-w" value="30" step="0.1" min="0.1"></label>
        <label>wys. <input type="number" id="item-h" value="30" step="0.1" min="0.1"></label>
        <label><input type="checkbox" id="rotation"> pozwól obrót 90°</label>
      </fieldset>

      <fieldset>
        <legend>Tryb</legend>
        <label><input type="radio" name="gapmode" id="gap-on" value="gap" checked> z odstępami</label>
        <label><input type="radio" name="gapmode" id="gap-off" value="nogap"> bez odstępów (krata cięcia)</label>
        <label>odstęp mm <input type="number" id="gap-mm" value="3" step="0.1" min="0"></label>
        <label><input type="checkbox" id="split"> podział na 2 grupy (góra/dół)</label>
        <label><input type="checkbox" id="split-spread"> dociśnij do skraju</label>
        <label><input type="checkbox" id="manual"> siatka manualna</label>
        <label>kol. <input type="number" id="manual-cols" value="0" step="1" min="0"></label>
        <label>rzędy <input type="number" id="manual-rows" value="0" step="1" min="0"></label>
      </fieldset>

      <fieldset>
        <legend>OPOS (mm)</legend>
        <label>bok <input type="number" id="opos-side" value="10" step="1" min="0"></label>
        <label>dół <input type="number" id="opos-bottom" value="10" step="1" min="0"></label>
        <label>góra <input type="number" id="opos-top" value="40" step="1" min="0"></label>
      </fieldset>

      <fieldset>
        <legend>Montaż wielu użytków</legend>
        <label><input type="checkbox" id="montage-enable"> włącz montaż (wymaga trybu z odstępami)</label>
        <div id="montage-rows"></div>
        <button type="button" id="montage-add">+ dodaj użytek</button>
      </fieldset>

      <fieldset>
        <legend>Zapis</legend>
        <label>nazwa <input type="text" id="base-name" value="wynik"></label>
        <button type="button" id="generate-btn">Generuj PDF-y</button>
      </fieldset>
    </section>

    <section class="preview">
      <div id="error" class="error" hidden></div>
      <div id="summary" class="summary">Wgraj PDF i ustaw parametry.</div>
      <div class="preview-block">
        <h2>Druk</h2>
        <img id="preview-print" alt="podgląd druku">
      </div>
      <div class="preview-block">
        <h2>Wykrojnik</h2>
        <img id="preview-cut" alt="podgląd wykrojnika">
      </div>
      <div class="downloads">
        <a id="download-print" href="/api/download/print" download hidden>Pobierz druk.pdf</a>
        <a id="download-cut" href="/api/download/cut" download hidden>Pobierz wykrojnik.pdf</a>
      </div>
    </section>
  </main>
  <script src="/static/app.js"></script>
</body>
</html>
```

- [ ] **Step 4: Zastąpić `web/static/style.css`**

```css
* { box-sizing: border-box; }
body { margin: 0; font: 14px/1.4 system-ui, sans-serif; color: #1d1d1f; background: #f5f5f7; }
header { padding: 10px 16px; background: #222; color: #fff; }
header h1 { margin: 0; font-size: 18px; font-weight: 600; }
.muted { color: #9aa0a6; font-weight: 400; }
main { display: grid; grid-template-columns: 360px 1fr; gap: 16px; padding: 16px; align-items: start; }
.controls fieldset { margin: 0 0 12px; border: 1px solid #d2d2d7; border-radius: 8px; padding: 10px 12px; background: #fff; }
.controls legend { font-weight: 600; padding: 0 4px; }
.controls label { display: inline-flex; align-items: center; gap: 4px; margin: 3px 8px 3px 0; }
.controls input[type=number] { width: 70px; }
.controls input[type=text] { width: 140px; }
.controls select { min-width: 90px; }
button { cursor: pointer; padding: 6px 12px; border: 1px solid #c7c7cc; border-radius: 6px; background: #fff; }
#generate-btn { background: #2f80ed; color: #fff; border-color: #2f80ed; font-weight: 600; }
.uploads { margin: 8px 0 0; padding-left: 18px; }
.preview { position: sticky; top: 16px; }
.preview-block { background: #fff; border: 1px solid #d2d2d7; border-radius: 8px; padding: 8px; margin-bottom: 12px; }
.preview-block h2 { margin: 0 0 6px; font-size: 14px; }
.preview img { width: 100%; height: auto; display: block; background: #fafafa; min-height: 80px; }
.summary { background: #eef3ff; border: 1px solid #cdd9f5; border-radius: 8px; padding: 8px 10px; margin-bottom: 12px; }
.error { background: #fdecea; border: 1px solid #f5c6c2; color: #a32018; border-radius: 8px; padding: 8px 10px; margin-bottom: 12px; }
.downloads a { display: inline-block; margin-right: 12px; }
.montage-row { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; border-top: 1px dashed #ddd; padding: 6px 0; }
.montage-row input[type=number] { width: 56px; }
```

- [ ] **Step 5: Uruchomić — PASS**

Run: `cd ~/summa-cut && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_web_frontend.py -q`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
cd ~/summa-cut
git add web/static/index.html web/static/style.css tests/test_web_frontend.py
git commit -m "feat(web): strona — układ dwukolumnowy, komplet kontrolek, lista montażu"
```

---

## Task 3: Kontroler `app.js`

**Files:**
- Modify: `web/static/app.js`

Brak sensownego testu jednostkowego JS bez przeglądarki — weryfikacja behawioralna w Task 4 (uvicorn + przeglądarka). Tu dostarczamy kompletny, działający kontroler.

- [ ] **Step 1: Zastąpić `web/static/app.js` pełną treścią**

```javascript
"use strict";
const $ = (id) => document.getElementById(id);
const uploads = {};          // name -> page_count
let montage = [];            // [{label,print_upload,print_page,cut_upload,cut_page,quantity}]
let previewTimer = null;
let generated = false;

async function init() {
  await fetch("/api/session", { method: "POST" });
  wireEvents();
}

function wireEvents() {
  $("upload-btn").addEventListener("click", doUpload);
  $("generate-btn").addEventListener("click", doGenerate);
  $("montage-add").addEventListener("click", () => { addMontageRow(); schedulePreview(); });
  $("montage-enable").addEventListener("change", onMontageToggle);
  // każda zmiana kontrolki → przeliczenie podglądu (debounce)
  $("controls").addEventListener("input", schedulePreview);
  $("controls").addEventListener("change", schedulePreview);
  // zmiana pliku → odśwież listę stron
  $("print-file").addEventListener("change", () => fillPages("print-file", "print-page"));
  $("cut-file").addEventListener("change", () => fillPages("cut-file", "cut-page"));
}

async function doUpload() {
  const files = $("upload-input").files;
  if (!files.length) return;
  for (const f of files) {
    const fd = new FormData();
    fd.append("file", f);
    const r = await fetch("/api/upload", { method: "POST", body: fd });
    if (r.ok) {
      const info = await r.json();
      uploads[info.name] = info.page_count;
    } else {
      showError((await r.json()).detail || "Błąd wgrywania.");
    }
  }
  renderUploads();
  refreshFileSelectors();
  schedulePreview();
}

function renderUploads() {
  $("uploads-list").innerHTML = Object.entries(uploads)
    .map(([n, pc]) => `<li>${n} <span class="muted">(${pc} str.)</span></li>`).join("");
}

function fileOptionsHtml(selected) {
  const names = Object.keys(uploads);
  return ['<option value="">—</option>']
    .concat(names.map((n) => `<option value="${n}" ${n === selected ? "selected" : ""}>${n}</option>`))
    .join("");
}

function pageOptionsHtml(name, selected) {
  const n = uploads[name] || 0;
  let o = "";
  for (let i = 0; i < n; i++) o += `<option value="${i}" ${i === selected ? "selected" : ""}>${i + 1}</option>`;
  return o || '<option value="0">1</option>';
}

function refreshFileSelectors() {
  for (const id of ["print-file", "cut-file"]) {
    const sel = $(id);
    const cur = sel.value;
    sel.innerHTML = fileOptionsHtml(cur);
  }
  fillPages("print-file", "print-page");
  fillPages("cut-file", "cut-page");
  renderMontage();
}

function fillPages(fileId, pageId) {
  const name = $(fileId).value;
  const sel = $(pageId);
  const cur = parseInt(sel.value || "0", 10);
  sel.innerHTML = pageOptionsHtml(name, cur);
}

function onMontageToggle() {
  const on = $("montage-enable").checked;
  if (on) {
    $("gap-on").checked = true;     // montaż wymaga trybu z odstępami
    $("gap-off").disabled = true;
    if (montage.length === 0) addMontageRow();
  } else {
    $("gap-off").disabled = false;
  }
  schedulePreview();
}

function addMontageRow() {
  montage.push({ label: "", print_upload: "", print_page: 0, cut_upload: "", cut_page: 0, quantity: 1 });
  renderMontage();
}

function renderMontage() {
  const box = $("montage-rows");
  const names = Object.keys(uploads);
  box.innerHTML = montage.map((m, i) => `
    <div class="montage-row" data-i="${i}">
      <input type="text" placeholder="etykieta" value="${m.label}" data-k="label">
      <select data-k="print_upload">${optList(names, m.print_upload)}</select>
      <input type="number" min="0" value="${m.print_page}" data-k="print_page" title="strona druku (od 0)">
      <select data-k="cut_upload">${optList(names, m.cut_upload)}</select>
      <input type="number" min="0" value="${m.cut_page}" data-k="cut_page" title="strona wykrojnika (od 0)">
      <input type="number" min="1" value="${m.quantity}" data-k="quantity" title="ilość">
      <button type="button" data-rm="${i}">usuń</button>
    </div>`).join("");
  box.querySelectorAll("[data-k]").forEach((el) => {
    el.addEventListener("input", () => {
      const row = el.closest(".montage-row");
      const i = parseInt(row.dataset.i, 10);
      const k = el.dataset.k;
      montage[i][k] = (k === "print_page" || k === "cut_page" || k === "quantity") ? parseInt(el.value || "0", 10) : el.value;
      schedulePreview();
    });
  });
  box.querySelectorAll("[data-rm]").forEach((b) => {
    b.addEventListener("click", () => {
      montage.splice(parseInt(b.dataset.rm, 10), 1);
      renderMontage();
      schedulePreview();
    });
  });
}

function optList(names, selected) {
  return ['<option value="">—</option>']
    .concat(names.map((n) => `<option value="${n}" ${n === selected ? "selected" : ""}>${n}</option>`))
    .join("");
}

function collectParams() {
  const gap = document.querySelector("input[name=gapmode]:checked").value === "gap";
  return {
    print_upload: $("print-file").value,
    print_page: parseInt($("print-page").value || "0", 10),
    cut_upload: $("cut-file").value || null,
    cut_page: parseInt($("cut-page").value || "0", 10),
    sheet_w_mm: parseFloat($("sheet-w").value),
    sheet_h_mm: parseFloat($("sheet-h").value),
    item_w_mm: parseFloat($("item-w").value),
    item_h_mm: parseFloat($("item-h").value),
    rotation_allowed: $("rotation").checked,
    gap_enabled: gap,
    gap_mm: parseFloat($("gap-mm").value),
    split_horizontal_groups: $("split").checked,
    split_max_spread: $("split-spread").checked,
    manual_grid_enabled: $("manual").checked,
    manual_columns: parseInt($("manual-cols").value || "0", 10),
    manual_rows: parseInt($("manual-rows").value || "0", 10),
    opos_side_offset_mm: parseFloat($("opos-side").value),
    opos_bottom_offset_mm: parseFloat($("opos-bottom").value),
    opos_top_offset_mm: parseFloat($("opos-top").value),
    montage: $("montage-enable").checked ? montage : [],
  };
}

function schedulePreview() {
  clearTimeout(previewTimer);
  previewTimer = setTimeout(updatePreview, 300);
}

async function updatePreview() {
  if (!$("print-file").value && !$("montage-enable").checked) return;
  const r = await fetch("/api/job", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(collectParams()),
  });
  if (r.ok) {
    const s = await r.json();
    clearError();
    $("summary").textContent =
      `Użytków: ${s.count} (pojemność ${s.capacity_count}` +
      (s.requested_count ? `, zamówiono ${s.requested_count}` : "") +
      `) · ${s.rows}×${s.columns}` + (s.used_rotation ? " · obrót 90°" : "");
    const t = Date.now();
    $("preview-print").src = `/api/preview/print.png?t=${t}`;
    $("preview-cut").src = `/api/preview/cut.png?t=${t}`;
  } else {
    showError((await r.json()).detail || "Błąd układu.");
  }
}

async function doGenerate() {
  const r = await fetch("/api/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ base_name: $("base-name").value || "wynik" }),
  });
  if (r.ok) {
    clearError();
    generated = true;
    const t = Date.now();
    const dp = $("download-print"), dc = $("download-cut");
    dp.href = `/api/download/print?t=${t}`; dp.hidden = false;
    dc.href = `/api/download/cut?t=${t}`; dc.hidden = false;
    $("summary").textContent = "Wygenerowano. Pobierz pliki po prawej.";
  } else {
    showError((await r.json()).detail || "Błąd generowania (najpierw ustaw poprawny układ).");
  }
}

function showError(msg) { const e = $("error"); e.textContent = msg; e.hidden = false; }
function clearError() { $("error").hidden = true; }

init();
```

- [ ] **Step 2: Sanity — plik serwowany i niepusty**

Run:
```bash
cd ~/summa-cut && QT_QPA_PLATFORM=offscreen .venv/bin/python -c "
from fastapi.testclient import TestClient
from web.server import create_app
from web.sessions import SessionStore
import tempfile
c = TestClient(create_app(store=SessionStore(base_dir=tempfile.mkdtemp())))
js = c.get('/static/app.js').text
print('app.js bytes', len(js), 'ma updatePreview:', 'updatePreview' in js, 'ma collectParams:', 'collectParams' in js)
"
```
Expected: niezerowy rozmiar, `True True`.

- [ ] **Step 3: Pełny zestaw testów przechodzi**

Run: `cd ~/summa-cut && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -q`
Expected: wszystkie passed (48 z Fazy 2a + 4 frontend = 52).

- [ ] **Step 4: Commit**

```bash
cd ~/summa-cut
git add web/static/app.js
git commit -m "feat(web): kontroler app.js (sesja, upload, podgląd na żywo, montaż, generuj)"
```

---

## Task 4: Weryfikacja end-to-end (uvicorn) + tag

**Files:** brak zmian (weryfikacja)

- [ ] **Step 1: Start serwera w tle**

Run (w tle): `cd ~/summa-cut && QT_QPA_PLATFORM=offscreen .venv/bin/python -m uvicorn web.app:app --port 8012 --log-level warning`

- [ ] **Step 2: Pełny przepływ przez HTTP (sesja→upload→job→preview→generate→download) jednym klientem z ciasteczkami**

Run:
```bash
cd ~/summa-cut && QT_QPA_PLATFORM=offscreen .venv/bin/python -c "
import io, time, urllib.request, urllib.error, http.cookiejar, json, fitz
from summa_cut.pdf_io import MM_PER_POINT
PT=1.0/MM_PER_POINT; side=40*PT
d=fitz.open(); d.new_page(width=side,height=side).draw_rect(fitz.Rect(3,3,side-3,side-3),color=(0,0,1)); pdf=d.tobytes(); d.close()
cj=http.cookiejar.CookieJar(); op=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
def post_json(p,obj):
    r=urllib.request.Request('http://127.0.0.1:8012'+p, data=json.dumps(obj).encode(), headers={'Content-Type':'application/json'}, method='POST'); return op.open(r)
# strona
print('GET / ->', op.open('http://127.0.0.1:8012/').status)
print('session ->', op.open(urllib.request.Request('http://127.0.0.1:8012/api/session', method='POST')).status)
# upload multipart
b='----b'; body=('--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"src.pdf\"\r\nContent-Type: application/pdf\r\n\r\n'%b).encode()+pdf+('\r\n--%s--\r\n'%b).encode()
ru=op.open(urllib.request.Request('http://127.0.0.1:8012/api/upload', data=body, headers={'Content-Type':'multipart/form-data; boundary=%s'%b}, method='POST'))
print('upload ->', ru.status, json.loads(ru.read())['page_count'])
job=dict(print_upload='src.pdf',print_page=0,cut_upload='src.pdf',cut_page=0,sheet_w_mm=330.0,sheet_h_mm=480.0,item_w_mm=30.0,item_h_mm=30.0,gap_enabled=True,gap_mm=3.0)
rj=post_json('/api/job',job); print('job ->', rj.status, json.loads(rj.read())['count'])
rp=op.open('http://127.0.0.1:8012/api/preview/print.png'); print('preview ->', rp.status, rp.headers['content-type'])
rg=post_json('/api/generate',{'base_name':'web'}); print('generate ->', rg.status, json.loads(rg.read())['print_name'])
rd=op.open('http://127.0.0.1:8012/api/download/print'); print('download ->', rd.status, rd.read()[:5])
"
```
Expected: kolejno statusy 200, niezerowy `count`, `image/png`, `web_druk.pdf`, `b'%PDF-'`.

- [ ] **Step 3: Zatrzymać serwer**

Zakończ proces uvicorn uruchomiony w Step 1.

- [ ] **Step 4: Commit (jeśli cokolwiek doszło) + tag**

```bash
cd ~/summa-cut
git tag -a phase2b-frontend -m "Phase 2b: frontend HTML/JS (tryb główny + montaż) nad API"
git log --oneline -6
```

- [ ] **Step 5: Weryfikacja wizualna (ręczna, dla człowieka)**

Poinformuj prowadzącego: `cd ~/summa-cut && .venv/bin/python -m uvicorn web.app:app --port 8012`, otwórz `http://127.0.0.1:8012/`, wgraj PDF, ustaw rozmiar użytku, sprawdź podgląd druku/wykrojnika i pobranie. (Headless pytest nie zobaczy renderu przeglądarki — to potwierdza człowiek lub osobny test Playwright, poza zakresem tej fazy.)

---

## Self-Review (autor planu)

**Pokrycie specu (Faza 2 front, tryb główny + montaż, układ dwukolumnowy):**
- Serwowanie strony + statyki ✔ Task 1. Układ dwukolumnowy (kontrolki lewo / podglądy prawo) ✔ `style.css` grid 360px/1fr (Task 2). Komplet kontrolek 1:1 z `JobParams` ✔ `index.html` (Task 2) + `collectParams` (Task 3). Lista montażowa add/remove/quantity ✔ Task 3 (`renderMontage`), wysyłana w `montage` do `/api/job`. Podgląd server-rendered PNG na żywo z debounce ✔ `schedulePreview`/`updatePreview` (300 ms, cache-busting). Generuj/pobierz ✔ `doGenerate` + linki. Montaż wymusza tryb z odstępami w UI ✔ `onMontageToggle` (spójne z guardem backendu z Fazy 2a). Trasy API niezmienione ✔.
- Testowalne headless: serwowanie strony + kontrakt id-ów (`test_web_frontend.py`); logika JS weryfikowana behawioralnie w Task 4 (uvicorn, pełny przepływ HTTP) + ręcznie wizualnie (Step 5). To akceptowalna granica bez wprowadzania przeglądarki/Playwright (YAGNI dla narzędzia wewn.).

**Placeholdery:** brak realnych. Pliki `index.html`/`style.css`/`app.js` najpierw tworzone minimalnie (Task 1) i jawnie zastępowane pełną treścią (Task 2/3) — to świadoma kolejność TDD-serwowania, nie placeholder.

**Spójność typów/nazw:** zestaw `REQUIRED_IDS` w teście (Task 2) = id-y używane w `app.js` (Task 3) = id-y w `index.html` (Task 2). `collectParams()` zwraca dokładnie pola `JobParams` (Faza 1/2a): print_upload/print_page/cut_upload/cut_page/sheet_*/item_*/rotation_allowed/gap_enabled/gap_mm/split_*/manual_*/opos_*_offset_mm/montage. Element montażu = {label,print_upload,print_page,cut_upload,cut_page,quantity} = `MontageItemParams`. Endpoints i kształty odpowiedzi zgodne z `server.py` (count/capacity_count/requested_count/rows/columns/used_rotation; print_name/cut_name).

**Ryzyka do pilnowania w trakcie:**
1. `StaticFiles`/`FileResponse` bez dodatkowych zależności (potwierdzone w środowisku).
2. Import `Path` w `server.py` już istnieje (Faza 1) — nie dublować; dodać tylko `FileResponse`, `StaticFiles`.
3. `TestClient` bez `with` nie uruchamia lifespan — to OK; trasy `/` i `/static` działają niezależnie od lifespanu.
4. Uvicorn w Task 4 uruchamiany w tle — pamiętać o zatrzymaniu procesu po teście (Step 3).
```
