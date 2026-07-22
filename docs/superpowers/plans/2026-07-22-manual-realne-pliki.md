# Etap A — realne pliki na kanwie montażu — plan implementacji

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Pokazać na kanwie montażu wierny podgląd każdego użytku (strona druku + wykrojnik na wierzchu, kadr W×H) zamiast szarego prostokąta — bez zmiany wyjściowego PDF-a.

**Architecture:** Nowa funkcja renderująca PNG kafla (kadr jak w eksporcie) + endpoint `GET /api/manual/tile.png`. Frontend wstawia `<image>` (href = endpoint) pod obwódką każdego placementu; prostokąt staje się przezroczysty (widać grafikę, dalej łapie drag). Kafelki są tylko do podglądu — ścieżka eksportu (wektorowa) nietknięta.

**Tech Stack:** FastAPI, PyMuPDF (fitz), pytest, Playwright. Testy: `.venv/bin/python -m pytest`. Deploy: rsync → `docker build` → `midclt call app.redeploy summa-cut` na drukpolu (`root@100.109.91.116`).

**Referencje:** spec `docs/superpowers/specs/2026-07-22-manual-realne-pliki-design.md`; `summa_cut/export.py` (`_centered_clip_rect_pt`, `_render_cell_stamp`), `web/preview_render.py` (`render_special_tile_png`), `web/server.py` (endpointy + `current_session`, `RawResponse`), `web/static/app.js` (`renderCanvas`, linie 552-565).

---

## Struktura plików

- `web/preview_render.py` — Create fn `render_manual_tile_png`.
- `web/server.py` — Add endpoint `GET /api/manual/tile.png`.
- `tests/test_web_api.py` — Add endpoint tests (ma już helper `_two_page_pdf_bytes` i klienta).
- `tests/test_web_preview.py` — Add test funkcji renderującej.
- `web/static/app.js` — Modify `renderCanvas` (dodaj `<image>` przed `rect`).
- `web/static/style.css` — Modify `.mc-item` fill → transparent.
- `web/static/index.html` — bump `?v=5`.

---

## Task 1: Backend — render kafla + endpoint

**Files:**
- Modify: `web/preview_render.py` (nowa fn), `web/server.py` (endpoint)
- Test: `tests/test_web_preview.py`, `tests/test_web_api.py`

- [ ] **Step 1: Testy funkcji renderującej — dopisz na końcu `tests/test_web_preview.py`:**

```python
def _two_page_para(tmp_path, w_mm=40.0, h_mm=30.0):
    doc = fitz.open()
    doc.new_page(width=w_mm * PT, height=h_mm * PT).draw_rect(
        fitz.Rect(2 * PT, 2 * PT, (w_mm - 2) * PT, (h_mm - 2) * PT), color=(0, 0, 1))
    doc.new_page(width=w_mm * PT, height=h_mm * PT).draw_rect(
        fitz.Rect(1 * PT, 1 * PT, (w_mm - 1) * PT, (h_mm - 1) * PT), color=(1, 0, 0))
    path = tmp_path / "para.pdf"
    doc.save(path); doc.close()
    return str(path)


def test_render_manual_tile_png_returns_png_with_aspect(tmp_path):
    from web.preview_render import render_manual_tile_png
    path = _two_page_para(tmp_path)  # 40x30
    bbox0 = (0.0, 0.0, 40 * PT, 30 * PT)
    bbox1 = (0.0, 0.0, 40 * PT, 30 * PT)
    png = render_manual_tile_png(path, 0, bbox0, path, 1, bbox1, 40.0, 30.0, 0, max_px=200)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    import io
    pix = fitz.Pixmap(io.BytesIO(png))
    # proporcja 40:30 → szer > wys, przy max_px=200 szerszy bok = 200
    assert pix.width == 200 and 140 <= pix.height <= 160
```

- [ ] **Step 2: Uruchom — ma FAIL (brak funkcji).**
Run: `.venv/bin/python -m pytest tests/test_web_preview.py::test_render_manual_tile_png_returns_png_with_aspect -v`
Expected: FAIL (ImportError / brak `render_manual_tile_png`).

- [ ] **Step 3: Dodaj funkcję w `web/preview_render.py`** (na końcu pliku):

