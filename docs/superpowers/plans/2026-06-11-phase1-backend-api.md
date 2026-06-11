# Phase 1 — Backend API (FastAPI, headless) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bezgłowe API HTTP (FastAPI) opakowujące istniejący silnik summa-cut: sesja, upload PDF, ustawienie zlecenia, podgląd PNG, generowanie i pobranie wynikowych PDF — w pełni otestowane `TestClient`-em, bez PySide6.

**Architecture:** Nowy pakiet `web/` reużywa rdzeń `summa_cut/` (layout/opos/export/models/pdf_io — potwierdzone Qt-free). Podgląd renderuje **prawdziwy wynik** (`generate_output_docs`, po Fazie 0 ~0,24 s) zrasteryzowany do PNG przez `fitz.Pixmap` — bez Qt-owego `summa_cut/preview.py`. Stan trzymany per-sesja (ciasteczko `sid` + katalog roboczy w tempie, TTL). Zakres: pojedynczy produkt z trybami siatki (split/max_spread/manual_grid/krata-bez-odstępów) + OPOS. Montaż wielu użytków i tryb specjalny dochodzą w późniejszych fazach (builder zaprojektowany pod rozszerzenie).

**Tech Stack:** Python, FastAPI + uvicorn, python-multipart (upload), PyMuPDF (render PNG), pikepdf (przez `export`), pytest + `fastapi.testclient.TestClient` (httpx).

---

## File Structure

```
web/
  __init__.py
  sessions.py        # Session (dataclass) + SessionStore: pamięć + workdir + TTL + sweep
  job_builder.py     # JobParams (pydantic) + build_job(params, session) -> JobSettings (+walidacja)
  preview_render.py  # render_output_png(job, layout, which, max_px) -> bytes  (fitz pixmap; Qt-free)
  server.py          # create_app(store) -> FastAPI; trasy: session/upload/job/preview/generate/download
requirements-web.txt # fastapi, uvicorn[standard], python-multipart  (obraz web — BEZ PySide6)
requirements.txt     # + httpx (dep testowa TestClient)
tests/
  test_web_sessions.py
  test_web_job_builder.py
  test_web_preview.py
  test_web_api.py     # pełny przepływ end-to-end przez TestClient
```

Zasada: `web/` NIE importuje `summa_cut.preview` ani niczego z PySide6. Reużywa wyłącznie `summa_cut.{export,layout,opos,models,pdf_io}`.

Wspólny fixture źródłowego PDF i budowniczy parametrów powtarzają się w kilku plikach testowych — to świadome (testy mają być samodzielne); nie wydzielamy współdzielonego conftestu w tej fazie.

---

## Task 1: Zależności web + szkielet pakietu

**Files:**
- Create: `requirements-web.txt`, `web/__init__.py`
- Modify: `requirements.txt`

- [ ] **Step 1: Utworzyć `requirements-web.txt`**

```
fastapi>=0.110
uvicorn[standard]>=0.29
python-multipart>=0.0.9
```

- [ ] **Step 2: Dopisać httpx (test TestClient) do `requirements.txt`**

Dodaj linię pod `pytest>=8`:

```
httpx>=0.27
```

- [ ] **Step 3: Zainstalować w .venv**

Run: `cd ~/summa-cut && .venv/bin/pip install -r requirements-web.txt 'httpx>=0.27'`
Expected: instaluje fastapi, uvicorn, python-multipart, httpx bez błędów.

- [ ] **Step 4: Utworzyć pusty pakiet `web/__init__.py`**

Treść pliku `web/__init__.py`:

```python
```

(pusty plik)

- [ ] **Step 5: Smoke importu**

Run: `cd ~/summa-cut && .venv/bin/python -c "import fastapi, uvicorn, multipart; import web; print('ok')"`
Expected: `ok`

- [ ] **Step 6: Commit**

```bash
cd ~/summa-cut
git add requirements-web.txt requirements.txt web/__init__.py
git commit -m "build(web): zależności FastAPI + szkielet pakietu web"
```

---

## Task 2: Magazyn sesji (`web/sessions.py`)

**Files:**
- Create: `web/sessions.py`
- Test: `tests/test_web_sessions.py`

- [ ] **Step 1: Napisać testy**

Utwórz `tests/test_web_sessions.py`:

