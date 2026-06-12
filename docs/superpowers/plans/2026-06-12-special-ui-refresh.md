# UI refresh: przełączany panel + jednolity podgląd + ładny wygląd — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Przebudować front (BEZ zmiany mechaniki/silnika/API): podgląd = jeden skalowany obraz z przyciskami Druk/Wykrojnik; prawy panel przełączany [Edytor 3×3 | Podgląd] z edytorem na całą szerokość; spójny, ładny wygląd całej appki.

**Architecture:** Czysto warstwa prezentacji w `web/static/{index.html,app.js,style.css}`. Backend, silnik i wszystkie trasy bez zmian. Edytor 3×3 (logika `tileOrigin/applyDrag/renderSpecialEditor`/pointer/keys) zostaje — przenosimy tylko jego markup z lewej kolumny do prawego panelu i powiększamy; px→mm liczone per oś przez `getBoundingClientRect`, więc większy rozmiar działa bez zmian logiki. Estetykę robi skill frontend-design na końcu (po ustaleniu struktury).

**Tech Stack:** vanilla JS + SVG, czysty CSS (bez frameworka). Testy: pytest (kontrakt id-ów, statyczne) + `node --check` + smoke Playwright (plugin `example-skills:webapp-testing`, playwright już w `.venv`).

---

## File Structure

- **Modify `web/static/index.html`** — sekcja `.preview`: z dwóch `<img>` (Druk+Wykrojnik) na jeden `#preview-img` + przełącznik `[Druk|Wykrojnik]` (Task 1); dodać przełącznik widoku `[Edytor|Podgląd]` i przenieść markup edytora do panelu (Task 2). Klasy-hooki pod styl (Task 3).
- **Modify `web/static/app.js`** — stan `previewWhich` + przełącznik podglądu (Task 1); stan `rightView` + przełącznik widoku + re-wire listenerów przeniesionych pól offsetów (Task 2).
- **Modify `web/static/style.css`** — minimalne style przełączników (Task 1/2), potem pełny refresh (Task 3).
- **Test `tests/test_web_frontend.py`** — kontrakt id-ów nowej struktury (Task 1, Task 2).

---

## Task 1: Jednolity podgląd z przełącznikiem Druk/Wykrojnik

**Files:**
- Modify: `web/static/index.html`
- Modify: `web/static/app.js`
- Modify: `web/static/style.css`
- Test: `tests/test_web_frontend.py`

- [ ] **Step 1: Write failing test**

Dopisz do `tests/test_web_frontend.py`:

```python
def test_preview_is_single_image_with_toggle():
    from pathlib import Path
    html = (Path(__file__).resolve().parents[1] / "web" / "static" / "index.html").read_text(encoding="utf-8")
    assert 'id="preview-img"' in html
    assert 'id="preview-print-btn"' in html and 'id="preview-cut-btn"' in html
    # stare dwa osobne obrazki podglądu znikają
    assert 'id="preview-print"' not in html
    assert 'id="preview-cut"' not in html


def test_app_js_preview_toggle():
    from pathlib import Path
    js = (Path(__file__).resolve().parents[1] / "web" / "static" / "app.js").read_text(encoding="utf-8")
    assert "previewWhich" in js
    assert "preview-img" in js
```

- [ ] **Step 2: Run — verify fail**

Run: `cd ~/summa-cut && .venv/bin/python -m pytest tests/test_web_frontend.py -q -k "single_image or preview_toggle"`
Expected: FAIL.

- [ ] **Step 3: Zmień HTML — sekcja `.preview`**

W `web/static/index.html` zamień blok (linie ~95-106):

```html
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
    </section>
```

na:

```html
    <section class="preview" id="panel">
      <div id="error" class="error" hidden></div>
      <div id="summary" class="summary">Wgraj PDF i ustaw parametry.</div>
      <div id="view-preview">
        <div class="segmented" id="preview-toggle">
          <button type="button" id="preview-print-btn" class="seg-btn active">Druk</button>
          <button type="button" id="preview-cut-btn" class="seg-btn">Wykrojnik</button>
        </div>
        <div class="preview-block">
          <img id="preview-img" alt="podgląd">
        </div>
      </div>
    </section>
```