```python
def render_manual_tile_png(
    print_path: str, print_page: int, print_bbox_pt,
    cut_path: str, cut_page: int, cut_bbox_pt,
    width_mm: float, height_mm: float, rotation_deg: int = 0,
    max_px: int = PREVIEW_MAX_PX,
) -> bytes:
    """Wierny kafel kanwy: kadr W×H strony druku + wykrojnik na wierzchu → PNG.

    Kadr identyczny jak w eksporcie (`_render_cell_stamp` / `_centered_clip_rect_pt`),
    więc podgląd = to, co trafi na arkusz. Tylko do wyświetlania — nie dotyka wyjścia."""
    from summa_cut.export import _centered_clip_rect_pt, mm_to_pt
    cell_w_pt = mm_to_pt(width_mm)
    cell_h_pt = mm_to_pt(height_mm)
    with fitz.open(print_path) as pdoc, fitz.open(cut_path) as cdoc:
        p_clip = _centered_clip_rect_pt(pdoc[print_page].rect, tuple(print_bbox_pt), width_mm, height_mm, rotation_deg)
        c_clip = _centered_clip_rect_pt(cdoc[cut_page].rect, tuple(cut_bbox_pt), width_mm, height_mm, rotation_deg)
        out = fitz.open()
        try:
            page = out.new_page(width=cell_w_pt, height=cell_h_pt)
            page.show_pdf_page(page.rect, pdoc, print_page, rotate=rotation_deg, clip=p_clip)
            page.show_pdf_page(page.rect, cdoc, cut_page, rotate=rotation_deg, clip=c_clip)
            scale = max_px / max(cell_w_pt, cell_h_pt, 1.0)
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            return pix.tobytes("png")
        finally:
            out.close()
```

Uwaga: sprawdź, czy `mm_to_pt` jest w `summa_cut.pdf_io` (grep). Jeśli mieszka w innym module, użyj właściwego importu (ten sam, którego używa `summa_cut/export.py`).

- [ ] **Step 4: Uruchom test — PASS.**
Run: `.venv/bin/python -m pytest tests/test_web_preview.py -v`
Expected: PASS.

- [ ] **Step 5: Testy endpointu — dopisz na końcu `tests/test_web_api.py`** (plik ma `_two_page_pdf_bytes()` i klienta `TestClient`; podejrzyj istniejące testy manualne ~linia 300, żeby użyć tego samego wzorca `c = TestClient(...)`, `POST /api/session`, `POST /api/upload`):

```python
def test_manual_tile_endpoint_returns_png(tmp_path):
    c = TestClient(create_app(store=SessionStore(base_dir=tmp_path)))
    c.post("/api/session")
    c.post("/api/upload", files={"file": ("para.pdf", _two_page_pdf_bytes(), "application/pdf")})
    r = c.get("/api/manual/tile.png", params={"upload": "para.pdf", "w": 40, "h": 30, "rot": 0})
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_manual_tile_endpoint_errors(tmp_path):
    c = TestClient(create_app(store=SessionStore(base_dir=tmp_path)))
    c.post("/api/session")
    c.post("/api/upload", files={"file": ("para.pdf", _two_page_pdf_bytes(), "application/pdf")})
    assert c.get("/api/manual/tile.png", params={"upload": "brak.pdf", "w": 40, "h": 30}).status_code == 404
    assert c.get("/api/manual/tile.png", params={"upload": "para.pdf", "w": 0, "h": 30}).status_code == 400
```

Sprawdź nagłówki importów w `test_web_api.py` — jeśli `create_app`, `SessionStore`, `TestClient` nie są zaimportowane na górze, dodaj importy jak w istniejących testach tego pliku.

- [ ] **Step 6: Uruchom — FAIL (brak endpointu).**
Run: `.venv/bin/python -m pytest tests/test_web_api.py::test_manual_tile_endpoint_returns_png -v`
Expected: FAIL (404 — brak trasy).

- [ ] **Step 7: Dodaj endpoint w `web/server.py`.** Zaimportuj `render_manual_tile_png` (dopisz do istniejącego importu z `web.preview_render`). Dodaj trasę obok `special_tile` (po `/api/special/tile.png`):

```python
    @app.get("/api/manual/tile.png")
    def manual_tile(upload: str, w: float, h: float, rot: int = 0,
                    session: Session = Depends(current_session)) -> RawResponse:
        info = session.uploads.get(upload)
        if info is None:
            raise HTTPException(status_code=404, detail="Nieznany plik.")
        if len(info.page_content_boxes_pt) < 2:
            raise HTTPException(status_code=400, detail="Plik musi mieć 2 strony: druk + wykrojnik.")
        if w <= 0 or h <= 0:
            raise HTTPException(status_code=400, detail="Wymiar musi być większy od zera.")
        png = render_manual_tile_png(
            info.path, 0, info.page_content_boxes_pt[0],
            info.path, 1, info.page_content_boxes_pt[1],
            w, h, rot,
        )
        return RawResponse(content=png, media_type="image/png")
```

Sprawdź nazwę klasy odpowiedzi (`RawResponse`) i zależność `current_session` — użyj tych samych, co sąsiednie endpointy (`special_tile`, `preview`).

- [ ] **Step 8: Uruchom testy endpointu + całość — PASS, brak regresji.**
Run: `.venv/bin/python -m pytest tests/test_web_api.py tests/test_web_preview.py -v`
Expected: PASS. Potem `.venv/bin/python -m pytest -q` → wszystko zielone.

- [ ] **Step 9: Commit**
```bash
git add web/preview_render.py web/server.py tests/test_web_api.py tests/test_web_preview.py
git commit -m "feat(manual): endpoint /api/manual/tile.png — wierny kafel (druk+wykrojnik)"
```

