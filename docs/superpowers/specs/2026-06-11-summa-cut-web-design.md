# summa-cut Web — projekt architektury

Data: 2026-06-11
Status: zatwierdzony do planowania

## 1. Założenia i nie-cele

**Cel:** webowa wersja summa-cut z pełną parnością funkcji względem desktopu,
hostowana w kontenerze Docker na drukpolu (TrueNAS SCALE), dostępna wyłącznie
z LAN drukpol oraz przez Tailscale, bez logowania (sieć zaufana).

**Sterownik decyzji:** realnym powodem jest wygoda wdrożeń/aktualizacji (jeden
kontener) i „zero instalacji u klienta" (web), a nie moc obliczeniowa — wolny
zapis (~47 s @560 użytków) wynika z superliniowego algorytmu, nie z CPU, i jest
adresowany osobno portem na pikepdf (Faza 0), który działa też na desktopie.

**Nie-cele:** publiczne wystawienie do internetu, konta użytkowników,
multi-tenant z twardą izolacją, mobilny UX. Desktop Qt **zostaje nietknięty** —
dzieli z wersją web ten sam silnik.

## 2. Struktura repo (jedno `~/summa-cut`, jeden silnik, dwa fronty)

```
summa_cut/        # RDZEŃ (API bez zmian): layout, opos, export, models, preview
  export.py       #   ← Faza 0: port mechaniki osadzania na pikepdf
app.py            # desktop Qt (zostaje)
special_mode_app.py
web/              # NOWE
  server.py       # FastAPI: trasy + cykl życia sesji
  routes_main.py  # tryb główny (montaż/split/manual_grid/krata)
  routes_special.py # tryb specjalny (wektorowy obrys)
  rendering.py    # silnik → PNG podglądu (opakowanie preview.py)
  sessions.py     # sesje w pamięci + workdir na wolumenie
  templates/      # Jinja2 + HTMX (formularze, panele podglądu)
  static/         # CSS + minimum JS (debounce, podmiana <img>)
Dockerfile        # chudy obraz bezgłowy (python + pymupdf + pikepdf, BEZ Qt)
compose.yaml      # uruchomienie jako custom app na SCALE
tests/            # + nowe testy backendu (headless, bez Qt)
```

**Zasada nadrzędna:** silnik (`summa_cut/`) pozostaje jedynym źródłem prawdy dla
matematyki layoutu/OPOS i mechaniki osadzania PDF. Web tylko go woła; żadnej
logiki layoutu nie duplikujemy po stronie klienta.

## 3. Komponenty

- **Silnik (`summa_cut/`)** — `compute_layout(job)`, `get_opos_positions`,
  `generate_output_docs` / `generate_cut_grid`, tryb specjalny
  (`get_drawings()` + spad + ścieżka clipping). API w zasadzie bez zmian;
  jedyna ingerencja to przepisanie mechaniki osadzania w `export.py` na pikepdf
  (Faza 0).
- **`web/rendering.py`** — przyjmuje `JobSettings` + załadowane źródło i zwraca
  PNG-i podglądu (druk / wykrojnik / złożony) przez istniejącą rasteryzację
  kafli (`preview.render_source_tile` + `render_layout_preview`). Cache miniatur
  kafla per (ścieżka, strona), jak w desktopie.
- **`web/sessions.py`** — `session_id` w ciasteczku → obiekt sesji
  `{workdir, źródłowe PDF-y, bieżący JobSettings}`. Mapa w pamięci + pliki w
  `/data/sessions/<id>` na wolumenie Dockera. TTL 6 h + okresowe sprzątanie.
  Bez bazy danych.
- **`web/routes_main.py` / `web/routes_special.py`** — trasy HTTP: upload,
  ustaw parametr, podgląd, generuj, pobierz.
- **Front (templates + HTMX)** — formularz kontrolek 1:1 z desktopem (arkusz,
  rozmiar użytku, tryby split horizontal/max_spread, manual_grid,
  montaż wielu użytków + quantity, krata cięcia bez odstępów, parametry OPOS).
  Zmiana pola → HTMX POST z debounce 150 ms → serwer zwraca podmieniony `<img>`
  podglądu. Tryb specjalny na osobnej zakładce/stronie.

## 4. Przepływ danych

