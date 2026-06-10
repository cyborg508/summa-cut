summa-cut — jak zrobić przenośną wersję na Windows

Cel
- zbudować plik EXE, który da się uruchamiać na Windows bez instalowania Pythona i bibliotek na komputerze docelowym

Najprostsza i najpewniejsza metoda
- build zrobić na komputerze z Windows
- do buildu Python jest potrzebny tylko na czas tworzenia EXE
- po zbudowaniu docelowy komputer nie potrzebuje już dodatkowego oprogramowania

Co jest w tej paczce
- source ZIP projektu
- skrypt build_windows.ps1
- requirements.txt

Krok po kroku

1. Rozpakuj ZIP np. do katalogu:
   C:\summa-cut

2. Zainstaluj Python dla Windows (najlepiej 3.12 x64)
   Ważne:
   - podczas instalacji zaznacz "Add Python to PATH"

3. Otwórz PowerShell w katalogu projektu, np.:
   cd C:\summa-cut

4. Utwórz środowisko i zainstaluj zależności:
   py -3.12 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   pip install pyinstaller

5. Uruchom build:
   powershell -ExecutionPolicy Bypass -File .\build_windows.ps1

6. Gotowy program będzie tutaj:
   dist\summa-cut\summa-cut.exe

Jak przenieść na inny komputer
- skopiuj cały katalog:
  dist\summa-cut\
- na komputerze docelowym uruchamiasz:
  summa-cut.exe
- nic więcej nie trzeba instalować

Ważne uwagi
- Nie przenoś samego EXE bez reszty plików z katalogu dist\summa-cut, jeśli build jest zrobiony w trybie onedir.
- Jeśli chcesz jednego EXE zamiast katalogu, można przerobić build na --onefile, ale dla aplikacji PySide6 zwykle wygodniejszy i stabilniejszy jest tryb katalogowy.
- Build najlepiej robić na Windows 10 lub 11 x64.

Jeśli PowerShell blokuje skrypt
- użyj dokładnie:
  powershell -ExecutionPolicy Bypass -File .\build_windows.ps1

Jeśli chcesz później ikonę, instalator albo skrót na pulpit
- to też można dodać w kolejnym kroku.
