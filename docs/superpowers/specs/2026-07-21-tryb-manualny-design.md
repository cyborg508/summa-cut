# summa-cut — Tryb manualny (impozycja ręczna w stylu PlaceIt)

Data: 2026-07-21
Status: zaakceptowany do planowania

## Cel

Dodać do web-aplikacji summa-cut (summa.cyplos.pl) **tryb manualny**: ręczne
układanie użytków na arkuszu w stylu PlaceIt, ale z summa-cutowym wynikiem —
dwa PDF-y (arkusz druku + arkusz wykrojnika ze znacznikami OPOS).

W odróżnieniu od obecnych trybów auto-układu (odstępy / krata / montaż siatkowy),
tutaj **pliki mogą mieć różne formaty**, a użytkownik sam decyduje o pozycji i
obrocie każdej instancji.

## Wejście / wyjście

- **Wejście:** dowolna liczba wgranych PDF-ów, każdy 2-stronicowy
  (str. 1 = druk, str. 2 = wykrojnik). Formaty poszczególnych plików mogą się różnić.
- **Wyjście:** dwa PDF-y — arkusz druku i arkusz wykrojnika. Oba mają te same
  pozycje instancji; arkusz wykrojnika dostaje ramkę znaczników OPOS dla Summy.
  (Bez zmian względem obecnego eksportu summa-cut.)

## Wybrany wariant realizacji

**Wariant A — przenieść interakcję PlaceIt do summa-cut jako nowy tryb.**
Kanwa drag/obrót/kopie/obwódka trafia do summa-cut; eksport zostaje summa-cutowy.
Uzasadnienie: summa-cut posiada trudniejszą, domenową połowę (OPOS, arkusz
wykrojnika, spłaszczanie pod SummaWinPlot), a PlaceIt jej nie zna. Przenosimy
tańszą połowę (interakcję), zostawiając sprawdzony silnik OPOS/wykrojnik.
Jedna apka, jeden deploy pod summa.cyplos.pl.

Odrzucone: (B) budowa kanwy od zera — reinwencja dopracowanego PlaceIt;
(C) dodanie OPOS/wykrojnika do PlaceIt — przeniesienie trudniejszej połowy i
rozbicie narzędzia „Summa" na dwie apki.

## Interfejs i przepływ pracy

**Wybór trybu.** Nowy, rozłączny przełącznik „Tryb manualny". Po włączeniu
chowane są pola auto-układu (rozmiar użytku, odstęp, podział na grupy, siatka
manualna, montaż siatkowy). Zostają widoczne: **rozmiar arkusza** i **OPOS**
(dalej definiują obszar roboczy i znaczniki).

**Paleta użytków.** Każdy wgrany PDF 2-stronicowy staje się kafelkiem palety —
str. 1 = druk, str. 2 = wykrojnik (automatycznie, bez ręcznego wyboru stron).

**Kanwa (SVG, wzorzec istniejącego `special-editor`).** Pokazuje arkusz i obrys
obszaru OPOS. Obsługuje:
- przeciąganie **instancji** z palety na arkusz (jeden użytek = wiele kopii),
- **obrót krokami 90°** (0/90/180/270),
- **duplikuj / usuń** instancję,
- przesuw myszą + doprecyzowanie strzałkami (jak w trybie specjalnym),
- **czerwoną obwódkę na żywo**, gdy instancja nachodzi na inną albo wychodzi
  poza obszar OPOS (parytet z PlaceIt).

**Podgląd.** Prawa strona: kanwa do edycji + istniejący podgląd PNG druk/wykrojnik
do weryfikacji wyniku przed generowaniem.

## Model danych i backend

**Reuse istniejących typów — bez nowych modeli pod pary.**
- Każdy wgrany PDF 2-str. → `MontageItem` (`print_page` = str. 0, `cut_page` =
  str. 1; rozmiary i bboxy z info uploadu). Eksport już rozwiązuje parę
  druk/wykrojnik per placement przez `montage_item_index`.
- Nowe parametry w `JobParams`:
  - `manual_free_enabled: bool`
  - `manual_placements: list[{ item_index, x_mm, y_mm, rotation_deg }]`
- Każdy `Placement`: `width_mm`/`height_mm` = rozmiar strony danego użytku
  (zamienione przy 90°/270°), `rotation_deg` z klienta, `montage_item_index` =
  indeks użytku w palecie. Współrzędne: `y_mm` = góra (spójnie z obecną
  semantyką `Placement` w eksporcie).

**Ścieżka „ręczne pozycje → LayoutResult".**
- `build_job`: gdy `manual_free_enabled`, buduje `montage_items` z palety i
  zwraca job bez `item_spec`/auto-grida.
- Nowa funkcja `build_manual_layout(job, placements)` → składa `LayoutResult`
  wprost z listy `Placement` (pomija `compute_layout`).
- `_job_and_layout` w serwerze rozgałęzia się: manualny → `build_manual_layout`,
  inaczej → `compute_layout`.
- Dalej bez zmian: `generate_output_docs` stempluje oba arkusze (druk + wykrojnik
  z OPOS).

**Do zweryfikowania w implementacji.** Eksport dziś stempluje z `rotation_deg`
0/90 (auto-układ). Sprawdzić ścieżkę `_render_cell_stamp` /
`_stamp_placements_pikepdf` i w razie potrzeby dociągnąć 180°/270°.

## Walidacja / bramka zapisu

- **Na kanwie:** czerwona obwódka na żywo — nachodzenie na inną instancję lub
  wyjście poza obszar roboczy OPOS.
- **Przy „Generuj": blokada** — jeśli którakolwiek instancja nachodzi na inną
  lub wychodzi poza obszar OPOS, generowanie jest odrzucane z komunikatem
  (nie wypuszczamy po cichu wadliwego arkusza; wzorzec bramki PlaceIt).

## Zakres — YAGNI (czego NIE robimy na start)

- brak auto-nestingu / auto-rozmieszczania,
- brak spadu/bleedu (użytek wchodzi jak jest — wykrojnik definiuje cięcie),
- brak snapowania do siatki (swobodnie jak PlaceIt, z doprecyzowaniem strzałkami),
- obrót wyłącznie krokami 90° (nie dowolny kąt).

## Testy

- `build_manual_layout`: poprawne pozycje, rozmiary i rotacja placementów;
  zamiana width/height przy 90°/270°; poprawny `montage_item_index`.
- Eksport: dwa PDF-y; N stempli we właściwych miejscach; arkusz wykrojnika
  ciągnie str. 2 danego użytku; ramka OPOS obecna.
- Bramka walidacji: odrzuca nachodzenie oraz wyjście poza obszar OPOS.
- (Jeśli dociągane) rotacja 180°/270° w eksporcie.

## Poza zakresem tej zmiany

Tryby auto-układu (odstępy, krata, montaż siatkowy, specjalny) pozostają
nietknięte. Deploy bez zmian (rsync → `docker build -t summa-cut-web:local .`
→ `midclt call app.redeploy summa-cut`).
