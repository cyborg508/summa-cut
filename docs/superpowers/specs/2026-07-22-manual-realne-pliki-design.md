# Etap A — realne pliki na kanwie montażu (tryb manualny)

Data: 2026-07-22
Status: zatwierdzony projekt (do implementacji)

## Kontekst

Tryb manualny pokazuje użytki jako szare prostokąty. Użytkownik chce montować,
widząc **realny plik** — stronę druku z wykrojnikiem nałożonym na wierzchu.

To Etap A z podziału (A → B). Etap B (podtryb „wykrojnik": montaż elementów
wyciętych konturem) powstanie później i będzie bazował na renderowaniu z Etapu A.

## Decyzje (potwierdzone z użytkownikiem)

- **D1 — Wierny kadr.** Kafelek pokazuje dokładnie to, co się wydrukuje:
  wyśrodkowany na treści kadr `W×H` (footprint placementu), z obrotem. Zmiana
  wymiaru/obrotu → nowy kadr.
- **D2 — Tylko podgląd.** Kafelki PNG są WYŁĄCZNIE do wyświetlania na kanwie.
  **Nie zmieniają wyjściowego PDF-a.** Gwarancja fidelity (zweryfikowana w kodzie):
  eksport (`summa_cut/export.py`) osadza użytki przez `show_pdf_page` (Form XObject,
  wektor) + `pikepdf add_overlay`; **druk** zapisywany wprost (`print_doc.save`, bez
  Ghostscripta), **wykrojnik** przez `flatten_pdf_bytes` (Ghostscript pdfwrite, dalej
  wektor). Rasteryzacja jest tylko w podglądzie ekranowym. Etap A nie dotyka tej ścieżki.

## Architektura

### Backend — render wiernego kafelka

`web/preview_render.py`, nowa funkcja:

```python
def render_manual_tile_png(
    print_path, print_page, print_bbox_pt,
    cut_path, cut_page, cut_bbox_pt,
    width_mm, height_mm, rotation_deg=0, max_px=PREVIEW_MAX_PX,
) -> bytes
```

- Buduje stronę o rozmiarze kafla (`width_mm × height_mm` w pt), `show_pdf_page`
  druku z kadrem `_centered_clip_rect_pt(src_rect, print_bbox_pt, width_mm, height_mm, rotation_deg)`
  i obrotem `rotation_deg`, potem wykrojnika (analogiczny kadr na `cut_bbox_pt`) **na
  wierzchu**, rasteryzuje `get_pixmap` → PNG. Logika kadru = 1:1 jak `_render_cell_stamp`
  w eksporcie, więc podgląd odpowiada wyjściu.
- Import `_centered_clip_rect_pt`, `mm_to_pt` z `summa_cut.export` / `summa_cut.pdf_io`.

`web/server.py`, nowy endpoint:

```python
@app.get("/api/manual/tile.png")
def manual_tile(upload: str, w: float, h: float, rot: int = 0,
                session: Session = Depends(current_session)) -> RawResponse
```

- `info = session.uploads.get(upload)`; brak → 404. `len(info.page_content_boxes_pt) < 2`
  → 400 („Plik musi mieć 2 strony: druk + wykrojnik."). `w <= 0 or h <= 0` → 400.
- Paleta = 2-str. PDF: str.0 = druk, str.1 = wykrojnik (ten sam plik).
  Woła `render_manual_tile_png(info.path, 0, info.page_content_boxes_pt[0],
  info.path, 1, info.page_content_boxes_pt[1], w, h, rot)`; zwraca `RawResponse(png, "image/png")`.
- URL deterministyczny po `(upload,w,h,rot)` → cache przeglądarki.

### Frontend — warstwa obrazu pod obwódką (`renderCanvas` w `web/static/app.js`)

Dla każdego placementu, PRZED prostokątem, dodać `<image>`:
- `href = /api/manual/tile.png?upload=<enc(name)>&w=<p.wMm>&h=<p.hMm>&rot=<p.rot>`,
  gdzie `name = manualState.items[p.itemIndex].upload`.
- `x=p.xMm*MC_SCALE, y=p.yMm*MC_SCALE, width=p.wMm*MC_SCALE, height=p.hMm*MC_SCALE`,
  `preserveAspectRatio="none"` (proporcja kafla = proporcja footprintu), atrybut
  `pointer-events="none"` (żeby drag łapał prostokąt).
- `p.wMm/p.hMm/p.rot` to wartości placementu (już zamienione przy obrocie), więc URL
  odpowiada dokładnie komórce eksportu.

Prostokąt `.mc-item` rysowany NAD obrazem: obwódka + zaznaczenie jak dziś, ale
`fill: transparent` (widać grafikę, a interior nadal łapie pointer — `visiblePainted`
liczy `transparent` jako pomalowane). Nachodzenie/poza-OPOS: `.mc-item.bad` zostaje
czerwony półprzezroczysty (sygnał błędu na grafice).

CSS (`web/static/style.css`): `.mc-item { fill: transparent; ... }` (zamiast
`rgba(40,90,200,0.12)`); `.mc-item.bad` bez zmian.

### Cache / re-render

- Drag: zmienia się tylko pozycja (`x/y`); `w/h/rot` bez zmian → URL ten sam → obraz
  z cache, bez pobierania.
- Zmiana wymiaru/obrót: URL się zmienia → nowy kadr (zgodnie z D1).

## Testy

- **Backend (pytest, `tests/test_web_preview.py` lub `test_web_api.py`):**
  - `render_manual_tile_png` na 2-str. PDF (np. 40×30) zwraca niepusty PNG; nagłówek
    PNG (`b"\x89PNG"`); rozmiar pixmapy zachowuje proporcję `w:h`.
  - `GET /api/manual/tile.png?upload=para.pdf&w=40&h=30&rot=0` → 200, `content-type
    image/png`, body zaczyna się od sygnatury PNG.
  - błędy: nieznany `upload` → 404; `w=0` → 400; plik 1-stronicowy → 400.
- **Front (Playwright na realnej apce):**
  - po włączeniu trybu + upload + „Dodaj na arkusz": w `#manual-canvas` jest `<image>`
    z `href` zawierającym `/api/manual/tile.png`; `naturalWidth>0` po załadowaniu.
  - obwódka `.mc-item` istnieje nad obrazem; drag dalej zmienia `x`.
  - zmiana `.pal-w` zmienia parametr `w=` w `href` obrazu.

## Poza zakresem (YAGNI)

- Podtryb „wykrojnik" (Etap B).
- Jakakolwiek zmiana ścieżki eksportu / wyjściowego PDF (D2 — wyjście nietknięte).
- Optymalizacja migotania obrazu przy przebudowie SVG w trakcie drag (jeśli wystąpi —
  osobno; cache URL powinien wystarczyć).

## Wdrożenie

rsync → `docker build -t summa-cut-web:local` → `midclt call app.redeploy summa-cut`;
bump `?v=5`; commit + dual-push (dom + GitHub); notka do pamięci.
