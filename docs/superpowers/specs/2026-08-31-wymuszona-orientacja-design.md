# Wymuszona orientacja użytku (0° / 90°) — spec

Data: 2026-08-31
Zakres: tryb automatyczny w aplikacji webowej (summa.cyplos.pl)

## Problem

W trybie automatycznym `compute_layout` liczy wariant 0° i (gdy `rotation_allowed`)
wariant 90°, po czym wybiera ten z większą liczbą użytków; przy remisie wygrywa 0°
(`max(variants, key=lambda v: (v[0], -v[5]))`).

Nie da się kazać silnikowi użyć orientacji 90°, jeśli 0° daje więcej użytków.
Jest to potrzebne, gdy o orientacji decyduje coś spoza upakowania — kierunek włókien
papieru albo kierunek cięcia na ploterze.

## Kluczowa obserwacja

Dzisiejszy checkbox „pozwól obrót 90°" to już dwa z trzech potrzebnych stanów:

| checkbox | znaczenie |
|---|---|
| zaznaczony | próbuj 0° i 90°, wygrywa więcej użytków → **Auto** |
| odznaczony | używaj tylko 0° → **Wymuś 0°** |

Lista trzyopcyjna jest więc czystym nadzbiorem obecnego zachowania. Dokładamy
wyłącznie brakujący trzeci stan; nic nie wymaga migracji.

## Rozwiązanie

### Silnik

`ItemSpec` dostaje `forced_rotation_deg: int | None = None`.

W `compute_layout` budowa listy `dims`:

- `None` → jak dziś (0°, plus 90° gdy `rotation_allowed` i wymiary różne),
- `0` → wyłącznie wariant 0°,
- `90` → wyłącznie wariant 90°.

Reszta funkcji nietknięta, więc wymuszenie działa także przy `split_horizontal_groups`
i `manual_grid_enabled` — to ta sama pętla po `dims`.

Domyślne `None` znaczy „zachowuj się jak dziś", więc desktop Qt i `settings.json`
działają bez zmian.

### Decyzje szczegółowe

**Kwadratowy użytek.** Przy `forced_rotation_deg=90` i `width == height` obrót nie
zmienia geometrii kafla, ale grafika w środku nie musi być symetryczna. Wariant 90°
jest generowany mimo to, a `used_rotation` wychodzi `True`. Zamierzone — inaczej
wymuszenie po cichu nic by nie robiło.

**Orientacja się nie mieści.** Brak cichego fallbacku na drugą orientację — byłoby to
sprzeczne ze słowem „wymuś". Layout zwraca 0 użytków, a front pokazuje komunikat
„Wymuszona orientacja nie mieści się na arkuszu", żeby nie wyglądało to na awarię.

### API webowe

`JobParams` dostaje `rotation_mode: Literal["auto", "0", "90"] = "auto"`.
Mapowanie w `_build_job`:

| `rotation_mode` | `ItemSpec` |
|---|---|
| `auto` | `rotation_allowed=True`, `forced_rotation_deg=None` |
| `0` | `forced_rotation_deg=0` |
| `90` | `forced_rotation_deg=90` |

Pole `rotation_allowed` zostaje jako fallback dla klientów, które nie wysyłają
`rotation_mode` (zgodność wsteczna).

### Front

`<input type="checkbox" id="rotation">` → `<select id="rotation-mode">` z opcjami
Auto / Wymuś 0° / Wymuś 90°. **Id `rotation` zostaje** na jakimś elemencie kontraktu
lub kontrakt id-ów zostaje zaktualizowany — patrz testy.

Podsumowanie pod podglądem: `„· obrót 90°"` dostaje dopisek `(wymuszony)`, gdy obrót
wynika z wyboru użytkownika, a nie z decyzji silnika.

Bump `?v=9`.

## Poza zakresem

- tryb manualny (ma obrót per użytek klawiszem R),
- tryb specjalny (rotacja świadomie wyłączona, `rotation_allowed=False`),
- desktop Qt (zachowanie bez zmian dzięki domyślnemu `None`).

## Testy

1. wymuszone 90° wygrywa, choć 0° daje więcej użytków,
2. wymuszone 0° ignoruje lepszy wariant 90°,
3. wymuszone 90° na kwadracie → `used_rotation=True`, liczba jak przy 0°,
4. wymuszona orientacja się nie mieści → 0 użytków, bez fallbacku,
5. `rotation_mode` mapuje się na `ItemSpec` (trzy warianty),
6. brak `rotation_mode` → zachowanie jak dziś (regresja),
7. kontrakt id-ów frontu.

## Wdrożenie

`.venv/bin/python -m pytest` → rsync (`--exclude .claude`) → `docker build -t
summa-cut-web:local` → `midclt call app.redeploy summa-cut` → dual-push.
