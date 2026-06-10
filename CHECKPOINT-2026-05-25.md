# Checkpoint 2026-05-25

Stan zapisany jako punkt powrotu kodu projektu `summa-cut`.

## Najważniejsze zmiany w tym stanie

- OPOS-y:
  - bazowe narożne OPOS-y zostały zachowane,
  - dodatkowe OPOS-y są teraz generowane tylko w pionie,
  - jeśli odległość pionowa przekracza `500 mm`, wstawiane są dodatkowe znaczniki z równym podziałem odstępów.

- Tryb specjalny:
  - edytor ma jeden przycisk `Zakończ` po prawej stronie,
  - stan edytora trybu specjalnego zapisuje się do ustawień,
  - po ponownym wejściu można wrócić do zapisanych przesunięć i dalej je poprawiać,
  - poprawiona została blokada ponownego wejścia do edytora po wcześniejszym użyciu trybu specjalnego.

- Materiały Windows:
  - przygotowana świeża paczka źródłowa Windows i instrukcja builda,
  - kopia została zapisana na `dom` w `/srv/backup/summa-cut-windows/`.

## Uwagi

- Do commita nie powinien trafiać sesyjny stan `settings.json` wskazujący na tymczasowe pliki `/tmp/...`.
- Ten checkpoint ma służyć jako bezpieczny punkt powrotu do bieżącego stanu kodu.
