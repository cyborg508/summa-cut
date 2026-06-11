# Tryb specjalny — interaktywny edytor 3×3 (web) — projekt

Data: 2026-06-11

## Problem

Webowy tryb specjalny (Faza 3) działa, ale UI jest nieintuicyjny: 8 surowych pól
liczbowych z krypticznymi etykietami (`rząd 0 X`, `kol 0 Y`, `kol 0 X`, `rząd 0 Y`…)
bez żadnego sprzężenia wizualnego — operator nie widzi, co które pole robi, ani czy
kafle się zazębiają. Dodatkowo pokazywanie tylko 2×2 nie wystarcza do oceny
zazębienia — trzeba widzieć kafel środkowy otoczony sąsiadami, czyli **3×3**.

Desktopowy „original" summa-cut rozwiązywał to interaktywnym edytorem: kanwa
rysująca **3×3** kafli z realną grafiką, gdzie **przeciągasz kafel myszą** (z Shiftem
lub bez), a wynik liczony jest z bazowej, powtarzalnej jednostki **2×2**.

## Cel

Zastąpić 8 pól liczbowych portem desktopowego edytora: **podgląd 3×3 + przeciąganie**,
parametry pozostają jako **2×2 powtarzalne** (8 offsetów), **bez zmian w silniku**.

## Decyzje (zatwierdzone w burzy mózgów)

1. **Model: 3×3 podgląd, 2×2 parametry powtarzalne** (wariant A). Silnik już to liczy
   (`layout._build_special_mode_placements`, `export.generate_output_docs` z
   `use_special`). NIE robimy 9 niezależnych kafli.
2. **Kafle z realną grafiką** przyciętego wykrojnika (nakładka druk+wykrojnik), jak
   desktop — backend zwraca jeden obraz kafla, front powiela go 9×.
3. **Dwa tryby przeciągania**, oba wymagane (mapowanie 1:1 z desktopu):
   - **Tryb „Zazębienie" (bez Shift):** poziomo → `row_offsets` (przesuwa środkowy
     RZĄD względem rzędów 1 i 3), pionowo → `col_offsets` (przesuwa środkową KOLUMNĘ
     względem kolumn 1 i 3).
   - **Tryb „Odstęp" (z Shift):** poziomo → `col_x_offsets` (odstęp KOLUMN), pionowo →
     `row_y_offsets` (odstęp RZĘDÓW).
   - Tryb wybierany **widocznym przełącznikiem** (odkrywalność), a trzymanie **Shift**
     działa jako skrót do trybu „Odstęp".
4. **8 pól liczbowych** → zwijana sekcja „dostrojenie ręczne", dwukierunkowo
   zsynchronizowana z edytorem (kto chce wpisać dokładną wartość mm — dalej może).
5. **Strzałki klawiatury** = drobny krok (0,5 mm) dla zaznaczonego kafla, w aktywnym
   trybie.
6. **Żywy podgląd całego arkusza** (istniejący) odświeża się po puszczeniu kafla
   (throttle), a edytor 3×3 reaguje natychmiast (klient, bez serwera).

## Mapowanie offsetów (referencja)

Indeksy bazowe: rząd 0 i 2 → baza 0, rząd 1 → baza 1 (analogicznie kolumny). Czyli
przeciąganie środkowego kafla (rząd 1, kol 1) steruje `*_offsets[1]`, a powtórki 0/2
pokazują efekt. Port desktopowego `_preview_tile_origin_pt` i `mouseMoveEvent`:

```
origin_x(row,col) zależy od: row_offsets[base(row)] + col_x_offsets wg kolumny
origin_y(row,col) zależy od: col_offsets[base(col)] + row_y_offsets wg rzędu
drag bez Shift: row_offsets[base(row)] += dx ;  col_offsets[base(col)] += dy
drag z Shift  : col_x_offsets[base(col)] += dx ;  row_y_offsets[base(row)] += dy
```

(Δ przeliczane z pikseli na mm przez skalę edytora.)

## Komponenty

### 1. Backend — `GET /api/special/tile.png` (jedyna nowa rzecz w backendzie)

- Zwraca PNG **jednego przygotowanego kafla**: nakładka strony druku i wykrojnika z
  przyciętych PDF-ów sesji (`__special_print__.pdf` + `__special_cut__.pdf`, które już
  istnieją po `/api/special/prepare`).
- Rasteryzacja przez istniejący stos fitz (jak `web/preview_render.py`). Wykrojnik
  rysowany półprzezroczyście na druku, żeby było widać obrys.
- Wymaga przygotowanej sesji specjalnej: jeśli brak przyciętych uploadów → **400**
  z jasnym komunikatem (spójnie z resztą tras, np. `/api/special/prepare`).