- [ ] **Step 4: app.js — stan `previewWhich` + przełącznik**

W `web/static/app.js`, w sekcji stanu na górze (np. po `let previewTimer = null;`) dodaj:

```javascript
let previewWhich = "print";   // który obraz pokazuje podgląd: 'print' | 'cut'
```

W `wireEvents()` dodaj (np. po wpięciu generate/upload):

```javascript
  $("preview-print-btn").addEventListener("click", () => setPreviewWhich("print"));
  $("preview-cut-btn").addEventListener("click", () => setPreviewWhich("cut"));
```

Dodaj funkcję (np. obok `updatePreview`):

```javascript
function setPreviewWhich(which) {
  previewWhich = which;
  $("preview-print-btn").classList.toggle("active", which === "print");
  $("preview-cut-btn").classList.toggle("active", which === "cut");
  $("preview-img").src = `/api/preview/${which}.png?t=${Date.now()}`;
}
```

Zmień `updatePreview()` — zamiast ustawiać dwa `<img>`, ustaw jeden wg `previewWhich`:

```javascript
async function updatePreview() {
  const specialReady = $("special-enable").checked && special.ready;
  if (!$("print-file").value && !$("montage-enable").checked && !specialReady) return;
  if (await applyJob()) {
    $("preview-img").src = `/api/preview/${previewWhich}.png?t=${Date.now()}`;
  }
}
```

- [ ] **Step 5: style.css — segment + skalowany obraz**

W `web/static/style.css` dodaj (i usuń regułę `.preview img { ... }` jeśli koliduje — zostaw `.preview-block`):

```css
.segmented { display: inline-flex; border: 1px solid #2f80ed; border-radius: 7px; overflow: hidden; margin-bottom: 10px; }
.seg-btn { border: none; background: #fff; color: #2f80ed; padding: 5px 14px; border-radius: 0; cursor: pointer; font: inherit; }
.seg-btn.active { background: #2f80ed; color: #fff; }
#preview-img { width: 100%; max-height: calc(100vh - 170px); object-fit: contain; display: block; background: #fafafa; min-height: 120px; }
```

- [ ] **Step 6: Run — kontrakt + składnia + pełny zestaw**

Run:
```bash
cd ~/summa-cut && .venv/bin/python -m pytest tests/test_web_frontend.py -q && node --check web/static/app.js && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
```
Expected: PASS, brak regresji.

- [ ] **Step 7: Commit**

```bash
cd ~/summa-cut && git add web/static/index.html web/static/app.js web/static/style.css tests/test_web_frontend.py
git commit -m "feat(ui): jednolity podgląd — jeden skalowany obraz + przełącznik Druk/Wykrojnik"
```

---

## Task 2: Przełączany panel [Edytor 3×3 | Podgląd] + edytor w panelu

**Files:**
- Modify: `web/static/index.html`
- Modify: `web/static/app.js`
- Modify: `web/static/style.css`
- Test: `tests/test_web_frontend.py`

- [ ] **Step 1: Write failing test**

Dopisz do `tests/test_web_frontend.py`:

```python
def test_panel_has_view_switch_and_editor_in_panel():
    from pathlib import Path
    html = (Path(__file__).resolve().parents[1] / "web" / "static" / "index.html").read_text(encoding="utf-8")
    # przełącznik widoku panelu
    assert 'id="view-switch"' in html
    assert 'id="view-editor-btn"' in html and 'id="view-preview-btn"' in html
    # kontener widoku edytora w panelu
    assert 'id="view-editor"' in html
    # edytor (svg) i 8 pól są wewnątrz sekcji panelu (.preview), nie w .controls
    panel = html.split('<section class="preview"', 1)[1]
    assert 'id="special-editor"' in panel
    assert 'id="special-row0"' in panel
    # w lewej kolewce (.controls) zostaje przycisk Przygotuj i checkbox
    controls = html.split('<section class="preview"', 1)[0]
    assert 'id="special-prepare-btn"' in controls
    assert 'id="special-enable"' in controls


def test_app_js_view_switch():
    from pathlib import Path
    js = (Path(__file__).resolve().parents[1] / "web" / "static" / "app.js").read_text(encoding="utf-8")
    assert "rightView" in js and "setRightView" in js
```