```python
from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from summa_cut.pdf_io import MM_PER_POINT
from web.sessions import SessionStore

PT = 1.0 / MM_PER_POINT


def _pdf_bytes() -> bytes:
    side = 40 * PT
    doc = fitz.open()
    page = doc.new_page(width=side, height=side)
    page.draw_rect(fitz.Rect(3, 3, side - 3, side - 3), color=(0, 0, 1), width=1.5)
    data = doc.tobytes()
    doc.close()
    return data


def test_create_makes_unique_sessions_with_workdir(tmp_path):
    store = SessionStore(base_dir=tmp_path)
    a = store.create()
    b = store.create()
    assert a.id != b.id
    assert Path(a.workdir).is_dir()
    assert store.get(a.id) is a
    assert store.get("nieistnieje") is None


def test_save_upload_returns_pdfinfo_and_stores_it(tmp_path):
    store = SessionStore(base_dir=tmp_path)
    s = store.create()
    info = store.save_upload(s, "plik.pdf", _pdf_bytes())
    assert info.page_count == 1
    assert info.name == "plik.pdf"
    assert "plik.pdf" in s.uploads
    assert Path(info.path).is_file()
    assert Path(info.path).parent == Path(s.workdir)


def test_save_upload_rejects_non_pdf(tmp_path):
    store = SessionStore(base_dir=tmp_path)
    s = store.create()
    with pytest.raises(ValueError):
        store.save_upload(s, "zly.pdf", b"to nie jest pdf")


def test_sweep_removes_expired_and_deletes_workdir(tmp_path):
    store = SessionStore(base_dir=tmp_path, ttl_seconds=0)
    s = store.create()
    workdir = Path(s.workdir)
    assert workdir.is_dir()
    store.sweep()
    assert store.get(s.id) is None
    assert not workdir.exists()
```

- [ ] **Step 2: Uruchomić — FAIL (brak modułu)**

Run: `cd ~/summa-cut && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_web_sessions.py -q`
Expected: FAIL (`ModuleNotFoundError: web.sessions`).

- [ ] **Step 3: Zaimplementować `web/sessions.py`**

```python
from __future__ import annotations

import secrets
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from summa_cut.pdf_io import PdfInfo, PdfReadError, read_pdf_info


@dataclass
class Session:
    id: str
    workdir: Path
    created: float
    last_seen: float
    uploads: dict[str, PdfInfo] = field(default_factory=dict)
    job_params: dict | None = None


class SessionStore:
    """Sesje w pamięci + katalog roboczy na dysku. Bez bazy danych.

    Każda sesja ma własny katalog `base_dir/<id>` na wgrane PDF-y i wyniki.
    `sweep()` usuwa sesje starsze niż TTL wraz z katalogiem."""

    def __init__(self, base_dir: str | Path, ttl_seconds: int = 6 * 3600) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = ttl_seconds
        self._sessions: dict[str, Session] = {}

    def create(self) -> Session:
        sid = secrets.token_urlsafe(16)
        workdir = self.base_dir / sid
        workdir.mkdir(parents=True, exist_ok=True)
        now = time.time()
        session = Session(id=sid, workdir=workdir, created=now, last_seen=now)
        self._sessions[sid] = session
        return session

    def get(self, sid: str | None) -> Session | None:
        if not sid:
            return None
        session = self._sessions.get(sid)
        if session is None:
            return None
        session.last_seen = time.time()
        return session

    def save_upload(self, session: Session, filename: str, data: bytes) -> PdfInfo:
        safe_name = Path(filename).name or "plik.pdf"
        target = session.workdir / safe_name
        target.write_bytes(data)
        try:
            info = read_pdf_info(str(target))
        except PdfReadError as exc:
            target.unlink(missing_ok=True)
            raise ValueError(str(exc)) from exc
        info.name = safe_name
        session.uploads[safe_name] = info
        return info

    def sweep(self) -> None:
        cutoff = time.time() - self.ttl_seconds
        for sid in list(self._sessions):
            session = self._sessions[sid]
            if session.last_seen <= cutoff:
                shutil.rmtree(session.workdir, ignore_errors=True)
                del self._sessions[sid]
```

- [ ] **Step 4: Uruchomić — PASS**

Run: `cd ~/summa-cut && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_web_sessions.py -q`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
cd ~/summa-cut
git add web/sessions.py tests/test_web_sessions.py
git commit -m "feat(web): magazyn sesji (pamięć + workdir + TTL + upload PDF)"
```

---

## Task 3: Builder zlecenia (`web/job_builder.py`)

**Files:**
- Create: `web/job_builder.py`
- Test: `tests/test_web_job_builder.py`

Mapuje parametry żądania na `JobSettings` dla pojedynczego produktu, odwzorowując walidacje z desktopu (`main_window._build_job_settings`).

- [ ] **Step 1: Napisać testy**

Utwórz `tests/test_web_job_builder.py`:

```python
from __future__ import annotations

import fitz
import pytest

from summa_cut.layout import compute_layout
from summa_cut.pdf_io import MM_PER_POINT
from web.sessions import SessionStore
from web.job_builder import JobParams, build_job

PT = 1.0 / MM_PER_POINT


def _pdf_bytes() -> bytes:
    side = 40 * PT
    doc = fitz.open()
    doc.new_page(width=side, height=side).draw_rect(fitz.Rect(3, 3, side - 3, side - 3), color=(0, 0, 1))
    data = doc.tobytes()
    doc.close()
    return data


