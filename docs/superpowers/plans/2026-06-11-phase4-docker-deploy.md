# Phase 4 — Konteneryzacja + deploy na drukpolu — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chudy, bezgłowy obraz Docker z web-aplikacją summa-cut i uruchomienie go jako usługi na drukpolu (TrueNAS SCALE), dostępnej tylko z LAN drukpol + przez Tailscale, bez publicznego wystawienia, bez logowania.

**Architecture:** Obraz `python:3.12-slim` instaluje TYLKO zależności runtime (FastAPI/uvicorn/python-multipart/PyMuPDF/pikepdf — bez PySide6, bez pytest), kopiuje `summa_cut/` + `web/` i startuje `uvicorn web.app:app` na 0.0.0.0:8000. Compose uruchamia kontener z `restart: unless-stopped`, mapuje port hosta i montuje wolumen na katalog sesji. Build i uruchomienie odbywają się NA drukpolu (na stacji nie ma Dockera). Środowisko drukpola potwierdzone recon: TrueNAS SCALE 25.10.3.1, Docker 28.3.1, Compose v2.38.1, SSH root key-auth (Tailscale REDACTED-HOST).

**Tech Stack:** Docker + Compose (na drukpolu), python:3.12-slim, uvicorn, rsync/SSH przez Tailscale.

---

## File Structure

```
Dockerfile             # chudy obraz bezgłowy: runtime deps + summa_cut/ + web/ → uvicorn
.dockerignore          # wykluczenia z kontekstu budowania (.venv, .git, tests, docs…)
compose.yaml           # usługa summa-cut-web: build, port, wolumen, restart
requirements-web.txt   # ROZSZERZONE: pełny zestaw runtime (dodaj PyMuPDF + pikepdf)
docs/DEPLOY-drukpol.md # runbook wdrożenia/aktualizacji na drukpolu
tests/test_web_no_qt.py # guard: web.app importuje się BEZ PySide6 (gwarancja chudego obrazu)
```

Reguła: kod aplikacji bez zmian. Faza 4 dokłada wyłącznie artefakty pakowania/wdrożenia + jeden test-strażnik.

---

## Task 1: Artefakty kontenera + strażnik „bez Qt"

**Files:**
- Modify: `requirements-web.txt`
- Create: `Dockerfile`, `.dockerignore`, `compose.yaml`, `tests/test_web_no_qt.py`
- Test: `tests/test_web_no_qt.py`

- [ ] **Step 1: Napisać test-strażnik (web.app bez PySide6)**

Utwórz `tests/test_web_no_qt.py`:
```python
"""Strażnik chudego obrazu: web.app musi się importować BEZ PySide6.

W kontenerze nie instalujemy Qt. Test symuluje to, blokując import PySide6
w podprocesie i importując web.app — jeśli cokolwiek w ścieżce web → rdzeń
sięgnie po Qt, import padnie."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def test_web_app_imports_without_pyside6():
    code = (
        "import sys;"
        "sys.modules['PySide6'] = None;"   # każdy `import PySide6` → ImportError
        "import web.app;"
        "print('OK')"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=str(REPO))
    assert r.returncode == 0, f"web.app nie zaimportował się bez PySide6:\n{r.stderr}"
    assert "OK" in r.stdout
```

- [ ] **Step 2: Uruchomić — PASS (już teraz, web jest Qt-free)**

Run: `cd ~/summa-cut && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_web_no_qt.py -q`
Expected: 1 passed. (To test-charakteryzacja istniejącej własności — chroni ją przed regresją w obrazie.)

- [ ] **Step 3: Rozszerzyć `requirements-web.txt` do pełnego runtime**

Zastąp całą treść `requirements-web.txt`:
```
fastapi>=0.110
uvicorn[standard]>=0.29
python-multipart>=0.0.9
PyMuPDF>=1.24
pikepdf>=9
```
(To jest komplet zależności potrzebnych do URUCHOMIENIA web-appki — bez PySide6 i bez narzędzi testowych. `requirements.txt` zostaje dla developmentu desktopu+testów.)

- [ ] **Step 4: Utworzyć `Dockerfile`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

COPY requirements-web.txt .
RUN pip install -r requirements-web.txt

COPY summa_cut/ ./summa_cut/
COPY web/ ./web/