- [ ] **Step 2: Run — verify fail**

Run: `cd ~/summa-cut && .venv/bin/python -m pytest tests/test_web_frontend.py -q -k "view_switch or panel_has"`
Expected: FAIL.

- [ ] **Step 3: HTML — usuń edytor z lewej, dodaj do panelu + przełącznik widoku**

(a) W `web/static/index.html`, w `<fieldset class="special">` USUŃ blok edytora i pól (linie ~70-84: `<div class="special-editor-wrap">…</div>` ORAZ `<details class="special-offsets">…</details>`), zostawiając w `#special-body` tylko: `spad`, `#special-prepare-btn`, `#special-status`. Po zmianie `#special-body` wygląda tak:

```html
        <div id="special-body" hidden>
          <label>spad mm <input type="number" id="special-bleed" value="3" step="0.1" min="0"></label>
          <button type="button" id="special-prepare-btn">Przygotuj wykrojnik</button>
          <span id="special-status" class="special-status"></span>
        </div>
```

(b) W sekcji `.preview` (z Tasku 1) dodaj przełącznik widoku NAD `#view-preview` i kontener `#view-editor` z PRZENIESIONYM markupem edytora. Sekcja `.preview` po zmianie:

```html
    <section class="preview" id="panel">
      <div id="error" class="error" hidden></div>
      <div id="summary" class="summary">Wgraj PDF i ustaw parametry.</div>

      <div class="segmented" id="view-switch" hidden>
        <button type="button" id="view-editor-btn" class="seg-btn active">Edytor 3×3</button>
        <button type="button" id="view-preview-btn" class="seg-btn">Podgląd</button>
      </div>

      <div id="view-editor" hidden>
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
      </div>

      <div id="view-preview">
        <div class="segmented" id="preview-toggle">
          <button type="button" id="preview-print-btn" class="seg-btn active">Druk</button>
          <button type="button" id="preview-cut-btn" class="seg-btn">Wykrojnik</button>
        </div>
        <div class="preview-block">
          <img id="preview-img" alt="podgląd">
        </div>
      </div>
    </section>
```

- [ ] **Step 4: app.js — stan `rightView` + przełączanie + re-wire pól**

W sekcji stanu na górze dodaj:

```javascript
let rightView = "preview";    // co pokazuje prawy panel: 'editor' | 'preview' (editor tylko gdy tryb specjalny)
```

Dodaj funkcję (obok `setPreviewWhich`):

```javascript
function setRightView(view) {
  rightView = view;
  const editorOn = view === "editor";
  $("view-editor").hidden = !editorOn;
  $("view-preview").hidden = editorOn;
  $("view-editor-btn").classList.toggle("active", editorOn);
  $("view-preview-btn").classList.toggle("active", !editorOn);
  if (editorOn) renderSpecialEditor();
}
```

W `wireEvents()` dodaj wpięcie przełącznika widoku i re-wire przeniesionych pól offsetów (są teraz POZA `#controls`, więc istniejący listener `#controls input` ich nie złapie):

```javascript
  $("view-editor-btn").addEventListener("click", () => setRightView("editor"));
  $("view-preview-btn").addEventListener("click", () => setRightView("preview"));
  // przeniesione pola „dostrojenie ręczne" są poza #controls — wepnij im odświeżanie
  for (const id of ["special-row0","special-row1","special-col0","special-col1",
                    "special-colx0","special-colx1","special-rowy0","special-rowy1"]) {
    $(id).addEventListener("input", () => { renderSpecialEditor(); schedulePreview(); });
  }
```

