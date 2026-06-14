# summa-cut

Impozytor PDF do **druku** i **wycinania na ploterze tnącym** (Summa, znaczniki OPOS). Z jednego lub kilku PDF-ów układa jak najwięcej użytków na arkuszu i generuje dwa zgodne pozycyjnie pliki:

- `druk.pdf` — strona drukowa powielona w układzie + OPOS-y
- `wykrojnik.pdf` — wykrojnik w tych samych pozycjach + OPOS-y

Program nie ingeruje w treść wejściowych PDF-ów — tylko je enkapsuluje, pozycjonuje, powiela, obraca, centruje w użytku i otacza elementami technicznymi.

Dostępny w dwóch wariantach z tej samej logiki:

- 🖥️ **Desktop** (PySide6 + PyMuPDF) — aplikacja okienkowa.
- 🌐 **Web** (FastAPI + PyMuPDF) — montaż i podgląd w przeglądarce.

**Demo:** https://summa.cyplos.pl

---

## Jak to działa

1. Wczytujesz PDF i wybierasz stronę **druku** oraz stronę **wykrojnika** (mogą pochodzić z jednego wielostronicowego pliku).
2. Ustawiasz format arkusza (domyślnie `330 × 480 mm`) i rozmiar użytku (domyślna propozycja z bounding boxa PDF-a).
3. Program liczy **maksymalną liczbę użytków**, buduje deterministyczny układ siatkowy i centruje PDF w każdym użytku.
4. Dodaje **4 znaczniki OPOS** w narożnikach; cała siatka mieści się w bezpiecznym polu wyznaczonym przez wewnętrzny obrys OPOS-ów.
5. Zapisujesz dwa zgodne pliki: `druk.pdf` i `wykrojnik.pdf`.

## Funkcje

- Wczytywanie PDF (jedno- i wielostronicowych), wybór strony druku i wykrojnika
- Format arkusza i rozmiar użytku zadawane ręcznie (z sensownymi domyślnymi)
- **Maksymalizacja liczby użytków** — prosty, przewidywalny układ siatkowy
- **Obrót 0° / 90°** (globalny) dla lepszego upakowania
- **Tryb z odstępami** — edytowalny odstęp między użytkami (domyślnie `3 mm`)
- **OPOS-y** Summa — 4 narożne znaczniki, układy ograniczone do pola roboczego
- Generowanie dwóch zgodnych pozycyjnie PDF-ów (`druk.pdf`, `wykrojnik.pdf`)
- **Tryb specjalny** (prototyp) — wykrojnik z rzeczywistego wektorowego obrysu strony, rozszerzenie o spad i przycięcie druku do kształtu (vector clipping path)
- Web: podgląd układu i podgląd PDF, pobieranie wyników

## Architektura

Czysta logika oddzielona od interfejsów (rdzeń bez zależności od Qt/FastAPI):

```
summa_cut/           # rdzeń + desktop (PySide6)
  models.py          #   typy danych (arkusz, użytek, layout)
  pdf_io.py          #   wczytywanie PDF, bounding boxy
  layout.py          #   algorytm układania (maks. liczba użytków, siatka, obrót)
  opos.py            #   znaczniki OPOS + pole robocze
  export.py          #   render druk.pdf / wykrojnik.pdf
  preview.py         #   podgląd układu
  special_trim.py    #   tryb specjalny: obrys + spad + clipping (shapely)
  main_window.py     #   GUI desktop
web/                 # interfejs web (FastAPI)
  app.py             #   punkt wejścia ASGI (uvicorn web.app:app)
  server.py          #   API: /api/upload, /api/job, /api/preview, /api/generate, /api/download
  job_builder.py     #   budowa zadania montażu z parametrów
  preview_render.py  #   render podglądów PNG
  sessions.py        #   sesje plikowe z TTL
  static/            #   index.html + app.js + style.css
tests/               # testy (pytest)
```

Szersze opisy: [`SPEC.md`](SPEC.md), [`ARCHITECTURE.md`](ARCHITECTURE.md), [`SPECIAL_MODE.md`](SPECIAL_MODE.md).

---

## Web

### Lokalnie

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-web.txt
uvicorn web.app:app --reload
```

Aplikacja: http://127.0.0.1:8000

### Docker

```bash
docker compose up --build
```

Domyślnie wystawia port `8800` → `8000` w kontenerze (zob. `compose.yaml`). Produkcyjnie działa jako TrueNAS Custom App za centralnym reverse proxy (Caddy + Let's Encrypt/Cloudflare DNS-01) pod `summa.cyplos.pl` — szczegóły w [`deploy/HTTPS-truenas-app.md`](deploy/HTTPS-truenas-app.md).

---

## Desktop

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Tryb specjalny (osobny prototyp): `python special_mode_app.py`. Instalacja na Linux: [`INSTALL_SUMMA_CUT_LINUX.md`](INSTALL_SUMMA_CUT_LINUX.md). Build Windows: katalog [`dist-windows/`](dist-windows).

---

## Testy

```bash
pip install -r requirements-dev.txt -r requirements-web.txt
pytest
```

## Stack

Python 3.12 · [PyMuPDF](https://pymupdf.readthedocs.io/) i [pikepdf](https://pikepdf.readthedocs.io/) (operacje na PDF) · [shapely](https://shapely.readthedocs.io/) (geometria obrysów) · [PySide6](https://doc.qt.io/qtforpython/) (desktop) · [FastAPI](https://fastapi.tiangolo.com/) + [Uvicorn](https://www.uvicorn.org/) (web)
