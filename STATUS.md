# summa-cut — status projektu

## Notatka wydajnościowa 2026-05-25

Najbardziej dokuczliwy problem odczuwalny przez użytkownika to lag przy wpisywaniu:
- rozmiaru strony,
- wymiarów 1 użytku,
- oraz ogólnie czekanie na pojawienie się montażu po zmianie parametrów.

### Najbardziej prawdopodobna przyczyna
Obecny pipeline podglądu jest zbyt ciężki jak na odświeżanie uruchamiane niemal przy każdej zmianie wartości GUI. W praktyce przy zmianie parametrów program liczy layout i odświeża kilka widoków, co daje odczuwalne opóźnienie.

### Najbardziej sensowny kierunek optymalizacji
Kolejność rekomendowanych działań:
1. ograniczyć częstotliwość auto-refresh przy wpisywaniu wartości (np. `editingFinished` albo dłuższy debounce zamiast agresywnego `valueChanged`),
2. rozdzielić szybki podgląd geometryczny montażu od pełnego renderu PDF,
3. przy auto-refresh renderować przede wszystkim podgląd arkusza / układu, a cięższy podgląd PDF robić dopiero po chwili bezczynności albo na żądanie,
4. dodać cache dla już otwartych PDF-ów, bboxów i podglądów,
5. w razie potrzeby przenieść cięższe operacje do workera / background threadu, żeby GUI nie blokowało wpisywania.

### Ważny wniosek architektoniczny
Na ten moment bardziej opłaca się poprawić architekturę odświeżania niż przepisywać cały program do C/C++. Jeśli kiedyś profilowanie pokaże, że naprawdę wolny jest sam silnik obliczeń, wtedy sensowniejsza będzie hybryda: GUI w Pythonie, a tylko najcięższy rdzeń obliczeniowy wyniesiony do szybszej warstwy.

## Aktualizacja 2026-05-20

### Materiały pod GitHub / GitHub Pages
Przygotowany został lokalny szkic strony projektu w katalogu `docs/`.

Dodane pliki:
- `docs/index.html`
- `docs/style.css`
- `docs/README_GITHUB_PAGES.md`

Obecny szkic strony zawiera:
- opis projektu,
- listę najważniejszych funkcji,
- aktualny status projektu,
- najbliższe kroki,
- placeholder pod sekcję pobierania wydań.

### Ważna uwaga o buildzie Windows
W materiałach Windows skrypt `build_windows.ps1` znajduje się obecnie w `dist-windows/`, co nie zgadza się z uproszczoną instrukcją zakładającą uruchomienie go z katalogu głównego projektu.

Praktyczny stan na dziś:
- najpewniejsza ścieżka to ręczne uruchomienie `pyinstaller` z katalogu głównego projektu,
- alternatywnie można skopiować `dist-windows/build_windows.ps1` do katalogu głównego i uruchomić go stamtąd.

### Checkpoint 2026-05-20
Zapisano dodatkowy punkt powrotu:
- `CHECKPOINT-2026-05-20.md`

## Stan na 2026-05-18

Projekt `summa-cut` został rozpoczęty jako nowy desktopowy program do przygotowania PDF do druku i cięcia na ploterze.

## Ustalona technologia
- Python
- PySide6
- PyMuPDF (`fitz`)

Punkt odniesienia technicznego: wcześniejszy projekt `Banner-Eyelets`.

## Zapisane dokumenty projektowe
W katalogu `summa-cut/` są już przygotowane:
- `SPEC.md` — specyfikacja v1
- `GUI.md` — makieta GUI
- `ARCHITECTURE.md` — architektura aplikacji
- `IMPLEMENTATION_PLAN.md` — plan wdrożenia

## Ustalona specyfikacja v1 — skrót
- program przygotowuje dwa pliki wyjściowe:
  - `druk.pdf`
  - `wykrojnik.pdf`
- nie modyfikuje zawartości wejściowych PDF-ów, tylko je enkapsuluje / rozmieszcza / obraca / centruje
- użytkownik wybiera:
  - 1 stronę druku
  - 1 stronę wykrojnika
- wejście może pochodzić z jednego lub kilku PDF-ów, także wielostronicowych
- format wyjściowy domyślnie: `330 × 480 mm`
- rozmiar użytku użytkownik definiuje ręcznie, z możliwością pobrania domyślnego bounding boxa z wybranej strony druku
- obrót w v1: `0°` albo `90°`
- dwa tryby pracy:
  - z odstępami (domyślnie `3 mm`)
  - bez odstępów
- wynik ma zawierać OPOS-y w rogach arkusza
- wykrojniki nie mogą wyjść poza wewnętrzny obrys OPOS-ów
- celem algorytmu jest zmieścić jak najwięcej użytków na arkuszu

## Stan implementacji
Zrobione:
- utworzony katalog projektu `summa-cut/`
- utworzony szkielet aplikacji Python/PySide6
- założone lokalne środowisko `.venv`
- zainstalowane zależności `PySide6` i `PyMuPDF`
- utworzone pliki startowe:
  - `app.py`
  - `requirements.txt`
  - `run.sh`
  - `launch.sh`
- utworzony pakiet `summa_cut/`
- dodane podstawowe ustawienia w `settings.json`
- utworzone główne okno aplikacji
- działa wczytywanie PDF
- działa odczyt liczby stron i rozmiarów stron z PDF
- działa niezależny wybór:
  - pliku druku
  - strony druku
  - pliku wykrojnika
  - strony wykrojnika
