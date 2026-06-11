# Edytor 3×3 trybu specjalnego (web) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Zastąpić 8 surowych pól trybu specjalnego interaktywnym edytorem 3×3 (przeciąganie kafli z realną grafiką, Shift = drugi tryb), zachowując model 2×2 powtarzalny i nie zmieniając silnika.

**Architecture:** Frontend dostaje widget SVG rysujący 9 kafli (środek edytowalny, 8 powtórek) z obrazka pojedynczego przygotowanego kafla; przeciąganie/strzałki sterują 8 istniejącymi offsetami (mapowanie 1:1 z desktopu, Shift przełącza przesuw↔odstęp). Backend dostaje jeden nowy endpoint `GET /api/special/tile.png` renderujący kafel (druk + obrys wykrojnika) z przyciętych PDF-ów sesji. Silnik, `prepare`, `/api/job`, generate — bez zmian.

**Tech Stack:** Python, PyMuPDF (fitz), FastAPI; vanilla JS + SVG (bez frameworka, jeden plik `app.js`). Testy: pytest + `node --check` + smoke Playwright (plugin `example-skills:webapp-testing`).

---

## File Structure

- **Modify `summa_cut/special_trim.py`** — dodać stałe `SPECIAL_PRINT_NAME`/`SPECIAL_CUT_NAME` i użyć ich w `prepare_special_trim` (zamiast literałów). Zero zmian logiki.
- **Modify `web/preview_render.py`** — dodać `render_special_tile_png(print_pdf_path, cut_pdf_path, max_px)` (kafel: druk + obrys wykrojnika na wierzchu).
- **Modify `web/server.py`** — trasa `GET /api/special/tile.png`.
- **Modify `web/static/index.html`** — sekcję `special-offsets` (8 pól) zamienić na: kontener edytora `<svg id="special-editor">` + legendę + zwijane „dostrojenie ręczne" (`<details>`) z tymi samymi 8 polami (id bez zmian).
- **Modify `web/static/app.js`** — czyste funkcje `baseRow/baseCol/tileOrigin/applyDrag` (eksport na `window` do testów), `readOffsets/writeOffsets`, `renderSpecialEditor`, obsługa pointer/klawiszy, wpięcie w `wireEvents`/`doSpecialPrepare`/`invalidateSpecial`.
- **Modify `web/static/style.css`** — styl edytora.
- **Test `tests/test_web_preview.py`** — `render_special_tile_png` zwraca niezerowy PNG.
- **Test `tests/test_web_api.py`** — `/api/special/tile.png` 200 po prepare, 400 bez.
- **Test `tests/test_web_frontend.py`** — kontrakt id-ów edytora + odwołania w app.js.

---

## Task 1: Backend — endpoint `GET /api/special/tile.png`

**Files:**
- Modify: `summa_cut/special_trim.py`
- Modify: `web/preview_render.py`
- Modify: `web/server.py`
- Test: `tests/test_web_preview.py`, `tests/test_web_api.py`

- [ ] **Step 1: Write failing test — render kafla**

Dopisz do `tests/test_web_preview.py`:

```python
def test_render_special_tile_png_nonzero(tmp_path):
    import fitz
    from web.preview_render import render_special_tile_png
    # „przycięty druk": szare wypełnienie; „przycięty wykrojnik": czerwony obrys
    pp = tmp_path / "p.pdf"
    doc = fitz.open(); pg = doc.new_page(width=80, height=60)
    pg.draw_rect(fitz.Rect(0, 0, 80, 60), color=(0, 0, 0), fill=(0.6, 0.6, 0.6), width=0)
    doc.save(str(pp)); doc.close()
    cp = tmp_path / "c.pdf"
    doc = fitz.open(); pg = doc.new_page(width=80, height=60)
    pg.draw_rect(fitz.Rect(2, 2, 78, 58), color=(1, 0, 0), width=1.0)
    doc.save(str(cp)); doc.close()

    png = render_special_tile_png(str(pp), str(cp), max_px=200)
    assert isinstance(png, bytes) and len(png) > 100
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
```

- [ ] **Step 2: Run — verify fail**

Run: `cd ~/summa-cut && .venv/bin/python -m pytest tests/test_web_preview.py -q -k special_tile`
Expected: FAIL — `ImportError: cannot import name 'render_special_tile_png'`.

- [ ] **Step 3: Implement render function**

W `web/preview_render.py` dopisz (po `render_output_png`):

