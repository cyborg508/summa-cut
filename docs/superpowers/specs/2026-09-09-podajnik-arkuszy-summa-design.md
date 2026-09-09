# Podajnik arkuszy 330×488 do plotera Summa S One D120 — projekt (WIP)

**Data:** 2026-09-09
**Status:** burza mózgów **niedokończona** — przerwana na etapie zatwierdzania architektury.
**Punkt wznowienia:** patrz sekcja „Gdzie stanęliśmy" na końcu.

---

## 1. Cel

Automatyczny podajnik arkuszy dla plotera tnącego Summa S One D120, montowany z tyłu maszyny.
Ma pozwolić na **odejście od plotera na ~godzinę** przy długiej serii tego samego zlecenia.

Konstrukcja DIY. Dostępne: ploter laserowy do pleksi, zamawianie wydruków 3D, sprężone powietrze
w hali, złom po starych drukarkach (silniki krokowe, rolki, separatory).

---

## 2. Ustalenia twarde (od użytkownika, potwierdzone przy maszynie)

| Parametr | Wartość |
|---|---|
| Arkusz | 330 × 488 mm |
| Orientacja | **krawędź czołowa 330 mm** — 330 w poprzek maszyny, 488 w kierunku posuwu |
| Papier | ~120 g/m², papier lub folia samoprzylepna; **silnie naelektryzowany** po druku |
| Cięcie | **wyłącznie kiss-cut**, nigdy na wylot ⇒ arkusz zostaje w jednym kawałku |
| Czas cięcia | 1–5 min na arkusz (razem z szukaniem OPOS) |
| Budżet czasu podajnika | 30–60 s na cykl — **podajnik może być wolny** |
| Wielkość serii | ~100 arkuszy na jedno ładowanie (stos ≈ 13 mm) |
| Tolerancja OPOS | **±3 mm w każdą stronę**; przy większym błędzie ploter wchodzi w tryb szukania |
| Odbiór grawitacyjny | **NIE działa** — arkusz nie wypada sam po podniesieniu rolek |
| Dźwignia rolek | niebieska, esowata, prawy tył, skok ok. 90° |
| Rolki dociskowe | 3 szt., przesuwne po szynie |

### Kluczowe zachowanie plotera (to definiuje całą architekturę)

1. Summa **nie przyjmie zadania**, dopóki arkusz nie jest założony.
2. Po cięciu arkusz **zatrzymuje się w rolkach** i czeka, aż ktoś go wyjmie.
3. Po włożeniu kolejnego arkusza w ten sam sposób i zamknięciu rolek **cięcie startuje
   automatycznie, bez ponownego wysyłania zadania**.
4. Podniesienie dźwigni rolek **nie kasuje zadania**.
5. Podczas pracy ploter przesuwa arkusz **w przód i w tył** — przy 488 mm arkusza jego tył
   wyjeżdża daleko poza maszynę.

**Konsekwencja:** podajnik **nie musi w ogóle rozmawiać z komputerem ani z ploterem**.
Operator raz uruchamia pracę i raz ustawia pierwszy OPOS ręcznie; dalej pętla jest ślepa
i czysto mechaniczna. Cała warstwa integracji z PC wypada z projektu.

---

## 3. Rozeznanie rynku