def _session_with_pdf(tmp_path):
    store = SessionStore(base_dir=tmp_path)
    s = store.create()
    store.save_upload(s, "src.pdf", _pdf_bytes())
    return s


def _params(**over) -> JobParams:
    base = dict(
        print_upload="src.pdf", print_page=0,
        cut_upload="src.pdf", cut_page=0,
        sheet_w_mm=330.0, sheet_h_mm=480.0,
        item_w_mm=30.0, item_h_mm=30.0, rotation_allowed=False,
        gap_enabled=True, gap_mm=3.0,
    )
    base.update(over)
    return JobParams(**base)


def test_build_job_basic_grid_produces_placements(tmp_path):
    s = _session_with_pdf(tmp_path)
    job = build_job(_params(), s)
    assert job.gap_enabled is True
    assert job.generate_cut_grid is False
    layout = compute_layout(job)
    assert layout.count > 50


def test_gapless_forces_cut_equals_print_and_grid(tmp_path):
    s = _session_with_pdf(tmp_path)
    job = build_job(_params(gap_enabled=False, cut_upload=None, cut_page=None), s)
    assert job.generate_cut_grid is True
    assert job.gap_enabled is False
    assert job.cut_page.pdf_path == job.print_page.pdf_path
    assert job.cut_page.page_index == job.print_page.page_index


def test_unknown_upload_raises(tmp_path):
    s = _session_with_pdf(tmp_path)
    with pytest.raises(ValueError):
        build_job(_params(print_upload="brak.pdf"), s)


def test_page_index_out_of_range_raises(tmp_path):
    s = _session_with_pdf(tmp_path)
    with pytest.raises(ValueError):
        build_job(_params(print_page=5), s)


def test_zero_item_size_raises(tmp_path):
    s = _session_with_pdf(tmp_path)
    with pytest.raises(ValueError):
        build_job(_params(item_w_mm=0.0), s)


def test_gap_mode_requires_cut_selection(tmp_path):
    s = _session_with_pdf(tmp_path)
    with pytest.raises(ValueError):
        build_job(_params(cut_upload=None), s)


def test_manual_grid_odd_rows_with_split_raises(tmp_path):
    s = _session_with_pdf(tmp_path)
    with pytest.raises(ValueError):
        build_job(_params(manual_grid_enabled=True, manual_columns=3, manual_rows=3,
                          split_horizontal_groups=True), s)


def test_opos_offsets_passed_through(tmp_path):
    s = _session_with_pdf(tmp_path)
    job = build_job(_params(opos_side_offset_mm=12.0, opos_bottom_offset_mm=8.0, opos_top_offset_mm=35.0), s)
    assert job.opos_spec.side_offset_mm == 12.0
    assert job.opos_spec.bottom_offset_mm == 8.0
    assert job.opos_spec.top_offset_mm == 35.0
```

- [ ] **Step 2: Uruchomić — FAIL**

Run: `cd ~/summa-cut && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_web_job_builder.py -q`
Expected: FAIL (`ModuleNotFoundError: web.job_builder`).

- [ ] **Step 3: Zaimplementować `web/job_builder.py`**

```python
from __future__ import annotations

from pydantic import BaseModel, Field

from summa_cut.models import ItemSpec, JobSettings, OposSpec, SelectedPage, SheetSpec
from web.sessions import Session


class JobParams(BaseModel):
    """Parametry zlecenia (pojedynczy produkt). Montaż/tryb specjalny — później."""
    print_upload: str
    print_page: int = 0
    cut_upload: str | None = None
    cut_page: int | None = None

    sheet_w_mm: float = 330.0
    sheet_h_mm: float = 480.0
    item_w_mm: float
    item_h_mm: float
    rotation_allowed: bool = False

    gap_enabled: bool = True
    gap_mm: float = 3.0

    split_horizontal_groups: bool = False
    split_max_spread: bool = False
    manual_grid_enabled: bool = False
    manual_columns: int = 0
    manual_rows: int = 0

    opos_side_offset_mm: float = Field(default=10.0)
    opos_bottom_offset_mm: float = Field(default=10.0)
    opos_top_offset_mm: float = Field(default=40.0)


def _require_page(session: Session, upload: str, page_index: int, what: str):
    info = session.uploads.get(upload)
    if info is None:
        raise ValueError(f"Nie wgrano pliku: {upload} ({what}).")
    if page_index < 0 or page_index >= info.page_count:
        raise ValueError(f"Strona {page_index} poza zakresem pliku {upload} ({what}).")
    return info