```python
def render_special_tile_png(print_pdf_path: str, cut_pdf_path: str, max_px: int = PREVIEW_MAX_PX) -> bytes:
    """Renderuje pojedynczy przygotowany kafel: pełna grafika druku + obrys wykrojnika na wierzchu.

    Używane przez edytor 3×3 trybu specjalnego — front powiela ten obrazek 9×."""
    with fitz.open(print_pdf_path) as pdoc, fitz.open(cut_pdf_path) as cdoc:
        rect = pdoc[0].rect
        out = fitz.open()
        try:
            page = out.new_page(width=rect.width, height=rect.height)
            page.show_pdf_page(page.rect, pdoc, 0)   # druk pod spodem
            page.show_pdf_page(page.rect, cdoc, 0)   # wykrojnik na wierzchu
            scale = max_px / max(rect.width, rect.height, 1.0)
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            return pix.tobytes("png")
        finally:
            out.close()
```

- [ ] **Step 4: Run — verify pass**

Run: `cd ~/summa-cut && .venv/bin/python -m pytest tests/test_web_preview.py -q -k special_tile`
Expected: PASS.

- [ ] **Step 5: Write failing test — trasa**

Dopisz do `tests/test_web_api.py` (reużywa `_client(tmp_path)` i `_make_special_source_bytes()` z Fazy 3):

```python
def test_special_tile_png_after_prepare(tmp_path):
    c = _client(tmp_path)
    c.post("/api/session")
    data = _make_special_source_bytes()
    c.post("/api/upload", files={"file": ("zrodlo.pdf", data, "application/pdf")})
    c.post("/api/special/prepare", json={
        "print_upload": "zrodlo.pdf", "print_page": 0,
        "cut_upload": "zrodlo.pdf", "cut_page": 0, "bleed_mm": 3.0,
    })
    r = c.get("/api/special/tile.png")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "image/png"
    assert len(r.content) > 100


def test_special_tile_png_without_prepare_is_400(tmp_path):
    c = _client(tmp_path)
    c.post("/api/session")
    r = c.get("/api/special/tile.png")
    assert r.status_code == 400
```

- [ ] **Step 6: Run — verify fail**

Run: `cd ~/summa-cut && .venv/bin/python -m pytest tests/test_web_api.py -q -k tile`
Expected: FAIL — 404 (trasa nie istnieje).

- [ ] **Step 7: Implement constants + route**

W `summa_cut/special_trim.py` dodaj stałe (zaraz po `_BEZIER_STEPS`):

```python
SPECIAL_PRINT_NAME = "__special_print__.pdf"
SPECIAL_CUT_NAME = "__special_cut__.pdf"
```

i w `prepare_special_trim` zamień literały na stałe:

```python
        out_print = work_dir / SPECIAL_PRINT_NAME
        out_cut = work_dir / SPECIAL_CUT_NAME
```

W `web/server.py` rozszerz import preview i dodaj import stałych:

```python
from web.preview_render import render_output_png, render_special_tile_png
from summa_cut.special_trim import prepare_special_trim, SPECIAL_PRINT_NAME, SPECIAL_CUT_NAME
```

(jeśli `prepare_special_trim` jest już importowany osobno — scal w jedną linię importu). Dodaj trasę po `/api/special/prepare`:

```python
    @app.get("/api/special/tile.png")
    def special_tile(session: Session = Depends(current_session)) -> RawResponse:
        p = session.uploads.get(SPECIAL_PRINT_NAME)
        c = session.uploads.get(SPECIAL_CUT_NAME)
        if p is None or c is None:
            raise HTTPException(status_code=400, detail="Najpierw przygotuj wykrojnik (/api/special/prepare).")
        png = render_special_tile_png(p.path, c.path)
        return RawResponse(content=png, media_type="image/png")
```

(`RawResponse` jest już zaimportowany w server.py jako alias `Response`. Sprawdź realną nazwę aliasu w pliku — w Fazie 1 było `from fastapi.responses import Response as RawResponse`; użyj tej samej nazwy co istniejąca trasa `/api/preview/{which}.png`.)

- [ ] **Step 8: Run — verify pass + full suite**