- Brak zmian w: `prepare_special_trim`, `job_builder`, `SpecialModePattern`, silniku,
  `/api/job`, `/api/generate`, `/api/download`.

### 2. Frontend — widget edytora 3×3 (`web/static/`, vanilla JS)

- **Stan:** istniejący obiekt `special` (po prepare ma `printUpload/cutUpload/pageW/
  pageH/ready`) + bieżące 8 offsetów + bieżący tryb (`zazebienie`|`odstep`) + zaznaczony
  kafel.
- **Render (SVG):** kontener 3×3; po `ready` pobiera `tile.png` raz i rysuje 9 `<image>`
  na pozycjach z portu `_preview_tile_origin`. Środek wyróżniony; powtórki przygaszone.
  Skala dobierana do bounding-boxa 9 kafli (jak desktop `_layout_metrics`).
- **Interakcja:** `pointerdown` na kaflu zaznacza i startuje drag; `pointermove`
  aktualizuje offsety wg trybu (mapowanie wyżej) i przerysowuje SVG natychmiast;
  `pointerup` kończy, throttle → `/api/job` + odświeżenie podglądu arkusza.
- **Przełącznik trybu:** dwa przyciski „Zazębienie" / „Odstęp"; Shift wciśnięty w
  trakcie drag tymczasowo wymusza „Odstęp".
- **Strzałki:** gdy kafel zaznaczony, ←↑↓→ zmieniają właściwy offset o 0,5 mm w aktywnym
  trybie.
- **Sekcja „dostrojenie ręczne" (zwijana):** dotychczasowe 8 pól; zmiana pola →
  aktualizuje stan i SVG; drag → aktualizuje pola. Jedno źródło prawdy = obiekt stanu.
- **Integracja:** `collectParams()` bez zmian merytorycznych — dalej wysyła 4 listy
  offsetów z aktualnego stanu. `invalidateSpecial()` (zerowanie po zmianie źródła/spadu)
  zostaje. Sekcja zastępuje obecny blok 8 surowych pól w `index.html`.

### 3. Bez zmian

Silnik (`summa_cut/*`), `prepare_special_trim`, `web/job_builder.py`, model
`SpecialModePattern`, trasy job/generate/download. To czysto warstwa prezentacji +
jeden endpoint podglądu kafla.

## Przepływ danych

1. upload druku+wykrojnika (jak teraz).
2. „Przygotuj wykrojnik" → `/api/special/prepare` (jak teraz) → `ready`, rozmiar kafla.
3. Edytor pobiera `/api/special/tile.png`, rysuje 9 kafli.
4. Operator przeciąga / przełącza tryb / używa strzałek → offsety w stanie, SVG na żywo.
5. Po puszczeniu (throttle) → `/api/job` (count/rows/cols) + `/api/preview/{print,cut}.png`.
6. „Generuj i zapisz" → `/api/generate` + `/api/download` (bez zmian).

## Testy

- **pytest:**
  - `/api/special/tile.png` zwraca `image/png` o niezerowym rozmiarze po prepare;
    zwraca 400 bez przygotowanej sesji specjalnej.
  - Kontrakt id-ów nowego edytora w `index.html` (kontener 3×3, przyciski trybu,
    sekcja „dostrojenie ręczne", 8 pól nadal obecne w zwijanej sekcji).
  - `node --check web/static/app.js`.
- **Czysta funkcja mapowania:** logikę `tileOrigin(row,col,offsets,pageW,pageH)` i
  `applyDrag(mode,row,col,dx,dy)` trzymamy jako małe, czyste funkcje JS; pokrywamy je
  smoke’iem Playwright (niżej). (Pytest ich nie dotyka — to JS.)
- **Playwright (plugin `example-skills:webapp-testing`):** smoke E2E przeciw żywemu
  uvicornowi — po prepare: drag środkowego kafla w trybie „Zazębienie" zmienia
  `row_offsets`/`col_offsets` (widoczne w polach „dostrojenie ręczne") i zmienia liczbę
  użytków z `/api/job`; przełączenie na „Odstęp" + drag zmienia `col_x_offsets`/
  `row_y_offsets`. To domyka lukę warstwy drag/JS, której pytest nie łapie.

## Poza zakresem (YAGNI)

- Prawdziwe 9 niezależnych kafli (odrzucone — wariant B).
- Rotacja kafli, montaż mieszany ze specjalnym.
- Zoom/pan edytora ponad auto-skalę.
- Zapisywanie/biblioteka presetów ułożeń (ewentualnie osobny etap, jeśli pojawi się
  potrzeba — np. „cegiełka ½").

## Wdrożenie

Po implementacji: rsync + `docker compose up -d --build` na drukpolu (bez nowych
zależności — `tile.png` używa już obecnego fitz). Smoke E2E + obejrzenie edytora przez
usera w przeglądarce.