def build_job(params: JobParams, session: Session) -> JobSettings:
    if params.item_w_mm <= 0 or params.item_h_mm <= 0:
        raise ValueError("Rozmiar użytku musi być większy od zera.")
    if params.sheet_w_mm <= 0 or params.sheet_h_mm <= 0:
        raise ValueError("Rozmiar arkusza musi być większy od zera.")

    with_gap = params.gap_enabled
    print_info = _require_page(session, params.print_upload, params.print_page, "druk")

    if with_gap:
        if not params.cut_upload or params.cut_page is None:
            raise ValueError("W trybie z odstępami wybierz też plik i stronę wykrojnika.")
        cut_upload, cut_page_index = params.cut_upload, params.cut_page
    else:
        cut_upload, cut_page_index = params.print_upload, params.print_page
    cut_info = _require_page(session, cut_upload, cut_page_index, "wykrojnik")

    if params.manual_grid_enabled:
        if params.manual_columns <= 0 or params.manual_rows <= 0:
            raise ValueError("W trybie manualnym liczba kolumn i rzędów musi być większa od zera.")
        if params.split_horizontal_groups and params.manual_rows % 2 == 1:
            raise ValueError("Przy podziale na 2 grupy manualna liczba rzędów musi być parzysta.")

    return JobSettings(
        print_page=SelectedPage(print_info.path, params.print_page),
        cut_page=SelectedPage(cut_info.path, cut_page_index),
        print_page_size_mm=print_info.page_sizes_mm[params.print_page],
        cut_page_size_mm=cut_info.page_sizes_mm[cut_page_index],
        print_content_size_mm=print_info.page_content_sizes_mm[params.print_page],
        cut_content_size_mm=cut_info.page_content_sizes_mm[cut_page_index],
        print_content_bbox_pt=print_info.page_content_boxes_pt[params.print_page],
        cut_content_bbox_pt=cut_info.page_content_boxes_pt[cut_page_index],
        sheet_spec=SheetSpec(params.sheet_w_mm, params.sheet_h_mm),
        item_spec=ItemSpec(params.item_w_mm, params.item_h_mm, params.rotation_allowed),
        gap_enabled=with_gap,
        gap_mm=params.gap_mm if with_gap else 0.0,
        generate_cut_grid=not with_gap,
        split_horizontal_groups=params.split_horizontal_groups,
        split_max_spread=params.split_horizontal_groups and params.split_max_spread,
        manual_grid_enabled=params.manual_grid_enabled,
        manual_columns=params.manual_columns,
        manual_rows=params.manual_rows,
        opos_spec=OposSpec(params.opos_side_offset_mm, params.opos_bottom_offset_mm, params.opos_top_offset_mm),
    )
```

- [ ] **Step 4: Uruchomić — PASS**

Run: `cd ~/summa-cut && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_web_job_builder.py -q`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
cd ~/summa-cut
git add web/job_builder.py tests/test_web_job_builder.py
git commit -m "feat(web): builder JobSettings z parametrów żądania (pojedynczy produkt)"
```

---

## Task 4: Render podglądu PNG (`web/preview_render.py`)

**Files:**
- Create: `web/preview_render.py`
- Test: `tests/test_web_preview.py`

- [ ] **Step 1: Napisać testy**

Utwórz `tests/test_web_preview.py`:

```python
from __future__ import annotations

import fitz
import pytest

from summa_cut.layout import compute_layout
from summa_cut.pdf_io import MM_PER_POINT
from web.sessions import SessionStore
from web.job_builder import JobParams, build_job
from web.preview_render import render_output_png

PT = 1.0 / MM_PER_POINT


def _job(tmp_path, **over):
    doc = fitz.open(); side = 40 * PT
    doc.new_page(width=side, height=side).draw_rect(fitz.Rect(3, 3, side - 3, side - 3), color=(0, 0, 1))
    data = doc.tobytes(); doc.close()
    store = SessionStore(base_dir=tmp_path); s = store.create()
    store.save_upload(s, "src.pdf", data)
    params = JobParams(print_upload="src.pdf", print_page=0, cut_upload="src.pdf", cut_page=0,
                       item_w_mm=30.0, item_h_mm=30.0, gap_enabled=True, gap_mm=3.0, **over)
    job = build_job(params, s)
    return job, compute_layout(job)


def test_render_print_returns_png_bytes(tmp_path):
    job, layout = _job(tmp_path)
    data = render_output_png(job, layout, which="print", max_px=400)
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(data) > 500


def test_render_cut_returns_png_bytes(tmp_path):
    job, layout = _job(tmp_path)
    data = render_output_png(job, layout, which="cut", max_px=400)
    assert data[:8] == b"\x89PNG\r\n\x1a\n"


def test_invalid_which_raises(tmp_path):
    job, layout = _job(tmp_path)
    with pytest.raises(ValueError):
        render_output_png(job, layout, which="bok", max_px=400)
```

- [ ] **Step 2: Uruchomić — FAIL**