Run: `cd ~/summa-cut && .venv/bin/python -m pytest tests/test_web_api.py tests/test_web_preview.py -q && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
Expected: PASS, brak regresji.

- [ ] **Step 9: Commit**

```bash
cd ~/summa-cut && git add summa_cut/special_trim.py web/preview_render.py web/server.py tests/test_web_api.py tests/test_web_preview.py
git commit -m "feat(special): endpoint /api/special/tile.png (kafel druk+obrys) + stałe nazw przyciętych PDF"
```

---

## Task 2: Frontend — edytor 3×3 (HTML + logika drag + pola ręczne)

**Files:**
- Modify: `web/static/index.html`
- Modify: `web/static/app.js`
- Modify: `web/static/style.css`
- Test: `tests/test_web_frontend.py`

- [ ] **Step 1: Write failing test — kontrakt id-ów**

Dopisz do `tests/test_web_frontend.py`:

```python
def test_index_has_3x3_editor():
    from pathlib import Path
    html = (Path(__file__).resolve().parents[1] / "web" / "static" / "index.html").read_text(encoding="utf-8")
    assert 'id="special-editor"' in html
    assert 'id="special-legend"' in html
    assert "<details" in html and "Dostrojenie ręczne" in html
    # 8 pól offsetów nadal obecne (przeniesione do <details>)
    for el_id in ["special-row0", "special-row1", "special-col0", "special-col1",
                  "special-colx0", "special-colx1", "special-rowy0", "special-rowy1"]:
        assert f'id="{el_id}"' in html


def test_app_js_has_editor_logic():
    from pathlib import Path
    js = (Path(__file__).resolve().parents[1] / "web" / "static" / "app.js").read_text(encoding="utf-8")
    assert "/api/special/tile.png" in js
    assert "tileOrigin" in js and "applyDrag" in js
    assert "renderSpecialEditor" in js
```

- [ ] **Step 2: Run — verify fail**

Run: `cd ~/summa-cut && .venv/bin/python -m pytest tests/test_web_frontend.py -q -k "3x3 or editor_logic"`
Expected: FAIL — brak id-ów/odwołań.

- [ ] **Step 3: Zmień HTML — edytor zamiast surowej siatki pól**

W `web/static/index.html` zamień cały blok `<fieldset class="special-offsets"> … </fieldset>` (linie ~70-80) na:

```html
          <div class="special-editor-wrap">
            <svg id="special-editor" viewBox="0 0 300 260" tabindex="0" role="img" aria-label="Edytor układu 3×3"></svg>
            <p id="special-legend" class="special-legend">Przeciągnij kafel: <b>bez Shift</b> = przesuń rząd/kolumnę; <b>z Shiftem</b> = zmień odstęp rzędów/kolumn. Strzałki = krok 0,1 mm.</p>
          </div>
          <details class="special-offsets">
            <summary>Dostrojenie ręczne (mm)</summary>
            <label>rząd 0 X <input type="number" id="special-row0" value="0" step="0.1"></label>
            <label>rząd 1 X <input type="number" id="special-row1" value="0" step="0.1"></label>
            <label>kol. 0 Y <input type="number" id="special-col0" value="0" step="0.1"></label>
            <label>kol. 1 Y <input type="number" id="special-col1" value="0" step="0.1"></label>
            <label>kol. 0 X <input type="number" id="special-colx0" value="0" step="0.1"></label>
            <label>kol. 1 X <input type="number" id="special-colx1" value="0" step="0.1"></label>
            <label>rząd 0 Y <input type="number" id="special-rowy0" value="0" step="0.1"></label>
            <label>rząd 1 Y <input type="number" id="special-rowy1" value="0" step="0.1"></label>
          </details>
```

(8 inputów z NIEZMIENIONYMI id — `collectParams()`/`specialOffsets()` działają bez zmian.)

- [ ] **Step 4: Dodaj logikę edytora do `app.js`**

W `web/static/app.js`, na górze (po linii `const special = {...}`), dodaj stan i czyste funkcje:

```javascript
// --- Edytor 3×3 trybu specjalnego -------------------------------------------
let selectedTile = [1, 1];     // [row, col] aktywnego kafla (domyślnie środek)
let tileImgUrl = null;          // URL obrazka pojedynczego kafla (po prepare)
let editorDrag = null;          // {row, col, startX, startY, off, scale} podczas drag

// rząd/kol 0 i 2 mapują się na bazę 0 (zewnętrzne), 1 na bazę 1 (środkowa) — jak desktop
function baseRow(row) { return (row === 0 || row === 2) ? 0 : 1; }
function baseCol(col) { return (col === 0 || col === 2) ? 0 : 1; }