EXPOSE 8000
CMD ["uvicorn", "web.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 5: Utworzyć `.dockerignore`**

```
.venv
.git
.gitignore
__pycache__
*.pyc
.pytest_cache
tests
docs
*.desktop
build
dist
*.md
app.py
special_mode_app.py
```
(Wykluczamy desktop (`app.py`/`special_mode_app.py`), testy, docs, .venv — obraz bierze tylko `summa_cut/` + `web/` + `requirements-web.txt`. Uwaga: `summa_cut/` zawiera moduły Qt — `preview.py`, `main_window.py`, `special_mode_window.py` — ale web ich nie importuje, więc są nieszkodliwym balastem; nie wykluczamy ich, bo `summa_cut/` kopiujemy w całości dla prostoty.)

- [ ] **Step 6: Utworzyć `compose.yaml`**

```yaml
services:
  summa-cut-web:
    build: .
    image: summa-cut-web:latest
    container_name: summa-cut-web
    restart: unless-stopped
    ports:
      - "8800:8000"
    volumes:
      - summa-cut-data:/tmp/summa-cut-web

volumes:
  summa-cut-data:
```
(Port hosta **8800** → 8000 w kontenerze, by nie kolidować z UI TrueNAS 80/443. Wolumen `summa-cut-data` montowany na `/tmp/summa-cut-web` = baza katalogu sesji z `web/app.py` — trwały między restartami, nie zaśmieca warstwy zapisu kontenera. Nasłuch 0.0.0.0 w kontenerze → reachable na wszystkich interfejsach hosta, w tym Tailscale; brak publicznego forwardu na drukpolu = nie wystawione na świat, zgodnie ze specem.)

- [ ] **Step 7: Walidacja artefaktów lokalnie (bez Dockera)**

Run:
```bash
cd ~/summa-cut && .venv/bin/python -c "
import yaml
c = yaml.safe_load(open('compose.yaml'))
svc = c['services']['summa-cut-web']
assert svc['ports'] == ['8800:8000'], svc['ports']
assert svc['restart'] == 'unless-stopped'
req = open('requirements-web.txt').read()
assert 'PySide6' not in req and 'PyMuPDF' in req and 'pikepdf' in req and 'fastapi' in req
df = open('Dockerfile').read()
assert 'web.app:app' in df and 'requirements-web.txt' in df and 'PySide6' not in df
print('artefakty OK')
"
```
Expected: `artefakty OK`. (PyYAML jest zależnością pośrednią uvicorn[standard]; gdyby brakło: `.venv/bin/pip install pyyaml`.)

- [ ] **Step 8: Pełny zestaw testów**

Run: `cd ~/summa-cut && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -q`
Expected: wszystkie passed (52 + 1 nowy = 53).

- [ ] **Step 9: Commit**

```bash
cd ~/summa-cut
git add Dockerfile .dockerignore compose.yaml requirements-web.txt tests/test_web_no_qt.py
git commit -m "feat(deploy): Dockerfile + compose (chudy bezgłowy obraz web) + strażnik bez-Qt"
```

---

## Task 2: Runbook wdrożenia na drukpolu (`docs/DEPLOY-drukpol.md`)

**Files:**
- Create: `docs/DEPLOY-drukpol.md`

Ten task tworzy dokument; **samo wdrożenie wykonuje prowadzący na żywo** (akcja na produkcyjnym serwerze offsite — patrz sekcja „Wykonanie" niżej, poza krokami pliku).

- [ ] **Step 1: Utworzyć `docs/DEPLOY-drukpol.md`**

````markdown
# Deploy summa-cut web na drukpolu (TrueNAS SCALE)

Środowisko: drukpol = TrueNAS SCALE 25.10, Docker 28.3 + Compose v2.38, dostęp
SSH root key-auth przez Tailscale (REDACTED-HOST). Aplikacja nasłuchuje na
porcie hosta **8800**, dostępna z LAN drukpol i przez Tailscale, bez publicznego
wystawienia, bez logowania (sieć zaufana).

## Pierwsze wdrożenie

1. Recon (gdzie docker trzyma dane, czy port wolny, dataset na kod):
   ```bash
   ssh root@REDACTED-HOST 'docker info | grep "Docker Root Dir"; ss -ltn | grep :8800 || echo "8800 wolny"; ls -d /mnt/*/ 2>/dev/null'
   ```
   Wybierz katalog na kod na puli danych, np. `/mnt/<pula>/apps/summa-cut`
   (nie /root — boot-pool bywa kasowany przy aktualizacji systemu).

2. Wgraj repo (bez .venv/.git) na drukpol:
   ```bash
   rsync -az --delete \
     --exclude .venv --exclude .git --exclude __pycache__ --exclude '*.pyc' \
     ~/summa-cut/ root@REDACTED-HOST:/mnt/<pula>/apps/summa-cut/
   ```

3. Build + start:
   ```bash
   ssh root@REDACTED-HOST 'cd /mnt/<pula>/apps/summa-cut && docker compose up -d --build'
   ```

4. Weryfikacja na drukpolu i przez Tailscale:
   ```bash
   ssh root@REDACTED-HOST 'curl -s -o /dev/null -w "lokalnie %{http_code}\n" http://localhost:8800/'
   curl -s -o /dev/null -w "tailscale %{http_code}\n" http://REDACTED-HOST:8800/
   ssh root@REDACTED-HOST 'docker compose -f /mnt/<pula>/apps/summa-cut/compose.yaml logs --tail=20'
   ```
   Oczekiwane: `200` w obu. Adres LAN drukpola: `ssh root@REDACTED-HOST "ip -4 addr show | grep -oP \"(?<=inet )192\\.168\\.[0-9.]+\""`.

## Aktualizacja (po zmianach w repo)

```bash
rsync -az --delete --exclude .venv --exclude .git --exclude __pycache__ \
  ~/summa-cut/ root@REDACTED-HOST:/mnt/<pula>/apps/summa-cut/
ssh root@REDACTED-HOST 'cd /mnt/<pula>/apps/summa-cut && docker compose up -d --build'
```

## Zatrzymanie / usunięcie

```bash
ssh root@REDACTED-HOST 'cd /mnt/<pula>/apps/summa-cut && docker compose down'        # stop
ssh root@REDACTED-HOST 'cd /mnt/<pula>/apps/summa-cut && docker compose down -v'     # + usuń wolumen sesji
```

## Uwagi
- Brak logowania jest świadomy (sieć zaufana). NIE forwardować portu 8800 na świat.
- Sesje wygasają po 6 h (sweeper w lifespanie); wolumen `summa-cut-data` to bufor /tmp.
- Gdyby `pip install` PyMuPDF/pikepdf padł na slim (brak wheela) — dołożyć w Dockerfile
  `RUN apt-get update && apt-get install -y --no-install-recommends libgl1 && rm -rf /var/lib/apt/lists/*` (zwykle niepotrzebne, wheele są samowystarczalne).
````

- [ ] **Step 2: Commit**

```bash
cd ~/summa-cut
git add docs/DEPLOY-drukpol.md
git commit -m "docs(deploy): runbook wdrożenia summa-cut web na drukpolu"
```

---

## Wykonanie wdrożenia (poza krokami plików — robi prowadzący, na żywo)

Po scaleniu Task 1+2 prowadzący wykonuje runbook NA drukpolu, podejmując na bieżąco
decyzje zależne od stanu serwera (ścieżka datasetu, brak kolizji portu). To akcja
na produkcyjnym serwerze — wykonywać świadomie, weryfikować każdy krok, nie
delegować w ciemno. Blast radius mały i odwracalny (`docker compose down`), nie
dotyka ZFS/backupów.

---

## Self-Review (autor planu)

**Pokrycie specu (sekcja 7 Deployment):** chudy obraz slim + runtime deps bez Qt ✔ (Dockerfile + rozszerzony requirements-web.txt + strażnik test); compose jako usługa, restart unless-stopped, wolumen sesji ✔; nasłuch na porcie hosta, dostęp LAN+Tailscale, bez publicznego wystawienia, bez TLS/loginu ✔ (compose 8800:8000 + runbook); aktualizacje = rebuild+recreate ✔ (runbook). Build na drukpolu (brak Dockera lokalnie) ✔.

**Placeholdery:** w plikach repo brak. `/mnt/<pula>/...` w runbooku to świadomy parametr rozwiązywany recon-em na żywo (krok 1) — runbook ops, nie kod; ścieżka zależy od układu pul drukpola, którego nie znamy bez recon.

**Spójność:** port 8800:8000 spójny w compose i runbooku; `web.app:app` spójne z Dockerfile CMD i istniejącym `web/app.py`; wolumen montowany na `/tmp/summa-cut-web` = `tempfile.gettempdir()/"summa-cut-web"` z `web/app.py`; requirements-web.txt = dokładnie deps importowane przez `web/` + rdzeń (fastapi/uvicorn/multipart/fitz/pikepdf).

**Ryzyko:** (1) wheele PyMuPDF/pikepdf na slim — zwykle OK (manylinux, samowystarczalne); fallback w runbooku. (2) docker root dir na boot-pool vs pula danych — recon krok 1 to ujawnia; kod kładziemy na puli. (3) nasłuch 0.0.0.0 — bezpieczne tylko bez publicznego forwardu (drukpol go nie ma); udokumentowane.
```
