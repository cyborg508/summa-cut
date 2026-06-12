# UI: przełączany panel (edytor/podgląd) + jednolity podgląd + refresh wyglądu — projekt

Data: 2026-06-12

## Problem

Mechanika trybu specjalnego działa, ale UI ma trzy bolączki:
1. **Podgląd to dwa obrazki pod sobą** (Druk + Wykrojnik) — zajmują dużo pionu, trzeba
   scrollować, brak skalowania do ekranu.
2. **Edytor 3×3 siedzi w wąskiej kolumnie kontrolek** (max ~340 px) — za mały do pracy.
3. **Wygląd całości jest surowy** (domyślne kontrolki HTML) — user chce, żeby było ładnie.

## Cel

Przebudować warstwę prezentacji (BEZ zmiany mechaniki/silnika/API): prawy panel staje
się **jednym przełączanym oknem**, podgląd to **jeden skalowany obraz z przyciskami
Druk/Wykrojnik**, edytor 3×3 dostaje **całą szerokość panelu**, a całość zyskuje
**spójny, ładny wygląd** (skill frontend-design w fazie implementacji).

## Decyzje (zatwierdzone w burzy mózgów)

1. **Układ: wariant B — prawy panel przełączany.** Lewa kolumna = kontrolki (bez zmian
   funkcjonalnych). Prawy panel (szeroki) ma górny przełącznik widoku.
2. **Przełącznik widoku panelu** `[Edytor 3×3 | Podgląd]` pokazywany **tylko gdy tryb
   specjalny włączony**. Po włączeniu trybu specjalnego panel domyślnie pokazuje
   **Edytor**. W trybie zwykłym (bez specjalnego) panel pokazuje tylko Podgląd (bez
   górnego przełącznika).
3. **Podgląd = jeden obraz** skalowany do ekranu (`object-fit: contain`, ograniczony
   wysokością okna), z przełącznikiem **`[Druk | Wykrojnik]`** zmieniającym co widać
   (zamiast dwóch `<img>` pod sobą).
