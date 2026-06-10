# summa-cut — checkpoint 2026-05-18

## Główny program
- aplikacja desktopowa w Python / PySide6 / PyMuPDF działa w obecnym zakresie opisanym w `STATUS.md`
- główny workflow obejmuje wybór PDF druku i wykrojnika, podgląd live oraz eksport `druk.pdf` i `wykrojnik.pdf`
- istnieją dwa warianty pracy:
  - z odstępami (`użytek + odstęp`)
  - bez odstępów (automatycznie generowany wykrojnik jako siatka linii)

## Tryb specjalny
- osobny prototyp do trimowania druku do rzeczywistego kształtu wykrojnika + spad
- obecnie działa na modelu: 1 PDF wejściowy, strona 1 = druk, strona 2 = wykrojnik
- wynik zapisywany jest jako testowy PDF wektorowy z clipping path

## Paczka instalacyjna
- przygotowana paczka źródłowa Linux:
  - `summa-cut-linux-source-2026-05-18.tar.gz`
- przygotowana instrukcja:
  - `INSTALL_SUMMA_CUT_LINUX.md`
- kopia została zapisana na `dom` w katalogu:
  - `/srv/backup/`

## Najbliższy sensowny powrót
1. test `Trybu specjalnego` na realnych plikach
2. decyzja, czy obrys wykrojnika jest wystarczająco wiarygodny
3. moduł montażu `2x2` z przesuwaniem elementów
4. dopiero potem ewentualna integracja z głównym `summa-cut`