- domyślnie po wczytaniu PDF ustawiane są:
  - strona 1 jako druk
  - strona 2 jako wykrojnik (jeśli istnieje)
- działa przycisk pobierania bounding boxa z wybranej strony druku do pól rozmiaru użytku
- do listy plików można przeciągać PDF-y metodą drag & drop
- działa usuwanie zaznaczonych plików z listy
- poprawiony błąd/mylące zachowanie, przez które interfejs sprawiał wrażenie, że druk i wykrojnik są domyślnie przypisywane tylko jako strona 1 i 2 jednego zestawu; wybory druku i wykrojnika są teraz niezależne i mają osobne opisy w GUI

## Stan GUI
Obecnie działa:
- lista wczytanych PDF-ów
- osobne comboboksy wyboru dla druku i wykrojnika
- pola arkusza
- pola rozmiaru użytku
- tryb odstępów / brak odstępów
- odstęp w mm
- obrót 90°
- podsumowanie po prawej stronie pokazujące aktualne wybory

Działa już także:
- liczenie prostego layoutu siatkowego z uwzględnieniem pola roboczego OPOS
- wybór lepszego wariantu 0° / 90° przy włączonym obrocie
- podgląd na żywo w zakładkach:
  - `Podgląd druku`
  - `Podgląd wykrojnika`
  - `Podgląd arkusza`
- generowanie stron wyjściowych w pamięci dla `druk.pdf` i `wykrojnik.pdf`
- zapis obu plików PDF do wybranego katalogu
- wydajność podglądu została poprawiona przez debounce odświeżania i wyłączenie `keyboardTracking` w polach liczbowych
- PDF wejściowy nie jest modyfikowany; program tylko osadza jego kopię w nowych plikach wyjściowych
- OPOS-y są generowane jako czarne prostokąty `2 × 2 mm`
- w trybie z odstępami:
  - wykrojnik pochodzi z wybranego PDF-a
  - układ działa jako kafel = `rozmiar użytku + odstęp`
  - oba PDF-y są przycinane/centrowane do wielkości tego kafla
- w trybie bez odstępów:
  - pole odstępu jest ukryte / nieaktywne
  - druk układa się na styk wg `rozmiaru użytku`
  - wykrojnik jest generowany automatycznie jako siatka pionowych i poziomych linii
  - linie wykrojnika wychodzą `1 mm` poza skrajny obrys siatki

Jeszcze nie działa / jest uproszczone:
- bardziej zaawansowany nesting niż prosty układ siatkowy
- bogatszy podgląd technologiczny niż podstawowy podgląd 2D
- brak dodatkowych ustawień technologicznych dla generowanego wykrojnika (np. grubość linii, inne warianty geometrii)

## Skrót uruchamiania
Projekt ma skrót na pulpicie:
- `/home/cyborg50/Desktop/summa-cut.desktop`
- `/home/cyborg50/Pulpit/summa-cut.desktop`

## Tryb specjalny — osobny prototyp
Powstał osobny szkielet prototypu `Tryb specjalny` do sprawdzenia trimowania druku do kształtu wykrojnika + spad.

Dodane pliki:
- `summa_cut/special_mode_window.py`
- `summa_cut/special_mode_main.py`
- `special_mode_app.py`
- `run-special-mode.sh`
- `launch-special-mode.sh`
- `SPECIAL_MODE.md`

Skrót uruchamiania na pulpicie:
- `/home/cyborg50/Desktop/summa-cut-special-mode.desktop`
- `/home/cyborg50/Pulpit/summa-cut-special-mode.desktop`

Obecny prototyp potrafi:
- wybrać jeden PDF wejściowy,
- pracować w założeniu: strona 1 = druk, strona 2 = wykrojnik,
- ustawić spad,
- wskazać katalog wynikowy,
- sprawdzić podstawowe informacje o wejściowym PDF-ie,
- wyciągnąć wektorowy obrys z 2. strony,
- pokazać przytrimowany podgląd druku,
- zapisać testowy PDF wektorowy z clipping path (bez zamiany całej strony na bitmapę).

## Checkpoint 2026-05-18
- zapisano paczkę instalacyjną Linux: `summa-cut-linux-source-2026-05-18.tar.gz`
- zapisano instrukcję instalacji: `INSTALL_SUMMA_CUT_LINUX.md`
- oba pliki zostały skopiowane na TrueNAS `dom` do katalogu:
  - `/srv/backup/`
- paczka jest źródłowa (bez lokalnego `.venv`) i nadaje się do odtworzenia środowiska na innym Linuxie

## Najbliższy następny krok
Najbardziej naturalny następny etap:
1. sprawdzić wynik PDF na realnym pliku Wojtka
2. dodać moduł montażu 2×2 na większym canvasie
3. dodać wybór 2 pionowe / 2 poziome oraz przesuwanie góra-dół / lewo-prawo
4. potraktować taki wzór jako bazę do późniejszego powielania w summa-cut

## Ważna uwaga na powrót
Przy powrocie do projektu zacząć od:
- przeczytania `summa-cut/STATUS.md`
- potem `summa-cut/SPEC.md`
- a następnie wrócić do `SPEC.md` i kontynuować od nowej, doprecyzowanej opcji
