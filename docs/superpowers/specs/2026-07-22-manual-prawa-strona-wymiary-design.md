# Tryb manualny: przestrzeń robocza na prawej stronie + wymiar per plik

Data: 2026-07-22
Status: zatwierdzony projekt (do implementacji)

## Kontekst i problem

Tryb manualny (ręczna impozycja par druk/wykrojnik) działa, ale:

1. **Kanwa jest w wąskiej lewej kolumnie** (~350px), przez co arkusz jest mały,
   a wcześniej użytki lądowały poza widocznym oknem (naprawione osobno, ale
   przestrzeń dalej ciasna). Montaż powinien odbywać się w szerokim panelu.
2. **Nie da się nadać własnego wymiaru użytkowi.** Footprint bierze się wyłącznie
   z natywnego rozmiaru strony PDF. Użytkownik potrzebuje wpisać wymiar ręcznie
   (np. gdy strona PDF ma zły rozmiar / za dużo tła).

## Cel

- Przenieść całą przestrzeń roboczą trybu manualnego (paleta + kanwa) do
  **prawego, szerokiego panelu**. Lewa kolumna zostaje na parametry.
- W palecie: obok nazwy każdego pliku **pola wymiaru szer./wys. (mm)** do wpisania,
  domyślnie podpowiedziane z rozmiaru strony PDF.

## Decyzje projektowe (potwierdzone z użytkownikiem)

- **D1 — Zmiana wymiaru pliku przeskalowuje WSZYSTKIE ułożone kopie** tego pliku
  (zachowany róg lewy-górny; obrót 90°/270° zamienia W↔H). Wymiar = cecha pliku.
- **D2 — Prawa strona w trybie manualnym = tylko przestrzeń montażu.** Podgląd
  wyrenderowanego PDF (obecny „Podgląd"/„Edytor 3×3") jest ukryty w trybie
  manualnym; efekt końcowy widać po „Generuj i zapisz PDF-y".
- **D3 — Wymiar KADRUJE bez skalowania.** Wpisany W×H to wyśrodkowane (na treści)
  okno kadrujące ze źródła, grafika 1:1. To dokładnie istniejąca ścieżka
  `use_full_page=False` w eksporcie — wymiar zastępuje jedynie footprint użytku.
- **D4 — Paleta i kanwa razem po prawej.** Lewa kolumna: Pliki PDF (upload),
  Arkusz, Tryb (z przełącznikiem trybu manualnego), OPOS.

## Architektura zmian

### Frontend — układ (index.html + app.js + style.css)

- Nowy kontener przestrzeni manualnej w prawym panelu `.preview`, np.
  `#manual-stage`, zawierający: podpowiedź, **paletę** (wiersze plików z polami
  wymiaru), licznik „Użytków: N", oraz kanwę `#manual-canvas`.
- W `onManualToggle`:
  - manual ON: pokaż `#manual-stage`, ukryj w prawym panelu `#view-switch`,
    `#view-editor`, `#view-preview`; w lewej kolumnie ukryj auto-layoutowe
    fieldsety jak dziś, a fieldset „Tryb manualny" nie zawiera już kanwy/palety
    (przenosi się do prawej) — zostaje pusty/usunięty z lewej.
  - manual OFF: przywróć dzisiejszy stan prawego panelu, ukryj `#manual-stage`.
- Kanwa zachowuje responsywny `viewBox` (skaluje się do szerokości prawej
  kolumny). Drag liczy px/mm z `getBoundingClientRect` (już wdrożone) → działa
  przy każdej szerokości.

### Frontend — paleta z wymiarami (app.js)

- Stan: `manualDims[name] = { wMm, hMm }`. Inicjalizacja przy pojawieniu się
  pliku w palecie = `uploadsInfo[name].page_sizes_mm[0]`.
- `renderPalette()`: dla każdego 2-str. pliku render wiersza:
  `nazwa` · `szer.[mm]` · `wys.[mm]` · `[Dodaj na arkusz]`.
- Klik „Dodaj na arkusz" (lub nazwa) → `addInstance(name)` używa `manualDims[name]`
  i wyśrodkowuje na obszarze OPOS (jak dziś).
- `oninput` na polu wymiaru → aktualizuje `manualDims[name]` i **przeskalowuje
  wszystkie placementy** tego pliku (D1): dla `rot∈{0,180}` → `wMm=W,hMm=H`;
  dla `rot∈{90,270}` → `wMm=H,hMm=W`; `xMm/yMm` bez zmian. Potem `renderCanvas()`
  + `schedulePreview()`.
- Walidacja graniczna wymiaru: liczby > 0; puste/≤0 → nie skalujemy (ignoruj do
  poprawnej wartości).

### Frontend — wysyłka zlecenia (app.js `manualJobBody`)

- `manual_items` wysyła teraz `{ upload, width_mm, height_mm }` z `manualDims`.
- `manual_placements` bez zmian (`item_index,x_mm,y_mm,rotation_deg`) — footprint
  wynika z wymiaru itemu po stronie backendu.

### Backend (web/job_builder.py)

- `ManualItemParams`: `width_mm: float | None = None`, `height_mm: float | None = None`.
- `_build_manual_job`: gdy `width_mm>0 and height_mm>0`, nadpisz footprint itemu —
  ustaw `print_page_size_mm` i `cut_page_size_mm` na `(width_mm, height_mm)`.
  Zawartość (`*_content_bbox_pt`, `*_content_size_mm`) bez zmian → kadr eksportu
  pozostaje wyśrodkowany na treści (D3). `build_manual_layout` i
  `validate_manual_placements` używają footprintu, więc nachodzenie/poza-OPOS
  liczą się poprawnie dla nowego wymiaru.
- Brak zmian w `summa_cut/export.py` i `manual_layout.py` (footprint płynie z itemu).

## Testy

- **Backend (pytest):**
  - `_build_manual_job` z `width_mm/height_mm` → `montage_items[i].print_page_size_mm`
    == wpisany wymiar; placement footprint == wymiar; walidacja nachodzenia działa
    na nadpisanym wymiarze.
  - Brak wymiaru (None) → zachowanie jak dziś (rozmiar z PDF). 96 istniejących zielonych.
- **Frontend (Playwright, na realnej aplikacji lokalnej):**
  - Po włączeniu trybu manualnego: `#manual-stage` jest w prawym panelu, PNG-podgląd
    ukryty; kanwa szeroka (≈ szer. prawej kolumny).
  - Paleta pokazuje pola wymiaru z domyślnym rozmiarem strony.
  - Zmiana wymiaru → prostokąt(y) tego pliku na kanwie zmieniają rozmiar.
  - „Dodaj na arkusz" → wyśrodkowany użytek; drag przesuwa.

## Poza zakresem (YAGNI)

- Skalowanie grafiki do wymiaru (odrzucone w D3).
- Wymiar per-placement (różny dla kopii tego samego pliku) — wymiar jest per plik (D1).
- Zmiana układu w trybach innych niż manualny.

## Wdrożenie

Standardowo: rsync → `docker build -t summa-cut-web:local` → `midclt call app.redeploy summa-cut`
na drukpolu; bump `?v=N` dla JS/CSS. Commit + dual-push (dom + GitHub).