Zmień `onSpecialToggle()` — pokaż/ukryj przełącznik widoku i ustaw widok:

```javascript
function onSpecialToggle() {
  const on = $("special-enable").checked;
  $("special-body").hidden = !on;
  $("view-switch").hidden = !on;
  updateGapLock();
  setRightView(on ? "editor" : "preview");
  schedulePreview();
}
```

W `doSpecialPrepare()` — po przygotowaniu pokaż edytor (gdyby user był na „Podgląd"). Zaraz po istniejącym `renderSpecialEditor();` (które dodano w poprzednim etapie po `special.ready = true;`) dodaj:

```javascript
  setRightView("editor");
```

- [ ] **Step 5: style.css — większy edytor w panelu**

Zmień regułę `#special-editor` (z Tasku edytora) na większą i usuń `max-width` z legendy:

```css
#special-editor { width: 100%; height: min(70vh, 620px); background:
  repeating-conic-gradient(#f2f2f2 0% 25%, #e7e7e7 0% 50%) 0 / 18px 18px;
  border: 1px solid #ccc; border-radius: 8px; touch-action: none; outline: none; }
.special-legend { font-size: 13px; color: #666; margin: 6px 0 0; }
```

(Usuń poprzednie `#special-editor { … max-width: 340px; height: 260px; … }` i `max-width: 340px` z `.special-legend`.)

- [ ] **Step 6: Run — kontrakt + składnia + pełny zestaw**

Run:
```bash
cd ~/summa-cut && .venv/bin/python -m pytest tests/test_web_frontend.py -q && node --check web/static/app.js && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
```
Expected: PASS, brak regresji.

- [ ] **Step 7: Commit**

```bash
cd ~/summa-cut && git add web/static/index.html web/static/app.js web/static/style.css tests/test_web_frontend.py
git commit -m "feat(ui): przełączany panel [Edytor 3×3|Podgląd], edytor na całą szerokość panelu"
```

---

## Task 3: Pełny refresh wyglądu (skill frontend-design)

**Files:**
- Modify: `web/static/style.css` (głównie), `web/static/index.html` (drobne klasy-hooki, BEZ zmiany id i struktury logicznej)
- Test: `tests/test_web_frontend.py` (regresja — wszystkie dotychczasowe kontrakty id-ów muszą dalej przechodzić)

- [ ] **Step 1: Użyj skilla `frontend-design`**

Wywołaj skill **frontend-design** i zaprojektuj spójny, profesjonalny wygląd całej appki (narzędzie warsztatowe LAN, bez logowania). Zakres i twarde ograniczenia:

- **NIE zmieniaj** żadnych `id`, nazw kontrolek, struktury logicznej ani JS. Wolno dodać klasy CSS i opakowujące `<div>` czysto pod styl, o ile testy kontraktu id-ów dalej przechodzą.
- **Elementy do ostylowania spójnie:** nagłówek (`header`), dwukolumnowy layout (`main` grid: kontrolki + panel; responsywnie zwijany na wąskim ekranie), sekcje kontrolek (`.controls fieldset` jako karty), pola/inputy/selecty, przyciski (warianty: primary = `#generate-btn` zielony „Generuj", secondary = zwykłe, akcent), **segmentowane przełączniki** (`.segmented`/`.seg-btn`/`.seg-btn.active` — Druk/Wykrojnik i Edytor/Podgląd), `#summary` i `.error`, edytor (`#special-editor` tło/ramka), legenda, `<details>` „Dostrojenie ręczne", lista uploadów, wiersze montażu.
- **Stany:** hover, focus-visible (czytelny pierścień focusu — WAŻNE, bo `#special-editor` jest sterowany klawiaturą), disabled (np. `#gap-off` blokowany).
- **Estetyka:** czysta, nowoczesna, dobry kontrast, spójna paleta i skala typografii; bez krzykliwości. Bez frameworka CSS — czysty CSS w `web/static/style.css`.
- Zachowaj istniejące zachowanie skalowania `#preview-img` (object-fit: contain, ograniczenie wysokości) i `#special-editor` (`touch-action: none`).

- [ ] **Step 2: Regresja kontraktu + składnia**

Run:
```bash
cd ~/summa-cut && .venv/bin/python -m pytest tests/test_web_frontend.py -q && node --check web/static/app.js && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
```
Expected: PASS (wszystkie kontrakty id-ów + całość 78+ testów). Jeśli refresh złamał któryś kontrakt id-ów — popraw markup tak, by id/struktura zostały, a styl był w CSS.

- [ ] **Step 3: Commit**

```bash
cd ~/summa-cut && git add web/static/style.css web/static/index.html
git commit -m "style(ui): spójny refresh wyglądu całej appki (frontend-design)"
```

---

## Task 4: Smoke E2E (Playwright) — przełączniki + drag w większym edytorze

**Files:** brak commitowanego kodu (weryfikacja). Plugin `example-skills:webapp-testing`, playwright w `.venv`.

- [ ] **Step 1: Serwer testowy + wsad**

```bash
cd ~/summa-cut && .venv/bin/python -m uvicorn web.app:app --port 8014 --log-level warning &
# źródło z wektorowym obrysem:
QT_QPA_PLATFORM=offscreen .venv/bin/python - <<'PY'
import fitz
doc=fitz.open(); p=doc.new_page(width=120,height=100)
p.draw_rect(fitz.Rect(20,20,70,50),color=(0,0,0),fill=(0.6,0.6,0.6),width=0)
p.draw_rect(fitz.Rect(20,20,70,50),color=(1,0,0),width=0.5)
doc.save("/tmp/sc_ui_src.pdf"); doc.close()
PY
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8014/
```

- [ ] **Step 2: Skrypt Playwright**

Napisz `/tmp/sc_ui_smoke.py` (headless chromium) i sprawdź:
1. Wejście na `http://127.0.0.1:8014/`, `networkidle`.
2. Upload `/tmp/sc_ui_src.pdf` (`#upload-input` + `#upload-btn`); wybór w `#print-file`/`#cut-file` = `sc_ui_src.pdf`.
3. **Podgląd, tryb zwykły:** klik `#preview-cut-btn` → `#preview-img` `src` zawiera `cut.png`; klik `#preview-print-btn` → `print.png`. (Po `applyJob` obraz się ładuje; sprawdź atrybut `src`.)
4. **Tryb specjalny:** zaznacz `#special-enable` → `#view-switch` widoczny (nie `hidden`) i panel pokazuje edytor (`#view-editor` nie `hidden`, `#view-preview` hidden).
5. Klik `#special-prepare-btn`, czekaj na „Gotowe" w `#special-status`; `#special-editor` ma 9 `image` i 9 `rect.tile`.
6. **Drag w większym edytorze:** pointerdown→move(+60,+40)→up na środkowym kaflu (`rect.tile[data-row="1"][data-col="1"]`); `#special-row1`≠0 i `#special-col1`≠0 (potwierdza poprawne px→mm przy nowym rozmiarze).
7. Klik `#view-preview-btn` → `#view-preview` widoczny, `#view-editor` hidden; klik `#view-editor-btn` → odwrotnie.
8. Zrzut ekranu `/tmp/sc_ui.png` (full_page) do oceny wyglądu.
Asercje twarde — jeśli któraś padnie, napraw w `app.js`/markup i powtórz.

- [ ] **Step 3: Uruchom + obejrzyj zrzut**

```bash
cd ~/summa-cut && .venv/bin/python /tmp/sc_ui_smoke.py
```
Obejrzyj `/tmp/sc_ui.png` (Read). Ubij serwer (`pkill -f "uvicorn web.app:app --port 8014"`).

---

## Task 5: Deploy na drukpolu + smoke + pamięć

**Files:** ew. `project_summacut.md` (pamięć). Bez nowych zależności runtime.

- [ ] **Step 1: Rsync + rebuild**

```bash
rsync -az --delete --exclude .venv --exclude .git --exclude __pycache__ --exclude .superpowers ~/summa-cut/ root@REDACTED-HOST:/srv/app/ \
&& ssh root@REDACTED-HOST 'cd /srv/app && docker compose up -d --build'
```

- [ ] **Step 2: Smoke na żywym drukpolu**

```bash
BASE=http://REDACTED-HOST:8800
curl -s $BASE/ | grep -o 'id="view-switch"' | head -1
curl -s $BASE/ | grep -o 'id="preview-img"' | head -1
curl -s -o /dev/null -w "GET / %{http_code}\n" $BASE/
```
Expected: `id="view-switch"`, `id="preview-img"`, `GET / 200`.

- [ ] **Step 3: Wzrokowa ocena usera**

User otwiera http://REDACTED-LAN:8800: ogląda nowy wygląd, przełącza Druk/Wykrojnik i Edytor/Podgląd, sprawdza większy edytor 3×3. Potwierdza, że jest ładnie i wygodnie.

- [ ] **Step 4: Pamięć**

Dopisz w `project_summacut.md`: refresh UI wdrożony (przełączany panel, jednolity podgląd, większy edytor, frontend-design), tag np. `ui-refresh`, liczba testów.

---

## Self-Review

**1. Spec coverage:**
- Podgląd = jeden skalowany obraz + Druk/Wykrojnik → Task 1. ✓
- Wariant B: prawy panel przełączany [Edytor|Podgląd], widoczny tylko w trybie specjalnym, domyślnie Edytor → Task 2 (`setRightView`, `onSpecialToggle`, `#view-switch hidden`). ✓
- Edytor + „Dostrojenie ręczne" przeniesione do panelu, większe → Task 2 (HTML move + CSS) + re-wire pól. ✓
- Pełny refresh wyglądu (frontend-design) → Task 3. ✓
- Brak zmian backend/silnik/API → żaden task ich nie dotyka. ✓
- Testy pytest (kontrakt) + Playwright → Taski 1-4. ✓

**2. Placeholder scan:** brak TBD/TODO; kod kompletny dla Tasków 1-2. Task 3 to świadomie „guidance + twarde ograniczenia + regresja" (estetyka nie jest TDD-owalna kodem) — to nie placeholder, lecz właściwa altitude dla pracy frontend-design. Task 4 to skrypt opisany krok-po-kroku (Playwright generowany przy wykonaniu, jak w poprzednim etapie).

**3. Type/identyfikatory consistency:** nowe id użyte spójnie: `preview-img`, `preview-print-btn`, `preview-cut-btn`, `view-switch`, `view-editor`, `view-editor-btn`, `view-preview`, `view-preview-btn`. Funkcje: `setPreviewWhich`, `setRightView`. Stan: `previewWhich`, `rightView`. Przeniesione id edytora (`special-editor`, `special-row0..rowy1`, `special-legend`) bez zmian → `renderSpecialEditor`/`readOffsets`/`writeOffsets`/`collectParams`/`specialOffsets` działają bez zmian (czytają po id). `updatePreview` ustawia `#preview-img` wg `previewWhich`. ✓

**Ryzyka:**
- Przeniesienie 8 pól poza `#controls` rozłącza istniejący listener `#controls input` → Task 2 jawnie dodaje listenery na te pola (renderSpecialEditor + schedulePreview). Pilnuje tego smoke Playwright (drag + edycja).
- `setRightView` woła `renderSpecialEditor` po pokazaniu edytora — ważne, bo render liczy skalę z `getBoundingClientRect`, a element musi być widoczny (nie `hidden`) by mieć wymiary. Kolejność w `setRightView`: najpierw `hidden=false`, potem `renderSpecialEditor()` — OK.
- Po Tasku 1 (zanim Task 2 doda `#view-editor`) edytor zostaje chwilowo w lewej kolumnie — appka działa; Task 2 go przenosi. Każdy task zostawia działający front.
