# summa-cut — checkpoint 2026-05-19 — integracja trybu specjalnego

## Stan głównego programu
- główny `summa-cut` działa dalej w standardowym trybie wyboru PDF druku i wykrojnika, podglądu live oraz eksportu `druk.pdf` i `wykrojnik.pdf`
- zachowane są dotychczasowe tryby pracy:
  - z odstępami (`użytek + odstęp`)
  - bez odstępów (automatycznie generowany wykrojnik jako siatka linii)

## Integracja trybu specjalnego
- do głównego okna `summa-cut` został dodany przycisk **Tryb specjalny**
- przycisk pobiera aktualnie wybrane pliki i strony z głównego okna:
  - druk
  - wykrojnik
- po uruchomieniu przygotowywane są tymczasowe przytrimowane PDF-y trybu specjalnego
- otwiera się edytor montażu `2x2` oparty o **druk z nałożonym obrysem wykrojnika**
- po kliknięciu **Zakończ** główny `summa-cut` nie próbuje już interpretować wyniku jako prostego prostokątnego kafla

## Aktualna, działająca logika
- wynik z edytora specjalnego jest używany jako baza do wyliczenia pełnego układu na arkuszu
- układ nie jest już traktowany jako powielanie zamkniętego bloku `2x2`
- pełne rozmieszczenie jest liczone z rzeczywistego kroku / rytmu wynikającego z edytora
- dzięki temu zniknął problem z błędnie zawyżonym odstępem między dalszymi kolumnami
- obecny stan został przez Wojtka potwierdzony jako: **„jest ok”**

## Ważne pliki zmieniane przy tej integracji
- `summa_cut/main_window.py`
- `summa_cut/layout.py`
- `summa_cut/export.py`
- `summa_cut/models.py`
- `summa_cut/special_mode_window.py`

## Najbliższy sensowny powrót
1. przetestować aktualny stan na kilku realnych plikach produkcyjnych
2. sprawdzić, czy potrzebne jest osobne pole `spad` dla trybu specjalnego w głównym GUI
3. zdecydować, czy logikę pełnego wypełniania arkusza zostawić w głównym `summa-cut`, czy kiedyś całkiem przenieść ją do edytora specjalnego
4. dopiero potem rozwijać kolejne warianty montażu