---

## Task 2: Frontend — obraz pod obwódką na kanwie

**Files:**
- Modify: `web/static/app.js` (`renderCanvas`, pętla placementów ~552-565)
- Modify: `web/static/style.css` (`.mc-item`)
- Modify: `web/static/index.html` (bump `?v=5`)

- [ ] **Step 1: W `renderCanvas`, w pętli `manualState.placements.forEach`, dodaj `<image>` PRZED prostokątem.** Zamień ciało pętli (od `const bad = ...` do `add("text", ...)`) na:

```javascript
  manualState.placements.forEach((p, i) => {
    const bad = mcRectBad(p, manualState.placements, wa);
    const name = manualState.items[p.itemIndex] ? manualState.items[p.itemIndex].upload : "";
    if (name) {
      const href = `/api/manual/tile.png?upload=${encodeURIComponent(name)}&w=${p.wMm}&h=${p.hMm}&rot=${p.rot}`;
      add("image", {
        href,
        x: p.xMm * MC_SCALE, y: p.yMm * MC_SCALE,
        width: p.wMm * MC_SCALE, height: p.hMm * MC_SCALE,
        preserveAspectRatio: "none",
        "pointer-events": "none",
      });
    }
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
```

- [ ] **Step 2: CSS — prostokąt przezroczysty (widać grafikę, dalej łapie drag).** W `web/static/style.css` zamień regułę `.mc-item`:
```css
.mc-item { fill: transparent; stroke: #285ac8; stroke-width: 1; cursor: move; }
```
(`.mc-item.sel` i `.mc-item.bad` zostają bez zmian — `bad` dalej ma czerwony półprzezroczysty fill jako sygnał nachodzenia nad grafiką.)

- [ ] **Step 3: Bump wersji.** W `web/static/index.html` zamień `?v=4` → `?v=5` (oba wystąpienia).

- [ ] **Step 4: Weryfikacja składni.**
Run: `node --check web/static/app.js`
Expected: OK.

- [ ] **Step 5: Commit**
```bash
git add web/static/app.js web/static/style.css web/static/index.html
git commit -m "feat(manual): realne pliki na kanwie (obraz kafla pod przezroczystą obwódką)"
```

---

## Task 3: Weryfikacja E2E + deploy

- [ ] **Step 1: Pełne testy.** `.venv/bin/python -m pytest -q` → wszystko zielone.
- [ ] **Step 2: Apka lokalnie.** `.venv/bin/uvicorn web.app:app --host 127.0.0.1 --port 8899 --log-level warning` (w tle); czekaj na 200 na `/static/index.html`.
- [ ] **Step 3: Playwright (viewport 1200×850):** włącz `#manual-free`; upload 2-str. PDF; „Dodaj na arkusz". Asercje (`ALL PASS`):
  - w `#manual-canvas` jest `image` z `href` zawierającym `/api/manual/tile.png` i `upload=`;
  - obraz się ładuje: `naturalWidth>0` (poczekaj na `load`);
  - `.mc-item` istnieje nad obrazem; drag zmienia `x`;
  - zmiana `.pal-w` na 20 zmienia `w=20` w `href` obrazu.
- [ ] **Step 4: Zatrzymaj apkę.** `pkill -f "uvicorn web.app:app"`.
- [ ] **Step 5: Deploy.**
```bash
rsync -az --delete --exclude .venv --exclude .git --exclude __pycache__ --exclude '*.pyc' --exclude .superpowers --exclude .claude ~/summa-cut/ root@100.109.91.116:/mnt/data/apps/summa-cut/
ssh root@100.109.91.116 'docker build -q -t summa-cut-web:local /mnt/data/apps/summa-cut && midclt call app.redeploy summa-cut'
```
- [ ] **Step 6: Weryfikacja live.** Czekaj aż `app.js?v=5`; powtórz Playwright z `BASE=https://summa.cyplos.pl` → `ALL PASS`.
- [ ] **Step 7: Dual-push.** `git push dom master`.
- [ ] **Step 8: Pamięć.** Dopisz do `project_summacut.md`: `?v=5`, nowy HEAD, funkcja (realne pliki na kanwie, endpoint `/api/manual/tile.png`, wyjście nietknięte).

---

## Self-review

- **Pokrycie spec:** D1 (wierny kadr) → Task 1 Step 3 (`_centered_clip_rect_pt`) + href z `w/h/rot`; D2 (tylko podgląd, wyjście nietknięte) → brak zmian w `export.py`, kafel tylko na kanwie (Task 2). Backend render+endpoint → Task 1. Front obraz+obwódka → Task 2. Testy → Task 1 (pytest), Task 3 (Playwright).
- **Placeholdery:** brak — kod/komendy konkretne.
- **Spójność:** `render_manual_tile_png` sygnatura identyczna w preview_render, teście i endpoint­cie; href params `upload,w,h,rot` zgodne z sygnaturą endpointu.