Run: `cd ~/summa-cut && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_web_preview.py -q`
Expected: FAIL (`ModuleNotFoundError: web.preview_render`).

- [ ] **Step 3: Zaimplementować `web/preview_render.py`**

```python
from __future__ import annotations

import fitz

from summa_cut.export import generate_output_docs
from summa_cut.models import JobSettings, LayoutResult


def render_output_png(job: JobSettings, layout: LayoutResult, which: str = "print", max_px: int = 900) -> bytes:
    """Renderuje PRAWDZIWY wynik (druk/wykrojnik) do PNG przez fitz.

    Po Fazie 0 generowanie jest szybkie (~0,24 s @560), więc podgląd = realny
    wynik zrasteryzowany, a nie osobny silnik. Qt-free."""
    if which not in ("print", "cut"):
        raise ValueError(f"Nieznany podgląd: {which!r} (dozwolone: 'print', 'cut').")
    docs = generate_output_docs(job, layout)
    try:
        doc = docs.print_doc if which == "print" else docs.cut_doc
        page = doc[0]
        scale = max_px / max(page.rect.width, page.rect.height, 1.0)
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        return pix.tobytes("png")
    finally:
        docs.print_doc.close()
        docs.cut_doc.close()
```

- [ ] **Step 4: Uruchomić — PASS**

Run: `cd ~/summa-cut && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_web_preview.py -q`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
cd ~/summa-cut
git add web/preview_render.py tests/test_web_preview.py
git commit -m "feat(web): render podglądu PNG z realnego wyniku (fitz, Qt-free)"
```

---

## Task 5: Aplikacja FastAPI — sesja + upload

**Files:**
- Create: `web/server.py`
- Test: `tests/test_web_api.py`

- [ ] **Step 1: Napisać testy sesji+uploadu**

Utwórz `tests/test_web_api.py`:

```python
from __future__ import annotations

import fitz
from fastapi.testclient import TestClient

from summa_cut.pdf_io import MM_PER_POINT
from web.server import create_app
from web.sessions import SessionStore

PT = 1.0 / MM_PER_POINT


def _pdf_bytes() -> bytes:
    doc = fitz.open(); side = 40 * PT
    doc.new_page(width=side, height=side).draw_rect(fitz.Rect(3, 3, side - 3, side - 3), color=(0, 0, 1))
    data = doc.tobytes(); doc.close()
    return data


def _client(tmp_path) -> TestClient:
    app = create_app(store=SessionStore(base_dir=tmp_path))
    return TestClient(app)


def test_create_session_sets_cookie(tmp_path):
    c = _client(tmp_path)
    r = c.post("/api/session")
    assert r.status_code == 200
    assert "sid" in r.cookies or "sid" in c.cookies
    assert r.json()["session_id"]


def test_upload_returns_page_info(tmp_path):
    c = _client(tmp_path)
    c.post("/api/session")
    r = c.post("/api/upload", files={"file": ("src.pdf", _pdf_bytes(), "application/pdf")})
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "src.pdf"
    assert body["page_count"] == 1
    assert len(body["page_sizes_mm"]) == 1


def test_upload_without_session_is_401(tmp_path):
    c = _client(tmp_path)
    r = c.post("/api/upload", files={"file": ("src.pdf", _pdf_bytes(), "application/pdf")})
    assert r.status_code == 401


def test_upload_rejects_non_pdf(tmp_path):
    c = _client(tmp_path)
    c.post("/api/session")
    r = c.post("/api/upload", files={"file": ("x.pdf", b"nie-pdf", "application/pdf")})
    assert r.status_code == 400
```

- [ ] **Step 2: Uruchomić — FAIL**

Run: `cd ~/summa-cut && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_web_api.py -q`
Expected: FAIL (`ModuleNotFoundError: web.server`).

- [ ] **Step 3: Zaimplementować `web/server.py` (sesja + upload)**

```python
from __future__ import annotations

from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile

from web.sessions import Session, SessionStore


def create_app(store: SessionStore) -> FastAPI:
    app = FastAPI(title="summa-cut web")
    app.state.store = store

    def current_session(request: Request) -> Session:
        session = store.get(request.cookies.get("sid"))
        if session is None:
            raise HTTPException(status_code=401, detail="Brak aktywnej sesji.")
        return session

    @app.post("/api/session")
    def create_session(response: Response) -> dict:
        session = store.create()
        response.set_cookie("sid", session.id, httponly=True, samesite="lax")
        return {"session_id": session.id}

    @app.post("/api/upload")
    async def upload(session: Session = Depends(current_session), file: UploadFile = File(...)) -> dict:
        data = await file.read()
        try:
            info = store.save_upload(session, file.filename or "plik.pdf", data)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {
            "name": info.name,
            "page_count": info.page_count,
            "page_sizes_mm": info.page_sizes_mm,
            "page_content_sizes_mm": info.page_content_sizes_mm,
        }

    return app
