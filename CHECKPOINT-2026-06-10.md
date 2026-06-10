# Checkpoint 2026-06-10 — przejęcie + szybki podgląd (v1.1)

Bezpieczny punkt powrotu kodu `summa-cut` po przejęciu projektu od OpenClaw
i przebudowie wydajności podglądu.

## Co zawiera ten stan
- **Samodzielne repo** `~/summa-cut` (wyciągnięte z workspace OpenClaw „Bocik").
- **Montaż wielu użytków** (`montage_items` + `quantity`) — wcześniej niezacommitowany, tu zachowany.
- **Wydajność podglądu przebudowana** (commit `a161074`):
  - `export._SourceCache` — plik źródłowy otwierany raz na eksport,
  - podgląd = **raster kafelkowy** (`preview.render_source_tile` + `render_layout_preview(tiles=)`),
    NIE buduje już pełnego PDF przy każdej zmianie,
  - pełny `generate_output_docs` przeniesiony do zapisu (`_save_both_pdfs`).
  - Pomiar: podgląd 560 użytków `~47 s → ~30 ms`.
- **10 testów** headless (`tests/test_export.py`, `tests/test_layout.py`):
  `QT_QPA_PLATFORM=offscreen python -m pytest tests/ -q` → 10 passed.
- Launchery `.desktop` (Desktop + Pulpit) wskazują `~/summa-cut`.

## Powrót do tego stanu
```bash
cd ~/summa-cut
git checkout v1.1            # ten checkpoint (odłączony HEAD — tylko podgląd/odtworzenie)
# lub twardy powrót gałęzi master:
git reset --hard v1.1
```

## Znane, jeszcze nieruszone
- **Zapis** dalej buduje PDF przez `show_pdf_page` → przy ~560 użytkach ~47 s (raz,
  z kursorem oczekiwania). Kandydat na optymalizację: `pikepdf` (add_overlay ×560 ≈ 85 ms).
- Drobne: gapless +1 mm overshoot bez marginesu; tooltip split „lewa/prawa" vs kod „góra/dół";
  martwy kod w trybie specjalnym.
