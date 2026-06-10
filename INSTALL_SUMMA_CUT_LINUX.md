# Summa Cut — instalacja na Linux (Mint/Ubuntu)

## Zawartość paczki
- kod źródłowy programu `summa-cut`
- skrypty uruchomieniowe `run.sh`, `launch.sh`
- plik `requirements.txt`
- dokumentacja projektu

## Wymagania
- Python 3.10+ (zalecane 3.12)
- dostęp do terminala
- środowisko graficzne X11 lub Wayland

## Instalacja
1. Rozpakuj paczkę:
   ```bash
   tar -xzf summa-cut-linux-source-2026-05-18.tar.gz
   cd summa-cut
   ```
2. Załóż środowisko wirtualne:
   ```bash
   python3 -m venv .venv
   ```
3. Aktywuj środowisko:
   ```bash
   source .venv/bin/activate
   ```
4. Zainstaluj zależności:
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

## Uruchamianie
- zwykłe uruchomienie:
  ```bash
  ./run.sh
  ```
- uruchomienie z logiem do `~/.summa-cut.log`:
  ```bash
  ./launch.sh
  ```

## Uwagi
- Program używa bibliotek `PySide6` i `PyMuPDF`.
- Jeżeli system nie ma pakietu `python3-venv`, doinstaluj go wcześniej.
- W razie problemów z Wayland/X11 użyj skryptu `launch.sh`, który ustawia `QT_QPA_PLATFORM="wayland;xcb"`.
- Ustawienia programu zapisują się w `settings.json` w katalogu projektu.
