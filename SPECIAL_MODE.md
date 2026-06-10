# summa-cut — Tryb specjalny

## Cel

Osobny prototyp do sprawdzenia, czy da się:
- odczytać rzeczywisty kształt wykrojnika z PDF,
- dodać do niego spad (na start `+2 mm`),
- przyciąć druk do takiego kształtu,
- a dopiero potem włączyć to do głównego programu `summa-cut`.

## Dlaczego osobno

Ten wariant jest dużo trudniejszy niż obecny układ prostokątny:
- wymaga geometrii nieregularnych kształtów,
- offsetowania obrysu,
- trimowania do kształtu,
- i w przyszłości może prowadzić do nieregularnego nestingu.

Dlatego lepiej najpierw zrobić osobny, mały moduł testowy.

## Zakres obecnego szkieletu

Obecna wersja potrafi:
- wybrać jeden PDF wejściowy,
- przyjąć założenie:
  - strona 1 = druk,
  - strona 2 = wykrojnik,
- ustawić spad w mm,
- wybrać katalog wynikowy,
- sprawdzić podstawowe informacje o wejściowym PDF-ie,
- wyciągnąć wektorowy obrys z 2. strony PDF,
- zbudować prototypowy obrys rozszerzony o spad,
- pokazać przytrimowany podgląd druku,
- użyć wektorowego clipping path zamiast wkładania bitmapy do PDF.

## Checkpoint 2026-05-18

Obecny stan prototypu warto traktować jako zapisany punkt powrotu:
- działa osobne uruchamianie `Trybu specjalnego`,
- wejście jest oparte o jeden PDF (`strona 1 = druk`, `strona 2 = wykrojnik`),
- prototyp wyciąga wektorowy obrys z 2. strony,
- buduje rozszerzony obrys o spad,
- pokazuje przytrimowany podgląd,
- zapisuje testowy wynik jako wektorowy PDF z clipping path.

Ten checkpoint nie rozwiązuje jeszcze montażu wielokrotnego ani integracji z głównym `summa-cut`.

## Następny krok implementacyjny

1. sprawdzić prototyp PDF na realnych plikach Wojtka,
2. ocenić, czy sposób wyciągania obrysu wykrojnika jest wystarczająco wiarygodny,
3. zbudować moduł montażu 2×2 z przesuwaniem elementów,
4. dopiero potem myśleć o włączeniu tej logiki do głównego programu.
