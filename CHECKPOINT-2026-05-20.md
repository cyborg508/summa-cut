# summa-cut — checkpoint 2026-05-20

Data: 2026-05-20

## Co obejmuje ten stan
- Przygotowany został lokalny szkic strony projektu pod GitHub Pages.
- Dodany katalog `docs/` z prostą statyczną stroną opisującą projekt.
- Dodany plik `docs/README_GITHUB_PAGES.md` z krótką instrukcją późniejszej publikacji.
- Strona zawiera sekcje: opis projektu, funkcje, status, najbliższe kroki i placeholder pod pobieranie wydań.

## Dodane pliki
- `docs/index.html`
- `docs/style.css`
- `docs/README_GITHUB_PAGES.md`

## Ważna uwaga o paczce Windows
- W paczce Windows skrypt `build_windows.ps1` znajduje się w katalogu `dist-windows/`, a nie w głównym katalogu projektu.
- To powoduje rozjazd względem wcześniejszej instrukcji uruchamiania z `C:\summa-cut\build_windows.ps1`.
- Doraźne obejście:
  - uruchamiać ręcznie komendę `pyinstaller` z katalogu głównego projektu,
  - albo skopiować `dist-windows/build_windows.ps1` do katalogu głównego przed uruchomieniem.

## Intencja tego checkpointu
To jest punkt powrotu po przygotowaniu materiałów pod publiczną prezentację projektu, ale jeszcze przed faktyczną publikacją repozytorium i strony na GitHubie.

## Sensowny następny krok
- dodać screenshoty programu do `docs/`
- przygotować porządne `README.md` pod repozytorium GitHub
- później dopiero opublikować repo i włączyć GitHub Pages z folderu `docs/`