// off = {row:[a,b], col:[a,b], colx:[a,b], rowy:[a,b]} w mm. Port _preview_tile_origin_pt.
function tileOrigin(row, col, off, pageW, pageH) {
  const firstX = off.row[baseRow(row)] + off.colx[0];
  const secondX = pageW + off.row[baseRow(row)] + off.colx[1];
  const x = col === 0 ? firstX : (col === 1 ? secondX : secondX + (secondX - firstX));
  const firstY = off.col[baseCol(col)] + off.rowy[0];
  const secondY = pageH + off.col[baseCol(col)] + off.rowy[1];
  const y = row === 0 ? firstY : (row === 1 ? secondY : secondY + (secondY - firstY));
  return { x, y };
}

// Przeciąganie kafla (row,col) o (dxMm,dyMm). Bez Shift: przesuw rzędu/kolumny;
// z Shift: odstęp kolumn/rzędów. Mutuje i zwraca off. Port mouseMoveEvent z desktopu.
function applyDrag(off, shift, row, col, dxMm, dyMm) {
  const br = baseRow(row), bc = baseCol(col);
  if (shift) { off.colx[bc] += dxMm; off.rowy[br] += dyMm; }
  else { off.row[br] += dxMm; off.col[bc] += dyMm; }
  return off;
}
// eksport do testów (Playwright page.evaluate)
window.tileOrigin = tileOrigin;
window.applyDrag = applyDrag;
window.baseRow = baseRow;
window.baseCol = baseCol;

function readOffsets() {
  const v = (id) => parseFloat($(id).value) || 0;
  return {
    row: [v("special-row0"), v("special-row1")],
    col: [v("special-col0"), v("special-col1")],
    colx: [v("special-colx0"), v("special-colx1")],
    rowy: [v("special-rowy0"), v("special-rowy1")],
  };
}
function writeOffsets(off) {
  const r = (n) => Math.round(n * 1000) / 1000;
  $("special-row0").value = r(off.row[0]);  $("special-row1").value = r(off.row[1]);
  $("special-col0").value = r(off.col[0]);  $("special-col1").value = r(off.col[1]);
  $("special-colx0").value = r(off.colx[0]); $("special-colx1").value = r(off.colx[1]);
  $("special-rowy0").value = r(off.rowy[0]); $("special-rowy1").value = r(off.rowy[1]);
}

function renderSpecialEditor() {
  const svg = $("special-editor");
  if (!svg) return;
  if (!(special.ready && tileImgUrl)) { svg.innerHTML = ""; return; }
  const off = readOffsets();
  const pw = special.pageW, ph = special.pageH;
  const tiles = [];
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (let row = 0; row < 3; row++) {
    for (let col = 0; col < 3; col++) {
      const o = tileOrigin(row, col, off, pw, ph);
      tiles.push({ row, col, x: o.x, y: o.y });
      minX = Math.min(minX, o.x); minY = Math.min(minY, o.y);
      maxX = Math.max(maxX, o.x + pw); maxY = Math.max(maxY, o.y + ph);
    }
  }
  const W = 300, H = 260, M = 18;
  const bw = Math.max(maxX - minX, 1), bh = Math.max(maxY - minY, 1);
  const scale = Math.min((W - 2 * M) / bw, (H - 2 * M) / bh);
  const ox = (W - bw * scale) / 2 - minX * scale;
  const oy = (H - bh * scale) / 2 - minY * scale;
  svg.dataset.scale = scale;   // px-na-mm dla draga
  const parts = [];
  for (const t of tiles) {
    const x = ox + t.x * scale, y = oy + t.y * scale, w = pw * scale, h = ph * scale;
    const isCenter = (t.row === 1 && t.col === 1);
    const isSel = (t.row === selectedTile[0] && t.col === selectedTile[1]);
    const op = isCenter ? 1 : 0.4;
    parts.push(`<image href="${tileImgUrl}" x="${x}" y="${y}" width="${w}" height="${h}" opacity="${op}" preserveAspectRatio="none"/>`);
    const stroke = isSel ? "#111" : (isCenter ? "#2f80ed" : "#bbb");
    const sw = isSel ? 2 : 1;
    const dash = isSel ? ' stroke-dasharray="4 3"' : "";
    parts.push(`<rect class="tile" data-row="${t.row}" data-col="${t.col}" x="${x}" y="${y}" width="${w}" height="${h}" fill="transparent" stroke="${stroke}" stroke-width="${sw}"${dash}/>`);
  }
  svg.innerHTML = parts.join("");
}