4. **Edytor 3×3 przeniesiony do prawego panelu** (widok „Edytor"), na całą szerokość;
   px→mm już liczone per oś wg `getBoundingClientRect`, więc większy rozmiar działa
   poprawnie. **Zwijane „Dostrojenie ręczne" (8 pól) przenosi się RAZEM z edytorem** do
   panelu (pod kanwą). W lewej kolumnie zostają tylko kontrolki trybu specjalnego:
   włącz, spad, „Przygotuj wykrojnik", status.
5. **Pełny refresh wyglądu całej appki** skillem frontend-design: nagłówek, kolumna
   kontrolek (sekcje jako karty), panel, segmentowane przełączniki, przyciski,
   typografia, odstępy, stany (hover/focus/disabled). Estetyka: czysta, „warsztatowa",
   profesjonalna; narzędzie LAN bez logowania.

## Komponenty

### Front (`web/static/index.html`, `app.js`, `style.css`)

- **Prawy panel — przełącznik widoku.** Segmentowany `[Edytor 3×3 | Podgląd]`
  (`#view-editor` / `#view-preview`), widoczny tylko przy włączonym trybie specjalnym.
  Stan `rightView ∈ {editor, preview}`. Po `onSpecialToggle(on=true)` → `rightView =
  editor`; po wyłączeniu → `preview` i przełącznik ukryty. Przełączanie pokazuje/ukrywa
  kontener edytora vs kontener podglądu.
- **Podgląd jednoobrazkowy.** Zamiast `#preview-print` + `#preview-cut` (dwa `<img>`) —
  jeden `<img id="preview-img">` + segmentowany `[Druk | Wykrojnik]`
  (`#preview-print-btn` / `#preview-cut-btn`). Stan `previewWhich ∈ {print, cut}`.
  `updatePreview()` po `applyJob()` ustawia `src` widocznego obrazu na
  `/api/preview/{previewWhich}.png?t=…`; przełącznik zmienia `previewWhich` i odświeża
  `src`. Obraz: `max-height: calc(100vh - …)`, `object-fit: contain`, `width:100%`.
- **Edytor 3×3 w panelu.** `#special-editor` (SVG) + legenda + zwijane „Dostrojenie
  ręczne" przenoszone z lewej kolumny do widoku „Edytor" w prawym panelu. Edytor
  rośnie do szerokości panelu (np. `width:100%; height: min(70vh, …)`). Logika
  (`tileOrigin`/`applyDrag`/`renderSpecialEditor`/pointer/keys) BEZ ZMIAN — tylko inny
  rodzic i większy rozmiar. „Dostrojenie ręczne" (8 pól) zostaje powiązane jak teraz
  (`readOffsets`/`writeOffsets`; `collectParams`/`specialOffsets` czytają te 8 pól —
  bez zmian).
- **Kontrolki trybu specjalnego w lewej kolumnie:** włącz, spad, „Przygotuj
  wykrojnik", status. (Bez edytora — ten jest w panelu.)
- **Refresh wyglądu:** nowy `style.css` (i drobne klasy w HTML) — spójny system: karty
  sekcji, segmentowane przełączniki, przyciski (primary/secondary/success), pola,
  nagłówek, siatka responsywna (kolumna kontrolek + panel). Bez frameworka CSS (zgodnie
  z resztą projektu — czysty CSS).

### Bez zmian

Backend (`web/server.py`, `preview_render.py`, `job_builder.py`, `special_trim.py`),
silnik (`summa_cut/*`), wszystkie trasy i mechanika. To wyłącznie warstwa prezentacji.
Endpointy podglądu (`/api/preview/print.png`, `/api/preview/cut.png`) i `tile.png` bez
zmian.

## Przepływ (front)

1. Tryb zwykły: panel = Podgląd, `[Druk|Wykrojnik]`, jeden obraz skalowany.
2. Włączenie trybu specjalnego: pokazuje się `[Edytor 3×3|Podgląd]`, panel → Edytor.
3. „Przygotuj wykrojnik" (lewa kolumna) → `tile.png` → edytor renderuje 9 kafli (jak
   teraz, tylko większy).
4. Przeciąganie/strzałki → offsety → throttle → `/api/job` + odświeżenie podglądu
   (przełączenie na „Podgląd" pokazuje wynik; Druk/Wykrojnik wybiera stronę).
5. „Generuj i zapisz" — bez zmian.

## Testy

- **pytest (kontrakt id-ów, statyczne):** nowy panel — `#view-editor`/`#view-preview`,
  `#preview-img`, `#preview-print-btn`/`#preview-cut-btn`; edytor (`#special-editor`) i
  legenda obecne; 8 pól offsetów nadal obecne; brak starych `#preview-print`/
  `#preview-cut` dwóch `<img>` (lub świadoma zmiana — test pilnuje nowej struktury).
- **`node --check web/static/app.js`.**
- **Smoke Playwright (plugin webapp-testing):** (a) tryb zwykły — `[Druk|Wykrojnik]`
  przełącza `src` jednego obrazu; (b) włączenie trybu specjalnego pokazuje przełącznik
  widoku i domyślnie Edytor; (c) `[Edytor|Podgląd]` przełącza zawartość panelu; (d) po
  prepare edytor (większy) ma 9 kafli, a drag środkowego (bez/z Shift) zmienia właściwe
  offsety (potwierdza, że px→mm działa przy nowym rozmiarze); (e) zrzut ekranu do oceny
  wizualnej.
- **Brak regresji** w istniejących testach pytest (76).

## Poza zakresem (YAGNI)

- Zmiany mechaniki/silnika/API.
- Modal/osobne okno edytora (wybrano panel przełączany).
- Tryb ciemny, i18n, presety układów.
- Zmiana zachowania montażu/zwykłego trybu (tylko ich wygląd).

## Wdrożenie

Po implementacji: rsync + `docker compose up -d --build` na drukpolu (bez nowych
zależności runtime — zmiany są w statycznych plikach front + ewentualnie CSS). Smoke +
wizualna ocena usera w przeglądarce.
