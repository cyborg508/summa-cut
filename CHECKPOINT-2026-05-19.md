# summa-cut — checkpoint 2026-05-19

## Główny program
- aplikacja desktopowa w Python / PySide6 / PyMuPDF działa w zakresie opisanym w `STATUS.md`
- główny workflow obejmuje wybór PDF druku i wykrojnika, podgląd live oraz eksport `druk.pdf` i `wykrojnik.pdf`
- istnieją dwa warianty pracy:
  - z odstępami (`użytek + odstęp`)
  - bez odstępów (automatycznie generowany wykrojnik jako siatka linii)

## Tryb specjalny
- działa osobny prototyp do trimowania druku do rzeczywistego kształtu wykrojnika + spad
- model wejścia pozostaje taki sam:
  - 1 PDF wejściowy
  - strona 1 = druk
  - strona 2 = wykrojnik
- prototyp potrafi:
  - wyciągnąć wektorowy obrys z 2. strony PDF
  - zbudować obrys rozszerzony o spad
  - zapisać przytrimowany druk i wykrojnik jako tymczasowe PDF-y wektorowe
  - otworzyć edytor montażu `2x2`
  - zapisać wynikowy PDF 2-stronicowy (`druk` + `wykrojnik`)
- ważna zmiana w aktualnym stanie:
  - edytor montażu `2x2` pracuje już nie na samym obrysie, tylko na **stronie druku z nałożonym obrysem wykrojnika**
  - ten sam typ podglądu jest widoczny także w głównym oknie `Trybu specjalnego`

## Najbliższy sensowny powrót
1. przetestować `Tryb specjalny` na realnym pliku Wojtka
2. ocenić, czy obrys wykrojnika jest dobrze wykrywany i czy overlay jest wystarczająco czytelny
3. ewentualnie poprawić widoczność obrysu w podglądzie
4. dopiero potem rozwijać dalej logikę montażu