function editorPointerDown(e) {
  const target = e.target.closest(".tile");
  if (!target) return;
  const row = parseInt(target.dataset.row, 10), col = parseInt(target.dataset.col, 10);
  selectedTile = [row, col];
  const scale = parseFloat($("special-editor").dataset.scale) || 1;
  editorDrag = { row, col, startX: e.clientX, startY: e.clientY, off: readOffsets(), scale };
  try { $("special-editor").setPointerCapture(e.pointerId); } catch (_) {}
  renderSpecialEditor();
}
function editorPointerMove(e) {
  if (!editorDrag) return;
  const dxMm = (e.clientX - editorDrag.startX) / editorDrag.scale;
  const dyMm = (e.clientY - editorDrag.startY) / editorDrag.scale;
  const off = JSON.parse(JSON.stringify(editorDrag.off));  // od świeżego snapshotu, bez kumulacji
  applyDrag(off, e.shiftKey, editorDrag.row, editorDrag.col, dxMm, dyMm);
  writeOffsets(off);
  renderSpecialEditor();
}
function editorPointerUp() {
  if (!editorDrag) return;
  editorDrag = null;
  schedulePreview();
}
function editorKey(e) {
  if (!special.ready) return;
  const step = 0.1;
  let dx = 0, dy = 0;
  if (e.key === "ArrowLeft") dx = -step;
  else if (e.key === "ArrowRight") dx = step;
  else if (e.key === "ArrowUp") dy = -step;
  else if (e.key === "ArrowDown") dy = step;
  else return;
  e.preventDefault();
  const off = readOffsets();
  applyDrag(off, e.shiftKey, selectedTile[0], selectedTile[1], dx, dy);
  writeOffsets(off);
  renderSpecialEditor();
  schedulePreview();
}
```

- [ ] **Step 5: Wepnij edytor w `wireEvents`, `doSpecialPrepare`, `invalidateSpecial`**

W `wireEvents()` (po linii `$("special-bleed").addEventListener("input", invalidateSpecial);`) dodaj:

```javascript
  const ed = $("special-editor");
  ed.addEventListener("pointerdown", editorPointerDown);
  ed.addEventListener("pointermove", editorPointerMove);
  ed.addEventListener("pointerup", editorPointerUp);
  ed.addEventListener("keydown", editorKey);
  // ręczna zmiana pól offsetów → przerysuj edytor (no-op gdy niegotowy)
  $("controls").addEventListener("input", renderSpecialEditor);
```

W `doSpecialPrepare()`, zaraz po `special.ready = true;` (przed `status.textContent = ...`) dodaj:

```javascript
  tileImgUrl = `/api/special/tile.png?t=${Date.now()}`;
  selectedTile = [1, 1];
  renderSpecialEditor();
```

W `invalidateSpecial()`, po wyzerowaniu `special.*` (np. po `special.pageH = 0;`) dodaj:

```javascript
  tileImgUrl = null;
  renderSpecialEditor();
