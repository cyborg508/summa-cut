# summa-cut — Plan implementacji v1

## Etap 1 — Szkielet projektu

Cel:
- przygotować bazę projektu do dalszej pracy

Zadania:
- utworzyć `app.py`
- utworzyć pakiet `summa_cut/`
- przenieść podstawową konfigurację aplikacji do osobnych modułów
- przygotować `requirements.txt`
- przygotować `run.sh` / `launch.sh`
- przygotować prosty mechanizm `settings.json`

Rezultat:
- aplikacja uruchamia się jako puste okno PySide6

---

## Etap 2 — Wczytywanie PDF

Cel:
- umożliwić wybór PDF i odczyt podstawowych informacji

Zadania:
- dodać otwieranie plików PDF
- odczytać liczbę stron
- odczytać bounding box / rozmiar stron
- pokazać listę plików w GUI
- umożliwić wybór strony druku i strony wykrojnika

Rezultat:
- użytkownik może wskazać źródła do druku i cięcia

---

## Etap 3 — Formularz parametrów

Cel:
- umożliwić ustawienie parametrów layoutu

Zadania:
- pola rozmiaru arkusza
- pola rozmiaru użytku
- tryb z odstępami / bez odstępów
- pole odstępu
- checkbox obrotu 90°
- akcja `Pobierz bounding box z PDF`
- walidacja podstawowych danych wejściowych

Rezultat:
- użytkownik może zdefiniować zadanie produkcyjne

---

## Etap 4 — Logika OPOS i pola roboczego

Cel:
- policzyć bezpieczny obszar pracy

Zadania:
- zakodować stałe pozycje OPOS-ów
- wyznaczyć wewnętrzny prostokąt roboczy
- dodać test, czy użytek mieści się w polu roboczym

Rezultat:
- aplikacja zna rzeczywiste ograniczenie layoutu

---

## Etap 5 — Algorytm układania v1

Cel:
- policzyć maksymalną liczbę użytków na arkuszu

Zadania:
- zaimplementować wariant 0°
- zaimplementować wariant 90°
- porównać wyniki
- wybrać lepszy wariant
- wygenerować listę `placements`
- policzyć liczbę rzędów i kolumn

Rezultat:
- aplikacja potrafi obliczyć layout

---

## Etap 6 — Podgląd układu

Cel:
- użytkownik widzi, co program policzył

Zadania:
- narysować arkusz
- narysować OPOS-y
- narysować pole robocze
- narysować prostokąty użytków
- pokazać podstawowe statystyki układu

Rezultat:
- użytkownik dostaje czytelny wizualny podgląd

---

## Etap 7 — Eksport PDF

Cel:
- wygenerować finalne pliki produkcyjne

Zadania:
- stworzyć `druk.pdf`
- stworzyć `wykrojnik.pdf`
- osadzić stronę źródłową w każdej pozycji layoutu
- zastosować centrowanie
- zastosować obrót 0/90
- dodać OPOS-y
- zapisać oba pliki

Rezultat:
- program tworzy gotowe dwa PDF-y

---

## Etap 8 — Dopracowanie produkcyjne v1

Cel:
- zrobić wersję używalną, nie tylko działającą

Zadania:
- poprawić komunikaty błędów
- dopracować domyślne wartości
- dodać zapamiętywanie ustawień
- poprawić ergonomię GUI
- sprawdzić działanie na realnych PDF-ach

Rezultat:
- pierwsza praktyczna wersja robocza programu

---

## Etap 9 — Test na realnym pliku

Cel:
- potwierdzić, że v1 działa w praktyce

Zadania:
- wczytać realny PDF produkcyjny
- sprawdzić wybór stron
- sprawdzić wyliczenie liczby użytków
- wygenerować oba pliki
- wizualnie potwierdzić zgodność położeń druku i wykrojnika

Rezultat:
- potwierdzona wersja v1 na rzeczywistym materiale

---

## Rekomendowana kolejność pracy teraz

1. zbudować szkielet aplikacji
2. uruchomić GUI z formularzem
3. dodać wczytywanie PDF
4. dodać layout
5. dodać eksport PDF
6. dopiero potem dopieszczać podgląd i ergonomię