```

- [ ] **Step 4: Uruchomić — PASS**

Run: `cd ~/summa-cut && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_web_api.py -q`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
cd ~/summa-cut
git add web/server.py tests/test_web_api.py
git commit -m "feat(web): FastAPI — sesja (ciasteczko) + upload PDF"
```

---

## Task 6: Trasy job + preview

**Files:**
- Modify: `web/server.py`
- Test: `tests/test_web_api.py`

- [ ] **Step 1: Dopisać testy job+preview**

Dodaj na końcu `tests/test_web_api.py`:

```python
def _session_with_upload(tmp_path):
    c = _client(tmp_path)
    c.post("/api/session")
    c.post("/api/upload", files={"file": ("src.pdf", _pdf_bytes(), "application/pdf")})
    return c


_JOB = dict(
    print_upload="src.pdf", print_page=0, cut_upload="src.pdf", cut_page=0,
    sheet_w_mm=330.0, sheet_h_mm=480.0, item_w_mm=30.0, item_h_mm=30.0,
    gap_enabled=True, gap_mm=3.0,
)


def test_job_returns_layout_summary(tmp_path):
    c = _session_with_upload(tmp_path)
    r = c.post("/api/job", json=_JOB)
    assert r.status_code == 200
    body = r.json()
    assert body["count"] > 50
    assert body["columns"] > 0 and body["rows"] > 0


def test_job_with_bad_params_is_400(tmp_path):
    c = _session_with_upload(tmp_path)
    r = c.post("/api/job", json={**_JOB, "item_w_mm": 0.0})
    assert r.status_code == 400


def test_preview_returns_png(tmp_path):
    c = _session_with_upload(tmp_path)
    c.post("/api/job", json=_JOB)
    r = c.get("/api/preview/print.png")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_preview_before_job_is_400(tmp_path):
    c = _session_with_upload(tmp_path)
    r = c.get("/api/preview/print.png")
    assert r.status_code == 400


def test_preview_bad_which_is_404(tmp_path):
    c = _session_with_upload(tmp_path)
    c.post("/api/job", json=_JOB)
    r = c.get("/api/preview/bok.png")
    assert r.status_code == 404
```

- [ ] **Step 2: Uruchomić — FAIL (nowe testy)**

Run: `cd ~/summa-cut && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_web_api.py -q`
Expected: nowe testy FAIL (404 dla nieistniejących tras), stare 4 PASS.

- [ ] **Step 3: Dodać trasy job+preview do `web/server.py`**

Zmień importy na górze `web/server.py`:

```python
from __future__ import annotations

from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import Response as RawResponse

from summa_cut.layout import compute_layout
from web.job_builder import JobParams, build_job
from web.preview_render import render_output_png
from web.sessions import Session, SessionStore
```

Wewnątrz `create_app`, PRZED `return app`, dodaj:

```python
    @app.post("/api/job")
    def set_job(params: JobParams, session: Session = Depends(current_session)) -> dict:
        try:
            job = build_job(params, session)
            layout = compute_layout(job)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        session.job_params = params.model_dump()
        return {
            "count": layout.count,
            "capacity_count": layout.capacity_count,
            "requested_count": layout.requested_count,
            "rows": layout.rows,
            "columns": layout.columns,
            "used_rotation": layout.used_rotation,
        }

    def _job_and_layout(session: Session):
        if session.job_params is None:
            raise HTTPException(status_code=400, detail="Najpierw ustaw zlecenie (/api/job).")
        job = build_job(JobParams(**session.job_params), session)
        return job, compute_layout(job)

    @app.get("/api/preview/{which}.png")
    def preview(which: str, session: Session = Depends(current_session)) -> RawResponse:
        if which not in ("print", "cut"):
            raise HTTPException(status_code=404, detail="Nieznany podgląd.")
        job, layout = _job_and_layout(session)
        png = render_output_png(job, layout, which=which, max_px=900)
        return RawResponse(content=png, media_type="image/png")
```

- [ ] **Step 4: Uruchomić — PASS**

Run: `cd ~/summa-cut && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_web_api.py -q`
Expected: wszystkie passed (4 + 5).

- [ ] **Step 5: Commit**

```bash
cd ~/summa-cut
git add web/server.py tests/test_web_api.py
git commit -m "feat(web): trasy /api/job (layout) + /api/preview/{which}.png"
```

---

## Task 7: Trasy generate + download

**Files:**
- Modify: `web/server.py`
- Test: `tests/test_web_api.py`

- [ ] **Step 1: Dopisać testy generate+download**

Dodaj na końcu `tests/test_web_api.py`:

