# summa-cut — Makieta GUI v1

## 1. Założenia interfejsu

Interfejs ma być prosty, produkcyjny i szybki w użyciu.
Użytkownik powinien móc przejść od wczytania PDF do wygenerowania plików wynikowych bez zbędnych ekranów.

Preferowany układ:
- jedno główne okno
- lewy panel ustawień
- prawy panel podglądu i wyników obliczeń
- dolny pasek statusu

Technologia GUI:
- PySide6

---

## 2. Główne okno

### 2.1. Górny pasek akcji

Przyciski / akcje:
- `Otwórz PDF`
- `Dodaj PDF`
- `Wyczyść`
- `Generuj układ`
- `Zapisz druk PDF`
- `Zapisz wykrojnik PDF`
- `Zapisz oba`

Dodatkowo menu:
- `Plik`
- `Ustawienia`
- `Pomoc`

---

## 3. Lewy panel — Dane wejściowe i ustawienia

### 3.1. Sekcja: Pliki wejściowe

Widok listy plików:
- tabela / lista wczytanych PDF-ów
- kolumny:
  - nazwa pliku
  - liczba stron
  - rozmiar strony domyślnej

Akcje:
- dodaj plik
- usuń zaznaczony plik
- podgląd pierwszej strony

### 3.2. Sekcja: Wybór stron

Pola:
- `PDF źródłowy do druku` — lista rozwijana
- `Strona druku` — lista rozwijana / spinner
- `PDF źródłowy wykrojnika` — lista rozwijana
- `Strona wykrojnika` — lista rozwijana / spinner

Założenie v1:
- użytkownik wybiera dokładnie jedną stronę druku i jedną stronę wykrojnika

### 3.3. Sekcja: Format arkusza

Pola:
- `Szerokość arkusza (mm)` — default `330`
- `Wysokość arkusza (mm)` — default `480`

Opcjonalne przyciski szybkich presetów na później:
- na razie poza zakresem implementacji v1

### 3.4. Sekcja: Rozmiar użytku

Pola:
- `Szerokość użytku (mm)`
- `Wysokość użytku (mm)`

Przycisk:
- `Pobierz bounding box z PDF` — wypełnia pola domyślnym rozmiarem z PDF

Zasady:
- PDF jest centrowany w obrębie użytku

### 3.5. Sekcja: Tryb układania

Pola:
- `Tryb pracy`:
  - `Z odstępami`
  - `Bez odstępów`

- `Odstęp (mm)` — default `3`
  - aktywne tylko w trybie `Z odstępami`

### 3.6. Sekcja: Obrót

Pola:
- checkbox `Zezwól na obrót 90°`

Znaczenie:
- wyłączone: tylko 0°
- włączone: 0° lub 90°

### 3.7. Sekcja: OPOS

Pola informacyjne w v1:
- `Lewy dolny: 10 mm od lewej, 10 mm od dołu`
- `Prawy dolny: 10 mm od prawej, 10 mm od dołu`
- `Lewy górny: 10 mm od lewej, 40 mm od góry`
- `Prawy górny: 10 mm od prawej, 40 mm od góry`

Na razie bez edycji — wartości stałe dla v1.

---

## 4. Prawy panel — Podgląd i wynik układania

### 4.1. Zakładki podglądu

Zakładki:
- `Podgląd druku`
- `Podgląd wykrojnika`
- `Podgląd arkusza / siatki`

### 4.2. Podgląd arkusza

Widok powinien pokazywać:
- obrys arkusza
- obszar roboczy wewnątrz OPOS-ów
- pozycje OPOS-ów
- siatkę użytków
- orientację użytków
- numerację pozycji (opcjonalnie)

W v1 wystarczy uproszczony podgląd 2D.

### 4.3. Panel wyników obliczeń

Pola tylko do odczytu:
- `Liczba użytków na arkuszu`
- `Liczba kolumn`
- `Liczba rzędów`
- `Czy użyto obrotu` — tak / nie
- `Wykorzystanie arkusza (%)` — opcjonalne
- `Rozmiar obszaru roboczego (mm)`

---

## 5. Dolny pasek statusu

Powinien pokazywać:
- status wczytania PDF
- błędy walidacji
- status generowania układu
- status eksportu plików

Przykłady:
- `Wczytano 1 plik PDF`
- `Wybrano stronę 1 do druku i stronę 2 do wykrojnika`
- `Układ wygenerowany: 24 użytki`
- `Zapisano druk.pdf i wykrojnik.pdf`

---

## 6. Walidacja GUI

Program powinien blokować generowanie układu, jeśli:
- nie wybrano strony druku
- nie wybrano strony wykrojnika
- szerokość lub wysokość arkusza <= 0
- szerokość lub wysokość użytku <= 0
- odstęp < 0
- użytek nie mieści się w obszarze roboczym nawet raz

Komunikaty błędów powinny być jasne i produkcyjne.

---

## 7. Minimalny flow użytkownika

1. Użytkownik otwiera PDF
2. Wybiera stronę druku
3. Wybiera stronę wykrojnika
4. Ustawia format arkusza
5. Ustawia rozmiar użytku
6. Wybiera tryb z odstępami / bez odstępów
7. Opcjonalnie włącza obrót 90°
8. Klik `Generuj układ`
9. Ogląda wynik
10. Zapisuje `druk.pdf` i `wykrojnik.pdf`

---

## 8. Elementy odkładane na później

Poza zakresem GUI v1:
- mieszanie wielu różnych projektów na jednym arkuszu
- ręczne przesuwanie pojedynczych użytków
- zaawansowany nesting nieregularny
- definiowanie własnych presetów OPOS
- osobny edytor wykrojnika generowanego automatycznie