```

- [ ] **Step 6: Styl edytora — `web/static/style.css`**

Dopisz:

```css
.special-editor-wrap { margin: 8px 0; }
#special-editor { width: 100%; max-width: 340px; height: 260px; background:
  repeating-conic-gradient(#f2f2f2 0% 25%, #e7e7e7 0% 50%) 0 / 16px 16px;
  border: 1px solid #ccc; border-radius: 6px; touch-action: none; outline: none; }
#special-editor .tile { cursor: grab; }
.special-legend { font-size: 12px; color: #666; margin: 4px 0 0; max-width: 340px; }
.special-offsets { margin-top: 8px; }
.special-offsets summary { cursor: pointer; font-size: 13px; color: #2f80ed; }
.special-offsets label { display: inline-block; width: 9rem; }
```

- [ ] **Step 7: Run — kontrakt + składnia**

Run:
```bash
cd ~/summa-cut && .venv/bin/python -m pytest tests/test_web_frontend.py -q && node --check web/static/app.js
```
Expected: PASS + `app.js` bez błędów składni.

- [ ] **Step 8: Full suite + commit**

Run: `cd ~/summa-cut && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
Expected: PASS, brak regresji.

```bash
cd ~/summa-cut && git add web/static/index.html web/static/app.js web/static/style.css tests/test_web_frontend.py
git commit -m "feat(special): interaktywny edytor 3×3 (drag, Shift, kafel z grafiką) zamiast 8 pól"
```

---

## Task 3: Smoke E2E warstwy drag (Playwright, plugin webapp-testing)

**Files:** brak commitowanego kodu — to weryfikacja warstwy JS, której pytest nie łapie. Użyj pluginu `example-skills:webapp-testing` (Playwright) przeciw żywemu serwerowi.

- [ ] **Step 1: Odpal serwer testowy**

```bash
cd ~/summa-cut && .venv/bin/python -m uvicorn web.app:app --port 8013 &
```
(zapamiętaj PID; ubij po teście). Sprawdź `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8013/` → `200`.

- [ ] **Step 2: Przygotuj wsadowy PDF z wektorowym obrysem**

```bash
cd ~/summa-cut && QT_QPA_PLATFORM=offscreen .venv/bin/python - <<'PY'
import fitz
doc=fitz.open(); p=doc.new_page(width=120,height=100)
p.draw_rect(fitz.Rect(20,20,70,50),color=(0,0,0),fill=(0.6,0.6,0.6),width=0)
p.draw_rect(fitz.Rect(20,20,70,50),color=(1,0,0),width=0.5)
doc.save("/tmp/sc_editor_src.pdf"); doc.close()
print("ok")
PY
```

- [ ] **Step 3: Smoke przez Playwright (plugin webapp-testing)**

Użyj pluginu, żeby w headless Chromium:
1. Otworzyć `http://127.0.0.1:8013/`.
2. Ustawić plik w `#upload-input` (`/tmp/sc_editor_src.pdf`) i kliknąć `#upload-btn`; poczekać aż `#print-file` i `#cut-file` mają opcję `zrodlo.pdf`; wybrać ją w obu + strona 0.
3. Zaznaczyć `#special-enable`, kliknąć `#special-prepare-btn`, poczekać aż `#special-status` zawiera „Gotowe".
4. **Asercja matematyki (page.evaluate):**
   - `tileOrigin(1,1,{row:[0,0],col:[0,0],colx:[0,0],rowy:[0,0]},50,30)` ≈ `{x:50,y:30}`.
   - `applyDrag({row:[0,0],col:[0,0],colx:[0,0],rowy:[0,0]},false,1,1,2,3)` → `row:[0,2]`, `col:[0,3]` (bez Shift przesuwa rząd/kolumnę).
   - `applyDrag({...zera},true,1,1,2,3)` → `colx:[0,2]`, `rowy:[0,3]` (z Shift = odstęp).
5. **Asercja renderu:** `#special-editor` ma 9 elementów `<image>` i 9 `rect.tile`.
6. **Asercja drag (bez Shift):** zasymulować pointerdown→move→up na środkowym kaflu (`rect.tile[data-row="1"][data-col="1"]`), przesuw ~30 px w prawo; po puszczeniu wartości `#special-row1` ≠ 0. Zrobić zrzut ekranu edytora.
7. **Asercja drag z Shift:** powtórzyć z `shiftKey`; `#special-colx1` (lub odpowiedni) ≠ 0.

Zapisz zrzut ekranu (np. `/tmp/sc_editor.png`) do wglądu. Jeśli któraś asercja padnie — to realny błąd warstwy JS; napraw w `app.js` i powtórz (nie obchodź asercji).

- [ ] **Step 4: Sprzątanie**

Ubij uvicorna (`kill <PID>`). Smoke nie commitujemy (artefakt = potwierdzenie + zrzut). Jeśli plugin pozwala zapisać skrypt Playwright do repo bez nowych zależności runtime — można, ale nie jest to wymagane.

---

## Task 4: Deploy na drukpolu + smoke + pamięć

**Files:** ew. `project_summacut.md` (pamięć). Bez nowych zależności (tile.png używa obecnego fitz).

- [ ] **Step 1: Rsync + rebuild**

```bash
rsync -az --delete --exclude .venv --exclude .git --exclude __pycache__ --exclude .superpowers ~/summa-cut/ root@REDACTED-HOST:/srv/app/ \
&& ssh root@REDACTED-HOST 'cd /srv/app && docker compose up -d --build'
```
Expected: kontener `summa-cut-web` wstaje.

- [ ] **Step 2: Smoke na żywym drukpolu**

```bash
BASE=http://REDACTED-HOST:8800; Jar=/tmp/sc_t.txt; rm -f $Jar
curl -s -c $Jar -X POST $BASE/api/session -o /dev/null
curl -s -b $Jar -X POST $BASE/api/upload -F "file=@/tmp/sc_editor_src.pdf;type=application/pdf" -o /dev/null -w "upload %{http_code}\n"
curl -s -b $Jar -X POST $BASE/api/special/prepare -H 'Content-Type: application/json' -d '{"print_upload":"sc_editor_src.pdf","print_page":0,"cut_upload":"sc_editor_src.pdf","cut_page":0,"bleed_mm":3.0}' -o /dev/null -w "prepare %{http_code}\n"
curl -s -b $Jar $BASE/api/special/tile.png -o /dev/null -w "tile %{http_code} %{content_type} %{size_download}B\n"
curl -s $BASE/ | grep -o 'id="special-editor"' | head -1
```
Expected: `upload 200`, `prepare 200`, `tile 200 image/png >0B`, oraz `id="special-editor"` (nowy front live).

- [ ] **Step 3: Wzrokowa weryfikacja usera**

User otwiera http://REDACTED-LAN:8800, włącza tryb specjalny, przygotowuje wykrojnik, przeciąga kafle (bez/z Shift), sprawdza czy podgląd arkusza reaguje. Potwierdza, że UI jest intuicyjny.

- [ ] **Step 4: Aktualizacja pamięci**

Dopisz w `project_summacut.md`: edytor 3×3 wdrożony (tag np. `special-editor`), nowy endpoint `tile.png`, że to czysto UI + 1 endpoint, liczba testów.

---

## Self-Review

**1. Spec coverage:**
- 3×3 podgląd / 2×2 param → Task 2 `tileOrigin` rysuje 9 kafli z bazą 0/1. ✓
- Kafle z realną grafiką (druk + obrys) → Task 1 `render_special_tile_png` (druk pod, wykrojnik na wierzch) + Task 2 `<image>`×9. ✓
- Dwa tryby przez Shift (bez przełącznika) + legenda → Task 2 `applyDrag(shift)`, `#special-legend`. ✓
- 8 pól → zwijane „dostrojenie ręczne", dwukierunkowo → Task 2 `<details>` + `readOffsets`/`writeOffsets` + `#controls input`→`renderSpecialEditor`; drag→`writeOffsets`. ✓
- Strzałki 0,1 mm (z Shift = odstęp) → Task 2 `editorKey`. ✓
- Żywy podgląd po puszczeniu (throttle) → Task 2 `editorPointerUp`→`schedulePreview` (debounce 300 ms istnieje). ✓
- Endpoint `tile.png` 400 bez prepare → Task 1. ✓
- Silnik/prepare/job/generate bez zmian → tak (Taski nie dotykają `summa_cut/layout|export`, `job_builder`, `_build_special_job`). ✓
- Testy pytest + Playwright → Taski 1-3. ✓

**2. Placeholder scan:** brak TBD/TODO; cały kod podany. Jedyne „sprawdź realną nazwę" dotyczy aliasu `RawResponse` w server.py (Faza 1 użyła `Response as RawResponse`) — wykonawca potwierdza w pliku, to nie placeholder logiki.

**3. Type consistency:** `off` ma kształt `{row,col,colx,rowy}` (po 2) wszędzie: `readOffsets`/`writeOffsets`/`tileOrigin`/`applyDrag`/`editorDrag.off`. `tileOrigin` zwraca `{x,y}`. `special.{pageW,pageH,ready,printUpload,cutUpload}` zgodne z istniejącym `app.js`. Stałe `SPECIAL_PRINT_NAME`/`SPECIAL_CUT_NAME` użyte w `prepare_special_trim` i trasie tile.png — spójnie. `render_special_tile_png(print_pdf_path, cut_pdf_path, max_px)` wołane z `p.path`, `c.path`. ✓

**Ryzyka:**
- Skala mm→px draga: `dataset.scale` ustawiana w `renderSpecialEditor`; `editorPointerMove` używa snapshotu skali z `pointerdown` — stabilne podczas jednego draga. Smoke Playwright (Task 3) potwierdzi, że drag realnie zmienia wartości.
- `<image href>` w SVG (nie `xlink:href`) — wspierane we współczesnych przeglądarkach (Chromium/Firefox); drukpol używany z nowoczesną przeglądarką. Smoke to potwierdzi.
