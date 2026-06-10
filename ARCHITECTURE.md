# summa-cut — Architektura v1

## 1. Cel architektury

Architektura v1 ma być:
- prosta
- czytelna
- łatwa do rozwijania
- zgodna z podejściem użytym wcześniej w Banner-Eyelets

Technologia bazowa:
- Python
- PySide6
- PyMuPDF (`fitz`)

Założenie:
GUI, logika układania i eksport PDF nie powinny być ze sobą ciasno sklejone.

---

## 2. Proponowana struktura katalogów

```text
summa-cut/
  SPEC.md
  GUI.md
  ARCHITECTURE.md
  IMPLEMENTATION_PLAN.md
  app.py
  requirements.txt
  run.sh
  launch.sh
  settings.json
  summa_cut/
    __init__.py
    models.py
    units.py
    pdf_io.py
    layout.py
    opos.py
    export.py
    preview.py
    settings.py
    main_window.py
```

W v1 można zacząć nawet od mniejszej liczby plików, ale ten podział jest zdrowy i skalowalny.

---

## 3. Warstwy aplikacji

### 3.1. Warstwa GUI
Odpowiedzialność:
- okno główne
- formularze
- wybór plików i stron
- podgląd
- komunikaty błędów
- uruchamianie generowania layoutu i eksportu

Moduł:
- `main_window.py`

### 3.2. Warstwa modeli danych
Odpowiedzialność:
- przechowywanie parametrów zadania
- format arkusza
- parametry użytku
- ustawienia trybu pracy
- wynik obliczonego układu

Moduł:
- `models.py`

### 3.3. Warstwa PDF I/O
Odpowiedzialność:
- otwieranie PDF
- odczyt liczby stron
- odczyt bounding boxów
- render miniaturek do podglądu
- pobieranie stron źródłowych do eksportu

Moduł:
- `pdf_io.py`

### 3.4. Warstwa logiki układania
Odpowiedzialność:
- wyliczenie obszaru roboczego
- uwzględnienie OPOS-ów
- obliczenie ile użytków mieści się na arkuszu
- sprawdzenie wariantu bez obrotu i z obrotem 90°
- wybranie lepszego wariantu
- zwrócenie pozycji wszystkich użytków

Moduł:
- `layout.py`

### 3.5. Warstwa OPOS
Odpowiedzialność:
- definicja pozycji znaczników OPOS
- rysowanie znaczników OPOS do PDF-a
- wyznaczanie wewnętrznego obrysu pola roboczego

Moduł:
- `opos.py`

### 3.6. Warstwa eksportu
Odpowiedzialność:
- budowa `druk.pdf`
- budowa `wykrojnik.pdf`
- umieszczenie kopii stron na arkuszu w odpowiednich pozycjach
- dodanie OPOS-ów
- zapis plików końcowych

Moduł:
- `export.py`

### 3.7. Warstwa podglądu
Odpowiedzialność:
- generowanie uproszczonego podglądu 2D arkusza
- pokazanie obszaru roboczego, OPOS-ów i siatki użytków

Moduł:
- `preview.py`

### 3.8. Warstwa ustawień
Odpowiedzialność:
- zapis i odczyt ustawień użytkownika
- domyślne wartości formularza

Moduł:
- `settings.py`

---

## 4. Modele danych

## 4.1. InputPdf
Reprezentuje wczytany plik PDF.

Pola:
- `path`
- `name`
- `page_count`
- `page_sizes_mm`

## 4.2. SelectedPage
Reprezentuje wybraną stronę źródłową.

Pola:
- `pdf_path`
- `page_index`

## 4.3. SheetSpec
Opisuje arkusz wyjściowy.

Pola:
- `width_mm`
- `height_mm`

## 4.4. ItemSpec
Opisuje użytek.

Pola:
- `width_mm`
- `height_mm`
- `rotation_allowed`

## 4.5. JobSettings
Pełny zestaw ustawień zadania.

Pola:
- `print_page`
- `cut_page`
- `sheet_spec`
- `item_spec`
- `gap_enabled`
- `gap_mm`
- `auto_generate_cut_in_gapless_mode` (na razie tylko flaga pod przyszłość)