```python
def test_generate_then_download_pdfs(tmp_path):
    c = _session_with_upload(tmp_path)
    c.post("/api/job", json=_JOB)
    r = c.post("/api/generate", json={"base_name": "moj_arkusz"})
    assert r.status_code == 200
    names = r.json()
    assert names["print_name"] == "moj_arkusz_druk.pdf"
    assert names["cut_name"] == "moj_arkusz_wykrojnik.pdf"

    rp = c.get("/api/download/print")
    assert rp.status_code == 200
    assert rp.headers["content-type"] == "application/pdf"
    assert rp.content[:5] == b"%PDF-"

    rc = c.get("/api/download/cut")
    assert rc.status_code == 200
    assert rc.content[:5] == b"%PDF-"


def test_generate_before_job_is_400(tmp_path):
    c = _session_with_upload(tmp_path)
    r = c.post("/api/generate", json={"base_name": "x"})
    assert r.status_code == 400


def test_download_before_generate_is_404(tmp_path):
    c = _session_with_upload(tmp_path)
    c.post("/api/job", json=_JOB)
    r = c.get("/api/download/print")
    assert r.status_code == 404
```

- [ ] **Step 2: Uruchomić — FAIL (nowe testy)**

Run: `cd ~/summa-cut && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_web_api.py -q`
Expected: nowe testy FAIL, reszta PASS.

- [ ] **Step 3: Dodać trasy generate+download do `web/server.py`**

Dodaj do importów na górze:

```python
from pathlib import Path

from pydantic import BaseModel

from fastapi.responses import FileResponse

from summa_cut.export import generate_output_docs, save_output_docs
```

Dodaj model PRZED `def create_app` (poziom modułu):

```python
class GenerateParams(BaseModel):
    base_name: str = "wynik"
```

Wewnątrz `create_app`, PRZED `return app`, dodaj:

```python
    @app.post("/api/generate")
    def generate(body: GenerateParams, session: Session = Depends(current_session)) -> dict:
        job, layout = _job_and_layout(session)
        docs = generate_output_docs(job, layout)
        try:
            print_path, cut_path = save_output_docs(docs, session.workdir, base_name=body.base_name)
        finally:
            docs.print_doc.close()
            docs.cut_doc.close()
        session.job_params["_print_name"] = print_path.name
        session.job_params["_cut_name"] = cut_path.name
        return {"print_name": print_path.name, "cut_name": cut_path.name}

    @app.get("/api/download/{which}")
    def download(which: str, session: Session = Depends(current_session)) -> FileResponse:
        if which not in ("print", "cut"):
            raise HTTPException(status_code=404, detail="Nieznany plik.")
        key = "_print_name" if which == "print" else "_cut_name"
        name = (session.job_params or {}).get(key)
        if not name:
            raise HTTPException(status_code=404, detail="Najpierw wygeneruj wynik (/api/generate).")
        path = Path(session.workdir) / name
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Plik wyniku nie istnieje.")
        return FileResponse(path, media_type="application/pdf", filename=name)
```

Uwaga: `_job_and_layout` buduje `JobParams(**session.job_params)`, więc dodatkowe klucze `_print_name`/`_cut_name` zaśmieciłyby walidację. Aby tego uniknąć, w `_job_and_layout` odfiltruj prywatne klucze — zmień jego treść na:

```python
    def _job_and_layout(session: Session):
        if session.job_params is None:
            raise HTTPException(status_code=400, detail="Najpierw ustaw zlecenie (/api/job).")
        clean = {k: v for k, v in session.job_params.items() if not k.startswith("_")}
        job = build_job(JobParams(**clean), session)
        return job, compute_layout(job)
```

- [ ] **Step 4: Uruchomić — PASS**

Run: `cd ~/summa-cut && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_web_api.py -q`
Expected: wszystkie passed.

- [ ] **Step 5: Commit**

```bash
cd ~/summa-cut
git add web/server.py tests/test_web_api.py
git commit -m "feat(web): trasy /api/generate + /api/download/{which}"
```

---

## Task 8: Punkt wejścia serwera + regresja całości

**Files:**
- Create: `web/app.py` (ASGI entrypoint)

- [ ] **Step 1: Utworzyć `web/app.py`**

```python
"""Punkt wejścia ASGI dla uvicorna: `uvicorn web.app:app`.

Domyślny magazyn sesji w katalogu tymczasowym; nasłuch tylko lokalny/sieciowy
(bez publicznego wystawienia) konfigurujemy na poziomie kontenera w Fazie 4."""
from __future__ import annotations

import tempfile
from pathlib import Path

from web.server import create_app
from web.sessions import SessionStore

_BASE = Path(tempfile.gettempdir()) / "summa-cut-web"
app = create_app(store=SessionStore(base_dir=_BASE))
```

- [ ] **Step 2: Smoke — aplikacja startuje i odpowiada**

