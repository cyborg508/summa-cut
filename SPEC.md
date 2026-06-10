# summa-cut — Specyfikacja v1

## 1. Cel programu

`summa-cut` to desktopowy program do przygotowania układu PDF do:
- druku
- wycinania na ploterze tnącym

Program generuje dwa pliki wyjściowe:
- `druk.pdf`
- `wykrojnik.pdf`

Program nie ingeruje w zawartość wejściowych PDF-ów. Może je tylko:
- enkapsulować w arkuszu wyjściowym
- pozycjonować
- powielać
- obracać
- centrować w zdefiniowanym użytku
- otaczać elementami technicznymi (np. OPOS)

---

## 2. Technologia bazowa

Punkt wyjścia technicznego z projektu Banner-Eyelets:
- język: Python
- GUI: PySide6
- PDF: PyMuPDF (`fitz`)

---

## 3. Wejście

Program ma umożliwiać wczytanie:
- jednego PDF-a lub kilku PDF-ów
- PDF-a jednostronicowego lub wielostronicowego

Zakres v1:
- użytkownik wybiera dokładnie 1 stronę do druku
- użytkownik wybiera dokładnie 1 stronę wykrojnika
- obie strony mogą pochodzić z wejściowego PDF-a wielostronicowego

Opcja mieszania wielu różnych projektów na jednym arkuszu:
- poza zakresem v1
- przewidziana do rozwinięcia później

---

## 4. Format wyjściowy

Domyślny format arkusza wyjściowego:
- `330 × 480 mm`

Użytkownik może ten format zmienić.

Program operuje na arkuszu prostokątnym o ręcznie zadanej szerokości i wysokości.

---

## 5. Rozmiar użytku

W v1 rozmiar użytku definiuje użytkownik.

Zasady:
- użytkownik podaje szerokość użytku
- użytkownik podaje wysokość użytku
- PDF jest centrowany w obrębie zdefiniowanego użytku
- domyślna propozycja rozmiaru użytku pochodzi z `bounding box` wejściowego PDF-a

Na razie program nie wyznacza automatycznie finalnego rozmiaru użytku z wykrojnika.

---

## 6. Obrót

Dopuszczalne orientacje użytku:
- `0°`
- `90°`

W v1 obrót działa globalnie:
- tryb bez obrotu
- tryb z dopuszczeniem obrotu 0/90 dla wszystkich kopii

Program nie miesza w jednym układzie niezależnych decyzji obrotu per pojedynczy użytek według złożonej heurystyki — celem v1 jest prosty, przewidywalny mechanizm maksymalizacji liczby użytków.

---

## 7. Tryby pracy

### 7.1. Tryb z odstępami

Tryb domyślny.

Parametry:
- odstęp domyślny: `3 mm`
- odstęp ma być edytowalny przez użytkownika

Zasady:
- wykrojnik pochodzi z dostarczonego PDF-a
- użytki są rozmieszczane z zadanym odstępem między sobą

### 7.2. Tryb bez odstępów

Zasady:
- brak odstępów między użytkami
- wykrojnik generuje program

Sposób generowania wykrojnika w tym trybie:
- poza zakresem obecnego doprecyzowania
- do ustalenia w kolejnej iteracji projektu

---

## 8. Cel algorytmu układania

Główny cel układania:
- zmieścić jak największą liczbę użytków na zadanym arkuszu

Priorytet optymalizacji:
1. maksymalna liczba użytków
2. dopiero później ewentualne dalsze optymalizacje

W v1 dopuszczalny jest prosty, deterministyczny algorytm układania w siatce.

---

## 9. OPOS-y

Program ma dodawać OPOS-y do obu plików wyjściowych:
- `druk.pdf`
- `wykrojnik.pdf`

Liczba OPOS-ów w v1:
- 4 sztuki
- po jednym w każdym rogu arkusza

### 9.1. Pozycje OPOS-ów

#### Dolne narożniki
- `10 mm` od dolnej krawędzi arkusza
- `10 mm` od lewej lub prawej pionowej krawędzi arkusza

#### Górne narożniki
- `40 mm` od górnej krawędzi arkusza
- `10 mm` od lewej lub prawej pionowej krawędzi arkusza

---

## 10. Ograniczenie pola roboczego

Wykrojniki nie mogą wystawać poza wewnętrzny obrys znaczników OPOS.

To oznacza, że program musi wyznaczyć bezpieczny obszar roboczy ograniczony przez wewnętrzny obrys czterech znaczników OPOS i tylko w tym obszarze rozmieszczać użytki.

W praktyce:
- cała siatka użytków musi mieścić się wewnątrz pola ograniczonego OPOS-ami
- żaden wykrojnik nie może przekroczyć tego obszaru

---

## 11. Wyjście

Program generuje dokładnie dwa pliki PDF:

1. `druk.pdf`
   - zawiera stronę drukową ułożoną w powtórzeniach
   - zawiera OPOS-y

2. `wykrojnik.pdf`
   - zawiera stronę wykrojnika ułożoną w tych samych pozycjach
   - zawiera OPOS-y

Układ obu plików musi być zgodny pozycją i orientacją.

---

## 12. Zachowanie programu w v1

Użytkownik ma móc:
- wczytać PDF
- wybrać stronę do druku
- wybrać stronę wykrojnika
- ustawić szerokość i wysokość arkusza
- ustawić szerokość i wysokość użytku
- wybrać tryb pracy: z odstępami / bez odstępów
- ustawić wielkość odstępu
- włączyć lub wyłączyć obrót 0/90
- wygenerować dwa pliki wynikowe

Program ma:
- policzyć maksymalną liczbę użytków
- zbudować layout
- wycentrować PDF w użytku
- dodać OPOS-y
- zapisać wynik jako dwa osobne PDF-y

---

## 13. Poza zakresem v1

Na później:
- mieszanie różnych projektów na jednym arkuszu
- automatyczne generowanie wykrojnika w trybie bez odstępów
- bardziej zaawansowany nesting niż prosty układ siatkowy
- niezależne decyzje obrotu per pojedynczy użytek
- dodatkowe reguły technologiczne, raporty i automatyzacje produkcyjne

---

## 14. Najbliższy następny krok

Po zatwierdzeniu tej specyfikacji kolejnym krokiem powinno być przygotowanie:
1. makiety GUI
2. architektury aplikacji
3. planu implementacji v1