1. **Upload** — użytkownik wgrywa źródłowy PDF (strona druku + strona
   wykrojnika); plik ląduje w workdir sesji, czytany przez PyMuPDF.
2. **Konfiguracja** — kontrolki budują `JobSettings`; po każdej zmianie serwer
   liczy `compute_layout` + OPOS i renderuje PNG podglądu (debounce 150 ms).
3. **Podgląd** — przeglądarka pokazuje 3 obrazki; round-trip ~30 ms render +
   mały PNG po LAN/Tailscale (niezauważalne).
4. **Generuj** — serwer woła zportowany na pikepdf eksport → `<nazwa>_druk.pdf`
   + `<nazwa>_wykrojnik.pdf` do workdir sesji.
5. **Pobierz** — linki do obu plików (druk.pdf + wykrojnik.pdf, osobno). Bez
   trwałego magazynu — pliki znikają z TTL sesji.

## 5. Sesje i współbieżność

Sieć zaufana, ale web bywa wieloosobowy — stąd lekka izolacja per-sesja
(ciasteczko + workdir), bez kont. Blokujące generowanie puszczamy w puli wątków
uvicorna, żeby jeden zapis nie zamroził cudzego podglądu. Brak kolejki i bazy —
YAGNI.

## 6. Port eksportu na pikepdf (Faza 0, warunek wstępny)

`generate_output_docs` przechodzi z setek wywołań `show_pdf_page` na osadzenie
strony źródła jako **XObject + N odwołań** (zmierzone ~85 ms @560 vs ~47 s).
Zysk dotyczy też desktopu.

**Ryzyko fidelity** (clip / centrowanie wg content bbox / obrót 90° / rozmiar
pliku / wektor vs raster) adresujemy **testem regresji**: ten sam wsad
generujemy starą i nową drogą, renderujemy oba wyniki do PNG i porównujemy
pikselowo w tolerancji oraz sprawdzamy pozycje placementów. Tryb bez odstępów
(`generate_cut_grid`) nie używa PDF wykrojnika i pozostaje bez zmian.

## 7. Deployment na drukpolu (TrueNAS SCALE)

- **Obraz:** `python:3.12-slim` + PyMuPDF + pikepdf + FastAPI/uvicorn/Jinja2.
  Bez Qt, bez X-serwera. Mały, bezgłowy.
- **Uruchomienie:** `compose.yaml` jako *custom app* w SCALE; nazwany wolumen na
  workdir sesji; `restart: unless-stopped`.
- **Sieć:** kontener nasłuchuje na porcie hosta; dostęp przez
  `http://<lan-ip-drukpol>:PORT` oraz `http://<tailscale-ip-drukpol>:PORT`.
  Drukpol nie jest przekierowany na świat; dodatkowo nie publikujemy publicznie
  i zdajemy się na firewall + Tailscale ACL. Bez TLS i loginu (sieć zaufana).
- **Aktualizacje:** przebudowa obrazu → nowy tag → recreate kontenera. To jest
  zakładana „łatwość wdrożeń".

## 8. Testy

- **Silnik:** istniejące 10 testów headless + nowy test regresji pikepdf
  (Faza 0).
- **Backend:** testy tras headless (upload → podgląd → generuj → pobierz) przez
  `fastapi.TestClient`, bez przeglądarki i bez Qt.
- **Podgląd:** test, że `web/rendering.py` zwraca niezerowy PNG dla
  reprezentatywnego `JobSettings`.

## 9. Fazy (każda jako osobny krok planu wdrożenia)

- **Faza 0** — port eksportu na pikepdf + test regresji fidelity (wartość też
  dla desktopu).
- **Faza 1** — backend API (sesje, upload, layout, podgląd PNG, generuj,
  pobierz), headless, otestowany.
- **Faza 2** — front HTML/HTMX, pełny tryb główny
  (montaż / split / manual_grid / krata / OPOS).
- **Faza 3** — webowy tryb specjalny.
- **Faza 4** — Dockerfile + compose + deployment na drukpolu, sieć/Tailscale,
  smoke end-to-end.

## Otwarte parametry (domyślne, do ew. korekty w trakcie)

- TTL sesji: 6 h.
- Pobranie: dwa osobne linki (nie ZIP).
- Port nasłuchu: do ustalenia przy Fazie 4.