## 4.6. OposSpec
Opis położeń znaczników OPOS.

Pola:
- `left_offset_mm`
- `right_offset_mm`
- `bottom_offset_mm`
- `top_offset_mm`

Dla v1 wartości stałe:
- bok: `10`
- dół: `10`
- góra: `40`

## 4.7. Placement
Jedno umieszczenie użytku na arkuszu.

Pola:
- `x_mm`
- `y_mm`
- `width_mm`
- `height_mm`
- `rotation_deg`
- `row`
- `column`

## 4.8. LayoutResult
Wynik obliczeń układu.

Pola:
- `placements`
- `count`
- `rows`
- `columns`
- `used_rotation`
- `work_area_rect`
- `sheet_rect`

---

## 5. Przepływ danych

### Krok 1: Wczytanie PDF
GUI -> `pdf_io.py`
- otwarcie pliku
- pobranie liczby stron
- pobranie bounding boxów
- aktualizacja formularza

### Krok 2: Ustawienie parametrów
GUI buduje `JobSettings`

### Krok 3: Generowanie layoutu
GUI -> `layout.py`
- wyliczenie pola roboczego
- obliczenie wariantu 0°
- jeśli obrót dozwolony: obliczenie wariantu 90°
- wybór wariantu z większą liczbą użytków
- zwrot `LayoutResult`

### Krok 4: Podgląd
GUI -> `preview.py`
- render uproszczonego planu arkusza

### Krok 5: Eksport
GUI -> `export.py`
- utworzenie PDF druku
- utworzenie PDF wykrojnika
- osadzenie odpowiednich stron wejściowych w pozycjach `placements`
- dodanie OPOS-ów
- zapis plików

---

## 6. Algorytm layoutu v1

W v1 wystarczy prosty algorytm siatkowy.

### 6.1. Obliczenie pola roboczego
Na podstawie arkusza i OPOS-ów wyznaczamy prostokąt roboczy wewnątrz znaczników.

### 6.2. Ustalenie efektywnego rozmiaru użytku
Tryb z odstępami:
- szerokość efektywna = szerokość użytku + odstęp
- wysokość efektywna = wysokość użytku + odstęp

Tryb bez odstępów:
- szerokość efektywna = szerokość użytku
- wysokość efektywna = wysokość użytku

### 6.3. Liczenie siatki
Dla wariantu 0°:
- liczba kolumn = floor(dostępna_szerokość / efektywna_szerokość)
- liczba rzędów = floor(dostępna_wysokość / efektywna_wysokość)

Dla wariantu 90°:
- zamieniamy szerokość i wysokość użytku
- liczymy analogicznie

### 6.4. Wybór wariantu
Wybieramy wariant z większą liczbą użytków.
W przypadku remisu można preferować wariant bez obrotu.

---

## 7. Eksport PDF

Eksport powinien używać osadzania strony PDF jako obiektu na nowej stronie wynikowej, bez modyfikacji źródła.

Dla każdego `Placement`:
- wyznacz docelowy prostokąt na stronie wynikowej
- umieść stronę źródłową w tym prostokącie
- wycentruj ją w użytku
- zastosuj ewentualny obrót 90°

To samo dla pliku druku i wykrojnika, ale z różnymi wybranymi stronami źródłowymi.

---

## 8. Podgląd

Podgląd v1 nie musi być wiernym rendererem całego PDF.
Wystarczy podgląd schematyczny:
- obrys arkusza
- obszar roboczy
- OPOS-y
- prostokąty użytków
- oznaczenie orientacji

To uprości implementację i przyspieszy działanie.

---

## 9. Obsługa błędów

Aplikacja powinna czytelnie obsługiwać:
- nieprawidłowy PDF
- brak strony do druku lub wykrojnika
- zerowy lub ujemny wymiar
- brak miejsca na choćby jeden użytek
- błąd zapisu pliku wynikowego
- błąd renderowania / importu strony PDF

---

## 10. Rozszerzalność

Ten podział pozwoli później dodać:
- wiele projektów na jednym arkuszu
- lepszy nesting
- bardziej rozbudowane OPOS-y
- automatyczne generowanie wykrojnika
- raport produkcyjny
- presety materiałów i urządzeń