Summa produkuje fabryczny odpowiednik — **Tray One**:
- obsługuje formaty do Tabloid Extra (13×19" = 330×483 mm), media 150–300 g/m²,
- arkusz jest wpychany w szczelinę **bez podnoszenia rolek dociskowych**,
- wymaga parametru „Tray One = ON" w firmware i oprogramowania GoSign,
- **kompatybilny wyłącznie z S1D60 i S1D75 — nie z D120**.

⇒ Zakup odpada, DIY uzasadnione. Potwierdza za to, że format i sama idea są wykonalne.

---

## 4. Architektura — sześć modułów

Kolejność w cyklu: magazyn → separacja → podanie → dźwignia w dół → *(cięcie)* →
dźwignia w górę → odbiór → od nowa.

| Moduł | Zadanie | Z czego | Test odbiorczy |
|---|---|---|---|
| **M1 magazyn** | ~100 ark. 330×488, prowadnice boczne, stała pozycja stosu | pleksi (laser) + narożniki 3D, na istniejącym stelażu roli | stos nie rozjeżdża się po 100 pobraniach |
| **M2 separacja** | oddziela i podaje **dokładnie jeden** arkusz | eżektor Venturiego, 2 zawory 12 V, przyssawki, ramię na serwie | **50/50 pojedynczo** na świeżym, naelektryzowanym stosie |
| **M3 podawanie** | wsuwa na stałą głębokość, potem **rozwiera docisk** | krokowiec + rolki ze starej drukarki, czujnik IR krawędzi | rozrzut wsunięcia < ±1,5 mm w 50 próbach |
| **M4 dźwignia** | podnosi/opuszcza dźwignię rolek dociskowych | siłownik liniowy 12 V + obejma 3D | 200 cykli bez przestawienia mocowania |
| **M5 odbiór** | wypycha wycięty arkusz z przodu do kosza | rolka na ramieniu, silnik DC + serwo | 50/50 arkuszy opuszcza maszynę |
| **M6 sterownik** | sekwencja, czasy, koniec cięcia, obsługa błędów | ESP32 + sterownik krokowca + panel WWW przez WiFi | seria 100 arkuszy bez interwencji |

### Decyzje projektowe i ich uzasadnienia

**Separacja: przyssawka + nadmuch (+ zbijanie ładunku).**
Odrzucone metody cierne (rożki narożne, rolka hamująca/retard, bramka szczelinowa), bo wszystkie
zakładają, że tarcie arkusz–arkusz jest mniejsze niż tarcie narzędzie–arkusz, a **elektrostatyka
łamie dokładnie to założenie**. Powietrze i podciśnienie działają niezależnie od tarcia.
Dodatkowo bramka szczelinowa przy 120 g nie zadziała — arkusz wyboczy się zamiast przejść.
Uzupełniająco: listwa jonizująca nad magazynem, uziemiona szczotka/tasiemka na drodze papieru,
uziemiona rama.

**Podciśnienie z eżektora Venturiego, nie z pompy.** W hali jest sprężone powietrze, więc jedno
źródło zasila i nadmuch, i podciśnienie. Brak części ruchomych, brak pompy, brak hałasu.
⚠️ **Instalacja warsztatowa niesie olej i wodę** — konieczny filtr-osuszacz + **reduktor
precyzyjny na 0,2–0,5 bara** (6 barów z sieci rozrzuci stos).

**Pobieranie z wierzchu stosu.** Pierwotnie proponowane pobieranie spod stosu **odrzucone przez
użytkownika** — przy 120 g i silnej statyce arkusz się skleja i wyboczy. Argument za spodem
(stała płaszczyzna podawania) upada, bo stos 100 ark. × 120 g to tylko ~13 mm — wystarczy
sprężynowana półka albo przyssawka na wahliwym ramieniu z podatnym zawieszeniem.

**Rolki podające muszą rozwierać docisk po wsunięciu.** Inaczej ploter, przesuwając arkusz
w tył podczas cięcia, szarpałby go przez nasz mechanizm albo zgubił pozycję. Po wsunięciu docisk
idzie w górę i arkusz swobodnie ślizga się po blacie z pleksi. Blat musi sięgać ≥250 mm za linię
rolek i nie kolidować z magazynem.

**Koniec cięcia z akcelerometru przyklejonego do ramy plotera.** Cięcie to nieprzerwane drgania;
cisza przez 10 s = koniec pracy. ~15 zł, brak celowania obiektywem, obojętne czy praca trwa
minutę czy pięć. Odrzucone: czasówka (musi być ustawiona na najdłuższą pracę ⇒ przy pracach
minutowych ~7 h straty na 100 arkuszy) i kamera (droższa i zawodniejsza w tej roli).

**Twarda bramka minimalnego czasu pracy.** Jeśli „cisza" przyjdzie po 20 s, to nie koniec pracy,
tylko **ploter stanął z błędem** (np. nie znalazł OPOS). Bez tego zabezpieczenia podajnik dosunąłby
kolejny arkusz na zakleszczony — i tak 80 razy pod rząd.

**Brak stacji rejestracji z wybrzuszaniem arkusza.** Przy tolerancji OPOS ±3 mm to przepłacanie
dokładności, której ploter nie wykorzysta. Wystarczą prowadnice boczne + wsunięcie na stałą drogę
od wykrytej krawędzi. (Rozważane wcześniej, bo przy rolkach dociskowych **nie ma miejsca na
zderzaki czołowe** — użytkownik potwierdził.)

**Zero ingerencji w ploter.** Żadnego USB, żadnego dotykania ekranu, żadnego wiercenia —
wszystko na obejmach do istniejącego stelaża roli i ramy stojaka.

---

## 5. Warunki brzegowe z oględzin maszyny

Zdjęcia: `docs/podajnik/foto/` (7 ujęć, 2026-09-09).

- Ploter stoi na firmowym stojaku na kółkach, z przodu tekstylny kosz na materiał.
- Z tyłu **stelaż na rolę** (dwa wałki + wsporniki) — gotowa rama nośna pod podajnik,
  nie trzeba niczego stawiać na podłodze.
- Z tyłu ciasno (kaloryfer, ściana) ⇒ **maszynę trzeba odsunąć od ściany na stałe o ~30–40 cm**.
- Załadowany arkusz zwiesza się z przodu przez blat w dół, do kosza.
- Panel dotykowy przy prawym krańcu maszyny (na razie nieużywany w projekcie).

---

## 6. Czego jeszcze nie ustaliliśmy

- **Sekwencja sterowania w szczegółach** — kolejność, czasy, warunki przejść między stanami.
- **Obsługa błędów** — brak arkusza, podwójne pobranie, przekrzywienie, pusty magazyn,
  zatrzymanie plotera z błędem. Zarys: retry 3×, potem stop i alarm; bramka minimalnego czasu pracy.
- **Etapy budowy i kosztorys** — zarys: eżektor 80–150 zł, 2 zawory ~80 zł, filtr + reduktor ~100 zł,
  przyssawki ~30 zł, ESP32 ~30 zł, serwa/siłownik 60–120 zł, czujniki ~30 zł, pleksi + druk 3D ~200 zł;
  silniki i rolki z odzysku. Razem rząd **600–900 zł**.
- **Siła potrzebna do przestawienia dźwigni rolek** — do zmierzenia wagą bagażową; przesądza
  o wyborze siłownik liniowy vs serwo.
- Sposób mocowania M5 (odbiór) z przodu tak, żeby nie wchodzić w tor karetki.

## Kolejność budowy (ustalona zasada)

**Najpierw sama separacja (M2), jako makieta na blacie**, przed ramą, magazynem i serwem.
To jedyny moduł, który może wywrócić cały projekt. Godzina cięcia pleksi, realny naelektryzowany
stos prosto z maszyny, 50 prób pod rząd. Jak padnie — tracimy kawałek pleksi zamiast dwóch tygodni.

---

## 7. Gdzie stanęliśmy

Przedstawiona została architektura sześciu modułów (sekcja 4) wraz z trzema decyzjami do
zakwestionowania: rozwieranie rolek podających, akcelerometr zamiast kamery/zegara oraz bramka
minimalnego czasu pracy. **Użytkownik nie zdążył jej zatwierdzić ani odrzucić.**

**Wznowienie:** poprosić o ocenę architektury z sekcji 4. Po akceptacji przejść do
sekwencji sterowania, obsługi błędów i etapów budowy z kosztorysem — potem dopiero plan wdrożenia.

Materiały wizualne z burzy mózgów (przekroje, cykl 6 faz, warianty separacji): `docs/podajnik/*.html`.
