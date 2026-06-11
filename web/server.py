from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from pydantic import BaseModel

from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from fastapi.responses import Response as RawResponse
from fastapi.staticfiles import StaticFiles

from summa_cut.export import generate_output_docs, save_output_docs
from summa_cut.layout import compute_layout
from summa_cut.special_trim import prepare_special_trim
from web.job_builder import JobParams, _require_page, build_job
from web.preview_render import render_output_png
from web.sessions import Session, SessionStore


class GenerateParams(BaseModel):
    base_name: str = "wynik"


class SpecialPrepareParams(BaseModel):
    print_upload: str
    print_page: int = 0
    cut_upload: str
    cut_page: int = 0
    bleed_mm: float = 3.0


def create_app(store: SessionStore) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        async def _sweeper():
            while True:
                await asyncio.sleep(3600)
                store.sweep()
        task = asyncio.create_task(_sweeper())
        try:
            yield
        finally:
            task.cancel()

    app = FastAPI(title="summa-cut web", lifespan=lifespan)
    app.state.store = store

    _static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(_static_dir / "index.html")

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

    @app.post("/api/special/prepare")
    def special_prepare(params: SpecialPrepareParams, session: Session = Depends(current_session)) -> dict:
        if params.print_upload not in session.uploads or params.cut_upload not in session.uploads:
            raise HTTPException(status_code=400, detail="Najpierw wgraj pliki druku i wykrojnika.")
        try:
            print_info = _require_page(session, params.print_upload, params.print_page, "druk (tryb specjalny)")
            cut_info = _require_page(session, params.cut_upload, params.cut_page, "wykrojnik (tryb specjalny)")
            result = prepare_special_trim(
                print_pdf_path=print_info.path, print_page=params.print_page,
                cut_pdf_path=cut_info.path, cut_page=params.cut_page,
                bleed_mm=params.bleed_mm, out_dir=session.workdir,
            )
            print_reg = store.save_upload(session, result.print_path.name, result.print_path.read_bytes())
            cut_reg = store.save_upload(session, result.cut_path.name, result.cut_path.read_bytes())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {
            "print_upload": print_reg.name,
            "cut_upload": cut_reg.name,
            "page_width_mm": result.page_width_mm,
            "page_height_mm": result.page_height_mm,
        }

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
        png = render_output_png(job, layout, which=which)
        return RawResponse(content=png, media_type="image/png")

    @app.post("/api/generate")
    def generate(body: GenerateParams, session: Session = Depends(current_session)) -> dict:
        job, layout = _job_and_layout(session)
        docs = generate_output_docs(job, layout)
        try:
            print_path, cut_path = save_output_docs(docs, session.workdir, base_name=body.base_name)
        finally:
            docs.print_doc.close()
            docs.cut_doc.close()
        session.result_print_name = print_path.name
        session.result_cut_name = cut_path.name
        return {"print_name": print_path.name, "cut_name": cut_path.name}

    @app.get("/api/download/{which}")
    def download(which: str, session: Session = Depends(current_session)) -> FileResponse:
        if which not in ("print", "cut"):
            raise HTTPException(status_code=404, detail="Nieznany plik.")
        name = session.result_print_name if which == "print" else session.result_cut_name
        if not name:
            raise HTTPException(status_code=404, detail="Najpierw wygeneruj wynik (/api/generate).")
        path = Path(session.workdir) / name
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Plik wyniku nie istnieje.")
        return FileResponse(path, media_type="application/pdf", filename=name)

    return app