Run:
```bash
cd ~/summa-cut && QT_QPA_PLATFORM=offscreen .venv/bin/python -c "
from fastapi.testclient import TestClient
from web.app import app
c = TestClient(app)
r = c.post('/api/session')
print('session', r.status_code, bool(r.json().get('session_id')))
"
```
Expected: `session 200 True`

- [ ] **Step 3: Cały zestaw testów przechodzi**

Run: `cd ~/summa-cut && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -q`
Expected: wszystkie passed (Faza 0: 13 + web: sessions 4, job_builder 8, preview 3, api 13 = 41).

- [ ] **Step 4: Smoke realnego serwera uvicorn (start → zapytanie → stop)**

Run:
```bash
cd ~/summa-cut && QT_QPA_PLATFORM=offscreen .venv/bin/python -m uvicorn web.app:app --port 8011 &
UVPID=$!; sleep 2
.venv/bin/python -c "import urllib.request,json; r=urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8011/api/session', method='POST')); print('http', r.status)"
kill $UVPID
```
Expected: `http 200` (potem proces zatrzymany).

- [ ] **Step 5: Commit + tag**

```bash
cd ~/summa-cut
git add web/app.py
git commit -m "feat(web): punkt wejścia ASGI (uvicorn web.app:app)"
git tag -a phase1-backend -m "Phase 1: backend API FastAPI (sesja/upload/job/preview/generate/download)"
```

---

## Self-Review (autor planu)

**Pokrycie specu (Faza 1 = sesje, upload, layout, podgląd PNG, generuj, pobierz, headless, otestowane):**
- Sesje ✔ Task 2 (`SessionStore` + workdir + TTL). Upload ✔ Task 2 (`save_upload`) + Task 5 (`/api/upload`). Layout ✔ Task 3 (`build_job`) + Task 6 (`/api/job`). Podgląd PNG ✔ Task 4 (`render_output_png`) + Task 6 (`/api/preview`). Generuj/pobierz ✔ Task 7. Headless ✔ — `web/` importuje wyłącznie `summa_cut.{export,layout,opos,models,pdf_io}` (potwierdzone Qt-free), nie `summa_cut.preview`. Otestowane ✔ — 28 testów web (`TestClient`), bez przeglądarki/Qt.
- Świadomie POZA Fazą 1 (zgodnie ze specem — późniejsze fazy): montaż wielu użytków, tryb specjalny, front HTML, Docker/deploy. `JobParams`/`build_job` zaprojektowane pod rozszerzenie.

**Placeholdery:** brak „TODO/TBD". Każdy krok ma pełny kod lub komendę z oczekiwanym wynikiem.

**Spójność typów/nazw:**
- `SessionStore(base_dir, ttl_seconds)`, `.create()→Session`, `.get(sid)→Session|None`, `.save_upload(session, filename, data)→PdfInfo`, `.sweep()` — używane spójnie w Task 2/3/4/5/6/7.
- `Session.uploads: dict[str, PdfInfo]`, `Session.job_params: dict|None`, `Session.workdir: Path` — spójne.
- `PdfInfo` (z `summa_cut.pdf_io`) pola: `name, path, page_count, page_sizes_mm, page_content_sizes_mm, page_content_boxes_pt` — używane w `build_job` i `/api/upload`.
- `JobParams(...)` pola identyczne w job_builder, preview teście i `_JOB` w api teście. `build_job(params, session)→JobSettings`.
- `render_output_png(job, layout, which, max_px)→bytes` — Task 4 i `/api/preview`.
- `create_app(store)→FastAPI`; zależność `current_session`; `_job_and_layout(session)` odfiltrowuje klucze `_*` (spójne z zapisem `_print_name`/`_cut_name` w Task 7).
- `generate_output_docs`/`save_output_docs`/`OutputDocs` — publiczne API rdzenia z Fazy 0, niezmienione.

**Ryzyka do pilnowania w trakcie:**
1. `TestClient` wymaga `httpx` (dodany w Task 1). Jeśli import `fastapi.testclient` zawiedzie → doinstaluj `httpx`.
2. Cookie w `TestClient`: klient utrzymuje ciasteczka między żądaniami w obrębie jednej instancji `TestClient` — testy zakładają jeden klient na sesję.
3. `_job_and_layout` MUSI odfiltrować prywatne klucze (`_print_name`/`_cut_name`) przed `JobParams(**...)`, inaczej walidacja pydantic odrzuci nadmiarowe pola (pydantic v2 domyślnie ignoruje? — `JobParams` nie ma `model_config extra=forbid`, więc ignoruje nadmiarowe; mimo to filtr zostawiamy dla jasności i bezpieczeństwa).
4. Render podglądu przy `max_px=900` woła `generate_output_docs` (po Fazie 0 ~0,24 s) — akceptowalne; w razie potrzeby cache dojdzie w Fazie 2.
```
